from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.field_operations.application import FieldOperationsApplication
from BACKEND.field_operations.engine import FieldOperationsConflict
from BACKEND.field_operations.models import (
    ActivityKind,
    CaseAction,
    CaseStatus,
    ConductEvidenceKind,
    PartnerStatus,
    ReviewChecklist,
    ReviewDecision,
    VerificationStatus,
)

IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
]


class PartnerCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    identity_id: UUID
    photo_reference: str = Field(min_length=16, max_length=160)
    qr_reference: str = Field(min_length=32, max_length=160)


class RoleCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    public_title: str = Field(min_length=2, max_length=100)
    allowed_activities: tuple[ActivityKind, ...]


class PartnerStatusCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected_version: int = Field(ge=1)
    status: PartnerStatus
    verification_status: VerificationStatus


class TerritoryCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    market_code: str = Field(pattern=r"^[A-Z]{2}-[A-Z0-9-]{2,12}$")
    region: str = Field(min_length=2, max_length=100)
    city: str = Field(min_length=2, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=2, max_length=120)


class AssignmentCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    partner_id: UUID
    role_id: UUID
    territory_id: UUID
    starts_at: datetime
    ends_at: datetime | None = None


class CaseCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    assignment_id: UUID
    subject_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    subject_id: UUID
    owner_identity_id: UUID | None = None
    capability_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")


class ActivityCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    assignment_id: UUID
    case_id: UUID | None = None
    kind: ActivityKind
    subject_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    subject_id: UUID
    evidence_reference: str = Field(min_length=16, max_length=160)
    quality_status: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9_.-]{1,62}$"
    )


class CaseTransitionCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected_version: int = Field(ge=1)
    action: CaseAction
    evidence_reference: str = Field(min_length=16, max_length=160)


class ReviewCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected_version: int = Field(ge=1)
    decision: ReviewDecision
    checklist: ReviewChecklist
    evidence_reference: str = Field(min_length=16, max_length=160)
    reason_code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.-]{1,62}$")


class OwnerConfirmationCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected_version: int = Field(ge=1)
    evidence_reference: str = Field(min_length=16, max_length=160)


class ConductEvidenceCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    partner_id: UUID
    kind: ConductEvidenceKind
    evidence_reference: str = Field(min_length=16, max_length=160)


def _subject(request: Request) -> AuthorizationSubject:
    value = getattr(request.state, "authorization_subject", None)
    if value is None:
        raise HTTPException(401, {"code": "authentication_required"})
    return value


def _call(operation):
    try:
        return operation()
    except FieldOperationsConflict as error:
        code = str(error)
        status = (
            403
            if code == "access_denied"
            else 404
            if code.endswith("not_found")
            else 409
        )
        raise HTTPException(status, {"code": code}) from error


