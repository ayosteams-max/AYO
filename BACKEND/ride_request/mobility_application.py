import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome
from BACKEND.identity.compatibility_models import AccountLifecycle, IdentityAccount
from BACKEND.persistence.account_access_repository import (
    PostgresAccountAccessRepository,
)
from BACKEND.persistence.audit_repository import PostgresAuditEventRepository
from BACKEND.persistence.customer_profile_repository import (
    PostgresCustomerProfileRepository,
)
from BACKEND.persistence.kernel_models import (
    DomainEvent,
    IdempotencyRecord,
    canonical_request_hash,
)
from BACKEND.persistence.kernel_repository import (
    PostgresDomainEventRepository,
    PostgresIdempotencyRepository,
    PostgresTransactionalOutboxRepository,
)
from BACKEND.persistence.ride_request_repository import PostgresRideRequestRepository
from BACKEND.persistence.trace import TraceContext
from BACKEND.persistence.unit_of_work import SqlAlchemyUnitOfWork
from BACKEND.ride_request.engine import transition_mobility_request
from BACKEND.ride_request.models import (
    LocationReference,
    MobilityRideRequestState,
    PassengerMobilityRideRequest,
    RideIntentPreferences,
    ScheduleIntentType,
)


class RideRequestAuthorizationError(PermissionError):
    pass


class CreatePassengerMobilityRideRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    client_request_id: UUID
    passenger_subject_id: UUID
    pickup_reference: LocationReference
    destination_reference: LocationReference
    stop_references: tuple[LocationReference, ...] = Field(default=(), max_length=8)
    schedule_intent: ScheduleIntentType
    scheduled_for: datetime | None = None
    passenger_count: int = Field(ge=1, le=8)
    preferences: RideIntentPreferences = Field(default_factory=RideIntentPreferences)
    expires_at: datetime


class PassengerMobilityUnitOfWork(SqlAlchemyUnitOfWork):
    def __enter__(self) -> "PassengerMobilityUnitOfWork":
        super().__enter__()
        return self

    @property
    def ride_requests(self) -> PostgresRideRequestRepository:
        return self.repository("ride_requests", PostgresRideRequestRepository)

    @property
    def accounts(self) -> PostgresAccountAccessRepository:
        return self.repository("accounts", PostgresAccountAccessRepository)

    @property
    def profiles(self) -> PostgresCustomerProfileRepository:
        return self.repository("profiles", PostgresCustomerProfileRepository)

    @property
    def idempotency(self) -> PostgresIdempotencyRepository:
        return self.repository("idempotency", PostgresIdempotencyRepository)

    @property
    def events(self) -> PostgresDomainEventRepository:
        return self.repository("events", PostgresDomainEventRepository)

    @property
    def audit(self) -> PostgresAuditEventRepository:
        return self.repository("audit", PostgresAuditEventRepository)


