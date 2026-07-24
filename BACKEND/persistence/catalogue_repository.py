import hashlib
import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, String, func, insert, or_, select, update
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.catalogue.engine import CatalogueConflict
from BACKEND.catalogue.models import CatalogueCategory, CatalogueItem
from BACKEND.persistence.tables import (
    catalogue_categories,
    catalogue_idempotency,
    catalogue_outbox,
    universal_catalogue_items,
)


def _item(row: Any) -> CatalogueItem:
    return CatalogueItem.model_validate(dict(row))


def _category(row: Any) -> CatalogueCategory:
    return CatalogueCategory.model_validate(dict(row))


class PostgresCatalogueRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def reserve(
        self,
        *,
        actor_id: UUID,
        operation: str,
        key: str,
        payload: dict[str, Any],
        candidate: UUID,
        at: datetime,
    ) -> tuple[UUID, bool]:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        found = self._connection.execute(
            pg_insert(catalogue_idempotency)
            .values(
                actor_identity_id=actor_id,
                operation=operation,
                idempotency_key=key,
                request_hash=digest,
                response_reference=candidate,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(catalogue_idempotency.c.response_reference)
        ).scalar_one_or_none()
        if found is not None:
            return cast(UUID, found), True
        row = (
            self._connection.execute(
                select(catalogue_idempotency).where(
                    catalogue_idempotency.c.actor_identity_id == actor_id,
                    catalogue_idempotency.c.operation == operation,
                    catalogue_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if row["request_hash"] != digest:
            raise CatalogueConflict("idempotency_conflict")
        return cast(UUID, row["response_reference"]), False

    def create_category(self, value: CatalogueCategory) -> CatalogueCategory:
        existing = self.get_category(value.category_id)
        if existing is not None:
            return existing
        self._connection.execute(
            insert(catalogue_categories).values(**value.model_dump(mode="json"))
        )
        return value

    def get_category(
        self, category_id: UUID, *, lock: bool = False
    ) -> CatalogueCategory | None:
        query = select(catalogue_categories).where(
            catalogue_categories.c.category_id == category_id
        )
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else _category(row)

    def category_depth(self, category_id: UUID) -> int:
        depth = 0
        current = self.get_category(category_id)
        seen: set[UUID] = set()
        while current is not None:
            if current.category_id in seen:
                raise CatalogueConflict("catalogue_category_cycle")
            seen.add(current.category_id)
            depth += 1
            current = (
                self.get_category(current.parent_category_id)
                if current.parent_category_id
                else None
            )
            if depth > 8:
                raise CatalogueConflict("catalogue_category_depth_exceeded")
        return depth

    def list_categories(
        self, merchant_id: UUID, *, query: str | None, limit: int
    ) -> tuple[CatalogueCategory, ...]:
        statement = select(catalogue_categories).where(
            catalogue_categories.c.merchant_id == merchant_id
        )
        if query:
            statement = statement.where(
                catalogue_categories.c.normalized_name.ilike(f"%{query}%")
            )
        rows = self._connection.execute(
            statement.order_by(
                catalogue_categories.c.sort_order,
                catalogue_categories.c.normalized_name,
            ).limit(limit)
        ).mappings()
        return tuple(_category(row) for row in rows)

    def create_item(
        self, value: CatalogueItem, *, event_type: str = "catalogue.item.created"
    ) -> CatalogueItem:
        existing = self.get_item(value.item_id)
        if existing is not None:
            return existing
        self._connection.execute(
            insert(universal_catalogue_items).values(**value.model_dump(mode="json"))
        )
        self.event(
            value.merchant_id,
            value.item_id,
            event_type,
            {"item_id": str(value.item_id), "status": value.status.value},
            value.created_at,
        )
        return value

    def get_item(self, item_id: UUID, *, lock: bool = False) -> CatalogueItem | None:
        query = select(universal_catalogue_items).where(
            universal_catalogue_items.c.item_id == item_id
        )
        if lock:
            query = query.with_for_update()
        row = self._connection.execute(query).mappings().one_or_none()
        return None if row is None else _item(row)

    def update_item(
        self, value: CatalogueItem, *, expected_version: int, event_type: str
    ) -> CatalogueItem:
        payload = value.model_dump(
            mode="json", exclude={"item_id", "merchant_id", "created_at"}
        )
        row = (
            self._connection.execute(
                update(universal_catalogue_items)
                .where(
                    universal_catalogue_items.c.item_id == value.item_id,
                    universal_catalogue_items.c.merchant_id == value.merchant_id,
                    universal_catalogue_items.c.version == expected_version,
                )
                .values(**payload)
                .returning(universal_catalogue_items)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise CatalogueConflict("catalogue_item_version_conflict")
        result = _item(row)
        self.event(
            result.merchant_id,
            result.item_id,
            event_type,
            {
                "item_id": str(result.item_id),
                "status": result.status.value,
                "version": result.version,
            },
            result.updated_at,
        )
        return result

    def search_items(
        self,
        merchant_id: UUID,
        *,
        query: str | None,
        category_id: UUID | None,
        tag: str | None,
        limit: int,
    ) -> tuple[CatalogueItem, ...]:
        statement = select(universal_catalogue_items).where(
            universal_catalogue_items.c.merchant_id == merchant_id
        )
        if category_id is not None:
            statement = statement.where(
                universal_catalogue_items.c.category_id == category_id
            )
        if query:
            pattern = f"%{query}%"
            statement = statement.where(
                or_(
                    func.lower(universal_catalogue_items.c.name).like(pattern),
                    sql_cast(universal_catalogue_items.c.search_keywords, String).ilike(
                        pattern
                    ),
                )
            )
        if tag:
            statement = statement.where(
                sql_cast(universal_catalogue_items.c.tags, String).ilike(f'%"{tag}"%')
            )
        rows = self._connection.execute(
            statement.order_by(
                universal_catalogue_items.c.updated_at.desc(),
                universal_catalogue_items.c.item_id,
            ).limit(limit)
        ).mappings()
        return tuple(_item(row) for row in rows)

    def list_all_for_quality(
        self, merchant_id: UUID, *, limit: int = 500
    ) -> tuple[CatalogueItem, ...]:
        rows = self._connection.execute(
            select(universal_catalogue_items)
            .where(universal_catalogue_items.c.merchant_id == merchant_id)
            .order_by(universal_catalogue_items.c.item_id)
            .limit(limit)
        ).mappings()
        return tuple(_item(row) for row in rows)

    def event(
        self,
        merchant_id: UUID,
        item_id: UUID | None,
        event_type: str,
        payload: dict[str, Any],
        at: datetime,
    ) -> None:
        self._connection.execute(
            insert(catalogue_outbox).values(
                message_id=uuid4(),
                merchant_id=merchant_id,
                item_id=item_id,
                event_type=event_type,
                safe_payload=payload,
                occurred_at=at,
                attempt_count=0,
            )
        )
