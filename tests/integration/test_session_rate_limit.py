from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import update

from BACKEND.persistence.rate_limit_repository import PostgresTokenBucketRateLimiter
from BACKEND.persistence.tables import rate_limit_buckets
from BACKEND.rate_limit.models import RateLimitPolicy
from BACKEND.session.models import SessionRecord
from BACKEND.session.privacy import hash_sensitive_identifier

pytestmark = [pytest.mark.integration, pytest.mark.session_persistence]


def session_record() -> SessionRecord:
    now = datetime.now(UTC)
    return SessionRecord(
        subject_id="subject_01",
        token_hash=hash_sensitive_identifier(b"synthetic-session-token"),
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )


def policy(capacity: int = 5) -> RateLimitPolicy:
    return RateLimitPolicy(
        name="authentication.login",
        capacity=capacity,
        refill_tokens=Decimal("1"),
        refill_period_seconds=60,
    )


def test_session_create_lookup_revoke_and_expiry_survive_transactions(
    postgres_composition,
) -> None:
    session = session_record()
    with postgres_composition.unit_of_work() as unit_of_work:
        stored = unit_of_work.sessions.create(session)
    with postgres_composition.unit_of_work() as unit_of_work:
        assert (
            unit_of_work.sessions.find_active_by_token_hash(
                session.token_hash, at=session.created_at
            )
            == stored
        )
        assert (
            unit_of_work.sessions.find_active_by_token_hash(
                session.token_hash, at=session.expires_at
            )
            is None
        )
        revoked = unit_of_work.sessions.revoke(
            session.session_id,
            revoked_at=datetime.now(UTC),
            reason="user_logout",
        )
        assert revoked is not None and revoked.version == 2
    with postgres_composition.unit_of_work() as unit_of_work:
        assert (
            unit_of_work.sessions.find_active_by_token_hash(
                session.token_hash, at=datetime.now(UTC)
            )
            is None
        )


def test_session_write_rolls_back_with_unit_of_work(postgres_composition) -> None:
    session = session_record()
    with (
        pytest.raises(RuntimeError, match="rollback"),
        postgres_composition.unit_of_work() as unit_of_work,
    ):
        unit_of_work.sessions.create(session)
        raise RuntimeError("rollback")
    with postgres_composition.unit_of_work() as unit_of_work:
        assert unit_of_work.sessions.get(session.session_id) is None


def test_token_bucket_allows_capacity_then_denies_and_refills(
    postgres_composition, postgres_engine
) -> None:
    key_hash = hash_sensitive_identifier(b"synthetic-rate-limit-key")
    decisions = []
    for _ in range(6):
        with postgres_composition.unit_of_work() as unit_of_work:
            decisions.append(
                unit_of_work.rate_limits.consume(key_hash=key_hash, policy=policy())
            )
    assert [decision.allowed for decision in decisions] == [
        True,
        True,
        True,
        True,
        True,
        False,
    ]
    assert decisions[-1].retry_after_seconds > 0

    with postgres_engine.begin() as connection:
        connection.execute(
            update(rate_limit_buckets).values(
                last_refill_at=datetime.now(UTC) - timedelta(seconds=60)
            )
        )
    with postgres_composition.unit_of_work() as unit_of_work:
        assert unit_of_work.rate_limits.consume(
            key_hash=key_hash, policy=policy()
        ).allowed


def test_concurrent_token_consumption_never_exceeds_capacity(
    postgres_composition,
) -> None:
    key_hash = hash_sensitive_identifier(b"concurrent-rate-limit-key")

    def consume(_: int) -> bool:
        with postgres_composition.unit_of_work() as unit_of_work:
            return unit_of_work.rate_limits.consume(
                key_hash=key_hash, policy=policy()
            ).allowed

    with ThreadPoolExecutor(max_workers=3) as executor:
        outcomes = list(executor.map(consume, range(20)))

    assert sum(outcomes) == 5


def test_rate_limit_storage_failure_is_surfaced_not_failed_open() -> None:
    connection = MagicMock()
    connection.execute.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        PostgresTokenBucketRateLimiter(connection).consume(
            key_hash=b"x" * 32,
            policy=policy(),
        )
