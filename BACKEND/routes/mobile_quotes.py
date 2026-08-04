from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.identity.models import IdentityType
from BACKEND.pricing.engine import PricingConflict
from BACKEND.pricing.mobile_quotes import MobileCashQuoteApplication


class MobileCashQuoteRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ride_request_id: UUID


class MobileCashQuoteResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    quote_id: UUID
    ride_request_id: UUID
    currency: str
    amount_minor: int
    expires_at: datetime
    pricing_version: str
    service_type: str
    payment_method: str


def create_mobile_quote_router(application: MobileCashQuoteApplication) -> APIRouter:
    router = APIRouter(
        prefix="/mobile/cash-fare-quotes",
        tags=["mobile-pricing"],
        route_class=AuthorizationRoute,
    )

    @router.post("", response_model=MobileCashQuoteResponse)
    @permission_required("pricing.estimate.create", resource_type="fare_estimate")
    def quote(
        command: MobileCashQuoteRequest,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> MobileCashQuoteResponse:
        subject: AuthorizationSubject | None = getattr(
            request.state, "authorization_subject", None
        )
        if subject is None:
            raise HTTPException(401, {"code": "authentication_required"})
        if subject.identity_type is not IdentityType.RIDER:
            raise HTTPException(403, {"code": "access_denied"})
        now = datetime.now(UTC)
        try:
            estimate = application.quote(
                subject,
                ride_request_id=command.ride_request_id,
                idempotency_key=idempotency_key,
                correlation_id=getattr(
                    request.state, "authorization_correlation_id", uuid4()
                ),
                at=now,
            )
        except PricingConflict as error:
            code = str(error).split(":", 1)[0]
            public = (
                code
                if code
                in {
                    "access_denied",
                    "ride_request_not_priceable",
                    "pricing_policy_unavailable",
                    "route_metrics_stale",
                    "idempotency_conflict",
                }
                else "quote_unavailable"
            )
            http_status = (
                status.HTTP_403_FORBIDDEN
                if public == "access_denied"
                else status.HTTP_409_CONFLICT
            )
            raise HTTPException(http_status, {"code": public}) from error
        return MobileCashQuoteResponse(
            quote_id=estimate.estimate_id,
            ride_request_id=estimate.ride_request_id,
            currency=estimate.breakdown.currency,
            amount_minor=estimate.breakdown.rider_total_minor,
            expires_at=estimate.expires_at,
            pricing_version=estimate.policy_version,
            service_type=estimate.service_type,
            payment_method="cash",
        )

    return router
