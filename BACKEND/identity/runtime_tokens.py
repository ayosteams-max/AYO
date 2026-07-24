from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt

from BACKEND.identity.models import AssuranceLevel, IdentityType


class AsymmetricJwtIssuer:
    """Issues short-lived access tokens with externally managed private key material."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        key_id: str,
        private_key: Any,
        algorithm: str = "EdDSA",
        lifetime: timedelta = timedelta(minutes=10),
    ) -> None:
        if not issuer or not audience or not key_id:
            raise ValueError("Token issuer configuration is incomplete")
        if algorithm not in {"RS256", "ES256", "EdDSA"}:
            raise ValueError("Only approved asymmetric token algorithms are allowed")
        if not timedelta(minutes=1) <= lifetime <= timedelta(minutes=15):
            raise ValueError("Access-token lifetime must be between 1 and 15 minutes")
        self._issuer = issuer
        self._audience = audience
        self._key_id = key_id
        self._private_key = private_key
        self._algorithm = algorithm
        self._lifetime = lifetime

    @property
    def lifetime(self) -> timedelta:
        return self._lifetime

    def issue(
        self,
        *,
        identity_id: UUID,
        session_id: UUID,
        identity_type: IdentityType,
        assurance_level: AssuranceLevel,
        now: datetime,
    ) -> tuple[str, datetime]:
        instant = now.astimezone(UTC)
        expires_at = instant + self._lifetime
        token = jwt.encode(
            {
                "iss": self._issuer,
                "aud": self._audience,
                "sub": str(identity_id),
                "sid": str(session_id),
                "jti": str(uuid4()),
                "identity_type": identity_type.value,
                "assurance_level": assurance_level.value,
                "iat": int(instant.timestamp()),
                "nbf": int(instant.timestamp()),
                "exp": int(expires_at.timestamp()),
            },
            key=self._private_key,
            algorithm=self._algorithm,
            headers={"kid": self._key_id, "typ": "at+jwt"},
        )
        return token, expires_at
