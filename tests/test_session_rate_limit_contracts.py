from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.persistence.rate_limit_repository import PostgresTokenBucketRateLimiter
from BACKEND.persistence.session_repository import PostgresSessionRepository
from BACKEND.rate_limit.models import RateLimitPolicy
from BACKEND.session.models import SessionRecord
from BACKEND.session.privacy import hash_sensitive_identifier


def session_record(**changes) -> SessionRecord:
    now = datetime.now(UTC)
    values = {
        "subject_id": "subject_01",
        "token_hash": hash_sensitive_identifier(b"synthetic-session-token"),
        "created_at": now,
        "expires_at": now + timedelta(hours=1),
    }
    values.update(changes)
    return SessionRecord.model_validate(values)


def rate_policy() -> RateLimitPolicy:
    return RateLimitPolicy(
        name="authentication.login",
        capacity=5,
        refill_tokens=Decimal("1"),
        refill_period_seconds=60,
    )


def test_session_contract_uses_hashes_utc_and_server_lifecycle() -> None:
    session = session_record()

    assert len(session.token_hash) == 32
    assert session.created_at.tzinfo is UTC
    assert session.expires_at.tzinfo is UTC
    assert session.is_active_at(session.created_at)
    assert not session.is_active_at(session.expires_at)


def test_session_contract_rejects_raw_short_tokens_and_invalid_lifecycle() -> None:
    with pytest.raises(ValueError, match="too short"):
        hash_sensitive_identifier(b"raw-token")
    with pytest.raises(ValidationError):
        session_record(token_hash=b"raw-token")
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="expiry"):
        session_record(created_at=now, expires_at=now)
    with pytest.raises(ValidationError, match="set together"):
        session_record(revocation_reason="logout")


def test_token_bucket_policy_is_bounded_and_decimal() -> None:
    policy = rate_policy()
    assert policy.capacity == 5
    assert policy.refill_tokens == Decimal("1")

    with pytest.raises(ValidationError):
        RateLimitPolicy(
            name="bad policy",
            capacity=0,
            refill_tokens=Decimal("0"),
            refill_period_seconds=0,
        )


def test_repository_boundaries_reject_unsafe_inputs_before_database_access() -> None:
    connection = MagicMock()
    sessions = PostgresSessionRepository(connection)
    limiter = PostgresTokenBucketRateLimiter(connection)
    now = datetime.now(UTC)

    with pytest.raises(ValueError, match="32 bytes"):
        sessions.find_active_by_token_hash(b"raw", at=now)
    with pytest.raises(ValueError, match="timezone-aware"):
        sessions.find_active_by_token_hash(b"x" * 32, at=datetime(2026, 7, 15))
    with pytest.raises(ValueError, match="timezone-aware"):
        sessions.revoke(uuid4(), revoked_at=datetime(2026, 7, 15), reason="user_logout")
    with pytest.raises(ValueError, match="safe category"):
        sessions.revoke(uuid4(), revoked_at=now, reason="raw secret reason")
    with pytest.raises(ValueError, match="32 bytes"):
        limiter.consume(key_hash=b"raw", policy=rate_policy())
    with pytest.raises(ValueError, match="within policy capacity"):
        limiter.consume(key_hash=b"x" * 32, policy=rate_policy(), cost=6)
    with pytest.raises(ValueError, match="timezone-aware"):
        session_record().is_active_at(datetime(2026, 7, 15))

    connection.execute.assert_not_called()
