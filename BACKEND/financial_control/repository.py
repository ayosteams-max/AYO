from datetime import datetime
from typing import Protocol
from uuid import UUID

from BACKEND.financial_control.models import (
    FinancialHold,
    FinancialHoldSourceType,
    FinancialHoldState,
    FinancialHoldStateHistory,
)


class FinancialHoldRepository(Protocol):
    def reserve_idempotency(
        self,
        *,
        actor_id: UUID,
        operation: str,
        key: str,
        payload: dict[str, str],
        response_reference: UUID,
        at: datetime,
    ) -> UUID: ...

    def get_hold(
        self, hold_id: UUID, *, lock: bool = False
    ) -> FinancialHold | None: ...

    def list_holds_for_source(
        self, *, source_type: FinancialHoldSourceType, source_id: UUID
    ) -> tuple[FinancialHold, ...]: ...

    def create_hold(
        self,
        hold: FinancialHold,
        initial_history: FinancialHoldStateHistory,
    ) -> FinancialHold: ...

    def transition_hold(
        self,
        *,
        hold_id: UUID,
        target_state: FinancialHoldState,
        updated_at: datetime,
        history: FinancialHoldStateHistory,
    ) -> FinancialHold: ...

    def list_history(self, hold_id: UUID) -> tuple[FinancialHoldStateHistory, ...]: ...
