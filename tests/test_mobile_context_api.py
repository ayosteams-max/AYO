from contextlib import AbstractContextManager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import ValidationError

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.identity.models import IdentityType
from BACKEND.identity.runtime import AuthenticationRuntime
from BACKEND.main import (
    AuthenticationActivation,
    MobileContextActivation,
    create_app,
)
from BACKEND.merchant.models import (
    MerchantKind,
    MerchantProfile,
    MerchantState,
    OnboardingSource,
)
from BACKEND.mobile_context.application import (
    MobileContextApplication,
    MobileContextFeatures,
    MobileContextUnavailable,
)
from BACKEND.mobile_context.models import (
    CourierMobileContext,
    MerchantMobileContext,
    MobileContextResponse,
    PersonalMobileContext,
)
from BACKEND.routes.mobile_context import create_mobile_context_router

NOW = datetime(2026, 8, 6, tzinfo=UTC)
IDENTITY = UUID("30000000-0000-4000-8000-000000000001")
PICKUP = UUID("30000000-0000-4000-8000-000000000002")


def _subject(identity_type: IdentityType = IdentityType.RIDER) -> AuthorizationSubject:
    return AuthorizationSubject(
        identity_id=IDENTITY,
        identity_type=identity_type,
        actor_type=(
            ActorType.RIDER
            if identity_type is IdentityType.RIDER
            else ActorType.DRIVER
            if identity_type is IdentityType.DRIVER
            else ActorType.SERVICE
        ),
    )


def _merchant(
    name: str, state: MerchantState, merchant_id: UUID | None = None
) -> MerchantProfile:
    return MerchantProfile(
        merchant_id=merchant_id or uuid4(),
        owner_identity_id=IDENTITY,
        legal_name=f"{name} legal",
        display_name=name,
        kind=MerchantKind.COMPANY,
        onboarding_source=OnboardingSource.SELF,
        state=state,
        capability_code="merchant.general",
        market_code="ET-AA",
        created_at=NOW,
        updated_at=NOW,
    )


class _Authorization:
    def __init__(self, permissions: set[str]) -> None:
        self.permissions = permissions

    def has_permission(self, identity_id, permission, *, at) -> bool:
        assert identity_id == IDENTITY
        assert at.tzinfo is not None
        return permission in self.permissions


class _Merchants:
    def __init__(self, values: tuple[MerchantProfile, ...]) -> None:
        self.values = values

    def list_owned(self, owner_id, limit=50):
        assert owner_id == IDENTITY
        return self.values[:limit]


class _Pickups:
    def __init__(self, pickup_ids: tuple[UUID, ...]) -> None:
        self.values = tuple(SimpleNamespace(pickup_id=value) for value in pickup_ids)

    def current_for_courier(self, identity_id):
        assert identity_id == IDENTITY
        return self.values


class _Unit(AbstractContextManager[Any]):
    def __init__(self, permissions, merchants, pickups) -> None:
        self.authorization = _Authorization(permissions)
        self.merchants = _Merchants(merchants)
        self.courier_pickup = _Pickups(pickups)
        self.entered = 0
        self.exited = 0

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *args):
        self.exited += 1
        return None


class _Composition:
    def __init__(self, unit: _Unit) -> None:
        self.unit = unit

    def unit_of_work(self):
        return self.unit


def _features(**changes: bool) -> MobileContextFeatures:
    values = {
        "personal_enabled": True,
        "merchant_enabled": True,
        "courier_dispatch_enabled": True,
        "courier_pickup_enabled": True,
    }
    values.update(changes)
    return MobileContextFeatures(**values)


def _application(
    *,
    permissions: set[str] | None = None,
    merchants: tuple[MerchantProfile, ...] = (),
    pickups: tuple[UUID, ...] = (),
) -> tuple[MobileContextApplication, _Unit]:
    unit = _Unit(permissions or set(), merchants, pickups)
    return MobileContextApplication(_Composition(unit)), unit


def test_public_dtos_are_frozen_and_forbid_extra_fields() -> None:
    for model, payload in (
        (PersonalMobileContext, {"available": True}),
        (
            MerchantMobileContext,
            {
                "merchant_id": uuid4(),
                "display_name": "Business",
                "availability": "available",
            },
        ),
        (CourierMobileContext, {"pickup_id": uuid4()}),
        (
            MobileContextResponse,
            {"personal": None, "merchants": (), "courier": None},
        ),
    ):
        value = model.model_validate(payload)
        with pytest.raises(ValidationError):
            model.model_validate({**payload, "identity_id": uuid4()})
        with pytest.raises(ValidationError):
            value.unexpected = True  # type: ignore[attr-defined,union-attr,misc]


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (MerchantState.DRAFT, "pending"),
        (MerchantState.VERIFICATION_PENDING, "pending"),
        (MerchantState.APPROVED, "available"),
        (MerchantState.SUSPENDED, "suspended"),
    ],
)
def test_merchant_states_map_truthfully(state, expected) -> None:
    application, _ = _application(
        permissions={"merchant.dashboard.read_own"},
        merchants=(_merchant("Business", state),),
    )
    result = application.read(_subject(), features=_features(), at=NOW)
    assert result.merchants[0].availability.value == expected


def test_multiple_merchants_are_deterministic_and_minimized() -> None:
    first = _merchant("Zed", MerchantState.APPROVED)
    second = _merchant("addis", MerchantState.DRAFT)
    application, _ = _application(
        permissions={"merchant.dashboard.read_own"}, merchants=(first, second)
    )
    payload = application.read(_subject(), features=_features(), at=NOW).model_dump(
        mode="json"
    )
    assert [item["display_name"] for item in payload["merchants"]] == ["addis", "Zed"]
    assert set(payload["merchants"][0]) == {
        "merchant_id",
        "display_name",
        "availability",
    }
    assert "owner_identity_id" not in str(payload)


