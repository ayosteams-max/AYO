import hashlib
from datetime import datetime, timedelta
from uuid import UUID

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.booking.models import BookingQuote
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.pricing.application import PricingApplication
from BACKEND.pricing.engine import calculate
from BACKEND.pricing.models import RouteMetrics


class BookingPricingApplication:
    """Pricing-owned adapter for pre-confirmation route evidence."""

    def __init__(
        self,
        composition: PostgresRepositoryComposition,
        *,
        quote_ttl_seconds: int = 300,
        maximum_metrics_age_seconds: int = 300,
    ) -> None:
        self._composition = composition
        self._quote_ttl_seconds = quote_ttl_seconds
        self._maximum_metrics_age_seconds = maximum_metrics_age_seconds

    def quote(
        self,
        *,
        policy_id: UUID,
        service_zone_id: UUID,
        metrics: RouteMetrics,
        at: datetime,
    ) -> BookingQuote:
        age = (at - metrics.observed_at).total_seconds()
        if age < 0 or age > self._maximum_metrics_age_seconds:
            raise ValueError("route_evidence_stale")
        with self._composition.unit_of_work() as unit:
            policy = PricingApplication._published_policy(
                unit.pricing.get_policy(policy_id), service_zone_id, at
            )
            return BookingQuote(
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                breakdown=calculate(policy, metrics),
                expires_at=at + timedelta(seconds=self._quote_ttl_seconds),
            )

    def establish_canonical_lineage(
        self,
        *,
        subject: AuthorizationSubject,
        ride_request_id: UUID,
        policy_id: UUID,
        metrics: RouteMetrics,
        idempotency_key: str,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ):
        pricing = PricingApplication(
            self._composition,
            maximum_metrics_age_seconds=self._maximum_metrics_age_seconds,
            estimate_ttl_seconds=self._quote_ttl_seconds,
        )
        key_digest = hashlib.sha256(idempotency_key.encode()).hexdigest()
        estimate = pricing.estimate(
            subject,
            ride_request_id=ride_request_id,
            policy_id=policy_id,
            metrics=metrics,
            idempotency_key=f"booking-estimate-{key_digest}",
            correlation_id=correlation_id,
            causation_id=causation_id,
            at=at,
        )
        acceptance = pricing.accept(
            subject,
            estimate.estimate_id,
            idempotency_key=f"booking-acceptance-{key_digest}",
            at=at,
        )
        payload = ":".join(
            (
                str(ride_request_id),
                str(estimate.estimate_id),
                str(acceptance.acceptance_id),
                str(estimate.policy_id),
                estimate.policy_version,
                str(acceptance.accepted_amount_minor),
                acceptance.currency,
            )
        )
        return estimate, acceptance, hashlib.sha256(payload.encode()).hexdigest()
