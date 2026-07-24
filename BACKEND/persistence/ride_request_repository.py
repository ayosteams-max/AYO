from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.persistence.tables import (
    canonical_destinations,
    canonical_pickups,
    canonical_ride_requests,
    ride_request_events,
    ride_request_idempotency,
    ride_request_outbox,
    ride_request_validation_decisions,
    service_zones,
)
from BACKEND.ride_request.models import (
    DestinationDefinition,
    MobilityRideRequestState,
    PassengerMobilityRideRequest,
    PickupDefinition,
    RideRequest,
    ServiceZone,
    ValidationDecision,
)

_LEGACY_FIELDS = frozenset(RideRequest.model_fields)


def _legacy_request(row: Any) -> RideRequest:
    return RideRequest.model_validate(
        {key: value for key, value in dict(row).items() if key in _LEGACY_FIELDS}
    )


def _mobility_request(row: Any) -> PassengerMobilityRideRequest:
    values = dict(row)
    return PassengerMobilityRideRequest.model_validate(
        {
            "request_id": values["request_id"],
            "model_version": values["mobility_model_version"],
            "client_request_id": values["client_request_id"],
            "requester_subject_id": values["requester_subject_id"],
            "passenger_subject_id": values["passenger_subject_id"],
            "state": values["state"],
            "pickup_reference": values["pickup_reference"],
            "destination_reference": values["destination_reference"],
            "stop_references": tuple(values["stop_references"] or ()),
            "schedule_intent": values["schedule_intent"],
            "scheduled_for": values["scheduled_for"],
            "passenger_count": values["passenger_count"],
            "preferences": values["ride_preferences"] or {},
            "version": values["version"],
            "created_at": values["created_at"],
            "updated_at": values["updated_at"],
            "expires_at": values["expires_at"],
        }
    )


class ConcurrentRideRequestChange(RuntimeError):
    pass


class PostgresRideRequestRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def owner_identity_id(self, request_id: UUID) -> UUID | None:
        value = self._connection.execute(
            select(canonical_ride_requests.c.rider_identity_id).where(
                canonical_ride_requests.c.request_id == request_id
            )
        ).scalar_one_or_none()
        return cast(UUID | None, value)

    def get(self, request_id: UUID) -> RideRequest | None:
        row = (
            self._connection.execute(
                select(canonical_ride_requests).where(
                    canonical_ride_requests.c.request_id == request_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _legacy_request(row)

    def find_zone(
        self, *, latitude: float, longitude: float, at: Any
    ) -> ServiceZone | None:
        row = (
            self._connection.execute(
                select(service_zones)
                .where(
                    service_zones.c.active_from <= at,
                    (
                        service_zones.c.active_until.is_(None)
                        | (service_zones.c.active_until > at)
                    ),
                    service_zones.c.min_latitude <= latitude,
                    service_zones.c.max_latitude >= latitude,
                    service_zones.c.min_longitude <= longitude,
                    service_zones.c.max_longitude >= longitude,
                )
                .order_by(service_zones.c.code, service_zones.c.version.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else ServiceZone.model_validate(dict(row))

    def add_zone(self, zone: ServiceZone) -> None:
        values = zone.model_dump()
        values["prohibited_rectangles"] = [list(x) for x in zone.prohibited_rectangles]
        values["supported_service_types"] = [
            x.value for x in zone.supported_service_types
        ]
        self._connection.execute(insert(service_zones).values(**values))

    def has_active(
        self, rider_identity_id: UUID, *, excluding: UUID | None = None
    ) -> bool:
        query = select(canonical_ride_requests.c.request_id).where(
            canonical_ride_requests.c.rider_identity_id == rider_identity_id,
            canonical_ride_requests.c.state.in_(
                ["requested", "validating", "ready_for_dispatch"]
            ),
        )
        if excluding is not None:
            query = query.where(canonical_ride_requests.c.request_id != excluding)
        return self._connection.execute(query.limit(1)).scalar_one_or_none() is not None

    def reserve_idempotency(
        self,
        *,
        rider_identity_id: UUID,
        operation: str,
        key: str,
        request_hash: str,
        response_reference: UUID,
        at: Any,
    ) -> UUID:
        self._connection.execute(
            pg_insert(ride_request_idempotency)
            .values(
                rider_identity_id=rider_identity_id,
                operation=operation,
                idempotency_key=key,
                request_hash=request_hash,
                response_reference=response_reference,
                created_at=at,
            )
            .on_conflict_do_nothing(
                index_elements=["rider_identity_id", "operation", "idempotency_key"]
            )
        )
        row = (
            self._connection.execute(
                select(ride_request_idempotency)
                .where(
                    ride_request_idempotency.c.rider_identity_id == rider_identity_id,
                    ride_request_idempotency.c.operation == operation,
                    ride_request_idempotency.c.idempotency_key == key,
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        if row["request_hash"] != request_hash:
            raise ValueError("Idempotency key reused with different request")
        return cast(UUID, row["response_reference"])

    def create(
        self,
        request: RideRequest,
        pickup: PickupDefinition,
        destination: DestinationDefinition,
    ) -> RideRequest:
        p = pickup.model_dump()
        coord = p.pop("coordinate")
        p.update(coord)
        d = destination.model_dump()
        coord = d.pop("coordinate")
        d.update(coord)
        self._connection.execute(insert(canonical_pickups).values(**p))
        self._connection.execute(insert(canonical_destinations).values(**d))
        row = (
            self._connection.execute(
                insert(canonical_ride_requests)
                .values(**request.model_dump())
                .returning(canonical_ride_requests)
            )
            .mappings()
            .one()
        )
        self.append_event(request, "ride_request.created", at=request.created_at)
        self.append_event(request, "pickup.recorded", at=request.created_at)
        return _legacy_request(row)

    def save(
        self, request: RideRequest, *, expected_version: int, event_type: str
    ) -> RideRequest:
        row = (
            self._connection.execute(
                update(canonical_ride_requests)
                .where(
                    canonical_ride_requests.c.request_id == request.request_id,
                    canonical_ride_requests.c.version == expected_version,
                )
                .values(
                    state=request.state.value,
                    version=request.version,
                    updated_at=request.updated_at,
                    cancellation_reason=request.cancellation_reason,
                )
                .returning(canonical_ride_requests)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ConcurrentRideRequestChange("Ride request changed concurrently")
        saved = _legacy_request(row)
        self.append_event(saved, event_type, at=saved.updated_at)
        return saved

    def append_validation(self, decision: ValidationDecision) -> None:
        values = decision.model_dump()
        values["reason_codes"] = list(decision.reason_codes)
        values["invalid_fields"] = list(decision.invalid_fields)
        self._connection.execute(
            insert(ride_request_validation_decisions).values(**values)
        )

    def append_event(self, request: RideRequest, event_type: str, *, at: Any) -> None:
        event_id = uuid4()
        payload = {
            "state": request.state.value,
            "service_type": request.service_type.value,
        }
        self._connection.execute(
            insert(ride_request_events).values(
                event_id=event_id,
                request_id=request.request_id,
                request_version=request.version,
                event_type=event_type,
                safe_payload=payload,
                occurred_at=at,
            )
        )
        self._connection.execute(
            insert(ride_request_outbox).values(
                event_id=event_id,
                event_type=event_type,
                aggregate_id=request.request_id,
                aggregate_version=request.version,
                safe_payload=payload,
                created_at=at,
                attempt_count=0,
            )
        )

    def create_mobility(
        self, request: PassengerMobilityRideRequest
    ) -> PassengerMobilityRideRequest:
        values = {
            "request_id": request.request_id,
            "client_request_id": request.client_request_id,
            "mobility_model_version": request.model_version,
            "requester_subject_id": request.requester_subject_id,
            "passenger_subject_id": request.passenger_subject_id,
            "state": request.state.value,
            "pickup_reference": request.pickup_reference,
            "destination_reference": request.destination_reference,
            "stop_references": list(request.stop_references),
            "schedule_intent": request.schedule_intent.value,
            "scheduled_for": request.scheduled_for,
            "passenger_count": request.passenger_count,
            "ride_preferences": request.preferences.model_dump(mode="json"),
            "version": request.version,
            "created_at": request.created_at,
            "updated_at": request.updated_at,
            "expires_at": request.expires_at,
        }
        row = (
            self._connection.execute(
                insert(canonical_ride_requests)
                .values(**values)
                .returning(canonical_ride_requests)
            )
            .mappings()
            .one()
        )
        return _mobility_request(row)

    def get_mobility(
        self, request_id: UUID, *, lock: bool = False
    ) -> PassengerMobilityRideRequest | None:
        statement = select(canonical_ride_requests).where(
            canonical_ride_requests.c.request_id == request_id,
            canonical_ride_requests.c.mobility_model_version == 2,
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return None if row is None else _mobility_request(row)

    def save_mobility(
        self,
        request: PassengerMobilityRideRequest,
        *,
        expected_version: int,
    ) -> PassengerMobilityRideRequest:
        row = (
            self._connection.execute(
                update(canonical_ride_requests)
                .where(
                    canonical_ride_requests.c.request_id == request.request_id,
                    canonical_ride_requests.c.mobility_model_version == 2,
                    canonical_ride_requests.c.version == expected_version,
                )
                .values(
                    state=request.state.value,
                    version=request.version,
                    updated_at=request.updated_at,
                )
                .returning(canonical_ride_requests)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ConcurrentRideRequestChange("Ride Request changed concurrently")
        return _mobility_request(row)

    def has_active_mobility_request(
        self, requester_subject_id: UUID, *, excluding: UUID | None = None
    ) -> bool:
        statement = select(canonical_ride_requests.c.request_id).where(
            canonical_ride_requests.c.mobility_model_version == 2,
            canonical_ride_requests.c.requester_subject_id == requester_subject_id,
            canonical_ride_requests.c.state.in_(
                [
                    MobilityRideRequestState.DRAFT.value,
                    MobilityRideRequestState.VALIDATED.value,
                    MobilityRideRequestState.SUBMITTED.value,
                ]
            ),
        )
        if excluding is not None:
            statement = statement.where(
                canonical_ride_requests.c.request_id != excluding
            )
        return (
            self._connection.execute(statement.limit(1)).scalar_one_or_none()
            is not None
        )
