from datetime import UTC, datetime
from uuid import UUID

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType
from BACKEND.persistence.composition import AyoPostgresUnitOfWork
from BACKEND.support.ai_policy import AIAction, ConfidenceBand, evaluate_ai_action
from BACKEND.support.models import (
    RequesterType,
    SupportAIInteraction,
    SupportCase,
    SupportCaseEvent,
    SupportEventType,
    SupportQueue,
)


class SupportAccessDenied(PermissionError):
    """Safe, constant-shape support resource denial."""


QUEUE_PERMISSIONS = {
    queue: f"support.queue.{queue.value}.access" for queue in SupportQueue
}


def _requester_type(subject: AuthorizationSubject) -> RequesterType:
    mapping = {
        IdentityType.ANONYMOUS: RequesterType.ANONYMOUS,
        IdentityType.RIDER: RequesterType.RIDER,
        IdentityType.DRIVER: RequesterType.DRIVER,
        IdentityType.MERCHANT: RequesterType.MERCHANT,
        IdentityType.STAFF: RequesterType.STAFF,
        IdentityType.ADMINISTRATOR: RequesterType.STAFF,
        IdentityType.SERVICE: RequesterType.SERVICE,
        IdentityType.SERVICE_PROVIDER: RequesterType.SERVICE,
    }
    return mapping[subject.identity_type]


