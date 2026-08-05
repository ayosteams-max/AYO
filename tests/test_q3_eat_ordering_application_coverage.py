from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.catalogue.models import (
    CatalogueItem,
    ItemAvailability,
    ItemKind,
    ItemStatus,
    ItemVisibility,
)
from BACKEND.eat_availability.application import (
    ConfigureEatAvailability,
    EatAvailabilityApplication,
    EvaluateEatAvailability,
)
from BACKEND.eat_availability.models import (
    EatAvailabilityOutcome,
    EatAvailabilityPolicy,
    EatAvailabilityState,
)
from BACKEND.identity.models import IdentityType
from BACKEND.merchant.models import (
    MerchantKind,
    MerchantProfile,
    MerchantState,
    OnboardingSource,
)
from BACKEND.ordering.application import OrderingApplication
from BACKEND.ordering.engine import OrderingConflict
from BACKEND.ordering.models import (
    BasketLine,
    CanonicalOrder,
    PublicCatalogueItem,
    PublicMerchant,
)

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


class _UnitContext(AbstractContextManager[Any]):
    def __init__(self, unit: Any) -> None:
        self.unit = unit

    def __enter__(self) -> Any:
        return self.unit

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class _Composition:
    def __init__(self, unit: Any) -> None:
        self.unit = unit

    def unit_of_work(self) -> _UnitContext:
        return _UnitContext(self.unit)


def _subject(identity_id: UUID | None = None) -> AuthorizationSubject:
    return AuthorizationSubject(
        identity_id=identity_id or uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )


def _merchant(
    merchant_id: UUID,
    *,
    state: MerchantState = MerchantState.APPROVED,
) -> MerchantProfile:
    return MerchantProfile(
        merchant_id=merchant_id,
        owner_identity_id=uuid4(),
        legal_name="Addis Kitchen PLC",
        display_name="Addis Kitchen",
        kind=MerchantKind.COMPANY,
        onboarding_source=OnboardingSource.SELF,
        state=state,
        capability_code="ayo.eat",
        market_code="ET-AA",
        created_at=NOW,
        updated_at=NOW,
    )


def _item(
    merchant_id: UUID,
    *,
    status: ItemStatus = ItemStatus.ACTIVE,
    visibility: ItemVisibility = ItemVisibility.PUBLIC,
    availability: ItemAvailability = ItemAvailability.AVAILABLE,
    price: int | None = 2500,
    modifier_version: int | None = None,
) -> CatalogueItem:
    return CatalogueItem(
        merchant_id=merchant_id,
        kind=ItemKind.MEAL,
        name="Vegetable Tibs",
        status=status,
        visibility=visibility,
        availability=availability,
        base_price_minor=price,
        modifier_contract_version=modifier_version,
        created_at=NOW,
        updated_at=NOW,
    )


def _policy(
    merchant_id: UUID,
    *,
    coverage: str = "coverage:addis:v1",
) -> EatAvailabilityPolicy:
    return EatAvailabilityPolicy(
        merchant_id=merchant_id,
        area_reference="area:addis:v1",
        coverage_reference=coverage,
        state=EatAvailabilityState.AVAILABLE,
        reason_code="configured",
        effective_from=NOW - timedelta(hours=1),
        effective_until=NOW + timedelta(hours=1),
        created_by_identity_id=uuid4(),
        created_at=NOW,
        updated_at=NOW,
    )


def _unit() -> Any:
    unit = MagicMock()
    unit.audit_events = []
    return unit


