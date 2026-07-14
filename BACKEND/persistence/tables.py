from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
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
