from datetime import datetime
from typing import Protocol
from uuid import UUID

from BACKEND.settlement.models import (
    ReconciliationException,
    ReconciliationRecord,
    SettlementApproval,
    SettlementBatch,
    SettlementBatchState,
    SettlementExternalEvidence,
    SettlementHoldEvidence,
    SettlementItem,
)


class SettlementRepository(Protocol):
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

    def create_batch(self, batch: SettlementBatch) -> SettlementBatch: ...

    def get_batch(
        self, settlement_batch_id: UUID, *, lock: bool = False
    ) -> SettlementBatch | None: ...

    def transition_batch(
        self,
        *,
        settlement_batch_id: UUID,
        target_state: SettlementBatchState,
        at: datetime,
        correlation_id: UUID,
        causation_id: UUID,
        reason_code: str,
    ) -> SettlementBatch: ...

    def add_item(self, item: SettlementItem) -> SettlementItem: ...

    def get_item(
        self, settlement_item_id: UUID, *, lock: bool = False
    ) -> SettlementItem | None: ...

    def list_items(self, settlement_batch_id: UUID) -> tuple[SettlementItem, ...]: ...

    def append_reconciliation_record(
        self, record: ReconciliationRecord
    ) -> ReconciliationRecord: ...

    def list_reconciliation_records(
        self, settlement_batch_id: UUID
    ) -> tuple[ReconciliationRecord, ...]: ...

    def append_exception(
        self, exception: ReconciliationException
    ) -> ReconciliationException: ...

    def list_exceptions(
        self, settlement_batch_id: UUID
    ) -> tuple[ReconciliationException, ...]: ...

    def append_approval(self, approval: SettlementApproval) -> SettlementApproval: ...

    def list_approvals(
        self, settlement_batch_id: UUID
    ) -> tuple[SettlementApproval, ...]: ...

    def append_hold_evidence(
        self, evidence: SettlementHoldEvidence
    ) -> SettlementHoldEvidence: ...

    def list_hold_evidence(
        self, settlement_batch_id: UUID
    ) -> tuple[SettlementHoldEvidence, ...]: ...

    def append_external_evidence(
        self, evidence: SettlementExternalEvidence
    ) -> SettlementExternalEvidence: ...

    def list_external_evidence(
        self, settlement_batch_id: UUID
    ) -> tuple[SettlementExternalEvidence, ...]: ...