class SupportService:
    """Case workflow and resource policy inside the caller's transaction."""

    def create_case(
        self,
        unit_of_work: AyoPostgresUnitOfWork,
        case: SupportCase,
        *,
        actor: AuthorizationSubject | None,
    ) -> SupportCase:
        if actor is not None and case.requester_identity_id != actor.identity_id:
            raise SupportAccessDenied("Support access denied")
        if actor is not None and case.requester_type is not _requester_type(actor):
            raise SupportAccessDenied("Support access denied")
        created_case, created = unit_of_work.support.create_case(case)
        if created:
            self._event(unit_of_work, created_case, SupportEventType.CREATED, actor)
            self._audit(unit_of_work, created_case, "support.case.created", actor)
        return created_case

    def require_read(
        self,
        unit_of_work: AyoPostgresUnitOfWork,
        case: SupportCase,
        actor: AuthorizationSubject,
    ) -> None:
        own_case = case.requester_identity_id == actor.identity_id
        ai_assigned = (
            actor.identity_type is IdentityType.SERVICE
            and case.ai_service_identity_id == actor.identity_id
            and unit_of_work.authorization.has_permission(
                actor.identity_id,
                "support.case.read_assigned",
                at=datetime.now(UTC),
            )
        )
        staff_queue = actor.identity_type in {
            IdentityType.STAFF,
            IdentityType.ADMINISTRATOR,
        } and unit_of_work.authorization.has_permission(
            actor.identity_id,
            QUEUE_PERMISSIONS[case.assigned_queue],
            at=datetime.now(UTC),
        )
        if not (own_case or ai_assigned or staff_queue):
            self._event(unit_of_work, case, SupportEventType.ACCESS_DENIED, actor)
            self._audit(
                unit_of_work,
                case,
                "support.restricted_access.denied",
                actor,
                AuditOutcome.DENIED,
            )
            raise SupportAccessDenied("Support access denied")

    def assign(
        self,
        unit_of_work: AyoPostgresUnitOfWork,
        case: SupportCase,
        *,
        actor: AuthorizationSubject,
        human_identity_id: UUID | None = None,
        ai_service_identity_id: UUID | None = None,
    ) -> SupportCase:
        self._require_staff_queue(unit_of_work, case, actor)
        changed = case.model_copy(
            update={
                "assigned_human_identity_id": human_identity_id,
                "ai_service_identity_id": ai_service_identity_id,
                "updated_at": datetime.now(UTC),
            }
        )
        saved = unit_of_work.support.save_case(changed, expected_version=case.version)
        self._event(unit_of_work, saved, SupportEventType.ASSIGNED, actor)
        self._audit(unit_of_work, saved, "support.case.assigned", actor)
        return saved

    def escalate(
        self,
        unit_of_work: AyoPostgresUnitOfWork,
        case: SupportCase,
        *,
        actor: AuthorizationSubject,
        queue: SupportQueue,
        reason: str,
    ) -> SupportCase:
        if actor.identity_type is IdentityType.SERVICE:
            allowed = (
                unit_of_work.authorization.has_permission(
                    actor.identity_id, "support.case.escalate", at=datetime.now(UTC)
                )
                and case.ai_service_identity_id == actor.identity_id
            )
        else:
            allowed = case.requester_identity_id == actor.identity_id or (
                actor.identity_type in {IdentityType.STAFF, IdentityType.ADMINISTRATOR}
            )
        if not allowed:
            raise SupportAccessDenied("Support access denied")
        changed = case.transition(
            case.status.ESCALATED,
            at=datetime.now(UTC),
            escalation_reason=reason,
        ).model_copy(update={"assigned_queue": queue, "ai_service_identity_id": None})
        saved = unit_of_work.support.save_case(changed, expected_version=case.version)
        self._event(unit_of_work, saved, SupportEventType.ESCALATED, actor)
        self._audit(unit_of_work, saved, "support.case.escalated", actor)
        return saved

    def record_ai_action(
        self,
        unit_of_work: AyoPostgresUnitOfWork,
        interaction: SupportAIInteraction,
        *,
        action: AIAction,
        confidence: ConfidenceBand,
        human_approved: bool = False,
        information_conflict: bool = False,
    ) -> bool:
        case = unit_of_work.support.get_case(interaction.case_id)
        if (
            case is None
            or case.ai_service_identity_id != interaction.ai_service_identity_id
        ):
            raise SupportAccessDenied("Support access denied")
        if not unit_of_work.authorization.has_permission(
            interaction.ai_service_identity_id,
            "support.guidance.provide",
            at=datetime.now(UTC),
        ):
            raise SupportAccessDenied("Support access denied")
        decision = evaluate_ai_action(
            action,
            confidence,
            human_approved=human_approved,
            information_conflict=information_conflict,
        )
        unit_of_work.support.append_ai_interaction(interaction)
        return decision.allowed

    @staticmethod
    def _require_staff_queue(unit_of_work, case, actor) -> None:
        if actor.identity_type not in {IdentityType.STAFF, IdentityType.ADMINISTRATOR}:
            raise SupportAccessDenied("Support access denied")
        if not unit_of_work.authorization.has_permission(
            actor.identity_id,
            QUEUE_PERMISSIONS[case.assigned_queue],
            at=datetime.now(UTC),
        ):
            raise SupportAccessDenied("Support access denied")

    @staticmethod
    def _event(unit_of_work, case, event_type, actor) -> None:
        unit_of_work.support.append_event(
            SupportCaseEvent(
                case_id=case.case_id,
                event_type=event_type,
                actor_identity_id=None if actor is None else actor.identity_id,
                actor_type=(
                    RequesterType.ANONYMOUS if actor is None else _requester_type(actor)
                ),
                correlation_id=case.correlation_id,
                safe_metadata={"category": case.category.value},
                occurred_at=datetime.now(UTC),
            )
        )

    @staticmethod
    def _audit(unit_of_work, case, action, actor, outcome=AuditOutcome.SUCCESS) -> None:
        unit_of_work.audit_events.append(
            AuditEvent(
                actor_type=ActorType.ANONYMOUS if actor is None else actor.actor_type,
                actor_id=None if actor is None else str(actor.identity_id),
                action=action,
                resource_type="support_case",
                resource_id=str(case.case_id),
                outcome=outcome,
                correlation_id=case.correlation_id,
                source_module="support",
                safe_metadata={"category": "support", "operation": action},
            )
        )
