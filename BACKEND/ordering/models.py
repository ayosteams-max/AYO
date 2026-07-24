from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrderState(StrEnum):
    WAITING_FOR_MERCHANT_CONFIRMATION = "waiting_for_merchant_confirmation"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PREPARING = "preparing"
    READY_FOR_PICKUP = "ready_for_pickup"


class BasketLine(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    item_id: UUID
    quantity: int = Field(ge=1, le=99)
    observed_version: int = Field(ge=1)
    variant_selections: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    modifier_selections: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    customer_instructions: str | None = Field(default=None, max_length=500)

    @field_validator("modifier_selections")
    @classmethod
    def modifier_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip().casefold() for value in values)
        if len(set(normalized)) != len(normalized):
            raise ValueError("modifier selections must be unique")
        if any(
            not value
            or len(value) > 63
            or not value[0].isalpha()
            or any(
                char not in "abcdefghijklmnopqrstuvwxyz0123456789_.-" for char in value
            )
            for value in normalized
        ):
            raise ValueError("modifier selection code is invalid")
        return normalized

    @field_validator("customer_instructions")
    @classmethod
    def safe_instructions(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            return None
        if any(ord(char) < 32 for char in normalized):
            raise ValueError("customer instructions contain control characters")
        return normalized


class OrderLineEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    item_id: UUID
    item_version: int = Field(ge=1)
    name: str = Field(min_length=2, max_length=160)
    kind: str = Field(min_length=3, max_length=24)
    category_id: UUID | None = None
    quantity: int = Field(ge=1, le=99)
    unit_price_minor: int = Field(ge=0)
    line_total_minor: int = Field(ge=0)
    currency: str = Field(pattern=r"^ETB$")
    modifier_selections: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    customer_instructions: str | None = Field(default=None, max_length=500)


class OrderPricingEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    authority: str = "commerce_pricing"
    policy_version: str = Field(min_length=3, max_length=63)
    subtotal_minor: int = Field(ge=0)
    currency: str = Field(pattern=r"^ETB$")
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class CanonicalOrder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    order_id: UUID = Field(default_factory=uuid4)
    customer_identity_id: UUID
    merchant_id: UUID
    merchant_display_name: str = Field(min_length=2, max_length=120)
    state: OrderState = OrderState.WAITING_FOR_MERCHANT_CONFIRMATION
    lines: tuple[OrderLineEvidence, ...] = Field(min_length=1, max_length=50)
    pricing: OrderPricingEvidence
    availability_evaluation_id: UUID | None = None
    composition_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    access_interaction_id: UUID | None = None
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    version: int = Field(default=1, ge=1)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("order timestamp must be timezone-aware")
        return value.astimezone(UTC)


class PublicMerchant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    merchant_id: UUID
    display_name: str
    capability_code: str
    market_code: str


class PublicCatalogueItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    item_id: UUID
    merchant_id: UUID
    category_id: UUID | None
    kind: str
    name: str
    description: str | None
    media: tuple[dict[str, object], ...]
    availability: str
    tags: tuple[str, ...]
    base_price_minor: int
    currency: str
    version: int


class PublicCategory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    category_id: UUID
    parent_category_id: UUID | None
    name: str
    description: str | None
    sort_order: int
