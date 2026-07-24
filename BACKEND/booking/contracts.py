from datetime import datetime
from typing import Protocol
from uuid import UUID

from BACKEND.booking.models import BookingQuote, PlaceCandidate, ProviderRouteEvidence
from BACKEND.pricing.models import RouteMetrics
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
