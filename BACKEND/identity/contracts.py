from typing import Protocol

from BACKEND.identity.models import AccessTokenClaims, AuthenticationMethodType


class AccessTokenCodec(Protocol):
    """Production implementation requires approved rotating key management."""

    def encode(self, claims: AccessTokenClaims) -> str: ...

    def decode_and_verify(self, token: str) -> AccessTokenClaims: ...


class AuthenticationMethodProvider(Protocol):
    method_type: AuthenticationMethodType

    def begin(self, destination_reference: bytes) -> str: ...

    def verify(self, challenge_reference: str, response: str) -> bool: ...


class CompromisedPasswordChecker(Protocol):
    def is_compromised(self, password: str) -> bool: ...


class PasskeyProvider(Protocol):
    def registration_options(self, identity_reference: str) -> dict[str, object]: ...

    def verify_assertion(self, assertion: bytes) -> str: ...


class IdentityProviderAdapter(Protocol):
    def verify_provider_assertion(self, assertion: str) -> str: ...
