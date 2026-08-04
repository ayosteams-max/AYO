from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.exc import IntegrityError

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome
from BACKEND.dispatch.contracts import DispatchConflict, IdempotencyConflict
from BACKEND.dispatch.models import (
    DispatchRide,
    DispatchScore,
    DriverCandidate,
    DriverOffer,
    OfferState,
    PlaceSnapshot,
    QuoteSnapshot,
    RideState,
)
from BACKEND.persistence.audit_repository import PostgresAuditEventRepository
from BACKEND.persistence.tables import (
    dispatch_assignments,
    dispatch_attempts,
    dispatch_driver_offers,
    dispatch_idempotency_records,
    dispatch_outbox,
    dispatch_ride_requests,
)


class DriverCandidateGateway(Protocol):
    """Bounded provider-neutral source of eligible driver snapshots."""

    def list_candidates(
        self, *, ride: DispatchRide, now: datetime, limit: int
    ) -> list[DriverCandidate]: ...


class NoDriverCandidateGateway:
    def list_candidates(
        self, *, ride: DispatchRide, now: datetime, limit: int
    ) -> list[DriverCandidate]:
        del ride, now, limit
        return []


def _score_payload(score: DispatchScore) -> dict[str, Any]:
    return score.model_dump(mode="json")


def _ride_from_row(row: Mapping[Any, Any]) -> DispatchRide:
    return DispatchRide(
        ride_id=row["ride_id"],
        rider_id=row["rider_identity_id"],
        pickup=PlaceSnapshot(
            place_id=row["pickup_place_id"], display_name=row["pickup_display_name"]
        ),
        destination=PlaceSnapshot(
            place_id=row["destination_place_id"],
            display_name=row["destination_display_name"],
        ),
        service_type=row["service_type"],
        quote=QuoteSnapshot(
            quote_id=row["quote_id"],
            amount_minor=row["fare_amount_minor"],
            currency=row["currency"],
            pricing_version=row["pricing_version"],
            expires_at=row["quote_expires_at"],
        ),
        state=RideState(row["state"]),
        accepted_at=row["accepted_at"],
        updated_at=row["updated_at"],
        version=row["version"],
        assigned_driver_id=row["assigned_driver_identity_id"],
        active_offer_id=row["active_offer_id"],
        attempted_driver_ids=frozenset(
            UUID(value) for value in row["attempted_driver_ids"]
        ),
    )


def _offer_from_row(row: Mapping[Any, Any]) -> DriverOffer:
    payload = dict(row["score_snapshot"])
    payload["trust_score"] = Decimal(str(payload["trust_score"]))
    return DriverOffer(
        offer_id=row["offer_id"],
        ride_id=row["ride_id"],
        driver_id=row["driver_identity_id"],
        state=OfferState(row["state"]),
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        policy_version=row["policy_version"],
        score=DispatchScore.model_validate(payload),
        version=row["version"],
    )


