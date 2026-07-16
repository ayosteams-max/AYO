from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from fastapi import HTTPException, Request, status
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp

from BACKEND.audit.models import AuditEvent, AuditOutcome
from BACKEND.authorization.contracts import AuthorizationRequest, AuthorizationSubject
from BACKEND.authorization.service import AuthorizationService
from BACKEND.observability import MetricsSink, NullMetricsSink
from BACKEND.persistence.composition import PostgresRepositoryComposition


class TrustedSubjectResolver(Protocol):
    async def resolve(self, request: Request) -> AuthorizationSubject | None: ...


class AnonymousSubjectResolver:
    async def resolve(self, request: Request) -> None:
        del request
        return None


class ResourceOwnershipResolver(Protocol):
    """Resolve authoritative ownership without trusting caller-supplied identity."""

    def owner_identity_id(
        self,
        *,
        resource_type: str,
        resource_id: str,
    ) -> UUID | None: ...


class DenyAllOwnershipResolver:
    def owner_identity_id(
        self,
        *,
        resource_type: str,
        resource_id: str,
    ) -> None:
        del resource_type, resource_id
        return None


class AuthorizationContextMiddleware(BaseHTTPMiddleware):
    """Resolves trusted Authentication output; it never parses caller role data."""

    def __init__(self, app: ASGIApp, *, resolver: TrustedSubjectResolver) -> None:
        super().__init__(app)
        self._resolver = resolver

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request.state.authorization_correlation_id = uuid4()
        request.state.authorization_subject = await self._resolver.resolve(request)
        return await call_next(request)


@dataclass(frozen=True, slots=True)
class PermissionRequirement:
    permission: str
    resource_type: str
    resource_id_parameter: str | None = None
    ownership_required: bool = False


class AuthorizationEnforcer:
    def __init__(
        self,
        composition: PostgresRepositoryComposition,
        *,
        metrics: MetricsSink | None = None,
        ownership_resolver: ResourceOwnershipResolver | None = None,
    ) -> None:
        self._composition = composition
        self._service = AuthorizationService()
        self._metrics = metrics or NullMetricsSink()
        self._ownership = ownership_resolver or DenyAllOwnershipResolver()

    def enforce(self, request: Request, requirement: PermissionRequirement) -> None:
        subject: AuthorizationSubject | None = getattr(
            request.state, "authorization_subject", None
        )
        if subject is None:
            self._metrics.increment(
                "authorization_failures", labels={"reason": "unauthenticated"}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "authentication_required"},
            )
        resource_id = (
            request.path_params.get(requirement.resource_id_parameter)
            if requirement.resource_id_parameter is not None
            else None
        )
        if requirement.ownership_required:
            if resource_id is None:
                raise RuntimeError("Ownership enforcement requires a resource ID")
            owner_identity_id = self._ownership.owner_identity_id(
                resource_type=requirement.resource_type,
                resource_id=resource_id,
            )
            if owner_identity_id != subject.identity_id:
                correlation_id = getattr(
                    request.state, "authorization_correlation_id", uuid4()
                )
                with self._composition.unit_of_work() as unit_of_work:
                    unit_of_work.audit_events.append(
                        AuditEvent(
                            actor_type=subject.actor_type,
                            actor_id=str(subject.identity_id),
                            session_id=subject.session_id,
                            action="authorization.ownership_denied",
                            resource_type=requirement.resource_type,
                            resource_id=resource_id,
                            outcome=AuditOutcome.DENIED,
                            reason="ownership_mismatch",
                            correlation_id=correlation_id,
                            source_module="authorization",
                            safe_metadata={
                                "category": "authorization",
                                "operation": requirement.permission,
                            },
                        )
                    )
                self._metrics.increment(
                    "authorization_failures", labels={"reason": "ownership_denied"}
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"code": "resource_access_denied"},
                )
        authorization_request = AuthorizationRequest(
            subject=subject,
            permission=requirement.permission,
            resource_type=requirement.resource_type,
            resource_id=resource_id,
            occurred_at=datetime.now(UTC),
            correlation_id=getattr(
                request.state, "authorization_correlation_id", uuid4()
            ),
        )
        with self._composition.unit_of_work() as unit_of_work:
            decision = self._service.authorize(unit_of_work, authorization_request)
        if not decision.allowed:
            self._metrics.increment(
                "authorization_failures", labels={"reason": "permission_denied"}
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "access_denied"},
            )


def permission_required(
    permission: str,
    *,
    resource_type: str,
    resource_id_parameter: str | None = None,
    ownership_required: bool = False,
) -> Callable[[Callable[..., object]], Callable[..., object]]:
    requirement = PermissionRequirement(
        permission=permission,
        resource_type=resource_type,
        resource_id_parameter=resource_id_parameter,
        ownership_required=ownership_required,
    )

    def decorator(endpoint: Callable[..., object]) -> Callable[..., object]:
        endpoint.__ayo_permission_requirement__ = requirement  # type: ignore[attr-defined]
        return endpoint

    return decorator


class AuthorizationRoute(APIRoute):
    """Route-level policy enforcement point for decorator-protected endpoints."""

    def get_route_handler(
        self,
    ) -> Callable[[Request], Coroutine[object, object, Response]]:
        original = super().get_route_handler()
        requirement: PermissionRequirement | None = getattr(
            self.endpoint, "__ayo_permission_requirement__", None
        )
        if requirement is None:
            return original

        async def protected(request: Request) -> Response:
            enforcer: AuthorizationEnforcer = request.app.state.authorization_enforcer
            enforcer.enforce(request, requirement)
            return await original(request)

        return protected


def require_permission(
    permission: str,
    *,
    resource_type: str,
    resource_id_parameter: str | None = None,
    ownership_required: bool = False,
) -> Callable[[Request], None]:
    requirement = PermissionRequirement(
        permission=permission,
        resource_type=resource_type,
        resource_id_parameter=resource_id_parameter,
        ownership_required=ownership_required,
    )

    def dependency(request: Request) -> None:
        enforcer: AuthorizationEnforcer = request.app.state.authorization_enforcer
        enforcer.enforce(request, requirement)

    return dependency
