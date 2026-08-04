from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.catalogue.application import UniversalCatalogueApplication
from BACKEND.catalogue.engine import CatalogueConflict
from BACKEND.catalogue.models import (
    ItemAvailability,
    ItemKind,
    ItemStatus,
    ItemVisibility,
    MediaReference,
)


class CategoryCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    parent_category_id: UUID | None = None
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    sort_order: int = Field(default=0, ge=0, le=1_000_000)


class ItemCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    category_id: UUID | None = None
    branch_id: UUID | None = None
    kind: ItemKind
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    media: tuple[MediaReference, ...] = Field(default_factory=tuple, max_length=12)
    availability: ItemAvailability = ItemAvailability.HIDDEN
    visibility: ItemVisibility = ItemVisibility.PRIVATE
    tags: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    search_keywords: tuple[str, ...] = Field(default_factory=tuple, max_length=30)
    base_price_minor: int | None = Field(default=None, ge=0, le=100_000_000_00)


class EditItemCommand(ItemCommand):
    expected_version: int = Field(ge=1)
    status: ItemStatus


class VersionCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected_version: int = Field(ge=1)


def _subject(request: Request) -> AuthorizationSubject:
    value = getattr(request.state, "authorization_subject", None)
    if value is None:
        raise HTTPException(401, {"code": "authentication_required"})
    return value


def _call(operation):
    try:
        return operation()
    except CatalogueConflict as error:
        code = str(error)
        status = (
            404
            if code.endswith("not_found")
            else 403
            if code == "access_denied"
            else 409
        )
        raise HTTPException(status, {"code": code}) from error


def create_catalogue_router(application: UniversalCatalogueApplication) -> APIRouter:
    router = APIRouter(
        prefix="/mobile/catalogue", tags=["catalogue"], route_class=AuthorizationRoute
    )

    @router.post("/{merchant_id}/categories", status_code=201)
    @permission_required(
        "catalogue.manage_own",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def create_category(
        merchant_id: UUID,
        command: CategoryCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        return _call(
            lambda: application.create_category(
                _subject(request),
                merchant_id=merchant_id,
                parent_category_id=command.parent_category_id,
                name=command.name,
                description=command.description,
                sort_order=command.sort_order,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.get("/{merchant_id}/categories")
    @permission_required(
        "catalogue.read_own",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def categories(
        merchant_id: UUID,
        request: Request,
        query: str | None = Query(default=None, max_length=120),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> list[dict[str, Any]]:
        return [
            value.model_dump(mode="json")
            for value in _call(
                lambda: application.categories(
                    _subject(request),
                    merchant_id=merchant_id,
                    query=query,
                    limit=limit,
                    at=datetime.now(UTC),
                )
            )
        ]

    @router.post("/{merchant_id}/items", status_code=201)
    @permission_required(
        "catalogue.manage_own",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def create_item(
        merchant_id: UUID,
        command: ItemCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        return _call(
            lambda: application.create_item(
                _subject(request),
                merchant_id=merchant_id,
                category_id=command.category_id,
                branch_id=command.branch_id,
                kind=command.kind,
                name=command.name,
                description=command.description,
                media=command.media,
                availability=command.availability,
                visibility=command.visibility,
                tags=command.tags,
                search_keywords=command.search_keywords,
                base_price_minor=command.base_price_minor,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.get("/{merchant_id}/items")
    @permission_required(
        "catalogue.read_own",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def items(
        merchant_id: UUID,
        request: Request,
        query: str | None = Query(default=None, max_length=160),
        category_id: UUID | None = None,
        tag: str | None = Query(default=None, max_length=63),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> list[dict[str, Any]]:
        return [
            value.model_dump(mode="json")
            for value in _call(
                lambda: application.search(
                    _subject(request),
                    merchant_id=merchant_id,
                    query=query,
                    category_id=category_id,
                    tag=tag,
                    limit=limit,
                    at=datetime.now(UTC),
                )
            )
        ]

    @router.put("/items/{item_id}")
    @permission_required(
        "catalogue.manage_own",
        resource_type="catalogue_item",
        resource_id_parameter="item_id",
    )
    def edit(
        item_id: UUID,
        command: EditItemCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        return _call(
            lambda: application.edit_item(
                _subject(request),
                item_id=item_id,
                expected_version=command.expected_version,
                kind=command.kind,
                name=command.name,
                description=command.description,
                category_id=command.category_id,
                branch_id=command.branch_id,
                media=command.media,
                status=command.status,
                availability=command.availability,
                visibility=command.visibility,
                tags=command.tags,
                search_keywords=command.search_keywords,
                base_price_minor=command.base_price_minor,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/items/{item_id}/archive")
    @permission_required(
        "catalogue.manage_own",
        resource_type="catalogue_item",
        resource_id_parameter="item_id",
    )
    def archive(
        item_id: UUID,
        command: VersionCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        return _call(
            lambda: application.archive(
                _subject(request),
                item_id=item_id,
                expected_version=command.expected_version,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/items/{item_id}/restore")
    @permission_required(
        "catalogue.manage_own",
        resource_type="catalogue_item",
        resource_id_parameter="item_id",
    )
    def restore(
        item_id: UUID,
        command: VersionCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        return _call(
            lambda: application.restore(
                _subject(request),
                item_id=item_id,
                expected_version=command.expected_version,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.post("/items/{item_id}/duplicate", status_code=201)
    @permission_required(
        "catalogue.manage_own",
        resource_type="catalogue_item",
        resource_id_parameter="item_id",
    )
    def duplicate(
        item_id: UUID,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        return _call(
            lambda: application.duplicate(
                _subject(request),
                item_id=item_id,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.get("/{merchant_id}/summary")
    @permission_required(
        "catalogue.read_own",
        resource_type="merchant",
        resource_id_parameter="merchant_id",
    )
    def summary(merchant_id: UUID, request: Request) -> dict[str, Any]:
        return _call(
            lambda: application.summary(
                _subject(request), merchant_id=merchant_id, at=datetime.now(UTC)
            )
        ).model_dump(mode="json")

    return router
