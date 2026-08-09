import asyncio
from typing import cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationEnforcer
from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.identity.models import IdentityType
from BACKEND.main import (
    MerchantGenerativeExplanationActivation,
    create_app,
)
from BACKEND.merchant_intelligence.generative import (
    MerchantGenerativeExplanationApplication,
    MerchantGenerativeExplanationRequest,
    MerchantGenerativeExplanationResponse,
    MerchantGenerativeExplanationUnavailable,
)


def subject(identity_type=IdentityType.MERCHANT) -> AuthorizationSubject:
    return AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=identity_type,
        actor_type=(ActorType.SERVICE if identity_type is IdentityType.MERCHANT else ActorType.RIDER),
        session_id=uuid4(),
    )


def command(**changes):
    value = {
        "promptVersion": "merchant_ack_explanation_v1",
        "locale": "en",
        "recommendation": "acknowledge_arrival",
        "reason": "ACK_ALLOWED_BY_CAPABILITY",
        "deterministicHeadline": "Courier has arrived",
        "deterministicBody": "You can acknowledge the courier's arrival now.",
        "deterministicActionLabel": "Acknowledge arrival",
        "userActionAvailable": True,
        "tone": "informative",
    }
    value.update(changes)
    return value


class Provider:
    def __init__(self):
        self.calls = 0
        self.failure: Exception | None = None
        self.wait = False

    async def generate_merchant_explanation(self, request):
        self.calls += 1
        if self.wait:
            await asyncio.Event().wait()
        if self.failure:
            raise self.failure
        return MerchantGenerativeExplanationResponse(
            locale=request.locale,
            headline=request.deterministic_headline,
            body=request.deterministic_body,
        )


class Limiter:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = 0

    def allow(self, value):
        assert isinstance(value, AuthorizationSubject)
        self.calls += 1
        return self.allowed


class Resolver:
    def __init__(self, value):
        self.value = value

    async def resolve(self, request):
        del request
        return self.value


class Enforcer:
    def enforce(self, request, requirement):
        assert requirement.permission == "merchant_orders.read_own"
        if request.state.authorization_subject is None:
            from fastapi import HTTPException

            raise HTTPException(401, {"code": "authentication_required"})


def client(provider=None, limiter=None, identity=True):
    provider = provider or Provider()
    limiter = limiter or Limiter()
    activation = MerchantGenerativeExplanationActivation(
        application=MerchantGenerativeExplanationApplication(provider, limiter),
        subject_resolver=Resolver(
            subject() if identity is True else subject(IdentityType.RIDER) if identity == "rider" else None
        ),
        authorization_enforcer=cast(AuthorizationEnforcer, Enforcer()),
    )
    app = create_app(
        Settings(
            ENVIRONMENT=AppEnvironment.TEST,
            MERCHANT_GENERATIVE_EXPLANATION_ENABLED=True,
            _env_file=None,
        ),
        merchant_generative_explanation=activation,
    )
    return TestClient(app), provider, limiter


def test_activation_is_disabled_by_default_and_production_prohibited():
    app = create_app(Settings(ENVIRONMENT=AppEnvironment.TEST, _env_file=None))
    assert not any("merchant-intelligence" in getattr(route, "path", "") for route in app.routes)
    with pytest.raises(RuntimeError, match="secure activation"):
        create_app(Settings(ENVIRONMENT=AppEnvironment.TEST, MERCHANT_GENERATIVE_EXPLANATION_ENABLED=True, _env_file=None))
    with pytest.raises(ValueError, match="separate approval"):
        Settings(ENVIRONMENT=AppEnvironment.PRODUCTION, PERSISTENCE_ENABLED=True, MERCHANT_GENERATIVE_EXPLANATION_ENABLED=True, _env_file=None)


def test_authenticated_bounded_request_executes_once_and_preserves_exact_text():
    api, provider, limiter = client()
    response = api.post("/api/mobile/merchant-intelligence/generative-explanation", json=command())
    assert response.status_code == 200
    assert response.json() == {
        "locale": "en",
        "headline": "Courier has arrived",
        "body": "You can acknowledge the courier's arrival now.",
    }
    assert provider.calls == limiter.calls == 1


