from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext
from functools import lru_cache

from BACKEND.marketplace.models import (
    CancellationAttribution,
    CancellationCause,
    CancellationEvidence,
    CancellationParty,
    DataQuality,
    DelayEvidence,
    DelayProtection,
    DemandForecast,
    DriverOpportunity,
    MarketplaceRecommendation,
    MarketplaceRuleSet,
    MarketplaceSnapshot,
    OpportunityAdjustment,
    RecommendationType,
    ScoreComponent,
    SignalKind,
)

MAX_BPS = 10_000


def _clamp(value: int, low: int = 0, high: int = MAX_BPS) -> int:
    return max(low, min(high, value))


def _ratio_score(good: int, total: int) -> int:
    if total <= 0:
        return 0
    return _clamp((good * MAX_BPS) // total)


def _inverse_threshold_score(value: int, healthy_threshold: int) -> int:
    if value <= healthy_threshold:
        return MAX_BPS
    return _clamp((healthy_threshold * MAX_BPS) // max(value, 1))


def _weighted_geometric_health(
    components: tuple[ScoreComponent, ...], rules: MarketplaceRuleSet
) -> int:
    if any(item.score_bps == 0 for item in components):
        return 0
    with localcontext() as context:
        context.prec = 50
        product = Decimal(1)
        for item in components:
            product *= _weighted_factor(
                item.score_bps, rules.component_weights_bps[item.code]
            )
        return _clamp(
            int(
                (product * Decimal(MAX_BPS)).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
        )


@lru_cache(maxsize=65_536)
def _weighted_factor(score_bps: int, weight_bps: int) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        normalized = Decimal(score_bps) / Decimal(MAX_BPS)
        weight = Decimal(weight_bps) / Decimal(MAX_BPS)
        return normalized**weight


def rider_satisfaction_score(
    snapshot: MarketplaceSnapshot, rules: MarketplaceRuleSet
) -> ScoreComponent:
    assignment = _ratio_score(snapshot.assigned_count, snapshot.request_count)
    wait = _inverse_threshold_score(
        snapshot.pickup_wait_p90_seconds, rules.healthy_wait_seconds
    )
    rider_cancellation = MAX_BPS - _ratio_score(
        snapshot.rider_cancel_count, snapshot.request_count
    )
    score = (assignment * 45 + wait * 35 + rider_cancellation * 20) // 100
    reasons = ["assignment_reliability", "pickup_wait", "rider_cancellation"]
    if snapshot.pickup_wait_p90_seconds > rules.healthy_wait_seconds:
        reasons.append("pickup_wait_breached")
    return ScoreComponent(
        code="rider_reliability", score_bps=score, reason_codes=tuple(reasons)
    )


def driver_fairness_score(
    snapshot: MarketplaceSnapshot, rules: MarketplaceRuleSet
) -> ScoreComponent:
    del rules
    if snapshot.opportunity_median_minor == 0:
        parity = MAX_BPS if snapshot.opportunity_bottom_decile_minor == 0 else 0
    else:
        parity = _ratio_score(
            snapshot.opportunity_bottom_decile_minor,
            snapshot.opportunity_median_minor,
        )
    idle = _inverse_threshold_score(
        snapshot.driver_idle_p50_seconds,
        max(snapshot.driver_deadhead_p50_seconds, 1) * 3,
    )
    score = (parity * 70 + idle * 30) // 100
    return ScoreComponent(
        code="driver_fairness",
        score_bps=score,
        reason_codes=("cohort_opportunity_parity", "idle_time_balance"),
    )


def marketplace_efficiency_score(
    snapshot: MarketplaceSnapshot, rules: MarketplaceRuleSet
) -> ScoreComponent:
    no_driver_bps = _ratio_score(snapshot.no_driver_count, snapshot.request_count)
    supply = _ratio_score(snapshot.eligible_driver_count, snapshot.online_driver_count)
    no_driver_score = MAX_BPS - min(
        MAX_BPS, (no_driver_bps * MAX_BPS) // max(rules.healthy_no_driver_bps, 1)
    )
    score = (no_driver_score * 60 + supply * 40) // 100
    return ScoreComponent(
        code="marketplace_efficiency",
        score_bps=score,
        reason_codes=("no_driver_outcome", "eligible_supply"),
    )


def business_sustainability_score(snapshot: MarketplaceSnapshot) -> ScoreComponent:
    score = MAX_BPS if snapshot.estimated_contribution_minor >= 0 else 0
    return ScoreComponent(
        code="business_sustainability",
        score_bps=score,
        reason_codes=(
            "nonnegative_contribution"
            if score == MAX_BPS
            else "negative_contribution_review",
        ),
    )


def predict_demand(
    snapshot: MarketplaceSnapshot,
    rules: MarketplaceRuleSet,
) -> DemandForecast:
    active = sorted(
        (
            signal
            for signal in snapshot.signals
            if signal.observed_at <= snapshot.window_ended_at < signal.expires_at
        ),
        key=lambda item: (item.kind, item.code, str(item.signal_id)),
    )
    factor = MAX_BPS
    context_codes: list[str] = []
    for signal in active:
        confidence_adjusted = MAX_BPS + (
            (signal.factor_bps - MAX_BPS) * signal.confidence_bps // MAX_BPS
        )
        factor = factor * confidence_adjusted // MAX_BPS
        factor = min(factor, rules.demand_signal_cap_bps)
        context_codes.extend((signal.kind.value, signal.code))
    expected = snapshot.forecast_baseline_requests * factor // MAX_BPS
    lower = expected * rules.demand_lower_band_bps // MAX_BPS
    upper = expected * rules.demand_upper_band_bps // MAX_BPS
    quality = (
        DataQuality.SUFFICIENT
        if snapshot.sample_size >= rules.minimum_sample_size
        else DataQuality.INSUFFICIENT
    )
    return DemandForecast(
        expected_requests=expected,
        lower_requests=lower,
        upper_requests=upper,
        factor_bps=factor,
        context_codes=tuple(context_codes),
        quality=quality,
    )


def balance_driver_opportunities(
    opportunities: list[DriverOpportunity], rules: MarketplaceRuleSet
) -> list[OpportunityAdjustment]:
    if not opportunities:
        return []
    fastest = min(item.pickup_eta_seconds for item in opportunities)
    comparable = [
        item
        for item in opportunities
        if item.pickup_eta_seconds <= fastest + rules.opportunity_equivalent_eta_seconds
    ]
    normalized = [
        item.offered_earnings_minor * 3_600 // max(item.eligible_online_seconds, 1)
        for item in comparable
    ]
    target = sorted(normalized)[len(normalized) // 2]
    results: list[OpportunityAdjustment] = []
    for item, hourly in zip(comparable, normalized, strict=True):
        deficit = max(0, target - hourly)
        credit = (
            min(rules.opportunity_maximum_credit_bps, deficit * MAX_BPS // target)
            if target > 0
            else 0
        )
        neutral = item.completed_trips < rules.neutral_driver_completed_trip_threshold
        reasons = ["materially_equivalent_pickup"]
        if neutral:
            reasons.append("neutral_new_driver")
        if credit:
            reasons.append("bounded_opportunity_credit")
        results.append(
            OpportunityAdjustment(
                driver_id=item.driver_id,
                credit_bps=credit,
                neutral_reputation=neutral,
                reason_codes=tuple(reasons),
            )
        )
    return sorted(results, key=lambda item: (-item.credit_bps, str(item.driver_id)))


def balance_driver_idle_time(
    opportunities: list[DriverOpportunity], rules: MarketplaceRuleSet
) -> list[OpportunityAdjustment]:
    """Bounded idle-time credit, restricted to equivalent pickup candidates."""
    if not opportunities:
        return []
    fastest = min(item.pickup_eta_seconds for item in opportunities)
    comparable = [
        item
        for item in opportunities
        if item.pickup_eta_seconds <= fastest + rules.opportunity_equivalent_eta_seconds
    ]
    maximum_idle = max((item.idle_seconds for item in comparable), default=0)
    return sorted(
        (
            OpportunityAdjustment(
                driver_id=item.driver_id,
                credit_bps=(
                    min(
                        rules.opportunity_maximum_credit_bps,
                        item.idle_seconds
                        * rules.opportunity_maximum_credit_bps
                        // maximum_idle,
                    )
                    if maximum_idle
                    else 0
                ),
                neutral_reputation=(
                    item.completed_trips < rules.neutral_driver_completed_trip_threshold
                ),
                reason_codes=("materially_equivalent_pickup", "bounded_idle_credit"),
            )
            for item in comparable
        ),
        key=lambda item: (-item.credit_bps, str(item.driver_id)),
    )


def attribute_cancellation(evidence: CancellationEvidence) -> CancellationAttribution:
    if evidence.external_signal_confidence_bps >= 7_000:
        return CancellationAttribution(
            responsible_party=CancellationParty.EXTERNAL,
            cause=CancellationCause.EXTERNAL_DISRUPTION,
            protected_from_driver_penalty=True,
            reason_codes=("verified_external_disruption",),
        )
    if evidence.communication_failed:
        return CancellationAttribution(
            responsible_party=CancellationParty.PLATFORM,
            cause=CancellationCause.COMMUNICATION_FAILURE,
            protected_from_driver_penalty=True,
            reason_codes=("platform_communication_failure",),
        )
    if evidence.pickup_ambiguous:
        return CancellationAttribution(
            responsible_party=CancellationParty.PLATFORM,
            cause=CancellationCause.PICKUP_AMBIGUITY,
            protected_from_driver_penalty=True,
            reason_codes=("pickup_ambiguity",),
        )
    if evidence.eta_error_seconds > 120:
        return CancellationAttribution(
            responsible_party=CancellationParty.PLATFORM,
            cause=CancellationCause.ETA_MISS,
            protected_from_driver_penalty=True,
            reason_codes=("material_eta_miss",),
        )
    if evidence.cancelled_by is CancellationParty.RIDER:
        return CancellationAttribution(
            responsible_party=CancellationParty.RIDER,
            cause=CancellationCause.RIDER_CHANGED_PLAN,
            protected_from_driver_penalty=True,
            reason_codes=(evidence.rider_reason or "rider_cancelled",),
        )
    if evidence.cancelled_by is CancellationParty.DRIVER:
        return CancellationAttribution(
            responsible_party=CancellationParty.DRIVER,
            cause=CancellationCause.DRIVER_AVOIDABLE,
            protected_from_driver_penalty=False,
            reason_codes=(evidence.driver_reason or "driver_cancelled",),
        )
    return CancellationAttribution(
        responsible_party=CancellationParty.UNKNOWN,
        cause=CancellationCause.UNKNOWN,
        protected_from_driver_penalty=True,
        reason_codes=("insufficient_attribution_evidence",),
    )


def protect_external_delay(
    evidence: DelayEvidence, rules: MarketplaceRuleSet
) -> DelayProtection:
    delay = max(0, evidence.actual_seconds - evidence.expected_seconds)
    protected = evidence.platform_route_failure or (
        evidence.signal_kind
        in {SignalKind.TRAFFIC, SignalKind.WEATHER, SignalKind.EVENT}
        and evidence.confidence_bps >= rules.external_delay_minimum_confidence_bps
    )
    reasons: tuple[str, ...]
    if evidence.platform_route_failure:
        reasons = ("platform_route_failure",)
    elif protected:
        reasons = ("external_delay_protected", evidence.signal_kind.value)  # type: ignore[union-attr]
    else:
        reasons = ("external_delay_unverified",)
    return DelayProtection(
        protected=protected,
        protected_seconds=delay if protected else 0,
        reason_codes=reasons,
    )


class DeterministicMarketplaceStrategy:
    def evaluate(
        self, snapshot: MarketplaceSnapshot, rules: MarketplaceRuleSet
    ) -> MarketplaceRecommendation:
        components = (
            rider_satisfaction_score(snapshot, rules),
            driver_fairness_score(snapshot, rules),
            marketplace_efficiency_score(snapshot, rules),
            business_sustainability_score(snapshot),
        )
        health = _weighted_geometric_health(components, rules)
        forecast = predict_demand(snapshot, rules)
        quality = (
            DataQuality.SUFFICIENT
            if snapshot.sample_size >= rules.minimum_sample_size
            else DataQuality.INSUFFICIENT
        )
        active_emergency = any(
            item.emergency
            and item.observed_at <= snapshot.window_ended_at < item.expires_at
            for item in snapshot.signals
        )
        supply_ratio = _ratio_score(
            snapshot.eligible_driver_count, max(forecast.expected_requests, 1)
        )
        wait_pressure = (
            snapshot.pickup_wait_p90_seconds
            * MAX_BPS
            // max(rules.healthy_wait_seconds, 1)
        )
        reasons: tuple[str, ...]
        if quality is DataQuality.INSUFFICIENT:
            recommendation = RecommendationType.INSUFFICIENT_DATA
            reasons = ("minimum_sample_not_met",)
        elif active_emergency and rules.emergency_surge_suppressed:
            recommendation = RecommendationType.SUPPRESS
            reasons = ("emergency_price_review_suppressed",)
        elif (
            supply_ratio < rules.surge_supply_ratio_bps
            and wait_pressure >= rules.surge_wait_pressure_bps
        ):
            recommendation = RecommendationType.PRICE_REVIEW
            reasons = ("supply_shortage", "pickup_wait_pressure", "advisory_only")
        elif supply_ratio < rules.surge_supply_ratio_bps:
            recommendation = RecommendationType.SUPPLY_GUIDANCE
            reasons = ("supply_shortage", "advisory_only")
        else:
            recommendation = RecommendationType.NO_CHANGE
            reasons = ("market_within_configured_bands",)
        generated = snapshot.window_ended_at
        return MarketplaceRecommendation(
            snapshot_id=snapshot.snapshot_id,
            rule_set_id=rules.rule_set_id,
            rule_version=rules.version,
            generated_at=generated,
            expires_at=generated + timedelta(seconds=rules.recommendation_ttl_seconds),
            health_score_bps=health,
            components=components,
            demand_forecast=forecast,
            recommendation=recommendation,
            reason_codes=reasons,
            quality=quality,
        )


def score_decimal(score_bps: int) -> Decimal:
    return (Decimal(score_bps) / Decimal(MAX_BPS)).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
