from typing import Protocol
from uuid import UUID

from BACKEND.audit.models import AuditEvent


class AuditEventRepository(Protocol):
    """Append/read-only audit persistence boundary."""

    def append(self, event: AuditEvent) -> AuditEvent: ...

    def get(self, event_id: UUID) -> AuditEvent | None: ...

    def find_by_correlation(
        self, correlation_id: UUID, *, limit: int = 100
    ) -> list[AuditEvent]: ...
