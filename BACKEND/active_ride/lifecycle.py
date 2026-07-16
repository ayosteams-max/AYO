from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from BACKEND.active_ride.application import ActiveRideUnitOfWork
from BACKEND.active_ride.engine import ActiveRideConflict
from BACKEND.active_ride.models import ActiveRide, ActiveRideState, ActorRole
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType
from BACKEND.localization.models import LocalizedMessageRef


class LifecycleCommandType(StrEnum):
    DRIVER_EN_ROUTE = "driver_en_route"
    DRIVER_ARRIVED = "driver_arrived"
    PICKUP_CONFIRMED = "pickup_confirmed"
    RIDE_STARTED = "ride_started"
    DESTINATION_ARRIVED = "destination_arrived"
    RIDE_COMPLETED = "ride_completed"
    DRIVER_CANCELLED = "driver_cancelled"
    RIDER_CANCELLED = "rider_cancelled"
    SUPPORT_INTERRUPTED = "support_interrupted"
    SYSTEM_INTERRUPTED = "system_interrupted"


TARGET_BY_COMMAND = {
    LifecycleCommandType.DRIVER_EN_ROUTE: ActiveRideState.DRIVER_EN_ROUTE,
    LifecycleCommandType.DRIVER_ARRIVED: ActiveRideState.DRIVER_ARRIVED,
    LifecycleCommandType.PICKUP_CONFIRMED: ActiveRideState.PICKUP_CONFIRMED,
    LifecycleCommandType.RIDE_STARTED: ActiveRideState.RIDE_IN_PROGRESS,
    LifecycleCommandType.DESTINATION_ARRIVED: ActiveRideState.DESTINATION_ARRIVED,
    LifecycleCommandType.RIDE_COMPLETED: ActiveRideState.COMPLETED,
    LifecycleCommandType.DRIVER_CANCELLED: ActiveRideState.DRIVER_CANCELLED,
    LifecycleCommandType.RIDER_CANCELLED: ActiveRideState.RIDER_CANCELLED,
    LifecycleCommandType.SUPPORT_INTERRUPTED: ActiveRideState.SUPPORT_INTERRUPTED,
    LifecycleCommandType.SYSTEM_INTERRUPTED: ActiveRideState.SYSTEM_INTERRUPTED,
}

COMMAND_AUTHORITY = {
    LifecycleCommandType.DRIVER_EN_ROUTE: frozenset({IdentityType.DRIVER}),
    LifecycleCommandType.DRIVER_ARRIVED: frozenset({IdentityType.DRIVER}),
    LifecycleCommandType.PICKUP_CONFIRMED: frozenset({IdentityType.SERVICE}),
    LifecycleCommandType.RIDE_STARTED: frozenset({IdentityType.DRIVER}),
    LifecycleCommandType.DESTINATION_ARRIVED: frozenset({IdentityType.DRIVER}),
    LifecycleCommandType.RIDE_COMPLETED: frozenset({IdentityType.DRIVER}),
    LifecycleCommandType.DRIVER_CANCELLED: frozenset({IdentityType.DRIVER}),
    LifecycleCommandType.RIDER_CANCELLED: frozenset({IdentityType.RIDER}),
    LifecycleCommandType.SUPPORT_INTERRUPTED: frozenset(
        {IdentityType.STAFF, IdentityType.ADMINISTRATOR}
    ),
    LifecycleCommandType.SYSTEM_INTERRUPTED: frozenset({IdentityType.SERVICE}),
}


class LifecycleCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    command_id: UUID
    expected_version: int = Field(ge=1)
    command_type: LifecycleCommandType
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$")
    evidence_references: tuple[str, ...] = Field(default=(), max_length=10)


class LifecycleUowFactory(Protocol):
    def __call__(self) -> ActiveRideUnitOfWork: ...


class ActiveRideLifecycleApplication:
    """Canonical post-assignment lifecycle; route-neutral and disabled by default."""

    def __init__(
        self,
        uow_factory: LifecycleUowFactory,
        *,
        policy_version: str = "active_ride.v1",
    ) -> None:
        self._uow_factory = uow_factory
        self._policy_version = policy_version

    def start_from_assignment(
        self, assignment_id: UUID, *, now: datetime | None = None
    ) -> ActiveRide:
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        with self._uow_factory() as unit:
            return cast(
                ActiveRide,
                unit.active_rides.create_from_immediate_assignment(
                    assignment_id=assignment_id,
                    lifecycle_policy_version=self._policy_version,
                    now=instant,
                ),
            )

    def command(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        command: LifecycleCommand,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if subject.identity_type not in COMMAND_AUTHORITY[command.command_type]:
            raise ActiveRideConflict("access_denied")
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        with self._uow_factory() as unit:
            ride = unit.active_rides.get(ride_id, lock=True)
            if ride is None or not self._owns_or_operates(subject, ride):
                raise ActiveRideConflict("ride_not_found")
            target = TARGET_BY_COMMAND[command.command_type]
            changed, created = unit.active_rides.command_transition(
                ride_id=ride_id,
                actor_id=subject.identity_id,
                command_id=command.command_id,
                command_type=f"active_ride.{command.command_type.value}",
                request_payload={
                    "state_to": target.value,
                    "reason_code": command.reason_code,
                    "evidence_references": list(command.evidence_references),
                    "policy_version": ride.lifecycle_policy_version,
                    "translation_key": f"active_ride.{target.value}",
                },
                expected_version=command.expected_version,
                target=target,
                now=instant,
            )
            return {
                "ride_id": str(changed.ride_id),
                "state": changed.state.value,
                "aggregate_version": changed.version,
                "last_sequence": changed.last_sequence,
                "command_created": created,
                "message": LocalizedMessageRef(
                    reason_code=f"active_ride.{target.value}",
                    translation_key=f"active_ride.{target.value}",
                ).model_dump(mode="json"),
            }

    def recover(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        *,
        after_sequence: int,
        limit: int = 100,
    ) -> dict[str, Any]:
        with self._uow_factory() as unit:
            ride = unit.active_rides.get(ride_id)
            if ride is None or not self._owns_or_operates(subject, ride):
                raise ActiveRideConflict("ride_not_found")
            unit.active_rides.replay_canonical_state(ride_id)
            events = unit.active_rides.events_after(
                ride_id, after_sequence, limit=min(max(limit, 1), 100)
            )
            return {
                "ride_id": str(ride.ride_id),
                "state": ride.state.value,
                "aggregate_version": ride.version,
                "last_sequence": ride.last_sequence,
                "events": [item.model_dump(mode="json") for item in events],
                "resync_required": False,
            }

    @staticmethod
    def _owns_or_operates(subject: AuthorizationSubject, ride: ActiveRide) -> bool:
        if subject.identity_type is IdentityType.RIDER:
            return subject.identity_id == ride.rider_id
        if subject.identity_type is IdentityType.DRIVER:
            return subject.identity_id == ride.driver_id
        return subject.identity_type in {
            IdentityType.SERVICE,
            IdentityType.STAFF,
            IdentityType.ADMINISTRATOR,
        }


def role_for_subject(subject: AuthorizationSubject) -> ActorRole:
    if subject.identity_type is IdentityType.RIDER:
        return ActorRole.RIDER
    if subject.identity_type is IdentityType.DRIVER:
        return ActorRole.DRIVER
    if subject.identity_type in {IdentityType.STAFF, IdentityType.ADMINISTRATOR}:
        return ActorRole.SUPPORT
    return ActorRole.WORKER
