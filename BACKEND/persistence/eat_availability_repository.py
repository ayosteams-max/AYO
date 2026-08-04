from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.eat_availability.engine import EatAvailabilityConflict, canonical_hash
from BACKEND.eat_availability.models import (
    EatAvailabilityEvaluation,
    EatAvailabilityPolicy,
)
from BACKEND.persistence.errors import OptimisticConcurrencyError
from BACKEND.persistence.tables import (
    p2_eat_availability_evaluations,
    p2_eat_availability_idempotency,
    p2_eat_availability_outbox,
    p2_eat_availability_policies,
    p2_eat_availability_policy_history,
)


class PostgresEatAvailabilityRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def reserve(
        self,
        *,
        actor_identity_id: UUID,
        operation: str,
        key: str,
        payload: dict[str, Any],
        at: datetime,
    ) -> str | None:
        digest = canonical_hash(payload)
        inserted = self._connection.execute(
            pg_insert(p2_eat_availability_idempotency)
            .values(
                actor_identity_id=actor_identity_id,
                operation=operation,
                idempotency_key=key,
                request_hash=digest,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(p2_eat_availability_idempotency.c.idempotency_key)
        ).scalar_one_or_none()
        if inserted is not None:
            return None
        row = (
            self._connection.execute(
                select(p2_eat_availability_idempotency).where(
                    p2_eat_availability_idempotency.c.actor_identity_id
                    == actor_identity_id,
                    p2_eat_availability_idempotency.c.operation == operation,
                    p2_eat_availability_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if row["request_hash"] != digest:
            raise EatAvailabilityConflict("idempotency_conflict")
        return row["response_reference"]

    def complete(
        self,
        *,
        actor_identity_id: UUID,
        operation: str,
        key: str,
        response_reference: str,
    ) -> None:
        self._connection.execute(
            update(p2_eat_availability_idempotency)
            .where(
                p2_eat_availability_idempotency.c.actor_identity_id
                == actor_identity_id,
                p2_eat_availability_idempotency.c.operation == operation,
                p2_eat_availability_idempotency.c.idempotency_key == key,
            )
            .values(response_reference=response_reference)
        )

    def get(self, policy_id: UUID) -> EatAvailabilityPolicy | None:
        row = (
            self._connection.execute(
                select(p2_eat_availability_policies).where(
                    p2_eat_availability_policies.c.policy_id == policy_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else EatAvailabilityPolicy.model_validate(dict(row))

    def find(
        self, *, merchant_id: UUID, area_reference: str
    ) -> EatAvailabilityPolicy | None:
        row = (
            self._connection.execute(
                select(p2_eat_availability_policies).where(
                    p2_eat_availability_policies.c.merchant_id == merchant_id,
                    p2_eat_availability_policies.c.product_code == "ayo_eat",
                    p2_eat_availability_policies.c.area_reference == area_reference,
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else EatAvailabilityPolicy.model_validate(dict(row))

    def put(
        self, policy: EatAvailabilityPolicy, *, expected_version: int | None
    ) -> EatAvailabilityPolicy:
        values = policy.model_dump(mode="python")
        if expected_version is None:
            self._connection.execute(
                insert(p2_eat_availability_policies).values(**values)
            )
        else:
            row = self._connection.execute(
                update(p2_eat_availability_policies)
                .where(
                    p2_eat_availability_policies.c.policy_id == policy.policy_id,
                    p2_eat_availability_policies.c.version == expected_version,
                )
                .values(**values)
                .returning(p2_eat_availability_policies.c.policy_id)
            ).scalar_one_or_none()
            if row is None:
                raise OptimisticConcurrencyError(
                    "P2 Eat availability policy changed concurrently"
                )
        payload = policy.model_dump(mode="json")
        self._connection.execute(
            insert(p2_eat_availability_policy_history).values(
                history_id=uuid4(),
                policy_id=policy.policy_id,
                policy_version=policy.version,
                immutable_payload=payload,
                evidence_hash=canonical_hash(payload),
                recorded_at=policy.updated_at,
            )
        )
        self._connection.execute(
            insert(p2_eat_availability_outbox).values(
                message_id=uuid4(),
                aggregate_id=policy.policy_id,
                event_type="eat.availability.configured",
                safe_payload={
                    "policy_id": str(policy.policy_id),
                    "merchant_id": str(policy.merchant_id),
                    "state": policy.state.value,
                    "version": policy.version,
                },
                occurred_at=policy.updated_at,
            )
        )
        return policy

    def record_evaluation(
        self, evaluation: EatAvailabilityEvaluation
    ) -> EatAvailabilityEvaluation:
        values = evaluation.model_dump(mode="python")
        values["item_references"] = [str(value) for value in evaluation.item_references]
        self._connection.execute(
            insert(p2_eat_availability_evaluations).values(**values)
        )
        self._connection.execute(
            insert(p2_eat_availability_outbox).values(
                message_id=uuid4(),
                aggregate_id=evaluation.evaluation_id,
                event_type="eat.availability.evaluated",
                safe_payload={
                    "evaluation_id": str(evaluation.evaluation_id),
                    "merchant_id": str(evaluation.merchant_id),
                    "outcome": evaluation.outcome.value,
                    "policy_version": evaluation.policy_version,
                },
                occurred_at=evaluation.evaluated_at,
            )
        )
        return evaluation
