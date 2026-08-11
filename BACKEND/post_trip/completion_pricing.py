from datetime import datetime
from typing import Protocol
from uuid import UUID

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.post_trip.engine import PostTripConflict
from BACKEND.post_trip.models import FinancialBreakdown
from BACKEND.pricing.application import PricingApplication
from BACKEND.pricing.models import RouteMetrics


class CompletionRouteMetricsProvider(Protocol):
    def completed_route_metrics(
        self, *, ride_id: UUID, route_evidence_id: str, at: datetime
    ) -> RouteMetrics: ...


class PostTripCompletionPricingAdapter:
    """Pricing-owned final-fare bridge; Post Trip never calculates a fare."""

    def __init__(
        self,
        composition: PostgresRepositoryComposition,
        pricing: PricingApplication,
        metrics: CompletionRouteMetricsProvider,
        service_subject: AuthorizationSubject,
    ) -> None:
        self._composition = composition
        self._pricing = pricing
        self._metrics = metrics
        self._service_subject = service_subject

    def final_breakdown(
        self,
        *,
        ride_id: UUID,
        booking_evidence_id: UUID,
        route_evidence_id: str,
        at: datetime,
    ) -> FinancialBreakdown:
        with self._composition.unit_of_work() as unit:
            ride = unit.active_rides.get(ride_id)
            if ride is None or ride.ride_request_id is None:
                raise PostTripConflict("completed_canonical_ride_required")
            confirmation = unit.booking.get_confirmation_for_ride_request(
                ride.ride_request_id
            )
            if (
                confirmation is None
                or confirmation.evidence_id != booking_evidence_id
                or confirmation.fare_estimate_id is None
                or confirmation.estimate_acceptance_id is None
                or confirmation.pricing_lineage_hash is None
            ):
                raise PostTripConflict("authoritative_pricing_lineage_missing")
            journey = unit.pricing.financial_journey(ride_id)
            if journey is not None and journey.fare_calculations:
                calculation = journey.fare_calculations[-1]
            else:
                calculation = None
        if calculation is None:
            route_metrics = self._metrics.completed_route_metrics(
                ride_id=ride_id, route_evidence_id=route_evidence_id, at=at
            )
            calculation = self._pricing.final_calculation(
                self._service_subject,
                ride_id=ride_id,
                estimate_id=confirmation.fare_estimate_id,
                metrics=route_metrics,
                idempotency_key=f"post-trip-final-pricing:{ride_id}",
                correlation_id=ride_id,
                at=at,
            )
        if (
            calculation.estimate_id != confirmation.fare_estimate_id
            or calculation.acceptance_id != confirmation.estimate_acceptance_id
            or calculation.ride_id != ride_id
        ):
            raise PostTripConflict("authoritative_pricing_lineage_conflict")
        b = calculation.breakdown
        return FinancialBreakdown(
            currency=b.currency,
            gross_fare_minor=b.rider_total_minor,
            commission_minor=b.ayo_commission_minor,
            taxes_minor=b.tax_placeholder_minor,
            adjustments_minor=0,
            net_driver_earnings_minor=b.driver_net_projection_minor,
            policy_version=calculation.policy_version,
            policy_evidence_hash=calculation.calculation_lineage.canonical_input_hash,
            fare_estimate_id=calculation.estimate_id,
            fare_calculation_id=calculation.calculation_id,
        )
