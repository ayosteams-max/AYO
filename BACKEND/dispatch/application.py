from datetime import UTC, datetime
from uuid import UUID

from BACKEND.dispatch.contracts import DispatchConflict
from BACKEND.dispatch.models import (
    CreateRideCommand,
    DispatchPolicy,
    DriverOffer,
    RideProjection,
)
from BACKEND.dispatch.service import ImmediateDispatchService
from BACKEND.persistence.composition import PostgresRepositoryComposition


class DispatchApplication:
    """Short transaction boundary around the approved dispatch domain service."""

    def __init__(
        self, composition: PostgresRepositoryComposition, policy: DispatchPolicy
    ) -> None:
        self._composition = composition
        self._policy = policy

    def create_ride(
        self, *, rider_id: UUID, idempotency_key: str, command: CreateRideCommand
    ) -> tuple[RideProjection, bool]:
        with self._composition.unit_of_work() as unit:
            return ImmediateDispatchService(unit.dispatch, self._policy).create_ride(
                rider_id=rider_id,
                idempotency_key=idempotency_key,
                command=command,
            )

    def dispatch_next(self, ride_id: UUID) -> DriverOffer | None:
        with self._composition.unit_of_work() as unit:
            return ImmediateDispatchService(unit.dispatch, self._policy).dispatch_next(
                ride_id
            )

    def recover_ride(self, rider_id: UUID) -> RideProjection | None:
        with self._composition.unit_of_work() as unit:
            return ImmediateDispatchService(
                unit.dispatch, self._policy
            ).recover_active_ride(rider_id)

    def get_offer(self, offer_id: UUID) -> DriverOffer | None:
        with self._composition.unit_of_work() as unit:
            return unit.dispatch.get_offer(offer_id)

    def accept_offer(self, offer_id: UUID, driver_id: UUID) -> RideProjection:
        with self._composition.unit_of_work() as unit:
            return ImmediateDispatchService(unit.dispatch, self._policy).accept_offer(
                offer_id, driver_id
            )

    def decline_offer(self, offer_id: UUID, driver_id: UUID) -> DriverOffer | None:
        with self._composition.unit_of_work() as unit:
            return ImmediateDispatchService(
                unit.dispatch, self._policy
            ).decline_and_reassign(offer_id, driver_id)

    def recover(
        self, *, now: datetime | None = None, limit: int = 100
    ) -> tuple[int, int, int]:
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        with self._composition.unit_of_work() as unit:
            service = ImmediateDispatchService(unit.dispatch, self._policy)
            expired = service.recover_expired_offers(now=instant, limit=limit)
            resumed = 0
            for ride_id in unit.dispatch.list_searching_ride_ids(limit=limit):
                try:
                    service.dispatch_next(ride_id, now=instant)
                    resumed += 1
                except DispatchConflict:
                    # Another worker or request progressed this ride.
                    continue
            abandoned = unit.dispatch.abandon_expired_searches(now=instant, limit=limit)
            return expired, resumed, abandoned
