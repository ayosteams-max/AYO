"""Add representative performance, readiness and recommendation evidence.

Revision ID: 20260721_0043
Revises: 20260721_0042
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0043"
down_revision: str | Sequence[str] | None = "20260721_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    permissions = sa.table(
        "permissions",
        sa.column("permission_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema="ayo",
    )
    codes = (
        (
            "00000000-0000-4000-8000-00000000f821",
            "field_performance.evidence.record",
            "Record authoritative representative performance evidence.",
        ),
        (
            "00000000-0000-4000-8000-00000000f822",
            "field_performance.readiness.record",
            "Record representative readiness assertions.",
        ),
        (
            "00000000-0000-4000-8000-00000000f823",
            "field_performance.recommend",
            "Prepare non-executing performance recommendations.",
        ),
        (
            "00000000-0000-4000-8000-00000000f824",
            "field_performance.read_own",
            "Read own representative performance evidence.",
        ),
        (
            "00000000-0000-4000-8000-00000000f825",
            "field_performance.management.read",
            "Read management performance summaries.",
        ),
    )
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": UUID(i),
                "code": c,
                "description": d,
                "created_at": datetime.now(UTC),
            }
            for i, c, d in codes
        ],
    )
    op.create_table(
        "field_performance_evidence",
        sa.Column("evidence_id", sa.UUID(), primary_key=True),
        sa.Column(
            "partner_id",
            sa.UUID(),
            sa.ForeignKey("ayo.field_partners.partner_id"),
            nullable=False,
        ),
        sa.Column("territory_id", sa.UUID()),
        sa.Column("metric", sa.String(48), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("source_domain", sa.String(63), nullable=False),
        sa.Column("source_event_id", sa.UUID(), nullable=False),
        sa.Column("evidence_reference", sa.String(160), nullable=False),
        sa.Column("window_starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.String(63), nullable=False),
        sa.Column("recorded_by_identity_id", sa.UUID(), nullable=False),
        sa.Column(
            "supersedes_evidence_id",
            sa.UUID(),
            sa.ForeignKey("ayo.field_performance_evidence.evidence_id"),
        ),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "value >= 0 AND window_ends_at > window_starts_at",
            name="field_performance_value_window_valid",
        ),
        sa.CheckConstraint(
            "unit <> 'basis_points' OR value <= 10000",
            name="field_performance_basis_points_valid",
        ),
        sa.CheckConstraint(
            "unit <> 'boolean' OR value IN (0,1)",
            name="field_performance_boolean_valid",
        ),
        sa.UniqueConstraint(
            "source_domain",
            "source_event_id",
            "metric",
            name="uq_field_performance_source_metric",
        ),
        schema="ayo",
    )
    op.create_index(
        "ix_field_performance_partner_metric",
        "field_performance_evidence",
        ["partner_id", "metric", "recorded_at"],
        schema="ayo",
    )
    op.create_index(
        "ix_field_performance_territory_window",
        "field_performance_evidence",
        ["territory_id", "window_ends_at"],
        schema="ayo",
    )
    op.create_table(
        "field_readiness_assertions",
        sa.Column("assertion_id", sa.UUID(), primary_key=True),
        sa.Column(
            "partner_id",
            sa.UUID(),
            sa.ForeignKey("ayo.field_partners.partner_id"),
            nullable=False,
        ),
        sa.Column("requirement", sa.String(48), nullable=False),
        sa.Column("satisfied", sa.Boolean(), nullable=False),
        sa.Column("source_domain", sa.String(63), nullable=False),
        sa.Column("source_event_id", sa.UUID(), nullable=False),
        sa.Column("evidence_reference", sa.String(160), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("recorded_by_identity_id", sa.UUID(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > effective_at",
            name="field_readiness_window_valid",
        ),
        sa.UniqueConstraint(
            "source_domain",
            "source_event_id",
            "requirement",
            name="uq_field_readiness_source_requirement",
        ),
        schema="ayo",
    )
    op.create_index(
        "ix_field_readiness_partner_requirement",
        "field_readiness_assertions",
        ["partner_id", "requirement", "recorded_at"],
        schema="ayo",
    )
    op.create_table(
        "field_performance_recommendations",
        sa.Column("recommendation_id", sa.UUID(), primary_key=True),
        sa.Column(
            "partner_id",
            sa.UUID(),
            sa.ForeignKey("ayo.field_partners.partner_id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("confidence_bps", sa.Integer(), nullable=False),
        sa.Column("reasoning", sa.String(2000), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("intelligence_domain", sa.String(63), nullable=False),
        sa.Column("policy_version", sa.String(63), nullable=False),
        sa.Column("recommended_by_identity_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "confidence_bps BETWEEN 0 AND 10000",
            name="field_recommendation_confidence_valid",
        ),
        sa.CheckConstraint(
            "status = 'recommendation_only'", name="field_recommendation_non_executing"
        ),
        schema="ayo",
    )
    op.create_index(
        "ix_field_recommendation_partner_time",
        "field_performance_recommendations",
        ["partner_id", "created_at"],
        schema="ayo",
    )
    op.create_table(
        "field_performance_events",
        sa.Column("event_id", sa.UUID(), primary_key=True),
        sa.Column("aggregate_type", sa.String(40), nullable=False),
        sa.Column("aggregate_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("actor_identity_id", sa.UUID(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        schema="ayo",
    )
    op.create_table(
        "field_performance_idempotency",
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
            name="uq_field_performance_idempotency",
        ),
        schema="ayo",
    )
    op.execute(
        "GRANT SELECT,INSERT ON ayo.field_performance_evidence,ayo.field_readiness_assertions,ayo.field_performance_recommendations,ayo.field_performance_events,ayo.field_performance_idempotency TO ayo_runtime"
    )


def downgrade() -> None:
    for table in (
        "field_performance_idempotency",
        "field_performance_events",
        "field_performance_recommendations",
        "field_readiness_assertions",
        "field_performance_evidence",
    ):
        op.drop_table(table, schema="ayo")
    op.execute("DELETE FROM ayo.permissions WHERE code LIKE 'field_performance.%'")
