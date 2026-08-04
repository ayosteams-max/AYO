import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Engine

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome
from BACKEND.customer_profile.models import (
    CustomerProfile,
    EmergencyContact,
    HouseholdRelationship,
    ProfileLifecycle,
    RelationshipState,
    RelationshipType,
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
from BACKEND.persistence.trace import TraceContext
from BACKEND.persistence.unit_of_work import SqlAlchemyUnitOfWork


class CustomerProfileUnitOfWork(SqlAlchemyUnitOfWork):
    def __enter__(self) -> "CustomerProfileUnitOfWork":
        super().__enter__()
        return self

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


class CustomerProfileService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._factories = {
            "profiles": PostgresCustomerProfileRepository,
            "idempotency": PostgresIdempotencyRepository,
            "events": PostgresDomainEventRepository,
            "outbox": PostgresTransactionalOutboxRepository,
            "audit": PostgresAuditEventRepository,
        }

    def _uow(self) -> CustomerProfileUnitOfWork:
        return CustomerProfileUnitOfWork(self._engine, self._factories)

    def create_profile(
        self,
        *,
        actor_subject_id: UUID,
        display_name: str,
        language: str,
        region: str,
        timezone: str,
        idempotency_key: str,
        trace: TraceContext,
        preferred_name: str | None = None,
        service_area_preference: str | None = None,
        profile_image_reference: str | None = None,
        at: datetime | None = None,
    ) -> CustomerProfile:
        instant = self._at(at)
        with self._uow() as unit:
            reservation = self._reserve(
                unit,
                "customer_profile.create",
                actor_subject_id,
                idempotency_key,
                f"{actor_subject_id}:{display_name}:{language}:{region}:{timezone}",
                trace,
                instant,
            )
            existing = unit.profiles.profile_for_subject(actor_subject_id)
            if reservation.completed_at is not None and existing is not None:
                return existing
            profile = CustomerProfile(
                subject_id=actor_subject_id,
                display_name=display_name.strip(),
                preferred_name=None
                if preferred_name is None
                else preferred_name.strip(),
                language=language,
                region=region,
                timezone=timezone,
                service_area_preference=service_area_preference,
                profile_image_reference=profile_image_reference,
                created_at=instant,
                updated_at=instant,
            )
            created = unit.profiles.create_profile(profile)
            self._record(
                unit,
                trace,
                "customer_profile.created",
                "customer_profile",
                created.profile_id,
                actor_subject_id,
                {"state": created.state.value},
                idempotency_key,
                instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"customer_profile/{created.profile_id}",
                completed_at=instant,
            )
            return created

    def update_profile(
        self,
        *,
        actor_subject_id: UUID,
        expected_version: int,
        idempotency_key: str,
        trace: TraceContext,
        display_name: str | None = None,
        preferred_name: str | None = None,
        language: str | None = None,
        region: str | None = None,
        timezone: str | None = None,
        service_area_preference: str | None = None,
        profile_image_reference: str | None = None,
        at: datetime | None = None,
    ) -> CustomerProfile:
        instant = self._at(at)
        changes: dict[str, object] = {
            key: value
            for key, value in {
                "display_name": display_name,
                "preferred_name": preferred_name,
                "language": language,
                "region": region,
                "timezone": timezone,
                "service_area_preference": service_area_preference,
                "profile_image_reference": profile_image_reference,
            }.items()
            if value is not None
        }
        if not changes:
            raise ValueError("At least one profile change is required")
        with self._uow() as unit:
            reservation = self._reserve(
                unit,
                "customer_profile.update",
                actor_subject_id,
                idempotency_key,
                f"{actor_subject_id}:{expected_version}:{sorted(changes.items())}",
                trace,
                instant,
            )
            profile = unit.profiles.profile_for_subject(actor_subject_id, lock=True)
            if profile is None:
                raise LookupError("Customer profile does not exist")
            if reservation.completed_at is not None:
                return profile
            updated = unit.profiles.update_profile(
                profile, expected_version=expected_version, at=instant, changes=changes
            )
            self._record(
                unit,
                trace,
                "customer_profile.updated",
                "customer_profile",
                updated.profile_id,
                actor_subject_id,
                {"version": updated.version},
                idempotency_key,
                instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"customer_profile/{updated.profile_id}/{updated.version}",
                completed_at=instant,
            )
            return updated

    def invite_relationship(
        self,
        *,
        actor_subject_id: UUID,
        invited_subject_id: UUID,
        relationship_type: RelationshipType,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> HouseholdRelationship:
        if actor_subject_id == invited_subject_id:
            raise ValueError("A Subject cannot invite itself")
        instant = self._at(at)
        with self._uow() as unit:
            reservation = self._reserve(
                unit,
                "customer_household.invite",
                actor_subject_id,
                idempotency_key,
                f"{actor_subject_id}:{invited_subject_id}:{relationship_type.value}",
                trace,
                instant,
            )
            relationship = HouseholdRelationship(
                inviting_subject_id=actor_subject_id,
                invited_subject_id=invited_subject_id,
                relationship_type=relationship_type,
                created_at=instant,
                updated_at=instant,
            )
            if reservation.completed_at is not None:
                stored = (
                    unit.profiles.relationship(
                        UUID(reservation.response_reference.rsplit("/", 1)[1])
                    )
                    if reservation.response_reference
                    else None
                )
                if stored is None:
                    raise RuntimeError("Completed relationship command has no result")
                return stored
            created = unit.profiles.create_relationship(relationship)
            self._record(
                unit,
                trace,
                "customer_household.relationship_invited",
                "customer_household_relationship",
                created.relationship_id,
                actor_subject_id,
                {
                    "relationship_type": relationship_type.value,
                    "state": created.state.value,
                },
                idempotency_key,
                instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"customer_household/{created.relationship_id}",
                completed_at=instant,
            )
            return created

    def transition_profile(
        self,
        *,
        actor_subject_id: UUID,
        target: ProfileLifecycle,
        expected_version: int,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> CustomerProfile:
        instant = self._at(at)
        with self._uow() as unit:
            reservation = self._reserve(
                unit,
                "customer_profile.transition",
                actor_subject_id,
                idempotency_key,
                f"{actor_subject_id}:{target.value}:{expected_version}",
                trace,
                instant,
            )
            profile = unit.profiles.profile_for_subject(actor_subject_id, lock=True)
            if profile is None:
                raise LookupError("Customer profile does not exist")
            if reservation.completed_at is not None:
                return profile
            updated = unit.profiles.transition_profile(
                profile,
                target=target,
                expected_version=expected_version,
                at=instant,
            )
            self._record(
                unit,
                trace,
                "customer_profile.lifecycle_changed",
                "customer_profile",
                updated.profile_id,
                actor_subject_id,
                {"previous_state": profile.state.value, "state": target.value},
                idempotency_key,
                instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"customer_profile/{updated.profile_id}/{updated.version}",
                completed_at=instant,
            )
            return updated

    def transition_relationship(
        self,
        *,
        actor_subject_id: UUID,
        relationship_id: UUID,
        target: RelationshipState,
        expected_version: int,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> HouseholdRelationship:
        instant = self._at(at)
        with self._uow() as unit:
            reservation = self._reserve(
                unit,
                "customer_household.transition",
                actor_subject_id,
                idempotency_key,
                f"{relationship_id}:{target.value}:{expected_version}",
                trace,
                instant,
            )
            relationship = unit.profiles.relationship(relationship_id, lock=True)
            if relationship is None:
                raise LookupError("Household relationship does not exist")
            if actor_subject_id not in {
                relationship.inviting_subject_id,
                relationship.invited_subject_id,
            }:
                raise PermissionError("Household relationship access denied")
            if (
                target is RelationshipState.ACTIVE
                and actor_subject_id != relationship.invited_subject_id
            ):
                raise PermissionError(
                    "Only the invited Subject may activate the relationship"
                )
            if reservation.completed_at is not None:
                return relationship
            updated = unit.profiles.transition_relationship(
                relationship,
                target=target,
                expected_version=expected_version,
                at=instant,
            )
            self._record(
                unit,
                trace,
                "customer_household.relationship_changed",
                "customer_household_relationship",
                relationship_id,
                actor_subject_id,
                {"previous_state": relationship.state.value, "state": target.value},
                idempotency_key,
                instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"customer_household/{relationship_id}/{updated.version}",
                completed_at=instant,
            )
            return updated

    def validate_intended_passenger(
        self, *, actor_subject_id: UUID, intended_subject_id: UUID
    ) -> bool:
        if actor_subject_id == intended_subject_id:
            return True
        with self._uow() as unit:
            return (
                unit.profiles.active_relationship_between(
                    actor_subject_id, intended_subject_id
                )
                is not None
            )

    def add_emergency_contact(
        self,
        *,
        actor_subject_id: UUID,
        display_name: str,
        channel_reference: str,
        priority: int,
        idempotency_key: str,
        trace: TraceContext,
        contact_subject_id: UUID | None = None,
        at: datetime | None = None,
    ) -> EmergencyContact:
        instant = self._at(at)
        with self._uow() as unit:
            reservation = self._reserve(
                unit,
                "customer_emergency_contact.create",
                actor_subject_id,
                idempotency_key,
                f"{actor_subject_id}:{display_name}:{channel_reference}:{priority}:{contact_subject_id}",
                trace,
                instant,
            )
            contact = EmergencyContact(
                subject_id=actor_subject_id,
                contact_subject_id=contact_subject_id,
                display_name=display_name.strip(),
                channel_reference=channel_reference,
                priority=priority,
                created_at=instant,
                updated_at=instant,
            )
            if reservation.completed_at is not None:
                stored = (
                    unit.profiles.contact(
                        UUID(reservation.response_reference.rsplit("/", 1)[1])
                    )
                    if reservation.response_reference
                    else None
                )
                if stored is None:
                    raise RuntimeError("Completed contact command has no result")
                return stored
            created = unit.profiles.create_contact(contact)
            self._record(
                unit,
                trace,
                "customer_profile.emergency_contact_added",
                "customer_emergency_contact",
                created.contact_id,
                actor_subject_id,
                {"priority": priority, "active": True},
                idempotency_key,
                instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"customer_emergency_contact/{created.contact_id}",
                completed_at=instant,
            )
            return created

    def set_emergency_contact_active(
        self,
        *,
        actor_subject_id: UUID,
        contact_id: UUID,
        active: bool,
        expected_version: int,
        idempotency_key: str,
        trace: TraceContext,
        at: datetime | None = None,
    ) -> EmergencyContact:
        instant = self._at(at)
        with self._uow() as unit:
            reservation = self._reserve(
                unit,
                "customer_emergency_contact.state",
                actor_subject_id,
                idempotency_key,
                f"{contact_id}:{active}:{expected_version}",
                trace,
                instant,
            )
            contact = unit.profiles.contact(contact_id, lock=True)
            if contact is None:
                raise LookupError("Emergency contact does not exist")
            if contact.subject_id != actor_subject_id:
                raise PermissionError("Emergency contact access denied")
            if reservation.completed_at is not None:
                return contact
            updated = unit.profiles.set_contact_active(
                contact, active=active, expected_version=expected_version, at=instant
            )
            self._record(
                unit,
                trace,
                "customer_profile.emergency_contact_changed",
                "customer_emergency_contact",
                contact_id,
                actor_subject_id,
                {"active": active},
                idempotency_key,
                instant,
            )
            unit.idempotency.complete(
                record=reservation,
                response_reference=f"customer_emergency_contact/{contact_id}/{updated.version}",
                completed_at=instant,
            )
            return updated

    @staticmethod
    def _reserve(
        unit: CustomerProfileUnitOfWork,
        scope: str,
        actor: UUID,
        key: str,
        material: str,
        trace: TraceContext,
        at: datetime,
    ) -> IdempotencyRecord:
        if trace.command_id is None:
            raise ValueError("Mutation requires command identifier")
        return unit.idempotency.reserve(
            IdempotencyRecord(
                scope=scope,
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
        unit: CustomerProfileUnitOfWork,
        trace: TraceContext,
        event_type: str,
        aggregate_type: str,
        aggregate_id: UUID,
        actor_id: UUID,
        payload: dict[str, str | int | bool | None],
        key: str,
        at: datetime,
    ) -> None:
        derived = hashlib.sha256(f"{event_type}:{key}".encode()).hexdigest()[:32]
        unit.events.append(
            DomainEvent(
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=str(aggregate_id),
                source_module="customer_profile",
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
                actor_type=ActorType.SERVICE,
                actor_id=str(actor_id),
                action=event_type,
                resource_type=aggregate_type,
                resource_id=str(aggregate_id),
                outcome=AuditOutcome.SUCCESS,
                correlation_id=trace.correlation_id,
                causation_id=trace.causation_id,
                request_id=trace.request_id,
                source_module="customer_profile",
                safe_metadata={"category": "customer_profile", "operation": event_type},
                idempotency_key=f"audit-{derived}",
            )
        )

    @staticmethod
    def _at(value: datetime | None) -> datetime:
        instant = value or datetime.now(UTC)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware")
        return instant.astimezone(UTC)
