from datetime import datetime
from typing import Protocol
from uuid import UUID

from BACKEND.session.models import SessionRecord


class SessionRepository(Protocol):
    def create(self, session: SessionRecord) -> SessionRecord: ...

    def get(self, session_id: UUID) -> SessionRecord | None: ...

    def find_active_by_token_hash(
        self, token_hash: bytes, *, at: datetime
    ) -> SessionRecord | None: ...

    def revoke(
        self, session_id: UUID, *, revoked_at: datetime, reason: str
    ) -> SessionRecord | None: ...
