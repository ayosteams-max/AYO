import hashlib
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.booking.contracts import (
    BookingDispatchStarter,
    BookingPricingAuthority,
    RouteIntelligenceProvider,
)
from BACKEND.booking.models import (
    BookingConfirmation,
    BookingConflict,
    BookingSession,
    PlaceCandidate,
    RoutePreview,
)
from BACKEND.identity.models import IdentityType
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.ride_request.application import (
    CreateRideRequestCommand,
    RideRequestApplication,
)
from BACKEND.ride_request.models import (
    Coordinate,
    DestinationDefinition,
    PaymentIntentType,
    PickupDefinition,
    RideRequest,
    RideRequestState,
    RideServiceType,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class PreviewRouteCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    client_preview_id: UUID
    booking_session: BookingSession
    pickup: PickupDefinition
    destination: DestinationDefinition
    service_type: RideServiceType = RideServiceType.IMMEDIATE_STANDARD


class ConfirmBookingCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: UUID
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    quote_id: UUID
    booking_session: BookingSession
    client_request_id: UUID
    idempotency_key: str = Field(min_length=16, max_length=128)
    consent_policy_version: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")


class BookingApplication:
    def __init__(
        self,
        composition: PostgresRepositoryComposition,
        routes: RouteIntelligenceProvider,
        pricing: BookingPricingAuthority,
        ride_requests: RideRequestApplication,
        pricing_policy_id: UUID,
        dispatch: BookingDispatchStarter | None = None,
    ) -> None:
        self._composition = composition
        self._routes = routes
        self._pricing = pricing
        self._ride_requests = ride_requests
        self._pricing_policy_id = pricing_policy_id
        self._dispatch = dispatch

    @property
    def dispatch_enabled(self) -> bool:
        return self._dispatch is not None

    def _start_dispatch(
        self, confirmation: BookingConfirmation, ride: RideRequest, *, at: datetime
    ) -> None:
        if self._dispatch is None:
            return
        try:
            self._dispatch.start(
                ride_request_id=ride.request_id,
                idempotency_key=f"booking-dispatch-{confirmation.confirmation_id}",
                correlation_id=ride.request_id,
                causation_id=confirmation.confirmation_id,
                at=at,
            )
        except (RuntimeError, TimeoutError) as error:
            raise BookingConflict("temporarily_unavailable") from error

    def search_places(
        self, *, query: str, locale: str, limit: int, at: datetime
    ) -> tuple[PlaceCandidate, ...]:
        normalized = " ".join(query.split())
        if len(normalized) < 2 or len(normalized) > 120:
            raise BookingConflict("invalid_place_query")
        if locale not in {"en", "am"}:
            raise BookingConflict("unsupported_locale")
        if not 1 <= limit <= 10:
            raise BookingConflict("invalid_result_limit")
        return self._routes.search_places(
            query=normalized, locale=locale, limit=limit, at=at.astimezone(UTC)
        )

    def preview(
        self,
        command: PreviewRouteCommand,
        *,
        subject: AuthorizationSubject | None,
        at: datetime,
    ) -> RoutePreview:
        at = at.astimezone(UTC)
        rider_id = None
        if subject is not None:
            if subject.identity_type is not IdentityType.RIDER:
                raise BookingConflict("access_denied")
            rider_id = subject.identity_id
        session_hash = _digest(command.booking_session)
        with self._composition.unit_of_work() as unit:
            existing = unit.booking.get_preview(command.client_preview_id)
            if existing is not None:
                if existing.booking_session_hash != session_hash:
                    raise BookingConflict("idempotency_conflict")
                return existing
            pickup_zone = unit.ride_requests.find_zone(
                latitude=command.pickup.coordinate.latitude,
                longitude=command.pickup.coordinate.longitude,
                at=at,
            )
            destination_zone = unit.ride_requests.find_zone(
                latitude=command.destination.coordinate.latitude,
                longitude=command.destination.coordinate.longitude,
                at=at,
            )
        if (
            pickup_zone is None
            or destination_zone is None
            or pickup_zone.zone_id != destination_zone.zone_id
            or command.service_type not in pickup_zone.supported_service_types
        ):
            raise BookingConflict("service_area_unsupported")
        route = self._routes.route(
            origin=command.pickup.coordinate,
            destination=command.destination.coordinate,
            at=at,
        )
        pickup = command.pickup.model_copy(
            update={
                "coordinate": Coordinate(
                    latitude=route.geometry[0][0], longitude=route.geometry[0][1]
                ),
                "observed_at": route.metrics.observed_at,
                "accuracy_metres": route.origin_accuracy_metres,
                "map_confidence_bps": route.map_confidence_bps,
                "safety_status": route.pickup_safety_status,
            }
        )
        destination = command.destination.model_copy(
            update={
                "coordinate": Coordinate(
                    latitude=route.geometry[-1][0], longitude=route.geometry[-1][1]
                ),
                "observed_at": route.metrics.observed_at,
                "accuracy_metres": route.destination_accuracy_metres,
                "map_confidence_bps": route.map_confidence_bps,
            }
        )
        with self._composition.unit_of_work() as unit:
            authoritative_pickup_zone = unit.ride_requests.find_zone(
                latitude=pickup.coordinate.latitude,
                longitude=pickup.coordinate.longitude,
                at=at,
            )
            authoritative_destination_zone = unit.ride_requests.find_zone(
                latitude=destination.coordinate.latitude,
                longitude=destination.coordinate.longitude,
                at=at,
            )
        if (
            authoritative_pickup_zone is None
            or authoritative_destination_zone is None
            or authoritative_pickup_zone.zone_id
            != authoritative_destination_zone.zone_id
            or authoritative_pickup_zone.zone_id != pickup_zone.zone_id
        ):
            raise BookingConflict("service_area_unsupported")
        quote = self._pricing.quote(
            policy_id=self._pricing_policy_id,
            service_zone_id=pickup_zone.zone_id,
            metrics=route.metrics,
            at=at,
        )
        expires_at = quote.expires_at
        payload = "|".join(
            (
                str(command.client_preview_id),
                session_hash,
                pickup.model_dump_json(),
                destination.model_dump_json(),
                route.model_dump_json(),
                quote.model_dump_json(),
                pickup_zone.version,
            )
        )
        preview = RoutePreview(
            evidence_id=command.client_preview_id,
            booking_session_hash=session_hash,
            rider_identity_id=rider_id,
            pickup=pickup,
            destination=destination,
            service_zone_id=pickup_zone.zone_id,
            service_zone_version=pickup_zone.version,
            service_type=command.service_type.value,
            route=route,
            quote=quote,
            evidence_hash=_digest(payload),
            created_at=at,
            expires_at=expires_at,
        )
        with self._composition.unit_of_work() as unit:
            return unit.booking.add_preview(preview)

    def confirm(
        self,
        command: ConfirmBookingCommand,
        *,
        subject: AuthorizationSubject,
        at: datetime,
    ) -> tuple[BookingConfirmation, RideRequest]:
        if subject.identity_type is not IdentityType.RIDER:
            raise BookingConflict("authentication_required")
        at = at.astimezone(UTC)
        key_hash = _digest(command.idempotency_key)
        with self._composition.unit_of_work() as unit:
            preview = unit.booking.get_preview(command.evidence_id, lock=True)
            existing = unit.booking.get_confirmation_for_evidence(command.evidence_id)
        if existing is not None:
            if (
                existing.rider_identity_id != subject.identity_id
                or existing.idempotency_key_hash != key_hash
                or existing.evidence_hash != command.evidence_hash
            ):
                raise BookingConflict("idempotency_conflict")
            ride = self._ride_requests.get_owned(
                subject=subject, request_id=existing.ride_request_id
            )
            self._start_dispatch(existing, ride, at=at)
            return existing, ride
        if preview is None:
            raise BookingConflict("route_evidence_not_found")
        if preview.booking_session_hash != _digest(command.booking_session):
            raise BookingConflict("route_evidence_not_found")
        if preview.rider_identity_id not in {None, subject.identity_id}:
            raise BookingConflict("access_denied")
        if preview.evidence_hash != command.evidence_hash:
            raise BookingConflict("route_changed")
        if preview.quote.quote_id != command.quote_id:
            raise BookingConflict("quote_changed")
        if at >= preview.expires_at:
            raise BookingConflict("route_evidence_expired")
        if at >= preview.quote.expires_at:
            raise BookingConflict("quote_expired")
        ride = self._ride_requests.create(
            subject=subject,
            command=CreateRideRequestCommand(
                client_request_id=command.client_request_id,
                idempotency_key=command.idempotency_key,
                pickup=preview.pickup,
                destination=preview.destination,
                service_type=RideServiceType.IMMEDIATE_STANDARD,
                payment_intent=PaymentIntentType.CASH_COMPATIBLE,
                consent_policy_version=command.consent_policy_version,
            ),
            at=at,
        )
        if ride.state is not RideRequestState.READY_FOR_DISPATCH:
            raise BookingConflict("booking_validation_failed")
        confirmation = BookingConfirmation(
            evidence_id=preview.evidence_id,
            evidence_hash=preview.evidence_hash,
            quote_id=preview.quote.quote_id,
            ride_request_id=ride.request_id,
            rider_identity_id=subject.identity_id,
            idempotency_key_hash=key_hash,
            confirmed_at=at,
        )
        with self._composition.unit_of_work() as unit:
            stored = unit.booking.add_confirmation(confirmation)
        self._start_dispatch(stored, ride, at=at)
        return stored, ride
