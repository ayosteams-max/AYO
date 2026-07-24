from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.catalogue.engine import (
    aggregate_quality,
    duplicate_item,
    normalize_search,
    quality,
)
from BACKEND.catalogue.models import (
    CatalogueItem,
    ItemAvailability,
    ItemKind,
    ItemStatus,
    ItemVisibility,
    MediaReference,
)
from BACKEND.config.settings import AppEnvironment, Settings

NOW = datetime(2026, 7, 20, 12, tzinfo=UTC)


def complete_item() -> CatalogueItem:
    return CatalogueItem(
        merchant_id=uuid4(),
        category_id=uuid4(),
        kind=ItemKind.PRODUCT,
        name="Ethiopian Coffee",
        description="Freshly roasted Ethiopian coffee beans.",
        media=(
            MediaReference(
                opaque_reference="media-reference-0001",
                alt_text="Bag of Ethiopian coffee",
                moderation_state="approved",
            ),
        ),
        status=ItemStatus.ACTIVE,
        availability=ItemAvailability.AVAILABLE,
        visibility=ItemVisibility.PUBLIC,
        tags=("Coffee", "coffee"),
        search_keywords=("Ethiopian Coffee",),
        base_price_minor=25_000,
        created_at=NOW,
        updated_at=NOW,
    )


def test_quality_score_is_explainable_and_complete_item_scores_100() -> None:
    report = quality(complete_item())
    assert report.score == 100
    assert report.missing == ()
    draft = complete_item().model_copy(
        update={
            "category_id": None,
            "media": (),
            "description": None,
            "base_price_minor": None,
            "availability": ItemAvailability.HIDDEN,
            "visibility": ItemVisibility.PRIVATE,
        }
    )
    assert quality(draft).missing == (
        "approved_photo",
        "description",
        "base_price",
        "category",
        "availability",
        "visibility",
    )


def test_duplicate_is_new_private_hidden_draft_without_pairing_transaction_state() -> (
    None
):
    source = complete_item()
    result = duplicate_item(source, at=NOW)
    assert result.item_id != source.item_id
    assert result.source_item_id == source.item_id
    assert result.status is ItemStatus.DRAFT
    assert result.availability is ItemAvailability.HIDDEN
    assert result.visibility is ItemVisibility.PRIVATE


def test_archived_item_cannot_be_public_or_available() -> None:
    with pytest.raises(ValidationError, match="archived items must be hidden"):
        CatalogueItem.model_validate(
            {**complete_item().model_dump(), "status": ItemStatus.ARCHIVED}
        )


def test_search_normalization_and_terms_are_deterministic() -> None:
    assert normalize_search("  Fresh   COFFEE ") == "fresh coffee"
    assert complete_item().tags == ("coffee",)


def test_catalogue_health_aggregation_ignores_archived_items() -> None:
    complete = complete_item()
    archived = complete.model_copy(
        update={
            "item_id": uuid4(),
            "status": ItemStatus.ARCHIVED,
            "availability": ItemAvailability.HIDDEN,
            "visibility": ItemVisibility.PRIVATE,
        }
    )
    assert aggregate_quality((complete, archived)) == (100, 100, ())


def test_catalogue_runtime_is_disabled_and_fails_closed_in_production() -> None:
    assert (
        Settings(  # type: ignore[call-arg]  # pydantic-settings init kwarg
            _env_file=None,
            DEBUG=False,
        ).CATALOGUE_PLATFORM_ENABLED
        is False
    )
    with pytest.raises(
        ValidationError, match="Catalogue Platform production activation"
    ):
        Settings(  # type: ignore[call-arg]  # pydantic-settings init kwarg
            _env_file=None,
            DEBUG=False,
            ENVIRONMENT=AppEnvironment.PRODUCTION,
            CATALOGUE_PLATFORM_ENABLED=True,
        )
