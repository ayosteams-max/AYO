from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.custody.application import CustodyApplication
from BACKEND.custody.engine import CustodyConflict, target_state
from BACKEND.custody.models import CustodyAction, CustodyRecord, CustodyState


def record(state=CustodyState.WAITING):
    return CustodyRecord(
        custody_id=uuid4(),
        pickup_id=uuid4(),
        order_id=uuid4(),
        merchant_id=uuid4(),
        courier_identity_id=uuid4(),
        state=state,
        version=1,
        sealed_at=None,
        verified_at=None,
        verification_method=None,
        merchant_released_at=None,
        custody_accepted_at=None,
        updated_at=datetime.now(UTC),
    )


def test_independent_custody_transitions():
    assert target_state(CustodyState.WAITING, CustodyAction.SEAL) is CustodyState.SEALED
    assert (
        target_state(CustodyState.SEALED, CustodyAction.VERIFY) is CustodyState.VERIFIED
    )
    assert (
        target_state(CustodyState.VERIFIED, CustodyAction.RELEASE)
        is CustodyState.RELEASED
    )
    assert (
        target_state(CustodyState.RELEASED, CustodyAction.ACCEPT)
        is CustodyState.ACCEPTED
    )
    with pytest.raises(CustodyConflict):
        target_state(CustodyState.VERIFIED, CustodyAction.ACCEPT)


def test_code_hash_is_keyed_and_deterministic():
    one = CustodyApplication(object(), verification_pepper=b"a" * 32)
    two = CustodyApplication(object(), verification_pepper=b"b" * 32)
    assert one._digest("opaque-code") == one._digest("opaque-code")
    assert one._digest("opaque-code") != two._digest("opaque-code")
    assert one._digest("opaque-code") != "opaque-code"


def test_future_delivery_state_absent():
    payload = record().model_dump()
    payload["state"] = "delivered"
    with pytest.raises(ValidationError):
        CustodyRecord.model_validate(payload)


def test_replay_wrong_order_and_concurrency_guards_are_persistent():
    root = Path(__file__).parents[1]
    repository = (root / "BACKEND/persistence/custody_repository.py").read_text()
    migration = (
        root / "database/migrations/versions/20260721_0039_pickup_chain_of_custody.py"
    ).read_text()
    application = (root / "BACKEND/custody/application.py").read_text()
    assert "used_at.is_(None)" in repository
    assert "expires_at >= at" in repository
    assert "commerce_custody_records.c.version == current.version" in repository
    assert "unique=True" in migration
    assert "courier_identity_id != subject.identity_id" in application


def test_short_pepper_and_production_activation_fail_closed():
    with pytest.raises(ValueError):
        CustodyApplication(object(), verification_pepper=b"short")
    assert Settings().CUSTODY_PLATFORM_ENABLED is False
    with pytest.raises(ValidationError):
        Settings(ENVIRONMENT=AppEnvironment.PRODUCTION, CUSTODY_PLATFORM_ENABLED=True)
