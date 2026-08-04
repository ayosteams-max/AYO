import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.exc import IntegrityError

from BACKEND.persistence.errors import SessionPersistenceConflict
from BACKEND.persistence.tables import sessions
from BACKEND.session.models import SessionRecord


def _row_to_session(row: Mapping[Any, Any]) -> SessionRecord:
    return SessionRecord.model_validate(dict(row))


class PostgresSessionRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create(self, session: SessionRecord) -> SessionRecord:
        try:
            row = (
                self._connection.execute(
                    insert(sessions)
                    .values(**session.model_dump(mode="python"))
                    .returning(sessions)
                )
                .mappings()
                .one()
            )
        except IntegrityError as error:
            raise SessionPersistenceConflict(
                "Session identifier or token fingerprint already exists"
            ) from error
        return _row_to_session(row)

    def get(self, session_id: UUID) -> SessionRecord | None:
        row = (
            self._connection.execute(
                select(sessions).where(sessions.c.session_id == session_id)
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _row_to_session(row)

    def find_active_by_token_hash(
        self, token_hash: bytes, *, at: datetime
    ) -> SessionRecord | None:
        if len(token_hash) != 32:
            raise ValueError("Session token fingerprint must be 32 bytes")
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("Session check time must be timezone-aware")
        row = (
            self._connection.execute(
                select(sessions).where(
                    sessions.c.token_hash == token_hash,
                    sessions.c.revoked_at.is_(None),
                    sessions.c.expires_at > at,
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _row_to_session(row)

    def revoke(
        self, session_id: UUID, *, revoked_at: datetime, reason: str
    ) -> SessionRecord | None:
        if revoked_at.tzinfo is None or revoked_at.utcoffset() is None:
            raise ValueError("Session revocation time must be timezone-aware")
        if re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", reason) is None:
            raise ValueError("Session revocation reason must be a safe category")
        row = (
            self._connection.execute(
                update(sessions)
                .where(
                    sessions.c.session_id == session_id,
                    sessions.c.revoked_at.is_(None),
                )
                .values(
                    revoked_at=revoked_at,
                    revocation_reason=reason,
                    version=sessions.c.version + 1,
                )
                .returning(sessions)
            )
            .mappings()
            .one_or_none()
        )
        if row is not None:
            return _row_to_session(row)
        existing = self.get(session_id)
        if existing is not None and existing.revocation_reason != reason:
            raise SessionPersistenceConflict(
                "Session was already revoked for a different reason"
            )
        return existing

    def revoke_all_for_identity(
        self, identity_id: UUID, *, revoked_at: datetime, reason: str
    ) -> int:
        if re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", reason) is None:
            raise ValueError("Session revocation reason must be a safe category")
        result = self._connection.execute(
            update(sessions)
            .where(
                sessions.c.identity_id == identity_id,
                sessions.c.revoked_at.is_(None),
            )
            .values(
                revoked_at=revoked_at,
                revocation_reason=reason,
                version=sessions.c.version + 1,
            )
        )
        return result.rowcount