def test_availability_configuration_enforces_authority_and_concurrency() -> None:
    subject = _subject()
    command = ConfigureEatAvailability(
        merchant_id=uuid4(),
        area_reference="area:addis:v1",
        coverage_reference="coverage:addis:v1",
        state=EatAvailabilityState.AVAILABLE,
        reason_code="configured",
        effective_from=NOW,
    )
    unit = _unit()
    app = EatAvailabilityApplication(_Composition(unit))

    unit.authorization.has_permission.return_value = False
    with pytest.raises(PermissionError, match="manage_denied"):
        app.configure(
            subject,
            command=command,
            idempotency_key="configure-availability-0001",
            correlation_id=uuid4(),
            request_id=uuid4(),
            at=NOW,
        )

    unit.authorization.has_permission.return_value = True
    unit.eat_availability.reserve.return_value = None
    unit.eat_availability.find.return_value = _policy(command.merchant_id)
    with pytest.raises(ValueError, match="expected_version_required"):
        app.configure(
            subject,
            command=command,
            idempotency_key="configure-availability-0002",
            correlation_id=uuid4(),
            request_id=uuid4(),
            at=NOW,
        )

    unit.eat_availability.find.return_value = None
    with pytest.raises(ValueError, match="expected_version_required"):
        app.configure(
            subject,
            command=command,
            idempotency_key="configure-availability-0003",
            correlation_id=uuid4(),
            request_id=uuid4(),
            expected_version=1,
            at=NOW,
        )

    current = _policy(command.merchant_id)
    unit.eat_availability.find.return_value = current
    with pytest.raises(ValueError, match="version_conflict"):
        app.configure(
            subject,
            command=command,
            idempotency_key="configure-availability-0004",
            correlation_id=uuid4(),
            request_id=uuid4(),
            expected_version=current.version + 1,
            at=NOW,
        )


def test_availability_configuration_records_governed_audit_and_replays() -> None:
    subject = _subject()
    merchant_id = uuid4()
    command = ConfigureEatAvailability(
        merchant_id=merchant_id,
        area_reference="area:addis:v1",
        coverage_reference="coverage:addis:v1",
        state=EatAvailabilityState.AVAILABLE,
        reason_code="configured",
        effective_from=NOW,
    )
    unit = _unit()
    unit.authorization.has_permission.return_value = True
    unit.eat_availability.reserve.return_value = None
    unit.eat_availability.find.return_value = None
    unit.eat_availability.put.side_effect = lambda value, **_: value
    app = EatAvailabilityApplication(_Composition(unit))

    created = app.configure(
        subject,
        command=command,
        idempotency_key="configure-availability-create",
        correlation_id=uuid4(),
        request_id=uuid4(),
        at=NOW,
    )
    assert unit.audit_events[0].resource_id == str(created.policy_id)
    assert unit.audit_events[0].safe_metadata == {
        "policy_version": 1,
        "state_to": "available",
    }

    existing = _policy(merchant_id)
    unit.eat_availability.reserve.return_value = (
        f"eat_availability/{existing.policy_id}"
    )
    unit.eat_availability.get.return_value = existing
    assert (
        app.configure(
            subject,
            command=command,
            idempotency_key="configure-availability-replay",
            correlation_id=uuid4(),
            request_id=uuid4(),
            at=NOW,
        )
        == existing
    )
    unit.eat_availability.get.return_value = None
    with pytest.raises(RuntimeError, match="result unavailable"):
        app.configure(
            subject,
            command=command,
            idempotency_key="configure-availability-orphan",
            correlation_id=uuid4(),
            request_id=uuid4(),
            at=NOW,
        )


@pytest.mark.parametrize(
    ("merchant_state", "coverage", "item_available", "expected"),
    [
        (
            MerchantState.APPROVED,
            "coverage:addis:v1",
            True,
            EatAvailabilityOutcome.AVAILABLE,
        ),
        (
            MerchantState.SUSPENDED,
            "coverage:addis:v1",
            True,
            EatAvailabilityOutcome.UNKNOWN_OR_STALE,
        ),
        (
            MerchantState.APPROVED,
            "coverage:wrong:v1",
            True,
            EatAvailabilityOutcome.UNKNOWN_OR_STALE,
        ),
        (
            MerchantState.APPROVED,
            "coverage:addis:v1",
            False,
            EatAvailabilityOutcome.PRODUCT_UNAVAILABLE,
        ),
    ],
)
def test_availability_evaluation_records_source_owned_evidence(
    merchant_state: MerchantState,
    coverage: str,
    item_available: bool,
    expected: EatAvailabilityOutcome,
) -> None:
    merchant_id = uuid4()
    item = _item(
        merchant_id,
        availability=(
            ItemAvailability.AVAILABLE
            if item_available
            else ItemAvailability.OUT_OF_STOCK
        ),
    )
    unit = _unit()
    unit.merchants.get_profile.return_value = _merchant(
        merchant_id, state=merchant_state
    )
    unit.catalogue.get_item.return_value = item
    unit.eat_availability.find.return_value = _policy(merchant_id)
    unit.eat_availability.record_evaluation.side_effect = lambda value: value
    result = EatAvailabilityApplication(_Composition(unit)).evaluate(
        _subject(),
        command=EvaluateEatAvailability(
            merchant_id=merchant_id,
            merchant_version=1,
            merchant_open=True,
            area_reference="area:addis:v1",
            coverage_reference=coverage,
            item_ids=(item.item_id,),
        ),
        correlation_id=uuid4(),
        request_id=uuid4(),
        at=NOW,
    )
    assert result.outcome is expected
    assert len(result.evidence_hash) == 64


