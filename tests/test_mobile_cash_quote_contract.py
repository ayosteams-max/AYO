from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationContextMiddleware
from BACKEND.identity.models import IdentityType
from BACKEND.routes.mobile_quotes import create_mobile_quote_router


class FixedResolver:
    def __init__(self, subject):
        self.subject = subject

    async def resolve(self, request: Request):
        del request
        return self.subject


class CapturingEnforcer:
    def __init__(self):
        self.requirement = None

    def enforce(self, request, requirement):
        del request
        self.requirement = requirement


class FixedQuoteApplication:
    def __init__(self, rider_id):
        self.rider_id = rider_id
        self.calls = []

    def quote(self, subject, **kwargs):
        assert subject.identity_id == self.rider_id
        self.calls.append(kwargs)
        now = datetime.now(UTC)
        return SimpleNamespace(
            estimate_id=uuid4(),
            ride_request_id=kwargs["ride_request_id"],
            breakdown=SimpleNamespace(currency="ETB", rider_total_minor=4325),
            expires_at=now + timedelta(minutes=5),
            policy_version="pricing.approved.v1",
            service_type="immediate_standard",
        )


def client(subject):
    enforcer = CapturingEnforcer()
    application = FixedQuoteApplication(subject.identity_id if subject else None)
    app = FastAPI()
    app.state.authorization_enforcer = enforcer
    app.include_router(create_mobile_quote_router(application), prefix="/api")
    app.add_middleware(AuthorizationContextMiddleware, resolver=FixedResolver(subject))
    return TestClient(app), application, enforcer


def test_authenticated_quote_contract_exposes_only_server_pricing_output():
    rider = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    api, application, enforcer = client(rider)
    ride_request_id = uuid4()
    response = api.post(
        "/api/mobile/cash-fare-quotes",
        json={"ride_request_id": str(ride_request_id)},
        headers={"Idempotency-Key": "mobile-quote-key-0001"},
    )
    assert response.status_code == 200
    assert response.json()["amount_minor"] == 4325
    assert response.json()["currency"] == "ETB"
    assert response.json()["payment_method"] == "cash"
    assert application.calls[0]["ride_request_id"] == ride_request_id
    assert enforcer.requirement.permission == "pricing.estimate.create"


def test_quote_contract_rejects_unauthenticated_and_client_fare_inputs():
    api, _, _ = client(None)
    assert (
        api.post(
            "/api/mobile/cash-fare-quotes",
            json={"ride_request_id": str(uuid4())},
            headers={"Idempotency-Key": "mobile-quote-key-0002"},
        ).status_code
        == 401
    )

    rider = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    api, _, _ = client(rider)
    response = api.post(
        "/api/mobile/cash-fare-quotes",
        json={"ride_request_id": str(uuid4()), "amount_minor": 1},
        headers={"Idempotency-Key": "mobile-quote-key-0003"},
    )
    assert response.status_code == 422


def test_mobile_quote_activation_is_disabled_and_production_fails_closed():
    from BACKEND.config.settings import AppEnvironment, Settings

    assert Settings(DEBUG=True, _env_file=None).MOBILE_CASH_QUOTE_ENABLED is False
    with pytest.raises(ValidationError, match="production activation"):
        Settings(
            DEBUG=True,
            ENVIRONMENT=AppEnvironment.PRODUCTION,
            MOBILE_CASH_QUOTE_ENABLED=True,
            _env_file=None,
        )
