from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import uuid4

from BACKEND.scheduled.engine import DeterministicScheduledStrategy
from BACKEND.scheduled.models import (
    ReservationPolicy,
    ReservationState,
    ScheduledCandidate,
    ScheduledReservation,
)


def test_scheduled_ranking_10000_candidates_under_characterization_budget():
    now = datetime(2026, 7, 16, 12, tzinfo=UTC)
    policy = ReservationPolicy(version="scheduled.v1")
    reservation = ScheduledReservation(
        booker_id=uuid4(),
        passenger_participant_id=uuid4(),
        pickup_place_id="place.addis.bole",
        destination_place_id="place.addis.saris",
        service_type="ayo.go",
        quote_id=uuid4(),
        requested_pickup_at=now + timedelta(days=1),
        requested_timezone="Africa/Addis_Ababa",
        state=ReservationState.PLANNING,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        created_at=now,
        updated_at=now,
    )
    candidates = [
        ScheduledCandidate(
            driver_id=uuid4(),
            eligible=True,
            safety_eligible=True,
            pickup_eta_low_seconds=120,
            pickup_eta_high_seconds=240 + index % 60,
            pickup_window_success_bps=9000,
            recovery_capacity_bps=8500,
            prediction_confidence_bps=9000,
            location_observed_at=now,
        )
        for index in range(10_000)
    ]
    started = perf_counter()
    result = DeterministicScheduledStrategy(policy).rank(
        reservation, candidates, now=now
    )
    elapsed_ms = (perf_counter() - started) * 1000
    assert len(result) == 10_000
    # Local regression budget, deliberately not represented as a production SLO.
    assert elapsed_ms < 500
