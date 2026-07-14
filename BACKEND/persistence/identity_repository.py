from collections.abc import Mapping
from datetime import UTC, datetime
from hmac import compare_digest
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update

from BACKEND.identity.authentication import AuthenticationChallenge
from BACKEND.identity.models import Identity
from BACKEND.identity.tokens import (
    RefreshRotationOutcome,
    RefreshRotationResult,
)
from BACKEND.persistence.tables import (
    authentication_challenges,
    identities,
    refresh_token_rotations,
    sessions,
    token_families,
)


def _row_to_identity(row: Mapping[str, Any]) -> Identity:
    return Identity.model_validate(dict(row))


def _row_to_challenge(row: Mapping[str, Any]) -> AuthenticationChallenge:
    return AuthenticationChallenge.model_validate(dict(row))


class PostgresIdentityRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create(self, identity: Identity) -> Identity:
        row = (
            self._connection.execute(
                insert(identities).values(**identity.model_dump()).returning(identities)
            )
            .mappings()
            .one()
        )
        return _row_to_identity(row)

    def get(self, identity_id: UUID) -> Identity | None:
        row = (
            self._connection.execute(
                select(identities).where(identities.c.identity_id == identity_id)
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _row_to_identity(row)

    def save(self, identity: Identity, *, expected_version: int) -> Identity:
        row = (
            self._connection.execute(
                update(identities)
                .where(
                    identities.c.identity_id == identity.identity_id,
                    identities.c.version == expected_version,
                )
                .values(
                    status=identity.status.value,
                    updated_at=identity.updated_at,
                    version=identities.c.version + 1,
                )
                .returning(identities)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise RuntimeError("Identity changed during the transaction")
        return _row_to_identity(row)


class PostgresAuthenticationChallengeRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create(self, challenge: AuthenticationChallenge) -> AuthenticationChallenge:
        row = (
            self._connection.execute(
                insert(authentication_challenges)
                .values(**challenge.model_dump())
                .returning(authentication_challenges)
            )
            .mappings()
            .one()
        )
        return _row_to_challenge(row)

    def verify(self, challenge_id: UUID, *, verifier: bytes, at: datetime) -> bool:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("Challenge verification time must be timezone-aware")
        at = at.astimezone(UTC)
        row = (
            self._connection.execute(
                select(authentication_challenges)
                .where(authentication_challenges.c.challenge_id == challenge_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return False
        challenge = _row_to_challenge(row)
        if (
            challenge.consumed_at is not None
            or at >= challenge.expires_at
            or challenge.attempt_count >= challenge.max_attempts
        ):
            return False
        matched = compare_digest(verifier, challenge.verifier)
        self._connection.execute(
            update(authentication_challenges)
            .where(authentication_challenges.c.challenge_id == challenge_id)
            .values(
                attempt_count=authentication_challenges.c.attempt_count + 1,
                consumed_at=at if matched else None,
            )
        )
        return matched


class PostgresRefreshTokenRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create_family(
        self,
        *,
        family_id: UUID,
        identity_id: UUID,
        session_id: UUID,
        token_hash: bytes,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        if created_at.tzinfo is None or expires_at.tzinfo is None:
            raise ValueError("Token-family timestamps must be timezone-aware")
        if expires_at <= created_at:
            raise ValueError("Token-family expiry must follow creation")
        self._connection.execute(
            insert(token_families).values(
                family_id=family_id,
                identity_id=identity_id,
                session_id=session_id,
                current_token_hash=token_hash,
                rotation_counter=0,
                status="active",
                created_at=created_at,
                expires_at=expires_at,
            )
        )

    def rotate(
        self,
        *,
        family_id: UUID,
        presented_hash: bytes,
        replacement_hash: bytes,
        at: datetime,
    ) -> RefreshRotationResult:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("Refresh rotation time must be timezone-aware")
        at = at.astimezone(UTC)
        if len(presented_hash) != 32 or len(replacement_hash) != 32:
            raise ValueError("Refresh-token fingerprints must be 32 bytes")
        family = (
            self._connection.execute(
                select(token_families)
                .where(token_families.c.family_id == family_id)
                .with_for_update()
            )
            .mappings()
            .one()
        )
        counter = family["rotation_counter"]
        if family["status"] != "active" or at >= family["expires_at"]:
            return RefreshRotationResult(
                outcome=RefreshRotationOutcome.DENIED,
                family_id=family_id,
                session_id=family["session_id"],
                rotation_counter=counter,
            )
        if compare_digest(presented_hash, family["current_token_hash"]):
            self._connection.execute(
                insert(refresh_token_rotations).values(
                    rotation_id=uuid4(),
                    family_id=family_id,
                    token_hash=presented_hash,
                    rotation_counter=counter,
                    consumed_at=at,
                )
            )
            counter += 1
            self._connection.execute(
                update(token_families)
                .where(token_families.c.family_id == family_id)
                .values(current_token_hash=replacement_hash, rotation_counter=counter)
            )
            self._connection.execute(
                update(sessions)
                .where(sessions.c.session_id == family["session_id"])
                .values(
                    token_hash=replacement_hash,
                    refresh_rotation_counter=counter,
                    version=sessions.c.version + 1,
                )
            )
            outcome = RefreshRotationOutcome.ROTATED
        else:
            replay = self._connection.execute(
                select(refresh_token_rotations.c.rotation_id).where(
                    refresh_token_rotations.c.family_id == family_id,
                    refresh_token_rotations.c.token_hash == presented_hash,
                )
            ).scalar_one_or_none()
            outcome = (
                RefreshRotationOutcome.REPLAY_DETECTED
                if replay is not None
                else RefreshRotationOutcome.DENIED
            )
            if replay is not None:
                self._connection.execute(
                    update(token_families)
                    .where(token_families.c.family_id == family_id)
                    .values(
                        status="revoked",
                        revoked_at=at,
                        replay_detected_at=at,
                    )
                )
                self._connection.execute(
                    update(sessions)
                    .where(sessions.c.session_id == family["session_id"])
                    .values(
                        revoked_at=at,
                        revocation_reason="refresh_token_replay",
                        version=sessions.c.version + 1,
                    )
                )
        return RefreshRotationResult(
            outcome=outcome,
            family_id=family_id,
            session_id=family["session_id"],
            rotation_counter=counter,
        )