def create_field_operations_router(
    application: FieldOperationsApplication,
) -> APIRouter:
    router = APIRouter(
        prefix="/operations/field",
        tags=["field-operations"],
        route_class=AuthorizationRoute,
    )

    @router.post("/partners", status_code=201)
    @permission_required(
        "field_operations.partner.manage", resource_type="field_partner"
    )
    def partner(
        command: PartnerCommand,
        request: Request,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        return _call(
            lambda: application.create_partner(
                _subject(request),
                **command.model_dump(),
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/partners/{partner_id}/status")
    @permission_required(
        "field_operations.partner.manage",
        resource_type="field_partner",
        resource_id_parameter="partner_id",
    )
    def partner_status(
        partner_id: UUID,
        command: PartnerStatusCommand,
        request: Request,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        return _call(
            lambda: application.update_partner_status(
                _subject(request),
                partner_id=partner_id,
                **command.model_dump(),
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/roles", status_code=201)
    @permission_required(
        "field_operations.configuration.manage", resource_type="field_role"
    )
    def role(
        command: RoleCommand, request: Request, idempotency_key: IdempotencyKey
    ) -> dict[str, Any]:
        return _call(
            lambda: application.create_role(
                _subject(request),
                **command.model_dump(),
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/territories", status_code=201)
    @permission_required(
        "field_operations.configuration.manage", resource_type="field_territory"
    )
    def territory(
        command: TerritoryCommand,
        request: Request,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        return _call(
            lambda: application.create_territory(
                _subject(request),
                **command.model_dump(),
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/assignments", status_code=201)
    @permission_required(
        "field_operations.assignment.manage", resource_type="field_assignment"
    )
    def assignment(
        command: AssignmentCommand,
        request: Request,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        return _call(
            lambda: application.assign_partner(
                _subject(request),
                **command.model_dump(),
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/cases", status_code=201)
    @permission_required("field_operations.case.manage", resource_type="field_case")
    def case(
        command: CaseCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        return _call(
            lambda: application.create_case(
                _subject(request),
                **command.model_dump(),
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/cases/{case_id}/transitions")
    @permission_required(
        "field_operations.case.manage",
        resource_type="field_case",
        resource_id_parameter="case_id",
    )
    def case_transition(
        case_id: UUID,
        command: CaseTransitionCommand,
        request: Request,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        return _call(
            lambda: application.transition_case(
                _subject(request),
                case_id=case_id,
                **command.model_dump(),
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/cases/{case_id}/owner-confirmation")
    @permission_required(
        "field_operations.case.confirm_owner",
        resource_type="field_case",
        resource_id_parameter="case_id",
    )
    def owner_confirmation(
        case_id: UUID,
        command: OwnerConfirmationCommand,
        request: Request,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        return _call(
            lambda: application.transition_case(
                _subject(request),
                case_id=case_id,
                action=CaseAction.CONFIRM_OWNER_VERIFICATION,
                **command.model_dump(),
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/reviews/{case_id}")
    @permission_required(
        "field_operations.case.review",
        resource_type="field_case",
        resource_id_parameter="case_id",
    )
    def review(
        case_id: UUID,
        command: ReviewCommand,
        request: Request,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        return _call(
            lambda: application.review_case(
                _subject(request),
                case_id=case_id,
                **command.model_dump(),
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.get("/reviews/queue")
    @permission_required("field_operations.case.review", resource_type="field_case")
    def reviews(
        request: Request, cursor: UUID | None = None, limit: int = 50
    ) -> dict[str, Any]:
        return _call(
            lambda: application.review_queue(
                _subject(request), cursor=cursor, limit=limit, at=datetime.now(UTC)
            )
        ).model_dump(mode="json")

    @router.get("/reviews/{case_id}/evidence")
    @permission_required(
        "field_operations.case.review",
        resource_type="field_case",
        resource_id_parameter="case_id",
    )
    def review_evidence(case_id: UUID, request: Request) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in _call(
                lambda: application.review_evidence(
                    _subject(request), case_id=case_id, at=datetime.now(UTC)
                )
            )
        ]

    @router.get("/cases")
    @permission_required(
        "field_operations.dashboard.read_own", resource_type="field_case"
    )
    def cases(
        request: Request,
        status: list[CaseStatus] | None = None,
        cursor: UUID | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        statuses = tuple(status or list(CaseStatus))
        return _call(
            lambda: application.representative_cases(
                _subject(request),
                statuses=statuses,
                cursor=cursor,
                limit=limit,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/quality/evidence", status_code=201)
    @permission_required(
        "field_operations.quality.record", resource_type="field_partner"
    )
    def conduct(
        command: ConductEvidenceCommand,
        request: Request,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, Any]:
        return _call(
            lambda: application.record_conduct_evidence(
                _subject(request),
                **command.model_dump(),
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.get("/quality/dashboard")
    @permission_required("field_operations.quality.read", resource_type="field_quality")
    def quality(request: Request, territory_id: UUID | None = None) -> dict[str, Any]:
        return _call(
            lambda: application.management_quality_dashboard(
                _subject(request), territory_id=territory_id, at=datetime.now(UTC)
            )
        ).model_dump(mode="json")

    @router.post("/activities", status_code=201)
    @permission_required(
        "field_operations.activity.record", resource_type="field_activity"
    )
    def activity(
        command: ActivityCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        return _call(
            lambda: application.record_activity(
                _subject(request),
                **command.model_dump(),
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.get("/dashboard")
    @permission_required(
        "field_operations.dashboard.read_own", resource_type="field_partner"
    )
    def dashboard(request: Request) -> dict[str, Any]:
        now = datetime.now(UTC)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return _call(
            lambda: application.dashboard(
                _subject(request), day_start=start, day_end=start + timedelta(days=1)
            )
        ).model_dump(mode="json")

    @router.get("/verify/{qr_reference}")
    @permission_required(
        "field_operations.partner.verify", resource_type="field_partner"
    )
    def verify(qr_reference: str, request: Request) -> dict[str, str | bool]:
        _subject(request)
        if not 32 <= len(qr_reference) <= 160:
            raise HTTPException(404, {"code": "field_partner_not_found"})
        return _call(lambda: application.verify_public_qr(qr_reference=qr_reference))

    return router
