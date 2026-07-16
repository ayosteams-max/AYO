from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Protocol, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from BACKEND.active_ride.models import ActiveRide, ActiveRideState
from BACKEND.arrival_waiting.engine import (
    ArrivalWaitingConflict,
    evaluate_arrival,
    evaluate_evidence,
    evaluate_readiness,
    evaluate_waiting_continuity,
    resolve_waiting_policy,
    start_waiting,
)
from BACKEND.arrival_waiting.models import (
    ArrivalPolicy,
    ArrivalSignals,
    ContinuitySignals,
    LandmarkReference,
    ReadinessPolicy,
    ReadinessSignals,
    WaitingPolicyContext,
    WaitingPolicyDefinition,
    WalkingGuidance,
    WalkingGuidanceRequest,
)
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType


class ArrivalWaitingUnitOfWork(Protocol):
    active_rides: Any
    arrival_waiting: Any

    def __enter__(self) -> "ArrivalWaitingUnitOfWork": ...
    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


class UowFactory(Protocol):
    def __call__(self) -> ArrivalWaitingUnitOfWork: ...


class LandmarkProvider(Protocol):
    def get(self, landmark_id: UUID, *, now: datetime) -> LandmarkReference | None: ...


class NoLandmarkProvider:
    def get(self, landmark_id: UUID, *, now: datetime) -> LandmarkReference | None:
        del landmark_id, now
        return None


class WalkingGuidanceProvider(Protocol):
    def route(
        self, request: WalkingGuidanceRequest, *, now: datetime
    ) -> WalkingGuidance | None: ...


class NoWalkingGuidanceProvider:
    def route(
        self, request: WalkingGuidanceRequest, *, now: datetime
    ) -> WalkingGuidance | None:
        del request, now
        return None


class ArrivalCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    command_id: UUID
    expected_ride_version: int = Field(ge=1)
    signals: ArrivalSignals


class ReadinessCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    command_id: UUID
    signals: ReadinessSignals
    prior_notification_at: datetime | None = None
    notification_count: int = Field(default=0, ge=0, le=20)


class StartWaitingCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    command_id: UUID
    expected_ride_version: int = Field(ge=1)
    context: WaitingPolicyContext


class ContinuityCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    command_id: UUID
    expected_session_version: int = Field(ge=1)
    observation_sequence: int = Field(ge=0)
    signals: ContinuitySignals


class EvidenceCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    command_id: UUID
    expected_session_version: int = Field(ge=1)
    signals: ContinuitySignals


class RiderPresentCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    command_id: UUID
    expected_session_version: int = Field(ge=1)


