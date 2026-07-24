import hashlib
import json

from BACKEND.catalogue.models import CatalogueItem
from BACKEND.ordering.models import OrderLineEvidence, OrderPricingEvidence


class OrderingConflict(Exception):
    pass


def normalize_basket(lines):
    if not lines or len(lines) > 50:
        raise OrderingConflict("basket_invalid")
    seen = set()
    for line in lines:
        if line.item_id in seen:
            raise OrderingConflict("basket_duplicate_item")
        seen.add(line.item_id)
        if line.variant_selections:
            raise OrderingConflict("item_variants_not_supported")
    return tuple(lines)


class CatalogueSubtotalPricingAuthority:
    policy_version = "commerce.catalogue_subtotal.v1"

    def price(
        self, lines: tuple[tuple[CatalogueItem, int], ...]
    ) -> tuple[tuple[OrderLineEvidence, ...], OrderPricingEvidence]:
        evidence = tuple(
            OrderLineEvidence(
                item_id=item.item_id,
                item_version=item.version,
                name=item.name,
                kind=item.kind.value,
                category_id=item.category_id,
                quantity=quantity,
                unit_price_minor=item.base_price_minor or 0,
                line_total_minor=(item.base_price_minor or 0) * quantity,
                currency=item.currency,
            )
            for item, quantity in lines
        )
        subtotal = sum(line.line_total_minor for line in evidence)
        payload = {
            "policy_version": self.policy_version,
            "subtotal_minor": subtotal,
            "currency": "ETB",
            "lines": [line.model_dump(mode="json") for line in evidence],
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return evidence, OrderPricingEvidence(
            policy_version=self.policy_version,
            subtotal_minor=subtotal,
            currency="ETB",
            evidence_hash=digest,
        )


def evidence_hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
