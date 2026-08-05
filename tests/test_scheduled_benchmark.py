import os
import platform
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from statistics import median
from time import perf_counter
from uuid import UUID, uuid4

from BACKEND.scheduled.engine import DeterministicScheduledStrategy
from BACKEND.scheduled.models import (
    ReservationPolicy,
    ReservationState,
    ScheduledCandidate,
    ScheduledReservation,
)

CHARACTERIZATION_TARGET_MS = 500
CHARACTERIZATION_RUNS = 5


def _reservation(*, now: datetime) -> ScheduledReservation:
    policy = ReservationPolicy(version="scheduled.v1")
    return ScheduledReservation(
        reservation_id=UUID("10000000-0000-4000-8000-000000000001"),
        booker_id=UUID("10000000-0000-4000-8000-000000000002"),
        passenger_participant_id=UUID("10000000-0000-4000-8000-000000000003"),
        pickup_place_id="place.addis.bole",
        destination_place_id="place.addis.saris",
        service_type="ayo.go",
        quote_id=UUID("10000000-0000-4000-8000-000000000004"),
        requested_pickup_at=now + timedelta(days=1),
        requested_timezone="Africa/Addis_Ababa",
        state=ReservationState.PLANNING,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        created_at=now,
        updated_at=now,
    )


def test_scheduled_ranking_is_deterministic_and_fail_closed() -> None:
    now = datetime(2026, 7, 16, 12, tzinfo=UTC)
    policy = ReservationPolicy(version="scheduled.v1")
    reservation = _reservation(now=now)
    candidates = [
        ScheduledCandidate(
            driver_id=UUID("20000000-0000-4000-8000-000000000003"),
            eligible=True,
            safety_eligible=True,
            pickup_eta_low_seconds=120,
            pickup_eta_high_seconds=240,
            pickup_window_success_bps=9000,
            recovery_capacity_bps=8500,
            prediction_confidence_bps=9000,
            location_observed_at=now,
        ),
        ScheduledCandidate(
            driver_id=UUID("20000000-0000-4000-8000-000000000001"),
            eligible=True,
            safety_eligible=True,
            pickup_eta_low_seconds=120,
            pickup_eta_high_seconds=240,
            pickup_window_success_bps=9000,
            recovery_capacity_bps=8500,
            prediction_confidence_bps=9000,
            location_observed_at=now,
        ),
        ScheduledCandidate(
            driver_id=UUID("20000000-0000-4000-8000-000000000002"),
            eligible=False,
            safety_eligible=True,
            pickup_eta_low_seconds=60,
            pickup_eta_high_seconds=90,
            pickup_window_success_bps=9900,
            recovery_capacity_bps=9900,
            prediction_confidence_bps=9900,
            location_observed_at=now,
        ),
    ]
    strategy = DeterministicScheduledStrategy(policy)

    first = strategy.rank(reservation, candidates, now=now)
    second = strategy.rank(reservation, list(reversed(candidates)), now=now)

    expected = [
        UUID("20000000-0000-4000-8000-000000000001"),
        UUID("20000000-0000-4000-8000-000000000003"),
    ]
    assert [item.driver_id for item in first] == expected
    assert [item.driver_id for item in second] == expected
    assert first == second
    assert all("eligible" in item.reason_codes for item in first)


def test_scheduled_ranking_10000_candidates_characterization(
    record_property: Callable[[str, object], None],
) -> None:
    now = datetime(2026, 7, 16, 12, tzinfo=UTC)
    policy = ReservationPolicy(version="scheduled.v1")
    reservation = _reservation(now=now)
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
    strategy = DeterministicScheduledStrategy(policy)
    samples_ms: list[float] = []
    for _ in range(CHARACTERIZATION_RUNS):
        started = perf_counter()
        result = strategy.rank(reservation, candidates, now=now)
        samples_ms.append((perf_counter() - started) * 1000)
        assert len(result) == 10_000

    median_ms = median(samples_ms)
    coverage_active = bool(
        os.environ.get("COVERAGE_RUN")
        or os.environ.get("COV_CORE_SOURCE")
        or sys.gettrace() is not None
    )
    record_property("benchmark_name", "scheduled_ranking_10000_candidates")
    record_property("target_ms", CHARACTERIZATION_TARGET_MS)
    record_property("samples_ms", ",".join(f"{sample:.3f}" for sample in samples_ms))
    record_property("median_ms", f"{median_ms:.3f}")
    record_property("coverage_instrumentation_active", str(coverage_active).lower())
    record_property("python_version", platform.python_version())
    record_property("platform", platform.platform())
    record_property("processor", platform.processor() or "unreported")

    # The 500 ms target remains characterization evidence. It is not a production
    # SLO or deterministic correctness assertion. A hard performance gate requires
    # a separately governed controlled job or another reproducible statistical rule.
    assert median_ms >= 0