class ArrivalWaitingApplication:
    def __init__(
        self,
        uow_factory: UowFactory,
        *,
        arrival_policy: ArrivalPolicy,
        readiness_policy: ReadinessPolicy,
        waiting_policies: tuple[WaitingPolicyDefinition, ...],
        landmarks: LandmarkProvider | None = None,
        walking_guidance: WalkingGuidanceProvider | None = None,
    ) -> None:
        if not waiting_policies:
            raise ValueError(
                "At least one externally configured waiting policy is required"
            )
        self._uow_factory = uow_factory
        self._arrival_policy = arrival_policy
        self._readiness_policy = readiness_policy
        self._waiting_policies = waiting_policies
        self._landmarks = landmarks or NoLandmarkProvider()
        self._walking_guidance = walking_guidance or NoWalkingGuidanceProvider()

    def arrival(self, subject: AuthorizationSubject, ride_id: UUID) -> dict[str, Any]:
        with self._uow_factory() as unit:
            self._owned(unit, subject, ride_id)
            item = unit.arrival_waiting.latest_arrival(ride_id)
            return (
                {"state": "arrival_unverified"} if item is None else self._public(item)
            )

    def readiness(self, subject: AuthorizationSubject, ride_id: UUID) -> dict[str, Any]:
        with self._uow_factory() as unit:
            self._owned(unit, subject, ride_id)
            item = unit.arrival_waiting.latest_readiness(ride_id)
            return (
                {"classification": "insufficient_data"}
                if item is None
                else self._public(item)
            )

    def waiting(
        self, subject: AuthorizationSubject, ride_id: UUID, *, now: datetime
    ) -> dict[str, Any]:
        with self._uow_factory() as unit:
            self._owned(unit, subject, ride_id)
            item = unit.arrival_waiting.latest_session(ride_id)
            if item is None:
                return {
                    "state": "not_started",
                    "audience": self._countdown_audience(subject),
                }
            result = self._public(item)
            result["audience"] = self._countdown_audience(subject)
            result["server_time"] = now.isoformat()
            result["countdown_seconds"] = max(
                0, int((item.free_wait_deadline - now).total_seconds())
            )
            return result

    def evidence(self, subject: AuthorizationSubject, ride_id: UUID) -> dict[str, Any]:
        with self._uow_factory() as unit:
            self._owned(unit, subject, ride_id)
            item = unit.arrival_waiting.latest_evidence(ride_id)
            return (
                {"ready": False, "responsibility": "insufficient_evidence"}
                if item is None
                else self._public(item)
            )

    def submit_arrival(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        command: ArrivalCommand,
        *,
        now: datetime,
    ) -> dict[str, Any]:
        self._driver(subject)
        payload = command.model_dump(mode="json")
        with self._uow_factory() as unit:
            ride = self._owned(unit, subject, ride_id, driver_only=True, lock=True)
            duplicate = unit.arrival_waiting.idempotent_response(
                actor_id=subject.identity_id,
                command_id=command.command_id,
                ride_id=ride_id,
                command_type="submit_arrival",
                request_payload=payload,
            )
            if duplicate is not None:
                return cast(dict[str, Any], duplicate)
            if ride.version != command.expected_ride_version:
                raise ArrivalWaitingConflict("stale_ride_version")
            if ride.state not in {
                ActiveRideState.DRIVER_EN_ROUTE,
                ActiveRideState.DRIVER_ARRIVED,
            }:
                raise ArrivalWaitingConflict("ride_not_arrival_eligible")
            if (
                ride.assignment_id is None
                or command.signals.approved_pickup_place_id != ride.pickup_place_id
            ):
                raise ArrivalWaitingConflict("pickup_or_assignment_mismatch")
            item = evaluate_arrival(
                ride_id,
                ride.assignment_id,
                command.signals,
                self._arrival_policy,
                now=now,
            )
            unit.arrival_waiting.save_arrival(item)
            response = self._public(item)
            self._save_command(
                unit,
                subject,
                command.command_id,
                ride_id,
                "submit_arrival",
                payload,
                response,
                now,
            )
            return response

    def evaluate_rider_readiness(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        command: ReadinessCommand,
        *,
        now: datetime,
    ) -> dict[str, Any]:
        payload = command.model_dump(mode="json")
        with self._uow_factory() as unit:
            self._owned(unit, subject, ride_id)
            duplicate = unit.arrival_waiting.idempotent_response(
                actor_id=subject.identity_id,
                command_id=command.command_id,
                ride_id=ride_id,
                command_type="evaluate_readiness",
                request_payload=payload,
            )
            if duplicate is not None:
                return cast(dict[str, Any], duplicate)
            item = evaluate_readiness(
                ride_id,
                command.signals,
                self._readiness_policy,
                now=now,
                prior_notification_at=command.prior_notification_at,
                notification_count=command.notification_count,
            )
            unit.arrival_waiting.save_readiness(item)
            response = self._public(item)
            self._save_command(
                unit,
                subject,
                command.command_id,
                ride_id,
                "evaluate_readiness",
                payload,
                response,
                now,
            )
            return response

    def start(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        command: StartWaitingCommand,
        *,
        now: datetime,
    ) -> dict[str, Any]:
        self._driver(subject)
        payload = command.model_dump(mode="json")
        with self._uow_factory() as unit:
            ride = self._owned(unit, subject, ride_id, driver_only=True, lock=True)
            duplicate = unit.arrival_waiting.idempotent_response(
                actor_id=subject.identity_id,
                command_id=command.command_id,
                ride_id=ride_id,
                command_type="start_waiting",
                request_payload=payload,
            )
            if duplicate is not None:
                return cast(dict[str, Any], duplicate)
            if ride.version != command.expected_ride_version:
                raise ArrivalWaitingConflict("stale_ride_version")
            if unit.arrival_waiting.latest_session(ride_id, lock=True) is not None:
                raise ArrivalWaitingConflict("waiting_already_started")
            arrival = unit.arrival_waiting.latest_arrival(ride_id)
            if arrival is None or ride.assignment_id is None:
                raise ArrivalWaitingConflict("arrival_not_verified")
            snapshot = resolve_waiting_policy(
                ride_id, command.context, self._waiting_policies, now=now
            )
            item = start_waiting(
                ride_id, ride.assignment_id, arrival, snapshot, now=now
            )
            unit.arrival_waiting.save_snapshot(snapshot)
            unit.arrival_waiting.create_session(item)
            response = self._public(item)
            self._save_command(
                unit,
                subject,
                command.command_id,
                ride_id,
                "start_waiting",
                payload,
                response,
                now,
            )
            return response

    def continuity(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        command: ContinuityCommand,
        *,
        now: datetime,
    ) -> dict[str, Any]:
        self._driver(subject)
        payload = command.model_dump(mode="json")
        with self._uow_factory() as unit:
            self._owned(unit, subject, ride_id, driver_only=True, lock=True)
            duplicate = unit.arrival_waiting.idempotent_response(
                actor_id=subject.identity_id,
                command_id=command.command_id,
                ride_id=ride_id,
                command_type="waiting_continuity",
                request_payload=payload,
            )
            if duplicate is not None:
                return cast(dict[str, Any], duplicate)
            session = unit.arrival_waiting.latest_session(ride_id, lock=True)
            if session is None:
                raise ArrivalWaitingConflict("waiting_not_started")
            if session.version != command.expected_session_version:
                raise ArrivalWaitingConflict("stale_waiting_session")
            snapshot = unit.arrival_waiting.get_snapshot(session.policy_snapshot_id)
            if snapshot is None:
                raise ArrivalWaitingConflict("waiting_policy_snapshot_missing")
            changed = evaluate_waiting_continuity(
                session,
                snapshot,
                command.signals,
                observation_sequence=command.observation_sequence,
                now=now,
            )
            unit.arrival_waiting.update_session(
                changed, expected_version=session.version
            )
            response = self._public(changed)
            self._save_command(
                unit,
                subject,
                command.command_id,
                ride_id,
                "waiting_continuity",
                payload,
                response,
                now,
            )
            return response

    def rider_present(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        command: RiderPresentCommand,
        *,
        now: datetime,
    ) -> dict[str, Any]:
        if subject.identity_type is not IdentityType.RIDER:
            raise ArrivalWaitingConflict("rider_required")
        payload = command.model_dump(mode="json")
        with self._uow_factory() as unit:
            self._owned(unit, subject, ride_id, lock=True)
            duplicate = unit.arrival_waiting.idempotent_response(
                actor_id=subject.identity_id,
                command_id=command.command_id,
                ride_id=ride_id,
                command_type="rider_present",
                request_payload=payload,
            )
            if duplicate is not None:
                return cast(dict[str, Any], duplicate)
            session = unit.arrival_waiting.latest_session(ride_id, lock=True)
            if session is None or session.version != command.expected_session_version:
                raise ArrivalWaitingConflict("stale_waiting_session")
            response = {"confirmed": True, "recorded_at": now.isoformat()}
            unit.arrival_waiting.record_notification(
                ride_id=ride_id,
                session_id=session.session_id,
                intent_type="rider_present_confirmation",
                delivery_status="confirmed",
                reason_code="waiting.rider_present_confirmed",
                occurred_at=now,
            )
            self._save_command(
                unit,
                subject,
                command.command_id,
                ride_id,
                "rider_present",
                payload,
                response,
                now,
            )
            return response

    def evaluate_no_show(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        command: EvidenceCommand,
        *,
        now: datetime,
    ) -> dict[str, Any]:
        self._driver(subject)
        payload = command.model_dump(mode="json")
        with self._uow_factory() as unit:
            self._owned(unit, subject, ride_id, driver_only=True, lock=True)
            duplicate = unit.arrival_waiting.idempotent_response(
                actor_id=subject.identity_id,
                command_id=command.command_id,
                ride_id=ride_id,
                command_type="evaluate_no_show",
                request_payload=payload,
            )
            if duplicate is not None:
                return cast(dict[str, Any], duplicate)
            session = unit.arrival_waiting.latest_session(ride_id, lock=True)
            if session is None or session.version != command.expected_session_version:
                raise ArrivalWaitingConflict("stale_waiting_session")
            snapshot = unit.arrival_waiting.get_snapshot(session.policy_snapshot_id)
            if snapshot is None:
                raise ArrivalWaitingConflict("waiting_policy_snapshot_missing")
            item = evaluate_evidence(session, snapshot, command.signals, now=now)
            unit.arrival_waiting.save_evidence(item)
            response = self._public(item)
            self._save_command(
                unit,
                subject,
                command.command_id,
                ride_id,
                "evaluate_no_show",
                payload,
                response,
                now,
            )
            return response

    def landmark(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        landmark_id: UUID,
        *,
        now: datetime,
    ) -> dict[str, Any]:
        with self._uow_factory() as unit:
            self._owned(unit, subject, ride_id)
        item = self._landmarks.get(landmark_id, now=now)
        if (
            item is None
            or item.expires_at <= now
            or item.ambiguous
            or item.user_submission_unverified
        ):
            return {
                "landmark_id": str(landmark_id),
                "status": "coordinates_fallback",
                "reason_code": "landmark.ambiguous_or_unverified",
            }
        return {
            "landmark_id": str(item.landmark_id),
            "status": "verified_guidance",
            "canonical_name_en": item.canonical_name_en,
            "canonical_name_am": item.canonical_name_am,
            "entrance_or_gate": item.entrance_or_gate,
            "terminal_code": item.terminal_code,
            "side_of_road_guidance": item.side_of_road_guidance,
            "confidence_bps": item.confidence_bps,
            "provenance_code": item.provenance_code,
            "named_pickup_points": [
                point.model_dump(mode="json", exclude={"reference_photo"})
                | {
                    "reference_photo": (
                        None
                        if point.reference_photo is None
                        else point.reference_photo.model_dump(mode="json")
                    )
                }
                for point in item.named_pickup_points
            ],
        }

    def walking_guidance(
        self,
        subject: AuthorizationSubject,
        ride_id: UUID,
        request: WalkingGuidanceRequest,
        *,
        now: datetime,
    ) -> dict[str, Any]:
        with self._uow_factory() as unit:
            self._owned(unit, subject, ride_id)
        if subject.identity_type is not IdentityType.RIDER:
            raise ArrivalWaitingConflict("rider_required")
        guidance = self._walking_guidance.route(request, now=now)
        if guidance is None or guidance.expires_at <= now:
            return {
                "status": "guidance_unavailable",
                "reason_code": "walking_guidance.provider_or_freshness_unavailable",
            }
        return {"status": "guidance_available", **self._public(guidance)}

    def _owned(
        self,
        unit: ArrivalWaitingUnitOfWork,
        subject: AuthorizationSubject,
        ride_id: UUID,
        *,
        driver_only: bool = False,
        lock: bool = False,
    ) -> ActiveRide:
        ride = unit.active_rides.get(ride_id, lock=lock)
        if ride is None:
            raise ArrivalWaitingConflict("ride_not_found")
        if driver_only:
            allowed = (
                subject.identity_type is IdentityType.DRIVER
                and ride.driver_id == subject.identity_id
            )
        else:
            allowed = (
                subject.identity_type is IdentityType.RIDER
                and ride.rider_id == subject.identity_id
            ) or (
                subject.identity_type is IdentityType.DRIVER
                and ride.driver_id == subject.identity_id
            )
            allowed = allowed or subject.identity_type in {
                IdentityType.STAFF,
                IdentityType.ADMINISTRATOR,
            }
        if not allowed:
            raise ArrivalWaitingConflict("access_denied")
        return cast(ActiveRide, ride)

    @staticmethod
    def _driver(subject: AuthorizationSubject) -> None:
        if subject.identity_type is not IdentityType.DRIVER:
            raise ArrivalWaitingConflict("driver_required")

    @staticmethod
    def _countdown_audience(subject: AuthorizationSubject) -> str:
        if subject.identity_type is IdentityType.RIDER:
            return "rider"
        if subject.identity_type is IdentityType.DRIVER:
            return "driver"
        return "support"

    @staticmethod
    def _public(item: BaseModel) -> dict[str, Any]:
        result = item.model_dump(mode="json")
        for prohibited in (
            "latitude_e6",
            "longitude_e6",
            "raw_location",
            "fee",
            "amount",
            "wallet",
        ):
            result.pop(prohibited, None)
        return result

    @staticmethod
    def _save_command(
        unit: ArrivalWaitingUnitOfWork,
        subject: AuthorizationSubject,
        command_id: UUID,
        ride_id: UUID,
        command_type: str,
        request: dict[str, Any],
        response: dict[str, Any],
        now: datetime,
    ) -> None:
        unit.arrival_waiting.save_idempotent_response(
            actor_id=subject.identity_id,
            command_id=command_id,
            ride_id=ride_id,
            command_type=command_type,
            request_payload=request,
            response_payload=response,
            now=now.astimezone(UTC),
        )
