"""Add universal commerce catalogue foundation.

Revision ID: 20260720_0033
Revises: 20260720_0032
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0033"
down_revision: str | Sequence[str] | None = "20260720_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    jsonb = postgresql.JSONB()
    permissions = sa.table(
        "permissions",
        sa.column("permission_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema="ayo",
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000f001"),
                "code": "catalogue.manage_own",
                "description": "Manage catalogue records for an owned merchant.",
                "created_at": now,
            },
            {
                "permission_id": UUID("00000000-0000-4000-8000-00000000f002"),
                "code": "catalogue.read_own",
                "description": "Read and search an owned merchant catalogue.",
                "created_at": now,
            },
        ],
    )
    op.create_table(
        "catalogue_categories",
        sa.Column("category_id", sa.UUID(), primary_key=True),
        sa.Column(
            "merchant_id",
            sa.UUID(),
            sa.ForeignKey("ayo.merchant_profiles.merchant_id"),
            nullable=False,
        ),
        sa.Column(
            "parent_category_id",
            sa.UUID(),
            sa.ForeignKey("ayo.catalogue_categories.category_id"),
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("normalized_name", sa.String(120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "merchant_id",
            "parent_category_id",
            "normalized_name",
            name="uq_catalogue_category_sibling",
        ),
        schema="ayo",
    )
    op.create_index(
        "ix_catalogue_category_tree",
        "catalogue_categories",
        ["merchant_id", "parent_category_id", "sort_order"],
        schema="ayo",
    )
    op.create_index(
        "uq_catalogue_root_category",
        "catalogue_categories",
        ["merchant_id", "normalized_name"],
        unique=True,
        schema="ayo",
        postgresql_where=sa.text("parent_category_id IS NULL"),
    )
    op.create_table(
        "universal_catalogue_items",
        sa.Column("item_id", sa.UUID(), primary_key=True),
        sa.Column(
            "merchant_id",
            sa.UUID(),
            sa.ForeignKey("ayo.merchant_profiles.merchant_id"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            sa.UUID(),
            sa.ForeignKey("ayo.catalogue_categories.category_id"),
        ),
        sa.Column(
            "branch_id", sa.UUID(), sa.ForeignKey("ayo.merchant_branches.branch_id")
        ),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(2000)),
        sa.Column("media", jsonb, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("availability", sa.String(32), nullable=False),
        sa.Column("visibility", sa.String(24), nullable=False),
        sa.Column("tags", jsonb, nullable=False),
        sa.Column("search_keywords", jsonb, nullable=False),
        sa.Column("base_price_minor", sa.BigInteger()),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("variant_contract_version", sa.Integer()),
        sa.Column("modifier_contract_version", sa.Integer()),
        sa.Column(
            "source_item_id",
            sa.UUID(),
            sa.ForeignKey("ayo.universal_catalogue_items.item_id"),
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "base_price_minor IS NULL OR base_price_minor >= 0",
            name="catalogue_nonnegative_price",
        ),
        sa.CheckConstraint("currency = 'ETB'", name="catalogue_etb_currency"),
        schema="ayo",
    )
    op.create_index(
        "ix_catalogue_item_page",
        "universal_catalogue_items",
        ["merchant_id", "status", "updated_at", "item_id"],
        schema="ayo",
    )
    op.create_index(
        "ix_catalogue_item_category",
        "universal_catalogue_items",
        ["merchant_id", "category_id", "status"],
        schema="ayo",
    )
    op.create_table(
        "catalogue_idempotency",
        sa.Column("actor_identity_id", sa.UUID(), nullable=False),
        sa.Column("operation", sa.String(63), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_reference", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "actor_identity_id",
            "operation",
            "idempotency_key",
            name="uq_catalogue_idempotency",
        ),
        schema="ayo",
    )
    op.create_table(
        "catalogue_outbox",
        sa.Column("message_id", sa.UUID(), primary_key=True),
        sa.Column(
            "merchant_id",
            sa.UUID(),
            sa.ForeignKey("ayo.merchant_profiles.merchant_id"),
            nullable=False,
        ),
        sa.Column(
            "item_id", sa.UUID(), sa.ForeignKey("ayo.universal_catalogue_items.item_id")
        ),
        sa.Column("event_type", sa.String(63), nullable=False),
        sa.Column("safe_payload", jsonb, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        schema="ayo",
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON ayo.catalogue_categories, ayo.universal_catalogue_items TO ayo_runtime"
    )
    op.execute(
        "GRANT SELECT, INSERT ON ayo.catalogue_idempotency, ayo.catalogue_outbox TO ayo_runtime"
    )


def downgrade() -> None:
    for table in (
        "catalogue_outbox",
        "catalogue_idempotency",
        "universal_catalogue_items",
        "catalogue_categories",
    ):
        op.drop_table(table, schema="ayo")
    op.execute(
        "DELETE FROM ayo.permissions WHERE code IN ('catalogue.manage_own', 'catalogue.read_own')"
    )
