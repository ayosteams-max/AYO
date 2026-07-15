from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from BACKEND.identity.verification import (
    AsymmetricJwtVerifier,
    AuthenticationFailed,
    RotatingStaticKeyProvider,
    VerifiedTokenIdentity,
)

ISSUER = "https://identity.test.ayo.example"
AUDIENCE = "ayo-api"


@pytest.fixture(scope="module")
def keys():
    first = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    second = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return first, second, forged


def claims(**overrides):
    now = datetime.now(UTC)
    value = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "nbf": now - timedelta(seconds=1),
        "exp": now + timedelta(minutes=5),
        "sub": str(uuid4()),
        "sid": str(uuid4()),
        "jti": str(uuid4()),
        "identity_type": "rider",
        "assurance_level": "basic",
    }
    value.update(overrides)
    return value


def token(private_key, *, key_id="key-1", algorithm="RS256", **overrides):
    return jwt.encode(
        claims(**overrides),
        private_key,
        algorithm=algorithm,
        headers={"kid": key_id, "typ": "at+jwt"},
    )


def verifier(keys):
    first, second, _ = keys
    return AsymmetricJwtVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        algorithms=("RS256",),
        key_provider=RotatingStaticKeyProvider(
            {
                ("key-1", "RS256"): first.public_key(),
                ("key-2", "RS256"): second.public_key(),
            }
        ),
    )


def test_valid_asymmetric_tokens_and_rotated_keys_are_accepted(keys) -> None:
    first, second, _ = keys
    checked = verifier(keys)
    one = checked.verify(token(first))
    two = checked.verify(token(second, key_id="key-2"))
    assert one.key_id == "key-1"
    assert two.key_id == "key-2"
    assert one.issuer == ISSUER
    assert one.audience == AUDIENCE


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"exp": datetime.now(UTC) - timedelta(seconds=60)}, "expired"),
        ({"nbf": datetime.now(UTC) + timedelta(minutes=5)}, "not_before"),
        ({"iss": "https://attacker.invalid"}, "issuer"),
        ({"aud": "other-api"}, "audience"),
    ],
)
def test_expired_not_before_wrong_issuer_and_audience_fail_closed(
    keys, overrides, reason
) -> None:
    del reason
    first, _, _ = keys
    with pytest.raises(AuthenticationFailed):
        verifier(keys).verify(token(first, **overrides))


def test_forged_malformed_unknown_key_and_role_claims_are_rejected(keys) -> None:
    first, _, forged = keys
    checked = verifier(keys)
    invalid = [
        "not-a-jwt-value",
        token(forged),
        token(first, key_id="unknown-key"),
        token(first, roles=["administrator"]),
        token(first, permissions=["dispatch.worker.recover"]),
    ]
    for value in invalid:
        with pytest.raises(AuthenticationFailed):
            checked.verify(value)


def test_symmetric_or_empty_key_configuration_is_prohibited(keys) -> None:
    first, _, _ = keys
    with pytest.raises(ValueError):
        RotatingStaticKeyProvider({})
    with pytest.raises(ValueError):
        AsymmetricJwtVerifier(
            issuer=ISSUER,
            audience=AUDIENCE,
            algorithms=("HS256",),
            key_provider=RotatingStaticKeyProvider(
                {("key-1", "RS256"): first.public_key()}
            ),
        )
    with pytest.raises(ValueError):
        AsymmetricJwtVerifier(
            issuer="",
            audience=AUDIENCE,
            key_provider=RotatingStaticKeyProvider(
                {("key-1", "RS256"): first.public_key()}
            ),
        )
    with pytest.raises(ValueError):
        AsymmetricJwtVerifier(
            issuer=ISSUER,
            audience=AUDIENCE,
            clock_skew_seconds=121,
            key_provider=RotatingStaticKeyProvider(
                {("key-1", "RS256"): first.public_key()}
            ),
        )


def test_token_identity_rejects_unsafe_time_bounds() -> None:
    now = datetime.now(UTC)
    base = {
        "token_id": uuid4(),
        "identity_id": uuid4(),
        "session_id": uuid4(),
        "identity_type": "rider",
        "assurance_level": "basic",
        "issued_at": now,
        "not_before": now,
        "issuer": ISSUER,
        "audience": AUDIENCE,
        "key_id": "key-1",
    }
    with pytest.raises(ValueError):
        VerifiedTokenIdentity(**base, expires_at=now)
    with pytest.raises(ValueError):
        VerifiedTokenIdentity(**base, expires_at=now + timedelta(minutes=16))
    with pytest.raises(ValueError):
        VerifiedTokenIdentity(
            **{**base, "issued_at": now.replace(tzinfo=None)},
            expires_at=now + timedelta(minutes=5),
        )


def test_short_token_and_untrusted_header_fail_before_key_resolution(keys) -> None:
    first, _, _ = keys
    checked = verifier(keys)
    with pytest.raises(AuthenticationFailed):
        checked.verify("short")
    wrong_type = jwt.encode(
        claims(),
        first,
        algorithm="RS256",
        headers={"kid": "key-1", "typ": "not-an-access-token"},
    )
    with pytest.raises(AuthenticationFailed):
        checked.verify(wrong_type)
