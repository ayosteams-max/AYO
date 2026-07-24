import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine

from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.engineering.runtime import EngineeringRuntime
from BACKEND.main import app, create_app

client = TestClient(app)


def test_root_and_health_endpoints():
    root = client.get("/")
    health = client.get("/health")

    assert root.status_code == 200
    assert root.json()["status"] == "Backend is running successfully."
    assert health.status_code == 200
    assert health.json() == {"status": "healthy"}


def test_openapi_preserves_current_route_inventory():
    paths = set(client.get("/openapi.json").json()["paths"])

    assert paths == {"/", "/health"}


def test_insecure_legacy_runtime_routes_are_not_exposed():
    legacy_requests = (
        ("post", "/api/rides/"),
        ("post", "/api/driver-offers/accept"),
        ("post", "/api/driver-offers/decline"),
        ("get", "/api/ride-status/legacy-ride"),
        ("post", "/api/ride-status/on-the-way"),
        ("post", "/api/ride-status/arrived"),
        ("post", "/api/ride-status/start"),
        ("post", "/api/ride-status/complete"),
        ("post", "/api/wallet/withdraw"),
        ("get", "/api/wallet/legacy-driver"),
    )

    for method, path in legacy_requests:
        response = client.request(method, path, json={})
        assert response.status_code == 404, (method, path, response.text)


def test_engineering_probes_distinguish_liveness_and_readiness():
    application = create_app(Settings(), engineering_runtime=EngineeringRuntime())

    with TestClient(application) as lifecycle_client:
        assert lifecycle_client.get("/livez").json() == {"status": "live"}
        assert lifecycle_client.get("/readyz").json() == {
            "status": "ready",
            "database": "not_required",
            "schema": "not_required",
        }

    assert application.state.engineering_runtime.live is False


def test_required_persistence_fails_closed_when_schema_is_not_postgresql_ready():
    engine = create_engine("sqlite://")
    runtime = EngineeringRuntime(engine, persistence_required=True)
    application = create_app(Settings(), engineering_runtime=runtime)

    with (
        pytest.raises(RuntimeError, match="failed startup validation"),
        TestClient(application),
    ):
        pass

    engine.dispose()


def test_application_environment_is_namespaced_and_production_safe(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.delenv("AYO_DEBUG", raising=False)
    assert Settings().DEBUG is False

    monkeypatch.setenv("AYO_DEBUG", "true")
    assert Settings().DEBUG is True

    with pytest.raises(ValidationError, match="Debug mode is prohibited"):
        Settings(ENVIRONMENT=AppEnvironment.PRODUCTION, PERSISTENCE_ENABLED=True)

    monkeypatch.setenv("AYO_DEBUG", "false")
    with pytest.raises(ValidationError, match="PostgreSQL persistence is required"):
        Settings(ENVIRONMENT=AppEnvironment.PRODUCTION)
