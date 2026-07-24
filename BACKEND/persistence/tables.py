from geoalchemy2 import Geometry
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
    ForeignKeyConstraint,
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

canonical_subjects = Table(
    "canonical_subjects",
    metadata,
    Column("subject_id", UUID(as_uuid=True), primary_key=True),
    Column("subject_kind", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    CheckConstraint(
        "subject_kind IN ('human','service','other')", name="valid_subject_kind"
    ),
    CheckConstraint("version > 0", name="positive_version"),
    schema=AYO_SCHEMA,
)

identity_accounts = Table(
    "identity_accounts",
    metadata,
    Column("account_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "subject_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_subjects.subject_id"),
        nullable=False,
    ),
    Column("state", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    Column("failed_attempt_count", Integer, nullable=False, server_default=text("0")),
    Column("last_failed_at", DateTime(timezone=True)),
    Column("failed_window_started_at", DateTime(timezone=True)),
    Column(
        "credential_change_required",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
    Column("credential_change_reason", String(63)),
    Column("credential_change_provenance", String(63)),
    UniqueConstraint("subject_id"),
    UniqueConstraint("account_id", "subject_id"),
    CheckConstraint(
        "state IN ('pending_activation','active','locked','suspended','closed')",
        name="valid_state",
    ),
    CheckConstraint("version > 0", name="positive_version"),
    CheckConstraint("failed_attempt_count >= 0", name="nonnegative_failed_attempts"),
    schema=AYO_SCHEMA,
)
Index("ix_identity_accounts_state", identity_accounts.c.state)

customer_profiles = Table(
    "customer_profiles",
    metadata,
    Column("profile_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "subject_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_subjects.subject_id"),
        nullable=False,
        unique=True,
    ),
    Column("state", String(16), nullable=False),
    Column("display_name", String(120), nullable=False),
    Column("preferred_name", String(120)),
    Column("language", String(35), nullable=False),
    Column("region", String(63), nullable=False),
    Column("timezone", String(63), nullable=False),
    Column("service_area_preference", String(80)),
    Column("profile_image_reference", String(200)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    CheckConstraint(
        "state IN ('active','suspended','closed')", name="valid_profile_state"
    ),
    CheckConstraint("version > 0", name="positive_profile_version"),
    schema=AYO_SCHEMA,
)

customer_household_relationships = Table(
    "customer_household_relationships",
    metadata,
    Column("relationship_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "inviting_subject_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_subjects.subject_id"),
        nullable=False,
    ),
    Column(
        "invited_subject_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_subjects.subject_id"),
        nullable=False,
    ),
    Column("relationship_type", String(24), nullable=False),
    Column("state", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    UniqueConstraint(
        "inviting_subject_id",
        "invited_subject_id",
        name="uq_customer_household_direction",
    ),
    CheckConstraint(
        "inviting_subject_id <> invited_subject_id", name="different_household_subjects"
    ),
    CheckConstraint(
        "relationship_type IN ('family_member','trusted_friend','caregiver','other')",
        name="valid_household_type",
    ),
    CheckConstraint(
        "state IN ('pending','active','suspended','removed')",
        name="valid_household_state",
    ),
    CheckConstraint("version > 0", name="positive_household_version"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_customer_household_invited_state",
    customer_household_relationships.c.invited_subject_id,
    customer_household_relationships.c.state,
)

customer_emergency_contacts = Table(
    "customer_emergency_contacts",
    metadata,
    Column("contact_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "subject_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_subjects.subject_id"),
        nullable=False,
    ),
    Column(
        "contact_subject_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_subjects.subject_id"),
    ),
    Column("display_name", String(120), nullable=False),
    Column("channel_reference", String(200), nullable=False),
    Column("priority", Integer, nullable=False),
    Column("active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    UniqueConstraint("subject_id", "priority", name="uq_customer_emergency_priority"),
    CheckConstraint("priority BETWEEN 1 AND 20", name="valid_emergency_priority"),
    CheckConstraint("version > 0", name="positive_emergency_version"),
    schema=AYO_SCHEMA,
)

identity_security_bootstrap = Table(
    "identity_security_bootstrap",
    metadata,
    Column("bootstrap_key", String(32), primary_key=True),
    Column(
        "target_account_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identity_accounts.account_id"),
        nullable=False,
    ),
    Column("assignment_id", UUID(as_uuid=True), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=False),
    Column("reason", String(63), nullable=False),
    Column("command_id", UUID(as_uuid=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    CheckConstraint(
        "bootstrap_key = 'first_platform_administrator'", name="singleton_key"
    ),
    schema=AYO_SCHEMA,
)

account_recovery_tokens = Table(
    "account_recovery_tokens",
    metadata,
    Column("token_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "account_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identity_accounts.account_id"),
        nullable=False,
    ),
    Column("purpose", String(32), nullable=False),
    Column("token_version", Integer, nullable=False),
    Column("token_hash", LargeBinary(32), nullable=False),
    Column("state", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("consumed_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
    Column("superseded_at", DateTime(timezone=True)),
    Column("version", Integer, nullable=False, server_default=text("1")),
    UniqueConstraint("token_hash"),
    UniqueConstraint("account_id", "purpose", "token_version"),
    CheckConstraint("purpose = 'password_recovery'", name="valid_purpose"),
    CheckConstraint(
        "state IN ('active','consumed','revoked','superseded')", name="valid_state"
    ),
    CheckConstraint("expires_at > created_at", name="valid_lifetime"),
    CheckConstraint("token_version > 0 AND version > 0", name="positive_versions"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_account_recovery_tokens_active",
    account_recovery_tokens.c.account_id,
    account_recovery_tokens.c.purpose,
    unique=True,
    postgresql_where=text("state = 'active'"),
)

authentication_origin_windows = Table(
    "authentication_origin_windows",
    metadata,
    Column("origin_hash", LargeBinary(32), primary_key=True),
    Column("window_started_at", DateTime(timezone=True), nullable=False),
    Column("attempt_count", Integer, nullable=False),
    Column("throttled_at", DateTime(timezone=True)),
    Column("version", Integer, nullable=False, server_default=text("1")),
    CheckConstraint("attempt_count > 0 AND version > 0", name="positive_counts"),
    schema=AYO_SCHEMA,
)

account_password_credentials = Table(
    "account_password_credentials",
    metadata,
    Column("credential_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "account_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identity_accounts.account_id"),
        nullable=False,
    ),
    Column("credential_version", Integer, nullable=False),
    Column("scheme", String(32), nullable=False),
    Column("verifier", String(512), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("superseded_at", DateTime(timezone=True)),
    UniqueConstraint("account_id", "credential_version"),
    CheckConstraint("credential_version > 0", name="positive_credential_version"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_account_password_credentials_active",
    account_password_credentials.c.account_id,
    unique=True,
    postgresql_where=account_password_credentials.c.superseded_at.is_(None),
)

account_sessions = Table(
    "account_sessions",
    metadata,
    Column("session_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "account_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identity_accounts.account_id"),
        nullable=False,
    ),
    Column("client_reference", String(128)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_used_at", DateTime(timezone=True), nullable=False),
    Column("absolute_expires_at", DateTime(timezone=True), nullable=False),
    Column("inactivity_seconds", Integer, nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    Column("revocation_reason", String(63)),
    Column("rotated_from_session_id", UUID(as_uuid=True)),
    Column("version", Integer, nullable=False, server_default=text("1")),
    CheckConstraint("inactivity_seconds > 0", name="positive_inactivity_seconds"),
    CheckConstraint("absolute_expires_at > created_at", name="valid_absolute_lifetime"),
    CheckConstraint("version > 0", name="positive_version"),
    CheckConstraint(
        "(revoked_at IS NULL AND revocation_reason IS NULL) OR "
        "(revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)",
        name="consistent_revocation",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_account_sessions_account_active",
    account_sessions.c.account_id,
    account_sessions.c.revoked_at,
)

account_role_assignments = Table(
    "account_role_assignments",
    metadata,
    Column("assignment_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "account_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identity_accounts.account_id"),
        nullable=False,
    ),
    Column(
        "role_id", UUID(as_uuid=True), ForeignKey("ayo.roles.role_id"), nullable=False
    ),
    Column(
        "assigned_by_account_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identity_accounts.account_id"),
        nullable=False,
    ),
    Column("assigned_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    Column("revoked_by_account_id", UUID(as_uuid=True)),
    Column("revocation_reason", String(63)),
    Column("version", Integer, nullable=False, server_default=text("1")),
    CheckConstraint("version > 0", name="positive_version"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_account_role_assignments_active",
    account_role_assignments.c.account_id,
    account_role_assignments.c.role_id,
    unique=True,
    postgresql_where=account_role_assignments.c.revoked_at.is_(None),
)

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

legacy_identity_mappings = Table(
    "legacy_identity_mappings",
    metadata,
    Column("mapping_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "legacy_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column(
        "subject_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_subjects.subject_id"),
        nullable=False,
    ),
    Column(
        "account_id",
        UUID(as_uuid=True),
    ),
    Column("semantic", String(40), nullable=False),
    Column("mapping_state", String(24), nullable=False),
    Column("provenance", String(63), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    UniqueConstraint("legacy_identity_id"),
    UniqueConstraint("subject_id"),
    UniqueConstraint("account_id"),
    ForeignKeyConstraint(
        ["account_id", "subject_id"],
        ["ayo.identity_accounts.account_id", "ayo.identity_accounts.subject_id"],
    ),
    CheckConstraint(
        "semantic IN ('canonical_subject','account','business_participant',"
        "'authentication_actor','authorization_principal','resource_owner',"
        "'audit_actor','ambiguous_legacy_reference')",
        name="valid_semantic",
    ),
    CheckConstraint(
        "mapping_state IN ('subject_mapped','account_mapped','ambiguous')",
        name="valid_mapping_state",
    ),
    CheckConstraint(
        "(mapping_state = 'account_mapped' AND account_id IS NOT NULL) OR "
        "(mapping_state <> 'account_mapped' AND account_id IS NULL)",
        name="account_mapping_consistent",
    ),
    CheckConstraint("version > 0", name="positive_version"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_legacy_identity_mappings_state",
    legacy_identity_mappings.c.mapping_state,
    legacy_identity_mappings.c.semantic,
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
Index(
    "uq_identity_auth_methods_type_lookup",
    identity_authentication_methods.c.method_type,
    identity_authentication_methods.c.lookup_reference,
    unique=True,
    postgresql_where=identity_authentication_methods.c.lookup_reference.is_not(None),
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

persistence_idempotency_records = Table(
    "persistence_idempotency_records",
    metadata,
    Column("scope", String(127), primary_key=True),
    Column("actor_reference", String(128), primary_key=True),
    Column("idempotency_key", String(128), primary_key=True),
    Column("request_hash", String(64), nullable=False),
    Column("command_id", UUID(as_uuid=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("request_id", UUID(as_uuid=True), nullable=False),
    Column("response_reference", String(256)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    CheckConstraint("scope ~ '^[a-z][a-z0-9_.-]{1,126}$'", name="valid_scope"),
    CheckConstraint("request_hash ~ '^[a-f0-9]{64}$'", name="valid_request_hash"),
    CheckConstraint(
        "completed_at IS NULL OR (completed_at >= created_at "
        "AND response_reference IS NOT NULL)",
        name="valid_completion",
    ),
    UniqueConstraint("command_id"),
    schema=AYO_SCHEMA,
)

persistence_domain_events = Table(
    "persistence_domain_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("event_type", String(127), nullable=False),
    Column("aggregate_type", String(127), nullable=False),
    Column("aggregate_id", String(128), nullable=False),
    Column("source_module", String(127), nullable=False),
    Column("schema_version", Integer, nullable=False, server_default=text("1")),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("request_id", UUID(as_uuid=True), nullable=False),
    Column("command_id", UUID(as_uuid=True)),
    Column("causation_id", UUID(as_uuid=True)),
    Column("idempotency_key", String(128)),
    CheckConstraint("schema_version > 0", name="positive_schema_version"),
    UniqueConstraint(
        "source_module",
        "aggregate_type",
        "aggregate_id",
        "event_type",
        "idempotency_key",
        name="uq_persistence_domain_events_event_idempotency",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_persistence_domain_events_aggregate",
    persistence_domain_events.c.aggregate_type,
    persistence_domain_events.c.aggregate_id,
    persistence_domain_events.c.occurred_at,
)
Index(
    "ix_persistence_domain_events_correlation",
    persistence_domain_events.c.correlation_id,
    persistence_domain_events.c.occurred_at,
)

persistence_outbox = Table(
    "persistence_outbox",
    metadata,
    Column(
        "event_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.persistence_domain_events.event_id"),
        primary_key=True,
    ),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    Column("claimed_at", DateTime(timezone=True)),
    Column("claimed_by", String(64)),
    Column("published_at", DateTime(timezone=True)),
    Column("dead_lettered_at", DateTime(timezone=True)),
    Column("last_error_code", String(63)),
    CheckConstraint("attempt_count >= 0", name="nonnegative_attempts"),
    CheckConstraint(
        "(claimed_at IS NULL) = (claimed_by IS NULL)", name="complete_claim"
    ),
    CheckConstraint(
        "NOT (published_at IS NOT NULL AND dead_lettered_at IS NOT NULL)",
        name="single_terminal_state",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_persistence_outbox_pending",
    persistence_outbox.c.available_at,
    persistence_outbox.c.event_id,
    postgresql_where=(persistence_outbox.c.published_at.is_(None))
    & (persistence_outbox.c.dead_lettered_at.is_(None)),
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
        nullable=True,
    ),
    Column("mobility_model_version", Integer, nullable=False, server_default=text("1")),
    # Migration 0049 installs these foreign keys explicitly. Keeping the future
    # references out of shared metadata preserves reproducibility of migration
    # 0016, which creates this table before canonical_subjects exists.
    Column("requester_subject_id", UUID(as_uuid=True)),
    Column("passenger_subject_id", UUID(as_uuid=True)),
    Column("state", String(32), nullable=False),
    Column("service_type", String(32)),
    Column("payment_intent", String(32)),
    Column(
        "pickup_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_pickups.pickup_id"),
        nullable=True,
    ),
    Column(
        "destination_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_destinations.destination_id"),
        nullable=True,
    ),
    Column(
        "service_zone_id", UUID(as_uuid=True), ForeignKey("ayo.service_zones.zone_id")
    ),
    Column("consent_policy_version", String(63)),
    Column("pickup_reference", String(200)),
    Column("destination_reference", String(200)),
    Column(
        "stop_references",
        JSONB().with_variant(JSON(), "sqlite"),
    ),
    Column("schedule_intent", String(16)),
    Column("scheduled_for", DateTime(timezone=True)),
    Column("passenger_count", Integer),
    Column(
        "ride_preferences",
        JSONB().with_variant(JSON(), "sqlite"),
    ),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("cancellation_reason", String(63)),
    ForeignKeyConstraint(
        ["requester_subject_id"],
        ["ayo.canonical_subjects.subject_id"],
        name="fk_ride_requests_requester_subject",
    ),
    ForeignKeyConstraint(
        ["passenger_subject_id"],
        ["ayo.canonical_subjects.subject_id"],
        name="fk_ride_requests_passenger_subject",
    ),
    UniqueConstraint("rider_identity_id", "client_request_id"),
    UniqueConstraint("requester_subject_id", "client_request_id"),
    CheckConstraint("version > 0", name="canonical_ride_request_positive_version"),
    CheckConstraint(
        "mobility_model_version IN (1, 2)",
        name="canonical_ride_request_model_version",
    ),
    CheckConstraint(
        "(mobility_model_version = 1 AND rider_identity_id IS NOT NULL) OR "
        "(mobility_model_version = 2 AND requester_subject_id IS NOT NULL "
        "AND passenger_subject_id IS NOT NULL AND pickup_reference IS NOT NULL "
        "AND destination_reference IS NOT NULL AND schedule_intent IS NOT NULL "
        "AND passenger_count BETWEEN 1 AND 8)",
        name="canonical_ride_request_model_shape",
    ),
    CheckConstraint(
        "schedule_intent IS NULL OR schedule_intent IN ('immediate','scheduled')",
        name="canonical_ride_request_schedule_intent",
    ),
    CheckConstraint(
        "service_type = 'immediate_standard'",
        name="canonical_ride_request_supported_type",
    ),
    schema=AYO_SCHEMA,
)

booking_route_evidence = Table(
    "booking_route_evidence",
    metadata,
    Column("evidence_id", UUID(as_uuid=True), primary_key=True),
    Column("booking_session_hash", String(64), nullable=False),
    Column(
        "rider_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
    ),
    Column("pickup_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column(
        "destination_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False
    ),
    Column(
        "service_zone_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.service_zones.zone_id"),
        nullable=False,
    ),
    Column("service_zone_version", String(63), nullable=False),
    Column("service_type", String(32), nullable=False),
    Column("route_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("quote_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("evidence_hash", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "service_type='immediate_standard'", name="booking_route_immediate_standard"
    ),
    CheckConstraint("expires_at > created_at", name="booking_route_positive_expiry"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_booking_route_session_expiry",
    booking_route_evidence.c.booking_session_hash,
    booking_route_evidence.c.expires_at,
)

booking_confirmations = Table(
    "booking_confirmations",
    metadata,
    Column("confirmation_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "evidence_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.booking_route_evidence.evidence_id"),
        nullable=False,
        unique=True,
    ),
    Column("evidence_hash", String(64), nullable=False),
    Column("quote_id", UUID(as_uuid=True), nullable=False),
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
    Column("idempotency_key_hash", String(64), nullable=False),
    Column("confirmed_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "rider_identity_id",
        "idempotency_key_hash",
        name="uq_booking_confirmation_rider_key",
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

worker_capability_sessions = Table(
    "worker_capability_sessions",
    metadata,
    Column("worker_session_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column(
        "identity_session_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.sessions.session_id"),
        nullable=False,
    ),
    Column("capability", String(32), nullable=False),
    Column("vehicle_id", UUID(as_uuid=True)),
    Column("service_zone_id", UUID(as_uuid=True)),
    Column("state", String(16), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("stopped_at", DateTime(timezone=True)),
    Column("version", Integer, nullable=False),
    CheckConstraint(
        "capability IN ('ride_driver','food_courier','parcel_courier','home_service_provider')",
        name="worker_session_known_capability",
    ),
    CheckConstraint("state IN ('online','offline')", name="worker_session_known_state"),
    CheckConstraint("version > 0", name="worker_session_positive_version"),
    CheckConstraint(
        "(state='online' AND stopped_at IS NULL) OR (state='offline' AND stopped_at IS NOT NULL)",
        name="worker_session_stop_consistency",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "uq_worker_session_one_active_earning_role",
    worker_capability_sessions.c.identity_id,
    unique=True,
    postgresql_where=worker_capability_sessions.c.state == "online",
)
Index(
    "ix_worker_session_dispatch_lookup",
    worker_capability_sessions.c.capability,
    worker_capability_sessions.c.service_zone_id,
    worker_capability_sessions.c.state,
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
    Column("decision_evidence", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
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
    Column("route_evidence_id", String(128), nullable=False),
    Column(
        "decision_reason_codes", JSONB().with_variant(JSON(), "sqlite"), nullable=False
    ),
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

payment_intents = Table(
    "payment_intents",
    metadata,
    Column("payment_intent_id", UUID(as_uuid=True), primary_key=True),
    Column("ride_id", UUID(as_uuid=True), nullable=False),
    Column("rider_identity_id", UUID(as_uuid=True), nullable=False),
    Column("passenger_identity_id", UUID(as_uuid=True), nullable=False),
    Column("booker_identity_id", UUID(as_uuid=True), nullable=False),
    Column("payer_identity_id", UUID(as_uuid=True), nullable=False),
    Column("amount_minor", BigInteger, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("payment_method_family", String(24), nullable=False),
    Column("state", String(24), nullable=False),
    Column("traceability", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("metadata_safe", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    Column("cancelled_at", DateTime(timezone=True)),
    CheckConstraint(
        "amount_minor >= 0 AND currency = 'ETB'",
        name="payment_intent_etb_nonnegative",
    ),
    CheckConstraint(
        "payment_method_family IN ('cash','mobile_money','card','bank_transfer','unknown')",
        name="payment_method_family_allowed",
    ),
    CheckConstraint(
        "state IN ('created','cancelled','expired')",
        name="payment_intent_state_allowed",
    ),
    CheckConstraint(
        "payer_identity_id = rider_identity_id",
        name="payment_payer_must_match_rider",
    ),
    CheckConstraint(
        "expires_at IS NULL OR expires_at > created_at",
        name="payment_intent_expiry_after_creation",
    ),
    CheckConstraint(
        "cancelled_at IS NULL OR cancelled_at >= created_at",
        name="payment_intent_cancelled_after_creation",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_payment_intents_ride", payment_intents.c.ride_id, payment_intents.c.created_at
)

payment_attempts = Table(
    "payment_attempts",
    metadata,
    Column("payment_attempt_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "payment_intent_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.payment_intents.payment_intent_id"),
        nullable=False,
    ),
    Column("provider_code", String(63), nullable=False),
    Column("provider_reference", String(128), nullable=False),
    Column("provider_event_id", String(128)),
    Column("state", String(32), nullable=False),
    Column("amount_minor", BigInteger, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("reason_code", String(63)),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "amount_minor >= 0 AND currency = 'ETB'",
        name="payment_attempt_etb_nonnegative",
    ),
    CheckConstraint(
        "state IN ('created','authorization_pending','authorized','capture_pending','captured','failed','cancelled','expired','outcome_unknown')",
        name="payment_attempt_state_allowed",
    ),
    CheckConstraint(
        "provider_code ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="payment_attempt_provider_code",
    ),
    CheckConstraint(
        "reason_code IS NULL OR reason_code ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="payment_attempt_reason_code",
    ),
    CheckConstraint(
        "updated_at >= created_at",
        name="payment_attempt_update_after_creation",
    ),
    UniqueConstraint(
        "payment_intent_id",
        "provider_code",
        "provider_reference",
        name="uq_payment_attempt_provider_reference",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_payment_attempts_intent",
    payment_attempts.c.payment_intent_id,
    payment_attempts.c.updated_at,
)
Index(
    "uq_payment_attempt_single_active_per_intent",
    payment_attempts.c.payment_intent_id,
    unique=True,
    postgresql_where=payment_attempts.c.state.in_(
        (
            "created",
            "authorization_pending",
            "authorized",
            "capture_pending",
            "outcome_unknown",
        )
    ),
)
payment_callback_envelopes = Table(
    "payment_callback_envelopes",
    metadata,
    Column("callback_id", UUID(as_uuid=True), primary_key=True),
    Column("provider_code", String(63), nullable=False),
    Column("provider_event_id", String(128), nullable=False),
    Column("provider_signature_fingerprint", String(128), nullable=False),
    Column("payload_hash", String(64), nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("replay_window_ends_at", DateTime(timezone=True), nullable=False),
    Column("correlated_attempt_id", UUID(as_uuid=True)),
    Column("processed_at", DateTime(timezone=True)),
    CheckConstraint(
        "provider_code ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="payment_callback_provider_code",
    ),
    CheckConstraint(
        "provider_signature_fingerprint ~ '^[a-z0-9]{16,128}$'",
        name="payment_callback_signature_fingerprint",
    ),
    CheckConstraint(
        "payload_hash ~ '^[a-f0-9]{64}$'",
        name="payment_callback_hash_hex",
    ),
    CheckConstraint(
        "replay_window_ends_at > received_at",
        name="payment_callback_replay_window",
    ),
    CheckConstraint(
        "processed_at IS NULL OR processed_at >= received_at",
        name="payment_callback_processed_after_received",
    ),
    UniqueConstraint("provider_code", "provider_event_id"),
    schema=AYO_SCHEMA,
)

payment_idempotency = Table(
    "payment_idempotency",
    metadata,
    Column("actor_id", UUID(as_uuid=True), primary_key=True),
    Column("operation", String(63), primary_key=True),
    Column("idempotency_key", String(128), primary_key=True),
    Column("request_hash", String(64), nullable=False),
    Column("response_reference", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

payment_events = Table(
    "payment_events",
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

payment_outbox = Table(
    "payment_outbox",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column("event_id", UUID(as_uuid=True), nullable=False, unique=True),
    Column("event_type", String(63), nullable=False),
    Column("safe_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    CheckConstraint("attempt_count >= 0", name="payment_outbox_nonnegative_attempts"),
    schema=AYO_SCHEMA,
)

refund_requests = Table(
    "refund_requests",
    metadata,
    Column("refund_request_id", UUID(as_uuid=True), primary_key=True),
    Column("ride_id", UUID(as_uuid=True), nullable=False),
    Column(
        "fare_calculation_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.fare_calculations.calculation_id"),
        nullable=False,
    ),
    Column(
        "payment_intent_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.payment_intents.payment_intent_id"),
        nullable=False,
    ),
    Column(
        "payment_attempt_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.payment_attempts.payment_attempt_id"),
        nullable=False,
    ),
    Column(
        "ledger_journal_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.ledger_journals.journal_id"),
        nullable=False,
    ),
    Column("refund_type", String(40), nullable=False),
    Column("state", String(24), nullable=False),
    Column("amount_minor", BigInteger, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("reason_code", String(63), nullable=False),
    Column("requested_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("requested_at", DateTime(timezone=True), nullable=False),
    Column("last_transition_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    Column("rejected_at", DateTime(timezone=True)),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    Column("metadata_safe", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("traceability", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    CheckConstraint(
        "refund_type IN ('partial_refund','full_refund','administrative_adjustment','customer_goodwill_adjustment','system_correction_request')",
        name="refund_type_allowed",
    ),
    CheckConstraint(
        "state IN ('requested','under_review','approved','scheduled','completed','rejected')",
        name="refund_request_state_allowed",
    ),
    CheckConstraint(
        "amount_minor >= 0 AND currency = 'ETB'",
        name="refund_request_etb_nonnegative",
    ),
    CheckConstraint(
        "reason_code ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="refund_request_reason_code",
    ),
    CheckConstraint(
        "last_transition_at >= requested_at",
        name="refund_request_transition_after_requested",
    ),
    CheckConstraint(
        "completed_at IS NULL OR completed_at >= requested_at",
        name="refund_request_completed_after_requested",
    ),
    CheckConstraint(
        "rejected_at IS NULL OR rejected_at >= requested_at",
        name="refund_request_rejected_after_requested",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_refund_requests_ride", refund_requests.c.ride_id, refund_requests.c.requested_at
)

refund_decisions = Table(
    "refund_decisions",
    metadata,
    Column("decision_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "refund_request_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.refund_requests.refund_request_id"),
        nullable=False,
    ),
    Column("decision_type", String(24), nullable=False),
    Column("decision_outcome", String(63), nullable=False),
    Column("decided_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("reason_code", String(63), nullable=False),
    Column("decision_safe", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("decided_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    CheckConstraint(
        "decision_type IN ('review','investigation','approval','rejection','scheduling','completion')",
        name="refund_decision_type_allowed",
    ),
    CheckConstraint(
        "decision_outcome ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="refund_decision_outcome_safe",
    ),
    CheckConstraint(
        "reason_code ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="refund_decision_reason_code",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_refund_decisions_request_time",
    refund_decisions.c.refund_request_id,
    refund_decisions.c.decided_at,
)

refund_authorizations = Table(
    "refund_authorizations",
    metadata,
    Column("authorization_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "refund_request_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.refund_requests.refund_request_id"),
        nullable=False,
    ),
    Column("authorization_type", String(40), nullable=False),
    Column("authorized_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("authority_permission", String(63), nullable=False),
    Column("reason_code", String(63), nullable=False),
    Column(
        "authorization_safe",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    ),
    Column("authorized_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    CheckConstraint(
        "authorization_type IN ('finance_approval')",
        name="refund_authorization_type_allowed",
    ),
    CheckConstraint(
        "authority_permission ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="refund_authorization_permission_safe",
    ),
    CheckConstraint(
        "reason_code ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="refund_authorization_reason_code",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_refund_authorizations_request_time",
    refund_authorizations.c.refund_request_id,
    refund_authorizations.c.authorized_at,
)

refund_evidence = Table(
    "refund_evidence",
    metadata,
    Column("evidence_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "refund_request_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.refund_requests.refund_request_id"),
        nullable=False,
    ),
    Column("evidence_type", String(63), nullable=False),
    Column("evidence_reference", String(160), nullable=False),
    Column("recorded_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("safe_metadata", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    CheckConstraint(
        "evidence_type ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="refund_evidence_type_safe",
    ),
    UniqueConstraint(
        "refund_request_id",
        "evidence_type",
        "evidence_reference",
        name="uq_refund_evidence_reference",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_refund_evidence_request_time",
    refund_evidence.c.refund_request_id,
    refund_evidence.c.recorded_at,
)

refund_idempotency = Table(
    "refund_idempotency",
    metadata,
    Column("actor_id", UUID(as_uuid=True), primary_key=True),
    Column("operation", String(63), primary_key=True),
    Column("idempotency_key", String(128), primary_key=True),
    Column("request_hash", String(64), nullable=False),
    Column("response_reference", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

refund_events = Table(
    "refund_events",
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

refund_outbox = Table(
    "refund_outbox",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column("event_id", UUID(as_uuid=True), nullable=False, unique=True),
    Column("event_type", String(63), nullable=False),
    Column("safe_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    CheckConstraint("attempt_count >= 0", name="refund_outbox_nonnegative_attempts"),
    schema=AYO_SCHEMA,
)

settlement_batches = Table(
    "settlement_batches",
    metadata,
    Column("settlement_batch_id", UUID(as_uuid=True), primary_key=True),
    Column("state", String(32), nullable=False),
    Column("created_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_transition_at", DateTime(timezone=True), nullable=False),
    Column("ready_for_settlement_at", DateTime(timezone=True)),
    Column("metadata_safe", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    CheckConstraint(
        "state IN ('created','collecting','reconciling','balanced','ready_for_settlement','exception','manual_review','resolved')",
        name="settlement_batch_state_allowed",
    ),
    CheckConstraint(
        "last_transition_at >= created_at",
        name="settlement_batch_transition_after_create",
    ),
    CheckConstraint(
        "ready_for_settlement_at IS NULL OR ready_for_settlement_at >= created_at",
        name="settlement_batch_ready_after_create",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_settlement_batches_state_time",
    settlement_batches.c.state,
    settlement_batches.c.last_transition_at,
)

settlement_items = Table(
    "settlement_items",
    metadata,
    Column("settlement_item_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "settlement_batch_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.settlement_batches.settlement_batch_id"),
        nullable=False,
    ),
    Column("ride_id", UUID(as_uuid=True), nullable=False),
    Column(
        "fare_calculation_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.fare_calculations.calculation_id"),
        nullable=False,
    ),
    Column(
        "payment_intent_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.payment_intents.payment_intent_id"),
        nullable=False,
    ),
    Column(
        "payment_attempt_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.payment_attempts.payment_attempt_id"),
        nullable=False,
    ),
    Column(
        "refund_request_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.refund_requests.refund_request_id"),
    ),
    Column(
        "ledger_journal_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.ledger_journals.journal_id"),
        nullable=False,
    ),
    Column("reconciliation_type", String(40), nullable=False),
    Column("amount_minor", BigInteger, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("traceability", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "reconciliation_type IN ('ride_reconciliation','payment_reconciliation','refund_reconciliation','provider_reconciliation','settlement_reconciliation','manual_adjustment_review')",
        name="settlement_item_reconciliation_type_allowed",
    ),
    CheckConstraint(
        "amount_minor >= 0 AND currency = 'ETB'",
        name="settlement_item_etb_nonnegative",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_settlement_items_batch_time",
    settlement_items.c.settlement_batch_id,
    settlement_items.c.created_at,
)

reconciliation_records = Table(
    "reconciliation_records",
    metadata,
    Column("reconciliation_record_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "settlement_batch_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.settlement_batches.settlement_batch_id"),
        nullable=False,
    ),
    Column(
        "settlement_item_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.settlement_items.settlement_item_id"),
        nullable=False,
    ),
    Column("reconciliation_type", String(40), nullable=False),
    Column("result", String(32), nullable=False),
    Column("reason_code", String(63), nullable=False),
    Column("decision_safe", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("recorded_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    CheckConstraint(
        "reconciliation_type IN ('ride_reconciliation','payment_reconciliation','refund_reconciliation','provider_reconciliation','settlement_reconciliation','manual_adjustment_review')",
        name="reconciliation_record_type_allowed",
    ),
    CheckConstraint(
        "result IN ('matched','partially_matched','mismatch','missing','duplicate','manual_review_required')",
        name="reconciliation_record_result_allowed",
    ),
    CheckConstraint(
        "reason_code ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="reconciliation_record_reason_safe",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_reconciliation_records_batch_time",
    reconciliation_records.c.settlement_batch_id,
    reconciliation_records.c.recorded_at,
)

reconciliation_exceptions = Table(
    "reconciliation_exceptions",
    metadata,
    Column("reconciliation_exception_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "settlement_batch_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.settlement_batches.settlement_batch_id"),
        nullable=False,
    ),
    Column(
        "settlement_item_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.settlement_items.settlement_item_id"),
        nullable=False,
    ),
    Column("exception_type", String(40), nullable=False),
    Column("exception_state", String(24), nullable=False),
    Column("details_safe", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("raised_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("raised_at", DateTime(timezone=True), nullable=False),
    Column("resolution_code", String(63)),
    Column("resolved_by_identity_id", UUID(as_uuid=True)),
    Column("resolved_at", DateTime(timezone=True)),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    CheckConstraint(
        "exception_type IN ('duplicate_payment','missing_callback','amount_mismatch','currency_mismatch','refund_mismatch','orphan_payment','late_callback','unknown_outcome','manual_investigation','missing_expected_record','missing_observed_record','reference_mismatch','status_mismatch','timing_mismatch','unauthorized_record')",
        name="reconciliation_exception_type_allowed",
    ),
    CheckConstraint(
        "exception_state IN ('exception','manual_review','resolved')",
        name="reconciliation_exception_state_allowed",
    ),
    CheckConstraint(
        "resolution_code IS NULL OR resolution_code ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="reconciliation_resolution_code_safe",
    ),
    CheckConstraint(
        "resolved_at IS NULL OR resolved_at >= raised_at",
        name="reconciliation_resolved_after_raised",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_reconciliation_exceptions_batch_time",
    reconciliation_exceptions.c.settlement_batch_id,
    reconciliation_exceptions.c.raised_at,
)

settlement_approvals = Table(
    "settlement_approvals",
    metadata,
    Column("settlement_approval_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "settlement_batch_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.settlement_batches.settlement_batch_id"),
        nullable=False,
    ),
    Column("decision", String(16), nullable=False),
    Column("reason_code", String(63), nullable=False),
    Column("prepared_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("decided_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("decided_by_actor_type", String(16), nullable=False),
    Column("decided_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    CheckConstraint(
        "decision IN ('approved','rejected','revoked')",
        name="settlement_approval_decision_allowed",
    ),
    CheckConstraint(
        "prepared_by_identity_id <> decided_by_identity_id",
        name="settlement_approval_maker_checker",
    ),
    UniqueConstraint(
        "settlement_batch_id",
        "decision",
        "decided_by_identity_id",
        "decided_at",
        name="uq_settlement_approval_evidence",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_settlement_approvals_batch_time",
    settlement_approvals.c.settlement_batch_id,
    settlement_approvals.c.decided_at,
)

settlement_hold_evidence = Table(
    "settlement_hold_evidence",
    metadata,
    Column("settlement_hold_evidence_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "settlement_batch_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.settlement_batches.settlement_batch_id"),
        nullable=False,
    ),
    Column("financial_hold_id", UUID(as_uuid=True)),
    Column("hold_state", String(32), nullable=False),
    Column("blocks_readiness", Boolean, nullable=False),
    Column("evaluated_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("evaluated_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_settlement_hold_evidence_batch_time",
    settlement_hold_evidence.c.settlement_batch_id,
    settlement_hold_evidence.c.evaluated_at,
)

settlement_external_evidence = Table(
    "settlement_external_evidence",
    metadata,
    Column("settlement_external_evidence_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "settlement_batch_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.settlement_batches.settlement_batch_id"),
        nullable=False,
    ),
    Column("evidence_type", String(16), nullable=False),
    Column("provider_code", String(63), nullable=False),
    Column("provider_reference", String(128), nullable=False),
    Column("evidence_fingerprint", String(128), nullable=False),
    Column("recorded_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    CheckConstraint(
        "evidence_type IN ('submission','confirmation','failure')",
        name="settlement_external_evidence_type_allowed",
    ),
    UniqueConstraint(
        "provider_code",
        "provider_reference",
        "evidence_type",
        name="uq_settlement_external_evidence_reference",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_settlement_external_evidence_batch_time",
    settlement_external_evidence.c.settlement_batch_id,
    settlement_external_evidence.c.recorded_at,
)

settlement_idempotency = Table(
    "settlement_idempotency",
    metadata,
    Column("actor_id", UUID(as_uuid=True), primary_key=True),
    Column("operation", String(63), primary_key=True),
    Column("idempotency_key", String(128), primary_key=True),
    Column("request_hash", String(64), nullable=False),
    Column("response_reference", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

settlement_events = Table(
    "settlement_events",
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

settlement_outbox = Table(
    "settlement_outbox",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column("event_id", UUID(as_uuid=True), nullable=False, unique=True),
    Column("event_type", String(63), nullable=False),
    Column("safe_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    CheckConstraint(
        "attempt_count >= 0", name="settlement_outbox_nonnegative_attempts"
    ),
    schema=AYO_SCHEMA,
)

wallet_accounts = Table(
    "wallet_accounts",
    metadata,
    Column("wallet_account_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "owner_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("currency", String(3), nullable=False),
    Column("available_minor", BigInteger, nullable=False),
    Column("pending_minor", BigInteger, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("owner_identity_id", "currency", name="uq_wallet_owner_currency"),
    CheckConstraint("currency = 'ETB'", name="wallet_account_currency_etb"),
    CheckConstraint(
        "available_minor >= 0", name="wallet_account_available_nonnegative"
    ),
    CheckConstraint("pending_minor >= 0", name="wallet_account_pending_nonnegative"),
    CheckConstraint(
        "updated_at >= created_at", name="wallet_account_updated_after_create"
    ),
    schema=AYO_SCHEMA,
)
Index("ix_wallet_accounts_owner", wallet_accounts.c.owner_identity_id)

wallet_lineage_entries = Table(
    "wallet_lineage_entries",
    metadata,
    Column("wallet_entry_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "wallet_account_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.wallet_accounts.wallet_account_id"),
        nullable=False,
    ),
    Column("authoritative_source_type", String(40), nullable=False),
    Column("authoritative_source_id", UUID(as_uuid=True), nullable=False),
    Column("entry_type", String(32), nullable=False),
    Column("amount_minor", BigInteger, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("resulting_available_minor", BigInteger, nullable=False),
    Column("resulting_pending_minor", BigInteger, nullable=False),
    Column("reason_code", String(63), nullable=False),
    Column("recorded_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    CheckConstraint(
        "authoritative_source_type IN ('ledger_journal','payment_attempt','refund_request','settlement_batch')",
        name="wallet_authoritative_source_type_allowed",
    ),
    CheckConstraint(
        "entry_type IN ('pending_credit','pending_release','pending_reversal','available_credit','available_debit')",
        name="wallet_entry_type_allowed",
    ),
    CheckConstraint("amount_minor >= 0", name="wallet_lineage_amount_nonnegative"),
    CheckConstraint("currency = 'ETB'", name="wallet_lineage_currency_etb"),
    CheckConstraint(
        "resulting_available_minor >= 0",
        name="wallet_lineage_result_available_nonnegative",
    ),
    CheckConstraint(
        "resulting_pending_minor >= 0",
        name="wallet_lineage_result_pending_nonnegative",
    ),
    CheckConstraint(
        "reason_code ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="wallet_lineage_reason_safe",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_wallet_lineage_account_time",
    wallet_lineage_entries.c.wallet_account_id,
    wallet_lineage_entries.c.recorded_at,
)

wallet_idempotency = Table(
    "wallet_idempotency",
    metadata,
    Column("actor_id", UUID(as_uuid=True), primary_key=True),
    Column("operation", String(63), primary_key=True),
    Column("idempotency_key", String(128), primary_key=True),
    Column("request_hash", String(64), nullable=False),
    Column("response_reference", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

wallet_events = Table(
    "wallet_events",
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

wallet_outbox = Table(
    "wallet_outbox",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column("event_id", UUID(as_uuid=True), nullable=False, unique=True),
    Column("event_type", String(63), nullable=False),
    Column("safe_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    CheckConstraint("attempt_count >= 0", name="wallet_outbox_nonnegative_attempts"),
    schema=AYO_SCHEMA,
)

financial_postings = Table(
    "financial_postings",
    metadata,
    Column("posting_id", UUID(as_uuid=True), primary_key=True),
    Column("source_type", String(40), nullable=False),
    Column("source_id", UUID(as_uuid=True), nullable=False),
    Column("operation", String(63), nullable=False),
    Column("reason_code", String(63), nullable=False),
    Column("state", String(24), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("total_debit_minor", BigInteger, nullable=False),
    Column("total_credit_minor", BigInteger, nullable=False),
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column(
        "ledger_journal_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.ledger_journals.journal_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "wallet_entry_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.wallet_lineage_entries.wallet_entry_id"),
        nullable=False,
        unique=True,
    ),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "source_type",
        "source_id",
        "operation",
        name="uq_financial_posting_source_operation",
    ),
    CheckConstraint(
        "source_type IN ('completed_payment','approved_refund','settlement_event','wallet_adjustment')",
        name="financial_posting_source_type_allowed",
    ),
    CheckConstraint("state IN ('posted')", name="financial_posting_state_allowed"),
    CheckConstraint("currency = 'ETB'", name="financial_posting_currency_etb"),
    CheckConstraint(
        "total_debit_minor > 0 AND total_credit_minor > 0",
        name="financial_posting_positive_totals",
    ),
    CheckConstraint(
        "total_debit_minor = total_credit_minor",
        name="financial_posting_balanced_totals",
    ),
    CheckConstraint(
        "operation ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="financial_posting_operation_safe",
    ),
    CheckConstraint(
        "reason_code ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="financial_posting_reason_safe",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_financial_postings_source_time",
    financial_postings.c.source_type,
    financial_postings.c.created_at,
)

financial_posting_lines = Table(
    "financial_posting_lines",
    metadata,
    Column("posting_line_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "posting_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.financial_postings.posting_id"),
        nullable=False,
    ),
    Column("line_index", Integer, nullable=False),
    Column(
        "account_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.ledger_accounts.account_id"),
        nullable=False,
    ),
    Column("side", String(8), nullable=False),
    Column("amount_minor", BigInteger, nullable=False),
    Column("currency", String(3), nullable=False),
    UniqueConstraint(
        "posting_id",
        "line_index",
        name="uq_financial_posting_line_index",
    ),
    CheckConstraint(
        "line_index BETWEEN 1 AND 1024", name="financial_posting_line_index_range"
    ),
    CheckConstraint(
        "side IN ('debit','credit')", name="financial_posting_side_allowed"
    ),
    CheckConstraint("amount_minor > 0", name="financial_posting_line_positive_amount"),
    CheckConstraint("currency = 'ETB'", name="financial_posting_line_currency_etb"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_financial_posting_lines_posting",
    financial_posting_lines.c.posting_id,
    financial_posting_lines.c.line_index,
)

financial_posting_idempotency = Table(
    "financial_posting_idempotency",
    metadata,
    Column("actor_id", UUID(as_uuid=True), primary_key=True),
    Column("operation", String(63), primary_key=True),
    Column("idempotency_key", String(128), primary_key=True),
    Column("request_hash", String(64), nullable=False),
    Column("response_reference", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

financial_posting_events = Table(
    "financial_posting_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("aggregate_type", String(32), nullable=False),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", String(63), nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("safe_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column(
        "replay_payload",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    ),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    schema=AYO_SCHEMA,
)

financial_posting_outbox = Table(
    "financial_posting_outbox",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column("event_id", UUID(as_uuid=True), nullable=False, unique=True),
    Column("event_type", String(63), nullable=False),
    Column("safe_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    CheckConstraint(
        "attempt_count >= 0",
        name="financial_posting_outbox_nonnegative_attempts",
    ),
    schema=AYO_SCHEMA,
)

financial_holds = Table(
    "financial_holds",
    metadata,
    Column("hold_id", UUID(as_uuid=True), primary_key=True),
    Column("hold_type", String(40), nullable=False),
    Column("source_type", String(32), nullable=False),
    Column("source_id", UUID(as_uuid=True), nullable=False),
    Column("reason_code", String(63), nullable=False),
    Column("reason_detail", String(240)),
    Column("state", String(24), nullable=False),
    Column("created_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("metadata_safe", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    CheckConstraint(
        "hold_type IN ('rider_payment','driver_payout','wallet','refund','settlement','fraud_review','compliance_review','finance_manual_review')",
        name="financial_hold_type_allowed",
    ),
    CheckConstraint(
        "source_type IN ('payment_attempt','settlement_batch','wallet_account','refund_request','financial_posting','identity')",
        name="financial_hold_source_type_allowed",
    ),
    CheckConstraint(
        "state IN ('created','active','under_review','released','escalated','expired','cancelled')",
        name="financial_hold_state_allowed",
    ),
    CheckConstraint(
        "reason_code ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="financial_hold_reason_safe",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_financial_hold_source",
    financial_holds.c.source_type,
    financial_holds.c.source_id,
)
Index(
    "ix_financial_hold_state_time",
    financial_holds.c.state,
    financial_holds.c.updated_at,
)

financial_hold_state_history = Table(
    "financial_hold_state_history",
    metadata,
    Column("history_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "hold_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.financial_holds.hold_id"),
        nullable=False,
    ),
    Column("from_state", String(24)),
    Column("to_state", String(24), nullable=False),
    Column("reason_code", String(63), nullable=False),
    Column("reason_detail", String(240)),
    Column("changed_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("changed_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    Column("metadata_safe", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    CheckConstraint(
        "from_state IS NULL OR from_state IN ('created','active','under_review','released','escalated','expired','cancelled')",
        name="financial_hold_history_from_state_allowed",
    ),
    CheckConstraint(
        "to_state IN ('created','active','under_review','released','escalated','expired','cancelled')",
        name="financial_hold_history_to_state_allowed",
    ),
    CheckConstraint(
        "reason_code ~ '^[a-z][a-z0-9_.-]{2,62}$'",
        name="financial_hold_history_reason_safe",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_financial_hold_history_hold_time",
    financial_hold_state_history.c.hold_id,
    financial_hold_state_history.c.changed_at,
)

financial_hold_idempotency = Table(
    "financial_hold_idempotency",
    metadata,
    Column("actor_id", UUID(as_uuid=True), primary_key=True),
    Column("operation", String(63), primary_key=True),
    Column("idempotency_key", String(128), primary_key=True),
    Column("request_hash", String(64), nullable=False),
    Column("response_reference", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

financial_hold_events = Table(
    "financial_hold_events",
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

financial_hold_outbox = Table(
    "financial_hold_outbox",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column("event_id", UUID(as_uuid=True), nullable=False, unique=True),
    Column("event_type", String(63), nullable=False),
    Column("safe_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    CheckConstraint(
        "attempt_count >= 0",
        name="financial_hold_outbox_nonnegative_attempts",
    ),
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

# Increment 19 Milestone 7: immutable post-trip evidence and private trust records.
post_trip_records = Table(
    "post_trip_records",
    metadata,
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        primary_key=True,
    ),
    Column(
        "package_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.trip_evidence_packages.package_id"),
        nullable=False,
        unique=True,
    ),
    Column("state", String(32), nullable=False),
    Column("cash_state", String(32)),
    Column(
        "financial_breakdown", JSONB().with_variant(JSON(), "sqlite"), nullable=False
    ),
    Column(
        "ledger_journal_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.ledger_journals.journal_id"),
    ),
    Column(
        "wallet_entry_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.wallet_lineage_entries.wallet_entry_id"),
    ),
    Column(
        "rider_receipt_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.trip_receipts.receipt_id"),
    ),
    Column(
        "driver_receipt_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.trip_receipts.receipt_id"),
    ),
    Column("archived_at", DateTime(timezone=True)),
    Column("version", Integer, nullable=False),
    CheckConstraint("version > 0", name="post_trip_positive_version"),
    schema=AYO_SCHEMA,
)

trip_evidence_packages = Table(
    "trip_evidence_packages",
    metadata,
    Column("package_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
        unique=True,
    ),
    Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("package_hash", String(64), nullable=False, unique=True),
    Column("finalized_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)

trip_cash_confirmations = Table(
    "trip_cash_confirmations",
    metadata,
    Column("confirmation_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column(
        "actor_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("actor_role", String(16), nullable=False),
    Column("confirmed", Boolean, nullable=False),
    Column("idempotency_key_hash", String(64), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("ride_id", "actor_role", name="uq_cash_confirmation_role"),
    UniqueConstraint(
        "actor_identity_id",
        "idempotency_key_hash",
        name="uq_cash_confirmation_idempotency",
    ),
    schema=AYO_SCHEMA,
)

trip_ratings = Table(
    "trip_ratings",
    metadata,
    Column("rating_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column(
        "author_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column(
        "target_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("stars", Integer, nullable=False),
    Column("feedback", String(1000)),
    Column("preference_requested", Boolean, nullable=False),
    Column("submitted_at", DateTime(timezone=True), nullable=False),
    Column("window_expires_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("ride_id", "author_identity_id", name="uq_trip_rating_author"),
    CheckConstraint("stars BETWEEN 1 AND 5", name="trip_rating_stars"),
    schema=AYO_SCHEMA,
)

preference_signals = Table(
    "preference_signals",
    metadata,
    Column("preference_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "owner_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("capability", String(32), nullable=False),
    Column("target_type", String(32), nullable=False),
    Column(
        "target_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column(
        "source_ride_id", UUID(as_uuid=True), ForeignKey("ayo.active_rides.ride_id")
    ),
    Column("active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    UniqueConstraint(
        "owner_identity_id",
        "capability",
        "target_type",
        "target_identity_id",
        name="uq_preference_target",
    ),
    schema=AYO_SCHEMA,
)

trip_receipts = Table(
    "trip_receipts",
    metadata,
    Column("receipt_id", UUID(as_uuid=True), primary_key=True),
    Column("receipt_number", String(64), nullable=False, unique=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column(
        "issued_to_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("receipt_type", String(40), nullable=False),
    Column("payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("payload_hash", String(64), nullable=False),
    Column("legal_entity", String(160), nullable=False),
    Column("regulatory_policy_version", String(63), nullable=False),
    Column("issued_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("ride_id", "receipt_type", name="uq_trip_receipt_type"),
    schema=AYO_SCHEMA,
)

post_trip_outbox = Table(
    "post_trip_outbox",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "ride_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.active_rides.ride_id"),
        nullable=False,
    ),
    Column("event_type", String(63), nullable=False),
    Column(
        "recipient_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("safe_payload", JSONB().with_variant(JSON(), "sqlite"), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    schema=AYO_SCHEMA,
)
merchant_profiles = Table(
    "merchant_profiles",
    metadata,
    Column("merchant_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "owner_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("legal_name", String(160), nullable=False),
    Column("display_name", String(120), nullable=False),
    Column("kind", String(24), nullable=False),
    Column("onboarding_source", String(24), nullable=False),
    Column(
        "assisted_by_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
    ),
    Column("state", String(32), nullable=False),
    Column("capability_code", String(63), nullable=False),
    Column("market_code", String(15), nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "owner_identity_id <> assisted_by_identity_id",
        name="merchant_owner_not_representative",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_merchant_owner",
    merchant_profiles.c.owner_identity_id,
    merchant_profiles.c.created_at,
)

merchant_branches = Table(
    "merchant_branches",
    metadata,
    Column("branch_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column("name", String(120), nullable=False),
    Column("address_label", String(240), nullable=False),
    Column("timezone", String(63), nullable=False),
    Column("operating_hours", JSONB, nullable=False),
    Column("active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("merchant_id", "name", name="uq_merchant_branch_name"),
    schema=AYO_SCHEMA,
)

merchant_verifications = Table(
    "merchant_verifications",
    metadata,
    Column("evidence_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column("kind", String(32), nullable=False),
    Column("state", String(24), nullable=False),
    Column("opaque_reference", String(160), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    Column("submitted_at", DateTime(timezone=True), nullable=False),
    Column("reviewed_at", DateTime(timezone=True)),
    Column(
        "reviewed_by_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
    ),
    Column("reason_code", String(63)),
    UniqueConstraint("merchant_id", "kind", name="uq_merchant_verification_kind"),
    schema=AYO_SCHEMA,
)

merchant_partner_programs = Table(
    "merchant_partner_programs",
    metadata,
    Column("program_id", UUID(as_uuid=True), primary_key=True),
    Column("code", String(63), nullable=False, unique=True),
    Column("badge_label", String(80), nullable=False),
    Column("capability_code", String(63), nullable=False),
    Column("market_code", String(15), nullable=False),
    Column("opens_at", DateTime(timezone=True), nullable=False),
    Column("closes_at", DateTime(timezone=True), nullable=False),
    Column("participant_limit", Integer),
    Column("benefit_configuration", JSONB, nullable=False),
    Column("active", Boolean, nullable=False),
    Column("version", Integer, nullable=False),
    CheckConstraint("closes_at > opens_at", name="merchant_program_window"),
    CheckConstraint(
        "participant_limit IS NULL OR participant_limit > 0",
        name="merchant_program_limit",
    ),
    schema=AYO_SCHEMA,
)

merchant_program_enrollments = Table(
    "merchant_program_enrollments",
    metadata,
    Column("enrollment_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "program_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_partner_programs.program_id"),
        nullable=False,
    ),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column("enrolled_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "program_id", "merchant_id", name="uq_merchant_program_enrollment"
    ),
    schema=AYO_SCHEMA,
)

merchant_catalogue_items = Table(
    "merchant_catalogue_items",
    metadata,
    Column("item_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column(
        "branch_id", UUID(as_uuid=True), ForeignKey("ayo.merchant_branches.branch_id")
    ),
    Column("kind", String(24), nullable=False),
    Column("name", String(160), nullable=False),
    Column("description", String(1000)),
    Column("category_code", String(63), nullable=False),
    Column("state", String(32), nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_merchant_catalogue_page",
    merchant_catalogue_items.c.merchant_id,
    merchant_catalogue_items.c.created_at,
    merchant_catalogue_items.c.item_id,
)

merchant_assistance = Table(
    "merchant_assistance",
    metadata,
    Column("assistance_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column(
        "representative_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("activity_code", String(63), nullable=False),
    Column("verified_onboarding", Boolean, nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "merchant_id",
        "representative_identity_id",
        "activity_code",
        name="uq_merchant_assistance_activity",
    ),
    schema=AYO_SCHEMA,
)

merchant_idempotency = Table(
    "merchant_idempotency",
    metadata,
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("operation", String(63), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_reference", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "actor_identity_id",
        "operation",
        "idempotency_key",
        name="uq_merchant_idempotency",
    ),
    schema=AYO_SCHEMA,
)

merchant_outbox = Table(
    "merchant_outbox",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column("event_type", String(63), nullable=False),
    Column("safe_payload", JSONB, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    schema=AYO_SCHEMA,
)

catalogue_categories = Table(
    "catalogue_categories",
    metadata,
    Column("category_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column(
        "parent_category_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.catalogue_categories.category_id"),
    ),
    Column("name", String(120), nullable=False),
    Column("description", String(500)),
    Column("normalized_name", String(120), nullable=False),
    Column("active", Boolean, nullable=False),
    Column("sort_order", Integer, nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "merchant_id",
        "parent_category_id",
        "normalized_name",
        name="uq_catalogue_category_sibling",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_catalogue_category_tree",
    catalogue_categories.c.merchant_id,
    catalogue_categories.c.parent_category_id,
    catalogue_categories.c.sort_order,
)
Index(
    "uq_catalogue_root_category",
    catalogue_categories.c.merchant_id,
    catalogue_categories.c.normalized_name,
    unique=True,
    postgresql_where=catalogue_categories.c.parent_category_id.is_(None),
)

universal_catalogue_items = Table(
    "universal_catalogue_items",
    metadata,
    Column("item_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column(
        "category_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.catalogue_categories.category_id"),
    ),
    Column(
        "branch_id", UUID(as_uuid=True), ForeignKey("ayo.merchant_branches.branch_id")
    ),
    Column("kind", String(24), nullable=False),
    Column("name", String(160), nullable=False),
    Column("description", String(2000)),
    Column("media", JSONB, nullable=False),
    Column("status", String(24), nullable=False),
    Column("availability", String(32), nullable=False),
    Column("visibility", String(24), nullable=False),
    Column("tags", JSONB, nullable=False),
    Column("search_keywords", JSONB, nullable=False),
    Column("base_price_minor", BigInteger),
    Column("currency", String(3), nullable=False),
    Column("variant_contract_version", Integer),
    Column("modifier_contract_version", Integer),
    Column(
        "source_item_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.universal_catalogue_items.item_id"),
    ),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "base_price_minor IS NULL OR base_price_minor >= 0",
        name="catalogue_nonnegative_price",
    ),
    CheckConstraint("currency = 'ETB'", name="catalogue_etb_currency"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_catalogue_item_page",
    universal_catalogue_items.c.merchant_id,
    universal_catalogue_items.c.status,
    universal_catalogue_items.c.updated_at,
    universal_catalogue_items.c.item_id,
)
Index(
    "ix_catalogue_item_category",
    universal_catalogue_items.c.merchant_id,
    universal_catalogue_items.c.category_id,
    universal_catalogue_items.c.status,
)

catalogue_idempotency = Table(
    "catalogue_idempotency",
    metadata,
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("operation", String(63), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_reference", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "actor_identity_id",
        "operation",
        "idempotency_key",
        name="uq_catalogue_idempotency",
    ),
    schema=AYO_SCHEMA,
)

catalogue_outbox = Table(
    "catalogue_outbox",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column(
        "item_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.universal_catalogue_items.item_id"),
    ),
    Column("event_type", String(63), nullable=False),
    Column("safe_payload", JSONB, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    schema=AYO_SCHEMA,
)

commerce_orders = Table(
    "commerce_orders",
    metadata,
    Column("order_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "customer_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column("merchant_display_name", String(120), nullable=False),
    Column("merchant_version", Integer, nullable=False),
    Column("state", String(63), nullable=False),
    Column("version", Integer, nullable=False),
    Column("pricing_evidence", JSONB, nullable=False),
    Column("availability_evaluation_id", UUID(as_uuid=True)),
    Column("composition_hash", String(64)),
    Column("access_interaction_id", UUID(as_uuid=True)),
    Column("evidence_hash", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_commerce_order_customer",
    commerce_orders.c.customer_identity_id,
    commerce_orders.c.created_at,
    commerce_orders.c.order_id,
)
commerce_order_lines = Table(
    "commerce_order_lines",
    metadata,
    Column(
        "order_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_orders.order_id"),
        primary_key=True,
    ),
    Column("line_number", Integer, primary_key=True),
    Column("item_id", UUID(as_uuid=True), nullable=False),
    Column("item_version", Integer, nullable=False),
    Column("name", String(160), nullable=False),
    Column("kind", String(24), nullable=False),
    Column("category_id", UUID(as_uuid=True)),
    Column("quantity", Integer, nullable=False),
    Column("unit_price_minor", BigInteger, nullable=False),
    Column("line_total_minor", BigInteger, nullable=False),
    Column("currency", String(3), nullable=False),
    Column(
        "modifier_selections", JSONB, nullable=False, server_default=text("'[]'::jsonb")
    ),
    Column("customer_instructions", String(500)),
    CheckConstraint("quantity > 0 AND quantity <= 99", name="commerce_line_quantity"),
    CheckConstraint(
        "unit_price_minor >= 0 AND line_total_minor >= 0", name="commerce_line_money"
    ),
    schema=AYO_SCHEMA,
)
commerce_order_evidence = Table(
    "commerce_order_evidence",
    metadata,
    Column(
        "order_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_orders.order_id"),
        primary_key=True,
    ),
    Column("immutable_payload", JSONB, nullable=False),
    Column("evidence_hash", String(64), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
commerce_order_idempotency = Table(
    "commerce_order_idempotency",
    metadata,
    Column("customer_identity_id", UUID(as_uuid=True), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("order_id", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "customer_identity_id", "idempotency_key", name="uq_commerce_order_idempotency"
    ),
    schema=AYO_SCHEMA,
)
commerce_order_outbox = Table(
    "commerce_order_outbox",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "order_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_orders.order_id"),
        nullable=False,
    ),
    Column("event_type", String(63), nullable=False),
    Column("safe_payload", JSONB, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    schema=AYO_SCHEMA,
)
commerce_order_timeline = Table(
    "commerce_order_timeline",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "order_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_orders.order_id"),
        nullable=False,
    ),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column("event_type", String(63), nullable=False),
    Column("from_state", String(63)),
    Column("to_state", String(63), nullable=False),
    Column(
        "actor_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
    ),
    Column("order_version", Integer, nullable=False),
    Column("customer_reason_code", String(63)),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_commerce_order_timeline",
    commerce_order_timeline.c.order_id,
    commerce_order_timeline.c.order_version,
)

p2_eat_availability_policies = Table(
    "p2_eat_availability_policies",
    metadata,
    Column("policy_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column("product_code", String(63), nullable=False),
    Column("area_reference", String(200), nullable=False),
    Column("coverage_reference", String(200), nullable=False),
    Column("state", String(63), nullable=False),
    Column("reason_code", String(63), nullable=False),
    Column("effective_from", DateTime(timezone=True), nullable=False),
    Column("effective_until", DateTime(timezone=True)),
    Column("version", Integer, nullable=False),
    Column(
        "created_by_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "merchant_id",
        "product_code",
        "area_reference",
        name="uq_p2_eat_policy_scope",
    ),
    CheckConstraint(
        "state IN ('available','temporarily_unavailable','unavailable')",
        name="valid_state",
    ),
    CheckConstraint("version > 0", name="positive_version"),
    CheckConstraint(
        "effective_until IS NULL OR effective_until > effective_from",
        name="valid_window",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_p2_eat_policy_effective",
    p2_eat_availability_policies.c.merchant_id,
    p2_eat_availability_policies.c.area_reference,
    p2_eat_availability_policies.c.effective_from,
)

p2_eat_availability_policy_history = Table(
    "p2_eat_availability_policy_history",
    metadata,
    Column("history_id", UUID(as_uuid=True), primary_key=True),
    Column("policy_id", UUID(as_uuid=True), nullable=False),
    Column("policy_version", Integer, nullable=False),
    Column("immutable_payload", JSONB, nullable=False),
    Column("evidence_hash", String(64), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("policy_id", "policy_version", name="uq_p2_eat_policy_history"),
    schema=AYO_SCHEMA,
)

p2_eat_availability_evaluations = Table(
    "p2_eat_availability_evaluations",
    metadata,
    Column("evaluation_id", UUID(as_uuid=True), primary_key=True),
    Column("policy_id", UUID(as_uuid=True)),
    Column("policy_version", Integer),
    Column("merchant_id", UUID(as_uuid=True), nullable=False),
    Column("area_reference", String(200), nullable=False),
    Column("coverage_reference", String(200), nullable=False),
    Column("item_references", JSONB, nullable=False),
    Column("merchant_open", Boolean, nullable=False),
    Column("outcome", String(63), nullable=False),
    Column("reason_code", String(63), nullable=False),
    Column("evaluated_at", DateTime(timezone=True), nullable=False),
    Column("evidence_hash", String(64), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("request_id", UUID(as_uuid=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_p2_eat_evaluation_merchant_time",
    p2_eat_availability_evaluations.c.merchant_id,
    p2_eat_availability_evaluations.c.evaluated_at,
)

p2_eat_availability_idempotency = Table(
    "p2_eat_availability_idempotency",
    metadata,
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("operation", String(63), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_reference", String(160)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "actor_identity_id",
        "operation",
        "idempotency_key",
        name="uq_p2_eat_availability_idempotency",
    ),
    schema=AYO_SCHEMA,
)

p2_eat_availability_outbox = Table(
    "p2_eat_availability_outbox",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", String(63), nullable=False),
    Column("safe_payload", JSONB, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    schema=AYO_SCHEMA,
)
commerce_order_rejections = Table(
    "commerce_order_rejections",
    metadata,
    Column(
        "order_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_orders.order_id"),
        primary_key=True,
    ),
    Column("customer_reason_code", String(63), nullable=False),
    Column("customer_message", String(240), nullable=False),
    Column("internal_merchant_note", String(1000)),
    Column(
        "decided_by_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("decided_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
commerce_merchant_action_idempotency = Table(
    "commerce_merchant_action_idempotency",
    metadata,
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("merchant_id", UUID(as_uuid=True), nullable=False),
    Column("order_id", UUID(as_uuid=True), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_version", Integer),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "actor_identity_id",
        "merchant_id",
        "idempotency_key",
        name="uq_commerce_merchant_action_idempotency",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_commerce_order_merchant_state",
    commerce_orders.c.merchant_id,
    commerce_orders.c.state,
    commerce_orders.c.created_at,
    commerce_orders.c.order_id,
)
commerce_order_preparations = Table(
    "commerce_order_preparations",
    metadata,
    Column(
        "order_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_orders.order_id"),
        primary_key=True,
    ),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("estimated_duration_seconds", Integer, nullable=False),
    Column("estimated_ready_at", DateTime(timezone=True), nullable=False),
    Column("progress_percent", Integer, nullable=False),
    Column("latest_delay_reason_code", String(63)),
    Column("latest_delay_message", String(240)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("ready_at", DateTime(timezone=True)),
    CheckConstraint(
        "estimated_duration_seconds >= 60 AND estimated_duration_seconds <= 14400",
        name="commerce_preparation_estimate_bounds",
    ),
    CheckConstraint(
        "progress_percent >= 0 AND progress_percent <= 100",
        name="commerce_preparation_progress_bounds",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_commerce_preparation_merchant",
    commerce_order_preparations.c.merchant_id,
    commerce_order_preparations.c.updated_at,
    commerce_order_preparations.c.order_id,
)

commerce_courier_dispatch_requests = Table(
    "commerce_courier_dispatch_requests",
    metadata,
    Column("dispatch_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "order_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_orders.order_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column("readiness_message_id", UUID(as_uuid=True), nullable=False, unique=True),
    Column("state", String(40), nullable=False),
    Column("version", Integer, nullable=False),
    Column("policy_code", String(63), nullable=False),
    Column("policy_version", Integer, nullable=False),
    Column("attempt_number", Integer, nullable=False, server_default=text("0")),
    Column("active_offer_id", UUID(as_uuid=True)),
    Column("active_assignment_id", UUID(as_uuid=True)),
    Column(
        "offered_courier_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
    ),
    Column(
        "assigned_courier_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("offered_at", DateTime(timezone=True)),
    Column("assigned_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_courier_dispatch_merchant_state",
    commerce_courier_dispatch_requests.c.merchant_id,
    commerce_courier_dispatch_requests.c.state,
    commerce_courier_dispatch_requests.c.updated_at,
)
commerce_courier_dispatch_events = Table(
    "commerce_courier_dispatch_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "dispatch_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_courier_dispatch_requests.dispatch_id"),
        nullable=False,
    ),
    Column("order_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", String(80), nullable=False),
    Column("from_state", String(40)),
    Column("to_state", String(40), nullable=False),
    Column(
        "actor_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
    ),
    Column("version", Integer, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True)),
    Column("causation_id", UUID(as_uuid=True)),
    schema=AYO_SCHEMA,
)
Index(
    "ix_courier_dispatch_event",
    commerce_courier_dispatch_events.c.dispatch_id,
    commerce_courier_dispatch_events.c.version,
)
commerce_courier_dispatch_idempotency = Table(
    "commerce_courier_dispatch_idempotency",
    metadata,
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("dispatch_id", UUID(as_uuid=True), nullable=False),
    Column("operation", String(40), nullable=False, server_default=text("'legacy'")),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_version", Integer),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "actor_identity_id",
        "operation",
        "idempotency_key",
        name="uq_courier_dispatch_actor_action_idempotency",
    ),
    schema=AYO_SCHEMA,
)

commerce_courier_pickups = Table(
    "commerce_courier_pickups",
    metadata,
    Column("pickup_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "dispatch_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_courier_dispatch_requests.dispatch_id"),
        nullable=False,
    ),
    Column(
        "order_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_orders.order_id"),
        nullable=False,
    ),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column(
        "assigned_courier_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column(
        "assignment_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.courier_dispatch_assignments.assignment_id"),
        unique=True,
    ),
    Column("assignment_version", Integer, nullable=False, server_default="1"),
    Column("attempt_number", Integer, nullable=False, server_default="1"),
    Column("assignment_message_id", UUID(as_uuid=True), nullable=False, unique=True),
    Column(
        "policy_code",
        String(80),
        nullable=False,
        server_default="AYO_COURIER_PICKUP_POLICY_V1",
    ),
    Column("policy_version", Integer, nullable=False, server_default="1"),
    Column("state", String(40), nullable=False),
    Column("version", Integer, nullable=False),
    Column("assigned_at", DateTime(timezone=True), nullable=False),
    Column("travelling_at", DateTime(timezone=True)),
    Column("arrived_at", DateTime(timezone=True)),
    Column("merchant_acknowledged_at", DateTime(timezone=True)),
    Column("waiting_duration_seconds", Integer),
    Column("terminal_reason", String(80)),
    Column("custody_accepted_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_courier_pickup_merchant_state",
    commerce_courier_pickups.c.merchant_id,
    commerce_courier_pickups.c.state,
    commerce_courier_pickups.c.updated_at,
)
commerce_courier_pickup_events = Table(
    "commerce_courier_pickup_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "pickup_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_courier_pickups.pickup_id"),
        nullable=False,
    ),
    Column("order_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", String(80), nullable=False),
    Column("from_state", String(40)),
    Column("to_state", String(40), nullable=False),
    Column(
        "actor_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
    ),
    Column("version", Integer, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_courier_pickup_event",
    commerce_courier_pickup_events.c.pickup_id,
    commerce_courier_pickup_events.c.version,
)
commerce_courier_pickup_idempotency = Table(
    "commerce_courier_pickup_idempotency",
    metadata,
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("pickup_id", UUID(as_uuid=True), nullable=False),
    Column("action", String(48), nullable=False, server_default="legacy"),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_version", Integer),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "actor_identity_id",
        "action",
        "idempotency_key",
        name="uq_courier_pickup_actor_action_idempotency",
    ),
    schema=AYO_SCHEMA,
)
commerce_courier_pickup_evidence = Table(
    "commerce_courier_pickup_evidence",
    metadata,
    Column("evidence_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "pickup_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_courier_pickups.pickup_id"),
        nullable=False,
    ),
    Column("pickup_version", Integer, nullable=False),
    Column("kind", String(48), nullable=False),
    Column("actor_identity_id", UUID(as_uuid=True)),
    Column("acting_for_identity_id", UUID(as_uuid=True)),
    Column("merchant_id", UUID(as_uuid=True)),
    Column("authority_basis", String(128)),
    Column("source_reference", UUID(as_uuid=True)),
    Column("source_version", Integer),
    Column("reason", String(80)),
    Column("waiting_duration_seconds", Integer),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_courier_pickup_evidence_attempt",
    commerce_courier_pickup_evidence.c.pickup_id,
    commerce_courier_pickup_evidence.c.pickup_version,
)
commerce_custody_records = Table(
    "commerce_custody_records",
    metadata,
    Column("custody_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "pickup_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_courier_pickups.pickup_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "order_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_orders.order_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column(
        "courier_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("state", String(40), nullable=False),
    Column("version", Integer, nullable=False),
    Column("sealed_at", DateTime(timezone=True)),
    Column("verified_at", DateTime(timezone=True)),
    Column("verification_method", String(20)),
    Column("merchant_released_at", DateTime(timezone=True)),
    Column("custody_accepted_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_custody_merchant_state",
    commerce_custody_records.c.merchant_id,
    commerce_custody_records.c.state,
    commerce_custody_records.c.updated_at,
)
commerce_custody_challenges = Table(
    "commerce_custody_challenges",
    metadata,
    Column("challenge_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "custody_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_custody_records.custody_id"),
        nullable=False,
    ),
    Column("code_hash", String(64), nullable=False, unique=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("used_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_custody_challenge_active",
    commerce_custody_challenges.c.custody_id,
    commerce_custody_challenges.c.expires_at,
)
commerce_custody_events = Table(
    "commerce_custody_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "custody_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_custody_records.custody_id"),
        nullable=False,
    ),
    Column("order_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", String(80), nullable=False),
    Column("from_state", String(40), nullable=False),
    Column("to_state", String(40), nullable=False),
    Column(
        "actor_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("version", Integer, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_custody_event",
    commerce_custody_events.c.custody_id,
    commerce_custody_events.c.version,
)
commerce_custody_idempotency = Table(
    "commerce_custody_idempotency",
    metadata,
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("custody_id", UUID(as_uuid=True), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_version", Integer),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "actor_identity_id", "idempotency_key", name="uq_custody_idempotency"
    ),
    schema=AYO_SCHEMA,
)
commerce_delivery_credentials = Table(
    "commerce_delivery_credentials",
    metadata,
    Column("credential_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "order_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_orders.order_id"),
        nullable=False,
        unique=True,
    ),
    Column("source_message_id", UUID(as_uuid=True), nullable=False, unique=True),
    Column("order_number", String(32), nullable=False, unique=True),
    Column("code_hash", String(64), nullable=False, unique=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("used_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
commerce_deliveries = Table(
    "commerce_deliveries",
    metadata,
    Column("delivery_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "custody_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_custody_records.custody_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "order_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_orders.order_id"),
        nullable=False,
        unique=True,
    ),
    Column("merchant_id", UUID(as_uuid=True), nullable=False),
    Column("courier_identity_id", UUID(as_uuid=True), nullable=False),
    Column(
        "credential_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_delivery_credentials.credential_id"),
        nullable=False,
    ),
    Column("source_message_id", UUID(as_uuid=True), nullable=False, unique=True),
    Column("state", String(40), nullable=False),
    Column("version", Integer, nullable=False),
    Column("arriving_at", DateTime(timezone=True)),
    Column("customer_available_at", DateTime(timezone=True)),
    Column("verified_at", DateTime(timezone=True)),
    Column("verification_method", String(20)),
    Column("customer_received_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("closed_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_delivery_courier_state",
    commerce_deliveries.c.courier_identity_id,
    commerce_deliveries.c.state,
    commerce_deliveries.c.updated_at,
)
commerce_delivery_events = Table(
    "commerce_delivery_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "delivery_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_deliveries.delivery_id"),
        nullable=False,
    ),
    Column("event_type", String(90), nullable=False),
    Column("from_state", String(40)),
    Column("to_state", String(40), nullable=False),
    Column("actor_identity_id", UUID(as_uuid=True)),
    Column("version", Integer, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_delivery_event",
    commerce_delivery_events.c.delivery_id,
    commerce_delivery_events.c.version,
)
commerce_delivery_idempotency = Table(
    "commerce_delivery_idempotency",
    metadata,
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("delivery_id", UUID(as_uuid=True), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_version", Integer),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "actor_identity_id", "idempotency_key", name="uq_delivery_idempotency"
    ),
    schema=AYO_SCHEMA,
)
commerce_delivery_reminders = Table(
    "commerce_delivery_reminders",
    metadata,
    Column("reminder_id", UUID(as_uuid=True), primary_key=True),
    Column("delivery_id", UUID(as_uuid=True), nullable=False),
    Column("channel", String(16), nullable=False),
    Column("eta_evidence_id", UUID(as_uuid=True), nullable=False),
    Column("eta_minutes", Integer, nullable=False),
    Column("policy_version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("delivery_id", "channel", name="uq_delivery_reminder_channel"),
    schema=AYO_SCHEMA,
)
commerce_delivery_notification_intents = Table(
    "commerce_delivery_notification_intents",
    metadata,
    Column("intent_id", UUID(as_uuid=True), primary_key=True),
    Column("order_id", UUID(as_uuid=True), nullable=False),
    Column("delivery_id", UUID(as_uuid=True)),
    Column("channel", String(16), nullable=False),
    Column("template_code", String(63), nullable=False),
    Column("secure_credential_reference", UUID(as_uuid=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    UniqueConstraint(
        "order_id", "channel", "template_code", name="uq_delivery_notification_intent"
    ),
    schema=AYO_SCHEMA,
)
commerce_preparation_events = Table(
    "commerce_preparation_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "order_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_orders.order_id"),
        nullable=False,
    ),
    Column("merchant_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", String(63), nullable=False),
    Column(
        "actor_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("order_version", Integer, nullable=False),
    Column("progress_percent", Integer, nullable=False),
    Column("estimated_duration_seconds", Integer),
    Column("delay_reason_code", String(63)),
    Column("delay_message", String(240)),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_commerce_preparation_event_order",
    commerce_preparation_events.c.order_id,
    commerce_preparation_events.c.order_version,
)
commerce_preparation_idempotency = Table(
    "commerce_preparation_idempotency",
    metadata,
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("merchant_id", UUID(as_uuid=True), nullable=False),
    Column("order_id", UUID(as_uuid=True), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_version", Integer),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "actor_identity_id",
        "merchant_id",
        "idempotency_key",
        name="uq_commerce_preparation_idempotency",
    ),
    schema=AYO_SCHEMA,
)

# Field Operations owns operational partner assignments and append-only assistance evidence.
field_partners = Table(
    "field_partners",
    metadata,
    Column("partner_id", UUID(as_uuid=True), primary_key=True),
    Column("public_partner_id", String(32), nullable=False, unique=True),
    Column(
        "identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
        unique=True,
    ),
    Column("photo_reference", String(160), nullable=False),
    Column("qr_reference_hash", String(64), nullable=False, unique=True),
    Column("verification_status", String(20), nullable=False),
    Column("status", String(20), nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
field_partner_roles = Table(
    "field_partner_roles",
    metadata,
    Column("role_id", UUID(as_uuid=True), primary_key=True),
    Column("code", String(63), nullable=False, unique=True),
    Column("public_title", String(100), nullable=False),
    Column("allowed_activities", JSON, nullable=False),
    Column("active", Boolean, nullable=False),
    Column("version", Integer, nullable=False),
    schema=AYO_SCHEMA,
)
field_territories = Table(
    "field_territories",
    metadata,
    Column("territory_id", UUID(as_uuid=True), primary_key=True),
    Column("market_code", String(15), nullable=False),
    Column("region", String(100), nullable=False),
    Column("city", String(100), nullable=False),
    Column("district", String(100)),
    Column("name", String(120), nullable=False),
    Column("active", Boolean, nullable=False),
    Column("version", Integer, nullable=False),
    UniqueConstraint(
        "market_code",
        "region",
        "city",
        "district",
        "name",
        name="uq_field_territory_path",
    ),
    schema=AYO_SCHEMA,
)
field_partner_assignments = Table(
    "field_partner_assignments",
    metadata,
    Column("assignment_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "partner_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.field_partners.partner_id"),
        nullable=False,
    ),
    Column(
        "role_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.field_partner_roles.role_id"),
        nullable=False,
    ),
    Column(
        "territory_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.field_territories.territory_id"),
        nullable=False,
    ),
    Column("starts_at", DateTime(timezone=True), nullable=False),
    Column("ends_at", DateTime(timezone=True)),
    schema=AYO_SCHEMA,
)
Index(
    "ix_field_assignment_partner_time",
    field_partner_assignments.c.partner_id,
    field_partner_assignments.c.starts_at,
    field_partner_assignments.c.ends_at,
)
field_assistance_cases = Table(
    "field_assistance_cases",
    metadata,
    Column("case_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "partner_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.field_partners.partner_id"),
        nullable=False,
    ),
    Column(
        "territory_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.field_territories.territory_id"),
        nullable=False,
    ),
    Column("subject_type", String(63), nullable=False),
    Column("subject_id", UUID(as_uuid=True), nullable=False),
    Column("owner_identity_id", UUID(as_uuid=True)),
    Column("capability_code", String(63), nullable=False),
    Column("status", String(40), nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "subject_type",
        "subject_id",
        "capability_code",
        name="uq_field_case_subject_capability",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_field_case_status_territory",
    field_assistance_cases.c.status,
    field_assistance_cases.c.territory_id,
    field_assistance_cases.c.case_id,
)
field_case_evidence = Table(
    "field_case_evidence",
    metadata,
    Column("evidence_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "case_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.field_assistance_cases.case_id"),
        nullable=False,
    ),
    Column("event_type", String(80), nullable=False),
    Column("from_status", String(40)),
    Column("to_status", String(40), nullable=False),
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("actor_role", String(40), nullable=False),
    Column("evidence_reference", String(160), nullable=False),
    Column("reason_code", String(63)),
    Column("checklist", JSON),
    Column("case_version", Integer, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("case_id", "case_version", name="uq_field_case_evidence_version"),
    schema=AYO_SCHEMA,
)
field_partner_conduct_evidence = Table(
    "field_partner_conduct_evidence",
    metadata,
    Column("evidence_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "partner_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.field_partners.partner_id"),
        nullable=False,
    ),
    Column("kind", String(40), nullable=False),
    Column("evidence_reference", String(160), nullable=False),
    Column("recorded_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
field_activities = Table(
    "field_activities",
    metadata,
    Column("activity_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "partner_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.field_partners.partner_id"),
        nullable=False,
    ),
    Column(
        "assignment_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.field_partner_assignments.assignment_id"),
        nullable=False,
    ),
    Column(
        "case_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.field_assistance_cases.case_id"),
    ),
    Column(
        "territory_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.field_territories.territory_id"),
        nullable=False,
    ),
    Column("kind", String(40), nullable=False),
    Column("subject_type", String(63), nullable=False),
    Column("subject_id", UUID(as_uuid=True), nullable=False),
    Column("evidence_reference", String(160), nullable=False),
    Column("quality_status", String(63)),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_field_activity_partner_time",
    field_activities.c.partner_id,
    field_activities.c.occurred_at,
)
field_operations_events = Table(
    "field_operations_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("aggregate_type", String(40), nullable=False),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", String(80), nullable=False),
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("evidence", JSON, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
field_operations_idempotency = Table(
    "field_operations_idempotency",
    metadata,
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("operation", String(63), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_reference", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "actor_identity_id",
        "operation",
        "idempotency_key",
        name="uq_field_operations_idempotency",
    ),
    schema=AYO_SCHEMA,
)

field_performance_evidence = Table(
    "field_performance_evidence",
    metadata,
    Column("evidence_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "partner_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.field_partners.partner_id"),
        nullable=False,
    ),
    Column("territory_id", UUID(as_uuid=True)),
    Column("metric", String(48), nullable=False),
    Column("value", BigInteger, nullable=False),
    Column("unit", String(20), nullable=False),
    Column("source_domain", String(63), nullable=False),
    Column("source_event_id", UUID(as_uuid=True), nullable=False),
    Column("evidence_reference", String(160), nullable=False),
    Column("window_starts_at", DateTime(timezone=True), nullable=False),
    Column("window_ends_at", DateTime(timezone=True), nullable=False),
    Column("policy_version", String(63), nullable=False),
    Column("recorded_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column(
        "supersedes_evidence_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.field_performance_evidence.evidence_id"),
    ),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "source_domain",
        "source_event_id",
        "metric",
        name="uq_field_performance_source_metric",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_field_performance_partner_metric",
    field_performance_evidence.c.partner_id,
    field_performance_evidence.c.metric,
    field_performance_evidence.c.recorded_at,
)
Index(
    "ix_field_performance_territory_window",
    field_performance_evidence.c.territory_id,
    field_performance_evidence.c.window_ends_at,
)
field_readiness_assertions = Table(
    "field_readiness_assertions",
    metadata,
    Column("assertion_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "partner_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.field_partners.partner_id"),
        nullable=False,
    ),
    Column("requirement", String(48), nullable=False),
    Column("satisfied", Boolean, nullable=False),
    Column("source_domain", String(63), nullable=False),
    Column("source_event_id", UUID(as_uuid=True), nullable=False),
    Column("evidence_reference", String(160), nullable=False),
    Column("effective_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    Column("recorded_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "source_domain",
        "source_event_id",
        "requirement",
        name="uq_field_readiness_source_requirement",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_field_readiness_partner_requirement",
    field_readiness_assertions.c.partner_id,
    field_readiness_assertions.c.requirement,
    field_readiness_assertions.c.recorded_at,
)
field_performance_recommendations = Table(
    "field_performance_recommendations",
    metadata,
    Column("recommendation_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "partner_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.field_partners.partner_id"),
        nullable=False,
    ),
    Column("kind", String(48), nullable=False),
    Column("evidence_ids", JSON, nullable=False),
    Column("confidence_bps", Integer, nullable=False),
    Column("reasoning", String(2000), nullable=False),
    Column("risks", JSON, nullable=False),
    Column("intelligence_domain", String(63), nullable=False),
    Column("policy_version", String(63), nullable=False),
    Column("recommended_by_identity_id", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("status", String(32), nullable=False),
    schema=AYO_SCHEMA,
)
Index(
    "ix_field_recommendation_partner_time",
    field_performance_recommendations.c.partner_id,
    field_performance_recommendations.c.created_at,
)
field_performance_events = Table(
    "field_performance_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("aggregate_type", String(40), nullable=False),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", String(80), nullable=False),
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("evidence", JSON, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    schema=AYO_SCHEMA,
)
field_performance_idempotency = Table(
    "field_performance_idempotency",
    metadata,
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("operation", String(63), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_reference", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "actor_identity_id",
        "operation",
        "idempotency_key",
        name="uq_field_performance_idempotency",
    ),
    schema=AYO_SCHEMA,
)

courier_dispatch_offers = Table(
    "courier_dispatch_offers",
    metadata,
    Column("offer_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "dispatch_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_courier_dispatch_requests.dispatch_id"),
        nullable=False,
    ),
    Column("attempt_number", Integer, nullable=False),
    Column(
        "courier_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("state", String(24), nullable=False),
    Column("offered_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("resolved_at", DateTime(timezone=True)),
    Column(
        "resolution_actor_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
    ),
    Column("resolution_reason", String(80)),
    Column("version", Integer, nullable=False),
    UniqueConstraint(
        "dispatch_id", "attempt_number", name="uq_courier_dispatch_offer_attempt"
    ),
    CheckConstraint(
        "state IN ('active','accepted','declined','expired','revoked')",
        name="courier_dispatch_offer_state_valid",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_courier_dispatch_offer_active",
    courier_dispatch_offers.c.dispatch_id,
    courier_dispatch_offers.c.state,
    courier_dispatch_offers.c.expires_at,
)

courier_dispatch_assignments = Table(
    "courier_dispatch_assignments",
    metadata,
    Column("assignment_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "dispatch_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_courier_dispatch_requests.dispatch_id"),
        nullable=False,
    ),
    Column(
        "offer_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.courier_dispatch_offers.offer_id"),
        nullable=False,
        unique=True,
    ),
    Column("attempt_number", Integer, nullable=False),
    Column(
        "courier_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("state", String(32), nullable=False),
    Column("assigned_at", DateTime(timezone=True), nullable=False),
    Column("closed_at", DateTime(timezone=True)),
    Column("close_reason", String(80)),
    Column("version", Integer, nullable=False),
    CheckConstraint(
        "state IN ('assigned','released_before_pickup','cancelled_before_pickup')",
        name="courier_dispatch_assignment_state_valid",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_courier_dispatch_assignment_active",
    courier_dispatch_assignments.c.dispatch_id,
    courier_dispatch_assignments.c.state,
)

courier_dispatch_evidence = Table(
    "courier_dispatch_evidence",
    metadata,
    Column("evidence_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "dispatch_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_courier_dispatch_requests.dispatch_id"),
        nullable=False,
    ),
    Column("dispatch_version", Integer, nullable=False),
    Column("event_type", String(96), nullable=False),
    Column("actor_identity_id", UUID(as_uuid=True)),
    Column(
        "source_evidence", JSONB, nullable=False, server_default=text("'[]'::jsonb")
    ),
    Column("policy_code", String(63), nullable=False),
    Column("policy_version", Integer, nullable=False),
    Column("decision_outcome", String(40), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("evidence_hash", String(64), nullable=False),
    UniqueConstraint(
        "dispatch_id", "dispatch_version", name="uq_courier_dispatch_evidence_version"
    ),
    schema=AYO_SCHEMA,
)

catalogue_modifier_options = Table(
    "catalogue_modifier_options",
    metadata,
    Column(
        "item_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.universal_catalogue_items.item_id"),
        primary_key=True,
    ),
    Column("contract_version", Integer, primary_key=True),
    Column("code", String(63), primary_key=True),
    Column("label", String(120), nullable=False),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("version", Integer, nullable=False, server_default=text("1")),
    CheckConstraint("contract_version > 0 AND version > 0", name="positive_versions"),
    schema=AYO_SCHEMA,
)
merchant_staff_decision_authorities = Table(
    "merchant_staff_decision_authorities",
    metadata,
    Column("authority_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column(
        "merchant_location_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_branches.branch_id"),
        nullable=False,
    ),
    Column(
        "staff_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("authority_basis", String(128), nullable=False),
    Column("active", Boolean, nullable=False),
    Column("valid_from", DateTime(timezone=True), nullable=False),
    Column("valid_until", DateTime(timezone=True)),
    Column(
        "granted_by_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("revoked_at", DateTime(timezone=True)),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "merchant_id",
        "merchant_location_id",
        "staff_identity_id",
        name="uq_merchant_staff_decision_authority",
    ),
    CheckConstraint("version > 0", name="positive_version"),
    CheckConstraint(
        "valid_until IS NULL OR valid_until > valid_from", name="valid_window"
    ),
    CheckConstraint(
        "(active AND revoked_at IS NULL) OR (NOT active AND revoked_at IS NOT NULL)",
        name="revocation_consistent",
    ),
    schema=AYO_SCHEMA,
)
merchant_decision_cases = Table(
    "merchant_decision_cases",
    metadata,
    Column("decision_case_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "order_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_orders.order_id"),
        nullable=False,
        unique=True,
    ),
    Column("order_version", Integer, nullable=False),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column(
        "merchant_location_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_branches.branch_id"),
        nullable=False,
    ),
    Column("state", String(63), nullable=False),
    Column("policy_name", String(63), nullable=False),
    Column("policy_version", Integer, nullable=False),
    Column("window_started_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "state IN ('pending_merchant_decision','accepted','rejected',"
        "'decision_window_expired')",
        name="valid_state",
    ),
    CheckConstraint(
        "policy_name = 'AYO_EAT_MERCHANT_DECISION_POLICY_V1'",
        name="approved_policy",
    ),
    CheckConstraint(
        "order_version > 0 AND policy_version > 0 AND version > 0",
        name="positive_versions",
    ),
    CheckConstraint("expires_at > window_started_at", name="valid_window"),
    schema=AYO_SCHEMA,
)
Index(
    "ix_merchant_decision_due",
    merchant_decision_cases.c.state,
    merchant_decision_cases.c.expires_at,
)
merchant_decision_evidence = Table(
    "merchant_decision_evidence",
    metadata,
    Column("evidence_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "decision_case_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_decision_cases.decision_case_id"),
        nullable=False,
    ),
    Column(
        "order_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.commerce_orders.order_id"),
        nullable=False,
    ),
    Column(
        "merchant_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_profiles.merchant_id"),
        nullable=False,
    ),
    Column(
        "merchant_location_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.merchant_branches.branch_id"),
        nullable=False,
    ),
    Column(
        "authenticated_subject_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
    ),
    Column(
        "merchant_owner_identity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identities.identity_id"),
        nullable=False,
    ),
    Column("authority_basis", String(128), nullable=False),
    Column("result", String(63), nullable=False),
    Column("rejection_reason", String(63)),
    Column("policy_name", String(63), nullable=False),
    Column("policy_version", Integer, nullable=False),
    Column("decided_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    Column("evidence_hash", String(64), nullable=False),
    Column("retention_class", String(63), nullable=False),
    UniqueConstraint("decision_case_id", name="uq_merchant_decision_terminal_evidence"),
    schema=AYO_SCHEMA,
)
merchant_decision_idempotency = Table(
    "merchant_decision_idempotency",
    metadata,
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("decision_case_id", UUID(as_uuid=True), nullable=False),
    Column("operation", String(63), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_version", Integer),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "actor_identity_id",
        "operation",
        "idempotency_key",
        name="uq_merchant_decision_idempotency",
    ),
    schema=AYO_SCHEMA,
)
merchant_decision_outbox = Table(
    "merchant_decision_outbox",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column("decision_case_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", String(63), nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("safe_payload", JSONB, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    schema=AYO_SCHEMA,
)
Index(
    "ix_catalogue_modifier_item_active",
    catalogue_modifier_options.c.item_id,
    catalogue_modifier_options.c.active,
)

mobility_service_areas = Table(
    "mobility_service_areas",
    metadata,
    Column("service_area_id", UUID(as_uuid=True), primary_key=True),
    Column("internal_name", String(128), nullable=False),
    Column("customer_safe_label", String(128)),
    Column("state", String(32), nullable=False),
    Column("effective_from", DateTime(timezone=True)),
    Column("effective_until", DateTime(timezone=True)),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("internal_name"),
    CheckConstraint(
        "state IN ('planned','approved','active','temporarily_suspended','retired')",
        name="mobility_service_area_state",
    ),
    CheckConstraint("version > 0", name="mobility_service_area_positive_version"),
    CheckConstraint(
        "effective_until IS NULL OR effective_from IS NULL "
        "OR effective_until > effective_from",
        name="mobility_service_area_effective_interval",
    ),
    schema=AYO_SCHEMA,
)

mobility_service_area_geometries = Table(
    "mobility_service_area_geometries",
    metadata,
    Column("geometry_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "service_area_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.mobility_service_areas.service_area_id"),
        nullable=False,
    ),
    Column("geometry_version", Integer, nullable=False),
    Column(
        "boundary",
        Geometry(
            geometry_type="MULTIPOLYGON",
            srid=4326,
            spatial_index=False,
        ),
        nullable=False,
    ),
    Column("provenance", String(256), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "service_area_id",
        "geometry_version",
        name="uq_mobility_area_geometry_version",
    ),
    UniqueConstraint(
        "service_area_id",
        "content_hash",
        name="uq_mobility_area_geometry_hash",
    ),
    CheckConstraint(
        "geometry_version > 0",
        name="mobility_service_area_geometry_positive_version",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_mobility_service_area_geometries_boundary",
    mobility_service_area_geometries.c.boundary,
    postgresql_using="gist",
)

mobility_ride_products = Table(
    "mobility_ride_products",
    metadata,
    Column("product_code", String(63), primary_key=True),
    Column("display_key", String(63), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "product_code IN "
        "('standard','premium','airport_transfer','accessible_private_ride')",
        name="mobility_ride_product_supported",
    ),
    schema=AYO_SCHEMA,
)

mobility_product_availability = Table(
    "mobility_product_availability",
    metadata,
    Column("availability_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "service_area_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.mobility_service_areas.service_area_id"),
        nullable=False,
    ),
    Column(
        "product_code",
        String(63),
        ForeignKey("ayo.mobility_ride_products.product_code"),
        nullable=False,
    ),
    Column("state", String(32), nullable=False),
    Column("effective_from", DateTime(timezone=True), nullable=False),
    Column("effective_until", DateTime(timezone=True)),
    Column("reason_classification", String(63), nullable=False),
    Column("provenance", String(256), nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("service_area_id", "product_code"),
    CheckConstraint(
        "state IN ('available','temporarily_unavailable','not_yet_launched','retired')",
        name="mobility_product_availability_state",
    ),
    CheckConstraint(
        "effective_until IS NULL OR effective_until > effective_from",
        name="mobility_product_availability_interval",
    ),
    CheckConstraint(
        "version > 0", name="mobility_product_availability_positive_version"
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_mobility_product_availability_effective",
    mobility_product_availability.c.service_area_id,
    mobility_product_availability.c.product_code,
    mobility_product_availability.c.effective_from,
    mobility_product_availability.c.effective_until,
)

mobility_availability_evaluations = Table(
    "mobility_availability_evaluations",
    metadata,
    Column("evaluation_id", UUID(as_uuid=True), primary_key=True),
    Column("ride_request_id", UUID(as_uuid=True)),
    Column("ride_request_version", Integer),
    Column("pickup_reference", String(200), nullable=False),
    Column("product_code", String(63), nullable=False),
    Column("intended_service_at", DateTime(timezone=True), nullable=False),
    Column("evaluated_at", DateTime(timezone=True), nullable=False),
    Column("service_area_id", UUID(as_uuid=True)),
    Column("service_area_version", Integer),
    Column("geometry_id", UUID(as_uuid=True)),
    Column("geometry_version", Integer),
    Column("availability_id", UUID(as_uuid=True)),
    Column("availability_version", Integer),
    Column("outcome", String(40), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("request_id", UUID(as_uuid=True), nullable=False),
    Column("command_id", UUID(as_uuid=True)),
    Column("supersedes_evaluation_id", UUID(as_uuid=True)),
    CheckConstraint(
        "outcome IN "
        "('available','outside_service_area','temporarily_unavailable',"
        "'not_yet_launched','product_unavailable','service_area_inactive',"
        "'unknown_or_unverifiable')",
        name="mobility_availability_evaluation_outcome",
    ),
    CheckConstraint(
        "(ride_request_id IS NULL AND ride_request_version IS NULL) OR "
        "(ride_request_id IS NOT NULL AND ride_request_version > 0)",
        name="mobility_availability_evaluation_ride_reference",
    ),
    ForeignKeyConstraint(
        ["ride_request_id"],
        ["ayo.canonical_ride_requests.request_id"],
        name="fk_mobility_evaluation_ride_request",
    ),
    ForeignKeyConstraint(
        ["geometry_id"],
        ["ayo.mobility_service_area_geometries.geometry_id"],
        name="fk_mobility_evaluation_geometry",
    ),
    ForeignKeyConstraint(
        ["availability_id"],
        ["ayo.mobility_product_availability.availability_id"],
        name="fk_mobility_evaluation_availability",
    ),
    ForeignKeyConstraint(
        ["supersedes_evaluation_id"],
        ["ayo.mobility_availability_evaluations.evaluation_id"],
        name="fk_mobility_evaluation_supersedes",
    ),
    schema=AYO_SCHEMA,
)

request_access_source_adapters = Table(
    "request_access_source_adapters",
    metadata,
    Column("adapter_id", UUID(as_uuid=True), primary_key=True),
    Column("adapter_code", String(127), nullable=False),
    Column("adapter_version", Integer, nullable=False),
    Column("channel", String(32), nullable=False),
    Column("active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "adapter_code",
        "adapter_version",
        name="uq_request_access_adapter_code_version",
    ),
    CheckConstraint("adapter_version > 0", name="request_access_adapter_version"),
    CheckConstraint(
        "channel IN ('mobile_app','voice_assistance','sms','ussd',"
        "'business_portal','support_tool')",
        name="request_access_adapter_channel",
    ),
    schema=AYO_SCHEMA,
)

request_access_channel_capabilities = Table(
    "request_access_channel_capabilities",
    metadata,
    Column("capability_id", UUID(as_uuid=True), primary_key=True),
    Column("target_domain", String(127), nullable=False),
    Column("command_type", String(127), nullable=False),
    Column("channel", String(32), nullable=False),
    Column(
        "adapter_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.request_access_source_adapters.adapter_id"),
        nullable=False,
    ),
    Column("adapter_version", Integer, nullable=False),
    Column("state", String(24), nullable=False),
    Column("effective_from", DateTime(timezone=True), nullable=False),
    Column("effective_until", DateTime(timezone=True)),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "target_domain",
        "command_type",
        "channel",
        "adapter_id",
        name="uq_request_access_channel_capability",
    ),
    CheckConstraint("version > 0", name="request_access_capability_version"),
    CheckConstraint(
        "state IN ('supported','unsupported','assisted_only','degraded','retired')",
        name="request_access_capability_state",
    ),
    CheckConstraint(
        "effective_until IS NULL OR effective_until > effective_from",
        name="request_access_capability_interval",
    ),
    schema=AYO_SCHEMA,
)

request_access_continuity_references = Table(
    "request_access_continuity_references",
    metadata,
    Column("continuity_id", UUID(as_uuid=True), primary_key=True),
    Column("reference_hash", String(64), nullable=False, unique=True),
    Column(
        "authenticated_account_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identity_accounts.account_id"),
        nullable=False,
    ),
    Column(
        "acting_subject_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_subjects.subject_id"),
        nullable=False,
    ),
    Column("target_domain", String(127), nullable=False),
    Column("target_type", String(127), nullable=False),
    Column("target_id", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "reference_hash ~ '^[a-f0-9]{64}$'",
        name="request_access_continuity_hash",
    ),
    CheckConstraint(
        "expires_at > created_at",
        name="request_access_continuity_expiry",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_request_access_continuity_target",
    request_access_continuity_references.c.target_domain,
    request_access_continuity_references.c.target_type,
    request_access_continuity_references.c.target_id,
)

request_access_interaction_provenance = Table(
    "request_access_interaction_provenance",
    metadata,
    Column("provenance_id", UUID(as_uuid=True), primary_key=True),
    Column("schema_version", Integer, nullable=False),
    Column("purpose", String(24), nullable=False),
    Column("target_domain", String(127), nullable=False),
    Column("target_type", String(127), nullable=False),
    Column("target_id", String(128), nullable=False),
    Column("target_version", Integer, nullable=False),
    Column("command_type", String(127), nullable=False),
    Column("channel", String(32), nullable=False),
    Column("interaction_method", String(32), nullable=False),
    Column(
        "adapter_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.request_access_source_adapters.adapter_id"),
        nullable=False,
    ),
    Column("adapter_version", Integer, nullable=False),
    Column(
        "initiating_subject_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_subjects.subject_id"),
    ),
    Column(
        "authenticated_account_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identity_accounts.account_id"),
        nullable=False,
    ),
    Column(
        "authenticated_subject_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_subjects.subject_id"),
        nullable=False,
    ),
    Column(
        "acting_subject_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_subjects.subject_id"),
        nullable=False,
    ),
    Column(
        "requester_subject_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_subjects.subject_id"),
    ),
    Column(
        "passenger_subject_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_subjects.subject_id"),
    ),
    Column("delegated_authority_reference", String(128)),
    Column("sponsor_organization_id", UUID(as_uuid=True)),
    Column(
        "support_agent_subject_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.canonical_subjects.subject_id"),
    ),
    Column(
        "support_agent_account_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.identity_accounts.account_id"),
    ),
    Column("response_channel_preference", String(32)),
    Column("interaction_language_reference", String(127)),
    Column(
        "interface_accommodation_references",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    ),
    Column("device_capability", String(32), nullable=False),
    Column("interaction_reference", String(128)),
    Column(
        "continuity_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.request_access_continuity_references.continuity_id"),
    ),
    Column(
        "supersedes_provenance_id",
        UUID(as_uuid=True),
        ForeignKey("ayo.request_access_interaction_provenance.provenance_id"),
    ),
    Column("correction_classification", String(127)),
    Column("accepted_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True)),
    Column("command_id", UUID(as_uuid=True), nullable=False),
    Column("request_id", UUID(as_uuid=True), nullable=False),
    Column("interaction_idempotency_key", String(128), nullable=False),
    UniqueConstraint(
        "authenticated_account_id",
        "interaction_idempotency_key",
        name="uq_request_access_interaction_idempotency",
    ),
    CheckConstraint("schema_version > 0", name="request_access_schema_version"),
    CheckConstraint("target_version > 0", name="request_access_target_version"),
    CheckConstraint(
        "purpose IN ('initiation','continuation','correction','legacy_verified')",
        name="request_access_provenance_purpose",
    ),
    CheckConstraint(
        "channel IN ('mobile_app','voice_assistance','sms','ussd',"
        "'business_portal','support_tool')",
        name="request_access_provenance_channel",
    ),
    CheckConstraint(
        "interaction_method IN "
        "('self_service','delegated','support_assisted','automated_assisted')",
        name="request_access_interaction_method",
    ),
    CheckConstraint(
        "device_capability IN "
        "('rich_screen','limited_screen','voice_only','text_capable_basic_phone',"
        "'assisted_channel','unknown')",
        name="request_access_device_capability",
    ),
    CheckConstraint(
        "(purpose = 'continuation') = (continuity_id IS NOT NULL)",
        name="request_access_explicit_continuation",
    ),
    CheckConstraint(
        "(purpose = 'correction') = "
        "(supersedes_provenance_id IS NOT NULL "
        "AND correction_classification IS NOT NULL)",
        name="request_access_correction_lineage",
    ),
    CheckConstraint(
        "(interaction_method = 'delegated') = "
        "(delegated_authority_reference IS NOT NULL)",
        name="request_access_delegation_evidence",
    ),
    CheckConstraint(
        "(interaction_method = 'support_assisted') = "
        "(support_agent_subject_id IS NOT NULL "
        "AND support_agent_account_id IS NOT NULL)",
        name="request_access_support_attribution",
    ),
    schema=AYO_SCHEMA,
)
Index(
    "ix_request_access_provenance_target",
    request_access_interaction_provenance.c.target_domain,
    request_access_interaction_provenance.c.target_type,
    request_access_interaction_provenance.c.target_id,
    request_access_interaction_provenance.c.accepted_at,
)
Index(
    "ix_request_access_provenance_correlation",
    request_access_interaction_provenance.c.correlation_id,
    request_access_interaction_provenance.c.accepted_at,
)

# P2 AYO Eat Increment 3 canonical Preparation lifecycle. These tables are separate
# from the Increment 20 compatibility projection so Preparation does not write the
# canonical Commerce Order lifecycle.
preparation_staff_authorities = Table(
    "preparation_staff_authorities",
    metadata,
    Column("authority_id", UUID(as_uuid=True), primary_key=True),
    Column("merchant_id", UUID(as_uuid=True), nullable=False),
    Column("merchant_location_id", UUID(as_uuid=True), nullable=False),
    Column("staff_identity_id", UUID(as_uuid=True), nullable=False),
    Column("action", String(40), nullable=False),
    Column("authority_basis", String(128), nullable=False),
    Column("active", Boolean, nullable=False),
    Column("valid_from", DateTime(timezone=True), nullable=False),
    Column("valid_until", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "merchant_id",
        "merchant_location_id",
        "staff_identity_id",
        "action",
        name="uq_preparation_staff_action",
    ),
    CheckConstraint(
        "action IN ('start','mark_ready','declare_unable','correct_readiness')",
        name="preparation_authority_action",
    ),
    schema=AYO_SCHEMA,
)
preparation_cases = Table(
    "preparation_cases",
    metadata,
    Column("preparation_case_id", UUID(as_uuid=True), primary_key=True),
    Column("decision_case_id", UUID(as_uuid=True), nullable=False, unique=True),
    Column("decision_evidence_id", UUID(as_uuid=True), nullable=False, unique=True),
    Column("order_id", UUID(as_uuid=True), nullable=False, unique=True),
    Column("order_version", Integer, nullable=False),
    Column("merchant_id", UUID(as_uuid=True), nullable=False),
    Column("merchant_location_id", UUID(as_uuid=True), nullable=False),
    Column("state", String(40), nullable=False),
    Column("policy_name", String(63), nullable=False),
    Column("policy_version", Integer, nullable=False),
    Column("estimated_ready_at", DateTime(timezone=True)),
    Column("overdue_observed_at", DateTime(timezone=True)),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "state IN ('pending_preparation','preparing','ready_for_pickup',"
        "'unable_to_prepare')",
        name="preparation_case_state",
    ),
    CheckConstraint(
        "version > 0 AND order_version > 0 AND policy_version > 0",
        name="preparation_case_positive_versions",
    ),
    schema=AYO_SCHEMA,
)
preparation_evidence = Table(
    "preparation_evidence",
    metadata,
    Column("evidence_id", UUID(as_uuid=True), primary_key=True),
    Column("preparation_case_id", UUID(as_uuid=True), nullable=False),
    Column("case_version", Integer, nullable=False),
    Column("order_id", UUID(as_uuid=True), nullable=False),
    Column("order_version", Integer, nullable=False),
    Column("decision_evidence_id", UUID(as_uuid=True), nullable=False),
    Column("merchant_id", UUID(as_uuid=True), nullable=False),
    Column("merchant_location_id", UUID(as_uuid=True), nullable=False),
    Column("authenticated_subject_id", UUID(as_uuid=True), nullable=False),
    Column("merchant_owner_identity_id", UUID(as_uuid=True), nullable=False),
    Column("authority_basis", String(128), nullable=False),
    Column("event_type", String(80), nullable=False),
    Column("from_state", String(40)),
    Column("to_state", String(40), nullable=False),
    Column("failure_reason", String(80)),
    Column("correction_reason", String(80)),
    Column("policy_name", String(63), nullable=False),
    Column("policy_version", Integer, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True), nullable=False),
    Column("evidence_hash", String(64), nullable=False),
    Column("retention_class", String(80), nullable=False),
    UniqueConstraint(
        "preparation_case_id", "case_version", name="uq_preparation_evidence_version"
    ),
    schema=AYO_SCHEMA,
)
preparation_idempotency = Table(
    "preparation_idempotency",
    metadata,
    Column("actor_identity_id", UUID(as_uuid=True), nullable=False),
    Column("preparation_case_id", UUID(as_uuid=True), nullable=False),
    Column("operation", String(40), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_version", Integer),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "actor_identity_id",
        "operation",
        "idempotency_key",
        name="uq_preparation_idempotency",
    ),
    schema=AYO_SCHEMA,
)
preparation_outbox = Table(
    "preparation_outbox",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column("preparation_case_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", String(80), nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("safe_payload", JSONB, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    schema=AYO_SCHEMA,
)
Index(
    "ix_preparation_cases_merchant_state",
    preparation_cases.c.merchant_id,
    preparation_cases.c.merchant_location_id,
    preparation_cases.c.state,
)
Index(
    "uq_request_access_single_initiation",
    request_access_interaction_provenance.c.target_domain,
    request_access_interaction_provenance.c.target_type,
    request_access_interaction_provenance.c.target_id,
    unique=True,
    postgresql_where=request_access_interaction_provenance.c.purpose == "initiation",
)
Index(
    "ix_mobility_availability_evaluations_current",
    mobility_availability_evaluations.c.ride_request_id,
    mobility_availability_evaluations.c.evaluated_at,
)
