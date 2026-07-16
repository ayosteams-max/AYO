import hashlib
import json
from uuid import UUID

from BACKEND.pricing.models import (
    CalculationLineage,
    DataQuality,
    FareBreakdown,
    PricingPolicy,
    PricingPolicyStatus,
    RouteMetrics,
)

FORMULA_VERSION = "static_etb_v1"


class PricingConflict(RuntimeError):
    pass


def _round_ratio(numerator: int, denominator: int) -> int:
    if numerator < 0 or denominator <= 0:
        raise PricingConflict("invalid_rounding_input")
    return (numerator + denominator // 2) // denominator


def _round_increment(value: int, increment: int) -> int:
    return _round_ratio(value, increment) * increment


def _input_hash(policy: PricingPolicy, metrics: RouteMetrics) -> str:
    inputs = {
        "formula_version": FORMULA_VERSION,
        "policy_id": str(policy.policy_id),
        "policy_version": policy.policy_version,
        "distance_meters": metrics.distance_meters,
        "duration_seconds": metrics.duration_seconds,
        "provider_id": metrics.provider_id,
        "provider_version": metrics.provider_version,
        "distance_source": metrics.distance_source,
        "duration_source": metrics.duration_source,
        "provenance_reference": metrics.provenance_reference,
        "observed_at": metrics.observed_at.isoformat(),
        "base_fare_minor": policy.base_fare_minor,
        "distance_rate_per_km_minor": policy.distance_rate_per_km_minor,
        "time_rate_per_minute_minor": policy.time_rate_per_minute_minor,
        "minimum_fare_minor": policy.minimum_fare_minor,
        "commission_basis_points": policy.commission_basis_points,
        "tax_placeholder_basis_points": policy.tax_placeholder_basis_points,
        "rounding_increment_minor": policy.rounding_increment_minor,
    }
    return hashlib.sha256(
        json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def calculate(policy: PricingPolicy, metrics: RouteMetrics) -> FareBreakdown:
    if policy.currency != "ETB" or policy.service_type != "immediate_standard":
        raise PricingConflict("unsupported_pricing_boundary")
    distance = _round_ratio(
        metrics.distance_meters * policy.distance_rate_per_km_minor, 1000
    )
    duration = _round_ratio(
        metrics.duration_seconds * policy.time_rate_per_minute_minor, 60
    )
    raw = policy.base_fare_minor + distance + duration
    minimum_adjustment = max(0, policy.minimum_fare_minor - raw)
    fare_before_tax = _round_increment(
        raw + minimum_adjustment, policy.rounding_increment_minor
    )
    tax = _round_ratio(fare_before_tax * policy.tax_placeholder_basis_points, 10_000)
    rider_total = fare_before_tax + tax
    commission = _round_ratio(fare_before_tax * policy.commission_basis_points, 10_000)
    if commission > fare_before_tax:
        raise PricingConflict("commission_exceeds_gross")
    return FareBreakdown(
        currency="ETB",
        base_minor=policy.base_fare_minor,
        distance_minor=distance,
        time_minor=duration,
        minimum_adjustment_minor=minimum_adjustment,
        tax_placeholder_minor=tax,
        rider_total_minor=rider_total,
        driver_gross_minor=fare_before_tax,
        ayo_commission_minor=commission,
        driver_net_projection_minor=fare_before_tax - commission,
    )


def build_lineage(
    policy: PricingPolicy,
    metrics: RouteMetrics,
    breakdown: FareBreakdown,
    *,
    audit_event_id: UUID,
    correlation_id: UUID,
    causation_id: UUID,
) -> CalculationLineage:
    if (
        policy.approved_by_identity_id is None
        or policy.approved_at is None
        or policy.published_by_identity_id is None
        or policy.published_at is None
    ):
        raise PricingConflict("complete_policy_approval_lineage_required")
    digest = _input_hash(policy, metrics)
    pre_minimum = breakdown.base_minor + breakdown.distance_minor + breakdown.time_minor
    return CalculationLineage(
        formula_version=FORMULA_VERSION,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        predecessor_policy_id=policy.predecessor_policy_id,
        made_by_identity_id=policy.made_by_identity_id,
        approved_by_identity_id=policy.approved_by_identity_id,
        approved_at=policy.approved_at,
        published_by_identity_id=policy.published_by_identity_id,
        published_at=policy.published_at,
        distance_meters=metrics.distance_meters,
        duration_seconds=metrics.duration_seconds,
        distance_source=metrics.distance_source,
        duration_source=metrics.duration_source,
        route_metric_provider_id=metrics.provider_id,
        route_metric_provider_version=metrics.provider_version,
        route_metric_provenance_reference=metrics.provenance_reference,
        route_metric_observed_at=metrics.observed_at,
        base_fare_minor=policy.base_fare_minor,
        distance_rate_per_km_minor=policy.distance_rate_per_km_minor,
        time_rate_per_minute_minor=policy.time_rate_per_minute_minor,
        minimum_fare_minor=policy.minimum_fare_minor,
        commission_basis_points=policy.commission_basis_points,
        tax_placeholder_basis_points=policy.tax_placeholder_basis_points,
        raw_distance_numerator=(
            metrics.distance_meters * policy.distance_rate_per_km_minor
        ),
        raw_distance_denominator=1000,
        raw_time_numerator=(
            metrics.duration_seconds * policy.time_rate_per_minute_minor
        ),
        raw_time_denominator=60,
        pre_minimum_minor=pre_minimum,
        minimum_adjustment_minor=breakdown.minimum_adjustment_minor,
        pre_rounding_minor=pre_minimum + breakdown.minimum_adjustment_minor,
        rounding_increment_minor=policy.rounding_increment_minor,
        rounded_fare_before_tax_minor=breakdown.driver_gross_minor,
        commission_numerator=(
            breakdown.driver_gross_minor * policy.commission_basis_points
        ),
        commission_denominator=10_000,
        tax_numerator=(
            breakdown.driver_gross_minor * policy.tax_placeholder_basis_points
        ),
        tax_denominator=10_000,
        canonical_input_hash=digest,
        audit_event_id=audit_event_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


def reconstruct(lineage: CalculationLineage) -> FareBreakdown:
    """Reproduce a result solely from its immutable lineage snapshot."""
    if lineage.formula_version != FORMULA_VERSION:
        raise PricingConflict("unsupported_formula_version")
    policy = PricingPolicy(
        policy_id=lineage.policy_id,
        policy_version=lineage.policy_version,
        predecessor_policy_id=lineage.predecessor_policy_id,
        service_zone_id=UUID(int=0),
        service_type="immediate_standard",
        currency="ETB",
        base_fare_minor=lineage.base_fare_minor,
        distance_rate_per_km_minor=lineage.distance_rate_per_km_minor,
        time_rate_per_minute_minor=lineage.time_rate_per_minute_minor,
        minimum_fare_minor=lineage.minimum_fare_minor,
        commission_basis_points=lineage.commission_basis_points,
        tax_placeholder_basis_points=lineage.tax_placeholder_basis_points,
        rounding_increment_minor=lineage.rounding_increment_minor,
        effective_from=lineage.published_at,
        status=PricingPolicyStatus.PUBLISHED,
        made_by_identity_id=lineage.made_by_identity_id,
        approved_by_identity_id=lineage.approved_by_identity_id,
        approved_at=lineage.approved_at,
        published_by_identity_id=lineage.published_by_identity_id,
        published_at=lineage.published_at,
        created_at=lineage.approved_at,
    )
    metrics = RouteMetrics(
        distance_meters=lineage.distance_meters,
        duration_seconds=lineage.duration_seconds,
        observed_at=lineage.route_metric_observed_at,
        provider_id=lineage.route_metric_provider_id,
        provider_version=lineage.route_metric_provider_version,
        distance_source=lineage.distance_source,
        duration_source=lineage.duration_source,
        provenance_reference=lineage.route_metric_provenance_reference,
        data_quality=DataQuality.VERIFIED,
    )
    if _input_hash(policy, metrics) != lineage.canonical_input_hash:
        raise PricingConflict("calculation_lineage_hash_mismatch")
    if (
        lineage.raw_distance_numerator
        != lineage.distance_meters * lineage.distance_rate_per_km_minor
        or lineage.raw_distance_denominator != 1000
        or lineage.raw_time_numerator
        != lineage.duration_seconds * lineage.time_rate_per_minute_minor
        or lineage.raw_time_denominator != 60
    ):
        raise PricingConflict("calculation_lineage_operand_mismatch")
    distance = _round_ratio(
        lineage.raw_distance_numerator, lineage.raw_distance_denominator
    )
    duration = _round_ratio(lineage.raw_time_numerator, lineage.raw_time_denominator)
    pre_minimum = lineage.base_fare_minor + distance + duration
    minimum_adjustment = max(0, lineage.minimum_fare_minor - pre_minimum)
    fare_before_tax = _round_increment(
        pre_minimum + minimum_adjustment, lineage.rounding_increment_minor
    )
    tax = _round_ratio(lineage.tax_numerator, lineage.tax_denominator)
    commission = _round_ratio(
        lineage.commission_numerator, lineage.commission_denominator
    )
    if (
        lineage.pre_minimum_minor != pre_minimum
        or lineage.minimum_adjustment_minor != minimum_adjustment
        or lineage.pre_rounding_minor != pre_minimum + minimum_adjustment
        or lineage.rounded_fare_before_tax_minor != fare_before_tax
        or lineage.commission_numerator
        != fare_before_tax * lineage.commission_basis_points
        or lineage.commission_denominator != 10_000
        or lineage.tax_numerator
        != fare_before_tax * lineage.tax_placeholder_basis_points
        or lineage.tax_denominator != 10_000
    ):
        raise PricingConflict("calculation_lineage_derivation_mismatch")
    return FareBreakdown(
        currency="ETB",
        base_minor=lineage.base_fare_minor,
        distance_minor=distance,
        time_minor=duration,
        minimum_adjustment_minor=minimum_adjustment,
        tax_placeholder_minor=tax,
        rider_total_minor=fare_before_tax + tax,
        driver_gross_minor=fare_before_tax,
        ayo_commission_minor=commission,
        driver_net_projection_minor=fare_before_tax - commission,
    )
