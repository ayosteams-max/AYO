from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update

from BACKEND.persistence.tables import (
    cash_accounting_policies,
    cash_reconciliation_evidence,
    post_trip_outbox,
    post_trip_records,
    preference_signals,
    trip_cash_accounting_records,
    trip_cash_collection_evidence,
    trip_cash_confirmations,
    trip_evidence_packages,
    trip_ratings,
    trip_receipts,
)
from BACKEND.post_trip.cash_accounting import (
    CashAccountingPolicy,
    CashAccountingRecord,
    CashCollectionEvidence,
    CashReconciliationEvidence,
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
            cash_evidence_state=(
                "awaiting_confirmations"
                if package.payment_method.value == "cash"
                else None
            ),
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

    def add_cash_collection_evidence(
        self, item: CashCollectionEvidence
    ) -> CashCollectionEvidence:
        existing = self.cash_collection_evidence(item.ride_id)
        if existing is not None:
            if existing.evidence_hash != item.evidence_hash:
                raise PostTripConflict("cash_collection_evidence_conflict")
            return existing
        self._connection.execute(
            insert(trip_cash_collection_evidence).values(
                evidence_id=item.evidence_id,
                ride_id=item.ride_id,
                fare_calculation_id=item.fare_calculation_id,
                state=item.state.value,
                payload=item.model_dump(mode="json"),
                evidence_hash=item.evidence_hash,
                recorded_at=item.recorded_at,
            )
        )
        return item

    def cash_collection_evidence(self, ride_id: UUID) -> CashCollectionEvidence | None:
        payload = self._connection.execute(
            select(trip_cash_collection_evidence.c.payload).where(
                trip_cash_collection_evidence.c.ride_id == ride_id
            )
        ).scalar_one_or_none()
        return (
            None if payload is None else CashCollectionEvidence.model_validate(payload)
        )

    def add_cash_accounting_policy(
        self, item: CashAccountingPolicy
    ) -> CashAccountingPolicy:
        self._connection.execute(
            insert(cash_accounting_policies).values(
                accounting_policy_id=item.accounting_policy_id,
                accounting_policy_version=item.accounting_policy_version,
                environment=item.environment.value,
                accounting_model=item.accounting_model.value,
                payload=item.model_dump(mode="json"),
                policy_evidence_hash=item.policy_evidence_hash,
            )
        )
        return item

    def cash_accounting_policy(self, policy_id: UUID) -> CashAccountingPolicy | None:
        payload = self._connection.execute(
            select(cash_accounting_policies.c.payload).where(
                cash_accounting_policies.c.accounting_policy_id == policy_id
            )
        ).scalar_one_or_none()
        return None if payload is None else CashAccountingPolicy.model_validate(payload)

    def add_cash_accounting_record(
        self, item: CashAccountingRecord
    ) -> CashAccountingRecord:
        existing = self.cash_accounting_record(item.ride_id)
        if existing is not None:
            if existing.instruction_id != item.instruction_id:
                raise PostTripConflict("cash_accounting_record_conflict")
            return existing
        self._connection.execute(
            insert(trip_cash_accounting_records).values(
                ride_id=item.ride_id,
                evidence_id=item.evidence_id,
                instruction_id=item.instruction_id,
                accounting_policy_id=item.accounting_policy_id,
                accounting_policy_version=item.accounting_policy_version,
                state=item.state.value,
                reconciliation_state=item.reconciliation_state.value,
                ledger_journal_id=item.ledger_journal_id,
                clearing_journal_id=item.clearing_journal_id,
                reconciliation_evidence_hash=item.reconciliation_evidence_hash,
                payload=item.model_dump(mode="json"),
                version=item.version,
            )
        )
        return item

    def cash_accounting_record(self, ride_id: UUID) -> CashAccountingRecord | None:
        payload = self._connection.execute(
            select(trip_cash_accounting_records.c.payload).where(
                trip_cash_accounting_records.c.ride_id == ride_id
            )
        ).scalar_one_or_none()
        return None if payload is None else CashAccountingRecord.model_validate(payload)

    def update_cash_accounting_record(
        self, item: CashAccountingRecord, *, expected_version: int
    ) -> CashAccountingRecord:
        changed = item.model_copy(update={"version": expected_version + 1})
        result = self._connection.execute(
            update(trip_cash_accounting_records)
            .where(
                trip_cash_accounting_records.c.ride_id == item.ride_id,
                trip_cash_accounting_records.c.version == expected_version,
            )
            .values(
                state=changed.state.value,
                reconciliation_state=changed.reconciliation_state.value,
                ledger_journal_id=changed.ledger_journal_id,
                clearing_journal_id=changed.clearing_journal_id,
                reconciliation_evidence_hash=changed.reconciliation_evidence_hash,
                payload=changed.model_dump(mode="json"),
                version=changed.version,
            )
        )
        if result.rowcount != 1:
            raise PostTripConflict("stale_cash_accounting_record")
        return changed

    def add_cash_reconciliation_evidence(
        self, item: CashReconciliationEvidence
    ) -> CashReconciliationEvidence:
        existing = self.cash_reconciliation_evidence(item.ride_id)
        if existing is not None:
            if existing != item:
                raise PostTripConflict("cash_reconciliation_evidence_conflict")
            return existing
        self._connection.execute(
            insert(cash_reconciliation_evidence).values(
                reconciliation_evidence_id=item.reconciliation_evidence_id,
                ride_id=item.ride_id,
                accounting_instruction_id=item.accounting_instruction_id,
                accounting_policy_id=item.accounting_policy_id,
                original_accounting_journal_id=item.original_accounting_journal_id,
                evidence_hash=item.evidence_hash,
                payload=item.model_dump(mode="json"),
                occurred_at=item.occurred_at,
            )
        )
        return item

    def cash_reconciliation_evidence(
        self, ride_id: UUID
    ) -> CashReconciliationEvidence | None:
        payload = self._connection.execute(
            select(cash_reconciliation_evidence.c.payload).where(
                cash_reconciliation_evidence.c.ride_id == ride_id
            )
        ).scalar_one_or_none()
        return (
            None
            if payload is None
            else CashReconciliationEvidence.model_validate(payload)
        )

    def update_cash_state(
        self, ride_id: UUID, state: str, expected_version: int
    ) -> PostTripRecord:
        evidence_state = {
            "awaiting_confirmations": "awaiting_confirmations",
            "partially_confirmed": "partially_confirmed",
            "cash_settled": "collection_corroborated",
            "cash_settlement_review": "cash_settlement_review",
        }[state]
        result = self._connection.execute(
            update(post_trip_records)
            .where(
                post_trip_records.c.ride_id == ride_id,
                post_trip_records.c.version == expected_version,
            )
            .values(
                cash_state=state,
                cash_evidence_state=evidence_state,
                version=expected_version + 1,
            )
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

    def mark_cash_accounting_evidenced(
        self,
        ride_id: UUID,
        *,
        journal_id: UUID,
        rider_receipt_id: UUID,
        driver_receipt_id: UUID,
        expected_version: int,
    ) -> PostTripRecord:
        result = self._connection.execute(
            update(post_trip_records)
            .where(
                post_trip_records.c.ride_id == ride_id,
                post_trip_records.c.state == PostTripState.AWAITING_SETTLEMENT.value,
                post_trip_records.c.version == expected_version,
            )
            .values(
                ledger_journal_id=journal_id,
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
