from datetime import datetime
from typing import Protocol
from uuid import UUID

from BACKEND.refund.models import (
    RefundAuthorization,
    RefundDecision,
    RefundEvidence,
    RefundRequest,
    RefundRequestState,
)


class RefundRepository(Protocol):
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

    def create_request(self, request: RefundRequest) -> RefundRequest: ...

    def get_request(
        self, refund_request_id: UUID, *, lock: bool = False
    ) -> RefundRequest | None: ...

    def transition_request(
        self,
        *,
        refund_request_id: UUID,
        target_state: RefundRequestState,
        at: datetime,
        correlation_id: UUID,
        causation_id: UUID,
        reason_code: str,
    ) -> RefundRequest: ...

    def append_decision(self, decision: RefundDecision) -> RefundDecision: ...

    def append_authorization(
        self, authorization: RefundAuthorization
    ) -> RefundAuthorization: ...

    def append_evidence(self, evidence: RefundEvidence) -> RefundEvidence: ...

    def list_decisions(self, refund_request_id: UUID) -> tuple[RefundDecision, ...]: ...

    def list_authorizations(
        self, refund_request_id: UUID
    ) -> tuple[RefundAuthorization, ...]: ...

    def list_evidence(self, refund_request_id: UUID) -> tuple[RefundEvidence, ...]: ...

    def list_requests_for_ride(self, ride_id: UUID) -> tuple[RefundRequest, ...]: ...
