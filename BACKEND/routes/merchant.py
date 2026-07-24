from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.merchant.application import MerchantApplication
from BACKEND.merchant.engine import MerchantConflict
from BACKEND.merchant.models import (
    CatalogueKind,
    MerchantKind,
    OnboardingSource,
    PartnerProgram,
    VerificationKind,
)


class RegisterMerchantCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    legal_name: str = Field(min_length=2, max_length=160)
    display_name: str = Field(min_length=2, max_length=120)
    kind: MerchantKind
    onboarding_source: OnboardingSource = OnboardingSource.SELF
    capability_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$", max_length=63)
    market_code: str = Field(pattern=r"^[A-Z]{2}-[A-Z0-9-]{2,12}$", max_length=15)
    representative_identity_id: UUID | None = None


class BranchCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    address_label: str = Field(min_length=2, max_length=240)
    operating_hours: dict[str, str] = Field(default_factory=dict)


class VerificationCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: VerificationKind
    opaque_reference: str = Field(min_length=16, max_length=160)
    expires_at: datetime | None = None


class CatalogueCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    branch_id: UUID | None = None
    kind: CatalogueKind
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    category_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$", max_length=63)


class ReviewCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    approved: bool
    reason_code: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9_.-]{1,62}$", max_length=63
    )


class CatalogueReviewCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ready: bool


def _subject(request: Request) -> AuthorizationSubject:
    subject = getattr(request.state, "authorization_subject", None)
    if subject is None:
        raise HTTPException(401, {"code": "authentication_required"})
    return subject


def _call(operation):
    try:
        return operation()
    except MerchantConflict as error:
        code = str(error)
        status = (
            404
            if code.endswith("not_found")
            else 403
            if code in {"access_denied", "merchant_representative_not_authorized"}
            else 409
        )
        raise HTTPException(status, {"code": code}) from error


def create_merchant_router(application: MerchantApplication) -> APIRouter:
    router = APIRouter(
        prefix="/mobile/merchants", tags=["merchant"], route_class=AuthorizationRoute
    )

    @router.post("", status_code=201)
    @permission_required("merchant.register_own", resource_type="merchant")
    def register(
        command: RegisterMerchantCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        result = _call(
            lambda: application.register(
                _subject(request),
                legal_name=command.legal_name,
                display_name=command.display_name,
                kind=command.kind,
                source=command.onboarding_source,
                capability_code=command.capability_code,
                market_code=command.market_code,
                representative_identity_id=command.representative_identity_id,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        )
        return result.model_dump(mode="json")

    @router.get("")
    @permission_required("merchant.dashboard.read_own", resource_type="merchant")
    def owned(request: Request) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in _call(lambda: application.list_owned(_subject(request)))
        ]

    @router.get("/{merchant_id}/dashboard")
    @permission_required(
        "merchant.dashboard.read_own",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def dashboard(merchant_id: UUID, request: Request) -> dict[str, Any]:
        return _call(
            lambda: application.dashboard(
                _subject(request), merchant_id=merchant_id, at=datetime.now(UTC)
            )
        ).model_dump(mode="json")

    @router.post("/{merchant_id}/branches", status_code=201)
    @permission_required(
        "merchant.manage_own",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def branch(
        merchant_id: UUID, command: BranchCommand, request: Request
    ) -> dict[str, Any]:
        return _call(
            lambda: application.add_branch(
                _subject(request),
                merchant_id=merchant_id,
                name=command.name,
                address_label=command.address_label,
                operating_hours=command.operating_hours,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/{merchant_id}/verifications")
    @permission_required(
        "merchant.manage_own",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def verification(
        merchant_id: UUID, command: VerificationCommand, request: Request
    ) -> dict[str, Any]:
        return _call(
            lambda: application.submit_verification(
                _subject(request),
                merchant_id=merchant_id,
                kind=command.kind,
                opaque_reference=command.opaque_reference,
                expires_at=command.expires_at,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/{merchant_id}/catalogue", status_code=201)
    @permission_required(
        "merchant.manage_own",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def catalogue(
        merchant_id: UUID, command: CatalogueCommand, request: Request
    ) -> dict[str, Any]:
        return _call(
            lambda: application.add_catalogue_item(
                _subject(request),
                merchant_id=merchant_id,
                branch_id=command.branch_id,
                kind=command.kind,
                name=command.name,
                description=command.description,
                category_code=command.category_code,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/{merchant_id}/programs/{program_id}", status_code=201)
    @permission_required(
        "merchant.manage_own",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def enroll(merchant_id: UUID, program_id: UUID, request: Request) -> dict[str, Any]:
        return _call(
            lambda: application.enroll_program(
                _subject(request),
                merchant_id=merchant_id,
                program_id=program_id,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/internal/verifications/{evidence_id}/review")
    @permission_required(
        "merchant.verification.review",
        resource_type="merchant_verification",
        resource_id_parameter="evidence_id",
    )
    def review_verification(
        evidence_id: UUID, command: ReviewCommand, request: Request
    ) -> dict[str, Any]:
        return _call(
            lambda: application.review_verification(
                _subject(request),
                evidence_id=evidence_id,
                approved=command.approved,
                reason_code=command.reason_code,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/internal/catalogue/{item_id}/review")
    @permission_required(
        "merchant.catalogue.review",
        resource_type="merchant_catalogue_item",
        resource_id_parameter="item_id",
    )
    def review_catalogue(
        item_id: UUID, command: CatalogueReviewCommand, request: Request
    ) -> dict[str, Any]:
        return _call(
            lambda: application.set_catalogue_readiness(
                _subject(request),
                item_id=item_id,
                ready=command.ready,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/internal/programs", status_code=201)
    @permission_required(
        "merchant.program.manage", resource_type="merchant_partner_program"
    )
    def configure_program(program: PartnerProgram, request: Request) -> dict[str, Any]:
        return _call(
            lambda: application.configure_program(
                _subject(request), program=program, at=datetime.now(UTC)
            )
        ).model_dump(mode="json")

    @router.get("/representative/progress")
    @permission_required("merchant.assist", resource_type="merchant_assistance")
    def representative_progress(request: Request) -> dict[str, int]:
        return _call(
            lambda: application.representative_progress(
                _subject(request), at=datetime.now(UTC)
            )
        )

    return router
