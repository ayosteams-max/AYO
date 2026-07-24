import hashlib
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome
from BACKEND.identity.compatibility_models import AccountLifecycle
from BACKEND.persistence.account_access_repository import (
    PostgresAccountAccessRepository,
)
from BACKEND.persistence.audit_repository import PostgresAuditEventRepository
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
from BACKEND.persistence.service_area_repository import PostgresServiceAreaRepository
from BACKEND.persistence.trace import TraceContext
from BACKEND.persistence.unit_of_work import SqlAlchemyUnitOfWork
from BACKEND.service_area.engine import transition_service_area
from BACKEND.service_area.models import (
    AvailabilityEvaluation,
    AvailabilityOutcome,
    ProductAvailability,
    ProductAvailabilityState,
    RideProductCode,
    ServiceArea,
    ServiceAreaGeometry,
    ServiceAreaState,
)


class ServiceAreaAuthorizationError(PermissionError):
    pass


class CreateServiceArea(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    internal_name: str = Field(min_length=1, max_length=128)
    customer_safe_label: str | None = Field(default=None, max_length=128)
    effective_from: datetime | None = None
    effective_until: datetime | None = None


class RecordBoundary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    boundary_wkt: str = Field(min_length=16, max_length=1_000_000)
    srid: int = 4326
    provenance: str = Field(min_length=1, max_length=256)


class ConfigureProductAvailability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    product_code: RideProductCode
    state: ProductAvailabilityState
    effective_from: datetime
    effective_until: datetime | None = None
    reason_classification: str = Field(min_length=1, max_length=63)
    provenance: str = Field(min_length=1, max_length=256)


class EvaluatePickupAvailability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    pickup_reference: str = Field(min_length=1, max_length=200)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    product_code: RideProductCode
    intended_service_at: datetime
    ride_request_id: UUID | None = None
    ride_request_version: int | None = Field(default=None, ge=1)
    supersedes_evaluation_id: UUID | None = None


class ServiceAreaUnitOfWork(SqlAlchemyUnitOfWork):
    def __enter__(self) -> "ServiceAreaUnitOfWork":
        super().__enter__()
        return self

    @property
    def service_areas(self) -> PostgresServiceAreaRepository:
        return self.repository("service_areas", PostgresServiceAreaRepository)

    @property
    def accounts(self) -> PostgresAccountAccessRepository:
        return self.repository("accounts", PostgresAccountAccessRepository)

    @property
    def ride_requests(self) -> PostgresRideRequestRepository:
        return self.repository("ride_requests", PostgresRideRequestRepository)

    @property
    def idempotency(self) -> PostgresIdempotencyRepository:
        return self.repository("idempotency", PostgresIdempotencyRepository)

    @property
    def events(self) -> PostgresDomainEventRepository:
        return self.repository("events", PostgresDomainEventRepository)

    @property
    def audit(self) -> PostgresAuditEventRepository:
        return self.repository("audit", PostgresAuditEventRepository)


class ServiceAreaApplicationService:
    """Administrative configuration and pickup-only availability evaluation."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._factories = {
            "service_areas": PostgresServiceAreaRepository,
            "accounts": PostgresAccountAccessRepository,
            "ride_requests": PostgresRideRequestRepository,
            "idempotency": PostgresIdempotencyRepository,
            "events": PostgresDomainEventRepository,
            "outbox": PostgresTransactionalOutboxRepository,
            "audit": PostgresAuditEventRepository,
        }

    def _uow(self) -> ServiceAreaUnitOfWork:
        return ServiceAreaUnitOfWork(self._engine, self._factories)

    def create(
        self,
        *,
        actor_account_id: UUID,
        command: CreateServiceArea,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> ServiceArea:
        instant = self._at(at)
        with self._uow() as unit:
            self._authorize(
                unit, actor_account_id, "mobility.service_area.create", instant
            )
            reservation = self._reserve(
                unit,
                actor_account_id,
                "create",
                command,
                idempotency_key,
                trace,
                instant,
            )
            if reservation.completed_at:
                if reservation.response_reference is None:
                    raise RuntimeError(
                        "Completed Service Area result reference unavailable"
                    )
                area = unit.service_areas.get(
                    UUID(reservation.response_reference.rsplit("/", 1)[-1])
                )
                if area is None:
                    raise RuntimeError("Completed Service Area result unavailable")
                return area
            area = unit.service_areas.create(
                ServiceArea(
                    service_area_id=uuid4(),
                    internal_name=command.internal_name,
                    customer_safe_label=command.customer_safe_label,
                    effective_from=command.effective_from,
                    effective_until=command.effective_until,
                    created_at=instant,
                    updated_at=instant,
                )
            )
            self._record(
                unit,
                trace,
                actor_account_id,
                area.service_area_id,
                area.version,
                "mobility.service_area_created",
                idempotency_key,
                instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"service_area/{area.service_area_id}",
                completed_at=instant,
            )
            return area

    def transition(
        self,
        *,
        actor_account_id: UUID,
        service_area_id: UUID,
        target: ServiceAreaState,
        expected_version: int,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> ServiceArea:
        instant = self._at(at)
        event = {
            ServiceAreaState.APPROVED: "mobility.service_area_approved",
            ServiceAreaState.ACTIVE: "mobility.service_area_activated",
            ServiceAreaState.TEMPORARILY_SUSPENDED: "mobility.service_area_suspended",
            ServiceAreaState.RETIRED: "mobility.service_area_retired",
        }.get(target)
        if event is None:
            raise ValueError("Target transition is not an administrative command")
        with self._uow() as unit:
            self._authorize(
                unit, actor_account_id, "mobility.service_area.manage", instant
            )
            area = unit.service_areas.get(service_area_id)
            if area is None:
                raise LookupError("Service Area does not exist")
            if (
                target is ServiceAreaState.ACTIVE
                and unit.service_areas.current_geometry(service_area_id) is None
            ):
                raise ValueError(
                    "Service Area requires boundary geometry before activation"
                )
            payload = f"{service_area_id}:{target.value}:{expected_version}"
            reservation = self._reserve_raw(
                unit,
                actor_account_id,
                f"transition.{target.value}",
                payload,
                idempotency_key,
                trace,
                instant,
            )
            if reservation.completed_at:
                current = unit.service_areas.get(service_area_id)
                if current is None:
                    raise RuntimeError("Completed Service Area result unavailable")
                return current
            if area.version != expected_version:
                raise ValueError("Stale Service Area version")
            saved = unit.service_areas.save(
                transition_service_area(area, target, at=instant),
                expected_version=expected_version,
            )
            self._record(
                unit,
                trace,
                actor_account_id,
                service_area_id,
                saved.version,
                event,
                idempotency_key,
                instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"service_area/{service_area_id}",
                completed_at=instant,
            )
            return saved

    def record_boundary(
        self,
        *,
        actor_account_id: UUID,
        service_area_id: UUID,
        geometry_version: int,
        command: RecordBoundary,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> ServiceAreaGeometry:
        instant = self._at(at)
        with self._uow() as unit:
            self._authorize(
                unit, actor_account_id, "mobility.service_area.manage", instant
            )
            if unit.service_areas.get(service_area_id) is None:
                raise LookupError("Service Area does not exist")
            reservation = self._reserve(
                unit,
                actor_account_id,
                "geometry",
                command,
                idempotency_key,
                trace,
                instant,
            )
            if reservation.completed_at:
                geometry = unit.service_areas.current_geometry(service_area_id)
                if geometry is None:
                    raise RuntimeError("Completed geometry result unavailable")
                return geometry
            geometry = unit.service_areas.add_geometry(
                geometry_id=uuid4(),
                service_area_id=service_area_id,
                geometry_version=geometry_version,
                boundary_wkt=command.boundary_wkt,
                srid=command.srid,
                provenance=command.provenance,
                recorded_at=instant,
            )
            self._record(
                unit,
                trace,
                actor_account_id,
                service_area_id,
                geometry.geometry_version,
                "mobility.service_area_geometry_recorded",
                idempotency_key,
                instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"service_area_geometry/{geometry.geometry_id}",
                completed_at=instant,
            )
            return geometry

    def configure_product(
        self,
        *,
        actor_account_id: UUID,
        service_area_id: UUID,
        command: ConfigureProductAvailability,
        expected_version: int | None,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> ProductAvailability:
        instant = self._at(at)
        with self._uow() as unit:
            self._authorize(
                unit, actor_account_id, "mobility.service_area.manage", instant
            )
            if unit.service_areas.get(service_area_id) is None:
                raise LookupError("Service Area does not exist")
            reservation = self._reserve(
                unit,
                actor_account_id,
                "product",
                command,
                idempotency_key,
                trace,
                instant,
            )
            if reservation.completed_at:
                current = unit.service_areas.get_availability(
                    service_area_id, command.product_code
                )
                if current is None:
                    raise RuntimeError("Completed product availability unavailable")
                return current
            availability = ProductAvailability(
                availability_id=uuid4(),
                service_area_id=service_area_id,
                product_code=command.product_code,
                state=command.state,
                effective_from=command.effective_from,
                effective_until=command.effective_until,
                reason_classification=command.reason_classification,
                provenance=command.provenance,
                version=1 if expected_version is None else expected_version + 1,
                created_at=instant,
                updated_at=instant,
            )
            saved = unit.service_areas.put_availability(
                availability, expected_version=expected_version
            )
            event = (
                "mobility.product_availability_assigned"
                if expected_version is None
                else "mobility.product_availability_changed"
            )
            self._record(
                unit,
                trace,
                actor_account_id,
                service_area_id,
                saved.version,
                event,
                idempotency_key,
                instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"product_availability/{saved.availability_id}",
                completed_at=instant,
            )
            return saved

    def evaluate_pickup(
        self,
        *,
        actor_account_id: UUID,
        command: EvaluatePickupAvailability,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> AvailabilityEvaluation:
        instant = self._at(at)
        with self._uow() as unit:
            self._authorize(
                unit, actor_account_id, "mobility.service_area.evaluate", instant
            )
            if command.ride_request_id is not None:
                ride = unit.ride_requests.get_mobility(command.ride_request_id)
                if ride is None or ride.version != command.ride_request_version:
                    raise ValueError("Ride Request reference is missing or stale")
                if ride.pickup_reference != command.pickup_reference:
                    raise ValueError(
                        "Evaluation pickup must match immutable Ride Request intent"
                    )
            evidence = unit.service_areas.evaluate(
                longitude=command.longitude,
                latitude=command.latitude,
                product_code=command.product_code,
                intended_at=command.intended_service_at,
            )
            evaluation = AvailabilityEvaluation(
                evaluation_id=uuid4(),
                ride_request_id=command.ride_request_id,
                ride_request_version=command.ride_request_version,
                pickup_reference=command.pickup_reference,
                product_code=command.product_code,
                intended_service_at=command.intended_service_at,
                evaluated_at=instant,
                correlation_id=trace.correlation_id,
                request_id=trace.request_id,
                command_id=trace.command_id,
                supersedes_evaluation_id=command.supersedes_evaluation_id,
                outcome=cast(AvailabilityOutcome, evidence["outcome"]),
                service_area_id=cast(UUID | None, evidence.get("service_area_id")),
                service_area_version=cast(
                    int | None, evidence.get("service_area_version")
                ),
                geometry_id=cast(UUID | None, evidence.get("geometry_id")),
                geometry_version=cast(int | None, evidence.get("geometry_version")),
                availability_id=cast(UUID | None, evidence.get("availability_id")),
                availability_version=cast(
                    int | None, evidence.get("availability_version")
                ),
            )
            return unit.service_areas.append_evaluation(evaluation)

    @staticmethod
    def _authorize(
        unit: ServiceAreaUnitOfWork, account_id: UUID, permission: str, at: datetime
    ) -> None:
        account = unit.accounts.get_account(account_id)
        if account is None or account.state is not AccountLifecycle.ACTIVE:
            raise ServiceAreaAuthorizationError("Active canonical Account required")
        if not unit.accounts.has_permission(account_id, permission, at=at):
            raise ServiceAreaAuthorizationError("Administrative permission required")

    def _reserve(
        self,
        unit: ServiceAreaUnitOfWork,
        actor: UUID,
        operation: str,
        command: BaseModel,
        key: str,
        trace: TraceContext,
        at: datetime,
    ) -> IdempotencyRecord:
        return self._reserve_raw(
            unit, actor, operation, command.model_dump_json(), key, trace, at
        )

    @staticmethod
    def _reserve_raw(
        unit: ServiceAreaUnitOfWork,
        actor: UUID,
        operation: str,
        material: str,
        key: str,
        trace: TraceContext,
        at: datetime,
    ) -> IdempotencyRecord:
        if trace.command_id is None:
            raise ValueError("Service Area mutation requires command identifier")
        return unit.idempotency.reserve(
            IdempotencyRecord(
                scope=f"mobility.service_area.{operation}",
                actor_reference=str(actor),
                idempotency_key=key,
                request_hash=canonical_request_hash(material.encode()),
                command_id=trace.command_id,
                correlation_id=trace.correlation_id,
                request_id=trace.request_id,
                created_at=at,
            )
        )

    @staticmethod
    def _record(
        unit: ServiceAreaUnitOfWork,
        trace: TraceContext,
        actor: UUID,
        area_id: UUID,
        version: int,
        event_type: str,
        key: str,
        at: datetime,
    ) -> None:
        derived = hashlib.sha256(f"{event_type}:{key}".encode()).hexdigest()[:32]
        unit.events.append(
            DomainEvent(
                event_type=event_type,
                aggregate_type="mobility.service_area",
                aggregate_id=str(area_id),
                source_module="service_area",
                schema_version=1,
                occurred_at=at,
                payload={"version": version},
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
                actor_type=ActorType.ADMINISTRATOR,
                actor_id=str(actor),
                action=event_type,
                resource_type="mobility_service_area",
                resource_id=str(area_id),
                outcome=AuditOutcome.SUCCESS,
                correlation_id=trace.correlation_id,
                causation_id=trace.causation_id,
                request_id=trace.request_id,
                source_module="service_area",
                safe_metadata={"category": "mobility", "operation": event_type},
                idempotency_key=f"audit-{derived}",
            )
        )

    @staticmethod
    def _at(value: datetime | None) -> datetime:
        instant = value or datetime.now(UTC)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware")
        return instant.astimezone(UTC)
