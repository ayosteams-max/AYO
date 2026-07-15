from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from BACKEND.active_ride.engine import evaluate_confidence
from BACKEND.active_ride.models import ConfidencePolicy, ConfidenceSignals


def test_confidence_engine_10000_evaluations_under_characterization_guard():
    now = datetime(2026, 7, 16, 12, tzinfo=UTC)
    ride_id = uuid4()
    policy = ConfidencePolicy()
    signals = ConfidenceSignals(
        driver_location_age_seconds=5,
        rider_location_age_seconds=6,
        pickup_eta_increase_seconds=200,
    )
    started = perf_counter()
    for _ in range(10_000):
        evaluate_confidence(ride_id, signals, policy, now=now)
    elapsed_ms = (perf_counter() - started) * 1000
    assert elapsed_ms < 1_000, f"confidence evaluation took {elapsed_ms:.2f} ms"
