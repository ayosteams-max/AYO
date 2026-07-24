from datetime import datetime
from typing import Protocol
from uuid import UUID

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.pricing.application import PricingApplication
from BACKEND.pricing.models import FareEstimate, RouteMetrics


class MobileQuoteInputResolver(Protocol):
    """Server-owned inputs, stable for retries; mobile supplies no fare factors."""

    def resolve(
        self, *, ride_request_id: UUID, subject: AuthorizationSubject, at: datetime
    ) -> tuple[UUID, RouteMetrics]: ...


class MobileCashQuoteApplication:
    def __init__(
        self, pricing: PricingApplication, inputs: MobileQuoteInputResolver
    ) -> None:
        self._pricing = pricing
        self._inputs = inputs

    def quote(
        self,
        subject: AuthorizationSubject,
        *,
        ride_request_id: UUID,
        idempotency_key: str,
        correlation_id: UUID,
        at: datetime,
    ) -> FareEstimate:
        policy_id, metrics = self._inputs.resolve(
            ride_request_id=ride_request_id, subject=subject, at=at
        )
        return self._pricing.estimate(
            subject,
            ride_request_id=ride_request_id,
            policy_id=policy_id,
            metrics=metrics,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            causation_id=ride_request_id,
            at=at,
        )
