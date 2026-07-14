from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)
AYO_SCHEMA = "ayo"
VERSION_TABLE = "ayo_schema_version"

sessions = Table(
    "sessions",
    metadata,
    Column("session_id", UUID(as_uuid=True), primary_key=True),
    Column("subject_id", String(128), nullable=False),
    Column("token_hash", LargeBinary(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
    Column("revocation_reason", String(64)),
    Column("version", Integer, nullable=False, server_default=text("1")),
    CheckConstraint("expires_at > created_at", name="valid_lifetime"),
    CheckConstraint("version > 0", name="positive_version"),
    CheckConstraint(
        "(revoked_at IS NULL) = (revocation_reason IS NULL)",
        name="consistent_revocation",
    ),
    CheckConstraint(
        "revocation_reason IS NULL OR revocation_reason ~ '^[a-z][a-z0-9_.-]{0,63}$'",
        name="safe_revocation_reason",
    ),
    UniqueConstraint("token_hash"),
    schema=AYO_SCHEMA,
)
Index("ix_sessions_subject_id", sessions.c.subject_id)
Index("ix_sessions_expires_at", sessions.c.expires_at)
Index(
    "ix_sessions_active_subject",
    sessions.c.subject_id,
    sessions.c.expires_at,
    postgresql_where=sessions.c.revoked_at.is_(None),
)

rate_limit_buckets = Table(
    "rate_limit_buckets",
    metadata,
    Column("key_hash", LargeBinary(32), primary_key=True),
    Column("policy_name", String(63), primary_key=True),
    Column("tokens", Numeric(20, 6), nullable=False),
    Column("last_refill_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("tokens >= 0", name="nonnegative_tokens"),
    schema=AYO_SCHEMA,
)
Index("ix_rate_limit_buckets_updated_at", rate_limit_buckets.c.updated_at)

audit_events = Table(
    "audit_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column(
        "recorded_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column("actor_type", String(24), nullable=False),
    Column("actor_id", String(128)),
    Column("session_id", UUID(as_uuid=True)),
    Column("action", String(128), nullable=False),
    Column("resource_type", String(128), nullable=False),
    Column("resource_id", String(128)),
    Column("outcome", String(16), nullable=False),
    Column("reason", String(128)),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True)),
    Column("request_id", UUID(as_uuid=True)),
    Column("source_module", String(63), nullable=False),
    Column("schema_version", Integer, nullable=False, server_default=text("1")),
    Column("safe_metadata", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("idempotency_key", String(128)),
    CheckConstraint("schema_version > 0", name="positive_schema_version"),
    CheckConstraint(
        "actor_type IN ('anonymous', 'rider', 'driver', 'staff', "
        "'administrator', 'system', 'service')",
        name="valid_actor_type",
    ),
    CheckConstraint(
        "outcome IN ('success', 'denied', 'failed', 'cancelled')",
        name="valid_outcome",
    ),
    schema=AYO_SCHEMA,
)
Index("ix_audit_events_occurred_at", audit_events.c.occurred_at)
Index("ix_audit_events_actor", audit_events.c.actor_type, audit_events.c.actor_id)
Index(
    "ix_audit_events_resource",
    audit_events.c.resource_type,
    audit_events.c.resource_id,
)
Index("ix_audit_events_action", audit_events.c.action)
Index("ix_audit_events_correlation_id", audit_events.c.correlation_id)
Index("ix_audit_events_outcome", audit_events.c.outcome)
Index(
    "uq_audit_events_idempotency",
    audit_events.c.source_module,
    audit_events.c.action,
    audit_events.c.idempotency_key,
    unique=True,
    postgresql_where=audit_events.c.idempotency_key.is_not(None),
)

rides = Table(
    "rides",
    metadata,
    Column(
        "id",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("public_ride_id", String(50), nullable=False),
    Column("rider_name", String(100), nullable=False),
    Column("pickup", String(200), nullable=False),
    Column("destination", String(200), nullable=False),
    Column("ride_type", String(40), nullable=False),
    Column("status", String(40), nullable=False),
    Column("driver_id", String(50)),
    Column("driver_name", String(100)),
    Column("driver_distance_km", Float),
    Column("driver_queue", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("current_offer_index", Integer),
    Column("current_offer", JSONB().with_variant(JSON(), "sqlite")),
    Column("gross_fare", Float),
    Column("payment_method", String(40)),
    Column("tip", Float),
    Column("bonus", Float),
    Column("version", Integer, nullable=False, server_default=text("1")),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    CheckConstraint("version > 0", name="positive_version"),
    UniqueConstraint("public_ride_id"),
    schema=AYO_SCHEMA,
)

legacy_wallets = Table(
    "legacy_wallets",
    metadata,
    Column(
        "id",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("driver_id", String(50), nullable=False),
    Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    CheckConstraint("version > 0", name="positive_version"),
    UniqueConstraint("driver_id"),
    comment=(
        "Non-authoritative prototype state. Never treat as a financial ledger or "
        "migrate as trusted balances."
    ),
    schema=AYO_SCHEMA,
)