class PassengerMobilityRideRequestService:
    """R1 canonical travel-intent application boundary."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._factories = {
            "ride_requests": PostgresRideRequestRepository,
            "accounts": PostgresAccountAccessRepository,
            "profiles": PostgresCustomerProfileRepository,
            "idempotency": PostgresIdempotencyRepository,
            "events": PostgresDomainEventRepository,
            "outbox": PostgresTransactionalOutboxRepository,
            "audit": PostgresAuditEventRepository,
        }

    def _uow(self) -> PassengerMobilityUnitOfWork:
        return PassengerMobilityUnitOfWork(self._engine, self._factories)

    def create_draft(
        self,
        *,
        actor_account_id: UUID,
        command: CreatePassengerMobilityRideRequest,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> PassengerMobilityRideRequest:
        instant = self._at(at)
        command_id = self._command_id(trace)
        material = command.model_dump_json()
        with self._uow() as unit:
            actor = self._active_account(unit, actor_account_id)
            self._require_passenger_authority(
                unit, actor.subject_id, command.passenger_subject_id
            )
            reservation = unit.idempotency.reserve(
                IdempotencyRecord(
                    scope="mobility.ride_request.create",
                    actor_reference=str(actor_account_id),
                    idempotency_key=idempotency_key,
                    request_hash=canonical_request_hash(material.encode()),
                    command_id=command_id,
                    correlation_id=trace.correlation_id,
                    request_id=trace.request_id,
                    created_at=instant,
                )
            )
            if reservation.completed_at is not None:
                return self._completed_request(unit, reservation)
            request = PassengerMobilityRideRequest(
                request_id=uuid4(),
                client_request_id=command.client_request_id,
                requester_subject_id=actor.subject_id,
                passenger_subject_id=command.passenger_subject_id,
                pickup_reference=command.pickup_reference,
                destination_reference=command.destination_reference,
                stop_references=command.stop_references,
                schedule_intent=command.schedule_intent,
                scheduled_for=command.scheduled_for,
                passenger_count=command.passenger_count,
                preferences=command.preferences,
                created_at=instant,
                updated_at=instant,
                expires_at=command.expires_at,
            )
            created = unit.ride_requests.create_mobility(request)
            self._record(
                unit,
                trace,
                created,
                event_type="mobility.ride_request_created",
                actor_account_id=actor_account_id,
                actor_type=ActorType.RIDER,
                key=idempotency_key,
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"mobility_ride_request/{created.request_id}",
                completed_at=instant,
            )
            return created

    def validate(
        self,
        *,
        actor_account_id: UUID,
        request_id: UUID,
        expected_version: int,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
        administrative_override: bool = False,
    ) -> PassengerMobilityRideRequest:
        return self._transition(
            actor_account_id=actor_account_id,
            request_id=request_id,
            expected_version=expected_version,
            target=MobilityRideRequestState.VALIDATED,
            event_type="mobility.ride_request_validated",
            idempotency_key=idempotency_key,
            trace=trace,
            at=at,
            administrative_override=administrative_override,
            revalidate=True,
        )

    def submit(
        self,
        *,
        actor_account_id: UUID,
        request_id: UUID,
        expected_version: int,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
        administrative_override: bool = False,
    ) -> PassengerMobilityRideRequest:
        return self._transition(
            actor_account_id=actor_account_id,
            request_id=request_id,
            expected_version=expected_version,
            target=MobilityRideRequestState.SUBMITTED,
            event_type="mobility.ride_request_submitted",
            idempotency_key=idempotency_key,
            trace=trace,
            at=at,
            administrative_override=administrative_override,
            revalidate=True,
        )

    def withdraw(
        self,
        *,
        actor_account_id: UUID,
        request_id: UUID,
        expected_version: int,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
        administrative_override: bool = False,
    ) -> PassengerMobilityRideRequest:
        return self._transition(
            actor_account_id=actor_account_id,
            request_id=request_id,
            expected_version=expected_version,
            target=MobilityRideRequestState.WITHDRAWN,
            event_type="mobility.ride_request_withdrawn",
            idempotency_key=idempotency_key,
            trace=trace,
            at=at,
            administrative_override=administrative_override,
        )

    def expire(
        self,
        *,
        actor_account_id: UUID,
        request_id: UUID,
        expected_version: int,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
        administrative_override: bool = False,
    ) -> PassengerMobilityRideRequest:
        instant = self._at(at)
        with self._uow() as unit:
            request = unit.ride_requests.get_mobility(request_id)
            if request is None:
                raise LookupError("Ride Request does not exist")
            if instant < request.expires_at:
                raise ValueError("Ride Request has not reached expiry")
        return self._transition(
            actor_account_id=actor_account_id,
            request_id=request_id,
            expected_version=expected_version,
            target=MobilityRideRequestState.EXPIRED,
            event_type="mobility.ride_request_expired",
            idempotency_key=idempotency_key,
            trace=trace,
            at=instant,
            administrative_override=administrative_override,
        )

    def get_authorized(
        self,
        *,
        actor_account_id: UUID,
        request_id: UUID,
        administrative_override: bool = False,
        at: datetime | None = None,
    ) -> PassengerMobilityRideRequest:
        instant = self._at(at)
        with self._uow() as unit:
            actor = self._active_account(unit, actor_account_id)
            request = unit.ride_requests.get_mobility(request_id)
            if request is None:
                raise LookupError("Ride Request does not exist")
            allowed = actor.subject_id in {
                request.requester_subject_id,
                request.passenger_subject_id,
            }
            if not allowed:
                allowed = self._administrative_override(
                    unit, actor_account_id, administrative_override, instant
                )
            if not allowed:
                raise RideRequestAuthorizationError("Ride Request access denied")
            return request

    def _transition(
        self,
        *,
        actor_account_id: UUID,
        request_id: UUID,
        expected_version: int,
        target: MobilityRideRequestState,
        event_type: str,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None,
        administrative_override: bool,
        revalidate: bool = False,
    ) -> PassengerMobilityRideRequest:
        instant = self._at(at)
        command_id = self._command_id(trace)
        material = f"{request_id}:{expected_version}:{target.value}"
        with self._uow() as unit:
            actor = self._active_account(unit, actor_account_id)
            request = unit.ride_requests.get_mobility(request_id, lock=True)
            if request is None:
                raise LookupError("Ride Request does not exist")
            override = actor.subject_id != request.requester_subject_id
            if override and not self._administrative_override(
                unit, actor_account_id, administrative_override, instant
            ):
                raise RideRequestAuthorizationError(
                    "Only requester or administrator may change Ride Request"
                )
            reservation = unit.idempotency.reserve(
                IdempotencyRecord(
                    scope=f"mobility.ride_request.{target.value}",
                    actor_reference=str(actor_account_id),
                    idempotency_key=idempotency_key,
                    request_hash=canonical_request_hash(material.encode()),
                    command_id=command_id,
                    correlation_id=trace.correlation_id,
                    request_id=trace.request_id,
                    created_at=instant,
                )
            )
            if reservation.completed_at is not None:
                return self._completed_request(unit, reservation)
            if request.version != expected_version:
                raise ValueError("Stale Ride Request version")
            if revalidate:
                self._validate_current(unit, request, instant)
            transitioned = transition_mobility_request(request, target, at=instant)
            saved = unit.ride_requests.save_mobility(
                transitioned, expected_version=expected_version
            )
            self._record(
                unit,
                trace,
                saved,
                event_type=event_type,
                actor_account_id=actor_account_id,
                actor_type=(ActorType.ADMINISTRATOR if override else ActorType.RIDER),
                key=idempotency_key,
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"mobility_ride_request/{request_id}",
                completed_at=instant,
            )
            return saved

    @staticmethod
    def _active_account(
        unit: PassengerMobilityUnitOfWork, account_id: UUID
    ) -> IdentityAccount:
        account = unit.accounts.get_account(account_id)
        if account is None or account.state is not AccountLifecycle.ACTIVE:
            raise RideRequestAuthorizationError("Active canonical Account required")
        return account

    @staticmethod
    def _require_passenger_authority(
        unit: PassengerMobilityUnitOfWork,
        requester_subject_id: UUID,
        passenger_subject_id: UUID,
    ) -> None:
        if requester_subject_id == passenger_subject_id:
            return
        if (
            unit.profiles.active_relationship_between(
                requester_subject_id, passenger_subject_id
            )
            is None
        ):
            raise RideRequestAuthorizationError(
                "Passenger requires active trusted household relationship"
            )

    def _validate_current(
        self,
        unit: PassengerMobilityUnitOfWork,
        request: PassengerMobilityRideRequest,
        at: datetime,
    ) -> None:
        self._require_passenger_authority(
            unit, request.requester_subject_id, request.passenger_subject_id
        )
        if at >= request.expires_at:
            raise ValueError("Expired Ride Request cannot be validated or submitted")
        if request.schedule_intent is ScheduleIntentType.SCHEDULED and (
            request.scheduled_for is None or request.scheduled_for <= at
        ):
            raise ValueError("Scheduled Ride Request time must be in the future")

    @staticmethod
    def _administrative_override(
        unit: PassengerMobilityUnitOfWork,
        account_id: UUID,
        requested: bool,
        at: datetime,
    ) -> bool:
        return requested and unit.accounts.has_permission(
            account_id, "identity.ownership.override", at=at
        )

    @staticmethod
    def _completed_request(
        unit: PassengerMobilityUnitOfWork, record: IdempotencyRecord
    ) -> PassengerMobilityRideRequest:
        if record.response_reference is None:
            raise RuntimeError("Completed command lacks response reference")
        request = unit.ride_requests.get_mobility(
            UUID(record.response_reference.rsplit("/", 1)[-1])
        )
        if request is None:
            raise RuntimeError("Completed Ride Request result is unavailable")
        return request

    @staticmethod
    def _record(
        unit: PassengerMobilityUnitOfWork,
        trace: TraceContext,
        request: PassengerMobilityRideRequest,
        *,
        event_type: str,
        actor_account_id: UUID,
        actor_type: ActorType,
        key: str,
        at: datetime,
    ) -> None:
        derived = hashlib.sha256(f"{event_type}:{key}".encode()).hexdigest()[:32]
        payload: dict[str, str | int | bool | None] = {
            "state": request.state.value,
            "schedule_intent": request.schedule_intent.value,
            "passenger_count": request.passenger_count,
            "model_version": request.model_version,
        }
        unit.events.append(
            DomainEvent(
                event_type=event_type,
                aggregate_type="mobility.ride_request",
                aggregate_id=str(request.request_id),
                source_module="ride_request",
                schema_version=1,
                occurred_at=at,
                payload=payload,
                correlation_id=trace.correlation_id,
                request_id=trace.request_id,
                command_id=trace.command_id,
                causation_id=trace.causation_id,
                idempotency_key=f"event-{derived}",
            )
        )
        unit.audit.append(
            AuditEvent(
                occurred_at=at,
                actor_type=actor_type,
                actor_id=str(actor_account_id),
                action=event_type,
                resource_type="mobility_ride_request",
                resource_id=str(request.request_id),
                outcome=AuditOutcome.SUCCESS,
                correlation_id=trace.correlation_id,
                causation_id=trace.causation_id,
                request_id=trace.request_id,
                source_module="ride_request",
                safe_metadata={
                    "category": "mobility",
                    "operation": event_type,
                    "state_to": request.state.value,
                },
                idempotency_key=f"audit-{derived}",
            )
        )

    @staticmethod
    def _command_id(trace: TraceContext) -> UUID:
        if trace.command_id is None:
            raise ValueError("Ride Request mutation requires command identifier")
        return trace.command_id

    @staticmethod
    def _at(value: datetime | None) -> datetime:
        instant = value or datetime.now(UTC)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware")
        return instant.astimezone(UTC)
