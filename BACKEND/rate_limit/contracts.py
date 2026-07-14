from typing import Protocol

from BACKEND.rate_limit.models import RateLimitDecision, RateLimitPolicy


class RateLimiter(Protocol):
    """A persistence failure raises; implementations never silently fail open."""

    def consume(
        self,
        *,
        key_hash: bytes,
        policy: RateLimitPolicy,
        cost: int = 1,
    ) -> RateLimitDecision: ...
