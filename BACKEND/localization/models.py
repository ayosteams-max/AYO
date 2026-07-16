from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TextDirection(StrEnum):
    LEFT_TO_RIGHT = "ltr"
    RIGHT_TO_LEFT = "rtl"


class WordingClass(StrEnum):
    GENERAL = "general"
    LEGAL = "legal"
    SAFETY = "safety"
    IDENTITY = "identity"
    PRICING = "pricing"
    FINANCIAL = "financial"
    EMERGENCY = "emergency"


LanguageTag = Annotated[
    str, Field(pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$", max_length=63)
]


class LanguagePreference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    preference_id: UUID = Field(default_factory=uuid4)
    identity_id: UUID
    preferred_language: LanguageTag
    device_language: LanguageTag | None = None
    fallback_chain: tuple[LanguageTag, ...]
    version: Annotated[int, Field(ge=1)] = 1
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Language-preference timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def no_cycles(self) -> "LanguagePreference":
        chain = (self.preferred_language, *self.fallback_chain)
        normalized = [item.lower() for item in chain]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Localization fallback chain contains a cycle")
        return self


class TranslationKey(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")]
    version: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,62}$")]
    wording_class: WordingClass
    human_review_required: bool
    accessibility_text_key: (
        Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")] | None
    ) = None
    plural_parameters: tuple[
        Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")], ...
    ] = ()

    @model_validator(mode="after")
    def critical_is_reviewed(self) -> "TranslationKey":
        if (
            self.wording_class is not WordingClass.GENERAL
            and not self.human_review_required
        ):
            raise ValueError("Critical wording requires human review")
        return self


class LanguagePackManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    language_tag: LanguageTag
    pack_version: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,62}$")
    direction: TextDirection
    fallback_language: LanguageTag | None = None
    offline_manifest_reference: str | None = Field(default=None, max_length=256)
    date_format_profile: str = Field(max_length=63)
    number_format_profile: str = Field(max_length=63)
    currency_format_profile: str = Field(max_length=63)
    approved_at: datetime | None = None

    @field_validator("approved_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Language-pack approval timestamp must be timezone-aware")
        return value.astimezone(UTC)


class LocalizedMessageRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    translation_key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    parameters: dict[str, str | int] = Field(default_factory=dict, max_length=12)


DISPATCH_MESSAGES = {
    "dispatch.accepted": "dispatch.request.accepted",
    "dispatch.searching": "dispatch.search.nearby_driver",
    "dispatch.no_suitable_driver": "dispatch.search.none_available",
    "dispatch.offer_expired": "dispatch.offer.expired",
    "dispatch.driver_assigned": "dispatch.assignment.created",
    "dispatch.cancelled": "dispatch.request.cancelled",
    "dispatch.retry_safe": "dispatch.request.retry_safe",
    "dispatch.location_stale": "dispatch.location.update_required",
    "dispatch.zone_unsupported": "dispatch.zone.unsupported",
}


def message_ref(reason_code: str) -> LocalizedMessageRef:
    try:
        key = DISPATCH_MESSAGES[reason_code]
    except KeyError as error:
        raise KeyError("Missing dispatch translation key") from error
    return LocalizedMessageRef(reason_code=reason_code, translation_key=key)


def resolve_available_language(
    preference: LanguagePreference, available_language_tags: frozenset[str]
) -> tuple[str | None, tuple[str, ...]]:
    available = {tag.lower(): tag for tag in available_language_tags}
    missing: list[str] = []
    for tag in (preference.preferred_language, *preference.fallback_chain):
        selected = available.get(tag.lower())
        if selected is not None:
            return selected, tuple(missing)
        missing.append(tag)
    return None, tuple(missing)
