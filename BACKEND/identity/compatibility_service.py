import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Engine

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome
from BACKEND.identity.compatibility_models import (
    AccountLifecycle,
    CanonicalSubject,
    IdentityAccount,
    LegacyIdentityMapping,
    LegacySemantic,
)
from BACKEND.persistence.audit_repository import PostgresAuditEventRepository
from BACKEND.persistence.identity_compatibility_repository import (
    PostgresIdentityCompatibilityRepository,
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
from BACKEND.persistence.trace import TraceContext
from BACKEND.persistence.unit_of_work import SqlAlchemyUnitOfWork


class IdentityCompatibilityUnitOfWork(SqlAlchemyUnitOfWork):
    def __enter__(self) -> "IdentityCompatibilityUnitOfWork":
        super().__enter__()
        return self

    @property
    def compatibility(self) -> PostgresIdentityCompatibilityRepository:
        return self.repository("compatibility", PostgresIdentityCompatibilityRepository)

    @property
    def idempotency(self) -> PostgresIdempotencyRepository:
        return self.repository("idempotency", PostgresIdempotencyRepository)

    @property
    def events(self) -> PostgresDomainEventRepository:
        return self.repository("events", PostgresDomainEventRepository)

    @property
    def audit(self) -> PostgresAuditEventRepository:
        return self.repository("audit", PostgresAuditEventRepository)


class IdentityCompatibilityService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._factories = {
            "compatibility": PostgresIdentityCompatibilityRepository,
            "idempotency": PostgresIdempotencyRepository,
            "events": PostgresDomainEventRepository,
            "outbox": PostgresTransactionalOutboxRepository,
            "audit": PostgresAuditEventRepository,
        }

    def _unit_of_work(self) -> IdentityCompatibilityUnitOfWork:
        return IdentityCompatibilityUnitOfWork(self._engine, self._factories)

    def map_legacy_subject(
        self,
        *,
        legacy_identity_id: UUID,
        semantic: LegacySemantic,
        provenance: str,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> tuple[CanonicalSubject, LegacyIdentityMapping]:
        instant = (at or datetime.now(UTC)).astimezone(UTC)
        command_id = self._require_command(trace)
        request_hash = canonical_request_hash(
            f"{legacy_identity_id}:{semantic.value}:{provenance}".encode()
        )
        with self._unit_of_work() as unit:
            reservation = unit.idempotency.reserve(
                IdempotencyRecord(
                    scope="identity.compatibility.map_subject",
                    actor_reference="system",
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    command_id=command_id,
                    correlation_id=trace.correlation_id,
                    request_id=trace.request_id,
                    created_at=instant,
                )
            )
            subject, mapping, created = unit.compatibility.map_legacy_subject(
                legacy_identity_id=legacy_identity_id,
                semantic=semantic,
                provenance=provenance,
                at=instant,
            )
            if created:
                unit.events.append(
                    self._event(
                        trace,
                        event_type="identity.subject_created",
                        aggregate_type="canonical_subject",
                        aggregate_id=str(subject.subject_id),
                        payload={"subject_kind": subject.subject_kind.value},
                        key=self._derived_key("subject", idempotency_key),
                        at=instant,
                    )
                )
                unit.events.append(
                    self._event(
                        trace,
                        event_type="identity.legacy_identity_mapped",
                        aggregate_type="legacy_identity_mapping",
                        aggregate_id=str(mapping.mapping_id),
                        payload={
                            "semantic": mapping.semantic.value,
                            "mapping_state": mapping.mapping_state.value,
                        },
                        key=self._derived_key("mapping", idempotency_key),
                        at=instant,
                    )
                )
                unit.audit.append(
                    self._audit(
                        trace,
                        action="identity.compatibility.subject_mapped",
                        resource_type="canonical_subject",
                        resource_id=str(subject.subject_id),
                        operation="map_subject",
                        key=self._derived_key("audit", idempotency_key),
                        at=instant,
                    )
                )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"subject/{subject.subject_id}",
                completed_at=instant,
            )
            return subject, mapping

    def create_account(
        self,
        *,
        legacy_identity_id: UUID,
        expected_mapping_version: int,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> tuple[IdentityAccount, LegacyIdentityMapping]:
        instant = (at or datetime.now(UTC)).astimezone(UTC)
        command_id = self._require_command(trace)
        request_hash = canonical_request_hash(
            f"{legacy_identity_id}:{expected_mapping_version}".encode()
        )
        with self._unit_of_work() as unit:
            reservation = unit.idempotency.reserve(
                IdempotencyRecord(
                    scope="identity.compatibility.create_account",
                    actor_reference="system",
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    command_id=command_id,
                    correlation_id=trace.correlation_id,
                    request_id=trace.request_id,
                    created_at=instant,
                )
            )
            account, mapping, created = unit.compatibility.create_account(
                legacy_identity_id=legacy_identity_id,
                at=instant,
                expected_mapping_version=expected_mapping_version,
            )
            if created:
                unit.events.append(
                    self._event(
                        trace,
                        event_type="identity.account_created",
                        aggregate_type="identity_account",
                        aggregate_id=str(account.account_id),
                        payload={"state": account.state.value},
                        key=self._derived_key("account", idempotency_key),
                        at=instant,
                    )
                )
                unit.audit.append(
                    self._audit(
                        trace,
                        action="identity.compatibility.account_created",
                        resource_type="identity_account",
                        resource_id=str(account.account_id),
                        operation="create_account",
                        key=self._derived_key("audit", idempotency_key),
                        at=instant,
                    )
                )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"account/{account.account_id}",
                completed_at=instant,
            )
            return account, mapping

    def transition_account(
        self,
        *,
        account_id: UUID,
        target: AccountLifecycle,
        expected_version: int,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> IdentityAccount:
        instant = (at or datetime.now(UTC)).astimezone(UTC)
        command_id = self._require_command(trace)
        request_hash = canonical_request_hash(
            f"{account_id}:{target.value}:{expected_version}".encode()
        )
        with self._unit_of_work() as unit:
            reservation = unit.idempotency.reserve(
                IdempotencyRecord(
                    scope="identity.compatibility.transition_account",
                    actor_reference="system",
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    command_id=command_id,
                    correlation_id=trace.correlation_id,
                    request_id=trace.request_id,
                    created_at=instant,
                )
            )
            current = unit.compatibility.get_account(account_id)
            if current is None:
                raise ValueError("Canonical account does not exist")
            if reservation.completed_at is not None:
                completed_version = int(
                    (reservation.response_reference or "").rsplit("/", 1)[-1]
                )
                if current.version != completed_version:
                    raise ValueError(
                        "Completed command result has since been superseded; "
                        "use the current account projection."
                    )
                return current
            transitioned = unit.compatibility.transition_account(
                current,
                target=target,
                at=instant,
                expected_version=expected_version,
            )
            unit.events.append(
                self._event(
                    trace,
                    event_type="identity.account_state_migrated",
                    aggregate_type="identity_account",
                    aggregate_id=str(account_id),
                    payload={
                        "previous_state": current.state.value,
                        "resulting_state": transitioned.state.value,
                    },
                    key=self._derived_key("state", idempotency_key),
                    at=instant,
                )
            )
            unit.audit.append(
                AuditEvent(
                    occurred_at=instant,
                    actor_type=ActorType.SYSTEM,
                    action="identity.compatibility.account_state_changed",
                    resource_type="identity_account",
                    resource_id=str(account_id),
                    outcome=AuditOutcome.SUCCESS,
                    correlation_id=trace.correlation_id,
                    request_id=trace.request_id,
                    source_module="identity_compatibility",
                    safe_metadata={
                        "category": "identity",
                        "operation": "transition_account",
                        "state_from": current.state.value,
                        "state_to": transitioned.state.value,
                    },
                    idempotency_key=self._derived_key("audit", idempotency_key),
                )
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"account/{account_id}/version/{transitioned.version}",
                completed_at=instant,
            )
            return transitioned

    @staticmethod
    def _require_command(trace: TraceContext) -> UUID:
        if trace.command_id is None:
            raise ValueError("Compatibility mutation requires a command identifier")
        return trace.command_id

    @staticmethod
    def _derived_key(label: str, key: str) -> str:
        return f"{label}-{hashlib.sha256(key.encode()).hexdigest()[:32]}"

    @staticmethod
    def _event(
        trace: TraceContext,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, str | int | bool | None],
        key: str,
        at: datetime,
    ) -> DomainEvent:
        return DomainEvent(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            source_module="identity_compatibility",
            occurred_at=at,
            payload=payload,
            correlation_id=trace.correlation_id,
            request_id=trace.request_id,
            command_id=trace.command_id,
            causation_id=trace.causation_id,
            idempotency_key=key,
        )

    @staticmethod
    def _audit(
        trace: TraceContext,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        operation: str,
        key: str,
        at: datetime,
    ) -> AuditEvent:
        return AuditEvent(
            occurred_at=at,
            actor_type=ActorType.SYSTEM,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=AuditOutcome.SUCCESS,
            correlation_id=trace.correlation_id,
            causation_id=trace.causation_id,
            request_id=trace.request_id,
            source_module="identity_compatibility",
            safe_metadata={"category": "identity", "operation": operation},
            idempotency_key=key,
        )
