from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationContextMiddleware
from BACKEND.dispatch.application import DispatchApplication
from BACKEND.dispatch.memory import InMemoryDispatchRepository
from BACKEND.dispatch.models import (
    CreateRideCommand,
    DispatchPolicy,
    DispatchScore,
    DriverOffer,
    PlaceSnapshot,
    RideProjection,
    RideState,
)
from BACKEND.dispatch.worker import DispatchRecoveryWorker
from BACKEND.identity.models import IdentityType
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.rate_limit.models import RateLimitDecision
from BACKEND.routes.dispatch import create_dispatch_router

NOW = datetime(2026, 7, 16, 8, tzinfo=UTC)
RIDER_ID = UUID("10000000-0000-4000-8000-000000000001")
DRIVER_ID = UUID("20000000-0000-4000-8000-000000000001")


def command_payload() -> dict[str, object]:
    return {
        "pickup": {"place_id": "pickup-0001", "display_name": "Bole"},
        "destination": {
            "place_id": "destination-0001",
            "display_name": "Meskel Square",
        },
        "service_type": "ayo_go",
        "quote": {
            "quote_id": str(uuid4()),
            "amount_minor": 18000,
            "currency": "ETB",
            "pricing_version": "pricing.v1",
            "expires_at": (NOW + timedelta(days=7)).isoformat(),
        },
    }


def projection(state: RideState = RideState.SEARCHING) -> RideProjection:
    return RideProjection(
        ride_id=uuid4(),
        state=state,
        version=1,
        accepted_at=NOW,
        pickup=PlaceSnapshot(place_id="pickup-0001", display_name="Bole"),
        destination=PlaceSnapshot(
            place_id="destination-0001", display_name="Meskel Square"
        ),
        service_type="ayo_go",
        estimated_fare_minor=18000,
        currency="ETB",
        assigned_driver_id=DRIVER_ID if state is RideState.ASSIGNED else None,
    )


class FixedResolver:
    def __init__(self, subject: AuthorizationSubject | None) -> None:
        self.subject = subject

    async def resolve(self, request):
        del request
        return self.subject


class AllowingEnforcer:
    def enforce(self, request, requirement) -> None:
        del request, requirement


class AllowingRateLimiter:
    def consume(self, *, subject, operation):
        del subject, operation
        return RateLimitDecision(allowed=True, remaining=1, retry_after_seconds=0)


class FakeApplication:
    def __init__(self) -> None:
        self.ride = projection()
        self.offer = DriverOffer(
            ride_id=self.ride.ride_id,
            driver_id=DRIVER_ID,
            created_at=NOW,
            expires_at=NOW + timedelta(seconds=15),
            policy_version="dispatch.v1",
            score=DispatchScore(
                driver_id=DRIVER_ID,
                pickup_eta_seconds=60,
                effective_eta_seconds=60,
                trust_score=Decimal("0.5000"),
                neutral_reputation=True,
                fairness_credit_seconds=0,
                reliability_penalty_seconds=0,
                policy_version="dispatch.v1",
                reason_codes=("fastest_suitable", "neutral_reputation"),
            ),
        )
        self.rider_ids: list[UUID] = []
        self.driver_ids: list[UUID] = []

    def create_ride(self, *, rider_id, idempotency_key, command):
        assert idempotency_key == "network-retry-key-0001"
        assert isinstance(command, CreateRideCommand)
        self.rider_ids.append(rider_id)
        return self.ride, True

    def dispatch_next(self, ride_id):
        assert ride_id == self.ride.ride_id
        return self.offer

    def recover_ride(self, rider_id):
        self.rider_ids.append(rider_id)
        return self.ride

    def get_offer(self, offer_id):
        return self.offer if offer_id == self.offer.offer_id else None

    def accept_offer(self, offer_id, driver_id):
        assert offer_id == self.offer.offer_id
        self.driver_ids.append(driver_id)
        return self.ride.model_copy(
            update={"state": RideState.ASSIGNED, "assigned_driver_id": driver_id}
        )

    def decline_offer(self, offer_id, driver_id):
        assert offer_id == self.offer.offer_id
        self.driver_ids.append(driver_id)
        return None


def client_for(
    subject: AuthorizationSubject | None, application: FakeApplication, limiter=None
):
    app = FastAPI()
    app.state.authorization_enforcer = AllowingEnforcer()
    app.state.dispatch_rate_limiter = limiter or AllowingRateLimiter()
    app.include_router(create_dispatch_router(cast(DispatchApplication, application)))
    app.add_middleware(AuthorizationContextMiddleware, resolver=FixedResolver(subject))
    return TestClient(app)


