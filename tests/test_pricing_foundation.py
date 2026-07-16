from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.pricing.engine import build_lineage, calculate, reconstruct
from BACKEND.pricing.models import (
    DataQuality,
    PricingPolicy,
    PricingPolicyStatus,
    RouteMetrics,
)

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def policy(**changes) -> PricingPolicy:
    values = {
        "policy_version": "synthetic.v1",
        "service_zone_id": uuid4(),
        "service_type": "immediate_standard",
        "currency": "ETB",
        "base_fare_minor": 1000,
        "distance_rate_per_km_minor": 500,
        "time_rate_per_minute_minor": 200,
        "minimum_fare_minor": 1500,
        "commission_basis_points": 2000,
        "tax_placeholder_basis_points": 0,
        "rounding_increment_minor": 5,
        "effective_from": NOW - timedelta(days=1),
        "made_by_identity_id": uuid4(),
        "created_at": NOW,
    }
    values.update(changes)
    return PricingPolicy(**values)


def metrics(**changes) -> RouteMetrics:
    values = {
        "distance_meters": 1500,
        "duration_seconds": 630,
        "observed_at": NOW,
        "provider_id": "synthetic.route",
        "provider_version": "v1",
        "distance_source": "approved_route_metric",
        "duration_source": "approved_route_metric",
        "provenance_reference": "synthetic-approved-001",
        "data_quality": DataQuality.APPROVED_SYNTHETIC,
    }
    values.update(changes)
    return RouteMetrics(**values)


def test_integer_etb_calculation_is_deterministic_and_transparent() -> None:
    result = calculate(policy(), metrics())
    assert result.base_minor == 1000
    assert result.distance_minor == 750
    assert result.time_minor == 2100
    assert result.rider_total_minor == 3850
    assert result.driver_gross_minor == 3850
    assert result.ayo_commission_minor == 770
    assert result.driver_net_projection_minor == 3080
    assert calculate(policy(), metrics()) == result


def test_complete_lineage_reconstructs_every_financial_component() -> None:
    maker, checker, publisher = uuid4(), uuid4(), uuid4()
    approved = policy(
        made_by_identity_id=maker,
        approved_by_identity_id=checker,
        approved_at=NOW,
        published_by_identity_id=publisher,
        published_at=NOW,
        status=PricingPolicyStatus.PUBLISHED,
    )
    route = metrics()
    result = calculate(approved, route)
    audit, correlation, causation = uuid4(), uuid4(), uuid4()
    lineage = build_lineage(
        approved,
        route,
        result,
        audit_event_id=audit,
        correlation_id=correlation,
        causation_id=causation,
    )
    assert reconstruct(lineage) == result
    assert lineage.distance_source == "approved_route_metric"
    assert lineage.route_metric_provider_version == "v1"
    assert lineage.approved_by_identity_id == checker
    assert lineage.published_by_identity_id == publisher
    assert lineage.audit_event_id == audit
    assert lineage.raw_distance_denominator == 1000
    assert lineage.raw_time_denominator == 60
    assert lineage.rounding_increment_minor == 5
    assert (
        lineage.canonical_input_hash
        == build_lineage(
            approved,
            route,
            result,
            audit_event_id=uuid4(),
            correlation_id=uuid4(),
            causation_id=uuid4(),
        ).canonical_input_hash
    )


def test_minimum_fare_and_half_up_rounding_are_integer_only() -> None:
    result = calculate(
        policy(
            base_fare_minor=101, minimum_fare_minor=333, rounding_increment_minor=10
        ),
        metrics(distance_meters=1, duration_seconds=1),
    )
    assert result.minimum_adjustment_minor > 0
    assert result.driver_gross_minor == 330
    assert isinstance(result.rider_total_minor, int)


def test_float_money_currency_mixing_and_maker_checker_bypass_fail() -> None:
    with pytest.raises(ValidationError):
        policy(base_fare_minor=10.5)
    with pytest.raises(ValidationError):
        policy(currency="USD")
    maker = uuid4()
    with pytest.raises(ValidationError):
        policy(made_by_identity_id=maker, approved_by_identity_id=maker)


@pytest.mark.parametrize(
    "field,value",
    [("distance_meters", 0), ("duration_seconds", 0), ("distance_meters", 2_000_001)],
)
def test_unreasonable_route_metrics_fail_closed(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        metrics(**{field: value})
