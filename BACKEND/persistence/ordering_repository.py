import hashlib
import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, String, func, insert, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import insert as pg_insert

from BACKEND.ordering.engine import OrderingConflict
from BACKEND.ordering.models import (
    CanonicalOrder,
    OrderLineEvidence,
    PublicCatalogueItem,
    PublicCategory,
    PublicMerchant,
)
from BACKEND.persistence.tables import (
    catalogue_categories,
    catalogue_modifier_options,
    commerce_order_evidence,
    commerce_order_idempotency,
    commerce_order_lines,
    commerce_order_outbox,
    commerce_order_timeline,
    commerce_orders,
    merchant_profiles,
    universal_catalogue_items,
)


class PostgresOrderingRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def reserve(
        self,
        *,
        customer_id: UUID,
        key: str,
        payload: dict[str, Any],
        candidate: UUID,
        at: datetime,
    ) -> tuple[UUID, bool]:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        found = self._connection.execute(
            pg_insert(commerce_order_idempotency)
            .values(
                customer_identity_id=customer_id,
                idempotency_key=key,
                request_hash=digest,
                order_id=candidate,
                created_at=at,
            )
            .on_conflict_do_nothing()
            .returning(commerce_order_idempotency.c.order_id)
        ).scalar_one_or_none()
        if found is not None:
            return cast(UUID, found), True
        row = (
            self._connection.execute(
                select(commerce_order_idempotency).where(
                    commerce_order_idempotency.c.customer_identity_id == customer_id,
                    commerce_order_idempotency.c.idempotency_key == key,
                )
            )
            .mappings()
            .one()
        )
        if row["request_hash"] != digest:
            raise OrderingConflict("idempotency_conflict")
        return cast(UUID, row["order_id"]), False

    def create(
        self, value: CanonicalOrder, *, merchant_version: int, request: dict[str, Any]
    ) -> CanonicalOrder:
        self._connection.execute(
            insert(commerce_orders).values(
                order_id=value.order_id,
                customer_identity_id=value.customer_identity_id,
                merchant_id=value.merchant_id,
                merchant_display_name=value.merchant_display_name,
                merchant_version=merchant_version,
                state=value.state.value,
                version=value.version,
                pricing_evidence=value.pricing.model_dump(mode="json"),
                availability_evaluation_id=value.availability_evaluation_id,
                composition_hash=value.composition_hash,
                access_interaction_id=value.access_interaction_id,
                evidence_hash=value.evidence_hash,
                created_at=value.created_at,
            )
        )
        for number, line in enumerate(value.lines, 1):
            line_values = line.model_dump(mode="json")
            self._connection.execute(
                insert(commerce_order_lines).values(
                    order_id=value.order_id,
                    line_number=number,
                    **line_values,
                )
            )
        immutable = {
            "order": value.model_dump(mode="json"),
            "request": request,
            "merchant_version": merchant_version,
        }
        self._connection.execute(
            insert(commerce_order_evidence).values(
                order_id=value.order_id,
                immutable_payload=immutable,
                evidence_hash=value.evidence_hash,
                recorded_at=value.created_at,
            )
        )
        self._connection.execute(
            insert(commerce_order_timeline).values(
                event_id=uuid4(),
                order_id=value.order_id,
                merchant_id=value.merchant_id,
                event_type="commerce.order.created",
                from_state=None,
                to_state=value.state.value,
                actor_identity_id=value.customer_identity_id,
                order_version=value.version,
                customer_reason_code=None,
                occurred_at=value.created_at,
            )
        )
        self._connection.execute(
            insert(commerce_order_outbox).values(
                message_id=uuid4(),
                order_id=value.order_id,
                event_type="commerce.order.created",
                safe_payload={
                    "order_id": str(value.order_id),
                    "state": value.state.value,
                },
                occurred_at=value.created_at,
                attempt_count=0,
            )
        )
        return value

    def get(self, order_id: UUID) -> CanonicalOrder | None:
        row = (
            self._connection.execute(
                select(commerce_orders).where(commerce_orders.c.order_id == order_id)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        line_rows = self._connection.execute(
            select(commerce_order_lines)
            .where(commerce_order_lines.c.order_id == order_id)
            .order_by(commerce_order_lines.c.line_number)
        ).mappings()
        return CanonicalOrder(
            order_id=row["order_id"],
            customer_identity_id=row["customer_identity_id"],
            merchant_id=row["merchant_id"],
            merchant_display_name=row["merchant_display_name"],
            state=row["state"],
            version=row["version"],
            lines=tuple(
                OrderLineEvidence.model_validate(
                    {
                        k: v
                        for k, v in line.items()
                        if k not in {"order_id", "line_number"}
                    }
                )
                for line in line_rows
            ),
            pricing=row["pricing_evidence"],
            availability_evaluation_id=row["availability_evaluation_id"],
            composition_hash=row["composition_hash"],
            access_interaction_id=row["access_interaction_id"],
            evidence_hash=row["evidence_hash"],
            created_at=row["created_at"],
        )

    def approved_modifier_codes(
        self, *, item_id: UUID, contract_version: int
    ) -> frozenset[str]:
        values = self._connection.execute(
            select(catalogue_modifier_options.c.code).where(
                catalogue_modifier_options.c.item_id == item_id,
                catalogue_modifier_options.c.contract_version == contract_version,
                catalogue_modifier_options.c.active.is_(True),
            )
        ).scalars()
        return frozenset(values)

    def public_merchants(
        self, *, query: str | None, limit: int
    ) -> tuple[PublicMerchant, ...]:
        statement = select(merchant_profiles).where(
            merchant_profiles.c.state == "approved"
        )
        if query:
            statement = statement.where(
                func.lower(merchant_profiles.c.display_name).like(
                    f"%{query.casefold()}%"
                )
            )
        rows = self._connection.execute(
            statement.order_by(
                merchant_profiles.c.display_name, merchant_profiles.c.merchant_id
            ).limit(limit)
        ).mappings()
        return tuple(
            PublicMerchant(
                merchant_id=row["merchant_id"],
                display_name=row["display_name"],
                capability_code=row["capability_code"],
                market_code=row["market_code"],
            )
            for row in rows
        )

    def public_merchant(self, merchant_id: UUID) -> PublicMerchant | None:
        row = (
            self._connection.execute(
                select(merchant_profiles).where(
                    merchant_profiles.c.merchant_id == merchant_id,
                    merchant_profiles.c.state == "approved",
                )
            )
            .mappings()
            .one_or_none()
        )
        return (
            None
            if row is None
            else PublicMerchant(
                merchant_id=row["merchant_id"],
                display_name=row["display_name"],
                capability_code=row["capability_code"],
                market_code=row["market_code"],
            )
        )

    def public_categories(
        self, merchant_id: UUID, *, limit: int
    ) -> tuple[PublicCategory, ...]:
        rows = self._connection.execute(
            select(catalogue_categories)
            .where(
                catalogue_categories.c.merchant_id == merchant_id,
                catalogue_categories.c.active.is_(True),
            )
            .order_by(catalogue_categories.c.sort_order, catalogue_categories.c.name)
            .limit(limit)
        ).mappings()
        return tuple(
            PublicCategory(
                category_id=row["category_id"],
                parent_category_id=row["parent_category_id"],
                name=row["name"],
                description=row["description"],
                sort_order=row["sort_order"],
            )
            for row in rows
        )

    def public_items(
        self,
        merchant_id: UUID,
        *,
        query: str | None,
        category_id: UUID | None,
        tag: str | None,
        limit: int,
    ) -> tuple[PublicCatalogueItem, ...]:
        statement = select(universal_catalogue_items).where(
            universal_catalogue_items.c.merchant_id == merchant_id,
            universal_catalogue_items.c.status == "active",
            universal_catalogue_items.c.visibility == "public",
            universal_catalogue_items.c.availability != "hidden",
            universal_catalogue_items.c.base_price_minor.is_not(None),
        )
        if category_id:
            statement = statement.where(
                universal_catalogue_items.c.category_id == category_id
            )
        if query:
            pattern = f"%{query.casefold()}%"
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
                sql_cast(universal_catalogue_items.c.tags, String).ilike(
                    f'%"{tag.casefold()}"%'
                )
            )
        rows = self._connection.execute(
            statement.order_by(
                universal_catalogue_items.c.name, universal_catalogue_items.c.item_id
            ).limit(limit)
        ).mappings()
        return tuple(
            PublicCatalogueItem(
                item_id=row["item_id"],
                merchant_id=row["merchant_id"],
                category_id=row["category_id"],
                kind=row["kind"],
                name=row["name"],
                description=row["description"],
                media=tuple(row["media"]),
                availability=row["availability"],
                tags=tuple(row["tags"]),
                base_price_minor=row["base_price_minor"],
                currency=row["currency"],
                version=row["version"],
            )
            for row in rows
        )

    def public_item(self, item_id: UUID) -> PublicCatalogueItem | None:
        rows = self.public_items_for_ids((item_id,))
        return rows[0] if rows else None

    def public_items_for_ids(
        self, item_ids: tuple[UUID, ...]
    ) -> tuple[PublicCatalogueItem, ...]:
        if not item_ids:
            return ()
        rows = self._connection.execute(
            select(universal_catalogue_items).where(
                universal_catalogue_items.c.item_id.in_(item_ids),
                universal_catalogue_items.c.status == "active",
                universal_catalogue_items.c.visibility == "public",
                universal_catalogue_items.c.availability != "hidden",
                universal_catalogue_items.c.base_price_minor.is_not(None),
            )
        ).mappings()
        return tuple(
            PublicCatalogueItem(
                item_id=row["item_id"],
                merchant_id=row["merchant_id"],
                category_id=row["category_id"],
                kind=row["kind"],
                name=row["name"],
                description=row["description"],
                media=tuple(row["media"]),
                availability=row["availability"],
                tags=tuple(row["tags"]),
                base_price_minor=row["base_price_minor"],
                currency=row["currency"],
                version=row["version"],
            )
            for row in rows
        )
