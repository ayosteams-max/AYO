import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import TrustedSubjectResolver
from BACKEND.mobile_context.application import (
    MobileContextApplication,
    MobileContextFeatures,
    MobileContextUnavailable,
)
from BACKEND.mobile_context.models import MobileContextResponse

logger = logging.getLogger(__name__)


def create_mobile_context_router(
    application: MobileContextApplication,
    subject_resolver: TrustedSubjectResolver,
    *,
    features: MobileContextFeatures,
) -> APIRouter:
    router = APIRouter(tags=["mobile-context"])

    @router.get("/mobile/context", response_model=MobileContextResponse)
    async def read_context(request: Request) -> MobileContextResponse:
        subject: AuthorizationSubject | None = await subject_resolver.resolve(request)
        if subject is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "authentication_required"},
            )
        try:
            return application.read(subject, features=features, at=datetime.now(UTC))
        except MobileContextUnavailable as error:
            logger.warning("mobile context projection unavailable")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "mobile_context_temporarily_unavailable"},
            ) from error
        except Exception as error:
            logger.error("unclassified mobile context projection failure")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "mobile_context_temporarily_unavailable"},
            ) from error

    return router
