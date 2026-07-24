from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.catalogue.engine import (
    CatalogueConflict,
    aggregate_quality,
    duplicate_item,
    normalize_search,
    quality,
)
from BACKEND.catalogue.models import (
    CatalogueCategory,
    CatalogueItem,
    CatalogueItemView,
    ItemAvailability,
    ItemKind,
    ItemStatus,
    ItemVisibility,
    MediaReference,
    MerchantCatalogueSummary,
)
from BACKEND.merchant.engine import verification_requirements


class UniversalCatalogueApplication:
    def __init__(self, composition: Any) -> None:
        self._composition = composition

    def create_category(
        self,
        subject: AuthorizationSubject,
        *,
        merchant_id: UUID,
        parent_category_id: UUID | None,
        name: str,
        description: str | None,
        sort_order: int,
        idempotency_key: str,
        at: datetime,
    ) -> CatalogueCategory:
        with self._composition.unit_of_work() as unit:
            self._owner(unit, subject, merchant_id, "catalogue.manage_own", at)
            if parent_category_id is not None:
                parent = unit.catalogue.get_category(parent_category_id)
                if parent is None or parent.merchant_id != merchant_id:
                    raise CatalogueConflict("catalogue_parent_category_not_found")
                if unit.catalogue.category_depth(parent_category_id) >= 4:
                    raise CatalogueConflict("catalogue_category_depth_exceeded")
            candidate = uuid4()
            category_id, _ = unit.catalogue.reserve(
                actor_id=subject.identity_id,
                operation="catalogue.category.create",
                key=idempotency_key,
                payload={
                    "merchant_id": str(merchant_id),
                    "parent_category_id": str(parent_category_id)
                    if parent_category_id
                    else None,
                    "name": name,
                    "description": description,
                    "sort_order": sort_order,
                },
                candidate=candidate,
                at=at,
            )
            existing = unit.catalogue.get_category(category_id)
            if existing is not None:
                return existing
            return unit.catalogue.create_category(
                CatalogueCategory(
                    category_id=category_id,
                    merchant_id=merchant_id,
                    parent_category_id=parent_category_id,
                    name=name,
                    description=description,
                    normalized_name=normalize_search(name),
                    sort_order=sort_order,
                    created_at=at,
                    updated_at=at,
                )
            )

    def create_item(
        self,
        subject: AuthorizationSubject,
        *,
        merchant_id: UUID,
        category_id: UUID | None,
        branch_id: UUID | None,
        kind: ItemKind,
        name: str,
        description: str | None,
        media: tuple[MediaReference, ...],
        availability: ItemAvailability,
        visibility: ItemVisibility,
        tags: tuple[str, ...],
        search_keywords: tuple[str, ...],
        base_price_minor: int | None,
        idempotency_key: str,
        at: datetime,
    ) -> CatalogueItemView:
        with self._composition.unit_of_work() as unit:
            self._owner(unit, subject, merchant_id, "catalogue.manage_own", at)
            self._scope(unit, merchant_id, category_id, branch_id)
            candidate = uuid4()
            item_id, _ = unit.catalogue.reserve(
                actor_id=subject.identity_id,
                operation="catalogue.item.create",
                key=idempotency_key,
                payload={
                    "merchant_id": str(merchant_id),
                    "category_id": str(category_id) if category_id else None,
                    "branch_id": str(branch_id) if branch_id else None,
                    "kind": kind.value,
                    "name": name,
                    "description": description,
                    "media": [m.model_dump(mode="json") for m in media],
                    "availability": availability.value,
                    "visibility": visibility.value,
                    "tags": tags,
                    "search_keywords": search_keywords,
                    "base_price_minor": base_price_minor,
                },
                candidate=candidate,
                at=at,
            )
            existing = unit.catalogue.get_item(item_id)
            if existing is not None:
                return CatalogueItemView(item=existing, quality=quality(existing))
            item = CatalogueItem(
                item_id=item_id,
                merchant_id=merchant_id,
                category_id=category_id,
                branch_id=branch_id,
                kind=kind,
                name=name,
                description=description,
                media=media,
                status=ItemStatus.DRAFT,
                availability=availability,
                visibility=visibility,
                tags=tags,
                search_keywords=search_keywords,
                base_price_minor=base_price_minor,
                created_at=at,
                updated_at=at,
            )
            created = unit.catalogue.create_item(item)
            return CatalogueItemView(item=created, quality=quality(created))

    def edit_item(
        self,
        subject: AuthorizationSubject,
        *,
        item_id: UUID,
        expected_version: int,
        kind: ItemKind,
        name: str,
        description: str | None,
        category_id: UUID | None,
        branch_id: UUID | None,
        media: tuple[MediaReference, ...],
        status: ItemStatus,
        availability: ItemAvailability,
        visibility: ItemVisibility,
        tags: tuple[str, ...],
        search_keywords: tuple[str, ...],
        base_price_minor: int | None,
        idempotency_key: str,
        at: datetime,
    ) -> CatalogueItemView:
        with self._composition.unit_of_work() as unit:
            current = self._owned_item(unit, subject, item_id, at)
            canonical, created = unit.catalogue.reserve(
                actor_id=subject.identity_id,
                operation=f"catalogue.item.edit.{item_id}",
                key=idempotency_key,
                payload={
                    "expected_version": expected_version,
                    "kind": kind.value,
                    "name": name,
                    "description": description,
                    "category_id": str(category_id) if category_id else None,
                    "branch_id": str(branch_id) if branch_id else None,
                    "media": [m.model_dump(mode="json") for m in media],
                    "status": status.value,
                    "availability": availability.value,
                    "visibility": visibility.value,
                    "tags": tags,
                    "search_keywords": search_keywords,
                    "base_price_minor": base_price_minor,
                },
                candidate=item_id,
                at=at,
            )
            if canonical != item_id:
                raise CatalogueConflict("catalogue_item_not_found")
            if not created:
                return CatalogueItemView(item=current, quality=quality(current))
            self._scope(unit, current.merchant_id, category_id, branch_id)
            if status is ItemStatus.ARCHIVED and (
                availability is not ItemAvailability.HIDDEN
                or visibility is not ItemVisibility.PRIVATE
            ):
                raise CatalogueConflict("catalogue_archived_item_must_be_hidden")
            updated = CatalogueItem.model_validate(
                {
                    **current.model_dump(),
                    "kind": kind,
                    "name": name,
                    "description": description,
                    "category_id": category_id,
                    "branch_id": branch_id,
                    "media": media,
                    "status": status,
                    "availability": availability,
                    "visibility": visibility,
                    "tags": tags,
                    "search_keywords": search_keywords,
                    "base_price_minor": base_price_minor,
                    "version": expected_version + 1,
                    "updated_at": at,
                }
            )
            result = unit.catalogue.update_item(
                updated,
                expected_version=expected_version,
                event_type="catalogue.item.edited",
            )
            return CatalogueItemView(item=result, quality=quality(result))

    def archive(
        self,
        subject: AuthorizationSubject,
        *,
        item_id: UUID,
        expected_version: int,
        idempotency_key: str,
        at: datetime,
    ) -> CatalogueItemView:
        return self._lifecycle(
            subject,
            item_id=item_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            at=at,
            restore=False,
        )

    def restore(
        self,
        subject: AuthorizationSubject,
        *,
        item_id: UUID,
        expected_version: int,
        idempotency_key: str,
        at: datetime,
    ) -> CatalogueItemView:
        return self._lifecycle(
            subject,
            item_id=item_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            at=at,
            restore=True,
        )

    def duplicate(
        self,
        subject: AuthorizationSubject,
        *,
        item_id: UUID,
        idempotency_key: str,
        at: datetime,
    ) -> CatalogueItemView:
        with self._composition.unit_of_work() as unit:
            current = self._owned_item(unit, subject, item_id, at)
            candidate = uuid4()
            duplicate_id, _ = unit.catalogue.reserve(
                actor_id=subject.identity_id,
                operation=f"catalogue.item.duplicate.{item_id}",
                key=idempotency_key,
                payload={"item_id": str(item_id), "source_version": current.version},
                candidate=candidate,
                at=at,
            )
            existing = unit.catalogue.get_item(duplicate_id)
            if existing is not None:
                return CatalogueItemView(item=existing, quality=quality(existing))
            value = CatalogueItem.model_validate(
                {**duplicate_item(current, at=at).model_dump(), "item_id": duplicate_id}
            )
            result = unit.catalogue.create_item(
                value, event_type="catalogue.item.duplicated"
            )
            return CatalogueItemView(item=result, quality=quality(result))

    def search(
        self,
        subject: AuthorizationSubject,
        *,
        merchant_id: UUID,
        query: str | None,
        category_id: UUID | None,
        tag: str | None,
        limit: int,
        at: datetime,
    ) -> tuple[CatalogueItemView, ...]:
        with self._composition.unit_of_work() as unit:
            self._owner(unit, subject, merchant_id, "catalogue.read_own", at)
            normalized_query = normalize_search(query) if query else None
            normalized_tag = normalize_search(tag) if tag else None
            return tuple(
                CatalogueItemView(item=item, quality=quality(item))
                for item in unit.catalogue.search_items(
                    merchant_id,
                    query=normalized_query,
                    category_id=category_id,
                    tag=normalized_tag,
                    limit=min(max(limit, 1), 100),
                )
            )

    def categories(
        self,
        subject: AuthorizationSubject,
        *,
        merchant_id: UUID,
        query: str | None,
        limit: int,
        at: datetime,
    ) -> tuple[CatalogueCategory, ...]:
        with self._composition.unit_of_work() as unit:
            self._owner(unit, subject, merchant_id, "catalogue.read_own", at)
            return unit.catalogue.list_categories(
                merchant_id,
                query=normalize_search(query) if query else None,
                limit=min(max(limit, 1), 100),
            )

    def summary(
        self, subject: AuthorizationSubject, *, merchant_id: UUID, at: datetime
    ) -> MerchantCatalogueSummary:
        with self._composition.unit_of_work() as unit:
            merchant = self._owner(unit, subject, merchant_id, "catalogue.read_own", at)
            items = unit.catalogue.list_all_for_quality(merchant_id)
            completion, media, missing = aggregate_quality(items)
            evidence = unit.merchants.verifications(merchant_id)
            required = verification_requirements(merchant.capability_code)
            approved = sum(
                any(e.kind is kind and e.state.value == "approved" for e in evidence)
                for kind in required
            )
            verification = 100 if not required else approved * 100 // len(required)
            business = 100 if merchant.legal_name and merchant.display_name else 0
            branches = unit.merchants.branch_count(merchant_id)
            hours = unit.merchants.operating_hours_count(merchant_id)
            operating = 0 if branches == 0 else min(100, hours * 100 // branches)
            active = sum(item.status is ItemStatus.ACTIVE for item in items)
            readiness = (
                verification * 25
                + business * 15
                + operating * 15
                + completion * 30
                + media * 15
            ) // 100
            return MerchantCatalogueSummary(
                merchant_id=merchant_id,
                item_count=len(items),
                active_count=active,
                completion_score=completion,
                media_quality_score=media,
                readiness_score=readiness,
                missing_information=missing,
                business_profile_score=business,
                verification_score=verification,
                operating_hours_score=operating,
            )

    def _lifecycle(
        self,
        subject: AuthorizationSubject,
        *,
        item_id: UUID,
        expected_version: int,
        idempotency_key: str,
        at: datetime,
        restore: bool,
    ) -> CatalogueItemView:
        with self._composition.unit_of_work() as unit:
            current = self._owned_item(unit, subject, item_id, at)
            operation = "restore" if restore else "archive"
            _, created = unit.catalogue.reserve(
                actor_id=subject.identity_id,
                operation=f"catalogue.item.{operation}.{item_id}",
                key=idempotency_key,
                payload={"expected_version": expected_version},
                candidate=item_id,
                at=at,
            )
            if not created:
                return CatalogueItemView(item=current, quality=quality(current))
            target = ItemStatus.DRAFT if restore else ItemStatus.ARCHIVED
            if current.status is target and current.version >= expected_version:
                return CatalogueItemView(item=current, quality=quality(current))
            if restore and current.status is not ItemStatus.ARCHIVED:
                raise CatalogueConflict("catalogue_item_not_archived")
            updated = CatalogueItem.model_validate(
                {
                    **current.model_dump(),
                    "status": target,
                    "availability": ItemAvailability.HIDDEN,
                    "visibility": ItemVisibility.PRIVATE,
                    "version": expected_version + 1,
                    "updated_at": at,
                }
            )
            result = unit.catalogue.update_item(
                updated,
                expected_version=expected_version,
                event_type=f"catalogue.item.{operation}d",
            )
            return CatalogueItemView(item=result, quality=quality(result))

    @staticmethod
    def _owner(
        unit: Any,
        subject: AuthorizationSubject,
        merchant_id: UUID,
        permission: str,
        at: datetime,
    ):
        merchant = unit.merchants.get_profile(merchant_id)
        if merchant is None or merchant.owner_identity_id != subject.identity_id:
            raise CatalogueConflict("merchant_not_found")
        if not unit.authorization.has_permission(
            subject.identity_id, permission, at=at
        ):
            raise CatalogueConflict("access_denied")
        return merchant

    def _owned_item(
        self, unit: Any, subject: AuthorizationSubject, item_id: UUID, at: datetime
    ) -> CatalogueItem:
        item = unit.catalogue.get_item(item_id, lock=True)
        if item is None:
            raise CatalogueConflict("catalogue_item_not_found")
        self._owner(unit, subject, item.merchant_id, "catalogue.manage_own", at)
        return item

    @staticmethod
    def _scope(
        unit: Any, merchant_id: UUID, category_id: UUID | None, branch_id: UUID | None
    ) -> None:
        if category_id is not None:
            category = unit.catalogue.get_category(category_id)
            if category is None or category.merchant_id != merchant_id:
                raise CatalogueConflict("catalogue_category_not_found")
        if (
            branch_id is not None
            and unit.merchants.get_branch_merchant(branch_id) != merchant_id
        ):
            raise CatalogueConflict("merchant_branch_not_found")
