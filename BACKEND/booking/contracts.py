from datetime import datetime
from typing import Protocol
from uuid import UUID

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.booking.models import BookingQuote, PlaceCandidate, ProviderRouteEvidence
from BACKEND.pricing.models import EstimateAcceptance, FareEstimate, RouteMetrics
from BACKEND.ride_request.models import Coordinate


class RouteIntelligenceProvider(Protocol):
    def search_places(
        self, *, query: str, locale: str, limit: int, at: datetime
    ) -> tuple[PlaceCandidate, ...]: ...

    def route(
        self, *, origin: Coordinate, destination: Coordinate, at: datetime
    ) -> ProviderRouteEvidence: ...


class BookingPricingAuthority(Protocol):
    def quote(
        self,
        *,
        policy_id: UUID,
        service_zone_id: UUID,
        metrics: RouteMetrics,
        at: datetime,
    ) -> BookingQuote: ...

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
    ) -> tuple[FareEstimate, EstimateAcceptance, str]: ...


class BookingDispatchStarter(Protocol):
    def start(
        self,
        *,
        ride_request_id: UUID,
        idempotency_key: str,
        correlation_id: UUID,
        causation_id: UUID,
        at: datetime,
    ) -> object: ...
