from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from BACKEND.pricing.models import RouteMetrics


class RouteMetricProvider(Protocol):
    """Provider-neutral boundary; implementations supply evidence, never fare totals."""

    def metrics(
        self,
        *,
        pickup_reference: UUID,
        destination_reference: UUID,
        observed_at: datetime,
    ) -> RouteMetrics: ...


class CertifiedPricingEvidenceReference(BaseModel):
    """Inactive seam for separately approved Mission 20 or other certified evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_reference: str = Field(min_length=8, max_length=128)
    evidence_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$")
    authority_policy_version: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,62}$")
    certified_at: datetime
