from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import insert, select

from BACKEND.authorization.enforcement import AuthorizationEnforcer
from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.dispatch.api_security import PostgresDispatchRateLimiter
from BACKEND.dispatch.application import DispatchApplication
from BACKEND.dispatch.models import (
    DispatchPolicy,
    DriverAvailability,
    DriverCandidate,
)
from BACKEND.dispatch.outbox import LocalIdempotentPublisher
from BACKEND.dispatch.outbox_worker import OutboxDeliveryWorker
from BACKEND.dispatch.scheduler import (
    DispatchRecoveryCoordinator,
    PostgresRecoveryWorkerLock,
    WorkerHealth,
)
from BACKEND.dispatch.worker import DispatchRecoveryWorker
from BACKEND.identity.verification import (
    AsymmetricJwtVerifier,
    RotatingStaticKeyProvider,
    VerifiedSubjectResolver,
)
from BACKEND.main import DispatchActivation, create_app
from BACKEND.observability import InMemoryMetricsSink
from BACKEND.persistence.audit_repository import StandaloneAuditWriter
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.persistence.tables import (
    audit_events,
    dispatch_assignments,
    dispatch_driver_offers,
    identities,
    identity_role_assignments,
    permissions,
    role_permissions,
    roles,
    sessions,
)

pytestmark = pytest.mark.integration
ISSUER = "https://identity.test.ayo.example"
AUDIENCE = "ayo-api"
RIDER_ID = UUID("10000000-0000-4000-8000-000000000101")
DRIVER_ID = UUID("20000000-0000-4000-8000-000000000101")
SERVICE_ID = UUID("50000000-0000-4000-8000-000000000101")
ADMIN_ID = UUID("60000000-0000-4000-8000-000000000101")
RIDER_SESSION = UUID("30000000-0000-4000-8000-000000000101")
DRIVER_SESSION = UUID("30000000-0000-4000-8000-000000000102")
SERVICE_SESSION = UUID("30000000-0000-4000-8000-000000000103")
ADMIN_SESSION = UUID("30000000-0000-4000-8000-000000000104")


class FixedCandidates:
    def list_candidates(self, *, ride, now, limit):
        del ride
        return [
            DriverCandidate(
                driver_id=DRIVER_ID,
                availability=DriverAvailability.AVAILABLE,
                verified=True,
                safety_eligible=True,
                service_types=frozenset({"ayo_go"}),
                pickup_eta_seconds=75,
                location_observed_at=now - timedelta(seconds=1),
            )
        ][:limit]


def seed_identity_access(postgres_engine) -> None:
    now = datetime.now(UTC)
    rider_permission = uuid4()
    driver_permission = uuid4()
    worker_permission = uuid4()
    health_permission = uuid4()
    rider_role = uuid4()
    driver_role = uuid4()
    worker_role = uuid4()
    health_role = uuid4()
    with postgres_engine.begin() as connection:
        for identity_id, identity_type, session_id in (
            (RIDER_ID, "rider", RIDER_SESSION),
            (DRIVER_ID, "driver", DRIVER_SESSION),
            (SERVICE_ID, "service", SERVICE_SESSION),
            (ADMIN_ID, "administrator", ADMIN_SESSION),
        ):
            connection.execute(
                insert(identities).values(
                    identity_id=identity_id,
                    public_id=uuid4(),
                    identity_type=identity_type,
                    status="active",
                    created_at=now,
                    updated_at=now,
                    version=1,
                )
            )
            connection.execute(
                insert(sessions).values(
                    session_id=session_id,
                    subject_id=str(identity_id),
                    identity_id=identity_id,
                    token_hash=uuid4().bytes + uuid4().bytes,
                    created_at=now,
                    expires_at=now + timedelta(hours=1),
                    version=1,
                )
            )
        for permission_id, code in (
            (rider_permission, "dispatch.rider.request"),
            (driver_permission, "dispatch.driver.offer.respond"),
            (worker_permission, "dispatch.worker.recover"),
            (health_permission, "dispatch.admin.health.read"),
        ):
            connection.execute(
                insert(permissions).values(
                    permission_id=permission_id,
                    code=code,
                    description=code,
                    created_at=now,
                )
            )
        for role_id, code in (
            (rider_role, "dispatch_test_rider"),
            (driver_role, "dispatch_test_driver"),
            (worker_role, "dispatch_test_worker"),
            (health_role, "dispatch_test_admin"),
        ):
            connection.execute(
                insert(roles).values(
                    role_id=role_id,
                    code=code,
                    description=code,
                    system_managed=False,
                    created_at=now,
                    version=1,
                )
            )
        connection.execute(
            insert(role_permissions),
            [
                {
                    "role_id": rider_role,
                    "permission_id": rider_permission,
                    "granted_at": now,
                },
                {
                    "role_id": driver_role,
                    "permission_id": driver_permission,
                    "granted_at": now,
                },
                {
                    "role_id": worker_role,
                    "permission_id": worker_permission,
                    "granted_at": now,
                },
                {
                    "role_id": health_role,
                    "permission_id": health_permission,
                    "granted_at": now,
                },
            ],
        )
        connection.execute(
            insert(identity_role_assignments),
            [
                {
                    "assignment_id": uuid4(),
                    "identity_id": RIDER_ID,
                    "role_id": rider_role,
                    "assigned_by_identity_id": RIDER_ID,
                    "assigned_at": now,
                },
                {
                    "assignment_id": uuid4(),
                    "identity_id": DRIVER_ID,
                    "role_id": driver_role,
                    "assigned_by_identity_id": RIDER_ID,
                    "assigned_at": now,
                },
                {
                    "assignment_id": uuid4(),
                    "identity_id": SERVICE_ID,
                    "role_id": worker_role,
                    "assigned_by_identity_id": RIDER_ID,
                    "assigned_at": now,
                },
                {
                    "assignment_id": uuid4(),
                    "identity_id": ADMIN_ID,
                    "role_id": health_role,
                    "assigned_by_identity_id": RIDER_ID,
                    "assigned_at": now,
                },
            ],
        )


