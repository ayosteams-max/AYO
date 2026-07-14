from fastapi.testclient import TestClient

from BACKEND.main import app

client = TestClient(app)


def test_complete_current_ride_happy_path():
    created = client.post(
        "/api/rides/",
        json={
            "rider_name": "Test Rider",
            "pickup": "Test Pickup",
            "destination": "Test Destination",
            "pickup_latitude": 8.9806,
            "pickup_longitude": 38.7578,
            "ride_type": "standard",
        },
    )
    assert created.status_code == 200
    ride = created.json()
    assert ride["status"] == "WAITING_FOR_DRIVER"

    decision = {"ride_id": ride["ride_id"], "driver_id": ride["driver_id"]}
    transitions = [
        ("/api/driver-offers/accept", "DRIVER_ACCEPTED"),
        ("/api/ride-status/on-the-way", "DRIVER_ON_THE_WAY"),
        ("/api/ride-status/arrived", "DRIVER_ARRIVED"),
        ("/api/ride-status/start", "TRIP_STARTED"),
    ]
    for endpoint, expected_status in transitions:
        response = client.post(endpoint, json=decision)
        assert response.status_code == 200
        assert response.json()["ride"]["status"] == expected_status

    completed = client.post(
        "/api/ride-status/complete",
        json={**decision, "gross_fare": 100, "payment_method": "CARD"},
    )
    assert completed.status_code == 200
    assert completed.json()["ride"]["status"] == "TRIP_COMPLETED"
    assert completed.json()["earnings"]["driver_net"] == 85


def test_invalid_transition_remains_rejected():
    created = client.post(
        "/api/rides/",
        json={
            "rider_name": "Test Rider",
            "pickup": "Test Pickup",
            "destination": "Test Destination",
            "pickup_latitude": 8.9806,
            "pickup_longitude": 38.7578,
        },
    ).json()

    response = client.post(
        "/api/ride-status/start",
        json={"ride_id": created["ride_id"], "driver_id": created["driver_id"]},
    )

    assert response.status_code == 409
