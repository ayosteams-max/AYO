"""Create the provider-neutral support foundation.

Revision ID: 20260715_0007
Revises: 20260715_0006
Create Date: 2026-07-15
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0007"
down_revision: str | Sequence[str] | None = "20260715_0006"
branch_labels = None
depends_on = None
SCHEMA = "ayo"


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "support_cases",
        sa.Column("case_id", uuid, primary_key=True),
        sa.Column("public_reference", uuid, nullable=False, unique=True),
        sa.Column(
            "requester_identity_id", uuid, sa.ForeignKey("ayo.identities.identity_id")
        ),
        sa.Column("requester_type", sa.String(24), nullable=False),
        sa.Column("source_channel", sa.String(32), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("risk_classification", sa.String(24), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("assigned_queue", sa.String(24), nullable=False),
        sa.Column(
            "assigned_human_identity_id",
            uuid,
            sa.ForeignKey("ayo.identities.identity_id"),
        ),
        sa.Column(
            "ai_service_identity_id", uuid, sa.ForeignKey("ayo.identities.identity_id")
        ),
        sa.Column("related_ride_reference", sa.String(128)),
        sa.Column("related_payment_status_reference", sa.String(128)),
        sa.Column("correlation_id", uuid, nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("escalation_reason", sa.String(63)),
        sa.Column("resolution_category", sa.String(63)),
        sa.Column("retention_classification", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("version > 0", name="ck_support_cases_positive_version"),
        sa.CheckConstraint(
            "requester_type IN ('anonymous','rider','driver','merchant','staff','service')",
            name="ck_support_cases_valid_requester_type",
        ),
        sa.CheckConstraint(
            "status IN ('new','gathering_information','in_progress',"
            "'waiting_for_customer','waiting_for_internal_team','escalated',"
            "'resolved','closed','cancelled')",
            name="ck_support_cases_valid_status",
        ),
        sa.CheckConstraint(
            "assigned_queue IN ('general','safety','fraud','finance','identity','legal')",
            name="ck_support_cases_valid_queue",
        ),
        sa.CheckConstraint(
            "priority IN ('low','normal','high','urgent','emergency')",
            name="ck_support_cases_valid_priority",
        ),
        sa.CheckConstraint(
            "risk_classification IN ('routine','sensitive','safety','fraud','financial',"
            "'identity','legal','account_takeover')",
            name="ck_support_cases_valid_risk",
        ),
        schema=SCHEMA,
    )
    for name, columns in (
        ("ix_support_cases_requester", ["requester_identity_id"]),
        ("ix_support_cases_queue_status", ["assigned_queue", "status"]),
        ("ix_support_cases_ai_assignment", ["ai_service_identity_id"]),
        ("ix_support_cases_human_assignment", ["assigned_human_identity_id"]),
    ):
        op.create_index(name, "support_cases", columns, schema=SCHEMA)
    op.create_table(
        "support_case_events",
        sa.Column("event_id", uuid, primary_key=True),
        sa.Column(
            "case_id", uuid, sa.ForeignKey("ayo.support_cases.case_id"), nullable=False
        ),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("actor_identity_id", uuid),
        sa.Column("actor_type", sa.String(24), nullable=False),
        sa.Column("correlation_id", uuid, nullable=False),
        sa.Column("safe_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('anonymous','rider','driver','merchant','staff','service')",
            name="ck_support_case_events_valid_actor_type",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_support_case_events_case_time",
        "support_case_events",
        ["case_id", "occurred_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_support_case_events_correlation",
        "support_case_events",
        ["correlation_id"],
        schema=SCHEMA,
    )
    op.create_table(
        "support_case_messages",
        sa.Column("message_id", uuid, primary_key=True),
        sa.Column(
            "case_id", uuid, sa.ForeignKey("ayo.support_cases.case_id"), nullable=False
        ),
        sa.Column(
            "author_identity_id", uuid, sa.ForeignKey("ayo.identities.identity_id")
        ),
        sa.Column("visibility", sa.String(24), nullable=False),
        sa.Column("language_tag", sa.String(35), nullable=False),
        sa.Column("content", sa.String(2000), nullable=False),
        sa.Column("redaction_applied", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "visibility IN ('customer_visible','internal_note')",
            name="ck_support_case_messages_valid_visibility",
        ),
        sa.CheckConstraint(
            "char_length(content) BETWEEN 1 AND 2000",
            name="ck_support_case_messages_bounded_content",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_support_case_messages_case_time",
        "support_case_messages",
        ["case_id", "created_at"],
        schema=SCHEMA,
    )
    op.create_table(
        "support_ai_interactions",
        sa.Column("interaction_id", uuid, primary_key=True),
        sa.Column("conversation_id", uuid, nullable=False),
        sa.Column(
            "case_id", uuid, sa.ForeignKey("ayo.support_cases.case_id"), nullable=False
        ),
        sa.Column(
            "ai_service_identity_id",
            uuid,
            sa.ForeignKey("ayo.identities.identity_id"),
            nullable=False,
        ),
        sa.Column("model_reference", sa.String(63)),
        sa.Column("model_version_reference", sa.String(63)),
        sa.Column("confidence_band", sa.String(16), nullable=False),
        sa.Column("action_category", sa.String(63), nullable=False),
        sa.Column("escalation_reason", sa.String(63)),
        sa.Column("human_takeover_at", sa.DateTime(timezone=True)),
        sa.Column("correlation_id", uuid, nullable=False),
        sa.Column("safe_outcome_category", sa.String(63), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence_band IN ('unknown','low','medium','high')",
            name="ck_support_ai_interactions_valid_confidence",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_support_ai_interactions_case",
        "support_ai_interactions",
        ["case_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_support_ai_interactions_conversation",
        "support_ai_interactions",
        ["conversation_id"],
        schema=SCHEMA,
    )

    permissions = sa.table(
        "permissions",
        sa.column("permission_id", uuid),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    op.bulk_insert(
        permissions,
        [
            {
                "permission_id": f"00000000-0000-4000-8000-0000000000{index}",
                "code": f"support.queue.{queue}.access",
                "description": description,
                "created_at": datetime.now(UTC),
            }
            for index, queue, description in (
                (20, "general", "Access support cases assigned to the general queue."),
                (21, "safety", "Access restricted safety support cases."),
                (22, "fraud", "Access restricted fraud support cases."),
                (23, "finance", "Access restricted finance support cases."),
                (24, "identity", "Access restricted identity support cases."),
                (25, "legal", "Access restricted legal support cases."),
            )
        ],
    )
    op.execute(
        "REVOKE ALL ON TABLE ayo.support_cases, ayo.support_case_events, ayo.support_case_messages, ayo.support_ai_interactions FROM PUBLIC"
    )
    op.execute("""
    DO $ayo$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ayo_runtime') THEN
        GRANT SELECT, INSERT, UPDATE ON ayo.support_cases TO ayo_runtime;
        GRANT SELECT, INSERT ON ayo.support_case_events, ayo.support_case_messages,
          ayo.support_ai_interactions TO ayo_runtime;
        REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON ayo.support_cases,
          ayo.support_case_events, ayo.support_case_messages,
          ayo.support_ai_interactions FROM ayo_runtime;
        REVOKE UPDATE ON ayo.support_case_events, ayo.support_case_messages,
          ayo.support_ai_interactions FROM ayo_runtime;
      END IF;
    END $ayo$
    """)


def downgrade() -> None:
    raise RuntimeError(
        "Destructive support downgrade is prohibited; use a forward fix."
    )
