from datetime import datetime
from hashlib import sha256
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from BACKEND.dispatch.handoff import (
    DispatchHandoff,
    HandoffOffer,
    HandoffOfferState,
    HandoffState,
)
from BACKEND.persistence.tables import (
    canonical_ride_requests,
    driver_eligibility_decisions,
    driver_vehicle_authorizations,
    driver_vehicles,
    immediate_dispatch_assignments,
    immediate_dispatch_candidate_sets,
    immediate_dispatch_events,
    immediate_dispatch_handoffs,
    immediate_dispatch_idempotency,
    immediate_dispatch_offers,
    immediate_dispatch_outbox,
    ride_request_validation_decisions,
    service_zones,
)


class HandoffConflict(RuntimeError):
    pass


class PostgresHandoffDispatchRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def ready_source(self, ride_request_id: UUID) -> dict[str, Any] | None:
        row = (
            self._connection.execute(
                select(
                    canonical_ride_requests,
                    ride_request_validation_decisions.c.decision_id,
                    ride_request_validation_decisions.c.policy_version.label(
                        "validation_policy_version"
                    ),
                    service_zones.c.version.label("zone_version"),
                )
                .join(
                    ride_request_validation_decisions,
                    ride_request_validation_decisions.c.request_id
                    == canonical_ride_requests.c.request_id,
                )
                .outerjoin(
                    service_zones,
                    service_zones.c.zone_id
                    == canonical_ride_requests.c.service_zone_id,
                )
                .where(
                    canonical_ride_requests.c.request_id == ride_request_id,
                    canonical_ride_requests.c.state == "ready_for_dispatch",
                    ride_request_validation_decisions.c.status == "valid",
                )
                .order_by(ride_request_validation_decisions.c.decided_at.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else dict(row)

    def reserve_idempotency(
        self,
        *,
        actor_id: UUID,
        operation: str,
        key: str,
        request_hash: str,
        response_reference: UUID,
        at: datetime,
    ) -> UUID:
        self._connection.execute(
            pg_insert(immediate_dispatch_idempotency)
            .values(
                actor_id=actor_id,
                operation=operation,
                key=key,
                request_hash=request_hash,
                response_reference=response_reference,
                created_at=at,
            )
            .on_conflict_do_nothing(index_elements=["actor_id", "operation", "key"])
        )
        row = (
            self._connection.execute(
                select(immediate_dispatch_idempotency)
                .where(
                    immediate_dispatch_idempotency.c.actor_id == actor_id,
                    immediate_dispatch_idempotency.c.operation == operation,
                    immediate_dispatch_idempotency.c.key == key,
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        if row["request_hash"] != request_hash:
            raise ValueError("Idempotency key reused with different request")
        return cast(UUID, row["response_reference"])

    def create_handoff(self, handoff: DispatchHandoff) -> DispatchHandoff:
        existing = self.get_handoff(handoff.handoff_id)
        if existing is not None:
            return existing
        self._connection.execute(
            insert(immediate_dispatch_handoffs).values(**handoff.model_dump())
        )
        self.event(handoff, "dispatch.handoff_received", handoff.created_at)
        self.event(
            handoff,
            "dispatch.rider.searching",
            handoff.created_at,
            {
                "recipient_identity_id": str(handoff.rider_identity_id),
                "translation_key": "dispatch.searching",
            },
        )
        return handoff

    def get_handoff(self, handoff_id: UUID) -> DispatchHandoff | None:
        row = (
            self._connection.execute(
                select(immediate_dispatch_handoffs).where(
                    immediate_dispatch_handoffs.c.handoff_id == handoff_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else DispatchHandoff.model_validate(dict(row))

    def get_handoff_for_rider(
        self, *, rider_id: UUID, ride_request_id: UUID
    ) -> DispatchHandoff | None:
        row = (
            self._connection.execute(
                select(immediate_dispatch_handoffs).where(
                    immediate_dispatch_handoffs.c.ride_request_id == ride_request_id,
                    immediate_dispatch_handoffs.c.rider_identity_id == rider_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else DispatchHandoff.model_validate(dict(row))

    def get_offer(self, offer_id: UUID) -> HandoffOffer | None:
        row = (
            self._connection.execute(
                select(immediate_dispatch_offers).where(
                    immediate_dispatch_offers.c.offer_id == offer_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else HandoffOffer.model_validate(dict(row))

    def get_active_offer_for_driver(self, driver_id: UUID) -> HandoffOffer | None:
        row = (
            self._connection.execute(
                select(immediate_dispatch_offers).where(
                    immediate_dispatch_offers.c.driver_id == driver_id,
                    immediate_dispatch_offers.c.state == "created",
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else HandoffOffer.model_validate(dict(row))

    def get_active_offer_for_handoff(self, handoff_id: UUID) -> HandoffOffer | None:
        row = (
            self._connection.execute(
                select(immediate_dispatch_offers).where(
                    immediate_dispatch_offers.c.handoff_id == handoff_id,
                    immediate_dispatch_offers.c.state == "created",
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else HandoffOffer.model_validate(dict(row))

    def list_expired_offers(self, *, at: datetime, limit: int) -> list[HandoffOffer]:
        rows = (
            self._connection.execute(
                select(immediate_dispatch_offers)
                .where(
                    immediate_dispatch_offers.c.state == "created",
                    immediate_dispatch_offers.c.expires_at <= at,
                )
                .order_by(immediate_dispatch_offers.c.expires_at)
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return [HandoffOffer.model_validate(dict(row)) for row in rows]

    def list_searching_handoff_ids(self, *, at: datetime, limit: int) -> list[UUID]:
        return list(
            self._connection.execute(
                select(immediate_dispatch_handoffs.c.handoff_id)
                .where(
                    immediate_dispatch_handoffs.c.state == "searching",
                    immediate_dispatch_handoffs.c.expires_at > at,
                )
                .order_by(immediate_dispatch_handoffs.c.created_at)
                .limit(limit)
            ).scalars()
        )

    def close_expired_handoffs(self, *, at: datetime, limit: int) -> int:
        rows = (
            self._connection.execute(
                select(immediate_dispatch_handoffs)
                .where(
                    immediate_dispatch_handoffs.c.state.in_(("searching", "offering")),
                    immediate_dispatch_handoffs.c.expires_at <= at,
                )
                .order_by(immediate_dispatch_handoffs.c.expires_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            .mappings()
            .all()
        )
        for row in rows:
            handoff = DispatchHandoff.model_validate(dict(row))
            self._connection.execute(
                update(immediate_dispatch_offers)
                .where(
                    immediate_dispatch_offers.c.handoff_id == handoff.handoff_id,
                    immediate_dispatch_offers.c.state == "created",
                )
                .values(
                    state="expired",
                    resolved_at=at,
                    version=immediate_dispatch_offers.c.version + 1,
                )
            )
            self._connection.execute(
                update(immediate_dispatch_handoffs)
                .where(
                    immediate_dispatch_handoffs.c.handoff_id == handoff.handoff_id,
                    immediate_dispatch_handoffs.c.version == handoff.version,
                )
                .values(state="no_driver", version=handoff.version + 1)
            )
            self.event(
                handoff,
                "dispatch.rider.no_driver_available",
                at,
                {
                    "recipient_identity_id": str(handoff.rider_identity_id),
                    "translation_key": "dispatch.rider.no_driver_available",
                },
            )
        return len(rows)

    def eligibility_current(
        self, driver_id: UUID, vehicle_id: UUID, *, now: datetime
    ) -> bool:
        decision = (
            self._connection.execute(
                select(driver_eligibility_decisions)
                .where(driver_eligibility_decisions.c.driver_identity_id == driver_id)
                .order_by(driver_eligibility_decisions.c.recomputed_at.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        if (
            decision is None
            or decision["status"] != "eligible"
            or decision["expires_at"] is None
            or decision["expires_at"] <= now
            or decision["vehicle_id"] != vehicle_id
        ):
            return False
        vehicle = self._connection.execute(
            select(driver_vehicles.c.approval_status).where(
                driver_vehicles.c.vehicle_id == vehicle_id
            )
        ).scalar_one_or_none()
        authorization = self._connection.execute(
            select(driver_vehicle_authorizations.c.authorization_id).where(
                driver_vehicle_authorizations.c.driver_identity_id == driver_id,
                driver_vehicle_authorizations.c.vehicle_id == vehicle_id,
                driver_vehicle_authorizations.c.status == "authorized",
                driver_vehicle_authorizations.c.expires_at > now,
            )
        ).scalar_one_or_none()
        return vehicle == "approved" and authorization is not None

    def record_candidates(
        self,
        handoff: DispatchHandoff,
        driver_ids: list[UUID],
        at: datetime,
        decision_evidence: dict[str, Any] | None = None,
    ) -> None:
        self._connection.execute(
            insert(immediate_dispatch_candidate_sets).values(
                candidate_set_id=uuid4(),
                handoff_id=handoff.handoff_id,
                policy_version=handoff.dispatch_policy_version,
                candidate_count=len(driver_ids),
                eligible_driver_ids=[str(x) for x in driver_ids],
                decision_evidence=decision_evidence or {},
                created_at=at,
            )
        )
        self.event(
            handoff,
            "dispatch.candidate_set_created",
            at,
            {"candidate_count": len(driver_ids)},
        )

    def create_offer(
        self, handoff: DispatchHandoff, offer: HandoffOffer
    ) -> HandoffOffer:
        try:
            self._connection.execute(
                insert(immediate_dispatch_offers).values(**offer.model_dump())
            )
        except IntegrityError as error:
            raise HandoffConflict("Active offer conflict") from error
        row = (
            self._connection.execute(
                update(immediate_dispatch_handoffs)
                .where(
                    immediate_dispatch_handoffs.c.handoff_id == handoff.handoff_id,
                    immediate_dispatch_handoffs.c.version == handoff.version,
                    immediate_dispatch_handoffs.c.state == "searching",
                )
                .values(state="offering", version=handoff.version + 1)
                .returning(immediate_dispatch_handoffs)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise HandoffConflict("Handoff changed before offer")
        self.event(
            DispatchHandoff.model_validate(dict(row)),
            "dispatch.offer_created",
            offer.created_at,
            {"offer_id": str(offer.offer_id)},
        )
        self.event(
            DispatchHandoff.model_validate(dict(row)),
            "dispatch.driver.new_offer",
            offer.created_at,
            {
                "recipient_identity_id": str(offer.driver_id),
                "offer_id": str(offer.offer_id),
                "expires_at": offer.expires_at.isoformat(),
                "translation_key": "dispatch.driver.new_offer",
            },
        )
        self.event(
            DispatchHandoff.model_validate(dict(row)),
            "dispatch.rider.driver_found",
            offer.created_at,
            {
                "recipient_identity_id": str(handoff.rider_identity_id),
                "translation_key": "dispatch.rider.driver_found",
            },
        )
        return offer

    def respond(
        self,
        *,
        offer_id: UUID,
        driver_id: UUID,
        accept: bool,
        expected_version: int,
        idempotency_key: str,
        at: datetime,
    ) -> UUID | None:
        request_hash = sha256(
            f"{offer_id}:{accept}:{expected_version}".encode()
        ).hexdigest()
        canonical = self.reserve_idempotency(
            actor_id=driver_id,
            operation="offer_response",
            key=idempotency_key,
            request_hash=request_hash,
            response_reference=offer_id,
            at=at,
        )
        offer_snapshot = (
            self._connection.execute(
                select(immediate_dispatch_offers).where(
                    immediate_dispatch_offers.c.offer_id == canonical
                )
            )
            .mappings()
            .one_or_none()
        )
        if offer_snapshot is None or offer_snapshot["driver_id"] != driver_id:
            raise HandoffConflict("Offer unavailable")
        handoff_row = (
            self._connection.execute(
                select(immediate_dispatch_handoffs)
                .where(
                    immediate_dispatch_handoffs.c.handoff_id
                    == offer_snapshot["handoff_id"]
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        offer = (
            self._connection.execute(
                select(immediate_dispatch_offers)
                .where(immediate_dispatch_offers.c.offer_id == canonical)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if offer is None or handoff_row is None:
            raise HandoffConflict("Offer unavailable")
        if offer["state"] == "accepted":
            return cast(
                UUID,
                self._connection.execute(
                    select(immediate_dispatch_assignments.c.assignment_id).where(
                        immediate_dispatch_assignments.c.offer_id == offer_id
                    )
                ).scalar_one(),
            )
        if offer["state"] == "rejected" and not accept:
            return None
        if (
            offer["state"] != "created"
            or offer["version"] != expected_version
            or offer["expires_at"] <= at
        ):
            raise HandoffConflict("Offer no longer active")
        handoff = DispatchHandoff.model_validate(dict(handoff_row))
        if handoff.state is not HandoffState.OFFERING:
            raise HandoffConflict("Handoff unavailable")
        outcome = "accepted" if accept else "rejected"
        self._connection.execute(
            update(immediate_dispatch_offers)
            .where(immediate_dispatch_offers.c.offer_id == offer_id)
            .values(state=outcome, version=expected_version + 1, resolved_at=at)
        )
        if not accept:
            self._connection.execute(
                update(immediate_dispatch_handoffs)
                .where(immediate_dispatch_handoffs.c.handoff_id == handoff.handoff_id)
                .values(state="searching", version=handoff.version + 1)
            )
            self.event(
                handoff, "dispatch.offer_rejected", at, {"offer_id": str(offer_id)}
            )
            return None
        assignment_id = uuid4()
        try:
            self._connection.execute(
                insert(immediate_dispatch_assignments).values(
                    assignment_id=assignment_id,
                    handoff_id=handoff.handoff_id,
                    offer_id=offer_id,
                    driver_id=driver_id,
                    vehicle_id=offer["vehicle_id"],
                    assigned_at=at,
                    correlation_id=handoff.correlation_id,
                )
            )
        except IntegrityError as error:
            raise HandoffConflict("Assignment conflict") from error
        updated = (
            self._connection.execute(
                update(immediate_dispatch_handoffs)
                .where(
                    immediate_dispatch_handoffs.c.handoff_id == handoff.handoff_id,
                    immediate_dispatch_handoffs.c.state == "offering",
                )
                .values(
                    state="assigned",
                    assigned_driver_id=driver_id,
                    version=handoff.version + 1,
                )
                .returning(immediate_dispatch_handoffs)
            )
            .mappings()
            .one_or_none()
        )
        if updated is None:
            raise HandoffConflict("Assignment lost race")
        self.event(
            DispatchHandoff.model_validate(dict(updated)),
            "dispatch.assignment_created",
            at,
            {"assignment_id": str(assignment_id)},
        )
        assigned_handoff = DispatchHandoff.model_validate(dict(updated))
        self.event(
            assigned_handoff,
            "dispatch.driver.acceptance_confirmed",
            at,
            {
                "recipient_identity_id": str(driver_id),
                "assignment_id": str(assignment_id),
                "translation_key": "dispatch.driver.accepted",
            },
        )
        self.event(
            assigned_handoff,
            "dispatch.rider.driver_accepted",
            at,
            {
                "recipient_identity_id": str(handoff.rider_identity_id),
                "assignment_id": str(assignment_id),
                "translation_key": "dispatch.rider.driver_found",
            },
        )
        return assignment_id

    def respond_canonical(
        self,
        *,
        offer_id: UUID,
        driver_id: UUID,
        accept: bool,
        expected_version: int,
        idempotency_key: str,
        at: datetime,
    ) -> UUID | None:
        offer = (
            self._connection.execute(
                select(
                    immediate_dispatch_offers.c.vehicle_id,
                    immediate_dispatch_offers.c.state,
                    immediate_dispatch_handoffs.c.service_zone_id,
                )
                .join(
                    immediate_dispatch_handoffs,
                    immediate_dispatch_handoffs.c.handoff_id
                    == immediate_dispatch_offers.c.handoff_id,
                )
                .where(
                    immediate_dispatch_offers.c.offer_id == offer_id,
                    immediate_dispatch_offers.c.driver_id == driver_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if offer is None:
            raise HandoffConflict("Offer unavailable")
        if accept and offer["state"] != "accepted":
            from BACKEND.persistence.worker_session_repository import (
                PostgresWorkerSessionRepository,
            )

            sessions = PostgresWorkerSessionRepository(self._connection)
            if not sessions.ride_driver_online(
                identity_id=driver_id,
                vehicle_id=offer["vehicle_id"],
                service_zone_id=offer["service_zone_id"],
                now=at,
                lock=True,
            ):
                raise HandoffConflict("Ride Driver mode is not online")
        return self.respond(
            offer_id=offer_id,
            driver_id=driver_id,
            accept=accept,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            at=at,
        )

    def cancel_before_assignment(self, ride_request_id: UUID, *, at: datetime) -> bool:
        row = (
            self._connection.execute(
                select(immediate_dispatch_handoffs)
                .where(immediate_dispatch_handoffs.c.ride_request_id == ride_request_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return False
        handoff = DispatchHandoff.model_validate(dict(row))
        if handoff.state is HandoffState.ASSIGNED:
            raise HandoffConflict("Post-assignment cancellation excluded")
        if handoff.state is HandoffState.CANCELLED:
            return True
        self._connection.execute(
            update(immediate_dispatch_offers)
            .where(
                immediate_dispatch_offers.c.handoff_id == handoff.handoff_id,
                immediate_dispatch_offers.c.state == "created",
            )
            .values(
                state="cancelled",
                resolved_at=at,
                version=immediate_dispatch_offers.c.version + 1,
            )
        )
        self._connection.execute(
            update(immediate_dispatch_handoffs)
            .where(immediate_dispatch_handoffs.c.handoff_id == handoff.handoff_id)
            .values(state="cancelled", version=handoff.version + 1)
        )
        self.event(handoff, "dispatch.cancelled_before_assignment", at)
        return True

    def resolve_open_offer(self, offer_id: UUID, *, outcome: str, at: datetime) -> None:
        if outcome not in {"expired", "superseded"}:
            raise ValueError("Unsupported offer resolution")
        snapshot = (
            self._connection.execute(
                select(immediate_dispatch_offers).where(
                    immediate_dispatch_offers.c.offer_id == offer_id
                )
            )
            .mappings()
            .one_or_none()
        )
        if snapshot is None:
            raise HandoffConflict("Offer unavailable")
        handoff_row = (
            self._connection.execute(
                select(immediate_dispatch_handoffs)
                .where(
                    immediate_dispatch_handoffs.c.handoff_id == snapshot["handoff_id"]
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        offer = (
            self._connection.execute(
                select(immediate_dispatch_offers)
                .where(immediate_dispatch_offers.c.offer_id == offer_id)
                .with_for_update()
            )
            .mappings()
            .one()
        )
        if offer["state"] != HandoffOfferState.CREATED.value:
            raise HandoffConflict("Offer no longer active")
        if outcome == "expired" and offer["expires_at"] > at:
            raise HandoffConflict("Offer has not expired")
        handoff = DispatchHandoff.model_validate(dict(handoff_row))
        if handoff.state is not HandoffState.OFFERING:
            raise HandoffConflict("Handoff unavailable")
        self._connection.execute(
            update(immediate_dispatch_offers)
            .where(immediate_dispatch_offers.c.offer_id == offer_id)
            .values(
                state=outcome,
                resolved_at=at,
                version=offer["version"] + 1,
            )
        )
        self._connection.execute(
            update(immediate_dispatch_handoffs)
            .where(immediate_dispatch_handoffs.c.handoff_id == handoff.handoff_id)
            .values(state="searching", version=handoff.version + 1)
        )
        self.event(
            handoff,
            f"dispatch.offer_{outcome}",
            at,
            {"offer_id": str(offer_id)},
        )

    def revoke_driver_offer(self, driver_id: UUID, *, at: datetime) -> bool:
        snapshot = (
            self._connection.execute(
                select(immediate_dispatch_offers).where(
                    immediate_dispatch_offers.c.driver_id == driver_id,
                    immediate_dispatch_offers.c.state == "created",
                )
            )
            .mappings()
            .one_or_none()
        )
        if snapshot is None:
            return False
        self.resolve_open_offer(snapshot["offer_id"], outcome="superseded", at=at)
        return True

    def event(
        self,
        handoff: DispatchHandoff,
        event_type: str,
        at: datetime,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event_id = uuid4()
        safe = payload or {"state": handoff.state.value}
        values = dict(
            event_id=event_id,
            event_type=event_type,
            aggregate_id=handoff.handoff_id,
            aggregate_version=handoff.version,
            safe_payload=safe,
            created_at=at,
            attempt_count=0,
        )
        self._connection.execute(
            insert(immediate_dispatch_events).values(
                event_id=event_id,
                handoff_id=handoff.handoff_id,
                event_type=event_type,
                aggregate_version=handoff.version,
                safe_payload=safe,
                correlation_id=handoff.correlation_id,
                causation_id=handoff.causation_id,
                occurred_at=at,
            )
        )
        self._connection.execute(insert(immediate_dispatch_outbox).values(**values))
