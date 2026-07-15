import secrets
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Protocol, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from BACKEND.active_ride.engine import ActiveRideConflict, evaluate_confidence
from BACKEND.active_ride.models import (
    ActiveRide,
    ActiveRideState,
    ActorRole,
    ConfidenceDecision,
    ConfidencePolicy,
    ConfidenceSignals,
    EvidenceRecord,
    PickupRecommendation,
)
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType
from BACKEND.observability import MetricsSink, NullMetricsSink


class ActiveRideUnitOfWork(Protocol):
    active_rides: Any

    def __enter__(self) -> "ActiveRideUnitOfWork": ...
    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...
    def commit(self) -> None: ...


class UowFactory(Protocol):
    def __call__(self) -> ActiveRideUnitOfWork: ...


class CommandEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    command_id: UUID
    expected_version: int = Field(ge=1)
    reason_code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.-]{1,62}$")


class ProgressCommand(CommandEnvelope):
    progress_basis_points: int = Field(ge=0, le=10_000)


class EvidenceCommand(CommandEnvelope):
    evidence_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$")
    evidence_references: tuple[str, ...] = Field(default=(), max_length=10)


class PickupVerifyCommand(CommandEnvelope):
    code: str = Field(pattern=r"^[0-9]{4,8}$")


class RequestPickupVerificationCommand(CommandEnvelope):
    passenger_mode: str = Field(
        default="authenticated", pattern=r"^(authenticated|verified_contact|assisted)$"
    )
    delivery_reference: str | None = Field(default=None, min_length=8, max_length=128)


class AckCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    sequence: int = Field(ge=0)


class PickupChangeCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    recommendation_id: UUID
    confirmed: bool


