import hashlib
from decimal import Decimal
from typing import Protocol

from fastapi import Request
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.rate_limit.models import RateLimitDecision, RateLimitPolicy

DISPATCH_RATE_POLICIES = {
    "ride_create": RateLimitPolicy(
        name="dispatch.ride_create",
        capacity=5,
        refill_tokens=Decimal(5),
        refill_period_seconds=60,
    ),
    "ride_active": RateLimitPolicy(
        name="dispatch.ride_active",
        capacity=60,
        refill_tokens=Decimal(60),
        refill_period_seconds=60,
    ),
    "offer_lookup": RateLimitPolicy(
        name="dispatch.offer_lookup",
        capacity=120,
        refill_tokens=Decimal(120),
        refill_period_seconds=60,
    ),
    "offer_response": RateLimitPolicy(
        name="dispatch.offer_response",
        capacity=30,
        refill_tokens=Decimal(30),
        refill_period_seconds=60,
    ),
    "scheduled_create": RateLimitPolicy(
        name="scheduled.create",
        capacity=5,
        refill_tokens=Decimal(5),
        refill_period_seconds=3600,
    ),
    "scheduled_manage": RateLimitPolicy(
        name="scheduled.manage",
        capacity=30,
        refill_tokens=Decimal(30),
        refill_period_seconds=3600,
    ),
    "scheduled_confirmation": RateLimitPolicy(
        name="scheduled.confirmation",
        capacity=10,
        refill_tokens=Decimal(10),
        refill_period_seconds=3600,
    ),
    "active_ride_read": RateLimitPolicy(
        name="active_ride.read",
        capacity=120,
        refill_tokens=Decimal(120),
        refill_period_seconds=60,
    ),
    "active_ride_command": RateLimitPolicy(
        name="active_ride.command",
        capacity=60,
        refill_tokens=Decimal(60),
        refill_period_seconds=60,
    ),
    "active_ride_verification": RateLimitPolicy(
        name="active_ride.verification",
        capacity=10,
        refill_tokens=Decimal(10),
        refill_period_seconds=60,
    ),
    "arrival_waiting_read": RateLimitPolicy(
        name="arrival_waiting.read",
        capacity=120,
        refill_tokens=Decimal("120"),
        refill_period_seconds=60,
    ),
    "arrival_waiting_command": RateLimitPolicy(
        name="arrival_waiting.command",
        capacity=60,
        refill_tokens=Decimal("60"),
        refill_period_seconds=60,
    ),
}


class DispatchRateLimitBoundary(Protocol):
    def consume(
        self, *, subject: AuthorizationSubject, operation: str
    ) -> RateLimitDecision: ...


class PostgresDispatchRateLimiter:
    def __init__(self, composition: PostgresRepositoryComposition) -> None:
        self._composition = composition

    def consume(
        self, *, subject: AuthorizationSubject, operation: str
    ) -> RateLimitDecision:
        try:
            policy = DISPATCH_RATE_POLICIES[operation]
        except KeyError as error:
            raise ValueError("Unknown dispatch rate-limit operation") from error
        key = hashlib.sha256(
            subject.identity_id.bytes + b":" + operation.encode("ascii")
        ).digest()
        with self._composition.unit_of_work() as unit:
            return unit.rate_limits.consume(key_hash=key, policy=policy)


class RequestSizeLimitMiddleware:
    """Reject oversized bodies before application parsing; never buffers the body."""

    def __init__(self, app: ASGIApp, *, maximum_bytes: int = 16_384) -> None:
        if not 1_024 <= maximum_bytes <= 1_048_576:
            raise ValueError("Request-size limit is outside approved bounds")
        self.app = app
        self.maximum_bytes = maximum_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if not any(
            part in path
            for part in (
                "/dispatch",
                "/scheduled",
                "/active-rides",
                "/arrival-waiting",
            )
        ):
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.maximum_bytes:
                    response = JSONResponse(
                        {"error": {"code": "request_too_large"}}, status_code=413
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse(
                    {"error": {"code": "invalid_content_length"}}, status_code=400
                )
                await response(scope, receive, send)
                return
        received = 0

        async def bounded_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.maximum_bytes:
                    raise RequestTooLarge
            return message

        try:
            await self.app(scope, bounded_receive, send)
        except RequestTooLarge:
            response = JSONResponse(
                {"error": {"code": "request_too_large"}}, status_code=413
            )
            await response(scope, receive, send)


class RequestTooLarge(Exception):
    pass


def require_rate_limit(
    request: Request,
    subject: AuthorizationSubject,
    operation: str,
) -> None:
    limiter: DispatchRateLimitBoundary = request.app.state.dispatch_rate_limiter
    decision = limiter.consume(subject=subject, operation=operation)
    if not decision.allowed:
        from fastapi import HTTPException

        raise HTTPException(
            429,
            {
                "code": "rate_limited",
                "retry_after_seconds": decision.retry_after_seconds,
            },
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
