from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class RateLimitPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")]
    capacity: Annotated[int, Field(ge=1, le=1_000_000)]
    refill_tokens: Annotated[Decimal, Field(gt=0, le=1_000_000)]
    refill_period_seconds: Annotated[int, Field(ge=1, le=86_400)]


class RateLimitDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    remaining: Annotated[Decimal, Field(ge=0)]
    retry_after_seconds: Annotated[int, Field(ge=0)]
