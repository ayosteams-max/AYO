from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
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
from sqlalchemy.dialects.postgresql import JSONB, UUID, ExcludeConstraint

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

identities = Table(
    "identities",
    metadata,
    Column("identity_id", UUID(as_uuid=True), primary_key=True),
    Column("public_id", UUID(as_uuid=True), nullable=False),
    Column("identity_type", String(32), nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    UniqueConstraint("public_id"),
    CheckConstraint("version > 0", name="positive_version"),
    CheckConstraint(
        "identity_type IN ('anonymous','rider','driver','staff','administrator',"
        "'service','merchant','service_provider')",
        name="valid_identity_type",
    ),
    CheckConstraint(
        "status IN ('pending','active','suspended','locked','disabled',"
        "'recovery_pending','deletion_pending')",
        name="valid_status",
    ),
    schema=AYO_SCHEMA,
)
Index("ix_identities_type_status", identities.c.identity_type, identities.c.status)

permissions = Table(
    "permissions",
    metadata,
    Column("permission_id", UUID(as_uuid=True), primary_key=True),
    Column("code", String(63), nullable=False),
    Column("description", String(256), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("code"),
    CheckConstraint("code ~ '^[a-z][a-z0-9_.-]{2,62}$'", name="valid_code"),
    schema=AYO_SCHEMA,
)

roles = Table(
    "roles",
    metadata,
    Column("role_id", UUID(as_uuid=True), primary_key=True),
    Column("code", String(63), nullable=False),
    Column("description", String(256), nullable=False),
    Column("system_managed", Boolean, nullable=False, server_default=text("false")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    UniqueConstraint("code"),
    CheckConstraint("code ~ '^[a-z][a-z0-9_.-]{2,62}$'", name="valid_code"),
    CheckConstraint("version > 0", name="positive_version"),
    schema=AYO_SCHEMA,
)

role_permissions = Table(
    "role_permissions",
    metadata,
    Column(
        "role_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.roles.role_id"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.permissions.permission_id"),
        primary_key=True,
    ),
    Column("granted_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index("ix_role_permissions_permission", role_permissions.c.permission_id)

identity_role_assignments = Table(
    "identity_role_assignments",
    metadata,
    Column("assignment_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column(
        "role_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.roles.role_id"),
        nullable=False,
    ),
    Column("assigned_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("assigned_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
    Column("revoked_by_identity_id", UUID(as_uuid=True)),
    Column("revocation_reason", String(63)),
    CheckConstraint(
        "expires_at IS NULL OR expires_at > assigned_at", name="valid_lifetime"
    ),
    CheckConstraint(
        "(revoked_at IS NULL AND revoked_by_identity_id IS NULL AND "
        "revocation_reason IS NULL) OR (revoked_at IS NOT NULL AND "
        "revoked_by_identity_id IS NOT NULL AND revocation_reason IS NOT NULL)",
        name="consistent_revocation",
    ),
    CheckConstraint(
        "revocation_reason IS NULL OR revocation_reason ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="safe_revocation_reason",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_identity_role_assignments_identity_active",
    identity_role_assignments.c.identity_id,
    identity_role_assignments.c.role_id,
    unique=True,
    postgresql_where=identity_role_assignments.c.revoked_at.is_(None),
)
Index("ix_identity_role_assignments_role", identity_role_assignments.c.role_id)

identity_authentication_methods = Table(
    "identity_authentication_methods",
    metadata,
    Column("method_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("method_type", String(32), nullable=False),
    Column("status", String(24), nullable=False),
    Column("lookup_reference", LargeBinary(32)),
    Column("assurance_level", String(32), nullable=False),
    Column("verified_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("identity_id", "method_type", "lookup_reference"),
    CheckConstraint(
        "method_type IN ('phone_otp','email_verification','password','passkey',"
        "'recovery_code','staff_mfa','service_credential')",
        name="valid_method_type",
    ),
    CheckConstraint(
        "assurance_level IN ('basic','multi_factor','phishing_resistant')",
        name="valid_assurance_level",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_identity_auth_methods_identity",
    identity_authentication_methods.c.identity_id,
)

credential_verifiers = Table(
    "credential_verifiers",
    metadata,
    Column("credential_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "method_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identity_authentication_methods.method_id"),
        nullable=False,
    ),
    Column("scheme", String(32), nullable=False),
    Column("verifier", String(512), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("method_id"),
    schema=AYO_SCHEMA,
)

authentication_challenges = Table(
    "authentication_challenges",
    metadata,
    Column("challenge_id", UUID(as_uuid=True), primary_key=True),
    Column("method_id", UUID(as_uuid=True)),
    Column("purpose", String(32), nullable=False),
    Column("verifier", LargeBinary(64), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("consumed_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    Column("max_attempts", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("attempt_count >= 0", name="nonnegative_attempts"),
    CheckConstraint("max_attempts BETWEEN 1 AND 10", name="bounded_max_attempts"),
    CheckConstraint("attempt_count <= max_attempts", name="attempts_within_limit"),
    schema=AYO_SCHEMA,
)
Index("ix_auth_challenges_expires_at", authentication_challenges.c.expires_at)

identity_devices = Table(
    "identity_devices",
    metadata,
    Column("device_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("fingerprint_reference", LargeBinary(32), nullable=False),
    Column("device_category", String(32), nullable=False),
    Column("operating_system_family", String(32), nullable=False),
    Column("trust_state", String(24), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("identity_id", "fingerprint_reference"),
    CheckConstraint(
        "trust_state IN ('unknown','recognized','trusted','restricted')",
        name="valid_trust_state",
    ),
    schema=AYO_SCHEMA,
)
Index("ix_identity_devices_identity", identity_devices.c.identity_id)

token_families = Table(
    "token_families",
    metadata,
    Column("family_id", UUID(as_uuid=True), primary_key=True),
    Column("identity_id", UUID(as_uuid=True), nullable=False),
    Column("session_id", UUID(as_uuid=True), nullable=False),
    Column("current_token_hash", LargeBinary(32), nullable=False),
    Column("rotation_counter", Integer, nullable=False, server_default=text("0")),
    Column("status", String(24), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    Column("replay_detected_at", DateTime(timezone=True)),
    UniqueConstraint("current_token_hash"),
    CheckConstraint("rotation_counter >= 0", name="nonnegative_rotation_counter"),
    CheckConstraint("status IN ('active','revoked','expired')", name="valid_status"),
    CheckConstraint("expires_at > created_at", name="valid_lifetime"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_token_families_identity_status",
    token_families.c.identity_id,
    token_families.c.status,
)
Index("ix_token_families_session", token_families.c.session_id)

refresh_token_rotations = Table(
    "refresh_token_rotations",
    metadata,
    Column("rotation_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "family_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.token_families.family_id"),
        nullable=False,
    ),
    Column("token_hash", LargeBinary(32), nullable=False),
    Column("rotation_counter", Integer, nullable=False),
    Column("consumed_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("token_hash"),
    UniqueConstraint("family_id", "rotation_counter"),
    schema=AYO_SCHEMA,
)

recovery_cases = Table(
    "recovery_cases",
    metadata,
    Column("recovery_id", UUID(as_uuid=True), primary_key=True),
    Column("identity_id", UUID(as_uuid=True), nullable=False),
    Column("status", String(24), nullable=False),
    Column("risk_level", String(24), nullable=False),
    Column("reason", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    schema=AYO_SCHEMA,
)
Index(
    "ix_recovery_cases_identity_status",
    recovery_cases.c.identity_id,
    recovery_cases.c.status,
)

sessions = Table(
    "sessions",
    metadata,
    Column("session_id", UUID(as_uuid=True), primary_key=True),
    Column("subject_id", String(128), nullable=False),
    Column("identity_id", UUID(as_uuid=True)),
    Column("device_id", UUID(as_uuid=True)),
    Column("device_fingerprint_ref", LargeBinary(32)),
    Column("device_category", String(32)),
    Column("application_version", String(32)),
    Column("operating_system_family", String(32)),
    Column("authentication_method", String(32)),
    Column("assurance_level", String(32)),
    Column("risk_state", String(32)),
    Column("ip_risk_ref", LargeBinary(32)),
    Column("token_family_id", UUID(as_uuid=True)),
    Column(
        "refresh_rotation_counter", Integer, nullable=False, server_default=text("0")
    ),
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
        "refresh_rotation_counter >= 0", name="nonnegative_rotation_counter"
    ),
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

support_cases = Table(
    "support_cases",
    metadata,
    Column("case_id", UUID(as_uuid=True), primary_key=True),
    Column("public_reference", UUID(as_uuid=True), nullable=False, unique=True),
    Column(
        "requester_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
    ),
    Column("requester_type", String(24), nullable=False),
    Column("source_channel", String(32), nullable=False),
    Column("category", String(40), nullable=False),
    Column("priority", String(16), nullable=False),
    Column("risk_classification", String(24), nullable=False),
    Column("status", String(32), nullable=False),
    Column("assigned_queue", String(24), nullable=False),
    Column(
        "assigned_human_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
    ),
    Column(
        "ai_service_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
    ),
    Column("related_ride_reference", String(128)),
    Column("related_payment_status_reference", String(128)),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("idempotency_key", String(128), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("resolved_at", DateTime(timezone=True)),
    Column("closed_at", DateTime(timezone=True)),
    Column("escalation_reason", String(63)),
    Column("resolution_category", String(63)),
    Column("retention_classification", String(32), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    CheckConstraint("version > 0", name="positive_version"),
    CheckConstraint(
        "requester_type IN ('anonymous','rider','driver','merchant','staff','service')",
        name="valid_requester_type",
    ),
    CheckConstraint(
        "status IN ('new','gathering_information','in_progress',"
        "'waiting_for_customer','waiting_for_internal_team','escalated',"
        "'resolved','closed','cancelled')",
        name="valid_status",
    ),
    CheckConstraint(
        "assigned_queue IN ('general','safety','fraud','finance','identity','legal')",
        name="valid_queue",
    ),
    CheckConstraint(
        "priority IN ('low','normal','high','urgent','emergency')",
        name="valid_priority",
    ),
    CheckConstraint(
        "risk_classification IN ('routine','sensitive','safety','fraud','financial',"
        "'identity','legal','account_takeover')",
        name="valid_risk",
    ),
    schema=AYO_SCHEMA,
)
Index("ix_support_cases_requester", support_cases.c.requester_identity_id)
Index(
    "ix_support_cases_queue_status",
    support_cases.c.assigned_queue,
    support_cases.c.status,
)
Index("ix_support_cases_ai_assignment", support_cases.c.ai_service_identity_id)
Index("ix_support_cases_human_assignment", support_cases.c.assigned_human_identity_id)

support_case_events = Table(
    "support_case_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "case_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.support_cases.case_id"),
        nullable=False,
    ),
    Column("event_type", String(40), nullable=False),
    Column("actor_identity_id", UUID(as_uuid=True)),
    Column("actor_type", String(24), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("safe_metadata", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "actor_type IN ('anonymous','rider','driver','merchant','staff','service')",
        name="valid_actor_type",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_support_case_events_case_time",
    support_case_events.c.case_id,
    support_case_events.c.occurred_at,
)
Index("ix_support_case_events_correlation", support_case_events.c.correlation_id)

support_case_messages = Table(
    "support_case_messages",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "case_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.support_cases.case_id"),
        nullable=False,
    ),
    Column(
        "author_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
    ),
    Column("visibility", String(24), nullable=False),
    Column("language_tag", String(35), nullable=False),
    Column("content", String(2000), nullable=False),
    Column("redaction_applied", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "visibility IN ('customer_visible','internal_note')", name="valid_visibility"
    ),
    CheckConstraint("char_length(content) BETWEEN 1 AND 2000", name="bounded_content"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_support_case_messages_case_time",
    support_case_messages.c.case_id,
    support_case_messages.c.created_at,
)

support_ai_interactions = Table(
    "support_ai_interactions",
    metadata,
    Column("interaction_id", UUID(as_uuid=True), primary_key=True),
    Column("conversation_id", UUID(as_uuid=True), nullable=False),
    Column(
        "case_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.support_cases.case_id"),
        nullable=False,
    ),
    Column(
        "ai_service_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("model_reference", String(63)),
    Column("model_version_reference", String(63)),
    Column("confidence_band", String(16), nullable=False),
    Column("action_category", String(63), nullable=False),
    Column("escalation_reason", String(63)),
    Column("human_takeover_at", DateTime(timezone=True)),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("safe_outcome_category", String(63), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "confidence_band IN ('unknown','low','medium','high')", name="valid_confidence"
    ),
    schema=AYO_SCHEMA,
)
Index("ix_support_ai_interactions_case", support_ai_interactions.c.case_id)
Index(
    "ix_support_ai_interactions_conversation", support_ai_interactions.c.conversation_id
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

# Mission 13 authoritative dispatch storage. These tables intentionally do not
# reuse the unsafe legacy rides table above.
dispatch_ride_requests = Table(
    "dispatch_ride_requests",
    metadata,
    Column("ride_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "rider_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("pickup_place_id", String(128), nullable=False),
    Column("pickup_display_name", String(200), nullable=False),
    Column("destination_place_id", String(128), nullable=False),
    Column("destination_display_name", String(200), nullable=False),
    Column("service_type", String(40), nullable=False),
    Column("quote_id", UUID(as_uuid=True), nullable=False),
    Column("fare_amount_minor", Integer, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("pricing_version", String(63), nullable=False),
    Column("quote_expires_at", DateTime(timezone=True), nullable=False),
    Column("state", String(32), nullable=False),
    Column(
        "assigned_driver_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
    ),
    Column("active_offer_id", UUID(as_uuid=True)),
    Column(
        "attempted_driver_ids",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        server_default=text("'[]'::jsonb"),
    ),
    Column("accepted_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("search_expires_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    CheckConstraint("fare_amount_minor >= 0", name="dispatch_ride_nonnegative_fare"),
    CheckConstraint("currency ~ '^[A-Z]{3}$'", name="dispatch_ride_valid_currency"),
    CheckConstraint(
        "service_type ~ '^[a-z][a-z0-9_.-]{1,39}$'",
        name="dispatch_ride_valid_service_type",
    ),
    CheckConstraint("version > 0", name="dispatch_ride_positive_version"),
    CheckConstraint(
        "pickup_place_id <> destination_place_id", name="dispatch_ride_distinct_places"
    ),
    CheckConstraint(
        "state IN ('searching','offering','assigned','no_driver_available','rider_cancelled')",
        name="dispatch_ride_valid_state",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_dispatch_rides_rider_state",
    dispatch_ride_requests.c.rider_identity_id,
    dispatch_ride_requests.c.state,
)
Index(
    "ix_dispatch_rides_search_expiry",
    dispatch_ride_requests.c.search_expires_at,
    postgresql_where=dispatch_ride_requests.c.state.in_(["searching", "offering"]),
)
Index(
    "uq_dispatch_active_ride_per_rider",
    dispatch_ride_requests.c.rider_identity_id,
    unique=True,
    postgresql_where=dispatch_ride_requests.c.state.in_(
        ["searching", "offering", "assigned"]
    ),
)

dispatch_attempts = Table(
    "dispatch_attempts",
    metadata,
    Column("attempt_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.dispatch_ride_requests.ride_id"),
        nullable=False,
    ),
    Column(
        "driver_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("sequence_number", Integer, nullable=False),
    Column("pickup_eta_seconds", Integer, nullable=False),
    Column("policy_version", String(63), nullable=False),
    Column("reason_codes", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("outcome", String(24), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("resolved_at", DateTime(timezone=True)),
    CheckConstraint("sequence_number > 0", name="dispatch_attempt_positive_sequence"),
    CheckConstraint(
        "pickup_eta_seconds BETWEEN 0 AND 14400", name="dispatch_attempt_valid_eta"
    ),
    CheckConstraint(
        "outcome IN ('offered','accepted','declined','expired','revoked')",
        name="dispatch_attempt_valid_outcome",
    ),
    UniqueConstraint("ride_id", "sequence_number", name="uq_dispatch_attempts_ride_id"),
    UniqueConstraint(
        "ride_id",
        "driver_identity_id",
        name="uq_dispatch_attempts_ride_id_driver_identity_id",
    ),
    schema=AYO_SCHEMA,
)

dispatch_driver_offers = Table(
    "dispatch_driver_offers",
    metadata,
    Column("offer_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "attempt_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.dispatch_attempts.attempt_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.dispatch_ride_requests.ride_id"),
        nullable=False,
    ),
    Column(
        "driver_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("state", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("resolved_at", DateTime(timezone=True)),
    Column("policy_version", String(63), nullable=False),
    Column("score_snapshot", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    CheckConstraint("expires_at > created_at", name="dispatch_offer_valid_lifetime"),
    CheckConstraint(
        "state IN ('created','accepted','declined','expired','revoked')",
        name="dispatch_offer_valid_state",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_dispatch_offers_expiry",
    dispatch_driver_offers.c.expires_at,
    postgresql_where=dispatch_driver_offers.c.state == "created",
)
Index(
    "uq_dispatch_active_offer_per_ride",
    dispatch_driver_offers.c.ride_id,
    unique=True,
    postgresql_where=dispatch_driver_offers.c.state == "created",
)
Index(
    "uq_dispatch_active_offer_per_driver",
    dispatch_driver_offers.c.driver_identity_id,
    unique=True,
    postgresql_where=dispatch_driver_offers.c.state == "created",
)

dispatch_assignments = Table(
    "dispatch_assignments",
    metadata,
    Column("assignment_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.dispatch_ride_requests.ride_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "offer_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.dispatch_driver_offers.offer_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "driver_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("assigned_at", DateTime(timezone=True), nullable=False),
    Column("released_at", DateTime(timezone=True)),
    CheckConstraint(
        "released_at IS NULL OR released_at >= assigned_at",
        name="dispatch_assignment_valid_lifetime",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "uq_dispatch_active_assignment_per_driver",
    dispatch_assignments.c.driver_identity_id,
    unique=True,
    postgresql_where=dispatch_assignments.c.released_at.is_(None),
)

dispatch_idempotency_records = Table(
    "dispatch_idempotency_records",
    metadata,
    Column(
        "rider_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        primary_key=True,
    ),
    Column("key_fingerprint", String(64), primary_key=True),
    Column("request_hash", String(64), nullable=False),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.dispatch_ride_requests.ride_id"),
        nullable=False,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "expires_at > created_at", name="dispatch_idempotency_valid_lifetime"
    ),
    schema=AYO_SCHEMA,
)

dispatch_outbox = Table(
    "dispatch_outbox",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column("aggregate_type", String(32), nullable=False),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", String(63), nullable=False),
    Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("claimed_at", DateTime(timezone=True)),
    Column("claimed_by", String(64)),
    Column("published_at", DateTime(timezone=True)),
    Column("dead_lettered_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    Column("last_error_code", String(63)),
    CheckConstraint("attempt_count >= 0", name="dispatch_outbox_nonnegative_attempts"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_dispatch_outbox_pending",
    dispatch_outbox.c.available_at,
    dispatch_outbox.c.occurred_at,
    postgresql_where=(dispatch_outbox.c.published_at.is_(None))
    & (dispatch_outbox.c.dead_lettered_at.is_(None)),
)

marketplace_rule_sets = Table(
    "marketplace_rule_sets",
    metadata,
    Column("rule_set_id", UUID(as_uuid=True), primary_key=True),
    Column("version", String(63), nullable=False, unique=True),
    Column("configuration", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("configuration_checksum", String(64), nullable=False),
    Column("effective_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "version ~ '^[a-z][a-z0-9_.-]{1,62}$'", name="marketplace_rule_valid_version"
    ),
    CheckConstraint(
        "configuration_checksum ~ '^[a-f0-9]{64}$'",
        name="marketplace_rule_valid_checksum",
    ),
    schema=AYO_SCHEMA,
)

marketplace_decisions = Table(
    "marketplace_decisions",
    metadata,
    Column("decision_id", UUID(as_uuid=True), primary_key=True),
    Column("snapshot_id", UUID(as_uuid=True), nullable=False),
    Column(
        "rule_set_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.marketplace_rule_sets.rule_set_id"),
        nullable=False,
    ),
    Column("market_code", String(63), nullable=False),
    Column("zone_code", String(63), nullable=False),
    Column("service_type", String(63), nullable=False),
    Column("window_ended_at", DateTime(timezone=True), nullable=False),
    Column("recommendation", String(32), nullable=False),
    Column("health_score_bps", Integer, nullable=False),
    Column("explanation", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("generated_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "snapshot_id", "rule_set_id", name="uq_marketplace_decision_snapshot_rule"
    ),
    CheckConstraint(
        "health_score_bps BETWEEN 0 AND 10000",
        name="marketplace_decision_valid_health",
    ),
    CheckConstraint(
        "recommendation IN ('no_change','supply_guidance','incentive_review',"
        "'price_review','suppress','insufficient_data')",
        name="marketplace_decision_valid_recommendation",
    ),
    CheckConstraint("expires_at > generated_at", name="marketplace_decision_lifetime"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_marketplace_decisions_market_window",
    marketplace_decisions.c.market_code,
    marketplace_decisions.c.zone_code,
    marketplace_decisions.c.window_ended_at,
)

marketplace_simulation_runs = Table(
    "marketplace_simulation_runs",
    metadata,
    Column("run_id", UUID(as_uuid=True), primary_key=True),
    Column("baseline_rule_version", String(63), nullable=False),
    Column("candidate_rule_version", String(63), nullable=False),
    Column("dataset_checksum", String(64), nullable=False),
    Column("result", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "dataset_checksum ~ '^[a-f0-9]{64}$'",
        name="marketplace_simulation_valid_checksum",
    ),
    schema=AYO_SCHEMA,
)

# Mission 16 scheduled dispatch authority. Flexible decision evidence is JSONB,
# while lifecycle, identity references and concurrency constraints remain typed.
ride_reservations = Table(
    "ride_reservations",
    metadata,
    Column("reservation_id", UUID(as_uuid=True), primary_key=True),
    Column("booker_id", UUID(as_uuid=True), nullable=False),
    Column("passenger_participant_id", UUID(as_uuid=True), nullable=False),
    Column("pickup_place_id", String(128), nullable=False),
    Column("destination_place_id", String(128), nullable=False),
    Column("requested_pickup_at", DateTime(timezone=True), nullable=False),
    Column("requested_timezone", String(64), nullable=False),
    Column("service_type", String(63), nullable=False),
    Column("quote_id", UUID(as_uuid=True), nullable=False),
    Column("state", String(40), nullable=False),
    Column("policy_id", UUID(as_uuid=True), nullable=False),
    Column("policy_version", String(63), nullable=False),
    Column("airport_context_id", UUID(as_uuid=True)),
    Column("active_soft_plan_id", UUID(as_uuid=True)),
    Column("active_commitment_id", UUID(as_uuid=True)),
    Column("activated_ride_id", UUID(as_uuid=True)),
    Column("soft_replacement_count", Integer, nullable=False, server_default=text("0")),
    Column(
        "formal_replacement_count", Integer, nullable=False, server_default=text("0")
    ),
    Column("version", Integer, nullable=False, server_default=text("1")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "pickup_place_id <> destination_place_id", name="reservation_distinct_places"
    ),
    CheckConstraint("version > 0", name="reservation_positive_version"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_ride_reservations_due",
    ride_reservations.c.state,
    ride_reservations.c.requested_pickup_at,
)


def _reservation_child(name: str, id_name: str, *, append_only: bool = False) -> Table:
    columns = [
        Column(id_name, UUID(as_uuid=True), primary_key=True),
        Column(
            "reservation_id",
            UUID(as_uuid=True),
            ForeignKey("ayo.ride_reservations.reservation_id"),
            nullable=False,
        ),
        Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
    ]
    if not append_only:
        columns.append(
            Column("version", Integer, nullable=False, server_default=text("1"))
        )
    return Table(name, metadata, *columns, schema=AYO_SCHEMA)


reservation_participants = _reservation_child(
    "reservation_participants", "participant_id"
)
reservation_consents = _reservation_child(
    "reservation_consents", "consent_id", append_only=True
)
reservation_state_history = _reservation_child(
    "reservation_state_history", "history_id", append_only=True
)
reservation_planning_cycles = _reservation_child(
    "reservation_planning_cycles", "planning_cycle_id"
)
reservation_soft_plans = _reservation_child("reservation_soft_plans", "soft_plan_id")
reservation_attempts = _reservation_child(
    "reservation_attempts", "attempt_id", append_only=True
)
reservation_checkpoints = _reservation_child("reservation_checkpoints", "checkpoint_id")
reservation_flight_context = _reservation_child(
    "reservation_flight_context", "flight_context_id"
)
reservation_pickup_verifications = Table(
    "reservation_pickup_verifications",
    metadata,
    Column("verification_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "reservation_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.ride_reservations.reservation_id"),
        nullable=False,
        unique=True,
    ),
    Column("code_hash", LargeBinary, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    Column("verified_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "attempt_count BETWEEN 0 AND 10", name="pickup_verification_attempts"
    ),
    CheckConstraint("expires_at > created_at", name="pickup_verification_lifetime"),
    schema=AYO_SCHEMA,
)

reservation_driver_commitments = Table(
    "reservation_driver_commitments",
    metadata,
    Column("commitment_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "reservation_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.ride_reservations.reservation_id"),
        nullable=False,
    ),
    Column("driver_id", UUID(as_uuid=True), nullable=False),
    Column("state", String(32), nullable=False),
    Column("window_started_at", DateTime(timezone=True), nullable=False),
    Column("window_ended_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    ExcludeConstraint(
        ("driver_id", "="),
        (
            func.tstzrange(text("window_started_at"), text("window_ended_at"), "[)"),
            "&&",
        ),
        where=text("state = 'committed'"),
        using="gist",
        name="ex_reservation_driver_commitment_overlap",
    ),
    CheckConstraint(
        "window_ended_at > window_started_at", name="commitment_positive_window"
    ),
    schema=AYO_SCHEMA,
)

reservation_idempotency_records = Table(
    "reservation_idempotency_records",
    metadata,
    Column("actor_id", UUID(as_uuid=True), primary_key=True),
    Column("key_fingerprint", String(64), primary_key=True),
    Column("request_hash", String(64), nullable=False),
    Column(
        "reservation_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.ride_reservations.reservation_id"),
        nullable=False,
    ),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

active_rides = Table(
    "active_rides",
    metadata,
    Column("ride_id", UUID(as_uuid=True), primary_key=True),
    Column("rider_id", UUID(as_uuid=True), nullable=False),
    Column("driver_id", UUID(as_uuid=True)),
    Column("vehicle_id", UUID(as_uuid=True)),
    Column("reservation_id", UUID(as_uuid=True)),
    Column("assignment_id", UUID(as_uuid=True)),
    Column("ride_request_id", UUID(as_uuid=True)),
    Column("dispatch_handoff_id", UUID(as_uuid=True)),
    Column(
        "lifecycle_policy_version",
        String(63),
        nullable=False,
        server_default=text("'active_ride.v1'"),
    ),
    Column("source_assignment_version", Integer),
    Column("state", String(48), nullable=False),
    Column("pickup_place_id", String(128), nullable=False),
    Column("destination_place_id", String(128), nullable=False),
    Column("service_type", String(63), nullable=False),
    Column("driver_changed", Boolean, nullable=False, server_default=text("false")),
    Column("last_sequence", Integer, nullable=False, server_default=text("0")),
    Column("version", Integer, nullable=False, server_default=text("1")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "version > 0 AND last_sequence >= 0", name="active_ride_positive_versions"
    ),
    schema=AYO_SCHEMA,
)
Index("ix_active_rides_rider_state", active_rides.c.rider_id, active_rides.c.state)
Index("ix_active_rides_driver_state", active_rides.c.driver_id, active_rides.c.state)
Index(
    "uq_active_rides_immediate_assignment",
    active_rides.c.assignment_id,
    unique=True,
    postgresql_where=active_rides.c.dispatch_handoff_id.is_not(None),
)
Index(
    "uq_active_rides_ride_request",
    active_rides.c.ride_request_id,
    unique=True,
    postgresql_where=active_rides.c.ride_request_id.is_not(None),
)

active_ride_events = Table(
    "active_ride_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column("sequence", Integer, nullable=False),
    Column("aggregate_version", Integer, nullable=False),
    Column("event_type", String(63), nullable=False),
    Column("schema_version", Integer, nullable=False, server_default=text("1")),
    Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("ride_id", "sequence"),
    CheckConstraint(
        "sequence > 0 AND aggregate_version > 0", name="active_event_positive_versions"
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_active_ride_events_replay",
    active_ride_events.c.ride_id,
    active_ride_events.c.sequence,
)

active_ride_idempotency_records = Table(
    "active_ride_idempotency_records",
    metadata,
    Column("actor_id", UUID(as_uuid=True), primary_key=True),
    Column("command_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column("command_type", String(63), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("result_version", Integer, nullable=False),
    Column("result_status", String(24), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

active_ride_projection_checkpoints = Table(
    "active_ride_projection_checkpoints",
    metadata,
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        primary_key=True,
    ),
    Column("role", String(24), primary_key=True),
    Column("projection", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("aggregate_version", Integer, nullable=False),
    Column("last_sequence", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

active_ride_pickup_verifications = Table(
    "active_ride_pickup_verifications",
    metadata,
    Column("verification_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column("assignment_id", UUID(as_uuid=True), nullable=False),
    Column("secret_digest", LargeBinary, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    Column("maximum_attempts", Integer, nullable=False),
    Column("cooldown_until", DateTime(timezone=True)),
    Column("verified_at", DateTime(timezone=True)),
    Column("invalidated_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "attempt_count >= 0 AND maximum_attempts BETWEEN 1 AND 10",
        name="active_pickup_attempts_valid",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_active_pickup_verification_current",
    active_ride_pickup_verifications.c.ride_id,
    active_ride_pickup_verifications.c.created_at,
)

active_ride_evidence = Table(
    "active_ride_evidence",
    metadata,
    Column("evidence_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column("evidence_type", String(63), nullable=False),
    Column("submitted_by_role", String(24), nullable=False),
    Column("responsibility", String(32), nullable=False),
    Column("reason_code", String(63), nullable=False),
    Column(
        "evidence_references", JSONB().with_variant(JSON(), "sqlite"), nullable=False
    ),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

active_ride_confidence_decisions = Table(
    "active_ride_confidence_decisions",
    metadata,
    Column("confidence_decision_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column("rule_set_id", String(63), nullable=False),
    Column("rule_set_version", String(63), nullable=False),
    Column("health_level", String(32), nullable=False),
    Column("reason_codes", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("signal_freshness", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("data_quality_status", String(24), nullable=False),
    Column(
        "recommended_actions", JSONB().with_variant(JSON(), "sqlite"), nullable=False
    ),
    Column("generated_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_active_confidence_latest",
    active_ride_confidence_decisions.c.ride_id,
    active_ride_confidence_decisions.c.generated_at,
)

active_ride_pickup_recommendations = Table(
    "active_ride_pickup_recommendations",
    metadata,
    Column("recommendation_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("confidence", String(32), nullable=False),
    Column("material_change", Boolean, nullable=False),
    Column("change_status", String(24), nullable=False),
    Column("generated_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_active_pickup_recommendation_latest",
    active_ride_pickup_recommendations.c.ride_id,
    active_ride_pickup_recommendations.c.generated_at,
)

active_ride_recovery_checkpoints = Table(
    "active_ride_recovery_checkpoints",
    metadata,
    Column("checkpoint_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column("kind", String(63), nullable=False),
    Column("due_at", DateTime(timezone=True), nullable=False),
    Column("claimed_by", String(128)),
    Column("claimed_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_active_recovery_due",
    active_ride_recovery_checkpoints.c.kind,
    active_ride_recovery_checkpoints.c.due_at,
)

arrival_evaluations = Table(
    "arrival_evaluations",
    metadata,
    Column("evaluation_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column("assignment_id", UUID(as_uuid=True), nullable=False),
    Column("state", String(32), nullable=False),
    Column("confidence_bps", Integer, nullable=False),
    Column("observation_sequence", Integer, nullable=False),
    Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("evaluated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "confidence_bps BETWEEN 0 AND 10000", name="arrival_confidence_range"
    ),
    UniqueConstraint("ride_id", "observation_sequence"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_arrival_evaluations_latest",
    arrival_evaluations.c.ride_id,
    arrival_evaluations.c.evaluated_at,
)

rider_readiness_decisions = Table(
    "rider_readiness_decisions",
    metadata,
    Column("decision_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column("classification", String(32), nullable=False),
    Column("confidence_bps", Integer, nullable=False),
    Column("notification_recommended", Boolean, nullable=False),
    Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("evaluated_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "confidence_bps BETWEEN 0 AND 10000", name="readiness_confidence_range"
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_rider_readiness_latest",
    rider_readiness_decisions.c.ride_id,
    rider_readiness_decisions.c.evaluated_at,
)

waiting_policy_snapshots = Table(
    "waiting_policy_snapshots",
    metadata,
    Column("snapshot_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column("source_policy_id", UUID(as_uuid=True), nullable=False),
    Column("source_policy_version", String(63), nullable=False),
    Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("selected_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

waiting_sessions = Table(
    "waiting_sessions",
    metadata,
    Column("session_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column("assignment_id", UUID(as_uuid=True), nullable=False),
    Column(
        "policy_snapshot_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.waiting_policy_snapshots.snapshot_id"),
        nullable=False,
    ),
    Column("state", String(32), nullable=False),
    Column("version", Integer, nullable=False),
    Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("free_wait_deadline", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("version > 0", name="waiting_session_positive_version"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_waiting_session_ride_state",
    waiting_sessions.c.ride_id,
    waiting_sessions.c.state,
)

waiting_session_events = Table(
    "waiting_session_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "session_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.waiting_sessions.session_id"),
        nullable=False,
    ),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column("event_type", String(63), nullable=False),
    Column("session_version", Integer, nullable=False),
    Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("session_id", "session_version"),
    schema=AYO_SCHEMA,
)

arrival_notification_evidence = Table(
    "arrival_notification_evidence",
    metadata,
    Column("notification_evidence_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column("session_id", UUID(as_uuid=True), nullable=True),
    Column("intent_type", String(63), nullable=False),
    Column("delivery_status", String(32), nullable=False),
    Column("reason_code", String(63), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

consequence_suppression_decisions = Table(
    "consequence_suppression_decisions",
    metadata,
    Column("evidence_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column(
        "session_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.waiting_sessions.session_id"),
        nullable=False,
    ),
    Column("ready", Boolean, nullable=False),
    Column("responsibility", String(40), nullable=False),
    Column("confidence_bps", Integer, nullable=False),
    Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("evaluated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "confidence_bps BETWEEN 0 AND 10000", name="evidence_confidence_range"
    ),
    schema=AYO_SCHEMA,
)

arrival_waiting_idempotency = Table(
    "arrival_waiting_idempotency",
    metadata,
    Column("actor_id", UUID(as_uuid=True), primary_key=True),
    Column("command_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column("command_type", String(63), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

driver_onboarding_cases = Table(
    "driver_onboarding_cases",
    metadata,
    Column("case_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "driver_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("state", String(40), nullable=False),
    Column("policy_version", String(63), nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    Column(
        "appeal_of_case_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.driver_onboarding_cases.case_id"),
    ),
    CheckConstraint("version > 0", name="driver_onboarding_positive_version"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_driver_onboarding_owner_state",
    driver_onboarding_cases.c.driver_identity_id,
    driver_onboarding_cases.c.state,
)

driver_document_evidence = Table(
    "driver_document_evidence",
    metadata,
    Column("evidence_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "case_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.driver_onboarding_cases.case_id"),
        nullable=False,
    ),
    Column(
        "driver_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column(
        "vehicle_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.driver_vehicles.vehicle_id"),
    ),
    Column("evidence_type", String(40), nullable=False),
    Column("immutable_reference", String(256), nullable=False),
    Column("issuing_authority_code", String(63), nullable=False),
    Column("document_reference_hash", LargeBinary(32), nullable=False),
    Column("issue_date", Date(), nullable=False),
    Column("expiry_date", Date(), nullable=False),
    Column("status", String(24), nullable=False),
    Column("policy_version", String(63), nullable=False),
    Column(
        "reviewer_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
    ),
    Column("reason_codes", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column(
        "replaces_evidence_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.driver_document_evidence.evidence_id"),
    ),
    Column(
        "superseded_by_evidence_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.driver_document_evidence.evidence_id"),
    ),
    Column("submitted_at", DateTime(timezone=True), nullable=False),
    Column("reviewed_at", DateTime(timezone=True)),
    Column("version", Integer, nullable=False),
    UniqueConstraint("driver_identity_id", "document_reference_hash"),
    CheckConstraint("expiry_date > issue_date", name="driver_evidence_valid_period"),
    CheckConstraint("version > 0", name="driver_evidence_positive_version"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_driver_evidence_owner_type",
    driver_document_evidence.c.driver_identity_id,
    driver_document_evidence.c.evidence_type,
)

driver_vehicles = Table(
    "driver_vehicles",
    metadata,
    Column("vehicle_id", UUID(as_uuid=True), primary_key=True),
    Column("canonical_reference_hash", LargeBinary(32), nullable=False, unique=True),
    Column("category", String(63), nullable=False),
    Column(
        "accessibility_capabilities",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    ),
    Column(
        "airport_standard_inputs",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    ),
    Column(
        "airport_premium_inputs", JSONB().with_variant(JSON(), "sqlite"), nullable=False
    ),
    Column("approval_status", String(24), nullable=False),
    Column("policy_version", String(63), nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("version > 0", name="driver_vehicle_positive_version"),
    schema=AYO_SCHEMA,
)

driver_vehicle_authorizations = Table(
    "driver_vehicle_authorizations",
    metadata,
    Column("authorization_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "driver_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column(
        "vehicle_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.driver_vehicles.vehicle_id"),
        nullable=False,
    ),
    Column("status", String(24), nullable=False),
    Column("policy_version", String(63), nullable=False),
    Column("effective_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("reason_codes", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("version", Integer, nullable=False),
    CheckConstraint(
        "expires_at > effective_at", name="driver_vehicle_authorization_valid_period"
    ),
    CheckConstraint(
        "version > 0", name="driver_vehicle_authorization_positive_version"
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_driver_vehicle_authorization_current",
    driver_vehicle_authorizations.c.driver_identity_id,
    driver_vehicle_authorizations.c.vehicle_id,
    unique=True,
    postgresql_where=driver_vehicle_authorizations.c.status == "authorized",
)

driver_eligibility_decisions = Table(
    "driver_eligibility_decisions",
    metadata,
    Column("decision_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "driver_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column(
        "vehicle_id", UUID(as_uuid=True), ForeignKey("ayo.driver_vehicles.vehicle_id")
    ),
    Column("policy_version", String(63), nullable=False),
    Column("status", String(32), nullable=False),
    Column("reason_codes", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("missing_evidence", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    Column("recomputed_at", DateTime(timezone=True), nullable=False),
    Column("audit_reference", UUID(as_uuid=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_driver_eligibility_latest",
    driver_eligibility_decisions.c.driver_identity_id,
    driver_eligibility_decisions.c.recomputed_at,
)

driver_trust_idempotency = Table(
    "driver_trust_idempotency",
    metadata,
    Column("actor_identity_id", UUID(as_uuid=True), primary_key=True),
    Column("idempotency_key", String(128), primary_key=True),
    Column("operation", String(63), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_reference", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

driver_trust_events = Table(
    "driver_trust_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("aggregate_type", String(40), nullable=False),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("aggregate_version", Integer, nullable=False),
    Column("event_type", String(63), nullable=False),
    Column("actor_identity_id", UUID(as_uuid=True)),
    Column("reason_codes", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("aggregate_type", "aggregate_id", "aggregate_version"),
    schema=AYO_SCHEMA,
)

driver_trust_outbox = Table(
    "driver_trust_outbox",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("event_type", String(63), nullable=False),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    CheckConstraint(
        "attempt_count >= 0", name="driver_trust_outbox_nonnegative_attempts"
    ),
    schema=AYO_SCHEMA,
)

service_zones = Table(
    "service_zones",
    metadata,
    Column("zone_id", UUID(as_uuid=True), primary_key=True),
    Column("code", String(63), nullable=False),
    Column("version", String(63), nullable=False),
    Column("min_latitude", Float, nullable=False),
    Column("max_latitude", Float, nullable=False),
    Column("min_longitude", Float, nullable=False),
    Column("max_longitude", Float, nullable=False),
    Column(
        "prohibited_rectangles", JSONB().with_variant(JSON(), "sqlite"), nullable=False
    ),
    Column(
        "supported_service_types",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    ),
    Column("active_from", DateTime(timezone=True), nullable=False),
    Column("active_until", DateTime(timezone=True)),
    Column("policy_version", String(63), nullable=False),
    UniqueConstraint("code", "version"),
    CheckConstraint(
        "min_latitude < max_latitude AND min_longitude < max_longitude",
        name="service_zone_positive_area",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_service_zones_active", service_zones.c.active_from, service_zones.c.active_until
)

canonical_pickups = Table(
    "canonical_pickups",
    metadata,
    Column("pickup_id", UUID(as_uuid=True), primary_key=True),
    Column("latitude", Float, nullable=False),
    Column("longitude", Float, nullable=False),
    Column("source", String(32), nullable=False),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Column("accuracy_metres", Float),
    Column("structured_address", String(512)),
    Column("landmark_reference", String(128)),
    Column("note", String(280)),
    Column("map_confidence_bps", Integer, nullable=False),
    Column("entrance_reference", String(128)),
    Column("exact_stop_reference", String(128)),
    Column("airport_terminal_reference", String(128)),
    Column("airport_zone_reference", String(128)),
    Column("reference_photo_metadata_reference", String(128)),
    Column("safety_status", String(24), nullable=False),
    Column("policy_version", String(63), nullable=False),
    CheckConstraint(
        "latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180",
        name="canonical_pickup_coordinates",
    ),
    CheckConstraint(
        "map_confidence_bps BETWEEN 0 AND 10000", name="canonical_pickup_confidence"
    ),
    schema=AYO_SCHEMA,
)

canonical_destinations = Table(
    "canonical_destinations",
    metadata,
    Column("destination_id", UUID(as_uuid=True), primary_key=True),
    Column("latitude", Float, nullable=False),
    Column("longitude", Float, nullable=False),
    Column("source", String(32), nullable=False),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Column("accuracy_metres", Float),
    Column("structured_address", String(512)),
    Column("landmark_reference", String(128)),
    Column("note", String(280)),
    Column("map_confidence_bps", Integer, nullable=False),
    CheckConstraint(
        "latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180",
        name="canonical_destination_coordinates",
    ),
    schema=AYO_SCHEMA,
)

canonical_ride_requests = Table(
    "canonical_ride_requests",
    metadata,
    Column("request_id", UUID(as_uuid=True), primary_key=True),
    Column("client_request_id", UUID(as_uuid=True), nullable=False),
    Column(
        "rider_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("state", String(32), nullable=False),
    Column("service_type", String(32), nullable=False),
    Column("payment_intent", String(32), nullable=False),
    Column(
        "pickup_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_pickups.pickup_id"),
        nullable=False,
    ),
    Column(
        "destination_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_destinations.destination_id"),
        nullable=False,
    ),
    Column(
        "service_zone_id", UUID(as_uuid=True), ForeignKey("ayo.service_zones.zone_id")
    ),
    Column("consent_policy_version", String(63), nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("cancellation_reason", String(63)),
    UniqueConstraint("rider_identity_id", "client_request_id"),
    CheckConstraint("version > 0", name="canonical_ride_request_positive_version"),
    CheckConstraint(
        "service_type = 'immediate_standard'",
        name="canonical_ride_request_supported_type",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_canonical_ride_request_owner_state",
    canonical_ride_requests.c.rider_identity_id,
    canonical_ride_requests.c.state,
)

ride_request_validation_decisions = Table(
    "ride_request_validation_decisions",
    metadata,
    Column("decision_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "request_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_ride_requests.request_id"),
        nullable=False,
    ),
    Column("policy_version", String(63), nullable=False),
    Column("zone_id", UUID(as_uuid=True)),
    Column("zone_version", String(63)),
    Column("status", String(24), nullable=False),
    Column("reason_codes", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("invalid_fields", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("evidence_freshness_seconds", Integer),
    Column("audit_reference", UUID(as_uuid=True), nullable=False),
    Column("decided_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

ride_request_idempotency = Table(
    "ride_request_idempotency",
    metadata,
    Column("rider_identity_id", UUID(as_uuid=True), primary_key=True),
    Column("operation", String(32), primary_key=True),
    Column("idempotency_key", String(128), primary_key=True),
    Column("request_hash", String(64), nullable=False),
    Column("response_reference", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

ride_request_events = Table(
    "ride_request_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "request_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_ride_requests.request_id"),
        nullable=False,
    ),
    Column("request_version", Integer, nullable=False),
    Column("event_type", String(63), nullable=False),
    Column("safe_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("request_id", "request_version", "event_type"),
    schema=AYO_SCHEMA,
)

ride_request_outbox = Table(
    "ride_request_outbox",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("event_type", String(63), nullable=False),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("aggregate_version", Integer, nullable=False),
    Column("safe_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    CheckConstraint(
        "attempt_count >= 0", name="ride_request_outbox_nonnegative_attempts"
    ),
    schema=AYO_SCHEMA,
)

immediate_dispatch_handoffs = Table(
    "immediate_dispatch_handoffs",
    metadata,
    Column("handoff_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_request_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_ride_requests.request_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "rider_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("service_type", String(32), nullable=False),
    Column("pickup_reference", UUID(as_uuid=True), nullable=False),
    Column("destination_reference", UUID(as_uuid=True), nullable=False),
    Column("service_zone_id", UUID(as_uuid=True), nullable=False),
    Column("service_zone_version", String(63), nullable=False),
    Column("validation_decision_id", UUID(as_uuid=True), nullable=False),
    Column("ride_request_version", Integer, nullable=False),
    Column("ride_policy_version", String(63), nullable=False),
    Column("dispatch_policy_version", String(63), nullable=False),
    Column("state", String(24), nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    Column("idempotency_identity", String(128), nullable=False),
    Column("audit_reference", UUID(as_uuid=True), nullable=False),
    Column("assigned_driver_id", UUID(as_uuid=True)),
    CheckConstraint(
        "service_type='immediate_standard'", name="handoff_immediate_standard_only"
    ),
    CheckConstraint("version>0", name="handoff_positive_version"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_immediate_handoff_state_expiry",
    immediate_dispatch_handoffs.c.state,
    immediate_dispatch_handoffs.c.expires_at,
)

immediate_dispatch_candidate_sets = Table(
    "immediate_dispatch_candidate_sets",
    metadata,
    Column("candidate_set_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "handoff_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.immediate_dispatch_handoffs.handoff_id"),
        nullable=False,
    ),
    Column("policy_version", String(63), nullable=False),
    Column("candidate_count", Integer, nullable=False),
    Column(
        "eligible_driver_ids", JSONB().with_variant(JSON(), "sqlite"), nullable=False
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

immediate_dispatch_offers = Table(
    "immediate_dispatch_offers",
    metadata,
    Column("offer_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "handoff_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.immediate_dispatch_handoffs.handoff_id"),
        nullable=False,
    ),
    Column("driver_id", UUID(as_uuid=True), nullable=False),
    Column("vehicle_id", UUID(as_uuid=True), nullable=False),
    Column("state", String(24), nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("resolved_at", DateTime(timezone=True)),
    Column("dispatch_policy_version", String(63), nullable=False),
    Column("pickup_cost_seconds", Integer, nullable=False),
    CheckConstraint("version>0", name="immediate_offer_positive_version"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_immediate_offer_active_handoff",
    immediate_dispatch_offers.c.handoff_id,
    unique=True,
    postgresql_where=immediate_dispatch_offers.c.state == "created",
)
Index(
    "ix_immediate_offer_active_driver",
    immediate_dispatch_offers.c.driver_id,
    unique=True,
    postgresql_where=immediate_dispatch_offers.c.state == "created",
)

immediate_dispatch_assignments = Table(
    "immediate_dispatch_assignments",
    metadata,
    Column("assignment_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "handoff_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.immediate_dispatch_handoffs.handoff_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "offer_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.immediate_dispatch_offers.offer_id"),
        nullable=False,
        unique=True,
    ),
    Column("driver_id", UUID(as_uuid=True), nullable=False),
    Column("vehicle_id", UUID(as_uuid=True), nullable=False),
    Column("assigned_at", DateTime(timezone=True), nullable=False),
    Column("released_at", DateTime(timezone=True)),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_immediate_assignment_active_driver",
    immediate_dispatch_assignments.c.driver_id,
    unique=True,
    postgresql_where=immediate_dispatch_assignments.c.released_at.is_(None),
)

immediate_dispatch_idempotency = Table(
    "immediate_dispatch_idempotency",
    metadata,
    Column("actor_id", UUID(as_uuid=True), primary_key=True),
    Column("operation", String(32), primary_key=True),
    Column("key", String(128), primary_key=True),
    Column("request_hash", String(64), nullable=False),
    Column("response_reference", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
immediate_dispatch_events = Table(
    "immediate_dispatch_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "handoff_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.immediate_dispatch_handoffs.handoff_id"),
        nullable=False,
    ),
    Column("event_type", String(63), nullable=False),
    Column("aggregate_version", Integer, nullable=False),
    Column("safe_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("handoff_id", "event_type", "aggregate_version"),
    schema=AYO_SCHEMA,
)
immediate_dispatch_outbox = Table(
    "immediate_dispatch_outbox",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("event_type", String(63), nullable=False),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("aggregate_version", Integer, nullable=False),
    Column("safe_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    schema=AYO_SCHEMA,
)

localization_preferences = Table(
    "localization_preferences",
    metadata,
    Column("preference_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
        unique=True,
    ),
    Column("preferred_language", String(63), nullable=False),
    Column("device_language", String(63)),
    Column("fallback_chain", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("version", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("version>0", name="localization_preference_positive_version"),
    schema=AYO_SCHEMA,
)
localization_pack_manifests = Table(
    "localization_pack_manifests",
    metadata,
    Column("language_tag", String(63), primary_key=True),
    Column("pack_version", String(63), primary_key=True),
    Column("direction", String(3), nullable=False),
    Column("fallback_language", String(63)),
    Column("offline_manifest_reference", String(256)),
    Column("date_format_profile", String(63), nullable=False),
    Column("number_format_profile", String(63), nullable=False),
    Column("currency_format_profile", String(63), nullable=False),
    Column("approved_at", DateTime(timezone=True)),
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

pricing_policies = Table(
    "pricing_policies",
    metadata,
    Column("policy_id", UUID(as_uuid=True), primary_key=True),
    Column("policy_version", String(63), nullable=False, unique=True),
    Column("predecessor_policy_id", UUID(as_uuid=True)),
    Column("service_zone_id", UUID(as_uuid=True), nullable=False),
    Column("service_type", String(32), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("base_fare_minor", BigInteger, nullable=False),
    Column("distance_rate_per_km_minor", BigInteger, nullable=False),
    Column("time_rate_per_minute_minor", BigInteger, nullable=False),
    Column("minimum_fare_minor", BigInteger, nullable=False),
    Column("commission_basis_points", Integer, nullable=False),
    Column("tax_placeholder_basis_points", Integer, nullable=False),
    Column("rounding_increment_minor", Integer, nullable=False),
    Column("effective_from", DateTime(timezone=True), nullable=False),
    Column("effective_until", DateTime(timezone=True)),
    Column("status", String(24), nullable=False),
    Column("made_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("approved_by_identity_id", UUID(as_uuid=True)),
    Column("approved_at", DateTime(timezone=True)),
    Column("published_at", DateTime(timezone=True)),
    Column("published_by_identity_id", UUID(as_uuid=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "service_type='immediate_standard' AND currency='ETB'",
        name="pricing_policy_pilot_boundary",
    ),
    CheckConstraint(
        "base_fare_minor>=0 AND distance_rate_per_km_minor>=0 AND "
        "time_rate_per_minute_minor>=0 AND minimum_fare_minor>=base_fare_minor",
        name="pricing_policy_nonnegative_money",
    ),
    CheckConstraint(
        "commission_basis_points BETWEEN 0 AND 10000 AND "
        "tax_placeholder_basis_points BETWEEN 0 AND 10000",
        name="pricing_policy_bounded_rates",
    ),
    CheckConstraint(
        "approved_by_identity_id IS NULL OR approved_by_identity_id<>made_by_identity_id",
        name="pricing_policy_maker_checker",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_pricing_policy_lookup",
    pricing_policies.c.service_zone_id,
    pricing_policies.c.service_type,
    pricing_policies.c.status,
    pricing_policies.c.effective_from,
)

fare_estimates = Table(
    "fare_estimates",
    metadata,
    Column("estimate_id", UUID(as_uuid=True), primary_key=True),
    Column("ride_request_id", UUID(as_uuid=True), nullable=False),
    Column("rider_identity_id", UUID(as_uuid=True), nullable=False),
    Column(
        "policy_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.pricing_policies.policy_id"),
        nullable=False,
    ),
    Column("policy_version", String(63), nullable=False),
    Column("service_zone_id", UUID(as_uuid=True), nullable=False),
    Column("service_type", String(32), nullable=False),
    Column("metrics", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("breakdown", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column(
        "financial_traceability", JSONB().with_variant(JSON(), "sqlite"), nullable=False
    ),
    Column(
        "calculation_lineage", JSONB().with_variant(JSON(), "sqlite"), nullable=False
    ),
    Column("state", String(32), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("reason_codes", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("translation_keys", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("audit_reference", UUID(as_uuid=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_fare_estimate_owner",
    fare_estimates.c.rider_identity_id,
    fare_estimates.c.created_at,
)

fare_estimate_acceptances = Table(
    "fare_estimate_acceptances",
    metadata,
    Column("acceptance_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "estimate_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.fare_estimates.estimate_id"),
        nullable=False,
        unique=True,
    ),
    Column("rider_identity_id", UUID(as_uuid=True), nullable=False),
    Column("accepted_policy_version", String(63), nullable=False),
    Column("accepted_amount_minor", BigInteger, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("accepted_at", DateTime(timezone=True), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("audit_reference", UUID(as_uuid=True), nullable=False),
    CheckConstraint(
        "accepted_amount_minor>=0 AND currency='ETB'",
        name="estimate_acceptance_etb_nonnegative",
    ),
    UniqueConstraint("rider_identity_id", "idempotency_key"),
    schema=AYO_SCHEMA,
)

fare_calculations = Table(
    "fare_calculations",
    metadata,
    Column("calculation_id", UUID(as_uuid=True), primary_key=True),
    Column("estimate_id", UUID(as_uuid=True), nullable=False),
    Column("acceptance_id", UUID(as_uuid=True), nullable=False),
    Column("ride_id", UUID(as_uuid=True), nullable=False),
    Column("rider_identity_id", UUID(as_uuid=True), nullable=False),
    Column("driver_identity_id", UUID(as_uuid=True), nullable=False),
    Column("policy_id", UUID(as_uuid=True), nullable=False),
    Column("policy_version", String(63), nullable=False),
    Column("state", String(40), nullable=False),
    Column("metrics", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("breakdown", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column(
        "financial_traceability", JSONB().with_variant(JSON(), "sqlite"), nullable=False
    ),
    Column(
        "calculation_lineage", JSONB().with_variant(JSON(), "sqlite"), nullable=False
    ),
    Column("estimate_difference_minor", BigInteger, nullable=False),
    Column("predecessor_calculation_id", UUID(as_uuid=True)),
    Column("reason_codes", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("translation_keys", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("audit_reference", UUID(as_uuid=True), nullable=False),
    Column("calculated_at", DateTime(timezone=True), nullable=False),
    Column(
        "settlement_instruction_ready",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_fare_calculation_ride",
    fare_calculations.c.ride_id,
    fare_calculations.c.calculated_at,
)
Index(
    "uq_fare_calculation_original",
    fare_calculations.c.ride_id,
    unique=True,
    postgresql_where=fare_calculations.c.predecessor_calculation_id.is_(None),
)

pricing_calculation_components = Table(
    "pricing_calculation_components",
    metadata,
    Column("component_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "calculation_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.fare_calculations.calculation_id"),
        nullable=False,
    ),
    Column("component_type", String(40), nullable=False),
    Column("amount_minor", BigInteger, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("policy_version", String(63), nullable=False),
    CheckConstraint(
        "amount_minor>=0 AND currency='ETB'", name="pricing_component_etb_nonnegative"
    ),
    UniqueConstraint("calculation_id", "component_type"),
    schema=AYO_SCHEMA,
)

pricing_idempotency = Table(
    "pricing_idempotency",
    metadata,
    Column("actor_id", UUID(as_uuid=True), primary_key=True),
    Column("operation", String(40), primary_key=True),
    Column("idempotency_key", String(128), primary_key=True),
    Column("request_hash", String(64), nullable=False),
    Column("response_reference", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

pricing_events = Table(
    "pricing_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("aggregate_type", String(32), nullable=False),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", String(63), nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("safe_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    schema=AYO_SCHEMA,
)

pricing_outbox = Table(
    "pricing_outbox",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column("event_id", UUID(as_uuid=True), nullable=False, unique=True),
    Column("event_type", String(63), nullable=False),
    Column("safe_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    schema=AYO_SCHEMA,
)

ledger_books = Table(
    "ledger_books",
    metadata,
    Column("book_id", UUID(as_uuid=True), primary_key=True),
    Column("code", String(63), nullable=False, unique=True),
    Column("description", String(240), nullable=False),
    Column("base_currency", String(3), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("archived_at", DateTime(timezone=True)),
    CheckConstraint("base_currency ~ '^[A-Z]{3}$'", name="ledger_book_currency_code"),
    schema=AYO_SCHEMA,
)

ledger_accounts = Table(
    "ledger_accounts",
    metadata,
    Column("account_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "book_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.ledger_books.book_id"),
        nullable=False,
    ),
    Column("code", String(63), nullable=False),
    Column("name", String(160), nullable=False),
    Column("account_class", String(24), nullable=False),
    Column("normal_side", String(8), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("archived_at", DateTime(timezone=True)),
    CheckConstraint(
        "account_class IN ('asset','liability','revenue','expense','equity','clearing')",
        name="ledger_account_class_allowed",
    ),
    CheckConstraint(
        "normal_side IN ('debit','credit')",
        name="ledger_account_normal_side_allowed",
    ),
    CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ledger_account_currency_code"),
    UniqueConstraint("book_id", "code", name="uq_ledger_account_code_per_book"),
    schema=AYO_SCHEMA,
)
Index("ix_ledger_account_book", ledger_accounts.c.book_id, ledger_accounts.c.code)

ledger_journals = Table(
    "ledger_journals",
    metadata,
    Column("journal_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "book_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.ledger_books.book_id"),
        nullable=False,
    ),
    Column("business_event_type", String(63), nullable=False),
    Column("business_event_id", UUID(as_uuid=True), nullable=False),
    Column("operation", String(63), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("source_system", String(63), nullable=False),
    Column("reason_code", String(63), nullable=False),
    Column(
        "traceability",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    ),
    Column(
        "predecessor_ledger_journal_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.ledger_journals.journal_id"),
    ),
    Column("effective_at", DateTime(timezone=True), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    Column("audit_reference", UUID(as_uuid=True), nullable=False),
    UniqueConstraint(
        "business_event_type",
        "business_event_id",
        "operation",
        "idempotency_key",
        name="uq_ledger_business_event_operation",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_ledger_journal_event",
    ledger_journals.c.business_event_type,
    ledger_journals.c.business_event_id,
)
Index(
    "ix_ledger_journal_book_time",
    ledger_journals.c.book_id,
    ledger_journals.c.recorded_at,
)

ledger_entries = Table(
    "ledger_entries",
    metadata,
    Column("entry_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "journal_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.ledger_journals.journal_id"),
        nullable=False,
    ),
    Column(
        "account_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.ledger_accounts.account_id"),
        nullable=False,
    ),
    Column("side", String(8), nullable=False),
    Column("amount_minor", BigInteger, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("line_index", Integer, nullable=False),
    Column("predecessor_entry_id", UUID(as_uuid=True)),
    CheckConstraint("side IN ('debit','credit')", name="ledger_entry_side_allowed"),
    CheckConstraint("amount_minor > 0", name="ledger_entry_positive_amount"),
    CheckConstraint("line_index >= 1", name="ledger_entry_line_index_positive"),
    CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ledger_entry_currency_code"),
    UniqueConstraint("journal_id", "line_index", name="uq_ledger_entry_line_index"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_ledger_entries_account", ledger_entries.c.account_id, ledger_entries.c.currency
)
Index(
    "ix_ledger_entries_journal",
    ledger_entries.c.journal_id,
    ledger_entries.c.line_index,
)

ledger_idempotency = Table(
    "ledger_idempotency",
    metadata,
    Column("actor_id", UUID(as_uuid=True), primary_key=True),
    Column("operation", String(63), primary_key=True),
    Column("idempotency_key", String(128), primary_key=True),
    Column("request_hash", String(64), nullable=False),
    Column("response_reference", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

ledger_events = Table(
    "ledger_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("aggregate_type", String(32), nullable=False),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", String(63), nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("safe_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("replay_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    schema=AYO_SCHEMA,
)

ledger_outbox = Table(
    "ledger_outbox",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column("event_id", UUID(as_uuid=True), nullable=False, unique=True),
    Column("event_type", String(63), nullable=False),
    Column("safe_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    CheckConstraint("attempt_count >= 0", name="ledger_outbox_nonnegative_attempts"),
    schema=AYO_SCHEMA,
)