def _ordering_unit(
    subject: AuthorizationSubject,
    merchant: MerchantProfile,
    item: CatalogueItem,
) -> Any:
    unit = _unit()
    unit.orders.reserve.return_value = (uuid4(), True)
    unit.orders.get.return_value = None
    unit.orders.approved_modifier_codes.return_value = {"extra"}
    unit.orders.create.side_effect = lambda value, **_: value
    unit.merchants.get_profile.return_value = merchant
    unit.catalogue.get_item.return_value = item
    unit.eat_availability.find.return_value = _policy(merchant.merchant_id)
    unit.eat_availability.record_evaluation.side_effect = lambda value: value
    return unit


def test_ordering_creates_channel_neutral_order_with_availability_evidence() -> None:
    subject = _subject()
    merchant_id = uuid4()
    merchant = _merchant(merchant_id)
    item = _item(merchant_id, modifier_version=1)
    unit = _ordering_unit(subject, merchant, item)
    line = BasketLine(
        item_id=item.item_id,
        quantity=2,
        observed_version=item.version,
        modifier_selections=("extra",),
        customer_instructions="Ring once",
    )
    order = OrderingApplication(_Composition(unit)).create(
        subject,
        merchant_id=merchant_id,
        lines=(line,),
        idempotency_key="order-create-0000001",
        at=NOW,
        area_reference="area:addis:v1",
        coverage_reference="coverage:addis:v1",
        merchant_open=True,
        correlation_id=uuid4(),
        request_id=uuid4(),
        access_interaction_id=uuid4(),
    )
    assert order.pricing.subtotal_minor == 5000
    assert order.availability_evaluation_id is not None
    assert order.lines[0].modifier_selections == ("extra",)

    unit.orders.reserve.return_value = (order.order_id, False)
    unit.orders.get.return_value = order
    replay = OrderingApplication(_Composition(unit)).create(
        subject,
        merchant_id=merchant_id,
        lines=(line,),
        idempotency_key="order-create-0000001",
        at=NOW,
    )
    assert replay == order


@pytest.mark.parametrize(
    ("merchant_state", "item_kwargs", "line_version", "modifiers", "message"),
    [
        (MerchantState.SUSPENDED, {}, 1, (), "merchant_unavailable"),
        (
            MerchantState.APPROVED,
            {
                "status": ItemStatus.ARCHIVED,
                "visibility": ItemVisibility.PRIVATE,
                "availability": ItemAvailability.HIDDEN,
            },
            1,
            (),
            "item_removed",
        ),
        (MerchantState.APPROVED, {}, 2, (), "catalogue_changed"),
        (
            MerchantState.APPROVED,
            {"availability": ItemAvailability.OUT_OF_STOCK},
            1,
            (),
            "item_out_of_stock",
        ),
        (
            MerchantState.APPROVED,
            {"availability": ItemAvailability.HIDDEN, "price": None},
            1,
            (),
            "item_unavailable",
        ),
        (MerchantState.APPROVED, {}, 1, ("extra",), "item_modifiers_not_approved"),
        (
            MerchantState.APPROVED,
            {"modifier_version": 1},
            1,
            ("unknown",),
            "item_modifier_not_approved",
        ),
    ],
)
def test_ordering_fails_closed_for_stale_or_unavailable_catalogue(
    merchant_state: MerchantState,
    item_kwargs: dict[str, Any],
    line_version: int,
    modifiers: tuple[str, ...],
    message: str,
) -> None:
    subject = _subject()
    merchant_id = uuid4()
    merchant = _merchant(merchant_id, state=merchant_state)
    item = _item(merchant_id, **item_kwargs)
    unit = _ordering_unit(subject, merchant, item)
    line = BasketLine(
        item_id=item.item_id,
        quantity=1,
        observed_version=line_version,
        modifier_selections=modifiers,
    )
    with pytest.raises(OrderingConflict, match=message):
        OrderingApplication(_Composition(unit)).create(
            subject,
            merchant_id=merchant_id,
            lines=(line,),
            idempotency_key=f"order-{message}-0001",
            at=NOW,
        )


