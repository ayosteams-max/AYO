from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from BACKEND.active_ride.models import PickupConfidence, PickupRecommendation


class PickupCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    place_id: Annotated[str, Field(min_length=8, max_length=128)]
    fallback_place_id: Annotated[str, Field(min_length=8, max_length=128)] | None = None
    entrance_or_gate: str | None = Field(default=None, max_length=120)
    terminal_or_zone: str | None = Field(default=None, max_length=80)
    walking_min_seconds: int | None = Field(default=None, ge=0, le=7200)
    walking_max_seconds: int | None = Field(default=None, ge=0, le=7200)
    approach_guidance: str = Field(max_length=300)
    legal_access_verified: bool = False
    accessibility_supported: bool = False
    divided_road_conflict: bool = False
    temporary_closure: bool = False
    source_stale: bool = False
    provider_available: bool = True
    cached: bool = False
    material_change: bool = False


def recommend_pickup(
    ride_id: UUID, candidate: PickupCandidate, *, now: datetime, ttl_seconds: int = 900
) -> PickupRecommendation:
    reasons: list[str] = []
    if candidate.temporary_closure:
        reasons.append("temporary_closure_avoided")
    if candidate.divided_road_conflict:
        reasons.append("locations_on_divided_road")
    if candidate.accessibility_supported:
        reasons.append("accessible_route_available")
    if candidate.legal_access_verified:
        reasons.append("legal_road_access")
    if candidate.cached:
        reasons.append("cached_guidance_only")
    if not candidate.provider_available:
        reasons.append("provider_unavailable")
    if candidate.source_stale:
        reasons.append("source_stale")
    if not candidate.provider_available or candidate.source_stale:
        confidence = PickupConfidence.INSUFFICIENT_DATA
    elif candidate.temporary_closure or candidate.divided_road_conflict:
        confidence = PickupConfidence.LOW
    elif candidate.legal_access_verified and candidate.accessibility_supported:
        confidence = PickupConfidence.VERIFIED
    elif candidate.legal_access_verified:
        confidence = PickupConfidence.HIGH
    else:
        confidence = PickupConfidence.MEDIUM
    return PickupRecommendation(
        ride_id=ride_id,
        primary_place_id=candidate.place_id,
        fallback_place_id=candidate.fallback_place_id,
        entrance_or_gate=candidate.entrance_or_gate,
        terminal_or_zone=candidate.terminal_or_zone,
        walking_time_min_seconds=candidate.walking_min_seconds,
        walking_time_max_seconds=candidate.walking_max_seconds,
        driver_approach_guidance=candidate.approach_guidance,
        accessibility_supported=candidate.accessibility_supported,
        confidence=confidence,
        source_freshness={
            "pickup_context": "stale" if candidate.source_stale else "fresh"
        },
        reason_codes=tuple(reasons or ["pickup_candidate_available"]),
        generated_at=now,
        expires_at=now + timedelta(seconds=ttl_seconds),
        material_change=candidate.material_change,
        change_status="proposed" if candidate.material_change else "not_required",
    )
