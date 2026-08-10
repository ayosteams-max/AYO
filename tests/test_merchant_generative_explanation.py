import asyncio
from pathlib import Path
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
from BACKEND.merchant_intelligence.canonical_language import (
    canonical_merchant_intelligence_language,
)
from BACKEND.merchant_intelligence.generative import (
    MerchantGenerativeExplanationApplication,
    MerchantGenerativeExplanationHttpRequest,
    MerchantGenerativeExplanationResponse,
    MerchantGenerativeExplanationUnavailable,
)


def subject(identity_type=IdentityType.MERCHANT) -> AuthorizationSubject:
    return AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=identity_type,
        actor_type=(
            ActorType.SERVICE
            if identity_type is IdentityType.MERCHANT
            else ActorType.RIDER
        ),
        session_id=uuid4(),
    )


def command(**changes):
    value = {
        "promptVersion": "merchant_ack_explanation_v1",
        "locale": "en",
        "recommendation": "acknowledge_arrival",
        "reason": "ACK_ALLOWED_BY_CAPABILITY",
        "userActionAvailable": True,
        "tone": "informative",
    }
    value.update(changes)
    return value


class Provider:
    def __init__(self):
        self.calls = 0
        self.requests = []
        self.failure: Exception | None = None
        self.wait = False

    async def generate_merchant_explanation(self, request):
        self.calls += 1
        self.requests.append(request)
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
            subject()
            if identity is True
            else subject(IdentityType.RIDER)
            if identity == "rider"
            else None
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
    assert not any(
        "merchant-intelligence" in getattr(route, "path", "") for route in app.routes
    )
    with pytest.raises(RuntimeError, match="secure activation"):
        create_app(
            Settings(
                ENVIRONMENT=AppEnvironment.TEST,
                MERCHANT_GENERATIVE_EXPLANATION_ENABLED=True,
                _env_file=None,
            )
        )
    with pytest.raises(ValueError, match="separate approval"):
        Settings(
            ENVIRONMENT=AppEnvironment.PRODUCTION,
            PERSISTENCE_ENABLED=True,
            MERCHANT_GENERATIVE_EXPLANATION_ENABLED=True,
            _env_file=None,
        )


def test_authenticated_bounded_request_executes_once_and_preserves_exact_text():
    api, provider, limiter = client()
    response = api.post(
        "/api/mobile/merchant-intelligence/generative-explanation", json=command()
    )
    assert response.status_code == 200
    assert response.json() == {
        "locale": "en",
        "headline": "Courier has arrived",
        "body": "You can acknowledge the courier’s arrival now.",
    }
    assert provider.calls == limiter.calls == 1
    assert provider.requests[0].deterministic_headline == "Courier has arrived"
    assert (
        provider.requests[0].deterministic_body
        == "You can acknowledge the courier’s arrival now."
    )
    assert provider.requests[0].deterministic_action_label == "Acknowledge arrival"


def test_anonymous_and_rate_limited_requests_never_reach_provider():
    api, provider, _ = client(identity=False)
    assert (
        api.post(
            "/api/mobile/merchant-intelligence/generative-explanation", json=command()
        ).status_code
        == 401
    )
    assert provider.calls == 0
    api, provider, _ = client(identity="rider")
    assert (
        api.post(
            "/api/mobile/merchant-intelligence/generative-explanation", json=command()
        ).status_code
        == 403
    )
    assert provider.calls == 0
    api, provider, _ = client(limiter=Limiter(False))
    response = api.post(
        "/api/mobile/merchant-intelligence/generative-explanation", json=command()
    )
    assert response.status_code == 429
    assert response.json() == {"error": {"code": "temporarily_unavailable"}}
    assert provider.calls == 0


