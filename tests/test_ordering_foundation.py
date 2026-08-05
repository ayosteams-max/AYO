from datetime import UTC, datetime
from uuid import uuid4

import pytest

from BACKEND.catalogue.models import (
    CatalogueItem,
    ItemAvailability,
    ItemKind,
    ItemStatus,
    ItemVisibility,
)
from BACKEND.ordering.engine import (
    CatalogueSubtotalPricingAuthority,
    OrderingConflict,
    evidence_hash,
    normalize_basket,
)
from BACKEND.ordering.models import BasketLine


def line(item_id=None, *, quantity=1, version=1):
    return BasketLine(
        item_id=item_id or uuid4(), quantity=quantity, observed_version=version
    )


def item(*, price=1250, version=3):
    now = datetime.now(UTC)
    return CatalogueItem(
        merchant_id=uuid4(),
        kind=ItemKind.PRODUCT,
        name="Ground coffee",
        status=ItemStatus.ACTIVE,
        availability=ItemAvailability.AVAILABLE,
        visibility=ItemVisibility.PUBLIC,
        base_price_minor=price,
        version=version,
        created_at=now,
        updated_at=now,
    )


def test_basket_rejects_duplicate_items():
    item_id = uuid4()
    with pytest.raises(OrderingConflict, match="basket_duplicate_item"):
        normalize_basket((line(item_id), line(item_id, quantity=2)))


def test_basket_preserves_normalized_composition_intent():
    value = BasketLine(
        item_id=uuid4(),
        quantity=1,
        observed_version=1,
        modifier_selections=(" Extra.Milk ", "no_sugar"),
        customer_instructions="  Please pack securely.  ",
    )
    normalized = normalize_basket((value,))
    assert normalized[0].modifier_selections == ("extra.milk", "no_sugar")
    assert normalized[0].customer_instructions == "Please pack securely."


def test_basket_rejects_variants_until_catalogue_approves_them():
    value = BasketLine(
        item_id=uuid4(),
        quantity=1,
        observed_version=1,
        variant_selections=("large",),
    )
    with pytest.raises(OrderingConflict, match="item_variants_not_supported"):
        normalize_basket((value,))


def test_pricing_authority_uses_integer_catalogue_evidence():
    first, second = item(price=1250), item(price=300)
    lines, pricing = CatalogueSubtotalPricingAuthority().price(
        ((first, 2), (second, 3))
    )
    assert pricing.subtotal_minor == 3400
    assert [value.line_total_minor for value in lines] == [2500, 900]
    assert pricing.currency == "ETB"
    assert len(pricing.evidence_hash) == 64


def test_evidence_hash_is_canonical():
    assert evidence_hash({"b": 2, "a": 1}) == evidence_hash({"a": 1, "b": 2})
