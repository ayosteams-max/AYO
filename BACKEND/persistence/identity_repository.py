from collections.abc import Mapping
from datetime import UTC, datetime
from hmac import compare_digest
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.exc import IntegrityError

from BACKEND.identity.authentication import AuthenticationChallenge
from BACKEND.identity.models import Identity
from BACKEND.identity.runtime_models import (
    ContactKind,
    PasswordCredentialRecord,
)
from BACKEND.identity.tokens import (
    RefreshRotationOutcome,
    RefreshRotationResult,
)
from BACKEND.persistence.tables import (
    authentication_challenges,
    credential_verifiers,
    identities,
    identity_authentication_methods,
    refresh_token_rotations,
    sessions,
    token_families,
)


class DuplicateAuthenticationIdentifier(RuntimeError):
    pass


def _row_to_identity(row: Mapping[Any, Any]) -> Identity:
    return Identity.model_validate(dict(row))


def _row_to_challenge(row: Mapping[Any, Any]) -> AuthenticationChallenge:
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


class PostgresPasswordCredentialRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create(
        self,
        *,
        identity_id: UUID,
        lookup_reference: bytes,
        verifier: str,
        scheme: str,
        contact_kind: ContactKind,
        created_at: datetime,
    ) -> None:
        if len(lookup_reference) != 32:
            raise ValueError("Authentication lookup reference must be 32 bytes")
        password_method_id = uuid4()
        verification_method_id = uuid4()
        verification_type = (
            "email_verification" if contact_kind is ContactKind.EMAIL else "phone_otp"
        )
        try:
            self._connection.execute(
                insert(identity_authentication_methods),
                [
                    {
                        "method_id": password_method_id,
                        "identity_id": identity_id,
                        "method_type": "password",
                        "status": "active",
                        "lookup_reference": lookup_reference,
                        "assurance_level": "basic",
                        "verified_at": created_at,
                        "created_at": created_at,
                    },
                    {
                        "method_id": verification_method_id,
                        "identity_id": identity_id,
                        "method_type": verification_type,
                        "status": "pending",
                        "lookup_reference": lookup_reference,
                        "assurance_level": "basic",
                        "verified_at": None,
                        "created_at": created_at,
                    },
                ],
            )
            self._connection.execute(
                insert(credential_verifiers).values(
                    credential_id=uuid4(),
                    method_id=password_method_id,
                    scheme=scheme,
                    verifier=verifier,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
        except IntegrityError as error:
            raise DuplicateAuthenticationIdentifier(
                "Authentication identifier is already registered"
            ) from error

    def find_by_lookup_reference(
        self, lookup_reference: bytes
    ) -> PasswordCredentialRecord | None:
        if len(lookup_reference) != 32:
            raise ValueError("Authentication lookup reference must be 32 bytes")
        row = (
            self._connection.execute(
                select(
                    identities.c.identity_id,
                    identities.c.identity_type,
                    identities.c.status.label("account_status"),
                    credential_verifiers.c.verifier,
                    credential_verifiers.c.scheme,
                )
                .select_from(
                    identity_authentication_methods.join(
                        identities,
                        identities.c.identity_id
                        == identity_authentication_methods.c.identity_id,
                    ).join(
                        credential_verifiers,
                        credential_verifiers.c.method_id
                        == identity_authentication_methods.c.method_id,
                    )
                )
                .where(
                    identity_authentication_methods.c.method_type == "password",
                    identity_authentication_methods.c.status == "active",
                    identity_authentication_methods.c.lookup_reference
                    == lookup_reference,
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else PasswordCredentialRecord.model_validate(row)

    def update_verifier(
        self,
        *,
        lookup_reference: bytes,
        verifier: str,
        scheme: str,
        updated_at: datetime,
    ) -> None:
        method_id = self._connection.execute(
            select(identity_authentication_methods.c.method_id).where(
                identity_authentication_methods.c.method_type == "password",
                identity_authentication_methods.c.lookup_reference == lookup_reference,
            )
        ).scalar_one()
        self._connection.execute(
            update(credential_verifiers)
            .where(credential_verifiers.c.method_id == method_id)
            .values(verifier=verifier, scheme=scheme, updated_at=updated_at)
        )

    def pending_verification_method(
        self,
        *,
        identity_id: UUID,
        method_type: str,
        lookup_reference: bytes,
    ) -> UUID | None:
        return self._connection.execute(
            select(identity_authentication_methods.c.method_id).where(
                identity_authentication_methods.c.identity_id == identity_id,
                identity_authentication_methods.c.method_type == method_type,
                identity_authentication_methods.c.lookup_reference == lookup_reference,
                identity_authentication_methods.c.status == "pending",
            )
        ).scalar_one_or_none()

    def mark_verification_method_verified(
        self, method_id: UUID, *, identity_id: UUID, verified_at: datetime
    ) -> UUID | None:
        return self._connection.execute(
            update(identity_authentication_methods)
            .where(
                identity_authentication_methods.c.method_id == method_id,
                identity_authentication_methods.c.identity_id == identity_id,
                identity_authentication_methods.c.status == "pending",
            )
            .values(status="verified", verified_at=verified_at)
            .returning(identity_authentication_methods.c.identity_id)
        ).scalar_one_or_none()

    def verification_method_belongs_to_identity(
        self, method_id: UUID, *, identity_id: UUID
    ) -> bool:
        return (
            self._connection.execute(
                select(identity_authentication_methods.c.method_id).where(
                    identity_authentication_methods.c.method_id == method_id,
                    identity_authentication_methods.c.identity_id == identity_id,
                )
            ).scalar_one_or_none()
            is not None
        )

    def activation_progress(self, identity_id: UUID) -> dict[str, str | None]:
        rows = self._connection.execute(
            select(
                identity_authentication_methods.c.method_type,
                identity_authentication_methods.c.status,
            ).where(
                identity_authentication_methods.c.identity_id == identity_id,
                identity_authentication_methods.c.method_type.in_(
                    ["email_verification", "phone_otp"]
                ),
            )
        ).all()
        statuses = {row.method_type: row.status for row in rows}
        return {
            "email_status": statuses.get("email_verification"),
            "phone_status": statuses.get("phone_otp"),
        }


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

    def get(self, challenge_id: UUID) -> AuthenticationChallenge | None:
        row = (
            self._connection.execute(
                select(authentication_challenges).where(
                    authentication_challenges.c.challenge_id == challenge_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _row_to_challenge(row)

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

    def revoke_for_session(self, session_id: UUID, *, at: datetime) -> int:
        result = self._connection.execute(
            update(token_families)
            .where(
                token_families.c.session_id == session_id,
                token_families.c.status == "active",
            )
            .values(status="revoked", revoked_at=at)
        )
        return result.rowcount

    def revoke_all_for_identity(self, identity_id: UUID, *, at: datetime) -> int:
        result = self._connection.execute(
            update(token_families)
            .where(
                token_families.c.identity_id == identity_id,
                token_families.c.status == "active",
            )
            .values(status="revoked", revoked_at=at)
        )
        return result.rowcount

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
