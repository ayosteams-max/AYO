from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.identity.models import IdentityType
from BACKEND.merchant.models import (
    MerchantKind,
    MerchantProfile,
    MerchantState,
    OnboardingSource,
)
from BACKEND.merchant_preparation.application import MerchantPreparationApplication
from BACKEND.merchant_preparation.engine import (
    PreparationConflict,
    target_state,
    validate_progress,
)
from BACKEND.merchant_preparation.models import (
    PreparationAction,
    PreparationEvent,
    PreparationRecord,
)
from BACKEND.ordering.models import OrderState
from BACKEND.routes.merchant_preparation import PreparationCommand

NOW = datetime(2026, 7, 21, 15, tzinfo=UTC)


class FakeUnit:
    def __init__(self, merchant: MerchantProfile) -> None:
        self.merchant = merchant
        self.merchants = self
        self.preparation = self
        self.read_called = False

    def get_profile(self, merchant_id, *, lock=False):
        del lock
        return self.merchant if merchant_id == self.merchant.merchant_id else None

    def get_view(self, order_id):
        del order_id
        self.read_called = True
        return None


class FakeComposition:
    def __init__(self, unit: FakeUnit) -> None:
        self.unit = unit

    class Context:
        def __init__(self, unit):
            self.unit = unit

        def __enter__(self):
            return self.unit

        def __exit__(self, *_):
            return False

    def unit_of_work(self):
        return self.Context(self.unit)


def test_preparation_lifecycle_is_explicit_and_future_states_are_absent() -> None:
    assert (
        target_state(OrderState.ACCEPTED, PreparationAction.START)
        is OrderState.PREPARING
    )
    assert (
        target_state(OrderState.PREPARING, PreparationAction.UPDATE_PROGRESS)
        is OrderState.PREPARING
    )
    assert (
        target_state(OrderState.PREPARING, PreparationAction.MARK_READY)
        is OrderState.READY_FOR_PICKUP
    )
    with pytest.raises(PreparationConflict, match="transition_not_allowed"):
        target_state(OrderState.REJECTED, PreparationAction.START)
    with pytest.raises(ValueError):
        OrderState("courier_assigned")


def test_progress_is_monotonic_and_ready_is_not_a_progress_value() -> None:
    assert validate_progress(20, 45) == 45
    for invalid in (0, 20, 19, 100):
        with pytest.raises(PreparationConflict):
            validate_progress(20, invalid)


def test_preparation_retrieval_denies_non_owner_before_reading_evidence() -> None:
    owner, intruder = uuid4(), uuid4()
    merchant = MerchantProfile(
        owner_identity_id=owner,
        legal_name="Addis Merchant PLC",
        display_name="Addis Merchant",
        kind=MerchantKind.COMPANY,
        onboarding_source=OnboardingSource.SELF,
        state=MerchantState.APPROVED,
        capability_code="merchant.general",
        market_code="ET-AA",
        created_at=NOW,
        updated_at=NOW,
    )
    unit = FakeUnit(merchant)
    subject = AuthorizationSubject(
        identity_id=intruder,
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    with pytest.raises(PreparationConflict, match="access_denied"):
        MerchantPreparationApplication(FakeComposition(unit)).detail(
            subject, merchant_id=merchant.merchant_id, order_id=uuid4()
        )
    assert not unit.read_called


def test_preparation_record_preserves_server_estimate_and_timestamps() -> None:
    value = PreparationRecord(
        order_id=uuid4(),
        merchant_id=uuid4(),
        started_at=NOW,
        estimated_duration_seconds=1200,
        estimated_ready_at=NOW + timedelta(minutes=20),
        progress_percent=25,
        updated_at=NOW,
    )
    assert value.estimated_ready_at - value.started_at == timedelta(minutes=20)
    assert value.ready_at is None


def test_preparation_event_is_immutable_and_auditable() -> None:
    event = PreparationEvent(
        order_id=uuid4(),
        merchant_id=uuid4(),
        event_type="commerce.preparation.progress_updated",
        actor_identity_id=uuid4(),
        order_version=4,
        progress_percent=50,
        delay_reason_code="merchant_reported_delay",
        delay_message="Preparation needs ten more minutes.",
        occurred_at=NOW,
    )
    assert event.order_version == 4
    with pytest.raises(ValidationError):
        event.progress_percent = 60  # type: ignore[misc]


def test_command_contract_requires_action_specific_fields_and_delay_pair() -> None:
    assert (
        PreparationCommand(
            expected_version=2,
            action=PreparationAction.START,
            estimated_duration_minutes=20,
        ).estimated_duration_minutes
        == 20
    )
    assert (
        PreparationCommand(
            expected_version=3,
            action=PreparationAction.UPDATE_PROGRESS,
            progress_percent=40,
            delay_reason_code="merchant_reported_delay",
            delay_message="Ten more minutes",
        ).progress_percent
        == 40
    )
    assert (
        PreparationCommand(
            expected_version=4, action=PreparationAction.MARK_READY
        ).action
        is PreparationAction.MARK_READY
    )
    with pytest.raises(ValidationError):
        PreparationCommand(expected_version=2, action=PreparationAction.START)
    with pytest.raises(ValidationError):
        PreparationCommand(
            expected_version=3,
            action=PreparationAction.UPDATE_PROGRESS,
            progress_percent=40,
            delay_reason_code="delay_only",
        )
    with pytest.raises(ValidationError):
        PreparationCommand(
            expected_version=4,
            action=PreparationAction.MARK_READY,
            progress_percent=99,
        )


def test_preparation_is_disabled_and_production_activation_fails_closed() -> None:
    assert not Settings().MERCHANT_PREPARATION_ENABLED
    with pytest.raises(ValidationError, match="production activation"):
        Settings(
            ENVIRONMENT=AppEnvironment.PRODUCTION, MERCHANT_PREPARATION_ENABLED=True
        )
