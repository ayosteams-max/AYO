from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.ordering.application import OrderingApplication
from BACKEND.ordering.engine import OrderingConflict
from BACKEND.ordering.models import BasketLine


class CreateOrderCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    merchant_id: UUID
    lines: tuple[BasketLine, ...] = Field(min_length=1, max_length=50)


def _subject(request: Request) -> AuthorizationSubject:
    value = getattr(request.state, "authorization_subject", None)
    if value is None:
        raise HTTPException(401, {"code": "authentication_required"})
    return value


def _call(operation):
    try:
        return operation()
    except OrderingConflict as error:
        code = str(error)
        status = (
            401
            if code == "authentication_required"
            else 403
            if code == "access_denied"
            else 404
            if code.endswith("not_found") or code == "item_removed"
            else 409
        )
        raise HTTPException(status, {"code": code}) from error


def create_public_commerce_router(application: OrderingApplication) -> APIRouter:
    router = APIRouter(prefix="/public/commerce", tags=["commerce-discovery"])

    @router.get("/merchants")
    def merchants(
        query: str | None = Query(default=None, max_length=120),
        limit: int = Query(default=30, ge=1, le=50),
    ):
        return [
            value.model_dump(mode="json")
            for value in _call(lambda: application.merchants(query=query, limit=limit))
        ]

    @router.get("/merchants/{merchant_id}")
    def merchant(merchant_id: UUID):
        return _call(lambda: application.merchant(merchant_id)).model_dump(mode="json")

    @router.get("/merchants/{merchant_id}/categories")
    def categories(merchant_id: UUID, limit: int = Query(default=50, ge=1, le=100)):
        return [
            value.model_dump(mode="json")
            for value in _call(lambda: application.categories(merchant_id, limit=limit))
        ]

    @router.get("/merchants/{merchant_id}/items")
    def items(
        merchant_id: UUID,
        query: str | None = Query(default=None, max_length=160),
        category_id: UUID | None = None,
        tag: str | None = Query(default=None, max_length=63),
        limit: int = Query(default=50, ge=1, le=100),
    ):
        return [
            value.model_dump(mode="json")
            for value in _call(
                lambda: application.items(
                    merchant_id,
                    query=query,
                    category_id=category_id,
                    tag=tag,
                    limit=limit,
                )
            )
        ]

    @router.get("/items/{item_id}")
    def item(item_id: UUID):
        return _call(lambda: application.item(item_id)).model_dump(mode="json")

    return router


def create_ordering_router(application: OrderingApplication) -> APIRouter:
    router = APIRouter(
        prefix="/mobile/orders", tags=["ordering"], route_class=AuthorizationRoute
    )

    @router.post("", status_code=201)
    @permission_required("ordering.create_own", resource_type="commerce_order")
    def create(
        command: CreateOrderCommand,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, Any]:
        return _call(
            lambda: application.create(
                _subject(request),
                merchant_id=command.merchant_id,
                lines=command.lines,
                idempotency_key=idempotency_key,
                at=datetime.now(UTC),
            )
        ).model_dump(mode="json")

    @router.get("/{order_id}")
    @permission_required(
        "ordering.read_own",
        resource_type="commerce_order",
        resource_id_parameter="order_id",
    )
    def get(order_id: UUID, request: Request) -> dict[str, Any]:
        return _call(lambda: application.get(_subject(request), order_id)).model_dump(
            mode="json"
        )

    return router
