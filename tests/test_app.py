from fastapi.testclient import TestClient

from BACKEND.main import app

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

    assert paths == {
        "/",
        "/health",
        "/api/rides/",
        "/api/driver-offers/accept",
        "/api/driver-offers/decline",
        "/api/ride-status/{ride_id}",
        "/api/ride-status/on-the-way",
        "/api/ride-status/arrived",
        "/api/ride-status/start",
        "/api/ride-status/complete",
        "/api/wallet/withdraw",
        "/api/wallet/{driver_id}",
    }