class ActiveRideApplication:
    def __init__(
        self,
        uow_factory: UowFactory,
        *,
        pin_secret: bytes,
        confidence_policy: ConfidencePolicy | None = None,
        metrics: MetricsSink | None = None,
    ) -> None:
        if len(pin_secret) < 32:
            raise ValueError("Pickup verification secret must be at least 32 bytes")
        self._uow_factory = uow_factory
        self._pin_secret = pin_secret
        self._confidence_policy = confidence_policy or ConfidencePolicy()
        self._metrics = metrics or NullMetricsSink()

    def snapshot(self, subject: AuthorizationSubject, ride_id: UUID) -> dict[str, Any]:
        with self._uow_factory() as unit:
            ride = self._owned(unit.active_rides, subject, ride_id)
            return cast(
                dict[str, Any],
                unit.active_rides.projection(ride, self._role(subject)),
            )

    def events(
        self, subject: AuthorizationSubject, ride_id: UUID, *, after: int, limit: int
    ) -> list[dict[str, Any]]:
        with self._uow_factory() as unit:
            self._owned(unit.active_rides, subject, ride_id)
            return [
                item.model_dump(mode="json")
                for item in unit.active_rides.events_after(ride_id, after, limit=limit)
            ]

    def acknowledge(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        sequence: int,
        *,
        now: datetime,
    ) -> None:
        with self._uow_factory() as unit:
            self._owned(unit.active_rides, subject, ride_id)
            unit.active_rides.acknowledge(
                ride_id, self._role(subject), sequence, now=now
            )

    def command(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        command: CommandEnvelope,
        *,
        command_type: str,
        target: ActiveRideState,
        driver_only: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        instant = (now or datetime.now(UTC)).astimezone(UTC)
        with self._uow_factory() as unit:
            self._owned(unit.active_rides, subject, ride_id, driver_only=driver_only)
            changed, created = unit.active_rides.command_transition(
                ride_id=ride_id,
                actor_id=subject.identity_id,
                command_id=command.command_id,
                command_type=command_type,
                request_payload=command.model_dump(mode="json"),
                expected_version=command.expected_version,
                target=target,
                now=instant,
            )
            result = unit.active_rides.projection(changed, self._role(subject))
            result["command_status"] = "confirmed"
            result["command_created"] = created
            self._metrics.increment(
                "active_ride_lifecycle_transition",
                labels={"event": command_type, "created": str(created).lower()},
            )
            return cast(dict[str, Any], result)

    def issue_verification(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        command: RequestPickupVerificationCommand | CommandEnvelope,
        *,
        now: datetime,
    ) -> dict[str, str]:
        with self._uow_factory() as unit:
            ride = self._owned(unit.active_rides, subject, ride_id)
            if subject.identity_id != ride.rider_id or ride.assignment_id is None:
                raise ActiveRideConflict("access_denied")
            changed, _ = unit.active_rides.command_transition(
                ride_id=ride_id,
                actor_id=subject.identity_id,
                command_id=command.command_id,
                command_type="pickup_verification_requested",
                request_payload={
                    "challenge": "pin",
                    "passenger_mode": getattr(
                        command, "passenger_mode", "authenticated"
                    ),
                },
                expected_version=command.expected_version,
                target=ActiveRideState.PICKUP_VERIFICATION_PENDING,
                now=now,
            )
            code = f"{secrets.randbelow(10_000):04d}"
            verification_id = unit.active_rides.issue_pin(
                ride_id=ride_id,
                assignment_id=changed.assignment_id,
                code=code,
                secret=self._pin_secret,
                now=now,
            )
            return {
                "verification_id": str(verification_id),
                "pickup_code": code,
                "expires_at": "server_controlled",
            }

    def verify_pickup(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        command: PickupVerifyCommand,
        *,
        now: datetime,
    ) -> dict[str, Any]:
        failed = False
        with self._uow_factory() as unit:
            self._owned(unit.active_rides, subject, ride_id, driver_only=True)
            valid = unit.active_rides.verify_pin(
                ride_id=ride_id, code=command.code, secret=self._pin_secret, now=now
            )
            if not valid:
                unit.active_rides.add_evidence(
                    EvidenceRecord(
                        ride_id=ride_id,
                        evidence_type="pickup_verification_failure",
                        submitted_by_role=ActorRole.DRIVER,
                        observed_at=now,
                        reason_code="pickup_pin_mismatch",
                    )
                )
                unit.commit()
                self._metrics.increment("active_ride_pickup_verification_failure")
                failed = True
            else:
                changed, _ = unit.active_rides.command_transition(
                    ride_id=ride_id,
                    actor_id=subject.identity_id,
                    command_id=command.command_id,
                    command_type="pickup_verified",
                    request_payload={"verification": "server_confirmed"},
                    expected_version=command.expected_version,
                    target=ActiveRideState.PICKUP_VERIFIED,
                    now=now,
                )
                self._metrics.increment("active_ride_pickup_verification_success")
                return cast(
                    dict[str, Any],
                    unit.active_rides.projection(changed, ActorRole.DRIVER),
                )
        if failed:
            raise ActiveRideConflict("verification_failed")
        raise ActiveRideConflict("verification_failed")

    def evidence(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        command: EvidenceCommand,
        *,
        now: datetime,
    ) -> None:
        with self._uow_factory() as unit:
            self._owned(unit.active_rides, subject, ride_id)
            unit.active_rides.add_evidence(
                EvidenceRecord(
                    ride_id=ride_id,
                    evidence_type=command.evidence_type,
                    submitted_by_role=self._role(subject),
                    observed_at=now,
                    reason_code=command.reason_code or "insufficient_evidence",
                    evidence_references=command.evidence_references,
                )
            )

    def evidence_transition(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        command: EvidenceCommand,
        *,
        command_type: str,
        target: ActiveRideState,
        driver_only: bool,
        now: datetime,
    ) -> dict[str, Any]:
        with self._uow_factory() as unit:
            self._owned(unit.active_rides, subject, ride_id, driver_only=driver_only)
            unit.active_rides.add_evidence(
                EvidenceRecord(
                    ride_id=ride_id,
                    evidence_type=command.evidence_type,
                    submitted_by_role=self._role(subject),
                    observed_at=now,
                    reason_code=command.reason_code or "insufficient_evidence",
                    evidence_references=command.evidence_references,
                )
            )
            changed, created = unit.active_rides.command_transition(
                ride_id=ride_id,
                actor_id=subject.identity_id,
                command_id=command.command_id,
                command_type=command_type,
                request_payload=command.model_dump(mode="json"),
                expected_version=command.expected_version,
                target=target,
                now=now,
            )
            result = unit.active_rides.projection(changed, self._role(subject))
            result.update(command_status="confirmed", command_created=created)
            return cast(dict[str, Any], result)

    def evaluate_confidence(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        signals: ConfidenceSignals,
        *,
        now: datetime,
    ) -> ConfidenceDecision:
        with self._uow_factory() as unit:
            self._owned(unit.active_rides, subject, ride_id)
            decision = evaluate_confidence(
                ride_id,
                signals,
                self._confidence_policy,
                now=now,
                previous=unit.active_rides.latest_confidence(ride_id),
            )
            unit.active_rides.save_confidence(decision)
            self._metrics.increment(
                "active_ride_confidence_evaluation",
                labels={"level": decision.health_level.value},
            )
            return decision

    def confidence(
        self, subject: AuthorizationSubject, ride_id: UUID
    ) -> ConfidenceDecision | None:
        with self._uow_factory() as unit:
            self._owned(unit.active_rides, subject, ride_id)
            return cast(
                ConfidenceDecision | None,
                unit.active_rides.latest_confidence(ride_id),
            )

    def pickup(
        self, subject: AuthorizationSubject, ride_id: UUID
    ) -> PickupRecommendation | None:
        with self._uow_factory() as unit:
            self._owned(unit.active_rides, subject, ride_id)
            return cast(
                PickupRecommendation | None,
                unit.active_rides.latest_pickup_recommendation(ride_id),
            )

    def pickup_change(
        self, subject: AuthorizationSubject, ride_id: UUID, command: PickupChangeCommand
    ) -> PickupRecommendation:
        with self._uow_factory() as unit:
            self._owned(unit.active_rides, subject, ride_id)
            result = unit.active_rides.decide_pickup_change(
                ride_id, command.recommendation_id, confirmed=command.confirmed
            )
            self._metrics.increment(
                "active_ride_pickup_recommendation_outcome",
                labels={"outcome": result.change_status},
            )
            return cast(PickupRecommendation, result)

    @staticmethod
    def _role(subject: AuthorizationSubject) -> ActorRole:
        if subject.identity_type is IdentityType.RIDER:
            return ActorRole.RIDER
        if subject.identity_type is IdentityType.DRIVER:
            return ActorRole.DRIVER
        return ActorRole.SUPPORT

    @staticmethod
    def _owned(
        repository: Any,
        subject: AuthorizationSubject,
        ride_id: UUID,
        *,
        driver_only: bool = False,
    ) -> ActiveRide:
        ride = cast(ActiveRide | None, repository.get(ride_id))
        if ride is None:
            raise ActiveRideConflict("ride_not_found")
        if driver_only:
            if (
                subject.identity_type is not IdentityType.DRIVER
                or ride.driver_id != subject.identity_id
            ):
                raise ActiveRideConflict("access_denied")
        elif subject.identity_id not in {
            ride.rider_id,
            ride.driver_id,
        } and subject.identity_type not in {
            IdentityType.STAFF,
            IdentityType.ADMINISTRATOR,
            IdentityType.SERVICE,
        }:
            raise ActiveRideConflict("access_denied")
        return ride