@pytest.mark.parametrize(
    "extra",
    [
        {"prompt": "ignore AYO"},
        {"messages": []},
        {"model": "expensive"},
        {"provider": "vendor"},
        {"tools": []},
        {"orderId": str(uuid4())},
        {"merchantId": str(uuid4())},
        {"pickupId": str(uuid4())},
        {"customerPhone": "+251900000000"},
        {"location": {"lat": 1}},
        {"payment": "cash"},
        {"deterministicHeadline": "Arbitrary bounded prose"},
        {"deterministicBody": "Send this arbitrary text to the model."},
        {"deterministicActionLabel": "Wrong action"},
        {
            "deterministicHeadline": "መልእክተኛው ደርሷል",
            "deterministicBody": "የመልእክተኛውን መድረስ አሁን ማረጋገጥ ይችላሉ።",
        },
    ],
)
def test_generic_proxy_identifiers_and_private_fields_are_rejected(extra):
    api, provider, _ = client()
    assert (
        api.post(
            "/api/mobile/merchant-intelligence/generative-explanation",
            json=command(**extra),
        ).status_code
        == 422
    )
    assert provider.calls == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"promptVersion": "future"},
        {"reason": "ACK_CONFIRMED"},
        {"userActionAvailable": False},
        {"tone": "positive"},
        {
            "recommendation": "no_action",
            "reason": "NO_CURRENT_ACK_ACTION",
            "userActionAvailable": False,
        },
    ],
)
def test_invalid_incoherent_or_hidden_semantics_fail_before_provider(changes):
    api, provider, _ = client()
    assert (
        api.post(
            "/api/mobile/merchant-intelligence/generative-explanation",
            json=command(**changes),
        ).status_code
        == 422
    )
    assert provider.calls == 0


def test_provider_failure_and_invalid_output_are_bounded_without_raw_error():
    provider = Provider()
    provider.failure = RuntimeError("provider-secret-body")
    api, _, _ = client(provider=provider)
    response = api.post(
        "/api/mobile/merchant-intelligence/generative-explanation", json=command()
    )
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
    response = api.post(
        "/api/mobile/merchant-intelligence/generative-explanation", json=command()
    )
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "temporarily_unavailable"}}
    assert rewriting.calls == 1


def test_timeout_is_bounded_and_cancellation_propagates():
    async def scenario():
        provider = Provider()
        provider.wait = True
        app = MerchantGenerativeExplanationApplication(
            provider, Limiter(), timeout_seconds=0.01
        )
        request = MerchantGenerativeExplanationHttpRequest.model_validate(command())
        with pytest.raises(MerchantGenerativeExplanationUnavailable):
            await app.explain(subject(), request)
        task = asyncio.create_task(
            MerchantGenerativeExplanationApplication(provider, Limiter()).explain(
                subject(), request
            )
        )
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