def test_ordering_rejects_partial_or_unavailable_area_context() -> None:
    subject = _subject()
    merchant_id = uuid4()
    merchant = _merchant(merchant_id)
    item = _item(merchant_id)
    unit = _ordering_unit(subject, merchant, item)
    app = OrderingApplication(_Composition(unit))
    line = BasketLine(item_id=item.item_id, quantity=1, observed_version=1)

    with pytest.raises(OrderingConflict, match="availability_context_incomplete"):
        app.create(
            subject,
            merchant_id=merchant_id,
            lines=(line,),
            idempotency_key="order-partial-context",
            at=NOW,
            area_reference="area:addis:v1",
        )

    unit.eat_availability.find.return_value = None
    with pytest.raises(OrderingConflict, match="unknown_or_stale"):
        app.create(
            subject,
            merchant_id=merchant_id,
            lines=(line,),
            idempotency_key="order-unavailable-area",
            at=NOW,
            area_reference="area:addis:v1",
            coverage_reference="coverage:addis:v1",
            merchant_open=True,
            correlation_id=uuid4(),
            request_id=uuid4(),
        )


def test_ordering_read_models_enforce_customer_and_public_visibility() -> None:
    owner = _subject()
    other = _subject()
    merchant_id = uuid4()
    item = _item(merchant_id)
    unit = _ordering_unit(owner, _merchant(merchant_id), item)
    app = OrderingApplication(_Composition(unit))
    public_merchant = PublicMerchant(
        merchant_id=merchant_id,
        display_name="Addis Kitchen",
        capability_code="ayo.eat",
        market_code="ET-AA",
    )
    public_item = PublicCatalogueItem(
        item_id=item.item_id,
        merchant_id=merchant_id,
        category_id=None,
        kind="meal",
        name="Vegetable Tibs",
        description=None,
        media=(),
        availability="available",
        tags=(),
        base_price_minor=2500,
        currency="ETB",
        version=1,
    )
    order = MagicMock(spec=CanonicalOrder)
    order.customer_identity_id = owner.identity_id
    unit.orders.get.return_value = None
    with pytest.raises(OrderingConflict, match="order_not_found"):
        app.get(owner, uuid4())
    unit.orders.get.return_value = order
    with pytest.raises(OrderingConflict, match="access_denied"):
        app.get(other, uuid4())
    assert app.get(owner, uuid4()) is order

    unit.orders.public_merchants.return_value = (public_merchant,)
    assert app.merchants(query=None, limit=0) == (public_merchant,)
    unit.orders.public_merchant.return_value = None
    with pytest.raises(OrderingConflict, match="merchant_unavailable"):
        app.merchant(merchant_id)
    unit.orders.public_merchant.return_value = public_merchant
    unit.orders.public_categories.return_value = ("category",)
    unit.orders.public_items.return_value = (public_item,)
    assert app.categories(merchant_id, limit=500) == ("category",)
    assert app.items(
        merchant_id, query=None, category_id=None, tag=None, limit=500
    ) == (public_item,)
    unit.orders.public_item.return_value = None
    with pytest.raises(OrderingConflict, match="item_removed"):
        app.item(item.item_id)
    unit.orders.public_item.return_value = public_item
    assert app.item(item.item_id) == public_item
