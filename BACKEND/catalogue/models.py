from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ItemKind(StrEnum):
    PRODUCT = "product"
    MEAL = "meal"
    SERVICE = "service"
    DIGITAL_ITEM = "digital_item"


class ItemStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ItemAvailability(StrEnum):
    AVAILABLE = "available"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    OUT_OF_STOCK = "out_of_stock"
    HIDDEN = "hidden"


class ItemVisibility(StrEnum):
    PUBLIC = "public"
    UNLISTED = "unlisted"
    PRIVATE = "private"


class CatalogueCategory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    category_id: UUID = Field(default_factory=uuid4)
    merchant_id: UUID
    parent_category_id: UUID | None = None
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    normalized_name: str = Field(pattern=r"^[a-z0-9][a-z0-9 -]{1,119}$", max_length=120)
    active: bool = True
    sort_order: int = Field(default=0, ge=0, le=1_000_000)
    version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def category_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("category timestamps must be timezone-aware")
        return value.astimezone(UTC)


class MediaReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    media_id: UUID = Field(default_factory=uuid4)
    opaque_reference: str = Field(min_length=16, max_length=240)
    alt_text: str = Field(min_length=2, max_length=240)
    sort_order: int = Field(default=0, ge=0, le=100)
    moderation_state: str = Field(
        default="pending", pattern=r"^(pending|approved|rejected)$"
    )


class CatalogueItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    item_id: UUID = Field(default_factory=uuid4)
    merchant_id: UUID
    category_id: UUID | None = None
    branch_id: UUID | None = None
    kind: ItemKind
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    media: tuple[MediaReference, ...] = Field(default_factory=tuple, max_length=12)
    status: ItemStatus = ItemStatus.DRAFT
    availability: ItemAvailability = ItemAvailability.HIDDEN
    visibility: ItemVisibility = ItemVisibility.PRIVATE
    tags: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    search_keywords: tuple[str, ...] = Field(default_factory=tuple, max_length=30)
    base_price_minor: int | None = Field(default=None, ge=0, le=100_000_000_00)
    currency: str = Field(default="ETB", pattern=r"^ETB$")
    variant_contract_version: int | None = Field(default=None, ge=1)
    modifier_contract_version: int | None = Field(default=None, ge=1)
    source_item_id: UUID | None = None
    version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("catalogue timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("tags", "search_keywords")
    @classmethod
    def normalized_terms(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(
            dict.fromkeys(value.strip().casefold() for value in values if value.strip())
        )
        if any(len(value) > 63 for value in normalized):
            raise ValueError("catalogue term exceeds 63 characters")
        return normalized

    @model_validator(mode="after")
    def archive_is_hidden(self) -> "CatalogueItem":
        if self.status is ItemStatus.ARCHIVED and (
            self.availability is not ItemAvailability.HIDDEN
            or self.visibility is not ItemVisibility.PRIVATE
        ):
            raise ValueError("archived items must be hidden and private")
        return self


class CatalogueQuality(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    score: int = Field(ge=0, le=100)
    missing: tuple[str, ...]
    photo_score: int = Field(ge=0, le=100)
    description_score: int = Field(ge=0, le=100)
    pricing_score: int = Field(ge=0, le=100)
    category_score: int = Field(ge=0, le=100)
    availability_score: int = Field(ge=0, le=100)
    visibility_score: int = Field(ge=0, le=100)


class CatalogueItemView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    item: CatalogueItem
    quality: CatalogueQuality


class MerchantCatalogueSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    merchant_id: UUID
    item_count: int = Field(ge=0)
    active_count: int = Field(ge=0)
    completion_score: int = Field(ge=0, le=100)
    media_quality_score: int = Field(ge=0, le=100)
    readiness_score: int = Field(ge=0, le=100)
    missing_information: tuple[str, ...]
    business_profile_score: int = Field(ge=0, le=100)
    verification_score: int = Field(ge=0, le=100)
    operating_hours_score: int = Field(ge=0, le=100)
    orders_placeholder: str = "Coming Soon"
    sales_placeholder: str = "Coming Soon"
    analytics_placeholder: str = "Coming Soon"
