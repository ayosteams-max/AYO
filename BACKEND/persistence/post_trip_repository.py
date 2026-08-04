from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update

from BACKEND.persistence.tables import (
    post_trip_outbox,
    post_trip_records,
    preference_signals,
    trip_cash_confirmations,
    trip_evidence_packages,
    trip_ratings,
    trip_receipts,
)
from BACKEND.post_trip.engine import PostTripConflict
from BACKEND.post_trip.models import (
    CashConfirmation,
    CashSettlementState,
    FinancialBreakdown,
    PostTripRecord,
    PostTripState,
    PreferenceSignal,
    Rating,
    Receipt,
    TripEvidencePackage,
)


class PostgresPostTripRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def package_for_ride(self, ride_id: UUID) -> TripEvidencePackage | None:
        row = self._connection.execute(
            select(trip_evidence_packages.c.payload).where(
                trip_evidence_packages.c.ride_id == ride_id
            )
        ).scalar_one_or_none()
        return None if row is None else TripEvidencePackage.model_validate(row)

    def create_package(
        self, package: TripEvidencePackage, breakdown: FinancialBreakdown
    ) -> PostTripRecord:
        existing = self.package_for_ride(package.ride_id)
        if existing is not None:
            if existing.package_hash != package.package_hash:
                raise PostTripConflict("trip_evidence_conflict")
            record = self.get(package.ride_id)
            if record is None:
                raise PostTripConflict("post_trip_record_missing")
            return record
        self._connection.execute(
            insert(trip_evidence_packages).values(
                package_id=package.package_id,
                ride_id=package.ride_id,
                payload=package.model_dump(mode="json"),
                package_hash=package.package_hash,
                finalized_at=package.finalized_at,
            )
        )
        record = PostTripRecord(
            ride_id=package.ride_id,
            package_id=package.package_id,
            state=PostTripState.AWAITING_SETTLEMENT,
            cash_state=CashSettlementState.AWAITING_CONFIRMATIONS
            if package.payment_method.value == "cash"
            else None,
            financial_breakdown=breakdown,
            version=1,
        )
        self._connection.execute(
            insert(post_trip_records).values(**record.model_dump(mode="json"))
        )
        return record

    def get(self, ride_id: UUID, *, lock: bool = False) -> PostTripRecord | None:
        query = select(post_trip_records).where(post_trip_records.c.ride_id == ride_id)
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else PostTripRecord.model_validate(dict(row))

    def add_cash_confirmation(
        self, item: CashConfirmation
    ) -> tuple[tuple[CashConfirmation, ...], bool]:
        existing = (
            self._connection.execute(
                select(trip_cash_confirmations).where(
                    trip_cash_confirmations.c.ride_id == item.ride_id,
                    trip_cash_confirmations.c.actor_role == item.actor_role,
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            replay = CashConfirmation.model_validate(dict(existing))
            if (
                replay.actor_identity_id != item.actor_identity_id
                or replay.confirmed != item.confirmed
                or replay.idempotency_key_hash != item.idempotency_key_hash
            ):
                raise PostTripConflict("cash_confirmation_already_submitted")
            return self.cash_confirmations(item.ride_id), False
        else:
            self._connection.execute(
                insert(trip_cash_confirmations).values(**item.model_dump())
            )
        return self.cash_confirmations(item.ride_id), True

    def cash_confirmations(self, ride_id: UUID) -> tuple[CashConfirmation, ...]:
        rows = self._connection.execute(
            select(trip_cash_confirmations)
            .where(trip_cash_confirmations.c.ride_id == ride_id)
            .order_by(trip_cash_confirmations.c.recorded_at)
        ).mappings()
        return tuple(CashConfirmation.model_validate(dict(row)) for row in rows)

    def update_cash_state(
        self, ride_id: UUID, state: str, expected_version: int
    ) -> PostTripRecord:
        result = self._connection.execute(
            update(post_trip_records)
            .where(
                post_trip_records.c.ride_id == ride_id,
                post_trip_records.c.version == expected_version,
            )
            .values(cash_state=state, version=expected_version + 1)
        )
        if result.rowcount != 1:
            raise PostTripConflict("stale_post_trip_record")
        record = self.get(ride_id)
        if record is None:
            raise PostTripConflict("post_trip_record_missing")
        return record

    def add_rating(self, item: Rating) -> Rating:
        existing = (
            self._connection.execute(
                select(trip_ratings).where(
                    trip_ratings.c.ride_id == item.ride_id,
                    trip_ratings.c.author_identity_id == item.author_identity_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            replay = Rating.model_validate(dict(existing))
            if (
                replay.stars != item.stars
                or replay.feedback != item.feedback
                or replay.preference_requested != item.preference_requested
            ):
                raise PostTripConflict("rating_already_submitted")
            return replay
        self._connection.execute(insert(trip_ratings).values(**item.model_dump()))
        return item

    def upsert_preference(self, item: PreferenceSignal) -> PreferenceSignal:
        existing = (
            self._connection.execute(
                select(preference_signals).where(
                    preference_signals.c.owner_identity_id == item.owner_identity_id,
                    preference_signals.c.capability == item.capability,
                    preference_signals.c.target_type == item.target_type,
                    preference_signals.c.target_identity_id == item.target_identity_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing is None:
            self._connection.execute(
                insert(preference_signals).values(**item.model_dump())
            )
            return item
        return PreferenceSignal.model_validate(dict(existing))

    def add_receipt(self, item: Receipt) -> Receipt:
        existing = (
            self._connection.execute(
                select(trip_receipts).where(
                    trip_receipts.c.ride_id == item.ride_id,
                    trip_receipts.c.receipt_type == item.receipt_type,
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            replay = Receipt.model_validate(dict(existing))
            if replay.payload_hash != item.payload_hash:
                raise PostTripConflict("receipt_conflict")
            return replay
        self._connection.execute(
            insert(trip_receipts).values(**item.model_dump(mode="json"))
        )
        return item

    def receipts_for(self, ride_id: UUID, identity_id: UUID) -> tuple[Receipt, ...]:
        rows = self._connection.execute(
            select(trip_receipts)
            .where(
                trip_receipts.c.ride_id == ride_id,
                trip_receipts.c.issued_to_identity_id == identity_id,
            )
            .order_by(trip_receipts.c.issued_at)
        ).mappings()
        return tuple(Receipt.model_validate(dict(row)) for row in rows)

    def notification_intent(
        self,
        *,
        ride_id: UUID,
        event_type: str,
        recipient_identity_id: UUID,
        payload: dict[str, object],
        at,
    ) -> None:
        self._connection.execute(
            insert(post_trip_outbox).values(
                message_id=uuid4(),
                ride_id=ride_id,
                event_type=event_type,
                recipient_identity_id=recipient_identity_id,
                safe_payload=payload,
                occurred_at=at,
                attempt_count=0,
            )
        )

    def mark_settled(
        self,
        ride_id: UUID,
        *,
        journal_id: UUID,
        wallet_entry_id: UUID | None,
        rider_receipt_id: UUID,
        driver_receipt_id: UUID,
        expected_version: int,
    ) -> PostTripRecord:
        result = self._connection.execute(
            update(post_trip_records)
            .where(
                post_trip_records.c.ride_id == ride_id,
                post_trip_records.c.version == expected_version,
            )
            .values(
                state=PostTripState.SETTLED.value,
                ledger_journal_id=journal_id,
                wallet_entry_id=wallet_entry_id,
                rider_receipt_id=rider_receipt_id,
                driver_receipt_id=driver_receipt_id,
                version=expected_version + 1,
            )
        )
        if result.rowcount != 1:
            raise PostTripConflict("stale_post_trip_record")
        record = self.get(ride_id)
        if record is None:
            raise PostTripConflict("post_trip_record_missing")
        return record

    def archive(self, ride_id: UUID, *, at, expected_version: int) -> PostTripRecord:
        result = self._connection.execute(
            update(post_trip_records)
            .where(
                post_trip_records.c.ride_id == ride_id,
                post_trip_records.c.state == PostTripState.SETTLED.value,
                post_trip_records.c.version == expected_version,
            )
            .values(
                state=PostTripState.ARCHIVED.value,
                archived_at=at,
                version=expected_version + 1,
            )
        )
        if result.rowcount != 1:
            raise PostTripConflict("archive_not_ready")
        record = self.get(ride_id)
        if record is None:
            raise PostTripConflict("post_trip_record_missing")
        return record
