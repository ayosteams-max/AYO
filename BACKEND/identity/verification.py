from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

import jwt
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from cryptography.hazmat.primitives.asymmetric.ed448 import Ed448PublicKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from fastapi import Request
from jwt import InvalidTokenError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import AccountStatus, AssuranceLevel, IdentityType
from BACKEND.observability import MetricsSink, NullMetricsSink
from BACKEND.persistence.composition import PostgresRepositoryComposition


class AuthenticationFailed(ValueError):
    """Safe internal category; never includes token or claim content."""


class VerifiedTokenIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    token_id: UUID
    identity_id: UUID
    session_id: UUID
    identity_type: IdentityType
    assurance_level: AssuranceLevel
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    issuer: str = Field(min_length=1, max_length=255)
    audience: str = Field(min_length=1, max_length=255)
    key_id: str = Field(min_length=1, max_length=128)

    @field_validator("issued_at", "not_before", "expires_at")
    @classmethod
    def aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Token timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def bounded_lifetime(self) -> "VerifiedTokenIdentity":
        if self.expires_at <= self.issued_at:
            raise ValueError("Token expiry must follow issue time")
        if self.expires_at - self.issued_at > timedelta(minutes=15):
            raise ValueError("Token lifetime exceeds policy")
        return self


class TokenVerifier(Protocol):
    def verify(
        self, token: str, *, now: datetime | None = None
    ) -> VerifiedTokenIdentity: ...


type VerificationKey = (
    RSAPublicKey
    | EllipticCurvePublicKey
    | Ed25519PublicKey
    | Ed448PublicKey
    | jwt.PyJWK
    | str
    | bytes
)


class VerificationKeyProvider(Protocol):
    def resolve(self, *, key_id: str, algorithm: str) -> VerificationKey | None: ...


class AuthenticationAuditWriter(Protocol):
    def append(self, event: AuditEvent) -> AuditEvent: ...


class RotatingStaticKeyProvider:
    """Controlled local/staging key ring; values contain public keys only."""

    def __init__(self, keys: Mapping[tuple[str, str], VerificationKey]) -> None:
        if not keys:
            raise ValueError("At least one verification key is required")
        self._keys = dict(keys)

    def resolve(self, *, key_id: str, algorithm: str) -> VerificationKey | None:
        return self._keys.get((key_id, algorithm))


class AsymmetricJwtVerifier:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        key_provider: VerificationKeyProvider,
        algorithms: tuple[str, ...] = ("RS256", "ES256", "EdDSA"),
        clock_skew_seconds: int = 30,
    ) -> None:
        if not issuer or not audience:
            raise ValueError("Issuer and audience are required")
        if not algorithms or any(
            item.startswith("HS") or item == "none" for item in algorithms
        ):
            raise ValueError("Only configured asymmetric algorithms are allowed")
        if not 0 <= clock_skew_seconds <= 120:
            raise ValueError("Clock skew must be between 0 and 120 seconds")
        self._issuer = issuer
        self._audience = audience
        self._keys = key_provider
        self._algorithms = algorithms
        self._leeway = clock_skew_seconds

    def verify(
        self, token: str, *, now: datetime | None = None
    ) -> VerifiedTokenIdentity:
        if not 16 <= len(token) <= 8192:
            raise AuthenticationFailed("malformed_token")
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            key_id = header.get("kid")
            token_type = header.get("typ")
            if (
                not isinstance(algorithm, str)
                or algorithm not in self._algorithms
                or not isinstance(key_id, str)
                or not 1 <= len(key_id) <= 128
                or token_type not in {"JWT", "at+jwt"}
            ):
                raise AuthenticationFailed("untrusted_header")
            key = self._keys.resolve(key_id=key_id, algorithm=algorithm)
            if key is None:
                raise AuthenticationFailed("unknown_key")
            payload = jwt.decode(
                token,
                key=key,
                algorithms=[algorithm],
                issuer=self._issuer,
                audience=self._audience,
                leeway=self._leeway,
                options={
                    "require": [
                        "iss",
                        "aud",
                        "exp",
                        "nbf",
                        "iat",
                        "sub",
                        "sid",
                        "jti",
                        "identity_type",
                        "assurance_level",
                    ]
                },
            )
            if {"role", "roles", "permissions", "scope"} & payload.keys():
                raise AuthenticationFailed("authorization_claim_prohibited")
            verified = VerifiedTokenIdentity(
                token_id=UUID(str(payload["jti"])),
                identity_id=UUID(str(payload["sub"])),
                session_id=UUID(str(payload["sid"])),
                identity_type=IdentityType(payload["identity_type"]),
                assurance_level=AssuranceLevel(payload["assurance_level"]),
                issued_at=datetime.fromtimestamp(payload["iat"], UTC),
                not_before=datetime.fromtimestamp(payload["nbf"], UTC),
                expires_at=datetime.fromtimestamp(payload["exp"], UTC),
                issuer=self._issuer,
                audience=self._audience,
                key_id=key_id,
            )
            if (
                verified.not_before > verified.expires_at
                or instant >= verified.expires_at + timedelta(seconds=self._leeway)
            ):
                raise AuthenticationFailed("token_time_invalid")
            return verified
        except AuthenticationFailed:
            raise
        except (InvalidTokenError, KeyError, TypeError, ValueError) as error:
            raise AuthenticationFailed("token_verification_failed") from error


