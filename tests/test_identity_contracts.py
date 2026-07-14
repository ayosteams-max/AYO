from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.identity.audit_taxonomy import AUTHENTICATION_AUDIT_ACTIONS
from BACKEND.identity.authentication import (
    AuthenticationChallenge,
    ChallengePurpose,
    HmacChallengeProtector,
)
from BACKEND.identity.models import (
    SAFE_AUTHENTICATION_FAILURE,
    AccessTokenClaims,
    AccountStatus,
    AssuranceLevel,
    Identity,
    IdentityType,
)
from BACKEND.identity.passwords import Argon2idPasswordVerifier
from BACKEND.identity.risk import AuthenticationRiskContext, RiskState


def identity(status: AccountStatus = AccountStatus.PENDING) -> Identity:
    now = datetime.now(UTC)
    return Identity(
        identity_type=IdentityType.RIDER,
        status=status,
        created_at=now,
        updated_at=now,
    )


def test_identity_taxonomy_and_status_transitions_are_constrained() -> None:
    rider = identity()
    active = rider.transition(AccountStatus.ACTIVE, at=datetime.now(UTC))
    assert active.status is AccountStatus.ACTIVE
    assert {item.value for item in IdentityType} >= {
        "anonymous",
        "rider",
        "driver",
        "staff",
        "administrator",
        "service",
        "merchant",
        "service_provider",
    }
    with pytest.raises(ValueError, match="Invalid account-status transition"):
        rider.transition(AccountStatus.SUSPENDED, at=datetime.now(UTC))
    with pytest.raises(ValueError, match="timezone-aware"):
        active.transition(AccountStatus.SUSPENDED, at=datetime.now())


def test_access_claims_are_short_lived_and_clock_skew_is_bounded() -> None:
    now = datetime.now(UTC)
    claims = AccessTokenClaims(
        identity_id=uuid4(),
        session_id=uuid4(),
        identity_type=IdentityType.RIDER,
        assurance_level=AssuranceLevel.BASIC,
        issued_at=now,
        not_before=now,
        expires_at=now + timedelta(minutes=5),
        audience="ayo-api",
        issuer="ayo",
        key_id="future-key-1",
    )
    assert claims.valid_at(now - timedelta(seconds=20))
    assert not claims.valid_at(now + timedelta(minutes=6))
    with pytest.raises(ValueError, match="Clock skew"):
        claims.valid_at(now, clock_skew_seconds=121)
    with pytest.raises(ValueError, match="timezone-aware"):
        claims.valid_at(datetime.now())
    with pytest.raises(ValidationError, match="15 minutes"):
        AccessTokenClaims.model_validate(
            {**claims.model_dump(), "expires_at": now + timedelta(minutes=20)}
        )


def test_argon2id_verifier_stores_no_plaintext_and_supports_upgrade() -> None:
    passwords = Argon2idPasswordVerifier()
    raw = "correct horse battery staple"
    verifier = passwords.hash(raw)
    assert raw not in verifier
    assert verifier.startswith("$argon2id$")
    assert passwords.verify(verifier, raw)
    assert not passwords.verify(verifier, "incorrect password value")
    assert not passwords.needs_upgrade(verifier)
    assert passwords.needs_upgrade("not-a-verifier")


def test_otp_challenge_is_keyed_single_secret_material_not_plaintext() -> None:
    protector = HmacChallengeProtector(b"synthetic-test-key-material-32-bytes-minimum")
    challenge_id = uuid4()
    otp = "123456"
    verifier = protector.protect(challenge_id, otp)
    challenge = AuthenticationChallenge(
        challenge_id=challenge_id,
        purpose=ChallengePurpose.PHONE_OTP,
        verifier=verifier,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        max_attempts=3,
    )
    assert otp.encode() not in challenge.verifier
    assert protector.matches(challenge_id, otp, challenge.verifier)
    assert not protector.matches(challenge_id, "654321", challenge.verifier)
    assert SAFE_AUTHENTICATION_FAILURE == "Authentication could not be completed."


def test_secret_boundaries_reject_unsafe_values() -> None:
    passwords = Argon2idPasswordVerifier()
    with pytest.raises(ValueError, match="length"):
        passwords.hash("too-short")
    with pytest.raises(ValueError, match="at least 32 bytes"):
        HmacChallengeProtector(b"short")

    protector = HmacChallengeProtector(b"synthetic-test-key-material-32-bytes-minimum")
    with pytest.raises(ValueError, match="length"):
        protector.protect(uuid4(), "")
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="expiry"):
        AuthenticationChallenge(
            purpose=ChallengePurpose.PHONE_OTP,
            verifier=b"x" * 32,
            created_at=now,
            expires_at=now,
        )


def test_authentication_audit_taxonomy_covers_security_lifecycle() -> None:
    assert {
        "authentication.succeeded",
        "authentication.failed",
        "authentication.refresh_token.replay_detected",
        "authentication.sessions.all_revoked",
        "authentication.recovery.denied",
        "authentication.step_up.failed",
    } <= AUTHENTICATION_AUDIT_ACTIONS


def test_risk_context_accepts_only_minimized_bounded_references() -> None:
    context = AuthenticationRiskContext(
        policy_version="risk-v1",
        device_reference=b"d" * 32,
        ip_risk_reference=b"i" * 32,
        new_device=True,
        repeated_failures=2,
    )
    assert context.new_device
    assert RiskState.HIGH.value == "high"
    with pytest.raises(ValidationError):
        AuthenticationRiskContext(
            policy_version="risk-v1",
            device_reference=b"raw-short-value",
        )
    with pytest.raises(ValidationError):
        AuthenticationRiskContext.model_validate(
            {"policy_version": "risk-v1", "raw_ip_address": "192.0.2.1"}
        )
