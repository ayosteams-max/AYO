from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from BACKEND.audit.models import ActorType
from BACKEND.identity.authentication import (
    AuthenticationChallenge,
    ChallengePurpose,
    HmacChallengeProtector,
)
from BACKEND.identity.models import AccountStatus, Identity, IdentityType
from BACKEND.identity.service import AuthenticationSecurityService
from BACKEND.identity.tokens import RefreshRotationOutcome
from BACKEND.persistence.tables import audit_events, sessions, token_families
from BACKEND.rate_limit.models import RateLimitPolicy
from BACKEND.session.models import SessionRecord
from BACKEND.session.privacy import hash_sensitive_identifier

pytestmark = [pytest.mark.integration, pytest.mark.authentication]


def create_identity_and_session(postgres_composition, *, suffix: str = "one"):
    now = datetime.now(UTC)
    identity = Identity(
        identity_type=IdentityType.RIDER,
        status=AccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    family_id = uuid4()
    token_hash = hash_sensitive_identifier(
        f"refresh-token-{suffix}-high-entropy".encode()
    )
    session = SessionRecord(
        subject_id=str(identity.identity_id),
        identity_id=identity.identity_id,
        device_id=uuid4(),
        device_fingerprint_ref=hash_sensitive_identifier(
            f"device-reference-{suffix}".encode()
        ),
        device_category="android",
        application_version="1.0.0",
        operating_system_family="android",
        authentication_method="phone_otp",
        assurance_level="basic",
        risk_state="unknown",
        ip_risk_ref=hash_sensitive_identifier(f"ip-risk-reference-{suffix}".encode()),
        token_family_id=family_id,
        token_hash=token_hash,
        created_at=now,
        expires_at=now + timedelta(days=30),
    )
    with postgres_composition.unit_of_work() as unit_of_work:
        unit_of_work.identities.create(identity)
        unit_of_work.sessions.create(session)
        unit_of_work.refresh_tokens.create_family(
            family_id=family_id,
            identity_id=identity.identity_id,
            session_id=session.session_id,
            token_hash=token_hash,
            created_at=now,
            expires_at=session.expires_at,
        )
    return identity, session, family_id, token_hash


def test_refresh_rotation_replay_revokes_family_and_audits(
    postgres_composition, postgres_engine
) -> None:
    _, session, family_id, original_hash = create_identity_and_session(
        postgres_composition
    )
    replacement_hash = hash_sensitive_identifier(b"replacement-token-high-entropy")
    service = AuthenticationSecurityService()
    with postgres_composition.unit_of_work() as unit_of_work:
        rotated = service.rotate_refresh_token(
            unit_of_work,
            family_id=family_id,
            presented_hash=original_hash,
            replacement_hash=replacement_hash,
            at=datetime.now(UTC),
            correlation_id=uuid4(),
        )
    assert rotated.outcome is RefreshRotationOutcome.ROTATED

    with postgres_composition.unit_of_work() as unit_of_work:
        replay = service.rotate_refresh_token(
            unit_of_work,
            family_id=family_id,
            presented_hash=original_hash,
            replacement_hash=hash_sensitive_identifier(
                b"attacker-replacement-token-high-entropy"
            ),
            at=datetime.now(UTC),
            correlation_id=uuid4(),
        )
    assert replay.outcome is RefreshRotationOutcome.REPLAY_DETECTED
    with postgres_engine.connect() as connection:
        family = (
            connection.execute(
                select(token_families).where(token_families.c.family_id == family_id)
            )
            .mappings()
            .one()
        )
        stored_session = (
            connection.execute(
                select(sessions).where(sessions.c.session_id == session.session_id)
            )
            .mappings()
            .one()
        )
        actions = set(connection.execute(select(audit_events.c.action)).scalars())
    assert family["status"] == "revoked"
    assert family["replay_detected_at"] is not None
    assert stored_session["revocation_reason"] == "refresh_token_replay"
    assert "authentication.session.refreshed" in actions
    assert "authentication.refresh_token.replay_detected" in actions


def test_one_device_and_all_device_logout_are_distinct(postgres_composition) -> None:
    identity, first, _, _ = create_identity_and_session(
        postgres_composition, suffix="first-device"
    )
    second = SessionRecord(
        subject_id=str(identity.identity_id),
        identity_id=identity.identity_id,
        device_id=uuid4(),
        token_hash=hash_sensitive_identifier(b"second-device-token-high-entropy"),
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    with postgres_composition.unit_of_work() as unit_of_work:
        unit_of_work.sessions.create(second)
    with postgres_composition.unit_of_work() as unit_of_work:
        unit_of_work.sessions.revoke(
            first.session_id, revoked_at=datetime.now(UTC), reason="user_logout"
        )
    with postgres_composition.unit_of_work() as unit_of_work:
        assert unit_of_work.sessions.get(first.session_id).revoked_at is not None
        assert unit_of_work.sessions.get(second.session_id).revoked_at is None

    with postgres_composition.unit_of_work() as unit_of_work:
        count = AuthenticationSecurityService().revoke_all_sessions(
            unit_of_work,
            identity_id=identity.identity_id,
            at=datetime.now(UTC),
            reason="security_reset",
            correlation_id=uuid4(),
            actor_type=ActorType.ADMINISTRATOR,
            actor_id="staff_opaque_1",
        )
    assert count == 1


def test_suspension_revokes_sessions_and_rolls_back_atomically(
    postgres_composition,
) -> None:
    identity, session, _, _ = create_identity_and_session(postgres_composition)
    service = AuthenticationSecurityService()
    with (
        pytest.raises(RuntimeError, match="force rollback"),
        postgres_composition.unit_of_work() as unit_of_work,
    ):
        service.change_account_status(
            unit_of_work,
            identity_id=identity.identity_id,
            target=AccountStatus.SUSPENDED,
            at=datetime.now(UTC),
            correlation_id=uuid4(),
        )
        raise RuntimeError("force rollback")
    with postgres_composition.unit_of_work() as unit_of_work:
        assert (
            unit_of_work.identities.get(identity.identity_id).status
            is AccountStatus.ACTIVE
        )
        assert unit_of_work.sessions.get(session.session_id).revoked_at is None

    with postgres_composition.unit_of_work() as unit_of_work:
        service.change_account_status(
            unit_of_work,
            identity_id=identity.identity_id,
            target=AccountStatus.SUSPENDED,
            at=datetime.now(UTC),
            correlation_id=uuid4(),
        )
    with postgres_composition.unit_of_work() as unit_of_work:
        assert unit_of_work.sessions.get(session.session_id).revoked_at is not None


def test_challenge_is_expiring_single_use_attempt_limited_and_rate_limited(
    postgres_composition,
) -> None:
    now = datetime.now(UTC)
    protector = HmacChallengeProtector(b"synthetic-test-key-material-32-bytes-minimum")
    challenge_id = uuid4()
    verifier = protector.protect(challenge_id, "123456")
    challenge = AuthenticationChallenge(
        challenge_id=challenge_id,
        purpose=ChallengePurpose.PHONE_OTP,
        verifier=verifier,
        created_at=now,
        expires_at=now + timedelta(minutes=5),
        max_attempts=2,
    )
    limiter_policy = RateLimitPolicy(
        name="authentication.otp_verify",
        capacity=2,
        refill_tokens=Decimal("1"),
        refill_period_seconds=60,
    )
    key_hash = hash_sensitive_identifier(b"otp-limiter-key-high-entropy")
    service = AuthenticationSecurityService()
    failed_correlation_id = uuid4()
    success_correlation_id = uuid4()
    consumed_correlation_id = uuid4()
    with postgres_composition.unit_of_work() as unit_of_work:
        unit_of_work.authentication_challenges.create(challenge)
        assert unit_of_work.rate_limits.consume(
            key_hash=key_hash, policy=limiter_policy
        ).allowed
        assert not service.verify_challenge(
            unit_of_work,
            challenge_id=challenge_id,
            verifier=protector.protect(challenge_id, "000000"),
            at=now,
            correlation_id=failed_correlation_id,
        )
    with postgres_composition.unit_of_work() as unit_of_work:
        assert service.verify_challenge(
            unit_of_work,
            challenge_id=challenge_id,
            verifier=verifier,
            at=now,
            correlation_id=success_correlation_id,
        )
        assert not service.verify_challenge(
            unit_of_work,
            challenge_id=challenge_id,
            verifier=verifier,
            at=now,
            correlation_id=consumed_correlation_id,
        )
    with postgres_composition.unit_of_work() as unit_of_work:
        actions = {
            event.action
            for correlation_id in (
                failed_correlation_id,
                success_correlation_id,
                consumed_correlation_id,
            )
            for event in unit_of_work.audit_events.find_by_correlation(correlation_id)
        }
    assert {"authentication.succeeded", "authentication.failed"} <= actions


def test_concurrent_refresh_detects_replay(postgres_composition) -> None:
    _, _, family_id, original_hash = create_identity_and_session(postgres_composition)
    service = AuthenticationSecurityService()

    def rotate(index: int):
        with postgres_composition.unit_of_work() as unit_of_work:
            return service.rotate_refresh_token(
                unit_of_work,
                family_id=family_id,
                presented_hash=original_hash,
                replacement_hash=hash_sensitive_identifier(
                    f"concurrent-replacement-{index}-entropy".encode()
                ),
                at=datetime.now(UTC),
                correlation_id=uuid4(),
            ).outcome

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(rotate, range(2)))
    assert set(outcomes) == {
        RefreshRotationOutcome.ROTATED,
        RefreshRotationOutcome.REPLAY_DETECTED,
    }
