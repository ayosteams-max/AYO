from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.identity.models import AssuranceLevel, IdentityType
from BACKEND.identity.runtime_models import (
    AuthenticationSessionResponse,
    ContactKind,
    IdentityActivationProgress,
    RegistrationRequest,
    VerificationPreparationResponse,
    normalize_contact,
)
from BACKEND.identity.runtime_tokens import AsymmetricJwtIssuer
from BACKEND.main import AuthenticationActivation, create_app


def response() -> AuthenticationSessionResponse:
    now = datetime.now(UTC)
    return AuthenticationSessionResponse(
        identity_id=uuid4(),
        session_id=uuid4(),
        identity_type=IdentityType.RIDER,
        access_token="opaque.access.token",
        access_expires_at=now + timedelta(minutes=10),
        refresh_token=f"{uuid4()}.{'r' * 64}",
        refresh_expires_at=now + timedelta(days=30),
    )


class FakeRuntime:
    def __init__(self) -> None:
        self.session = response()
        self.signed_out = False
        self.signed_out_all = False

    def register(self, payload):
        assert payload.password != ""
        return self.session

    def sign_in(self, payload):
        assert payload.contact
        return self.session

    def refresh(self, refresh_token):
        assert refresh_token
        return self.session

    def sign_out(self, *, identity_id, session_id):
        assert identity_id == self.session.identity_id
        assert session_id == self.session.session_id
        self.signed_out = True

    def sign_out_all(self, *, identity_id, session_id):
        assert identity_id == self.session.identity_id
        assert session_id == self.session.session_id
        self.signed_out_all = True
        return 2

    def prepare_recovery(self, kind, contact):
        assert kind is ContactKind.EMAIL
        assert contact == "rider@example.com"

    def activation_progress(self, identity_id):
        return IdentityActivationProgress(
            identity_id=identity_id, email_status="pending", activated=False
        )

    def prepare_verification(self, *, identity_id, kind, contact):
        assert identity_id == self.session.identity_id
        assert kind is ContactKind.EMAIL
        assert contact == "rider@example.com"
        return VerificationPreparationResponse(
            challenge_id=uuid4(), expires_at=datetime.now(UTC) + timedelta(minutes=10)
        )

    def complete_verification(self, *, identity_id, challenge_id, code):
        assert identity_id == self.session.identity_id
        assert challenge_id
        assert code == "123456"
        return IdentityActivationProgress(
            identity_id=identity_id, email_status="verified", activated=True
        )


class FakeResolver:
    def __init__(self, session: AuthenticationSessionResponse) -> None:
        self.session = session

    async def resolve(self, request):
        if request.headers.get("Authorization") != "Bearer access-token":
            return None
        return AuthorizationSubject(
            identity_id=self.session.identity_id,
            identity_type=IdentityType.RIDER,
            actor_type=ActorType.RIDER,
            session_id=self.session.session_id,
        )


def test_authentication_is_disabled_by_default_and_requires_secure_activation():
    app = create_app(Settings(ENVIRONMENT=AppEnvironment.TEST, _env_file=None))
    assert (
        "/api/auth/sign-in" not in TestClient(app).get("/openapi.json").json()["paths"]
    )
    with pytest.raises(RuntimeError, match="explicit secure activation"):
        create_app(
            Settings(
                ENVIRONMENT=AppEnvironment.TEST,
                AUTHENTICATION_ENABLED=True,
                _env_file=None,
            )
        )


def test_authentication_routes_and_server_authoritative_logout():
    runtime = FakeRuntime()
    app = create_app(
        Settings(
            ENVIRONMENT=AppEnvironment.TEST,
            AUTHENTICATION_ENABLED=True,
            _env_file=None,
        ),
        authentication=AuthenticationActivation(runtime, FakeResolver(runtime.session)),  # type: ignore[arg-type]
    )
    client = TestClient(app)
    device = {
        "device_id": str(uuid4()),
        "device_category": "mobile",
        "operating_system_family": "android",
        "application_version": "1.0.0",
    }
    credentials = {
        "contact_kind": "email",
        "contact": "rider@example.com",
        "password": "correct horse battery staple",
        **device,
    }
    assert client.post("/api/auth/register", json=credentials).status_code == 201
    assert client.post("/api/auth/sign-in", json=credentials).status_code == 200
    assert (
        client.post(
            "/api/auth/refresh",
            json={"refresh_token": runtime.session.refresh_token},
        ).status_code
        == 200
    )
    assert client.post("/api/auth/sign-out").status_code == 401
    assert (
        client.post(
            "/api/auth/sign-out", headers={"Authorization": "Bearer access-token"}
        ).status_code
        == 204
    )
    assert runtime.signed_out
    all_response = client.post(
        "/api/auth/sign-out-all",
        headers={"Authorization": "Bearer access-token"},
    )
    assert all_response.json() == {"revoked_sessions": 2}
    assert runtime.signed_out_all
    reset = client.post(
        "/api/auth/password-reset/prepare",
        json={"contact_kind": "email", "contact": "rider@example.com"},
    )
    assert reset.status_code == 202
    capabilities = client.get("/api/auth/capabilities").json()
    assert capabilities["password_reset"] == "preparation_only"
    assert capabilities["mfa"]["activation"] == "future_compatible_not_active"
    headers = {"Authorization": "Bearer access-token"}
    assert (
        client.get("/api/auth/activation", headers=headers).json()["activated"] is False
    )
    prepared = client.post(
        "/api/auth/verification/prepare",
        headers=headers,
        json={"contact_kind": "email", "contact": "rider@example.com"},
    )
    assert prepared.status_code == 200
    completed = client.post(
        "/api/auth/verification/complete",
        headers=headers,
        json={"challenge_id": prepared.json()["challenge_id"], "code": "123456"},
    )
    assert completed.json()["activated"] is True


def test_contact_normalization_and_registration_validation_are_bounded():
    assert normalize_contact(ContactKind.EMAIL, " Rider@Example.COM ") == (
        "rider@example.com"
    )
    assert normalize_contact(ContactKind.PHONE, "+251911223344") == "+251911223344"
    with pytest.raises(ValueError):
        normalize_contact(ContactKind.PHONE, "0911223344")
    with pytest.raises(ValueError):
        RegistrationRequest(
            contact_kind="email",
            contact="rider@example.com",
            password="short",
            device_id=uuid4(),
            operating_system_family="android",
            application_version="1.0.0",
        )


def test_access_token_issuer_is_asymmetric_short_lived_and_authority_minimized():
    private_key = Ed25519PrivateKey.generate()
    issuer = AsymmetricJwtIssuer(
        issuer="ayo",
        audience="ayo-api",
        key_id="test-ed25519-1",
        private_key=private_key,
    )
    now = datetime.now(UTC)
    token, expires_at = issuer.issue(
        identity_id=uuid4(),
        session_id=uuid4(),
        identity_type=IdentityType.RIDER,
        assurance_level=AssuranceLevel.BASIC,
        now=now,
    )
    claims = jwt.decode(
        token,
        key=private_key.public_key(),
        algorithms=["EdDSA"],
        audience="ayo-api",
        issuer="ayo",
    )
    assert expires_at - now <= timedelta(minutes=10, seconds=1)
    assert not {"role", "roles", "permissions", "scope"} & claims.keys()
    assert jwt.get_unverified_header(token)["typ"] == "at+jwt"
