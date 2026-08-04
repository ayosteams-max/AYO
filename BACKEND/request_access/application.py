import hashlib
from datetime import UTC, datetime, timedelta
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
from BACKEND.persistence.request_access_repository import (
    PostgresRequestAccessRepository,
)
from BACKEND.persistence.trace import TraceContext
from BACKEND.persistence.unit_of_work import SqlAlchemyUnitOfWork
from BACKEND.request_access.models import (
    AccessChannel,
    CapabilityState,
    ChannelActionCapability,
    ContinuityReference,
    InteractionMethod,
    InteractionProvenanceEnvelope,
    InteractionProvenanceRecord,
    ProvenancePurpose,
    SourceAdapter,
)


class RequestAccessAuthorizationError(PermissionError):
    pass


class RegisterSourceAdapter(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    adapter_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,126}$")
    adapter_version: int = Field(ge=1)
    channel: AccessChannel


class DeclareChannelCapability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    target_domain: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,126}$")
    command_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,126}$")
    adapter_id: UUID
    state: CapabilityState
    effective_from: datetime
    effective_until: datetime | None = None


class IssuedContinuityReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    continuity_id: UUID
    reference: str
    expires_at: datetime


class RequestAccessUnitOfWork(SqlAlchemyUnitOfWork):
    def __enter__(self) -> "RequestAccessUnitOfWork":
        super().__enter__()
        return self

    @property
    def request_access(self) -> PostgresRequestAccessRepository:
        return self.repository("request_access", PostgresRequestAccessRepository)

    @property
    def accounts(self) -> PostgresAccountAccessRepository:
        return self.repository("accounts", PostgresAccountAccessRepository)

    @property
    def idempotency(self) -> PostgresIdempotencyRepository:
        return self.repository("idempotency", PostgresIdempotencyRepository)

    @property
    def events(self) -> PostgresDomainEventRepository:
        return self.repository("events", PostgresDomainEventRepository)

    @property
    def audit(self) -> PostgresAuditEventRepository:
        return self.repository("audit", PostgresAuditEventRepository)


