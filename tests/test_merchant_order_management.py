from datetime import UTC, datetime
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
from BACKEND.merchant_orders.application import MerchantOrderApplication
from BACKEND.merchant_orders.engine import MerchantOrderConflict, transition
from BACKEND.merchant_orders.models import (
    MerchantOrderAction,
    MerchantOrderRecord,
    MerchantOrderView,
    OrderTimelineEvent,
    RejectionDecision,
)
from BACKEND.ordering.models import OrderLineEvidence, OrderPricingEvidence, OrderState
from BACKEND.routes.merchant_orders import MerchantDecisionCommand

NOW = datetime(2026, 7, 21, 12, tzinfo=UTC)


class FakeUnit:
    def __init__(self, merchant: MerchantProfile) -> None:
        self.merchants = self
        self.merchant_orders = self
        self.merchant = merchant
        self.read_called = False

    def get_profile(self, merchant_id, *, lock=False):
        del lock
        return self.merchant if merchant_id == self.merchant.merchant_id else None

    def list_for_merchant(self, merchant_id, *, state, limit):
        del merchant_id, state, limit
        self.read_called = True
        return ()


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


def record(
    state: OrderState = OrderState.WAITING_FOR_MERCHANT_CONFIRMATION, version: int = 1
) -> MerchantOrderRecord:
    line = OrderLineEvidence(
        item_id=uuid4(),
        item_version=1,
        name="Ethiopian coffee",
        kind="product",
        quantity=2,
        unit_price_minor=1000,
        line_total_minor=2000,
        currency="ETB",
    )
    pricing = OrderPricingEvidence(
        policy_version="commerce.catalogue_subtotal.v1",
        subtotal_minor=2000,
        currency="ETB",
        evidence_hash="a" * 64,
    )
    return MerchantOrderRecord(
        order_id=uuid4(),
        merchant_id=uuid4(),
        merchant_display_name="Addis Market",
        state=state,
        lines=(line,),
        pricing=pricing,
        evidence_hash="b" * 64,
        version=version,
        created_at=NOW,
    )


def test_only_waiting_order_can_be_accepted_or_rejected() -> None:
    assert (
        transition(
            OrderState.WAITING_FOR_MERCHANT_CONFIRMATION, MerchantOrderAction.ACCEPT
        )
        is OrderState.ACCEPTED
    )
    assert (
        transition(
            OrderState.WAITING_FOR_MERCHANT_CONFIRMATION, MerchantOrderAction.REJECT
        )
        is OrderState.REJECTED
    )
    for terminal in (OrderState.ACCEPTED, OrderState.REJECTED):
        with pytest.raises(MerchantOrderConflict, match="order_transition_not_allowed"):
            transition(terminal, MerchantOrderAction.ACCEPT)


def test_merchant_order_retrieval_checks_owner_before_repository_access() -> None:
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
    app = MerchantOrderApplication(FakeComposition(unit))
    subject = AuthorizationSubject(
        identity_id=intruder,
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    with pytest.raises(MerchantOrderConflict, match="access_denied"):
        app.list_orders(
            subject, merchant_id=merchant.merchant_id, state=None, limit=50, at=NOW
        )
    assert not unit.read_called


def test_rejection_requires_customer_reason_and_keeps_internal_note_separate() -> None:
    order = record(OrderState.REJECTED, 2)
    rejection = RejectionDecision(
        order_id=order.order_id,
        customer_reason_code="merchant_declined",
        customer_message="This item cannot be prepared today.",
        internal_merchant_note="Supplier did not arrive.",
        decided_by_identity_id=uuid4(),
        decided_at=NOW,
    )
    timeline = (
        OrderTimelineEvent(
            order_id=order.order_id,
            merchant_id=order.merchant_id,
            event_type="commerce.order.rejected",
            from_state=OrderState.WAITING_FOR_MERCHANT_CONFIRMATION,
            to_state=OrderState.REJECTED,
            actor_identity_id=uuid4(),
            order_version=2,
            customer_reason_code="merchant_declined",
            occurred_at=NOW,
        ),
    )
    view = MerchantOrderView(order=order, timeline=timeline, rejection=rejection)
    assert view.rejection is not None
    assert view.rejection.customer_message != view.rejection.internal_merchant_note
    assert "customer_identity_id" not in view.model_dump()["order"]


def test_rejected_view_without_rejection_evidence_fails_closed() -> None:
    with pytest.raises(ValidationError, match="rejection evidence"):
        MerchantOrderView(order=record(OrderState.REJECTED, 2), timeline=())


def test_decision_command_forbids_notes_on_accept_and_requires_rejection_message() -> (
    None
):
    with pytest.raises(ValidationError):
        MerchantDecisionCommand(
            expected_version=1,
            action=MerchantOrderAction.ACCEPT,
            internal_merchant_note="hidden",
        )
    with pytest.raises(ValidationError):
        MerchantDecisionCommand(
            expected_version=1,
            action=MerchantOrderAction.REJECT,
            customer_reason_code="merchant_declined",
        )
    valid = MerchantDecisionCommand(
        expected_version=1,
        action=MerchantOrderAction.REJECT,
        customer_reason_code="merchant_declined",
        customer_message="Unavailable today",
        internal_merchant_note="Private",
    )
    assert valid.internal_merchant_note == "Private"


def test_merchant_order_runtime_is_disabled_and_production_activation_fails_closed() -> (
    None
):
    assert not Settings().MERCHANT_ORDER_MANAGEMENT_ENABLED
    with pytest.raises(ValidationError, match="production activation"):
        Settings(
            ENVIRONMENT=AppEnvironment.PRODUCTION,
            MERCHANT_ORDER_MANAGEMENT_ENABLED=True,
        )