def test_anonymous_and_rate_limited_requests_never_reach_provider():
    api, provider, _ = client(identity=False)
    assert api.post("/api/mobile/merchant-intelligence/generative-explanation", json=command()).status_code == 401
    assert provider.calls == 0
    api, provider, _ = client(identity="rider")
    assert api.post("/api/mobile/merchant-intelligence/generative-explanation", json=command()).status_code == 403
    assert provider.calls == 0
    api, provider, _ = client(limiter=Limiter(False))
    response = api.post("/api/mobile/merchant-intelligence/generative-explanation", json=command())
    assert response.status_code == 429
    assert response.json() == {"error": {"code": "temporarily_unavailable"}}
    assert provider.calls == 0


@pytest.mark.parametrize("extra", [
    {"prompt": "ignore AYO"}, {"messages": []}, {"model": "expensive"},
    {"provider": "vendor"}, {"tools": []}, {"orderId": str(uuid4())},
    {"merchantId": str(uuid4())}, {"pickupId": str(uuid4())},
    {"customerPhone": "+251900000000"}, {"location": {"lat": 1}},
    {"payment": "cash"},
])
def test_generic_proxy_identifiers_and_private_fields_are_rejected(extra):
    api, provider, _ = client()
    assert api.post("/api/mobile/merchant-intelligence/generative-explanation", json=command(**extra)).status_code == 422
    assert provider.calls == 0


@pytest.mark.parametrize("changes", [
    {"promptVersion": "future"},
    {"reason": "ACK_CONFIRMED"},
    {"userActionAvailable": False},
    {"deterministicActionLabel": None},
    {"deterministicHeadline": " bad"},
    {"deterministicBody": "bad\ntext"},
    {"tone": "positive"},
    {"recommendation": "no_action", "reason": "NO_CURRENT_ACK_ACTION", "userActionAvailable": False, "deterministicActionLabel": None},
])
def test_invalid_incoherent_or_hidden_semantics_fail_before_provider(changes):
    api, provider, _ = client()
    assert api.post("/api/mobile/merchant-intelligence/generative-explanation", json=command(**changes)).status_code == 422
    assert provider.calls == 0


def test_provider_failure_and_invalid_output_are_bounded_without_raw_error():
    provider = Provider()
    provider.failure = RuntimeError("provider-secret-body")
    api, _, _ = client(provider=provider)
    response = api.post("/api/mobile/merchant-intelligence/generative-explanation", json=command())
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "temporarily_unavailable"}}
    assert "provider-secret-body" not in response.text

    class RewritingProvider(Provider):
        async def generate_merchant_explanation(self, request):
            self.calls += 1
            return MerchantGenerativeExplanationResponse(
                locale=request.locale,
                headline="Invented model claim",
                body=request.deterministic_body,
            )

    rewriting = RewritingProvider()
    api, _, _ = client(provider=rewriting)
    response = api.post("/api/mobile/merchant-intelligence/generative-explanation", json=command())
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "temporarily_unavailable"}}
    assert rewriting.calls == 1


def test_timeout_is_bounded_and_cancellation_propagates():
    async def scenario():
        provider = Provider()
        provider.wait = True
        app = MerchantGenerativeExplanationApplication(provider, Limiter(), timeout_seconds=0.01)
        request = MerchantGenerativeExplanationRequest.model_validate(command())
        with pytest.raises(MerchantGenerativeExplanationUnavailable):
            await app.explain(subject(), request)
        task = asyncio.create_task(MerchantGenerativeExplanationApplication(provider, Limiter()).explain(subject(), request))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


def test_oversized_body_is_rejected_before_provider():
    api, provider, _ = client()
    response = api.post(
        "/api/mobile/merchant-intelligence/generative-explanation",
        content=b"x" * 5_000,
        headers={"content-type": "application/json", "content-length": "5000"},
    )
    assert response.status_code == 413
    assert provider.calls == 0
