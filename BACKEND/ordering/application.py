from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.catalogue.models import ItemAvailability, ItemStatus, ItemVisibility
from BACKEND.eat_availability.engine import availability_outcome, canonical_hash
from BACKEND.eat_availability.models import (
    EatAvailabilityEvaluation,
    EatAvailabilityOutcome,
)
from BACKEND.merchant.models import MerchantState
from BACKEND.ordering.engine import (
    CatalogueSubtotalPricingAuthority,
    OrderingConflict,
    evidence_hash,
    normalize_basket,
)
from BACKEND.ordering.models import BasketLine, CanonicalOrder


class OrderingApplication:
    def __init__(
        self, composition: Any, pricing: CatalogueSubtotalPricingAuthority | None = None
    ) -> None:
        self._composition = composition
        self._pricing = pricing or CatalogueSubtotalPricingAuthority()

    def create(
        self,
        subject: AuthorizationSubject,
        *,
        merchant_id: UUID,
        lines: tuple[BasketLine, ...],
        idempotency_key: str,
        at: datetime,
        area_reference: str | None = None,
        coverage_reference: str | None = None,
        merchant_open: bool | None = None,
        correlation_id: UUID | None = None,
        request_id: UUID | None = None,
        access_interaction_id: UUID | None = None,
    ) -> CanonicalOrder:
        basket = normalize_basket(lines)
        request = {
            "merchant_id": str(merchant_id),
            "lines": [line.model_dump(mode="json") for line in basket],
            "area_reference": area_reference,
            "coverage_reference": coverage_reference,
            "merchant_open": merchant_open,
            "access_interaction_id": (
                None if access_interaction_id is None else str(access_interaction_id)
            ),
        }
        with self._composition.unit_of_work() as unit:
            order_id, created = unit.orders.reserve(
                customer_id=subject.identity_id,
                key=idempotency_key,
                payload=request,
                candidate=uuid4(),
                at=at,
            )
            existing = unit.orders.get(order_id)
            if not created and existing is not None:
                return existing
            merchant = unit.merchants.get_profile(merchant_id, lock=True)
            if merchant is None or merchant.state is not MerchantState.APPROVED:
                raise OrderingConflict("merchant_unavailable")
            priced = []
            for line in basket:
                item = unit.catalogue.get_item(line.item_id, lock=True)
                if (
                    item is None
                    or item.merchant_id != merchant_id
                    or item.status is not ItemStatus.ACTIVE
                    or item.visibility is not ItemVisibility.PUBLIC
                ):
                    raise OrderingConflict("item_removed")
                if item.version != line.observed_version:
                    raise OrderingConflict("catalogue_changed")
                if item.availability is ItemAvailability.OUT_OF_STOCK:
                    raise OrderingConflict("item_out_of_stock")
                if (
                    item.availability is not ItemAvailability.AVAILABLE
                    or item.base_price_minor is None
                ):
                    raise OrderingConflict("item_unavailable")
                if line.modifier_selections:
                    if item.modifier_contract_version is None:
                        raise OrderingConflict("item_modifiers_not_approved")
                    approved = unit.orders.approved_modifier_codes(
                        item_id=item.item_id,
                        contract_version=item.modifier_contract_version,
                    )
                    if not set(line.modifier_selections) <= approved:
                        raise OrderingConflict("item_modifier_not_approved")
                priced.append((item, line.quantity))
            base_evidence, pricing = self._pricing.price(tuple(priced))
            line_evidence = tuple(
                evidence.model_copy(
                    update={
                        "modifier_selections": source.modifier_selections,
                        "customer_instructions": source.customer_instructions,
                    }
                )
                for evidence, source in zip(base_evidence, basket, strict=True)
            )
            availability_evaluation_id = None
            if any(
                value is not None
                for value in (
                    area_reference,
                    coverage_reference,
                    merchant_open,
                    correlation_id,
                    request_id,
                )
            ):
                if (
                    area_reference is None
                    or coverage_reference is None
                    or merchant_open is None
                    or correlation_id is None
                    or request_id is None
                ):
                    raise OrderingConflict("availability_context_incomplete")
                policy = unit.eat_availability.find(
                    merchant_id=merchant_id, area_reference=area_reference
                )
                coverage_matches = (
                    policy is not None
                    and policy.coverage_reference == coverage_reference
                )
                outcome, reason = availability_outcome(
                    policy if coverage_matches else None,
                    merchant_open=merchant_open,
                    items_available=True,
                    at=at,
                )
                evaluation_payload = {
                    "policy_id": None if policy is None else str(policy.policy_id),
                    "policy_version": None if policy is None else policy.version,
                    "merchant_id": str(merchant_id),
                    "merchant_version": merchant.version,
                    "area_reference": area_reference,
                    "coverage_reference": coverage_reference,
                    "item_ids": sorted(str(line.item_id) for line in basket),
                    "merchant_open": merchant_open,
                    "outcome": outcome.value,
                    "reason_code": reason,
                    "evaluated_at": at.isoformat(),
                }
                evaluation = unit.eat_availability.record_evaluation(
                    EatAvailabilityEvaluation(
                        policy_id=None if policy is None else policy.policy_id,
                        policy_version=None if policy is None else policy.version,
                        merchant_id=merchant_id,
                        area_reference=area_reference,
                        coverage_reference=coverage_reference,
                        item_references=tuple(line.item_id for line in basket),
                        merchant_open=merchant_open,
                        outcome=outcome,
                        reason_code=reason,
                        evaluated_at=at,
                        evidence_hash=canonical_hash(evaluation_payload),
                        correlation_id=correlation_id,
                        request_id=request_id,
                    )
                )
                if outcome is not EatAvailabilityOutcome.AVAILABLE:
                    raise OrderingConflict(outcome.value)
                availability_evaluation_id = evaluation.evaluation_id
            composition_payload = {
                "merchant_id": str(merchant_id),
                "merchant_version": merchant.version,
                "lines": [
                    {
                        "item_id": str(line.item_id),
                        "observed_version": line.observed_version,
                        "quantity": line.quantity,
                        "modifier_selections": line.modifier_selections,
                        "customer_instructions": line.customer_instructions,
                    }
                    for line in basket
                ],
                "availability_evaluation_id": (
                    None
                    if availability_evaluation_id is None
                    else str(availability_evaluation_id)
                ),
                "access_interaction_id": (
                    None
                    if access_interaction_id is None
                    else str(access_interaction_id)
                ),
            }
            composition_digest = canonical_hash(composition_payload)
            immutable = {
                "order_id": str(order_id),
                "customer_identity_id": str(subject.identity_id),
                "merchant_id": str(merchant_id),
                "merchant_version": merchant.version,
                "lines": [line.model_dump(mode="json") for line in line_evidence],
                "pricing": pricing.model_dump(mode="json"),
                "composition": composition_payload,
                "composition_hash": composition_digest,
                "created_at": at.isoformat(),
            }
            order = CanonicalOrder(
                order_id=order_id,
                customer_identity_id=subject.identity_id,
                merchant_id=merchant_id,
                merchant_display_name=merchant.display_name,
                lines=line_evidence,
                pricing=pricing,
                availability_evaluation_id=availability_evaluation_id,
                composition_hash=composition_digest,
                access_interaction_id=access_interaction_id,
                evidence_hash=evidence_hash(immutable),
                created_at=at,
            )
            return unit.orders.create(
                order, merchant_version=merchant.version, request=request
            )

    def get(self, subject: AuthorizationSubject, order_id: UUID) -> CanonicalOrder:
        with self._composition.unit_of_work() as unit:
            order = unit.orders.get(order_id)
            if order is None:
                raise OrderingConflict("order_not_found")
            if order.customer_identity_id != subject.identity_id:
                raise OrderingConflict("access_denied")
            return order

    def merchants(self, *, query: str | None, limit: int):
        with self._composition.unit_of_work() as unit:
            return unit.orders.public_merchants(
                query=query, limit=min(max(limit, 1), 50)
            )

    def merchant(self, merchant_id: UUID):
        with self._composition.unit_of_work() as unit:
            value = unit.orders.public_merchant(merchant_id)
            if value is None:
                raise OrderingConflict("merchant_unavailable")
            return value

    def categories(self, merchant_id: UUID, *, limit: int):
        self.merchant(merchant_id)
        with self._composition.unit_of_work() as unit:
            return unit.orders.public_categories(
                merchant_id, limit=min(max(limit, 1), 100)
            )

    def items(
        self,
        merchant_id: UUID,
        *,
        query: str | None,
        category_id: UUID | None,
        tag: str | None,
        limit: int,
    ):
        self.merchant(merchant_id)
        with self._composition.unit_of_work() as unit:
            return unit.orders.public_items(
                merchant_id,
                query=query,
                category_id=category_id,
                tag=tag,
                limit=min(max(limit, 1), 100),
            )

    def item(self, item_id: UUID):
        with self._composition.unit_of_work() as unit:
            value = unit.orders.public_item(item_id)
            if value is None or unit.orders.public_merchant(value.merchant_id) is None:
                raise OrderingConflict("item_removed")
            return value
