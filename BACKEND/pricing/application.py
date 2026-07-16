import re
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.pricing.engine import PricingConflict, build_lineage, calculate
from BACKEND.pricing.models import (
    CalculationState,
    EstimateAcceptance,
    FareCalculation,
    FareEstimate,
    FinancialJourney,
    FinancialTraceability,
    PricingPolicy,
    PricingPolicyStatus,
    RouteMetrics,
)


class PricingApplication:
    def __init__(
        self,
        composition: PostgresRepositoryComposition,
        *,
        maximum_metrics_age_seconds: int = 300,
        estimate_ttl_seconds: int = 300,
    ) -> None:
        self._composition = composition
        self._maximum_metrics_age_seconds = maximum_metrics_age_seconds
        self._estimate_ttl_seconds = estimate_ttl_seconds

    def create_policy(
        self, subject: AuthorizationSubject, policy: PricingPolicy
    ) -> PricingPolicy:
        self._policy_operator(subject)
        if policy.made_by_identity_id != subject.identity_id:
            raise PricingConflict("caller_supplied_maker_rejected")
        with self._composition.unit_of_work() as unit:
            return unit.pricing.add_policy(policy)

    def approve_policy(
        self, subject: AuthorizationSubject, policy_id: UUID, *, at: datetime
    ) -> PricingPolicy:
        self._policy_operator(subject)
        with self._composition.unit_of_work() as unit:
            return unit.pricing.approve_policy(policy_id, subject.identity_id, at=at)

    def publish_policy(
        self, subject: AuthorizationSubject, policy_id: UUID, *, at: datetime
    ) -> PricingPolicy:
        self._policy_operator(subject)
        with self._composition.unit_of_work() as unit:
            return unit.pricing.publish_policy(policy_id, subject.identity_id, at=at)

    def estimate(
        self,
        subject: AuthorizationSubject,
        *,
        ride_request_id: UUID,
        policy_id: UUID,
        metrics: RouteMetrics,
        idempotency_key: str,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> FareEstimate:
        if subject.identity_type is not IdentityType.RIDER:
            raise PricingConflict("access_denied")
        self._key(idempotency_key)
        self._fresh(metrics, at)
        candidate_id = uuid4()
        with self._composition.unit_of_work() as unit:
            canonical = unit.pricing.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="estimate",
                key=idempotency_key,
                payload={
                    "ride_request_id": str(ride_request_id),
                    "policy_id": str(policy_id),
                    "metrics": metrics.model_dump(mode="json"),
                },
                response_reference=candidate_id,
                at=at,
            )
            existing = unit.pricing.get_estimate(canonical)
            if existing is not None:
                return existing
            source = unit.pricing.ride_request_source(ride_request_id)
            policy = unit.pricing.get_policy(policy_id)
            if (
                source is None
                or source["rider_identity_id"] != subject.identity_id
                or source["state"] != "ready_for_dispatch"
                or source["service_type"] != "immediate_standard"
                or source["payment_intent"] != "cash_compatible"
                or source["service_zone_id"] is None
            ):
                raise PricingConflict("ride_request_not_priceable")
            policy = self._published_policy(policy, source["service_zone_id"], at)
            breakdown = calculate(policy, metrics)
            audit_reference = uuid4()
            estimate = FareEstimate(
                estimate_id=canonical,
                ride_request_id=ride_request_id,
                rider_identity_id=subject.identity_id,
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                service_zone_id=source["service_zone_id"],
                service_type="immediate_standard",
                metrics=metrics,
                breakdown=breakdown,
                financial_traceability=FinancialTraceability(
                    ride_request_id=ride_request_id,
                    fare_estimate_id=canonical,
                ),
                calculation_lineage=build_lineage(
                    policy,
                    metrics,
                    breakdown,
                    audit_event_id=audit_reference,
                    correlation_id=correlation_id,
                    causation_id=causation_id,
                ),
                expires_at=at + timedelta(seconds=self._estimate_ttl_seconds),
                created_at=at,
                reason_codes=("pricing.static_policy_applied",),
                translation_keys=("pricing.estimate.created",),
                audit_reference=audit_reference,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )
            return unit.pricing.add_estimate(estimate)

    def accept(
        self,
        subject: AuthorizationSubject,
        estimate_id: UUID,
        *,
        idempotency_key: str,
        at: datetime,
    ) -> EstimateAcceptance:
        if subject.identity_type is not IdentityType.RIDER:
            raise PricingConflict("access_denied")
        self._key(idempotency_key)
        candidate_id = uuid4()
        with self._composition.unit_of_work() as unit:
            canonical = unit.pricing.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="accept_estimate",
                key=idempotency_key,
                payload={"estimate_id": str(estimate_id)},
                response_reference=candidate_id,
                at=at,
            )
            estimate = unit.pricing.get_estimate(estimate_id)
            if estimate is None or estimate.rider_identity_id != subject.identity_id:
                raise PricingConflict("estimate_not_found")
            existing = unit.pricing.get_acceptance_for_estimate(estimate_id)
            if existing is not None:
                if existing.acceptance_id != canonical:
                    raise PricingConflict("estimate_already_accepted")
                return existing
            if at >= estimate.expires_at:
                raise PricingConflict("estimate_expired")
            acceptance = EstimateAcceptance(
                acceptance_id=canonical,
                estimate_id=estimate_id,
                rider_identity_id=subject.identity_id,
                accepted_policy_version=estimate.policy_version,
                accepted_amount_minor=estimate.breakdown.rider_total_minor,
                currency=estimate.breakdown.currency,
                accepted_at=at,
                idempotency_key=idempotency_key,
                audit_reference=uuid4(),
            )
            return unit.pricing.add_acceptance(acceptance, estimate)

    def final_calculation(
        self,
        subject: AuthorizationSubject,
        *,
        ride_id: UUID,
        estimate_id: UUID,
        metrics: RouteMetrics,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> FareCalculation:
        if subject.identity_type is not IdentityType.SERVICE:
            raise PricingConflict("access_denied")
        self._key(idempotency_key)
        self._fresh(metrics, at)
        candidate_id = uuid4()
        with self._composition.unit_of_work() as unit:
            canonical = unit.pricing.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="final_calculation",
                key=idempotency_key,
                payload={
                    "ride_id": str(ride_id),
                    "estimate_id": str(estimate_id),
                    "metrics": metrics.model_dump(mode="json"),
                },
                response_reference=candidate_id,
                at=at,
            )
            existing = unit.pricing.get_calculation(canonical)
            if existing is not None:
                return existing
            estimate = unit.pricing.get_estimate(estimate_id)
            acceptance = unit.pricing.get_acceptance_for_estimate(estimate_id)
            ride = unit.pricing.active_ride_source(ride_id, lock=True)
            if (
                estimate is None
                or acceptance is None
                or ride is None
                or ride["state"] != "completed"
                or ride["service_type"] != "immediate_standard"
                or ride["ride_request_id"] != estimate.ride_request_id
                or ride["rider_id"] != estimate.rider_identity_id
                or ride["driver_id"] is None
                or ride["dispatch_handoff_id"] is None
                or ride["assignment_id"] is None
            ):
                raise PricingConflict("completed_canonical_ride_required")
            policy = unit.pricing.get_policy(estimate.policy_id)
            if (
                policy is None
                or policy.policy_version != acceptance.accepted_policy_version
            ):
                raise PricingConflict("accepted_policy_unavailable")
            breakdown = calculate(policy, metrics)
            difference = breakdown.rider_total_minor - acceptance.accepted_amount_minor
            audit_reference = uuid4()
            item = FareCalculation(
                calculation_id=canonical,
                estimate_id=estimate_id,
                acceptance_id=acceptance.acceptance_id,
                ride_id=ride_id,
                rider_identity_id=estimate.rider_identity_id,
                driver_identity_id=ride["driver_id"],
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                state=CalculationState.FINAL_CALCULATED,
                metrics=metrics,
                breakdown=breakdown,
                financial_traceability=FinancialTraceability(
                    ride_request_id=estimate.ride_request_id,
                    dispatch_handoff_id=ride["dispatch_handoff_id"],
                    assignment_id=ride["assignment_id"],
                    active_ride_id=ride_id,
                    fare_estimate_id=estimate_id,
                    fare_calculation_id=canonical,
                ),
                calculation_lineage=build_lineage(
                    policy,
                    metrics,
                    breakdown,
                    audit_event_id=audit_reference,
                    correlation_id=correlation_id,
                    causation_id=estimate_id,
                ),
                estimate_difference_minor=difference,
                reason_codes=(
                    "pricing.final_matches_estimate"
                    if difference == 0
                    else "pricing.final_inputs_changed",
                ),
                translation_keys=("pricing.final.calculated",),
                audit_reference=audit_reference,
                calculated_at=at,
                settlement_instruction_ready=False,
            )
            return unit.pricing.add_calculation(item, correlation_id)

    def correct_calculation(
        self,
        subject: AuthorizationSubject,
        *,
        predecessor_calculation_id: UUID,
        metrics: RouteMetrics,
        reason_code: str,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> FareCalculation:
        self._policy_operator(subject)
        self._key(idempotency_key)
        self._fresh(metrics, at)
        if re.fullmatch(r"[a-z][a-z0-9_.-]{1,62}", reason_code) is None:
            raise PricingConflict("reason_code_invalid")
        candidate_id = uuid4()
        with self._composition.unit_of_work() as unit:
            canonical = unit.pricing.reserve_idempotency(
                actor_id=subject.identity_id,
                operation="correct_calculation",
                key=idempotency_key,
                payload={
                    "predecessor_calculation_id": str(predecessor_calculation_id),
                    "metrics": metrics.model_dump(mode="json"),
                    "reason_code": reason_code,
                },
                response_reference=candidate_id,
                at=at,
            )
            existing = unit.pricing.get_calculation(canonical)
            if existing is not None:
                return existing
            prior = unit.pricing.get_calculation(predecessor_calculation_id)
            if prior is None:
                raise PricingConflict("calculation_not_found")
            policy = unit.pricing.get_policy(prior.policy_id)
            if policy is None or policy.policy_version != prior.policy_version:
                raise PricingConflict("calculation_policy_unavailable")
            breakdown = calculate(policy, metrics)
            audit_reference = uuid4()
            corrected = FareCalculation(
                calculation_id=canonical,
                estimate_id=prior.estimate_id,
                acceptance_id=prior.acceptance_id,
                ride_id=prior.ride_id,
                rider_identity_id=prior.rider_identity_id,
                driver_identity_id=prior.driver_identity_id,
                policy_id=prior.policy_id,
                policy_version=prior.policy_version,
                state=CalculationState.CORRECTED,
                metrics=metrics,
                breakdown=breakdown,
                financial_traceability=FinancialTraceability(
                    ride_request_id=prior.financial_traceability.ride_request_id,
                    dispatch_handoff_id=(
                        prior.financial_traceability.dispatch_handoff_id
                    ),
                    assignment_id=prior.financial_traceability.assignment_id,
                    active_ride_id=prior.financial_traceability.active_ride_id,
                    fare_estimate_id=prior.financial_traceability.fare_estimate_id,
                    fare_calculation_id=canonical,
                    predecessor_fare_calculation_id=prior.calculation_id,
                ),
                calculation_lineage=build_lineage(
                    policy,
                    metrics,
                    breakdown,
                    audit_event_id=audit_reference,
                    correlation_id=correlation_id,
                    causation_id=predecessor_calculation_id,
                ),
                estimate_difference_minor=prior.estimate_difference_minor
                + breakdown.rider_total_minor
                - prior.breakdown.rider_total_minor,
                predecessor_calculation_id=prior.calculation_id,
                reason_codes=(reason_code,),
                translation_keys=("pricing.final.corrected",),
                audit_reference=audit_reference,
                calculated_at=at,
                settlement_instruction_ready=False,
            )
            return unit.pricing.add_calculation(corrected, correlation_id)

    def financial_journey(
        self, subject: AuthorizationSubject, ride_id: UUID, *, at: datetime
    ) -> FinancialJourney:
        with self._composition.unit_of_work() as unit:
            if not unit.authorization.has_permission(
                subject.identity_id, "pricing.trace.read", at=at
            ):
                raise PricingConflict("financial_journey_not_found")
            journey = unit.pricing.financial_journey(ride_id)
            if journey is None:
                raise PricingConflict("financial_journey_not_found")
            return journey

    @staticmethod
    def rider_breakdown(
        subject: AuthorizationSubject, item: FareEstimate | FareCalculation
    ) -> dict[str, Any]:
        if (
            subject.identity_type is not IdentityType.RIDER
            or subject.identity_id != item.rider_identity_id
        ):
            raise PricingConflict("pricing_record_not_found")
        return {
            "currency": item.breakdown.currency,
            "total_minor": item.breakdown.rider_total_minor,
            "base_minor": item.breakdown.base_minor,
            "distance_minor": item.breakdown.distance_minor,
            "time_minor": item.breakdown.time_minor,
            "minimum_adjustment_minor": item.breakdown.minimum_adjustment_minor,
            "tax_placeholder_minor": item.breakdown.tax_placeholder_minor,
            "policy_version": item.policy_version,
            "reason_codes": item.reason_codes,
            "translation_keys": (*item.translation_keys, "pricing.support.appeal"),
        }

    @staticmethod
    def driver_breakdown(
        subject: AuthorizationSubject, item: FareCalculation
    ) -> dict[str, Any]:
        if (
            subject.identity_type is not IdentityType.DRIVER
            or subject.identity_id != item.driver_identity_id
        ):
            raise PricingConflict("pricing_record_not_found")
        return {
            "currency": item.breakdown.currency,
            "fare_basis_minor": item.breakdown.driver_gross_minor,
            "distance_minor": item.breakdown.distance_minor,
            "time_minor": item.breakdown.time_minor,
            "approved_extras_minor": 0,
            "gross_minor": item.breakdown.driver_gross_minor,
            "ayo_commission_minor": item.breakdown.ayo_commission_minor,
            "tax_deduction_placeholder_minor": 0,
            "projected_net_minor": item.breakdown.driver_net_projection_minor,
            "status": item.state.value,
            "policy_version": item.policy_version,
            "reason_codes": item.reason_codes,
            "translation_keys": item.translation_keys,
        }

    @staticmethod
    def cash_expectation(item: FareCalculation) -> dict[str, Any]:
        return {
            "currency": item.breakdown.currency,
            "amount_expected_minor": item.breakdown.rider_total_minor,
            "collection_status": "not_recorded",
            "reconciliation_status": "not_started",
            "translation_key": "pricing.cash.amount_expected",
        }

    def _fresh(self, metrics: RouteMetrics, at: datetime) -> None:
        age = (at - metrics.observed_at).total_seconds()
        if age < 0 or age > self._maximum_metrics_age_seconds:
            raise PricingConflict("route_metrics_stale")

    @staticmethod
    def _key(value: str) -> None:
        if not 16 <= len(value) <= 128:
            raise PricingConflict("idempotency_key_invalid")

    @staticmethod
    def _published_policy(
        policy: PricingPolicy | None, service_zone_id: UUID, at: datetime
    ) -> PricingPolicy:
        if (
            policy is None
            or policy.status is not PricingPolicyStatus.PUBLISHED
            or policy.service_zone_id != service_zone_id
            or policy.effective_from > at
            or (policy.effective_until is not None and policy.effective_until <= at)
        ):
            raise PricingConflict("published_policy_required")
        return policy

    @staticmethod
    def _policy_operator(subject: AuthorizationSubject) -> None:
        if subject.identity_type not in {
            IdentityType.STAFF,
            IdentityType.ADMINISTRATOR,
        }:
            raise PricingConflict("access_denied")
