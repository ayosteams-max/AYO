import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from BACKEND.identity.authentication import HmacChallengeProtector
from BACKEND.identity.runtime import (
    AuthenticationDenied,
    AuthenticationRuntime,
    RegistrationConflict,
)
from BACKEND.identity.runtime_models import (
    ContactKind,
    RegistrationRequest,
    SignInRequest,
)
from BACKEND.identity.runtime_tokens import AsymmetricJwtIssuer

pytestmark = [pytest.mark.integration, pytest.mark.authentication]


class Delivery:
    code: str | None = None

    def deliver(self, *, kind, destination, code, expires_at):
        assert destination == "rider@example.com"
        assert expires_at
        self.code = code


def runtime(postgres_composition, delivery=None) -> AuthenticationRuntime:
    return AuthenticationRuntime(
        postgres_composition,
        token_issuer=AsymmetricJwtIssuer(
            issuer="ayo-test",
            audience="ayo-api-test",
            key_id="test-ed25519-1",
            private_key=Ed25519PrivateKey.generate(),
        ),
        identifier_pepper=b"test-only-identifier-pepper-material-32-bytes",
        challenge_protector=HmacChallengeProtector(
            b"test-challenge-protection-key-material-32"
        ),
        verification_delivery=delivery,
    )


def registration() -> RegistrationRequest:
    from uuid import uuid4

    return RegistrationRequest(
        contact_kind=ContactKind.EMAIL,
        contact="rider@example.com",
        password="correct horse battery staple",
        device_id=uuid4(),
        operating_system_family="android",
        application_version="1.0.0",
    )


def test_registration_sign_in_rotation_replay_and_global_logout(postgres_composition):
    auth = runtime(postgres_composition)
    created = auth.register(registration())
    assert created.access_token
    assert created.refresh_token
    with pytest.raises(RegistrationConflict):
        auth.register(registration())

    request = SignInRequest(**registration().model_dump())
    signed_in = auth.sign_in(request)
    rotated = auth.refresh(signed_in.refresh_token)
    assert rotated.refresh_token != signed_in.refresh_token
    with pytest.raises(AuthenticationDenied):
        auth.refresh(signed_in.refresh_token)

    second = auth.sign_in(request)
    revoked = auth.sign_out_all(
        identity_id=second.identity_id, session_id=second.session_id
    )
    assert revoked >= 1
    with pytest.raises(AuthenticationDenied):
        auth.refresh(second.refresh_token)


def test_contact_activation_is_single_use_and_identity_bound(postgres_composition):
    delivery = Delivery()
    auth = runtime(postgres_composition, delivery)
    session = auth.register(registration())
    assert auth.activation_progress(session.identity_id).activated is False
    prepared = auth.prepare_verification(
        identity_id=session.identity_id,
        kind=ContactKind.EMAIL,
        contact="rider@example.com",
    )
    assert delivery.code is not None
    activated = auth.complete_verification(
        identity_id=session.identity_id,
        challenge_id=prepared.challenge_id,
        code=delivery.code,
    )
    assert activated.activated is True
    with pytest.raises(AuthenticationDenied):
        auth.complete_verification(
            identity_id=session.identity_id,
            challenge_id=prepared.challenge_id,
            code=delivery.code,
        )