def subject(identity_type: IdentityType, identity_id: UUID) -> AuthorizationSubject:
    actor = ActorType.RIDER if identity_type is IdentityType.RIDER else ActorType.DRIVER
    return AuthorizationSubject(
        identity_id=identity_id, identity_type=identity_type, actor_type=actor
    )


def test_rider_api_uses_authenticated_identity_and_sanitizes_response() -> None:
    application = FakeApplication()
    client = client_for(subject(IdentityType.RIDER, RIDER_ID), application)
    response = client.post(
        "/dispatch/rides",
        headers={"Idempotency-Key": "network-retry-key-0001"},
        json=command_payload(),
    )
    assert response.status_code == 201
    assert application.rider_ids == [RIDER_ID, RIDER_ID]
    assert set(response.json()) == {
        "ride_id",
        "state",
        "version",
        "pickup_name",
        "destination_name",
        "service_type",
        "estimated_fare_minor",
        "currency",
    }
    injected = command_payload() | {"rider_id": str(uuid4())}
    assert (
        client.post(
            "/dispatch/rides",
            headers={"Idempotency-Key": "network-retry-key-0001"},
            json=injected,
        ).status_code
        == 422
    )


def test_api_denies_missing_or_wrong_identity_type() -> None:
    application = FakeApplication()
    assert (
        client_for(None, application).get("/dispatch/rides/active").status_code == 401
    )
    driver = subject(IdentityType.DRIVER, DRIVER_ID)
    assert (
        client_for(driver, application).get("/dispatch/rides/active").status_code == 403
    )


def test_driver_offer_is_owner_scoped_and_hides_scoring() -> None:
    application = FakeApplication()
    client = client_for(subject(IdentityType.DRIVER, DRIVER_ID), application)
    response = client.get(f"/dispatch/offers/{application.offer.offer_id}")
    assert response.status_code == 200
    assert set(response.json()) == {"offer_id", "ride_id", "expires_at"}
    assert (
        client.post(f"/dispatch/offers/{application.offer.offer_id}/accept").status_code
        == 200
    )
    assert (
        client.post(
            f"/dispatch/offers/{application.offer.offer_id}/decline"
        ).status_code
        == 204
    )
    stranger = client_for(subject(IdentityType.DRIVER, uuid4()), application)
    assert (
        stranger.get(f"/dispatch/offers/{application.offer.offer_id}").status_code
        == 404
    )


def test_rate_limit_boundary_returns_stable_public_error() -> None:
    class DenyingRateLimiter:
        def consume(self, *, subject, operation):
            del subject, operation
            return RateLimitDecision(allowed=False, remaining=0, retry_after_seconds=12)

    client = client_for(
        subject(IdentityType.RIDER, RIDER_ID),
        FakeApplication(),
        DenyingRateLimiter(),
    )
    response = client.get("/dispatch/rides/active")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "12"


class FakeUnit:
    def __init__(self, repository) -> None:
        self.dispatch = repository

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class FakeComposition:
    def __init__(self, repository) -> None:
        self.repository = repository

    def unit_of_work(self):
        return FakeUnit(self.repository)


class RecoveryMemoryDispatchRepository(InMemoryDispatchRepository):
    def list_searching_ride_ids(self, *, limit: int) -> list[UUID]:
        del limit
        return []

    def abandon_expired_searches(self, *, now: datetime, limit: int) -> int:
        del now, limit
        return 0


def test_application_and_worker_are_bounded_transaction_entry_points() -> None:
    repository = RecoveryMemoryDispatchRepository()
    policy = DispatchPolicy(version="dispatch.v1")
    application = DispatchApplication(
        cast(PostgresRepositoryComposition, FakeComposition(repository)),
        policy,
    )
    command = CreateRideCommand.model_validate(command_payload())
    ride, created = application.create_ride(
        rider_id=RIDER_ID,
        idempotency_key="network-retry-key-0001",
        command=command,
        now=NOW,
    )
    assert created
    assert application.recover_ride(RIDER_ID) == ride
    assert application.dispatch_next(ride.ride_id) is None
    result = DispatchRecoveryWorker(application, batch_limit=10).run_once(now=NOW)
    assert result.expired_offers == 0
    assert result.resumed_searches == 0
    assert result.abandoned_searches == 0