_ACTOR_BY_IDENTITY = {
    IdentityType.RIDER: ActorType.RIDER,
    IdentityType.DRIVER: ActorType.DRIVER,
    IdentityType.STAFF: ActorType.STAFF,
    IdentityType.ADMINISTRATOR: ActorType.ADMINISTRATOR,
    IdentityType.SERVICE: ActorType.SERVICE,
}


class VerifiedSubjectResolver:
    def __init__(
        self,
        verifier: TokenVerifier,
        composition: PostgresRepositoryComposition,
        *,
        metrics: MetricsSink | None = None,
        audit_writer: AuthenticationAuditWriter | None = None,
    ) -> None:
        self._verifier = verifier
        self._composition = composition
        self._metrics = metrics or NullMetricsSink()
        self._audit_writer = audit_writer

    async def resolve(self, request: Request) -> AuthorizationSubject | None:
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer ") or len(authorization) > 8200:
            self._record_failure(request, "missing_or_malformed")
            return None
        try:
            verified = self._verifier.verify(authorization[7:])
            actor = _ACTOR_BY_IDENTITY.get(verified.identity_type)
            if actor is None:
                raise AuthenticationFailed("identity_type_not_allowed")
            now = datetime.now(UTC)
            with self._composition.unit_of_work() as unit:
                identity = unit.identities.get(verified.identity_id)
                session = unit.sessions.get(verified.session_id)
            if (
                identity is None
                or identity.status is not AccountStatus.ACTIVE
                or identity.identity_type is not verified.identity_type
                or session is None
                or session.identity_id != verified.identity_id
                or not session.is_active_at(now)
            ):
                raise AuthenticationFailed("subject_state_invalid")
            return AuthorizationSubject(
                identity_id=verified.identity_id,
                identity_type=verified.identity_type,
                actor_type=actor,
                session_id=verified.session_id,
                assurance_level=verified.assurance_level,
            )
        except AuthenticationFailed as error:
            self._record_failure(request, str(error))
            return None

    def _record_failure(self, request: Request, reason: str) -> None:
        self._metrics.increment("authentication_failures", labels={"reason": reason})
        if self._audit_writer is not None:
            self._audit_writer.append(
                AuditEvent(
                    actor_type=ActorType.ANONYMOUS,
                    action="authentication.access.denied",
                    resource_type="dispatch_api",
                    outcome=AuditOutcome.DENIED,
                    reason=reason,
                    correlation_id=request.state.authorization_correlation_id,
                    source_module="identity",
                    safe_metadata={"operation": "token_verification"},
                )
            )
