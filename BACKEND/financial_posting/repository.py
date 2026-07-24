from datetime import datetime
from typing import Protocol
from uuid import UUID

from BACKEND.financial_posting.models import (
    FinancialPosting,
    FinancialPostingLine,
)


class FinancialPostingRepository(Protocol):
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

    def get_posting(self, posting_id: UUID) -> FinancialPosting | None: ...

    def list_lines(self, posting_id: UUID) -> tuple[FinancialPostingLine, ...]: ...

    def create_posting(
        self,
        posting: FinancialPosting,
        lines: tuple[FinancialPostingLine, ...],
    ) -> FinancialPosting: ...
