import re
from collections.abc import Iterable
from datetime import datetime
from uuid import uuid4

from BACKEND.catalogue.models import (
    CatalogueItem,
    CatalogueQuality,
    ItemAvailability,
    ItemStatus,
    ItemVisibility,
)


class CatalogueConflict(ValueError):
    pass


def normalize_search(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def quality(item: CatalogueItem) -> CatalogueQuality:
    approved_photos = tuple(
        media for media in item.media if media.moderation_state == "approved"
    )
    photo = 100 if approved_photos else 0
    description = 100 if item.description and len(item.description.strip()) >= 20 else 0
    pricing = 100 if item.base_price_minor is not None else 0
    category = 100 if item.category_id is not None else 0
    availability = 100 if item.availability is not ItemAvailability.HIDDEN else 0
    visibility = 100 if item.visibility is ItemVisibility.PUBLIC else 0
    missing = []
    if not photo:
        missing.append("approved_photo")
    if not description:
        missing.append("description")
    if not pricing:
        missing.append("base_price")
    if not category:
        missing.append("category")
    if not availability:
        missing.append("availability")
    if not visibility:
        missing.append("visibility")
    score = (
        photo * 15
        + description * 20
        + pricing * 20
        + category * 15
        + availability * 15
        + visibility * 15
    ) // 100
    return CatalogueQuality(
        score=score,
        missing=tuple(missing),
        photo_score=photo,
        description_score=description,
        pricing_score=pricing,
        category_score=category,
        availability_score=availability,
        visibility_score=visibility,
    )


def duplicate_item(item: CatalogueItem, *, at: datetime) -> CatalogueItem:
    return CatalogueItem.model_validate(
        {
            **item.model_dump(),
            "item_id": uuid4(),
            "name": f"{item.name} copy"[:160],
            "status": ItemStatus.DRAFT,
            "availability": ItemAvailability.HIDDEN,
            "visibility": ItemVisibility.PRIVATE,
            "source_item_id": item.item_id,
            "version": 1,
            "created_at": at,
            "updated_at": at,
        }
    )


def aggregate_quality(
    items: Iterable[CatalogueItem],
) -> tuple[int, int, tuple[str, ...]]:
    values = tuple(items)
    if not values:
        return 0, 0, ("catalogue_item",)
    reports = tuple(
        quality(item) for item in values if item.status is not ItemStatus.ARCHIVED
    )
    if not reports:
        return 0, 0, ("active_catalogue_item",)
    completion = sum(report.score for report in reports) // len(reports)
    media = sum(report.photo_score for report in reports) // len(reports)
    missing = tuple(sorted({field for report in reports for field in report.missing}))
    return completion, media, missing