class RequestAccessApplicationService:
    """Channel-neutral accepted-interaction evidence service."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._factories = {
            "request_access": PostgresRequestAccessRepository,
            "accounts": PostgresAccountAccessRepository,
            "idempotency": PostgresIdempotencyRepository,
            "events": PostgresDomainEventRepository,
            "outbox": PostgresTransactionalOutboxRepository,
            "audit": PostgresAuditEventRepository,
        }

    def _uow(self) -> RequestAccessUnitOfWork:
        return RequestAccessUnitOfWork(self._engine, self._factories)

    def register_adapter(
        self,
        *,
        actor_account_id: UUID,
        command: RegisterSourceAdapter,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> SourceAdapter:
        instant = self._at(at)
        with self._uow() as unit:
            self._authorize(unit, actor_account_id, "access.provenance.manage", instant)
            reservation = self._reserve(
                unit,
                actor_account_id,
                "adapter.register",
                command.model_dump_json(),
                idempotency_key,
                trace,
                instant,
            )
            if reservation.completed_at:
                adapter = unit.request_access.get_adapter(
                    UUID(reservation.response_reference.rsplit("/", 1)[-1])  # type: ignore[union-attr]
                )
                if adapter is None:
                    raise RuntimeError("Completed adapter result is unavailable")
                return adapter
            adapter = unit.request_access.register_adapter(
                SourceAdapter(
                    adapter_id=uuid4(),
                    adapter_code=command.adapter_code,
                    adapter_version=command.adapter_version,
                    channel=command.channel,
                    active=True,
                    created_at=instant,
                )
            )
            self._record_evidence(
                unit,
                trace=trace,
                actor_account_id=actor_account_id,
                resource_id=adapter.adapter_id,
                aggregate_type="access.source_adapter",
                event_type="access.source_adapter_registered",
                payload={"adapter_version": adapter.adapter_version},
                idempotency_key=idempotency_key,
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"request_access_adapter/{adapter.adapter_id}",
                completed_at=instant,
            )
            return adapter

    def declare_capability(
        self,
        *,
        actor_account_id: UUID,
        command: DeclareChannelCapability,
        expected_version: int | None,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> ChannelActionCapability:
        instant = self._at(at)
        with self._uow() as unit:
            self._authorize(unit, actor_account_id, "access.provenance.manage", instant)
            adapter = unit.request_access.get_adapter(command.adapter_id)
            if adapter is None or not adapter.active:
                raise ValueError("Active registered source adapter required")
            reservation = self._reserve(
                unit,
                actor_account_id,
                "capability.declare",
                command.model_dump_json() + f":{expected_version}",
                idempotency_key,
                trace,
                instant,
            )
            if reservation.completed_at:
                stored = unit.request_access.get_capability(
                    target_domain=command.target_domain,
                    command_type=command.command_type,
                    adapter_id=command.adapter_id,
                )
                if stored is None:
                    raise RuntimeError("Completed capability result is unavailable")
                return stored
            existing = unit.request_access.get_capability(
                target_domain=command.target_domain,
                command_type=command.command_type,
                adapter_id=command.adapter_id,
            )
            if expected_version is None and existing is not None:
                raise ValueError("Capability already exists; expected version required")
            if expected_version is not None and (
                existing is None or existing.version != expected_version
            ):
                raise ValueError("Stale or missing capability version")
            capability = ChannelActionCapability(
                capability_id=existing.capability_id if existing else uuid4(),
                target_domain=command.target_domain,
                command_type=command.command_type,
                channel=adapter.channel,
                adapter_id=adapter.adapter_id,
                adapter_version=adapter.adapter_version,
                state=command.state,
                effective_from=command.effective_from,
                effective_until=command.effective_until,
                version=1 if existing is None else existing.version + 1,
                created_at=instant if existing is None else existing.created_at,
                updated_at=instant,
            )
            saved = unit.request_access.put_capability(
                capability, expected_version=expected_version
            )
            event_type = (
                "access.channel_capability_retired"
                if saved.state is CapabilityState.RETIRED
                else "access.channel_capability_declared"
            )
            self._record_evidence(
                unit,
                trace=trace,
                actor_account_id=actor_account_id,
                resource_id=saved.capability_id,
                aggregate_type="access.channel_capability",
                event_type=event_type,
                payload={"version": saved.version, "state": saved.state.value},
                idempotency_key=idempotency_key,
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"request_access_capability/{saved.capability_id}",
                completed_at=instant,
            )
            return saved

    def issue_continuity_reference(
        self,
        *,
        actor_account_id: UUID,
        acting_subject_id: UUID,
        target_domain: str,
        target_type: str,
        target_id: str,
        continuity_reference: str,
        ttl: timedelta,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> IssuedContinuityReference:
        instant = self._at(at)
        if not timedelta(minutes=1) <= ttl <= timedelta(days=30):
            raise ValueError(
                "Continuity lifetime must be between one minute and 30 days"
            )
        if len(continuity_reference) < 32:
            raise ValueError("Continuity reference must contain at least 32 characters")
        with self._uow() as unit:
            account = self._authorize(
                unit, actor_account_id, "access.provenance.record", instant
            )
            if account.subject_id != acting_subject_id:
                raise RequestAccessAuthorizationError(
                    "Continuity actor must match authenticated Account"
                )
            material = (
                f"{acting_subject_id}:{target_domain}:{target_type}:{target_id}:"
                f"{self._hash_reference(continuity_reference)}:{ttl.total_seconds()}"
            )
            reservation = self._reserve(
                unit,
                actor_account_id,
                "continuity.issue",
                material,
                idempotency_key,
                trace,
                instant,
            )
            if reservation.completed_at:
                stored = unit.request_access.get_continuity_by_hash(
                    self._hash_reference(continuity_reference)
                )
                if stored is None:
                    raise RuntimeError("Completed continuity result is unavailable")
                return IssuedContinuityReference(
                    continuity_id=stored.continuity_id,
                    reference=continuity_reference,
                    expires_at=stored.expires_at,
                )
            reference = unit.request_access.append_continuity(
                ContinuityReference(
                    continuity_id=uuid4(),
                    reference_hash=self._hash_reference(continuity_reference),
                    authenticated_account_id=actor_account_id,
                    acting_subject_id=acting_subject_id,
                    target_domain=target_domain,
                    target_type=target_type,
                    target_id=target_id,
                    created_at=instant,
                    expires_at=instant + ttl,
                )
            )
            audit_key = hashlib.sha256(
                f"continuity:{idempotency_key}".encode()
            ).hexdigest()[:32]
            unit.audit.append(
                AuditEvent(
                    occurred_at=instant,
                    actor_type=ActorType.SERVICE,
                    actor_id=str(actor_account_id),
                    action="access.continuity_reference_issued",
                    resource_type="access_continuity_reference",
                    resource_id=str(reference.continuity_id),
                    outcome=AuditOutcome.SUCCESS,
                    correlation_id=trace.correlation_id,
                    causation_id=trace.causation_id,
                    request_id=trace.request_id,
                    source_module="request_access",
                    safe_metadata={
                        "category": "access_provenance",
                        "operation": "continuity_reference_issued",
                    },
                    idempotency_key=f"audit-{audit_key}",
                )
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"continuity_reference/{reference.continuity_id}",
                completed_at=instant,
            )
            return IssuedContinuityReference(
                continuity_id=reference.continuity_id,
                reference=continuity_reference,
                expires_at=reference.expires_at,
            )

    def record_accepted_interaction(
        self,
        *,
        actor_account_id: UUID,
        envelope: InteractionProvenanceEnvelope,
        interaction_idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> InteractionProvenanceRecord:
        """Record evidence only after the owning domain accepted its command."""

        instant = self._at(at)
        if trace.command_id is None:
            raise ValueError("Accepted interaction requires command identifier")
        if envelope.continuity_id is not None:
            raise ValueError("Caller cannot supply internal continuity identity")
        with self._uow() as unit:
            account = self._authorize(
                unit, actor_account_id, "access.provenance.record", instant
            )
            if actor_account_id != envelope.authenticated_account_id:
                raise RequestAccessAuthorizationError(
                    "Authenticated Account must match server actor"
                )
            if account.subject_id != envelope.authenticated_subject_id:
                raise RequestAccessAuthorizationError(
                    "Authenticated Subject does not match canonical Account"
                )
            if envelope.acting_subject_id != account.subject_id:
                raise RequestAccessAuthorizationError(
                    "Acting Subject requires separately approved delegation integration"
                )
            if envelope.interaction_method is InteractionMethod.SUPPORT_ASSISTED:
                self._authorize(
                    unit, actor_account_id, "access.provenance.support", instant
                )
                if (
                    envelope.support_agent_account_id != actor_account_id
                    or envelope.support_agent_subject_id != account.subject_id
                ):
                    raise RequestAccessAuthorizationError(
                        "Support attribution must match authenticated workforce actor"
                    )
            material = (
                envelope.model_dump_json()
                + ":"
                + (
                    self._hash_reference(envelope.continuity_reference)
                    if envelope.continuity_reference
                    else "none"
                )
            )
            reservation = self._reserve(
                unit,
                actor_account_id,
                "interaction.record",
                material,
                interaction_idempotency_key,
                trace,
                instant,
            )
            if reservation.completed_at:
                stored = unit.request_access.get_provenance(
                    UUID(reservation.response_reference.rsplit("/", 1)[-1])  # type: ignore[union-attr]
                )
                if stored is None:
                    raise RuntimeError("Completed provenance result is unavailable")
                return stored
            adapter = unit.request_access.get_adapter(envelope.adapter_id)
            if (
                adapter is None
                or not adapter.active
                or adapter.channel is not envelope.channel
                or adapter.adapter_version != envelope.adapter_version
            ):
                raise RequestAccessAuthorizationError(
                    "Registered active source adapter is required"
                )
            capability = unit.request_access.get_capability(
                target_domain=envelope.target_domain,
                command_type=envelope.command_type,
                adapter_id=envelope.adapter_id,
            )
            if (
                capability is None
                or capability.state is not CapabilityState.SUPPORTED
                or instant < capability.effective_from
                or (
                    capability.effective_until is not None
                    and instant >= capability.effective_until
                )
            ):
                raise RequestAccessAuthorizationError(
                    "Channel action is not currently supported"
                )
            continuity_id = self._validate_continuity(
                unit, envelope=envelope, at=instant
            )
            if envelope.purpose is ProvenancePurpose.CORRECTION:
                superseded = unit.request_access.get_provenance(
                    envelope.supersedes_provenance_id  # type: ignore[arg-type]
                )
                if (
                    superseded is None
                    or superseded.target_domain != envelope.target_domain
                    or superseded.target_type != envelope.target_type
                    or superseded.target_id != envelope.target_id
                ):
                    raise ValueError(
                        "Correction must supersede evidence for the same target"
                    )
            values = envelope.model_dump(mode="python")
            values["continuity_id"] = continuity_id
            record = unit.request_access.append_provenance(
                InteractionProvenanceRecord(
                    **values,
                    provenance_id=uuid4(),
                    accepted_at=instant,
                    correlation_id=trace.correlation_id,
                    causation_id=trace.causation_id,
                    command_id=trace.command_id,
                    request_id=trace.request_id,
                    interaction_idempotency_key=interaction_idempotency_key,
                )
            )
            event_type = {
                ProvenancePurpose.INITIATION: "access.interaction_provenance_recorded",
                ProvenancePurpose.CONTINUATION: "access.interaction_continuation_recorded",
                ProvenancePurpose.CORRECTION: "access.interaction_provenance_corrected",
                ProvenancePurpose.LEGACY_VERIFIED: "access.interaction_provenance_recorded",
            }[record.purpose]
            self._record_evidence(
                unit,
                trace=trace,
                actor_account_id=actor_account_id,
                resource_id=record.provenance_id,
                aggregate_type="access.interaction_provenance",
                event_type=event_type,
                payload={
                    "schema_version": record.schema_version,
                    "target_type": record.target_type,
                    "target_id": record.target_id,
                    "target_version": record.target_version,
                    "channel": record.channel.value,
                    "purpose": record.purpose.value,
                    "adapter_version": record.adapter_version,
                },
                idempotency_key=interaction_idempotency_key,
                at=instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"interaction_provenance/{record.provenance_id}",
                completed_at=instant,
            )
            return record

    @staticmethod
    def _validate_continuity(
        unit: RequestAccessUnitOfWork,
        *,
        envelope: InteractionProvenanceEnvelope,
        at: datetime,
    ) -> UUID | None:
        if envelope.purpose is not ProvenancePurpose.CONTINUATION:
            return None
        raw = envelope.continuity_reference
        if raw is None or len(raw) < 32:
            raise RequestAccessAuthorizationError(
                "Explicit high-entropy continuity reference required"
            )
        reference = unit.request_access.get_continuity_by_hash(
            RequestAccessApplicationService._hash_reference(raw)
        )
        if (
            reference is None
            or reference.expires_at <= at
            or reference.authenticated_account_id != envelope.authenticated_account_id
            or reference.acting_subject_id != envelope.acting_subject_id
            or reference.target_domain != envelope.target_domain
            or reference.target_type != envelope.target_type
            or reference.target_id != envelope.target_id
        ):
            raise RequestAccessAuthorizationError(
                "Continuity reference is invalid, expired, or target-mismatched"
            )
        return reference.continuity_id

    @staticmethod
    def _hash_reference(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _authorize(
        unit: RequestAccessUnitOfWork,
        account_id: UUID,
        permission: str,
        at: datetime,
    ):
        account = unit.accounts.get_account(account_id)
        if account is None or account.state is not AccountLifecycle.ACTIVE:
            raise RequestAccessAuthorizationError("Active canonical Account required")
        if not unit.accounts.has_permission(account_id, permission, at=at):
            raise RequestAccessAuthorizationError("Request Access permission required")
        return account

    @staticmethod
    def _reserve(
        unit: RequestAccessUnitOfWork,
        actor: UUID,
        operation: str,
        material: str,
        key: str,
        trace: TraceContext,
        at: datetime,
    ) -> IdempotencyRecord:
        if trace.command_id is None:
            raise ValueError("Request Access mutation requires command identifier")
        return unit.idempotency.reserve(
            IdempotencyRecord(
                scope=f"access.provenance.{operation}",
                actor_reference=str(actor),
                idempotency_key=key,
                request_hash=canonical_request_hash(material.encode("utf-8")),
                command_id=trace.command_id,
                correlation_id=trace.correlation_id,
                request_id=trace.request_id,
                created_at=at,
            )
        )

    @staticmethod
    def _record_evidence(
        unit: RequestAccessUnitOfWork,
        *,
        trace: TraceContext,
        actor_account_id: UUID,
        resource_id: UUID,
        aggregate_type: str,
        event_type: str,
        payload: dict[str, str | int | bool | None],
        idempotency_key: str,
        at: datetime,
    ) -> None:
        derived = hashlib.sha256(
            f"{event_type}:{idempotency_key}".encode()
        ).hexdigest()[:32]
        unit.events.append(
            DomainEvent(
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=str(resource_id),
                source_module="request_access",
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
                actor_type=ActorType.SERVICE,
                actor_id=str(actor_account_id),
                action=event_type,
                resource_type=aggregate_type.replace(".", "_"),
                resource_id=str(resource_id),
                outcome=AuditOutcome.SUCCESS,
                correlation_id=trace.correlation_id,
                causation_id=trace.causation_id,
                request_id=trace.request_id,
                source_module="request_access",
                safe_metadata={
                    "category": "access_provenance",
                    "operation": event_type,
                },
                idempotency_key=f"audit-{derived}",
            )
        )

    @staticmethod
    def _at(value: datetime | None) -> datetime:
        instant = value or datetime.now(UTC)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware")
        return instant.astimezone(UTC)
