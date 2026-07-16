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
    PickupDefinition,
    RideRequest,
    ServiceZone,
    ValidationDecision,
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
        return None if row is None else RideRequest.model_validate(dict(row))

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
        return RideRequest.model_validate(dict(row))

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
        saved = RideRequest.model_validate(dict(row))
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
