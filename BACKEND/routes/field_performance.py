from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.field_performance.application import FieldPerformanceApplication
from BACKEND.field_performance.engine import FieldPerformanceConflict
from BACKEND.field_performance.models import (
    EvidenceUnit,
    PerformanceMetric,
    ReadinessRequirement,
    RecommendationKind,
)

IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
]


class EvidenceCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    partner_id: UUID
    territory_id: UUID | None = None
    metric: PerformanceMetric
    value: int = Field(ge=0)
    unit: EvidenceUnit
    source_domain: str
    source_event_id: UUID
    evidence_reference: str = Field(min_length=16, max_length=160)
    window_starts_at: datetime
    window_ends_at: datetime
    policy_version: str
    supersedes_evidence_id: UUID | None = None


class ReadinessCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    partner_id: UUID
    requirement: ReadinessRequirement
    satisfied: bool
    source_domain: str
    source_event_id: UUID
    evidence_reference: str = Field(min_length=16, max_length=160)
    effective_at: datetime
    expires_at: datetime | None = None


class RecommendationCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    partner_id: UUID
    kind: RecommendationKind
    evidence_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)
    confidence_bps: int = Field(ge=0, le=10_000)
    reasoning: str = Field(min_length=20, max_length=2000)
    risks: tuple[str, ...] = Field(min_length=1, max_length=20)
    intelligence_domain: str
    policy_version: str


def _subject(request: Request) -> AuthorizationSubject:
    subject = getattr(request.state, "authorization_subject", None)
    if subject is None:
        raise HTTPException(status_code=401, detail={"code": "authentication_required"})
    return subject


def create_field_performance_router(
    application: FieldPerformanceApplication,
) -> APIRouter:
    router = APIRouter(
        prefix="/operations/field/performance",
        tags=["field-performance"],
        route_class=AuthorizationRoute,
    )

    @router.post("/evidence")
    @permission_required(
        "field_performance.evidence.record", resource_type="field_performance"
    )
    def record_evidence(
        command: EvidenceCommand, request: Request, key: IdempotencyKey
    ):
        try:
            return application.record_evidence(
                _subject(request),
                **command.model_dump(),
                idempotency_key=key,
                at=datetime.now(UTC),
            )
        except FieldPerformanceConflict as error:
            raise HTTPException(status_code=409, detail={"code": str(error)}) from error

    @router.post("/readiness")
    @permission_required(
        "field_performance.readiness.record", resource_type="field_performance"
    )
    def record_readiness(
        command: ReadinessCommand, request: Request, key: IdempotencyKey
    ):
        try:
            return application.record_readiness(
                _subject(request),
                **command.model_dump(),
                idempotency_key=key,
                at=datetime.now(UTC),
            )
        except FieldPerformanceConflict as error:
            raise HTTPException(status_code=409, detail={"code": str(error)}) from error

    @router.post("/recommendations")
    @permission_required(
        "field_performance.recommend", resource_type="field_performance"
    )
    def recommend(
        command: RecommendationCommand, request: Request, key: IdempotencyKey
    ):
        try:
            return application.recommend(
                _subject(request),
                **command.model_dump(),
                idempotency_key=key,
                at=datetime.now(UTC),
            )
        except FieldPerformanceConflict as error:
            raise HTTPException(status_code=409, detail={"code": str(error)}) from error

    @router.get("/me")
    @permission_required(
        "field_performance.read_own", resource_type="field_performance"
    )
    def own_view(request: Request):
        try:
            return application.own_view(_subject(request), at=datetime.now(UTC))
        except FieldPerformanceConflict as error:
            raise HTTPException(status_code=404, detail={"code": str(error)}) from error

    @router.get("/management")
    @permission_required(
        "field_performance.management.read", resource_type="field_performance"
    )
    def management(request: Request, territory_id: UUID | None = None):
        try:
            return application.management_summary(
                _subject(request), territory_id=territory_id, at=datetime.now(UTC)
            )
        except FieldPerformanceConflict as error:
            raise HTTPException(status_code=403, detail={"code": str(error)}) from error

    return router
