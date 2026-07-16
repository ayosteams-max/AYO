import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, or_, select, update

from BACKEND.arrival_waiting.engine import ArrivalWaitingConflict
from BACKEND.arrival_waiting.models import (
    ArrivalEvaluation,
    EvidenceDecision,
    ReadinessDecision,
    WaitingPolicySnapshot,
    WaitingSession,
)
from BACKEND.persistence.tables import (
    arrival_evaluations,
    arrival_notification_evidence,
    arrival_waiting_idempotency,
    consequence_suppression_decisions,
    dispatch_outbox,
    rider_readiness_decisions,
    waiting_policy_snapshots,
    waiting_session_events,
    waiting_sessions,
)


class PostgresArrivalWaitingRepository:
    """Transactional persistence for privacy-minimized Mission 20 decisions."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def save_arrival(self, item: ArrivalEvaluation) -> None:
        self._connection.execute(
            insert(arrival_evaluations).values(
                evaluation_id=item.evaluation_id,
                ride_id=item.ride_id,
                assignment_id=item.assignment_id,
                state=item.state.value,
                confidence_bps=item.confidence_bps,
                observation_sequence=item.observation_sequence,
                payload=item.model_dump(mode="json"),
                evaluated_at=item.evaluated_at,
            )
        )
        if item.state.value == "arrival_verified":
            self.outbox(
                item.ride_id,
                "arrival.driver_arrival_verified",
                item.evaluated_at,
                {"evaluation_id": str(item.evaluation_id)},
            )

    def latest_arrival(self, ride_id: UUID) -> ArrivalEvaluation | None:
        payload = self._latest_payload(
            arrival_evaluations,
            ride_id,
            arrival_evaluations.c.evaluated_at,
        )
        return None if payload is None else ArrivalEvaluation.model_validate(payload)

    def save_readiness(self, item: ReadinessDecision) -> None:
        self._connection.execute(
            insert(rider_readiness_decisions).values(
                decision_id=item.decision_id,
                ride_id=item.ride_id,
                classification=item.classification.value,
                confidence_bps=item.confidence_bps,
                notification_recommended=item.notification_recommended,
                payload=item.model_dump(mode="json"),
                evaluated_at=item.evaluated_at,
                expires_at=item.expires_at,
            )
        )
        if item.notification_recommended:
            self.outbox(
                item.ride_id,
                "arrival.rider_start_walking_advised",
                item.evaluated_at,
                {"decision_id": str(item.decision_id)},
            )

    def latest_readiness(self, ride_id: UUID) -> ReadinessDecision | None:
        payload = self._latest_payload(
            rider_readiness_decisions,
            ride_id,
            rider_readiness_decisions.c.evaluated_at,
        )
        return None if payload is None else ReadinessDecision.model_validate(payload)

    def save_snapshot(self, item: WaitingPolicySnapshot) -> None:
        self._connection.execute(
            insert(waiting_policy_snapshots).values(
                snapshot_id=item.snapshot_id,
                ride_id=item.ride_id,
                source_policy_id=item.source_policy_id,
                source_policy_version=item.source_policy_version,
                payload=item.model_dump(mode="json"),
                selected_at=item.selected_at,
            )
        )

    def get_snapshot(self, snapshot_id: UUID) -> WaitingPolicySnapshot | None:
        payload = self._connection.execute(
            select(waiting_policy_snapshots.c.payload).where(
                waiting_policy_snapshots.c.snapshot_id == snapshot_id
            )
        ).scalar_one_or_none()
        return (
            None if payload is None else WaitingPolicySnapshot.model_validate(payload)
        )

    def create_session(self, item: WaitingSession) -> None:
        self._connection.execute(
            insert(waiting_sessions).values(**self._session_values(item))
        )
        self._event(item, "free_wait_started")
        self.outbox(
            item.ride_id,
            "arrival.free_wait_started",
            item.started_at,
            {"session_id": str(item.session_id)},
        )

    def latest_session(
        self, ride_id: UUID, *, lock: bool = False
    ) -> WaitingSession | None:
        query = (
            select(waiting_sessions.c.payload)
            .where(waiting_sessions.c.ride_id == ride_id)
            .order_by(waiting_sessions.c.started_at.desc())
            .limit(1)
        )
        if lock:
            query = query.with_for_update()
        payload = self._connection.execute(query).scalar_one_or_none()
        return None if payload is None else WaitingSession.model_validate(payload)

    def claim_due_sessions(self, *, now: datetime, limit: int) -> list[WaitingSession]:
        if not 1 <= limit <= 500:
            raise ValueError("Waiting recovery limit must be between 1 and 500")
        payloads = self._connection.execute(
            select(waiting_sessions.c.payload)
            .where(
                waiting_sessions.c.free_wait_deadline <= now,
                or_(
                    waiting_sessions.c.state == "free_wait_active",
                    waiting_sessions.c.state == "free_wait_ending",
                ),
            )
            .order_by(waiting_sessions.c.free_wait_deadline)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).scalars()
        return [WaitingSession.model_validate(payload) for payload in payloads]

    def update_session(self, item: WaitingSession, *, expected_version: int) -> None:
        changed = int(
            self._connection.execute(
                update(waiting_sessions)
                .where(
                    waiting_sessions.c.session_id == item.session_id,
                    waiting_sessions.c.version == expected_version,
                )
                .values(**self._session_values(item))
            ).rowcount
            or 0
        )
        if changed != 1:
            raise ArrivalWaitingConflict("stale_waiting_session")
        event = item.state.value
        self._event(item, event)
        outbox_type = {
            "free_wait_ending": "arrival.free_wait_ending",
            "wait_paused": "arrival.waiting_paused",
            "wait_invalidated": "arrival.waiting_invalidated",
        }.get(event)
        if outbox_type is not None:
            self.outbox(
                item.ride_id,
                outbox_type,
                item.updated_at,
                {"session_id": str(item.session_id)},
            )

    def save_evidence(self, item: EvidenceDecision) -> None:
        self._connection.execute(
            insert(consequence_suppression_decisions).values(
                evidence_id=item.evidence_id,
                ride_id=item.ride_id,
                session_id=item.session_id,
                ready=item.ready,
                responsibility=item.responsibility.value,
                confidence_bps=item.confidence_bps,
                payload=item.model_dump(mode="json"),
                evaluated_at=item.evaluated_at,
            )
        )
        self.outbox(
            item.ride_id,
            "arrival.evidence_ready"
            if item.ready
            else "arrival.consequence_suppressed",
            item.evaluated_at,
            {"evidence_id": str(item.evidence_id)},
        )

    def latest_evidence(self, ride_id: UUID) -> EvidenceDecision | None:
        payload = self._latest_payload(
            consequence_suppression_decisions,
            ride_id,
            consequence_suppression_decisions.c.evaluated_at,
        )
        return None if payload is None else EvidenceDecision.model_validate(payload)

    def record_notification(
        self,
        *,
        ride_id: UUID,
        session_id: UUID | None,
        intent_type: str,
        delivery_status: str,
        reason_code: str,
        occurred_at: datetime,
    ) -> None:
        self._connection.execute(
            insert(arrival_notification_evidence).values(
                notification_evidence_id=uuid4(),
                ride_id=ride_id,
                session_id=session_id,
                intent_type=intent_type,
                delivery_status=delivery_status,
                reason_code=reason_code,
                occurred_at=occurred_at,
            )
        )

    def idempotent_response(
        self,
        *,
        actor_id: UUID,
        command_id: UUID,
        ride_id: UUID,
        command_type: str,
        request_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        request_hash = self._hash(request_payload)
        row = (
            self._connection.execute(
                select(arrival_waiting_idempotency).where(
                    arrival_waiting_idempotency.c.actor_id == actor_id,
                    arrival_waiting_idempotency.c.command_id == command_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        if (
            row["ride_id"] != ride_id
            or row["command_type"] != command_type
            or row["request_hash"] != request_hash
        ):
            raise ArrivalWaitingConflict("idempotency_conflict")
        return dict(row["response_payload"])

    def save_idempotent_response(
        self,
        *,
        actor_id: UUID,
        command_id: UUID,
        ride_id: UUID,
        command_type: str,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any],
        now: datetime,
    ) -> None:
        self._connection.execute(
            insert(arrival_waiting_idempotency).values(
                actor_id=actor_id,
                command_id=command_id,
                ride_id=ride_id,
                command_type=command_type,
                request_hash=self._hash(request_payload),
                response_payload=response_payload,
                created_at=now,
            )
        )

    def outbox(
        self,
        ride_id: UUID,
        event_type: str,
        now: datetime,
        payload: dict[str, str],
    ) -> None:
        self._connection.execute(
            insert(dispatch_outbox).values(
                message_id=uuid4(),
                aggregate_type="arrival_waiting",
                aggregate_id=ride_id,
                event_type=event_type,
                payload={"ride_id": str(ride_id), **payload},
                occurred_at=now,
                available_at=now,
                attempt_count=0,
            )
        )

    def _latest_payload(self, table: Any, ride_id: UUID, ordering: Any) -> Any | None:
        return self._connection.execute(
            select(table.c.payload)
            .where(table.c.ride_id == ride_id)
            .order_by(ordering.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _session_values(self, item: WaitingSession) -> dict[str, Any]:
        return {
            "session_id": item.session_id,
            "ride_id": item.ride_id,
            "assignment_id": item.assignment_id,
            "policy_snapshot_id": item.policy_snapshot_id,
            "state": item.state.value,
            "version": item.version,
            "payload": item.model_dump(mode="json"),
            "started_at": item.started_at,
            "free_wait_deadline": item.free_wait_deadline,
            "updated_at": item.updated_at,
        }

    def _event(self, item: WaitingSession, event_type: str) -> None:
        self._connection.execute(
            insert(waiting_session_events).values(
                event_id=uuid4(),
                session_id=item.session_id,
                ride_id=item.ride_id,
                event_type=event_type,
                session_version=item.version,
                payload={
                    "state": item.state.value,
                    "reason_codes": list(item.reason_codes),
                },
                occurred_at=item.updated_at,
            )
        )

    @staticmethod
    def _hash(payload: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
