from fastapi import APIRouter, HTTPException, Request

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationRoute, permission_required
from BACKEND.identity.models import IdentityType
from BACKEND.merchant_intelligence.generative import (
    MerchantGenerativeExplanationApplication,
    MerchantGenerativeExplanationHttpRequest,
    MerchantGenerativeExplanationRateLimited,
    MerchantGenerativeExplanationResponse,
    MerchantGenerativeExplanationUnavailable,
)


def _subject(request: Request) -> AuthorizationSubject:
    value = getattr(request.state, "authorization_subject", None)
    if value is None:
        raise HTTPException(401, {"code": "authentication_required"})
    if value.identity_type is not IdentityType.MERCHANT:
        raise HTTPException(403, {"code": "access_denied"})
    return value


def create_merchant_intelligence_router(
    application: MerchantGenerativeExplanationApplication,
) -> APIRouter:
    router = APIRouter(
        prefix="/mobile/merchant-intelligence",
        tags=["merchant-intelligence"],
        route_class=AuthorizationRoute,
    )

    @router.post(
        "/generative-explanation",
        response_model=MerchantGenerativeExplanationResponse,
    )
    @permission_required(
        "merchant_orders.read_own", resource_type="merchant_intelligence"
    )
    async def explain(
        command: MerchantGenerativeExplanationHttpRequest, request: Request
    ) -> MerchantGenerativeExplanationResponse:
        try:
            return await application.explain(_subject(request), command)
        except MerchantGenerativeExplanationRateLimited as error:
            raise HTTPException(429, {"code": "temporarily_unavailable"}) from error
        except MerchantGenerativeExplanationUnavailable as error:
            raise HTTPException(503, {"code": "temporarily_unavailable"}) from error

    return router
