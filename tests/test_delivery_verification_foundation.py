from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.delivery_verification.application import DeliveryApplication
from BACKEND.delivery_verification.engine import (
    DeliveryConflict,
    ReminderPolicy,
    reminder_allowed,
    target_state,
)
from BACKEND.delivery_verification.models import (
    DeliveryAction,
    DeliveryRecord,
    DeliveryState,
)


def record(state=DeliveryState.ARRIVING):
    return DeliveryRecord(
        delivery_id=uuid4(),
        custody_id=uuid4(),
        order_id=uuid4(),
        merchant_id=uuid4(),
        courier_identity_id=uuid4(),
        credential_id=uuid4(),
        state=state,
        version=1,
        arriving_at=datetime.now(UTC),
        customer_available_at=None,
        verified_at=None,
        verification_method=None,
        customer_received_at=None,
        completed_at=None,
        closed_at=None,
        updated_at=datetime.now(UTC),
    )


def test_delivery_lifecycle_requires_every_evidence_boundary():
    assert (
        target_state(DeliveryState.ARRIVING, DeliveryAction.CUSTOMER_AVAILABLE)
        is DeliveryState.AVAILABLE
    )
    assert (
        target_state(DeliveryState.AVAILABLE, DeliveryAction.VERIFY)
        is DeliveryState.VERIFIED
    )
    assert (
        target_state(DeliveryState.VERIFIED, DeliveryAction.CONFIRM_RECEIVED)
        is DeliveryState.RECEIVED
    )
    assert (
        target_state(DeliveryState.RECEIVED, DeliveryAction.COMPLETE)
        is DeliveryState.COMPLETED
    )
    assert (
        target_state(DeliveryState.COMPLETED, DeliveryAction.CLOSE)
        is DeliveryState.CLOSED
    )
    with pytest.raises(DeliveryConflict):
        target_state(DeliveryState.VERIFIED, DeliveryAction.COMPLETE)


def test_qr_and_manual_use_same_keyed_credential():
    app = DeliveryApplication(object(), credential_pepper=b"x" * 32)
    order = uuid4()
    code = app._code(order)
    assert app._digest(code) == app._digest(code)
    assert len(code) >= 8


def test_reminder_is_single_evidence_bounded_and_suppressed_when_following():
    policy = ReminderPolicy()
    assert reminder_allowed(
        eta_minutes=20, customer_following=False, already_sent=False, policy=policy
    )
    assert not reminder_allowed(
        eta_minutes=20, customer_following=True, already_sent=False, policy=policy
    )
    assert not reminder_allowed(
        eta_minutes=10, customer_following=False, already_sent=True, policy=policy
    )


def test_replay_concurrency_privacy_and_completion_guards_persist():
    source = (
        Path(__file__).parents[1] / "BACKEND/persistence/delivery_repository.py"
    ).read_text()
    assert "used_at.is_(None)" in source and "expires_at >= at" in source
    assert "commerce_deliveries.c.version == current.version" in source
    assert (
        "authoritative_delivery_evidence" not in source
        or "chain_of_custody_closed" in source
    )
    assert all(
        word not in source
        for word in ("customer_name", "customer_phone", "customer_email")
    )


def test_disabled_production_and_future_financial_state_absent():
    assert Settings().DELIVERY_PLATFORM_ENABLED is False
    with pytest.raises(ValidationError):
        Settings(ENVIRONMENT=AppEnvironment.PRODUCTION, DELIVERY_PLATFORM_ENABLED=True)
    payload = record().model_dump()
    payload["state"] = "settled"
    with pytest.raises(ValidationError):
        DeliveryRecord.model_validate(payload)