@pytest.mark.parametrize(
    ("locale", "reason", "headline", "body", "action_label"),
    [
        (
            "en",
            "ACK_ALLOWED_BY_CAPABILITY",
            "Courier has arrived",
            "You can acknowledge the courier’s arrival now.",
            "Acknowledge arrival",
        ),
        (
            "en",
            "ACK_IN_PROGRESS",
            "Acknowledging arrival",
            "AYO is confirming your acknowledgement.",
            None,
        ),
        (
            "en",
            "ACK_CONFIRMED",
            "Arrival acknowledged",
            "The courier’s arrival has been confirmed.",
            None,
        ),
        (
            "en",
            "ACK_RESULT_UNCERTAIN_RECONCILIATION_AVAILABLE",
            "Confirmation not clear yet",
            "AYO could not confirm the result. You can check the current status.",
            "Check status",
        ),
        (
            "en",
            "ACK_RECONCILIATION_IN_PROGRESS",
            "Checking status",
            "AYO is checking the latest acknowledgement status.",
            None,
        ),
        (
            "en",
            "ACK_SAME_ATTEMPT_RETRY_AVAILABLE",
            "Try acknowledgement again",
            "You can retry the same acknowledgement safely.",
            "Try again",
        ),
        (
            "en",
            "ACK_RETRY_ALLOWED_BY_CAPABILITY",
            "Try again",
            "The previous acknowledgement did not complete. You can try again.",
            "Try again",
        ),
        (
            "en",
            "ACK_RESULT_UNCERTAIN_NO_CURRENT_ACTION",
            "Confirmation not clear yet",
            "AYO could not confirm the result. No action is available right now.",
            None,
        ),
        (
            "en",
            "ACK_SAME_ATTEMPT_RETRY_NOT_CURRENTLY_ALLOWED",
            "Action not available right now",
            "The acknowledgement cannot be retried safely right now.",
            None,
        ),
        (
            "en",
            "ACK_REJECTED_NO_CURRENT_ACTION",
            "Action not available right now",
            "The arrival acknowledgement did not complete, and no action is available right now.",
            None,
        ),
        (
            "am",
            "ACK_ALLOWED_BY_CAPABILITY",
            "መልእክተኛው ደርሷል",
            "የመልእክተኛውን መድረስ አሁን ማረጋገጥ ይችላሉ።",
            "መድረሱን አረጋግጥ",
        ),
        ("am", "ACK_IN_PROGRESS", "መድረሱ እየተረጋገጠ ነው", "AYO ማረጋገጫዎን እያረጋገጠ ነው።", None),
        ("am", "ACK_CONFIRMED", "መድረሱ ተረጋግጧል", "የመልእክተኛው መድረስ ተረጋግጧል።", None),
        (
            "am",
            "ACK_RESULT_UNCERTAIN_RECONCILIATION_AVAILABLE",
            "ማረጋገጫው ገና ግልጽ አይደለም",
            "AYO ውጤቱን ማረጋገጥ አልቻለም። የአሁኑን ሁኔታ ማየት ይችላሉ።",
            "ሁኔታውን ይመልከቱ",
        ),
        (
            "am",
            "ACK_RECONCILIATION_IN_PROGRESS",
            "ሁኔታው እየታየ ነው",
            "AYO የቅርብ ጊዜውን የማረጋገጫ ሁኔታ እያየ ነው።",
            None,
        ),
        (
            "am",
            "ACK_SAME_ATTEMPT_RETRY_AVAILABLE",
            "ማረጋገጫውን እንደገና ይሞክሩ",
            "ይኸውን ማረጋገጫ በደህና እንደገና መሞከር ይችላሉ።",
            "እንደገና ሞክር",
        ),
        (
            "am",
            "ACK_RETRY_ALLOWED_BY_CAPABILITY",
            "እንደገና ይሞክሩ",
            "የቀድሞው ማረጋገጫ አልተጠናቀቀም። እንደገና መሞከር ይችላሉ።",
            "እንደገና ሞክር",
        ),
        (
            "am",
            "ACK_RESULT_UNCERTAIN_NO_CURRENT_ACTION",
            "ማረጋገጫው ገና ግልጽ አይደለም",
            "AYO ውጤቱን ማረጋገጥ አልቻለም። አሁን የሚገኝ እርምጃ የለም።",
            None,
        ),
        (
            "am",
            "ACK_SAME_ATTEMPT_RETRY_NOT_CURRENTLY_ALLOWED",
            "እርምጃው አሁን አይገኝም",
            "ማረጋገጫውን አሁን በደህና እንደገና መሞከር አይቻልም።",
            None,
        ),
        (
            "am",
            "ACK_REJECTED_NO_CURRENT_ACTION",
            "እርምጃው አሁን አይገኝም",
            "የመድረስ ማረጋገጫው አልተጠናቀቀም፣ እና አሁን የሚገኝ እርምጃ የለም።",
            None,
        ),
    ],
)
def test_server_canonical_language_matches_locked_phase_two_copy(
    locale, reason, headline, body, action_label
):
    language = canonical_merchant_intelligence_language(locale, reason)
    assert (language.headline, language.body, language.action_label) == (
        headline,
        body,
        action_label,
    )


def test_server_canonical_text_is_present_in_locked_mobile_phase_two_contract():
    mobile = Path(
        "AYO-Mobile/localization/merchant-operational-intelligence.ts"
    ).read_text(encoding="utf-8")
    reasons = (
        "ACK_ALLOWED_BY_CAPABILITY",
        "ACK_IN_PROGRESS",
        "ACK_CONFIRMED",
        "ACK_RESULT_UNCERTAIN_RECONCILIATION_AVAILABLE",
        "ACK_RECONCILIATION_IN_PROGRESS",
        "ACK_SAME_ATTEMPT_RETRY_AVAILABLE",
        "ACK_RETRY_ALLOWED_BY_CAPABILITY",
        "ACK_RESULT_UNCERTAIN_NO_CURRENT_ACTION",
        "ACK_SAME_ATTEMPT_RETRY_NOT_CURRENTLY_ALLOWED",
        "ACK_REJECTED_NO_CURRENT_ACTION",
    )
    for locale in ("en", "am"):
        for reason in reasons:
            language = canonical_merchant_intelligence_language(locale, reason)
            assert language.headline in mobile
            assert language.body in mobile
            if language.action_label is not None:
                assert language.action_label in mobile
