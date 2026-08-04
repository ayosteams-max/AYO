from fastapi import APIRouter, HTTPException, Request, Response, status

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import TrustedSubjectResolver
from BACKEND.identity.runtime import (
    AuthenticationDenied,
    AuthenticationRateLimited,
    AuthenticationRuntime,
    RegistrationConflict,
    VerificationDeliveryUnavailable,
)
from BACKEND.identity.runtime_models import (
    AuthenticationSessionResponse,
    IdentityActivationProgress,
    RecoveryPreparationRequest,
    RefreshRequest,
    RegistrationRequest,
    SignInRequest,
    VerificationCompletionRequest,
    VerificationPreparationRequest,
    VerificationPreparationResponse,
)


def create_authentication_router(
    runtime: AuthenticationRuntime,
    subject_resolver: TrustedSubjectResolver,
) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["authentication"])

    def rate_limited(error: AuthenticationRateLimited) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "authentication_rate_limited"},
            headers={"Retry-After": str(error.retry_after_seconds)},
        )

    async def authenticated_subject(request: Request) -> AuthorizationSubject:
        subject = await subject_resolver.resolve(request)
        if subject is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "authentication_required"},
            )
        return subject

    @router.post(
        "/register",
        response_model=AuthenticationSessionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def register(payload: RegistrationRequest) -> AuthenticationSessionResponse:
        try:
            return runtime.register(payload)
        except RegistrationConflict as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "registration_unavailable"},
            ) from error
        except AuthenticationRateLimited as error:
            raise rate_limited(error) from error

    @router.post("/sign-in", response_model=AuthenticationSessionResponse)
    def sign_in(payload: SignInRequest) -> AuthenticationSessionResponse:
        try:
            return runtime.sign_in(payload)
        except AuthenticationDenied as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "authentication_failed"},
            ) from error
        except AuthenticationRateLimited as error:
            raise rate_limited(error) from error

    @router.post("/refresh", response_model=AuthenticationSessionResponse)
    def refresh(payload: RefreshRequest) -> AuthenticationSessionResponse:
        try:
            return runtime.refresh(payload.refresh_token)
        except AuthenticationDenied as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "refresh_denied"},
            ) from error
        except AuthenticationRateLimited as error:
            raise rate_limited(error) from error

    @router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
    async def sign_out(request: Request) -> Response:
        subject = await authenticated_subject(request)
        if subject.session_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "authentication_required"},
            )
        runtime.sign_out(identity_id=subject.identity_id, session_id=subject.session_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/sign-out-all")
    async def sign_out_all(request: Request) -> dict[str, int]:
        subject = await authenticated_subject(request)
        if subject.session_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "authentication_required"},
            )
        count = runtime.sign_out_all(
            identity_id=subject.identity_id, session_id=subject.session_id
        )
        return {"revoked_sessions": count}

    @router.post("/password-reset/prepare", status_code=status.HTTP_202_ACCEPTED)
    def prepare_password_reset(payload: RecoveryPreparationRequest) -> dict[str, str]:
        try:
            runtime.prepare_recovery(payload.contact_kind, payload.contact)
        except AuthenticationRateLimited as error:
            raise rate_limited(error) from error
        return {"status": "accepted"}

    @router.get("/capabilities")
    def capabilities() -> dict[str, object]:
        return {
            "password_reset": "preparation_only",  # nosec B105 - capability label
            "contact_verification": {
                "email": "architecture_ready_provider_required",
                "phone": "architecture_ready_provider_required",
            },
            "mfa": {
                "supported_methods": ["passkey", "staff_mfa"],
                "activation": "future_compatible_not_active",
            },
        }

    @router.get("/activation", response_model=IdentityActivationProgress)
    async def activation_progress(request: Request) -> IdentityActivationProgress:
        subject = await authenticated_subject(request)
        return runtime.activation_progress(subject.identity_id)

    @router.post(
        "/verification/prepare", response_model=VerificationPreparationResponse
    )
    async def prepare_verification(
        payload: VerificationPreparationRequest, request: Request
    ) -> VerificationPreparationResponse:
        subject = await authenticated_subject(request)
        try:
            return runtime.prepare_verification(
                identity_id=subject.identity_id,
                kind=payload.contact_kind,
                contact=payload.contact,
            )
        except VerificationDeliveryUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "verification_temporarily_unavailable"},
            ) from error
        except AuthenticationDenied as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "verification_not_available"},
            ) from error
        except AuthenticationRateLimited as error:
            raise rate_limited(error) from error

    @router.post("/verification/complete", response_model=IdentityActivationProgress)
    async def complete_verification(
        payload: VerificationCompletionRequest, request: Request
    ) -> IdentityActivationProgress:
        subject = await authenticated_subject(request)
        try:
            return runtime.complete_verification(
                identity_id=subject.identity_id,
                challenge_id=payload.challenge_id,
                code=payload.code,
            )
        except VerificationDeliveryUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "verification_temporarily_unavailable"},
            ) from error
        except AuthenticationDenied as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "verification_failed"},
            ) from error
        except AuthenticationRateLimited as error:
            raise rate_limited(error) from error

    return router
