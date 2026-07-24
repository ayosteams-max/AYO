import hashlib
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, func, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.field_operations.engine import FieldOperationsConflict
from BACKEND.field_operations.models import (
    AssistanceCase,
    CaseEvidence,
    CaseQueue,
    CaseStatus,
    ConductEvidence,
    FieldActivity,
    FieldPartner,
    ManagementQualityDashboard,
    PartnerAssignment,
    PartnerRole,
    PartnerStatus,
    ReviewChecklist,
    Territory,
    VerificationStatus,
)
from BACKEND.persistence.tables import (
    field_activities,
    field_assistance_cases,
    field_case_evidence,
    field_operations_events,
    field_operations_idempotency,
    field_partner_assignments,
    field_partner_conduct_evidence,
    field_partner_roles,
    field_partners,
    field_territories,
)


def _model(kind, row):
    return kind.model_validate(dict(row))


class PostgresFieldOperationsRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def reserve(
        self,
        actor: UUID,
        key: str,
        operation: str,
        payload: str,
        candidate: UUID,
        at: datetime,
    ) -> UUID:
        if not 16 <= len(key) <= 128:
            raise FieldOperationsConflict("idempotency_key_invalid")
        digest = hashlib.sha256(payload.encode()).hexdigest()
        found = self._connection.execute(
            pg_insert(field_operations_idempotency)
            .values(
                actor_identity_id=actor,
                operation=operation,
                idempotency_key=key,
                request_hash=digest,
                response_reference=candidate,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(field_operations_idempotency.c.response_reference)
        ).scalar_one_or_none()
        if found is not None:
            return cast(UUID, found)
        row = (
            self._connection.execute(
                select(field_operations_idempotency).where(
                    field_operations_idempotency.c.actor_identity_id == actor,
                    field_operations_idempotency.c.operation == operation,
                    field_operations_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if row["request_hash"] != digest:
            raise FieldOperationsConflict("idempotency_conflict")
        return cast(UUID, row["response_reference"])

    def create_partner(self, value: FieldPartner, *, actor_id: UUID) -> FieldPartner:
        self._connection.execute(
            insert(field_partners).values(**value.model_dump(mode="json"))
        )
        self._event(
            "partner",
            value.partner_id,
            "field.partner.created",
            actor_id,
            {"status": value.status.value},
            value.created_at,
        )
        return value

    def get_partner(self, partner_id: UUID) -> FieldPartner | None:
        row = (
            self._connection.execute(
                select(field_partners).where(field_partners.c.partner_id == partner_id)
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _model(FieldPartner, row)

    def update_partner_status(
        self,
        current: FieldPartner,
        *,
        expected_version: int,
        status: PartnerStatus,
        verification_status: VerificationStatus,
        actor_id: UUID,
        at: datetime,
    ) -> FieldPartner:
        row = (
            self._connection.execute(
                update(field_partners)
                .where(
                    field_partners.c.partner_id == current.partner_id,
                    field_partners.c.version == expected_version,
                )
                .values(
                    status=status.value,
                    verification_status=verification_status.value,
                    version=field_partners.c.version + 1,
                    updated_at=at,
                )
                .returning(field_partners)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise FieldOperationsConflict("field_partner_version_conflict")
        value = _model(FieldPartner, row)
        self._event(
            "partner",
            value.partner_id,
            "field.partner.status_changed",
            actor_id,
            {
                "status": status.value,
                "verification_status": verification_status.value,
            },
            at,
        )
        return value

    def partner_for_identity(self, identity_id: UUID) -> FieldPartner | None:
        row = (
            self._connection.execute(
                select(field_partners).where(
                    field_partners.c.identity_id == identity_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _model(FieldPartner, row)

    def partner_by_qr_hash(self, digest: str) -> FieldPartner | None:
        row = (
            self._connection.execute(
                select(field_partners).where(
                    field_partners.c.qr_reference_hash == digest
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _model(FieldPartner, row)

    def create_role(
        self, value: PartnerRole, *, actor_id: UUID, at: datetime
    ) -> PartnerRole:
        data = value.model_dump(mode="json")
        data["allowed_activities"] = [item.value for item in value.allowed_activities]
        self._connection.execute(insert(field_partner_roles).values(**data))
        self._event(
            "role",
            value.role_id,
            "field.role.created",
            actor_id,
            {"code": value.code},
            at,
        )
        return value

    def get_role(self, role_id: UUID) -> PartnerRole | None:
        row = (
            self._connection.execute(
                select(field_partner_roles).where(
                    field_partner_roles.c.role_id == role_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _model(PartnerRole, row)

    def create_territory(
        self, value: Territory, *, actor_id: UUID, at: datetime
    ) -> Territory:
        self._connection.execute(
            insert(field_territories).values(**value.model_dump(mode="json"))
        )
        self._event(
            "territory",
            value.territory_id,
            "field.territory.created",
            actor_id,
            {"market_code": value.market_code},
            at,
        )
        return value

    def get_territory(self, territory_id: UUID) -> Territory | None:
        row = (
            self._connection.execute(
                select(field_territories).where(
                    field_territories.c.territory_id == territory_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _model(Territory, row)

    def create_assignment(
        self, value: PartnerAssignment, *, actor_id: UUID, at: datetime
    ) -> PartnerAssignment:
        self._connection.execute(
            insert(field_partner_assignments).values(**value.model_dump(mode="json"))
        )
        self._event(
            "assignment",
            value.assignment_id,
            "field.assignment.created",
            actor_id,
            {
                "partner_id": str(value.partner_id),
                "territory_id": str(value.territory_id),
            },
            at,
        )
        return value

    def create_case(self, value: AssistanceCase, *, actor_id: UUID) -> AssistanceCase:
        self._connection.execute(
            insert(field_assistance_cases).values(**value.model_dump(mode="json"))
        )
        self._event(
            "case",
            value.case_id,
            "field.case.created",
            actor_id,
            {"subject_type": value.subject_type},
            value.created_at,
        )
        self._connection.execute(
            insert(field_case_evidence).values(
                **CaseEvidence(
                    case_id=value.case_id,
                    event_type="field.case.assigned",
                    from_status=None,
                    to_status=value.status,
                    actor_identity_id=actor_id,
                    actor_role="representative",
                    evidence_reference=f"assignment-case-{value.case_id}",
                    case_version=value.version,
                    occurred_at=value.created_at,
                ).model_dump(mode="json")
            )
        )
        return value

    def get_case(self, case_id: UUID, *, lock: bool = False) -> AssistanceCase | None:
        query = select(field_assistance_cases).where(
            field_assistance_cases.c.case_id == case_id
        )
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else _model(AssistanceCase, row)

    def find_case_by_subject(
        self, subject_type: str, subject_id: UUID, capability_code: str
    ) -> AssistanceCase | None:
        row = (
            self._connection.execute(
                select(field_assistance_cases)
                .where(
                    field_assistance_cases.c.subject_type == subject_type,
                    field_assistance_cases.c.subject_id == subject_id,
                    field_assistance_cases.c.capability_code == capability_code,
                )
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _model(AssistanceCase, row)

    def case_evidence(self, case_id: UUID) -> tuple[CaseEvidence, ...]:
        rows = self._connection.execute(
            select(field_case_evidence)
            .where(field_case_evidence.c.case_id == case_id)
            .order_by(field_case_evidence.c.case_version)
            .limit(100)
        ).mappings()
        return tuple(_model(CaseEvidence, row) for row in rows)

    def transition_case(
        self,
        current: AssistanceCase,
        *,
        target: CaseStatus,
        actor_id: UUID,
        actor_role: str,
        evidence_reference: str,
        expected_version: int,
        at: datetime,
        reason_code: str | None = None,
        checklist: ReviewChecklist | None = None,
    ) -> AssistanceCase:
        row = (
            self._connection.execute(
                update(field_assistance_cases)
                .where(
                    field_assistance_cases.c.case_id == current.case_id,
                    field_assistance_cases.c.version == expected_version,
                )
                .values(
                    status=target.value,
                    version=field_assistance_cases.c.version + 1,
                    updated_at=at,
                )
                .returning(field_assistance_cases)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise FieldOperationsConflict("field_case_version_conflict")
        value = _model(AssistanceCase, row)
        evidence = CaseEvidence(
            case_id=value.case_id,
            event_type=f"field.case.{target.value}",
            from_status=current.status,
            to_status=target,
            actor_identity_id=actor_id,
            actor_role=actor_role,
            evidence_reference=evidence_reference,
            reason_code=reason_code,
            checklist=checklist,
            case_version=value.version,
            occurred_at=at,
        )
        self._connection.execute(
            insert(field_case_evidence).values(**evidence.model_dump(mode="json"))
        )
        self._event(
            "case",
            value.case_id,
            evidence.event_type,
            actor_id,
            {"from_status": current.status.value, "to_status": target.value},
            at,
        )
        return value

    def append_conduct_evidence(self, value: ConductEvidence) -> ConductEvidence:
        self._connection.execute(
            insert(field_partner_conduct_evidence).values(
                **value.model_dump(mode="json")
            )
        )
        self._event(
            "partner",
            value.partner_id,
            f"field.conduct.{value.kind.value}",
            value.recorded_by_identity_id,
            {"evidence_id": str(value.evidence_id)},
            value.occurred_at,
        )
        return value

    def get_conduct_evidence(self, evidence_id: UUID) -> ConductEvidence | None:
        row = (
            self._connection.execute(
                select(field_partner_conduct_evidence).where(
                    field_partner_conduct_evidence.c.evidence_id == evidence_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _model(ConductEvidence, row)

    def case_queue(
        self,
        *,
        partner_id: UUID | None,
        statuses: tuple[CaseStatus, ...],
        cursor: UUID | None,
        limit: int,
    ) -> CaseQueue:
        bounded = min(max(limit, 1), 100)
        query = select(field_assistance_cases).where(
            field_assistance_cases.c.status.in_(tuple(item.value for item in statuses))
        )
        if partner_id is not None:
            query = query.where(field_assistance_cases.c.partner_id == partner_id)
        if cursor is not None:
            query = query.where(field_assistance_cases.c.case_id > cursor)
        rows = tuple(
            self._connection.execute(
                query.order_by(field_assistance_cases.c.case_id).limit(bounded + 1)
            ).mappings()
        )
        items = tuple(_model(AssistanceCase, row) for row in rows[:bounded])
        return CaseQueue(
            items=items,
            next_cursor=items[-1].case_id if len(rows) > bounded and items else None,
        )

    def quality_dashboard(
        self, territory_id: UUID | None
    ) -> ManagementQualityDashboard:
        query = select(field_assistance_cases.c.status, func.count()).group_by(
            field_assistance_cases.c.status
        )
        if territory_id is not None:
            query = query.where(field_assistance_cases.c.territory_id == territory_id)
        grouped: dict[str, int] = {
            str(row[0]): int(row[1]) for row in self._connection.execute(query).all()
        }
        approved = int(grouped.get(CaseStatus.APPROVED.value, 0))
        returned = int(grouped.get(CaseStatus.RETURNED_FOR_CORRECTION.value, 0))
        rejected = int(grouped.get(CaseStatus.REJECTED.value, 0))
        reviewed = approved + returned + rejected
        return ManagementQualityDashboard(
            territory_workload=sum(grouped.values()),
            review_workload=int(grouped.get(CaseStatus.SUBMITTED_FOR_REVIEW.value, 0)),
            approved=approved,
            returned=returned,
            rejected=rejected,
            approval_rate_bps=(approved * 10_000 // reviewed) if reviewed else 0,
        )

    def get_assignment(self, assignment_id: UUID) -> PartnerAssignment | None:
        row = (
            self._connection.execute(
                select(field_partner_assignments).where(
                    field_partner_assignments.c.assignment_id == assignment_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _model(PartnerAssignment, row)

    def active_assignments(
        self, partner_id: UUID, at: datetime
    ) -> tuple[PartnerAssignment, ...]:
        rows = self._connection.execute(
            select(field_partner_assignments)
            .where(
                field_partner_assignments.c.partner_id == partner_id,
                field_partner_assignments.c.starts_at <= at,
                or_(
                    field_partner_assignments.c.ends_at.is_(None),
                    field_partner_assignments.c.ends_at > at,
                ),
            )
            .order_by(field_partner_assignments.c.starts_at)
            .limit(100)
        ).mappings()
        return tuple(_model(PartnerAssignment, row) for row in rows)

    def append_activity(self, value: FieldActivity, *, actor_id: UUID) -> FieldActivity:
        self._connection.execute(
            insert(field_activities).values(**value.model_dump(mode="json"))
        )
        self._event(
            "activity",
            value.activity_id,
            "field.activity.recorded",
            actor_id,
            {"kind": value.kind.value, "subject_type": value.subject_type},
            value.occurred_at,
        )
        return value

    def get_activity(self, activity_id: UUID) -> FieldActivity | None:
        row = (
            self._connection.execute(
                select(field_activities).where(
                    field_activities.c.activity_id == activity_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _model(FieldActivity, row)

    def dashboard_counts(
        self, partner_id: UUID, start: datetime, end: datetime
    ) -> tuple[int, int, int]:
        activities = cast(
            int,
            self._connection.execute(
                select(func.count())
                .select_from(field_activities)
                .where(
                    field_activities.c.partner_id == partner_id,
                    field_activities.c.occurred_at >= start,
                    field_activities.c.occurred_at < end,
                )
            ).scalar_one(),
        )
        completed = cast(
            int,
            self._connection.execute(
                select(func.count())
                .select_from(field_activities)
                .where(
                    field_activities.c.partner_id == partner_id,
                    field_activities.c.kind == "onboarding_completed",
                    field_activities.c.occurred_at >= start,
                    field_activities.c.occurred_at < end,
                )
            ).scalar_one(),
        )
        pending = cast(
            int,
            self._connection.execute(
                select(func.count())
                .select_from(field_assistance_cases)
                .where(
                    field_assistance_cases.c.partner_id == partner_id,
                    field_assistance_cases.c.status.in_(("assigned", "in_progress")),
                )
            ).scalar_one(),
        )
        return activities, completed, pending

    def representative_status_counts(self, partner_id: UUID) -> dict[str, int]:
        return {
            str(row[0]): int(row[1])
            for row in self._connection.execute(
                select(field_assistance_cases.c.status, func.count())
                .where(field_assistance_cases.c.partner_id == partner_id)
                .group_by(field_assistance_cases.c.status)
            ).all()
        }

    def _event(
        self,
        aggregate_type: str,
        aggregate_id: UUID,
        event_type: str,
        actor_id: UUID,
        evidence: dict[str, str],
        at: datetime,
    ) -> None:
        self._connection.execute(
            insert(field_operations_events).values(
                event_id=uuid4(),
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                actor_identity_id=actor_id,
                evidence=evidence,
                occurred_at=at,
            )
        )
