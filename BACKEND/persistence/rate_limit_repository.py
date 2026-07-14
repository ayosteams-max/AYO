from decimal import ROUND_CEILING, Decimal

from sqlalchemy import Connection, func, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from BACKEND.persistence.tables import rate_limit_buckets
from BACKEND.rate_limit.models import RateLimitDecision, RateLimitPolicy


class PostgresTokenBucketRateLimiter:
    """Transactional token bucket; storage errors surface and never fail open."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def consume(
        self,
        *,
        key_hash: bytes,
        policy: RateLimitPolicy,
        cost: int = 1,
    ) -> RateLimitDecision:
        if len(key_hash) != 32:
            raise ValueError("Rate-limit key fingerprint must be 32 bytes")
        if not 1 <= cost <= policy.capacity:
            raise ValueError("Rate-limit cost must be within policy capacity")

        now = self._connection.execute(select(func.clock_timestamp())).scalar_one()
        self._connection.execute(
            postgres_insert(rate_limit_buckets)
            .values(
                key_hash=key_hash,
                policy_name=policy.name,
                tokens=Decimal(policy.capacity),
                last_refill_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    rate_limit_buckets.c.key_hash,
                    rate_limit_buckets.c.policy_name,
                ]
            )
        )
        row = (
            self._connection.execute(
                select(rate_limit_buckets)
                .where(
                    rate_limit_buckets.c.key_hash == key_hash,
                    rate_limit_buckets.c.policy_name == policy.name,
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )

        elapsed = Decimal(str(max(0.0, (now - row["last_refill_at"]).total_seconds())))
        refill = elapsed * policy.refill_tokens / Decimal(policy.refill_period_seconds)
        available = min(Decimal(policy.capacity), row["tokens"] + refill)
        allowed = available >= cost
        remaining = available - cost if allowed else available
        self._connection.execute(
            update(rate_limit_buckets)
            .where(
                rate_limit_buckets.c.key_hash == key_hash,
                rate_limit_buckets.c.policy_name == policy.name,
            )
            .values(tokens=remaining, last_refill_at=now, updated_at=now)
        )

        retry_after = 0
        if not allowed:
            missing = Decimal(cost) - remaining
            retry_after = int(
                (
                    missing
                    * Decimal(policy.refill_period_seconds)
                    / policy.refill_tokens
                ).to_integral_value(rounding=ROUND_CEILING)
            )
        return RateLimitDecision(
            allowed=allowed,
            remaining=remaining,
            retry_after_seconds=retry_after,
        )
