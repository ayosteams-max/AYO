from uuid import UUID

from sqlalchemy import Connection, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.booking.models import BookingConfirmation, BookingConflict, RoutePreview
from BACKEND.persistence.tables import booking_confirmations, booking_route_evidence


class PostgresBookingRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def add_preview(self, preview: RoutePreview) -> RoutePreview:
        inserted = self._connection.execute(
            pg_insert(booking_route_evidence)
            .values(
                evidence_id=preview.evidence_id,
                booking_session_hash=preview.booking_session_hash,
                rider_identity_id=preview.rider_identity_id,
                pickup_payload=preview.pickup.model_dump(mode="json"),
                destination_payload=preview.destination.model_dump(mode="json"),
                service_zone_id=preview.service_zone_id,
                service_zone_version=preview.service_zone_version,
                service_type=preview.service_type,
                route_payload=preview.route.model_dump(mode="json"),
                quote_payload=preview.quote.model_dump(mode="json"),
                evidence_hash=preview.evidence_hash,
                created_at=preview.created_at,
                expires_at=preview.expires_at,
            )
            .on_conflict_do_nothing()
            .returning(booking_route_evidence.c.evidence_id)
        ).scalar_one_or_none()
        if inserted is not None:
            return preview
        existing = self.get_preview(preview.evidence_id)
        if (
            existing is None
            or existing.booking_session_hash != preview.booking_session_hash
        ):
            raise BookingConflict("idempotency_conflict")
        return existing

    def get_preview(
        self, evidence_id: UUID, *, lock: bool = False
    ) -> RoutePreview | None:
        query = select(booking_route_evidence).where(
            booking_route_evidence.c.evidence_id == evidence_id
        )
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        if row is None:
            return None
        value = dict(row)
        value["pickup"] = value.pop("pickup_payload")
        value["destination"] = value.pop("destination_payload")
        value["route"] = value.pop("route_payload")
        value["quote"] = value.pop("quote_payload")
        return RoutePreview.model_validate(value)

    def get_confirmation_for_evidence(
        self, evidence_id: UUID
    ) -> BookingConfirmation | None:
        row = (
            self._connection.execute(
                select(booking_confirmations).where(
                    booking_confirmations.c.evidence_id == evidence_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else BookingConfirmation.model_validate(dict(row))

    def get_confirmation_for_ride_request(
        self, ride_request_id: UUID
    ) -> BookingConfirmation | None:
        row = (
            self._connection.execute(
                select(booking_confirmations).where(
                    booking_confirmations.c.ride_request_id == ride_request_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else BookingConfirmation.model_validate(dict(row))

    def add_confirmation(self, item: BookingConfirmation) -> BookingConfirmation:
        inserted = self._connection.execute(
            pg_insert(booking_confirmations)
            .values(**item.model_dump())
            .on_conflict_do_nothing()
            .returning(booking_confirmations.c.confirmation_id)
        ).scalar_one_or_none()
        if inserted is not None:
            return item
        existing = self.get_confirmation_for_evidence(item.evidence_id)
        if existing is None or (
            existing.rider_identity_id != item.rider_identity_id
            or existing.idempotency_key_hash != item.idempotency_key_hash
            or existing.ride_request_id != item.ride_request_id
            or existing.evidence_hash != item.evidence_hash
        ):
            raise BookingConflict("idempotency_conflict")
        return existing
