from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from BACKEND.arrival_waiting.engine import evaluate_arrival
from BACKEND.arrival_waiting.models import (
    ArrivalPolicy,
    ArrivalSignals,
    LocationObservation,
)


def test_arrival_evaluation_benchmark_is_bounded():
    now = datetime(2026, 7, 16, 12, tzinfo=UTC)
    policy = ArrivalPolicy(
        policy_id="arrival.benchmark",
        version="v1",
        maximum_location_age_seconds=30,
        maximum_accuracy_meters=30,
        maximum_stationary_speed_cm_per_second=100,
        minimum_stationary_seconds=20,
        minimum_pickup_confidence_bps=8000,
        minimum_map_confidence_bps=8000,
        minimum_verification_confidence_bps=8000,
    )
    signals = ArrivalSignals(
        observation=LocationObservation(
            observed_at=now,
            sequence=1,
            latitude_e6=9_005_000,
            longitude_e6=38_763_000,
            accuracy_meters=5,
            speed_cm_per_second=0,
            heading_degrees=90,
        ),
        approved_pickup_place_id="place.addis.bole",
        pickup_recommendation_id=uuid4(),
        pickup_recommendation_version="v1",
        pickup_zone_id="zone.bole.gate_1",
        inside_pickup_zone=True,
        pickup_confidence_bps=9500,
        map_confidence_bps=9000,
        seconds_stationary=30,
        approach_consistent=True,
        heading_reliable=True,
        accessible_pickup=True,
        operationally_available=True,
    )
    ride_id, assignment_id = uuid4(), uuid4()
    started = perf_counter()
    for _ in range(5_000):
        evaluate_arrival(ride_id, assignment_id, signals, policy, now=now)
    elapsed = perf_counter() - started
    assert elapsed < 2.5
