from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.financial_control.authorization import (
    FINANCIAL_HOLD_CANCEL_PERMISSION,
    FINANCIAL_HOLD_CREATE_PERMISSION,
    FINANCIAL_HOLD_ESCALATE_PERMISSION,
    FINANCIAL_HOLD_EXPIRE_PERMISSION,
    FINANCIAL_HOLD_RELEASE_PERMISSION,
    FINANCIAL_HOLD_REVIEW_PERMISSION,
    FINANCIAL_HOLD_TRACE_READ_PERMISSION,
    SUPPORT_FINANCIAL_HOLD_READ_STATUS_PERMISSION,
    is_service_identity,
)
from BACKEND.financial_control.engine import (
    FinancialHoldConflict,
    ensure_transition_allowed,
)
from BACKEND.financial_control.models import (
    FinancialHold,
    FinancialHoldCreateCommand,
    FinancialHoldResult,
    FinancialHoldSourceType,
    FinancialHoldState,
    FinancialHoldStateHistory,
    FinancialHoldTransitionCommand,
    FinancialHoldType,
)
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.persistence.tables import wallet_accounts


class FinancialHoldStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hold: FinancialHold
    history: tuple[FinancialHoldStateHistory, ...]


class FinancialHoldApplicationService:
    def __init__(self, composition: PostgresRepositoryComposition) -> None:
        self._composition = composition

    def create_hold(
        self,
        subject: AuthorizationSubject,
        command: FinancialHoldCreateCommand,
    ) -> FinancialHoldResult:
        self._require_permission(
            subject,
            FINANCIAL_HOLD_CREATE_PERMISSION,
            at=command.occurred_at,
        )
        self._require_service_identity(subject)
        self._assert_type_source_compatibility(command.hold_type, command.source_type)

        candidate = uuid4()
        with self._composition.unit_of_work() as unit:
            self._assert_lineage_exists(
                unit,
                source_type=command.source_type,
                source_id=command.source_id,
            )
            canonical = unit.financial_holds.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="financial.hold.create",
                key=command.idempotency_key,
                payload={
                    "hold_type": command.hold_type.value,
                    "source_type": command.source_type.value,
                    "source_id": str(command.source_id),
                    "reason_code": command.reason.reason_code.value,
                    "reason_detail": command.reason.reason_detail or "",
                },
                response_reference=candidate,
                at=command.occurred_at,
            )
            existing = unit.financial_holds.get_hold(canonical)
            if existing is not None:
                return FinancialHoldResult(
                    hold=existing,
                    history=unit.financial_holds.list_history(existing.hold_id),
                )

            hold = FinancialHold(
                hold_id=canonical,
                hold_type=command.hold_type,
                source_type=command.source_type,
                source_id=command.source_id,
                reason_code=command.reason.reason_code,
                reason_detail=command.reason.reason_detail,
                state=FinancialHoldState.CREATED,
                created_by_identity_id=subject.identity_id,
                correlation_id=command.correlation_id,
                causation_id=command.causation_id,
                created_at=command.occurred_at,
                updated_at=command.occurred_at,
            )
            history = FinancialHoldStateHistory(
                hold_id=hold.hold_id,
                from_state=None,
                to_state=FinancialHoldState.CREATED,
                reason_code=command.reason.reason_code,
                reason_detail=command.reason.reason_detail,
                changed_by_identity_id=subject.identity_id,
                changed_at=command.occurred_at,
                correlation_id=command.correlation_id,
                causation_id=command.causation_id,
            )
            unit.financial_holds.create_hold(hold, history)
            return FinancialHoldResult(hold=hold, history=(history,))

    def transition_hold(
        self,
        subject: AuthorizationSubject,
        *,
        hold_id: UUID,
        command: FinancialHoldTransitionCommand,
    ) -> FinancialHoldResult:
        self._require_permission(
            subject,
            self._permission_for_target(command.target_state),
            at=command.occurred_at,
        )
        self._require_service_identity(subject)

        candidate = hold_id
        with self._composition.unit_of_work() as unit:
            canonical = unit.financial_holds.reserve_idempotency(
                actor_id=subject.identity_id,
                operation=f"financial.hold.transition.{command.target_state.value}",
                key=command.idempotency_key,
                payload={
                    "hold_id": str(hold_id),
                    "target_state": command.target_state.value,
                    "reason_code": command.reason.reason_code.value,
                    "reason_detail": command.reason.reason_detail or "",
                },
                response_reference=candidate,
                at=command.occurred_at,
            )
            if canonical != hold_id:
                raise FinancialHoldConflict(
                    "financial_hold_idempotency_reference_mismatch"
                )

            hold = unit.financial_holds.get_hold(hold_id, lock=True)
            if hold is None:
                raise FinancialHoldConflict("financial_hold_not_found")
            if hold.state is command.target_state:
                return FinancialHoldResult(
                    hold=hold,
                    history=unit.financial_holds.list_history(hold.hold_id),
                )
            ensure_transition_allowed(
                hold.state, command.target_state, at=command.occurred_at
            )

            history = FinancialHoldStateHistory(
                hold_id=hold.hold_id,
                from_state=hold.state,
                to_state=command.target_state,
                reason_code=command.reason.reason_code,
                reason_detail=command.reason.reason_detail,
                changed_by_identity_id=subject.identity_id,
                changed_at=command.occurred_at,
                correlation_id=command.correlation_id,
                causation_id=command.causation_id,
            )
            updated = unit.financial_holds.transition_hold(
                hold_id=hold.hold_id,
                target_state=command.target_state,
                updated_at=command.occurred_at,
                history=history,
            )
            return FinancialHoldResult(
                hold=updated,
                history=unit.financial_holds.list_history(hold.hold_id),
            )

    def hold_status(
        self,
        subject: AuthorizationSubject,
        *,
        hold_id: UUID,
        at: datetime,
    ) -> FinancialHoldStatus:
        with self._composition.unit_of_work() as unit:
            hold = unit.financial_holds.get_hold(hold_id)
            if hold is None:
                raise FinancialHoldConflict("financial_hold_not_found")
            if not unit.authorization.has_permission(
                subject.identity_id,
                FINANCIAL_HOLD_TRACE_READ_PERMISSION,
                at=at,
            ) and not unit.authorization.has_permission(
                subject.identity_id,
                SUPPORT_FINANCIAL_HOLD_READ_STATUS_PERMISSION,
                at=at,
            ):
                raise FinancialHoldConflict("financial_hold_status_not_found")
            return FinancialHoldStatus(
                hold=hold,
                history=unit.financial_holds.list_history(hold.hold_id),
            )

    @staticmethod
    def _permission_for_target(target: FinancialHoldState) -> str:
        if target is FinancialHoldState.UNDER_REVIEW:
            return FINANCIAL_HOLD_REVIEW_PERMISSION
        if target is FinancialHoldState.RELEASED:
            return FINANCIAL_HOLD_RELEASE_PERMISSION
        if target is FinancialHoldState.ESCALATED:
            return FINANCIAL_HOLD_ESCALATE_PERMISSION
        if target is FinancialHoldState.EXPIRED:
            return FINANCIAL_HOLD_EXPIRE_PERMISSION
        if target is FinancialHoldState.CANCELLED:
            return FINANCIAL_HOLD_CANCEL_PERMISSION
        if target is FinancialHoldState.ACTIVE:
            return FINANCIAL_HOLD_REVIEW_PERMISSION
        raise FinancialHoldConflict("financial_hold_transition_invalid")

    @staticmethod
    def _assert_type_source_compatibility(
        hold_type: FinancialHoldType,
        source_type: FinancialHoldSourceType,
    ) -> None:
        allowed = {
            FinancialHoldType.RIDER_PAYMENT: FinancialHoldSourceType.PAYMENT_ATTEMPT,
            FinancialHoldType.DRIVER_PAYOUT: FinancialHoldSourceType.SETTLEMENT_BATCH,
            FinancialHoldType.WALLET: FinancialHoldSourceType.WALLET_ACCOUNT,
            FinancialHoldType.REFUND: FinancialHoldSourceType.REFUND_REQUEST,
            FinancialHoldType.SETTLEMENT: FinancialHoldSourceType.SETTLEMENT_BATCH,
            FinancialHoldType.FRAUD_REVIEW: FinancialHoldSourceType.IDENTITY,
            FinancialHoldType.COMPLIANCE_REVIEW: FinancialHoldSourceType.IDENTITY,
            FinancialHoldType.FINANCE_MANUAL_REVIEW: FinancialHoldSourceType.FINANCIAL_POSTING,
        }
        if allowed[hold_type] is not source_type:
            raise FinancialHoldConflict("financial_hold_source_type_invalid")

    @staticmethod
    def _assert_lineage_exists(
        unit: Any,
        *,
        source_type: FinancialHoldSourceType,
        source_id: UUID,
    ) -> None:
        if source_type is FinancialHoldSourceType.PAYMENT_ATTEMPT:
            found = unit.payments.get_attempt(source_id) is not None
        elif source_type is FinancialHoldSourceType.SETTLEMENT_BATCH:
            found = unit.settlements.get_batch(source_id) is not None
        elif source_type is FinancialHoldSourceType.WALLET_ACCOUNT:
            found = (
                unit.connection.execute(
                    select(wallet_accounts.c.wallet_account_id).where(
                        wallet_accounts.c.wallet_account_id == source_id
                    )
                ).scalar_one_or_none()
                is not None
            )
        elif source_type is FinancialHoldSourceType.REFUND_REQUEST:
            found = unit.refunds.get_request(source_id) is not None
        elif source_type is FinancialHoldSourceType.FINANCIAL_POSTING:
            found = unit.financial_postings.get_posting(source_id) is not None
        elif source_type is FinancialHoldSourceType.IDENTITY:
            found = unit.identities.get(source_id) is not None
        else:
            found = False
        if not found:
            raise FinancialHoldConflict("financial_hold_lineage_missing")

    def _require_permission(
        self,
        subject: AuthorizationSubject,
        permission: str,
        *,
        at: datetime,
    ) -> None:
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, permission, at=at
            ):
                raise FinancialHoldConflict("access_denied")

    @staticmethod
    def _require_service_identity(subject: AuthorizationSubject) -> None:
        if not is_service_identity(subject.identity_type):
            raise FinancialHoldConflict("financial_hold_service_identity_required")