class PostgresDispatchRepository:
    """Transactional PostgreSQL authority for immediate dispatch."""

    def __init__(
        self,
        connection: Connection,
        candidate_gateway: DriverCandidateGateway | None = None,
    ) -> None:
        self._connection = connection
        self._candidates = candidate_gateway or NoDriverCandidateGateway()
        self._audit = PostgresAuditEventRepository(connection)

    def _outbox(
        self, event_type: str, ride_id: UUID, occurred_at: datetime, **payload: Any
    ) -> None:
        self._connection.execute(
            insert(dispatch_outbox).values(
                message_id=uuid4(),
                aggregate_type="ride",
                aggregate_id=ride_id,
                event_type=event_type,
                payload={"ride_id": str(ride_id), **payload},
                occurred_at=occurred_at,
                available_at=occurred_at,
                attempt_count=0,
            )
        )

    def create_ride_idempotently(
        self,
        *,
        rider_id: UUID,
        idempotency_fingerprint: str,
        request_hash: str,
        ride: DispatchRide,
        audit_event: AuditEvent,
    ) -> tuple[DispatchRide, bool]:
        existing = (
            self._connection.execute(
                select(dispatch_idempotency_records).where(
                    dispatch_idempotency_records.c.rider_identity_id == rider_id,
                    dispatch_idempotency_records.c.key_fingerprint
                    == idempotency_fingerprint,
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            if existing["request_hash"] != request_hash:
                raise IdempotencyConflict("Idempotency key was reused")
            stored = self.get_ride(existing["ride_id"])
            if stored is None:
                raise DispatchConflict("Idempotency record has no ride")
            return stored, False

        values = {
            "ride_id": ride.ride_id,
            "rider_identity_id": rider_id,
            "pickup_place_id": ride.pickup.place_id,
            "pickup_display_name": ride.pickup.display_name,
            "destination_place_id": ride.destination.place_id,
            "destination_display_name": ride.destination.display_name,
            "service_type": ride.service_type,
            "quote_id": ride.quote.quote_id,
            "fare_amount_minor": ride.quote.amount_minor,
            "currency": ride.quote.currency,
            "pricing_version": ride.quote.pricing_version,
            "quote_expires_at": ride.quote.expires_at,
            "state": ride.state.value,
            "attempted_driver_ids": [],
            "accepted_at": ride.accepted_at,
            "updated_at": ride.updated_at,
            "search_expires_at": ride.accepted_at + timedelta(minutes=5),
            "version": ride.version,
        }
        try:
            with self._connection.begin_nested():
                self._connection.execute(
                    insert(dispatch_ride_requests).values(**values)
                )
                self._connection.execute(
                    insert(dispatch_idempotency_records).values(
                        rider_identity_id=rider_id,
                        key_fingerprint=idempotency_fingerprint,
                        request_hash=request_hash,
                        ride_id=ride.ride_id,
                        created_at=ride.accepted_at,
                        expires_at=ride.accepted_at + timedelta(hours=24),
                    )
                )
        except IntegrityError as error:
            collision = (
                self._connection.execute(
                    select(dispatch_idempotency_records).where(
                        dispatch_idempotency_records.c.rider_identity_id == rider_id,
                        dispatch_idempotency_records.c.key_fingerprint
                        == idempotency_fingerprint,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if collision is not None:
                if collision["request_hash"] != request_hash:
                    raise IdempotencyConflict("Idempotency key was reused") from error
                stored = self.get_ride(collision["ride_id"])
                if stored is None:
                    raise DispatchConflict("Idempotency record has no ride") from error
                return stored, False
            raise DispatchConflict("Rider already has an active ride") from error
        self._audit.append(audit_event)
        self._outbox("dispatch.ride.requested", ride.ride_id, ride.accepted_at)
        return ride, True

    def get_ride(self, ride_id: UUID) -> DispatchRide | None:
        row = (
            self._connection.execute(
                select(dispatch_ride_requests).where(
                    dispatch_ride_requests.c.ride_id == ride_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _ride_from_row(row)

    def get_active_ride_for_rider(self, rider_id: UUID) -> DispatchRide | None:
        row = (
            self._connection.execute(
                select(dispatch_ride_requests).where(
                    dispatch_ride_requests.c.rider_identity_id == rider_id,
                    dispatch_ride_requests.c.state.in_(
                        ("searching", "offering", "assigned")
                    ),
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _ride_from_row(row)

    def list_candidates(
        self, *, ride: DispatchRide, now: datetime, limit: int
    ) -> list[DriverCandidate]:
        return self._candidates.list_candidates(ride=ride, now=now, limit=limit)

    def reserve_and_offer(
        self,
        *,
        expected_ride_version: int,
        offer: DriverOffer,
        audit_event: AuditEvent,
    ) -> DispatchRide:
        ride_row = (
            self._connection.execute(
                select(dispatch_ride_requests)
                .where(dispatch_ride_requests.c.ride_id == offer.ride_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if (
            ride_row is None
            or ride_row["state"] != "searching"
            or ride_row["version"] != expected_ride_version
        ):
            raise DispatchConflict("Ride changed before offer")
        sequence = self._connection.execute(
            select(dispatch_attempts.c.attempt_id).where(
                dispatch_attempts.c.ride_id == offer.ride_id
            )
        ).all()
        attempt_id = uuid4()
        try:
            with self._connection.begin_nested():
                self._connection.execute(
                    insert(dispatch_attempts).values(
                        attempt_id=attempt_id,
                        ride_id=offer.ride_id,
                        driver_identity_id=offer.driver_id,
                        sequence_number=len(sequence) + 1,
                        pickup_eta_seconds=offer.score.pickup_eta_seconds,
                        policy_version=offer.policy_version,
                        reason_codes=list(offer.score.reason_codes),
                        outcome="offered",
                        created_at=offer.created_at,
                    )
                )
                self._connection.execute(
                    insert(dispatch_driver_offers).values(
                        offer_id=offer.offer_id,
                        attempt_id=attempt_id,
                        ride_id=offer.ride_id,
                        driver_identity_id=offer.driver_id,
                        state=offer.state.value,
                        created_at=offer.created_at,
                        expires_at=offer.expires_at,
                        policy_version=offer.policy_version,
                        score_snapshot=_score_payload(offer.score),
                        version=offer.version,
                    )
                )
        except IntegrityError as error:
            raise DispatchConflict(
                "Driver or ride already has an active offer"
            ) from error
        attempted = [*ride_row["attempted_driver_ids"], str(offer.driver_id)]
        updated = (
            self._connection.execute(
                update(dispatch_ride_requests)
                .where(
                    dispatch_ride_requests.c.ride_id == offer.ride_id,
                    dispatch_ride_requests.c.version == expected_ride_version,
                )
                .values(
                    state="offering",
                    active_offer_id=offer.offer_id,
                    attempted_driver_ids=attempted,
                    updated_at=offer.created_at,
                    version=expected_ride_version + 1,
                )
                .returning(dispatch_ride_requests)
            )
            .mappings()
            .one_or_none()
        )
        if updated is None:
            raise DispatchConflict("Ride changed before offer")
        self._audit.append(audit_event)
        self._outbox(
            "dispatch.driver_offer.created",
            offer.ride_id,
            offer.created_at,
            offer_id=str(offer.offer_id),
            driver_id=str(offer.driver_id),
            expires_at=offer.expires_at.isoformat(),
        )
        return _ride_from_row(updated)

    def get_offer(self, offer_id: UUID) -> DriverOffer | None:
        row = (
            self._connection.execute(
                select(dispatch_driver_offers).where(
                    dispatch_driver_offers.c.offer_id == offer_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _offer_from_row(row)

    def resolve_offer_and_requeue(
        self,
        *,
        offer_id: UUID,
        driver_id: UUID,
        outcome: str,
        now: datetime,
        audit_event: AuditEvent,
    ) -> DispatchRide:
        if outcome not in {"declined", "expired"}:
            raise ValueError("Unsupported offer outcome")
        offer = (
            self._connection.execute(
                select(dispatch_driver_offers)
                .where(dispatch_driver_offers.c.offer_id == offer_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if (
            offer is None
            or offer["driver_identity_id"] != driver_id
            or offer["state"] != "created"
        ):
            raise DispatchConflict("Offer is no longer active")
        if outcome == "expired" and offer["expires_at"] > now:
            raise DispatchConflict("Offer has not expired")
        self._connection.execute(
            update(dispatch_driver_offers)
            .where(dispatch_driver_offers.c.offer_id == offer_id)
            .values(state=outcome, resolved_at=now, version=offer["version"] + 1)
        )
        self._connection.execute(
            update(dispatch_attempts)
            .where(dispatch_attempts.c.attempt_id == offer["attempt_id"])
            .values(outcome=outcome, resolved_at=now)
        )
        row = (
            self._connection.execute(
                update(dispatch_ride_requests)
                .where(
                    dispatch_ride_requests.c.ride_id == offer["ride_id"],
                    dispatch_ride_requests.c.active_offer_id == offer_id,
                    dispatch_ride_requests.c.state == "offering",
                )
                .values(
                    state="searching",
                    active_offer_id=None,
                    updated_at=now,
                    version=dispatch_ride_requests.c.version + 1,
                )
                .returning(dispatch_ride_requests)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DispatchConflict("Ride is no longer offering")
        self._audit.append(audit_event)
        self._outbox(
            f"dispatch.driver_offer.{outcome}",
            offer["ride_id"],
            now,
            offer_id=str(offer_id),
        )
        return _ride_from_row(row)

    def accept_offer(
        self, *, offer_id: UUID, driver_id: UUID, now: datetime, audit_event: AuditEvent
    ) -> DispatchRide:
        offer = (
            self._connection.execute(
                select(dispatch_driver_offers)
                .where(dispatch_driver_offers.c.offer_id == offer_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if offer is None or offer["driver_identity_id"] != driver_id:
            raise DispatchConflict("Offer is unavailable")
        if offer["state"] == "accepted":
            ride = self.get_ride(offer["ride_id"])
            if ride is None or ride.assigned_driver_id != driver_id:
                raise DispatchConflict("Assignment is inconsistent")
            return ride
        if offer["state"] != "created" or offer["expires_at"] <= now:
            raise DispatchConflict("Offer is not active")
        self._connection.execute(
            update(dispatch_driver_offers)
            .where(dispatch_driver_offers.c.offer_id == offer_id)
            .values(state="accepted", resolved_at=now, version=offer["version"] + 1)
        )
        self._connection.execute(
            update(dispatch_attempts)
            .where(dispatch_attempts.c.attempt_id == offer["attempt_id"])
            .values(outcome="accepted", resolved_at=now)
        )
        try:
            self._connection.execute(
                insert(dispatch_assignments).values(
                    assignment_id=uuid4(),
                    ride_id=offer["ride_id"],
                    offer_id=offer_id,
                    driver_identity_id=driver_id,
                    assigned_at=now,
                )
            )
        except IntegrityError as error:
            raise DispatchConflict("Ride is already assigned") from error
        row = (
            self._connection.execute(
                update(dispatch_ride_requests)
                .where(
                    dispatch_ride_requests.c.ride_id == offer["ride_id"],
                    dispatch_ride_requests.c.active_offer_id == offer_id,
                    dispatch_ride_requests.c.state == "offering",
                )
                .values(
                    state="assigned",
                    assigned_driver_identity_id=driver_id,
                    active_offer_id=None,
                    updated_at=now,
                    version=dispatch_ride_requests.c.version + 1,
                )
                .returning(dispatch_ride_requests)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DispatchConflict("Ride is no longer offering")
        self._audit.append(audit_event)
        self._outbox(
            "dispatch.driver.assigned",
            offer["ride_id"],
            now,
            offer_id=str(offer_id),
            driver_id=str(driver_id),
        )
        return _ride_from_row(row)

    def list_expired_active_offers(
        self, *, now: datetime, limit: int
    ) -> list[DriverOffer]:
        rows = (
            self._connection.execute(
                select(dispatch_driver_offers)
                .where(
                    dispatch_driver_offers.c.state == "created",
                    dispatch_driver_offers.c.expires_at <= now,
                )
                .order_by(
                    dispatch_driver_offers.c.expires_at,
                    dispatch_driver_offers.c.offer_id,
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            .mappings()
            .all()
        )
        return [_offer_from_row(row) for row in rows]

    def mark_no_driver(
        self,
        *,
        ride_id: UUID,
        expected_version: int,
        now: datetime,
        audit_event: AuditEvent,
    ) -> DispatchRide:
        row = (
            self._connection.execute(
                update(dispatch_ride_requests)
                .where(
                    dispatch_ride_requests.c.ride_id == ride_id,
                    dispatch_ride_requests.c.state == "searching",
                    dispatch_ride_requests.c.version == expected_version,
                )
                .values(
                    state="no_driver_available",
                    updated_at=now,
                    version=expected_version + 1,
                )
                .returning(dispatch_ride_requests)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DispatchConflict("Ride changed before no-driver outcome")
        self._audit.append(audit_event)
        self._outbox("dispatch.ride.no_driver_available", ride_id, now)
        return _ride_from_row(row)

    def append_audit(self, event: AuditEvent) -> None:
        self._audit.append(event)

    def list_searching_ride_ids(self, *, limit: int = 100) -> list[UUID]:
        if not 1 <= limit <= 1_000:
            raise ValueError("Search recovery limit must be between 1 and 1000")
        return list(
            self._connection.execute(
                select(dispatch_ride_requests.c.ride_id)
                .where(dispatch_ride_requests.c.state == "searching")
                .order_by(dispatch_ride_requests.c.accepted_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).scalars()
        )

    def abandon_expired_searches(self, *, now: datetime, limit: int = 100) -> int:
        rows = (
            self._connection.execute(
                select(dispatch_ride_requests.c.ride_id)
                .where(
                    dispatch_ride_requests.c.state.in_(("searching", "offering")),
                    dispatch_ride_requests.c.search_expires_at <= now,
                )
                .order_by(dispatch_ride_requests.c.search_expires_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )
        for ride_id in rows:
            active_attempts = list(
                self._connection.execute(
                    select(dispatch_driver_offers.c.attempt_id).where(
                        dispatch_driver_offers.c.ride_id == ride_id,
                        dispatch_driver_offers.c.state == "created",
                    )
                ).scalars()
            )
            self._connection.execute(
                update(dispatch_driver_offers)
                .where(
                    dispatch_driver_offers.c.ride_id == ride_id,
                    dispatch_driver_offers.c.state == "created",
                )
                .values(
                    state="revoked",
                    resolved_at=now,
                    version=dispatch_driver_offers.c.version + 1,
                )
            )
            if active_attempts:
                self._connection.execute(
                    update(dispatch_attempts)
                    .where(dispatch_attempts.c.attempt_id.in_(active_attempts))
                    .values(outcome="revoked", resolved_at=now)
                )
            self._connection.execute(
                update(dispatch_ride_requests)
                .where(dispatch_ride_requests.c.ride_id == ride_id)
                .values(
                    state="no_driver_available",
                    active_offer_id=None,
                    updated_at=now,
                    version=dispatch_ride_requests.c.version + 1,
                )
            )
            self._outbox("dispatch.ride.no_driver_available", ride_id, now)
            self._audit.append(
                AuditEvent(
                    occurred_at=now,
                    recorded_at=now,
                    actor_type=ActorType.SYSTEM,
                    action="dispatch.ride.search_abandoned",
                    resource_type="ride",
                    resource_id=str(ride_id),
                    outcome=AuditOutcome.SUCCESS,
                    reason="search_timeout",
                    correlation_id=ride_id,
                    source_module="dispatch",
                    safe_metadata={"state_to": "no_driver_available"},
                )
            )
        return len(rows)
