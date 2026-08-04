import hashlib
import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.merchant_orders.engine import MerchantOrderConflict
from BACKEND.merchant_orders.models import (
    MerchantDecisionCase,
    MerchantDecisionEvidence,
    MerchantDecisionState,
    MerchantOrderRecord,
    MerchantOrderView,
    MerchantStaffAuthority,
    OrderTimelineEvent,
    RejectionDecision,
)
from BACKEND.ordering.models import CanonicalOrder, OrderLineEvidence, OrderState
from BACKEND.persistence.tables import (
    commerce_merchant_action_idempotency,
    commerce_order_lines,
    commerce_order_outbox,
    commerce_order_rejections,
    commerce_order_timeline,
    commerce_orders,
    merchant_branches,
    merchant_decision_cases,
    merchant_decision_evidence,
    merchant_decision_idempotency,
    merchant_decision_outbox,
    merchant_profiles,
    merchant_staff_decision_authorities,
)


class PostgresMerchantOrderRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def reserve(
        self,
        *,
        actor_id: UUID,
        merchant_id: UUID,
        order_id: UUID,
        key: str,
        payload: dict[str, Any],
        at: datetime,
    ) -> tuple[int | None, bool]:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        inserted = self._connection.execute(
            pg_insert(commerce_merchant_action_idempotency)
            .values(
                actor_identity_id=actor_id,
                merchant_id=merchant_id,
                order_id=order_id,
                idempotency_key=key,
                request_hash=digest,
                response_version=None,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(commerce_merchant_action_idempotency.c.order_id)
        ).scalar_one_or_none()
        if inserted is not None:
            return None, True
        row = (
            self._connection.execute(
                select(commerce_merchant_action_idempotency).where(
                    commerce_merchant_action_idempotency.c.actor_identity_id
                    == actor_id,
                    commerce_merchant_action_idempotency.c.merchant_id == merchant_id,
                    commerce_merchant_action_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if row["request_hash"] != digest or row["order_id"] != order_id:
            raise MerchantOrderConflict("idempotency_conflict")
        return cast(int | None, row["response_version"]), False

    def branch_is_active(self, merchant_id: UUID, location_id: UUID) -> bool:
        return (
            self._connection.execute(
                select(merchant_branches.c.branch_id).where(
                    merchant_branches.c.branch_id == location_id,
                    merchant_branches.c.merchant_id == merchant_id,
                    merchant_branches.c.active.is_(True),
                )
            ).scalar_one_or_none()
            is not None
        )

    def staff_authority(
        self,
        *,
        merchant_id: UUID,
        location_id: UUID,
        staff_identity_id: UUID,
        at: datetime,
    ) -> MerchantStaffAuthority | None:
        row = (
            self._connection.execute(
                select(merchant_staff_decision_authorities)
                .join(
                    merchant_profiles,
                    merchant_profiles.c.merchant_id
                    == merchant_staff_decision_authorities.c.merchant_id,
                )
                .where(
                    merchant_staff_decision_authorities.c.merchant_id == merchant_id,
                    merchant_staff_decision_authorities.c.merchant_location_id
                    == location_id,
                    merchant_staff_decision_authorities.c.staff_identity_id
                    == staff_identity_id,
                    merchant_staff_decision_authorities.c.active.is_(True),
                    merchant_staff_decision_authorities.c.valid_from <= at,
                    (
                        merchant_staff_decision_authorities.c.valid_until.is_(None)
                        | (merchant_staff_decision_authorities.c.valid_until > at)
                    ),
                    merchant_staff_decision_authorities.c.revoked_at.is_(None),
                    merchant_staff_decision_authorities.c.granted_by_identity_id
                    == merchant_profiles.c.owner_identity_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else MerchantStaffAuthority.model_validate(dict(row))

    def admit_decision_case(self, value: MerchantDecisionCase) -> MerchantDecisionCase:
        inserted = self._connection.execute(
            pg_insert(merchant_decision_cases)
            .values(**value.model_dump(mode="python"))
            .on_conflict_do_nothing(index_elements=["order_id"])
            .returning(merchant_decision_cases.c.decision_case_id)
        ).scalar_one_or_none()
        if inserted is None:
            existing = self.get_decision_case_by_order(value.order_id)
            if existing is None:
                raise MerchantOrderConflict("merchant_decision_admission_conflict")
            return existing
        return value

    def get_decision_case(
        self, decision_case_id: UUID, *, lock: bool = False
    ) -> MerchantDecisionCase | None:
        statement = select(merchant_decision_cases).where(
            merchant_decision_cases.c.decision_case_id == decision_case_id
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return None if row is None else MerchantDecisionCase.model_validate(dict(row))

    def get_decision_case_by_order(self, order_id: UUID) -> MerchantDecisionCase | None:
        row = (
            self._connection.execute(
                select(merchant_decision_cases).where(
                    merchant_decision_cases.c.order_id == order_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else MerchantDecisionCase.model_validate(dict(row))

    def get_decision_evidence(
        self, decision_case_id: UUID
    ) -> MerchantDecisionEvidence | None:
        row = (
            self._connection.execute(
                select(merchant_decision_evidence).where(
                    merchant_decision_evidence.c.decision_case_id == decision_case_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return (
            None if row is None else MerchantDecisionEvidence.model_validate(dict(row))
        )

    def reserve_decision(
        self,
        *,
        actor_identity_id: UUID,
        decision_case_id: UUID,
        operation: str,
        key: str,
        payload: dict[str, Any],
        at: datetime,
    ) -> tuple[int | None, bool]:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        inserted = self._connection.execute(
            pg_insert(merchant_decision_idempotency)
            .values(
                actor_identity_id=actor_identity_id,
                decision_case_id=decision_case_id,
                operation=operation,
                idempotency_key=key,
                request_hash=digest,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(merchant_decision_idempotency.c.idempotency_key)
        ).scalar_one_or_none()
        if inserted is not None:
            return None, True
        row = (
            self._connection.execute(
                select(merchant_decision_idempotency).where(
                    merchant_decision_idempotency.c.actor_identity_id
                    == actor_identity_id,
                    merchant_decision_idempotency.c.operation == operation,
                    merchant_decision_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if row["request_hash"] != digest or row["decision_case_id"] != decision_case_id:
            raise MerchantOrderConflict("idempotency_conflict")
        return cast(int | None, row["response_version"]), False

    def terminal_decision(
        self,
        current: MerchantDecisionCase,
        evidence: MerchantDecisionEvidence,
        *,
        idempotency_actor_id: UUID | None,
        idempotency_key: str | None,
    ) -> MerchantDecisionCase:
        next_version = current.version + 1
        updated = self._connection.execute(
            update(merchant_decision_cases)
            .where(
                merchant_decision_cases.c.decision_case_id == current.decision_case_id,
                merchant_decision_cases.c.state == MerchantDecisionState.PENDING.value,
                merchant_decision_cases.c.version == current.version,
            )
            .values(
                state=evidence.result.value,
                version=next_version,
                updated_at=evidence.decided_at,
            )
            .returning(merchant_decision_cases.c.decision_case_id)
        ).scalar_one_or_none()
        if updated is None:
            raise MerchantOrderConflict("merchant_decision_version_conflict")
        values = evidence.model_dump(mode="python")
        self._connection.execute(insert(merchant_decision_evidence).values(**values))
        if idempotency_actor_id is not None and idempotency_key is not None:
            self._connection.execute(
                update(merchant_decision_idempotency)
                .where(
                    merchant_decision_idempotency.c.actor_identity_id
                    == idempotency_actor_id,
                    merchant_decision_idempotency.c.decision_case_id
                    == current.decision_case_id,
                    merchant_decision_idempotency.c.idempotency_key == idempotency_key,
                )
                .values(response_version=next_version)
            )
        event_suffix = (
            "merchant_decision_expired"
            if evidence.result is MerchantDecisionState.EXPIRED
            else evidence.result.value
        )
        self._connection.execute(
            insert(merchant_decision_outbox).values(
                message_id=uuid4(),
                decision_case_id=current.decision_case_id,
                event_type=f"commerce.order.{event_suffix}",
                schema_version=1,
                safe_payload={
                    "decision_case_id": str(current.decision_case_id),
                    "order_id": str(current.order_id),
                    "merchant_id": str(current.merchant_id),
                    "merchant_location_id": str(current.merchant_location_id),
                    "state": evidence.result.value,
                    "version": next_version,
                    "rejection_reason": (
                        None
                        if evidence.rejection_reason is None
                        else evidence.rejection_reason.value
                    ),
                    "policy_name": evidence.policy_name,
                    "policy_version": evidence.policy_version,
                    "correlation_id": str(evidence.correlation_id),
                    "causation_id": str(evidence.causation_id),
                    "evidence_hash": evidence.evidence_hash,
                },
                occurred_at=evidence.decided_at,
            )
        )
        return current.model_copy(
            update={
                "state": evidence.result,
                "version": next_version,
                "updated_at": evidence.decided_at,
            }
        )

    def due_decision_cases(
        self, *, at: datetime, limit: int
    ) -> tuple[MerchantDecisionCase, ...]:
        rows = self._connection.execute(
            select(merchant_decision_cases)
            .where(
                merchant_decision_cases.c.state == MerchantDecisionState.PENDING.value,
                merchant_decision_cases.c.expires_at <= at,
            )
            .order_by(
                merchant_decision_cases.c.expires_at,
                merchant_decision_cases.c.decision_case_id,
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).mappings()
        return tuple(MerchantDecisionCase.model_validate(dict(row)) for row in rows)

    def get_order(self, order_id: UUID, *, lock: bool = False) -> CanonicalOrder | None:
        statement = select(commerce_orders).where(
            commerce_orders.c.order_id == order_id
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return None if row is None else self._order(row)

    def list_for_merchant(
        self, merchant_id: UUID, *, state: str | None, limit: int
    ) -> tuple[MerchantOrderView, ...]:
        statement = select(commerce_orders.c.order_id).where(
            commerce_orders.c.merchant_id == merchant_id
        )
        if state is not None:
            try:
                canonical_state = OrderState(state).value
            except ValueError as error:
                raise MerchantOrderConflict("order_state_invalid") from error
            statement = statement.where(commerce_orders.c.state == canonical_state)
        ids = self._connection.execute(
            statement.order_by(
                commerce_orders.c.created_at.desc(), commerce_orders.c.order_id
            ).limit(limit)
        ).scalars()
        return tuple(
            value for order_id in ids if (value := self.get_view(order_id)) is not None
        )

    def get_view(self, order_id: UUID) -> MerchantOrderView | None:
        order = self.get_order(order_id)
        if order is None:
            return None
        timeline_rows = self._connection.execute(
            select(commerce_order_timeline)
            .where(commerce_order_timeline.c.order_id == order_id)
            .order_by(
                commerce_order_timeline.c.order_version,
                commerce_order_timeline.c.occurred_at,
                commerce_order_timeline.c.event_id,
            )
        ).mappings()
        rejection_row = (
            self._connection.execute(
                select(commerce_order_rejections).where(
                    commerce_order_rejections.c.order_id == order_id
                )
            )
            .mappings()
            .one_or_none()
        )
        safe_order = MerchantOrderRecord.model_validate(
            order.model_dump(exclude={"customer_identity_id"})
        )
        return MerchantOrderView(
            order=safe_order,
            timeline=tuple(
                OrderTimelineEvent.model_validate(dict(row)) for row in timeline_rows
            ),
            rejection=None
            if rejection_row is None
            else RejectionDecision.model_validate(dict(rejection_row)),
        )

    def transition(
        self,
        current: CanonicalOrder,
        *,
        target: OrderState,
        actor_id: UUID,
        customer_reason_code: str | None,
        customer_message: str | None,
        internal_merchant_note: str | None,
        idempotency_key: str,
        at: datetime,
    ) -> MerchantOrderView:
        next_version = current.version + 1
        updated = self._connection.execute(
            update(commerce_orders)
            .where(
                commerce_orders.c.order_id == current.order_id,
                commerce_orders.c.merchant_id == current.merchant_id,
                commerce_orders.c.state == current.state.value,
                commerce_orders.c.version == current.version,
            )
            .values(state=target.value, version=next_version)
            .returning(commerce_orders.c.order_id)
        ).scalar_one_or_none()
        if updated is None:
            raise MerchantOrderConflict("order_version_conflict")
        if target is OrderState.REJECTED:
            self._connection.execute(
                insert(commerce_order_rejections).values(
                    order_id=current.order_id,
                    customer_reason_code=customer_reason_code,
                    customer_message=customer_message,
                    internal_merchant_note=internal_merchant_note,
                    decided_by_identity_id=actor_id,
                    decided_at=at,
                )
            )
        self._connection.execute(
            insert(commerce_order_timeline).values(
                event_id=uuid4(),
                order_id=current.order_id,
                merchant_id=current.merchant_id,
                event_type=f"commerce.order.{target.value}",
                from_state=current.state.value,
                to_state=target.value,
                actor_identity_id=actor_id,
                order_version=next_version,
                customer_reason_code=customer_reason_code,
                occurred_at=at,
            )
        )
        self._connection.execute(
            update(commerce_merchant_action_idempotency)
            .where(
                commerce_merchant_action_idempotency.c.actor_identity_id == actor_id,
                commerce_merchant_action_idempotency.c.merchant_id
                == current.merchant_id,
                commerce_merchant_action_idempotency.c.order_id == current.order_id,
                commerce_merchant_action_idempotency.c.idempotency_key
                == idempotency_key,
                commerce_merchant_action_idempotency.c.response_version.is_(None),
            )
            .values(response_version=next_version)
        )
        self._connection.execute(
            insert(commerce_order_outbox).values(
                message_id=uuid4(),
                order_id=current.order_id,
                event_type=f"commerce.order.{target.value}",
                safe_payload={
                    "order_id": str(current.order_id),
                    "state": target.value,
                    "version": next_version,
                    "customer_reason_code": customer_reason_code,
                },
                occurred_at=at,
                attempt_count=0,
            )
        )
        result = self.get_view(current.order_id)
        if result is None:
            raise MerchantOrderConflict("merchant_order_not_found")
        return result

    def _order(self, row: Any) -> CanonicalOrder:
        line_rows = self._connection.execute(
            select(commerce_order_lines)
            .where(commerce_order_lines.c.order_id == row["order_id"])
            .order_by(commerce_order_lines.c.line_number)
        ).mappings()
        return CanonicalOrder(
            order_id=row["order_id"],
            customer_identity_id=row["customer_identity_id"],
            merchant_id=row["merchant_id"],
            merchant_display_name=row["merchant_display_name"],
            state=row["state"],
            lines=tuple(
                OrderLineEvidence.model_validate(
                    {
                        key: value
                        for key, value in line.items()
                        if key not in {"order_id", "line_number"}
                    }
                )
                for line in line_rows
            ),
            pricing=row["pricing_evidence"],
            evidence_hash=row["evidence_hash"],
            version=row["version"],
            created_at=row["created_at"],
        )