def access_token(private_key, *, identity_id, session_id, identity_type):
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "nbf": now - timedelta(seconds=1),
            "exp": now + timedelta(minutes=5),
            "sub": str(identity_id),
            "sid": str(session_id),
            "jti": str(uuid4()),
            "identity_type": identity_type,
            "assurance_level": "basic",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key-1", "typ": "at+jwt"},
    )


def test_authenticated_rider_to_driver_assignment_end_to_end(postgres_engine) -> None:
    seed_identity_access(postgres_engine)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    composition = PostgresRepositoryComposition(
        postgres_engine, dispatch_candidates=FixedCandidates()
    )
    metrics = InMemoryMetricsSink()
    verifier = AsymmetricJwtVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        algorithms=("RS256",),
        key_provider=RotatingStaticKeyProvider(
            {("test-key-1", "RS256"): private_key.public_key()}
        ),
    )
    dispatch = DispatchApplication(composition, DispatchPolicy(version="dispatch.v1"))
    health = WorkerHealth()
    outbox_health = WorkerHealth()
    activation = DispatchActivation(
        application=dispatch,
        subject_resolver=VerifiedSubjectResolver(
            verifier,
            composition,
            metrics=metrics,
            audit_writer=StandaloneAuditWriter(postgres_engine),
        ),
        authorization_enforcer=AuthorizationEnforcer(composition, metrics=metrics),
        rate_limiter=PostgresDispatchRateLimiter(composition),
        recovery_coordinator=DispatchRecoveryCoordinator(
            DispatchRecoveryWorker(dispatch),
            PostgresRecoveryWorkerLock(postgres_engine),
            health,
            metrics=metrics,
        ),
        outbox_worker=OutboxDeliveryWorker(
            composition,
            LocalIdempotentPublisher(),
            worker_id="e2e-outbox",
            metrics=metrics,
            health=outbox_health,
        ),
        recovery_health=health,
        outbox_health=outbox_health,
        metrics=metrics,
    )
    app = create_app(
        Settings(ENVIRONMENT=AppEnvironment.TEST, DISPATCH_ENABLED=True),
        dispatch=activation,
    )
    client = TestClient(app)
    rider_token = access_token(
        private_key,
        identity_id=RIDER_ID,
        session_id=RIDER_SESSION,
        identity_type="rider",
    )
    driver_token = access_token(
        private_key,
        identity_id=DRIVER_ID,
        session_id=DRIVER_SESSION,
        identity_type="driver",
    )
    service_token = access_token(
        private_key,
        identity_id=SERVICE_ID,
        session_id=SERVICE_SESSION,
        identity_type="service",
    )
    admin_token = access_token(
        private_key,
        identity_id=ADMIN_ID,
        session_id=ADMIN_SESSION,
        identity_type="administrator",
    )
    now = datetime.now(UTC)
    ride_response = client.post(
        "/api/dispatch/rides",
        headers={
            "Authorization": f"Bearer {rider_token}",
            "Idempotency-Key": "e2e-network-retry-key-0001",
        },
        json={
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
                "expires_at": (now + timedelta(minutes=5)).isoformat(),
            },
        },
    )
    assert ride_response.status_code == 201
    assert "assigned_driver_id" not in ride_response.json()
    with postgres_engine.connect() as connection:
        offer_id = connection.execute(
            select(dispatch_driver_offers.c.offer_id)
        ).scalar_one()
    offer_response = client.get(
        f"/api/dispatch/offers/{offer_id}",
        headers={"Authorization": f"Bearer {driver_token}"},
    )
    assert offer_response.status_code == 200
    assert set(offer_response.json()) == {"offer_id", "ride_id", "expires_at"}
    accepted = client.post(
        f"/api/dispatch/offers/{offer_id}/accept",
        headers={"Authorization": f"Bearer {driver_token}"},
    )
    assert accepted.status_code == 200
    assert set(accepted.json()) == {
        "ride_id",
        "state",
        "version",
        "pickup_name",
        "destination_name",
        "service_type",
        "estimated_fare_minor",
        "currency",
    }
    with postgres_engine.connect() as connection:
        assignment = connection.execute(select(dispatch_assignments)).mappings().one()
    assert assignment["driver_identity_id"] == DRIVER_ID
    assert assignment["ride_id"] == UUID(accepted.json()["ride_id"])
    delivered = client.post(
        "/api/internal/dispatch/workers/outbox/run",
        headers={"Authorization": f"Bearer {service_token}"},
    )
    assert delivered.status_code == 200
    health_response = client.get(
        "/api/internal/dispatch/workers/outbox/health",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert health_response.status_code == 200
    assert "last_failure_reason" in health_response.json()
    denied = client.get(
        "/api/internal/dispatch/workers/outbox/health",
        headers={"Authorization": f"Bearer {rider_token}"},
    )
    assert denied.status_code == 403
    forged = client.get(
        "/api/dispatch/rides/active",
        headers={"Authorization": "Bearer malformed-token-value"},
    )
    assert forged.status_code == 401
    assert forged.json() == {"error": {"code": "authentication_required"}}
    with postgres_engine.connect() as connection:
        actions = set(connection.execute(select(audit_events.c.action)).scalars())
    assert "authentication.access.denied" in actions
