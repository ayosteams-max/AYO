import hashlib
import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.merchant_preparation.canonical import (
    CanonicalPreparationCase,
    CanonicalPreparationEvidence,
    CanonicalPreparationState,
)
from BACKEND.merchant_preparation.engine import PreparationConflict
from BACKEND.persistence.tables import (
    preparation_cases,
    preparation_evidence,
    preparation_idempotency,
    preparation_outbox,
    preparation_staff_authorities,
)


class PostgresCanonicalPreparationRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def admit(
        self, value: CanonicalPreparationCase, correlation_id: UUID, causation_id: UUID
    ) -> CanonicalPreparationCase:
        inserted = self._connection.execute(
            pg_insert(preparation_cases)
            .values(**value.model_dump(mode="python"))
            .on_conflict_do_nothing(index_elements=["decision_case_id"])
            .returning(preparation_cases.c.preparation_case_id)
        ).scalar_one_or_none()
        if inserted is None:
            row = (
                self._connection.execute(
                    select(preparation_cases).where(
                        preparation_cases.c.decision_case_id == value.decision_case_id
                    )
                )
                .mappings()
                .one()
            )
            return CanonicalPreparationCase.model_validate(dict(row))
        self._connection.execute(
            insert(preparation_outbox).values(
                message_id=uuid4(),
                preparation_case_id=value.preparation_case_id,
                event_type="commerce.preparation.admitted",
                schema_version=1,
                safe_payload={
                    "preparation_case_id": str(value.preparation_case_id),
                    "order_id": str(value.order_id),
                    "state": value.state.value,
                    "version": value.version,
                    "correlation_id": str(correlation_id),
                    "causation_id": str(causation_id),
                },
                occurred_at=value.created_at,
            )
        )
        return value

    def get(
        self, preparation_case_id: UUID, *, lock: bool = False
    ) -> CanonicalPreparationCase | None:
        statement = select(preparation_cases).where(
            preparation_cases.c.preparation_case_id == preparation_case_id
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return (
            None if row is None else CanonicalPreparationCase.model_validate(dict(row))
        )

    def reserve(
        self,
        actor: UUID,
        case_id: UUID,
        operation: str,
        key: str,
        payload: dict[str, Any],
        at: datetime,
    ) -> tuple[int | None, bool]:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        inserted = self._connection.execute(
            pg_insert(preparation_idempotency)
            .values(
                actor_identity_id=actor,
                preparation_case_id=case_id,
                operation=operation,
                idempotency_key=key,
                request_hash=digest,
                response_version=None,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(preparation_idempotency.c.preparation_case_id)
        ).scalar_one_or_none()
        if inserted is not None:
            return None, True
        row = (
            self._connection.execute(
                select(preparation_idempotency).where(
                    preparation_idempotency.c.actor_identity_id == actor,
                    preparation_idempotency.c.operation == operation,
                    preparation_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if row["preparation_case_id"] != case_id or row["request_hash"] != digest:
            raise PreparationConflict("idempotency_conflict")
        return cast(int | None, row["response_version"]), False

    def staff_authority(
        self,
        merchant_id: UUID,
        location_id: UUID,
        staff_id: UUID,
        action: str,
        at: datetime,
    ) -> str | None:
        row = self._connection.execute(
            select(preparation_staff_authorities.c.authority_basis).where(
                preparation_staff_authorities.c.merchant_id == merchant_id,
                preparation_staff_authorities.c.merchant_location_id == location_id,
                preparation_staff_authorities.c.staff_identity_id == staff_id,
                preparation_staff_authorities.c.action == action,
                preparation_staff_authorities.c.active.is_(True),
                preparation_staff_authorities.c.revoked_at.is_(None),
                preparation_staff_authorities.c.valid_from <= at,
                (preparation_staff_authorities.c.valid_until.is_(None))
                | (preparation_staff_authorities.c.valid_until > at),
            )
        ).scalar_one_or_none()
        return cast(str | None, row)

    def apply(
        self,
        current: CanonicalPreparationCase,
        target: CanonicalPreparationState,
        evidence: CanonicalPreparationEvidence,
        estimated_ready_at: datetime | None,
        actor: UUID,
        operation: str,
        key: str,
    ) -> CanonicalPreparationCase:
        result = self._connection.execute(
            update(preparation_cases)
            .where(
                preparation_cases.c.preparation_case_id == current.preparation_case_id,
                preparation_cases.c.state == current.state.value,
                preparation_cases.c.version == current.version,
            )
            .values(
                state=target.value,
                version=current.version + 1,
                estimated_ready_at=estimated_ready_at,
                updated_at=evidence.occurred_at,
            )
            .returning(preparation_cases.c.preparation_case_id)
        ).scalar_one_or_none()
        if result is None:
            raise PreparationConflict("preparation_version_conflict")
        values = evidence.model_dump(mode="python")
        self._connection.execute(insert(preparation_evidence).values(**values))
        self._connection.execute(
            update(preparation_idempotency)
            .where(
                preparation_idempotency.c.actor_identity_id == actor,
                preparation_idempotency.c.preparation_case_id
                == current.preparation_case_id,
                preparation_idempotency.c.operation == operation,
                preparation_idempotency.c.idempotency_key == key,
            )
            .values(response_version=current.version + 1)
        )
        self._outbox(evidence)
        return current.model_copy(
            update={
                "state": target,
                "version": current.version + 1,
                "estimated_ready_at": estimated_ready_at,
                "updated_at": evidence.occurred_at,
            }
        )

    def observe_overdue(
        self,
        current: CanonicalPreparationCase,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> CanonicalPreparationCase:
        if current.overdue_observed_at is not None:
            return current
        result = self._connection.execute(
            update(preparation_cases)
            .where(
                preparation_cases.c.preparation_case_id == current.preparation_case_id,
                preparation_cases.c.version == current.version,
                preparation_cases.c.overdue_observed_at.is_(None),
            )
            .values(overdue_observed_at=at, version=current.version + 1, updated_at=at)
            .returning(preparation_cases.c.preparation_case_id)
        ).scalar_one_or_none()
        if result is None:
            raise PreparationConflict("preparation_version_conflict")
        self._connection.execute(
            insert(preparation_outbox).values(
                message_id=uuid4(),
                preparation_case_id=current.preparation_case_id,
                event_type="commerce.preparation.overdue_observed",
                schema_version=1,
                safe_payload={
                    "preparation_case_id": str(current.preparation_case_id),
                    "order_id": str(current.order_id),
                    "state": current.state.value,
                    "version": current.version + 1,
                    "correlation_id": str(correlation_id),
                    "causation_id": str(causation_id),
                },
                occurred_at=at,
            )
        )
        return current.model_copy(
            update={
                "overdue_observed_at": at,
                "version": current.version + 1,
                "updated_at": at,
            }
        )

    def _outbox(self, evidence: CanonicalPreparationEvidence) -> None:
        self._connection.execute(
            insert(preparation_outbox).values(
                message_id=uuid4(),
                preparation_case_id=evidence.preparation_case_id,
                event_type=evidence.event_type,
                schema_version=1,
                safe_payload={
                    "preparation_case_id": str(evidence.preparation_case_id),
                    "order_id": str(evidence.order_id),
                    "state": evidence.to_state.value,
                    "version": evidence.case_version,
                    "failure_reason": None
                    if evidence.failure_reason is None
                    else evidence.failure_reason.value,
                    "correction_reason": None
                    if evidence.correction_reason is None
                    else evidence.correction_reason.value,
                    "correlation_id": str(evidence.correlation_id),
                    "causation_id": str(evidence.causation_id),
                    "evidence_hash": evidence.evidence_hash,
                },
                occurred_at=evidence.occurred_at,
            )
        )
