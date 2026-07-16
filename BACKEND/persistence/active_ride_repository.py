import hashlib
import hmac
import json
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update

from BACKEND.active_ride.engine import ActiveRideConflict, transition
from BACKEND.active_ride.models import (
    ActiveRide,
    ActiveRideState,
    ActorRole,
    CommandStatus,
    ConfidenceDecision,
    EvidenceRecord,
    PickupRecommendation,
    RideEvent,
)
from BACKEND.persistence.tables import (
    active_ride_confidence_decisions,
    active_ride_events,
    active_ride_evidence,
    active_ride_idempotency_records,
    active_ride_pickup_recommendations,
    active_ride_pickup_verifications,
    active_ride_projection_checkpoints,
    active_rides,
    dispatch_outbox,
    immediate_dispatch_assignments,
    immediate_dispatch_handoffs,
)


def _ride(row: Mapping[str, Any]) -> ActiveRide:
    return ActiveRide(
        ride_id=row["ride_id"],
        rider_id=row["rider_id"],
        driver_id=row["driver_id"],
        vehicle_id=row["vehicle_id"],
        reservation_id=row["reservation_id"],
        assignment_id=row["assignment_id"],
        ride_request_id=row["ride_request_id"],
        dispatch_handoff_id=row["dispatch_handoff_id"],
        lifecycle_policy_version=row["lifecycle_policy_version"],
        source_assignment_version=row["source_assignment_version"],
        state=ActiveRideState(row["state"]),
        pickup_place_id=row["pickup_place_id"],
        destination_place_id=row["destination_place_id"],
        service_type=row["service_type"],
        driver_changed=row["driver_changed"],
        last_sequence=row["last_sequence"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgresActiveRideRepository:
    """Transaction-scoped authority; callers own commit/rollback through the UoW."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create_from_assignment(self, ride: ActiveRide) -> ActiveRide:
        if (
            ride.state is not ActiveRideState.ASSIGNED
            or ride.driver_id is None
            or ride.assignment_id is None
        ):
            raise ActiveRideConflict("assignment_required")
        self._connection.execute(insert(active_rides).values(**ride.model_dump()))
        self._append_event(ride, "driver_assigned", {"driver_changed": False})
        self._checkpoint(ride)
        return ride

    def create_from_immediate_assignment(
        self,
        *,
        assignment_id: UUID,
        lifecycle_policy_version: str,
        now: datetime,
    ) -> ActiveRide:
        source = (
            self._connection.execute(
                select(
                    immediate_dispatch_assignments.c.assignment_id,
                    immediate_dispatch_assignments.c.driver_id,
                    immediate_dispatch_assignments.c.vehicle_id,
                    immediate_dispatch_assignments.c.released_at,
                    immediate_dispatch_handoffs.c.handoff_id,
                    immediate_dispatch_handoffs.c.ride_request_id,
                    immediate_dispatch_handoffs.c.rider_identity_id,
                    immediate_dispatch_handoffs.c.service_type,
                    immediate_dispatch_handoffs.c.pickup_reference,
                    immediate_dispatch_handoffs.c.destination_reference,
                    immediate_dispatch_handoffs.c.state.label("handoff_state"),
                    immediate_dispatch_handoffs.c.version.label("handoff_version"),
                    immediate_dispatch_handoffs.c.assigned_driver_id,
                )
                .join(
                    immediate_dispatch_handoffs,
                    immediate_dispatch_handoffs.c.handoff_id
                    == immediate_dispatch_assignments.c.handoff_id,
                )
                .where(immediate_dispatch_assignments.c.assignment_id == assignment_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if (
            source is None
            or source["handoff_state"] != "assigned"
            or source["released_at"] is not None
            or source["service_type"] != "immediate_standard"
            or source["assigned_driver_id"] != source["driver_id"]
        ):
            raise ActiveRideConflict("authoritative_assignment_required")
        existing = (
            self._connection.execute(
                select(active_rides).where(
                    active_rides.c.assignment_id == assignment_id
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            return _ride(dict(existing))
        ride = ActiveRide(
            rider_id=source["rider_identity_id"],
            driver_id=source["driver_id"],
            vehicle_id=source["vehicle_id"],
            assignment_id=assignment_id,
            ride_request_id=source["ride_request_id"],
            dispatch_handoff_id=source["handoff_id"],
            lifecycle_policy_version=lifecycle_policy_version,
            source_assignment_version=source["handoff_version"],
            state=ActiveRideState.DRIVER_ASSIGNED,
            pickup_place_id=str(source["pickup_reference"]),
            destination_place_id=str(source["destination_reference"]),
            service_type="immediate_standard",
            created_at=now,
            updated_at=now,
            last_sequence=1,
        )
        self._connection.execute(insert(active_rides).values(**ride.model_dump()))
        self._append_event(
            ride,
            "active_ride.driver_assigned",
            {
                "state_from": None,
                "state_to": ride.state.value,
                "assignment_id": str(assignment_id),
                "translation_key": "active_ride.driver_assigned",
            },
        )
        self._checkpoint(ride)
        return ride

    def get(self, ride_id: UUID, *, lock: bool = False) -> ActiveRide | None:
        query = select(active_rides).where(active_rides.c.ride_id == ride_id)
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else _ride(dict(row))

    def command_transition(
        self,
        *,
        ride_id: UUID,
        actor_id: UUID,
        command_id: UUID,
        command_type: str,
        request_payload: dict[str, Any],
        expected_version: int,
        target: ActiveRideState,
        now: datetime,
    ) -> tuple[ActiveRide, bool]:
        request_hash = hashlib.sha256(
            json.dumps(
                {"ride_id": str(ride_id), **request_payload},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        existing = (
            self._connection.execute(
                select(active_ride_idempotency_records).where(
                    active_ride_idempotency_records.c.actor_id == actor_id,
                    active_ride_idempotency_records.c.command_id == command_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            if (
                existing["request_hash"] != request_hash
                or existing["command_type"] != command_type
            ):
                raise ActiveRideConflict("idempotency_conflict")
            stored = self.get(ride_id)
            if stored is None:
                raise ActiveRideConflict("ride_not_found")
            return stored, False
        current = self.get(ride_id, lock=True)
        if current is None:
            raise ActiveRideConflict("ride_not_found")
        if current.version != expected_version:
            raise ActiveRideConflict("stale_command")
        changed = transition(current, target, now=now)
        result = self._connection.execute(
            update(active_rides)
            .where(
                active_rides.c.ride_id == ride_id,
                active_rides.c.version == expected_version,
            )
            .values(
                state=changed.state.value,
                version=changed.version,
                last_sequence=changed.last_sequence,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            raise ActiveRideConflict("stale_command")
        self._append_event(
            changed,
            command_type,
            {
                **request_payload,
                "state_from": current.state.value,
                "state_to": changed.state.value,
            },
        )
        self._connection.execute(
            insert(active_ride_idempotency_records).values(
                actor_id=actor_id,
                command_id=command_id,
                ride_id=ride_id,
                command_type=command_type,
                request_hash=request_hash,
                result_version=changed.version,
                result_status=CommandStatus.CONFIRMED.value,
                created_at=now,
                expires_at=now + timedelta(hours=24),
            )
        )
        self._checkpoint(changed)
        return changed, True

    def reassign(
        self, *, ride_id: UUID, driver_id: UUID, assignment_id: UUID, now: datetime
    ) -> ActiveRide:
        current = self.get(ride_id, lock=True)
        if current is None or current.state is not ActiveRideState.REASSIGNING:
            raise ActiveRideConflict("reassignment_state_required")
        changed = transition(current, ActiveRideState.ASSIGNED, now=now).model_copy(
            update={
                "driver_id": driver_id,
                "assignment_id": assignment_id,
                "driver_changed": True,
            }
        )
        self._connection.execute(
            update(active_rides)
            .where(active_rides.c.ride_id == ride_id)
            .values(
                driver_id=driver_id,
                assignment_id=assignment_id,
                driver_changed=True,
                state=changed.state.value,
                version=changed.version,
                last_sequence=changed.last_sequence,
                updated_at=now,
            )
        )
        self._connection.execute(
            update(active_ride_pickup_verifications)
            .where(
                active_ride_pickup_verifications.c.ride_id == ride_id,
                active_ride_pickup_verifications.c.invalidated_at.is_(None),
            )
            .values(invalidated_at=now)
        )
        self._append_event(changed, "driver_reassigned", {"driver_changed": True})
        self._checkpoint(changed)
        return changed

    def events_after(
        self, ride_id: UUID, after: int, *, limit: int = 100
    ) -> list[RideEvent]:
        ride = self.get(ride_id)
        if ride is None:
            raise ActiveRideConflict("ride_not_found")
        if after > ride.last_sequence:
            raise ActiveRideConflict("resync_required")
        rows = self._connection.execute(
            select(active_ride_events)
            .where(
                active_ride_events.c.ride_id == ride_id,
                active_ride_events.c.sequence > after,
            )
            .order_by(active_ride_events.c.sequence)
            .limit(min(max(limit, 1), 100))
        ).mappings()
        return [RideEvent.model_validate(dict(row)) for row in rows]

    def replay_canonical_state(self, ride_id: UUID) -> ActiveRideState:
        rows = (
            self._connection.execute(
                select(active_ride_events)
                .where(active_ride_events.c.ride_id == ride_id)
                .order_by(active_ride_events.c.sequence)
            )
            .mappings()
            .all()
        )
        if not rows:
            raise ActiveRideConflict("ride_not_found")
        expected_sequence = 1
        state: ActiveRideState | None = None
        for row in rows:
            if row["sequence"] != expected_sequence:
                raise ActiveRideConflict("event_stream_gap")
            target = row["payload"].get("state_to")
            if target is None:
                raise ActiveRideConflict("event_state_missing")
            state = ActiveRideState(target)
            expected_sequence += 1
        stored = self.get(ride_id)
        if stored is None or stored.state is not state:
            raise ActiveRideConflict("event_snapshot_mismatch")
        return state

    def acknowledge(
        self, ride_id: UUID, role: ActorRole, sequence: int, *, now: datetime
    ) -> None:
        ride = self.get(ride_id)
        if ride is None or sequence > ride.last_sequence:
            raise ActiveRideConflict("invalid_acknowledgement")
        projection = self.projection(ride, role)
        values = {
            "ride_id": ride_id,
            "role": role.value,
            "projection": projection,
            "aggregate_version": ride.version,
            "last_sequence": sequence,
            "updated_at": now,
        }
        existing = self._connection.execute(
            select(active_ride_projection_checkpoints).where(
                active_ride_projection_checkpoints.c.ride_id == ride_id,
                active_ride_projection_checkpoints.c.role == role.value,
            )
        ).first()
        if existing is None:
            self._connection.execute(
                insert(active_ride_projection_checkpoints).values(**values)
            )
        else:
            self._connection.execute(
                update(active_ride_projection_checkpoints)
                .where(
                    active_ride_projection_checkpoints.c.ride_id == ride_id,
                    active_ride_projection_checkpoints.c.role == role.value,
                    active_ride_projection_checkpoints.c.last_sequence <= sequence,
                )
                .values(**values)
            )

    def projection(self, ride: ActiveRide, role: ActorRole) -> dict[str, Any]:
        shared: dict[str, Any] = {
            "ride_id": str(ride.ride_id),
            "state": ride.state.value,
            "aggregate_version": ride.version,
            "last_sequence": ride.last_sequence,
            "updated_at": ride.updated_at.isoformat(),
            "pickup_place_id": ride.pickup_place_id,
            "service_type": ride.service_type,
            "driver_changed": ride.driver_changed,
            "support_available": True,
            "safety_available": True,
        }
        if role is ActorRole.RIDER:
            shared.update(
                {
                    "driver": None
                    if ride.driver_id is None
                    else {"driver_reference": str(ride.driver_id)},
                    "eta_freshness": "unknown",
                    "action_required": self._rider_action(ride.state),
                    "price_change_notice": None,
                }
            )
        elif role is ActorRole.DRIVER:
            shared.update(
                {
                    "rider": {"rider_reference": str(ride.rider_id)},
                    "destination_place_id": ride.destination_place_id,
                    "action_required": self._driver_action(ride.state),
                    "estimated_earnings": None,
                }
            )
        return shared

    def issue_pin(
        self,
        *,
        ride_id: UUID,
        assignment_id: UUID,
        code: str,
        secret: bytes,
        now: datetime,
        ttl_seconds: int = 300,
        maximum_attempts: int = 5,
    ) -> UUID:
        ride = self.get(ride_id, lock=True)
        if (
            ride is None
            or ride.assignment_id != assignment_id
            or ride.state is not ActiveRideState.PICKUP_VERIFICATION_PENDING
        ):
            raise ActiveRideConflict("verification_not_available")
        self._connection.execute(
            update(active_ride_pickup_verifications)
            .where(
                active_ride_pickup_verifications.c.ride_id == ride_id,
                active_ride_pickup_verifications.c.invalidated_at.is_(None),
            )
            .values(invalidated_at=now)
        )
        verification_id = uuid4()
        digest = hmac.digest(
            secret, ride_id.bytes + assignment_id.bytes + code.encode("ascii"), "sha256"
        )
        self._connection.execute(
            insert(active_ride_pickup_verifications).values(
                verification_id=verification_id,
                ride_id=ride_id,
                assignment_id=assignment_id,
                secret_digest=digest,
                expires_at=now + timedelta(seconds=ttl_seconds),
                attempt_count=0,
                maximum_attempts=maximum_attempts,
                created_at=now,
            )
        )
        return verification_id

    def verify_pin(
        self, *, ride_id: UUID, code: str, secret: bytes, now: datetime
    ) -> bool:
        row = (
            self._connection.execute(
                select(active_ride_pickup_verifications)
                .where(
                    active_ride_pickup_verifications.c.ride_id == ride_id,
                    active_ride_pickup_verifications.c.invalidated_at.is_(None),
                )
                .order_by(active_ride_pickup_verifications.c.created_at.desc())
                .limit(1)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["verified_at"] is not None:
            raise ActiveRideConflict("verification_not_available")
        if now >= row["expires_at"]:
            raise ActiveRideConflict("verification_expired")
        if row["cooldown_until"] is not None and now < row["cooldown_until"]:
            raise ActiveRideConflict("verification_cooldown")
        if row["attempt_count"] >= row["maximum_attempts"]:
            raise ActiveRideConflict("verification_locked")
        candidate = hmac.digest(
            secret,
            ride_id.bytes + row["assignment_id"].bytes + code.encode("ascii"),
            "sha256",
        )
        if not hmac.compare_digest(candidate, row["secret_digest"]):
            attempts = row["attempt_count"] + 1
            self._connection.execute(
                update(active_ride_pickup_verifications)
                .where(
                    active_ride_pickup_verifications.c.verification_id
                    == row["verification_id"]
                )
                .values(
                    attempt_count=attempts,
                    cooldown_until=now + timedelta(seconds=30)
                    if attempts >= 3
                    else None,
                )
            )
            return False
        self._connection.execute(
            update(active_ride_pickup_verifications)
            .where(
                active_ride_pickup_verifications.c.verification_id
                == row["verification_id"]
            )
            .values(verified_at=now)
        )
        return True

    def add_evidence(self, evidence: EvidenceRecord) -> None:
        payload = evidence.model_dump()
        payload["evidence_references"] = list(evidence.evidence_references)
        self._connection.execute(insert(active_ride_evidence).values(**payload))

    def save_confidence(self, decision: ConfidenceDecision) -> None:
        self._connection.execute(
            insert(active_ride_confidence_decisions).values(**decision.model_dump())
        )
        self._outbox(
            decision.ride_id,
            "ride_confidence_evaluated",
            decision.generated_at,
            {
                "decision_id": str(decision.confidence_decision_id),
                "level": decision.health_level.value,
            },
        )

    def latest_confidence(self, ride_id: UUID) -> ConfidenceDecision | None:
        row = (
            self._connection.execute(
                select(active_ride_confidence_decisions)
                .where(active_ride_confidence_decisions.c.ride_id == ride_id)
                .order_by(active_ride_confidence_decisions.c.generated_at.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else ConfidenceDecision.model_validate(dict(row))

    def save_pickup_recommendation(self, item: PickupRecommendation) -> None:
        self._connection.execute(
            insert(active_ride_pickup_recommendations).values(
                recommendation_id=item.recommendation_id,
                ride_id=item.ride_id,
                payload=item.model_dump(mode="json"),
                confidence=item.confidence.value,
                material_change=item.material_change,
                change_status=item.change_status,
                generated_at=item.generated_at,
                expires_at=item.expires_at,
            )
        )

    def latest_pickup_recommendation(
        self, ride_id: UUID
    ) -> PickupRecommendation | None:
        row = (
            self._connection.execute(
                select(active_ride_pickup_recommendations)
                .where(active_ride_pickup_recommendations.c.ride_id == ride_id)
                .order_by(active_ride_pickup_recommendations.c.generated_at.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        return (
            None if row is None else PickupRecommendation.model_validate(row["payload"])
        )

    def decide_pickup_change(
        self, ride_id: UUID, recommendation_id: UUID, *, confirmed: bool
    ) -> PickupRecommendation:
        row = (
            self._connection.execute(
                select(active_ride_pickup_recommendations)
                .where(
                    active_ride_pickup_recommendations.c.ride_id == ride_id,
                    active_ride_pickup_recommendations.c.recommendation_id
                    == recommendation_id,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if (
            row is None
            or not row["material_change"]
            or row["change_status"] != "proposed"
        ):
            raise ActiveRideConflict("pickup_change_not_pending")
        status = "confirmed" if confirmed else "declined"
        payload = dict(row["payload"])
        payload["change_status"] = status
        self._connection.execute(
            update(active_ride_pickup_recommendations)
            .where(
                active_ride_pickup_recommendations.c.recommendation_id
                == recommendation_id
            )
            .values(change_status=status, payload=payload)
        )
        return PickupRecommendation.model_validate(payload)

    def _append_event(
        self, ride: ActiveRide, event_type: str, payload: dict[str, Any]
    ) -> None:
        event = RideEvent(
            ride_id=ride.ride_id,
            sequence=ride.last_sequence,
            aggregate_version=ride.version,
            event_type=event_type,
            occurred_at=ride.updated_at,
            payload=payload,
        )
        self._connection.execute(
            insert(active_ride_events).values(**event.model_dump())
        )
        self._outbox(
            ride.ride_id,
            event_type,
            ride.updated_at,
            {"event_id": str(event.event_id), "sequence": event.sequence},
        )

    def _outbox(
        self, ride_id: UUID, event_type: str, now: datetime, payload: dict[str, Any]
    ) -> None:
        self._connection.execute(
            insert(dispatch_outbox).values(
                message_id=uuid4(),
                aggregate_type="active_ride",
                aggregate_id=ride_id,
                event_type=event_type,
                payload={"ride_id": str(ride_id), **payload},
                occurred_at=now,
                available_at=now,
                attempt_count=0,
            )
        )

    def _checkpoint(self, ride: ActiveRide) -> None:
        for role in (ActorRole.RIDER, ActorRole.DRIVER):
            values = {
                "ride_id": ride.ride_id,
                "role": role.value,
                "projection": self.projection(ride, role),
                "aggregate_version": ride.version,
                "last_sequence": ride.last_sequence,
                "updated_at": ride.updated_at,
            }
            existing = self._connection.execute(
                select(active_ride_projection_checkpoints).where(
                    active_ride_projection_checkpoints.c.ride_id == ride.ride_id,
                    active_ride_projection_checkpoints.c.role == role.value,
                )
            ).first()
            if existing is None:
                self._connection.execute(
                    insert(active_ride_projection_checkpoints).values(**values)
                )
            else:
                self._connection.execute(
                    update(active_ride_projection_checkpoints)
                    .where(
                        active_ride_projection_checkpoints.c.ride_id == ride.ride_id,
                        active_ride_projection_checkpoints.c.role == role.value,
                    )
                    .values(**values)
                )

    @staticmethod
    def _rider_action(state: ActiveRideState) -> str | None:
        return (
            "provide_pickup_pin"
            if state is ActiveRideState.PICKUP_VERIFICATION_PENDING
            else None
        )

    @staticmethod
    def _driver_action(state: ActiveRideState) -> str | None:
        return {
            ActiveRideState.ASSIGNED: "start_to_pickup",
            ActiveRideState.DRIVER_EN_ROUTE: "arrive",
            ActiveRideState.PICKUP_VERIFICATION_PENDING: "enter_pickup_pin",
            ActiveRideState.PICKUP_VERIFIED: "start_trip",
            ActiveRideState.COMPLETION_PENDING: "complete_trip",
        }.get(state)