def test_permission_absence_excludes_merchant_and_courier_contexts() -> None:
    application, _ = _application(
        merchants=(_merchant("Hidden", MerchantState.APPROVED),), pickups=(PICKUP,)
    )
    result = application.read(
        _subject(IdentityType.DRIVER), features=_features(), at=NOW
    )
    assert result.merchants == ()
    assert result.courier is None


def test_personal_context_requires_rider_identity_and_feature() -> None:
    application, _ = _application()
    assert application.read(_subject(), features=_features(), at=NOW).personal
    assert (
        application.read(
            _subject(IdentityType.DRIVER), features=_features(), at=NOW
        ).personal
        is None
    )
    assert (
        application.read(
            _subject(), features=_features(personal_enabled=False), at=NOW
        ).personal
        is None
    )


def test_independently_proven_merchant_and_courier_contexts_coexist() -> None:
    application, unit = _application(
        permissions={
            "merchant.dashboard.read_own",
            "courier_pickup.manage_assigned",
        },
        merchants=(_merchant("Shop", MerchantState.APPROVED),),
        pickups=(PICKUP,),
    )
    result = application.read(_subject(), features=_features(), at=NOW)
    assert result.personal is not None
    assert len(result.merchants) == 1
    assert result.courier and result.courier.pickup_id == PICKUP
    assert unit.entered == unit.exited == 1


def test_ambiguous_or_disabled_courier_context_fails_closed() -> None:
    application, _ = _application(
        permissions={"courier_pickup.manage_assigned"},
        pickups=(PICKUP, uuid4()),
    )
    assert application.read(_subject(), features=_features(), at=NOW).courier is None
    assert (
        application.read(
            _subject(), features=_features(courier_pickup_enabled=False), at=NOW
        ).courier
        is None
    )


def test_excess_merchant_contexts_fail_closed() -> None:
    application, _ = _application(
        permissions={"merchant.dashboard.read_own"},
        merchants=tuple(
            _merchant(f"Business {index:02d}", MerchantState.APPROVED)
            for index in range(51)
        ),
    )
    with pytest.raises(MobileContextUnavailable, match="limit"):
        application.read(_subject(), features=_features(), at=NOW)


class _Resolver:
    def __init__(self, subject: AuthorizationSubject | None) -> None:
        self.subject = subject

    async def resolve(self, request):
        del request
        return self.subject


def _client(subject: AuthorizationSubject | None, application) -> TestClient:
    api = FastAPI()
    api.include_router(
        create_mobile_context_router(
            application, _Resolver(subject), features=_features()
        )
    )
    return TestClient(api)


def test_route_is_authenticated_no_input_and_selector_values_are_ignored() -> None:
    application, _ = _application()
    assert _client(None, application).get("/mobile/context").status_code == 401
    client = _client(_subject(), application)
    expected = client.get("/mobile/context")
    supplied = client.get(
        "/mobile/context",
        params={"identity_id": str(uuid4()), "requested_role": "courier"},
    )
    assert expected.status_code == supplied.status_code == 200
    assert expected.json() == supplied.json()
    router = create_mobile_context_router(
        application, _Resolver(_subject()), features=_features()
    )
    route = cast(
        APIRoute,
        next(
            route
            for route in router.routes
            if getattr(route, "path", None) == "/mobile/context"
        ),
    )
    assert [parameter.name for parameter in route.dependant.query_params] == []


def test_valid_identity_with_no_contexts_gets_bounded_empty_response() -> None:
    application, _ = _application()
    response = _client(_subject(IdentityType.DRIVER), application).get(
        "/mobile/context"
    )
    assert response.status_code == 200
    assert response.json() == {"personal": None, "merchants": [], "courier": None}


def test_internal_failures_are_sanitized(caplog) -> None:
    class _Failure:
        def read(self, subject, *, features, at):
            del subject, features, at
            raise RuntimeError("secret internal assignment detail")

    response = _client(_subject(), _Failure()).get("/mobile/context")
    assert response.status_code == 503
    assert response.json() == {
        "detail": {"code": "mobile_context_temporarily_unavailable"}
    }
    assert "secret" not in response.text
    assert "secret" not in caplog.text


def test_platform_activation_is_default_disabled_and_requires_authentication() -> None:
    assert Settings().MOBILE_ACTOR_CONTEXT_ENABLED is False
    with pytest.raises(ValueError, match="requires Authentication"):
        Settings(MOBILE_ACTOR_CONTEXT_ENABLED=True)
    with pytest.raises(ValueError, match="production activation"):
        Settings(
            ENVIRONMENT=AppEnvironment.PRODUCTION,
            AUTHENTICATION_ENABLED=True,
            MOBILE_ACTOR_CONTEXT_ENABLED=True,
        )


def test_registered_route_uses_stable_error_envelope() -> None:
    class _Failure:
        def read(self, subject, *, features, at):
            del subject, features, at
            raise RuntimeError("private repository detail")

    resolver = _Resolver(_subject())
    api = create_app(
        Settings(
            ENVIRONMENT=AppEnvironment.TEST,
            AUTHENTICATION_ENABLED=True,
            MOBILE_ACTOR_CONTEXT_ENABLED=True,
        ),
        authentication=AuthenticationActivation(
            runtime=cast(AuthenticationRuntime, object()),
            subject_resolver=resolver,
        ),
        mobile_context=MobileContextActivation(
            application=cast(MobileContextApplication, _Failure()),
            subject_resolver=resolver,
        ),
    )
    response = TestClient(api).get("/api/mobile/context")
    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "mobile_context_temporarily_unavailable"}
    }
    assert "private" not in response.text
