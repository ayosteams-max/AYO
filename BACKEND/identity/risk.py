from enum import StrEnum
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field


class RiskState(StrEnum):
    UNKNOWN = "unknown"
    LOW = "low"
    ELEVATED = "elevated"
    HIGH = "high"
    RESTRICTED = "restricted"


class AuthenticationRiskContext(BaseModel):
    """Minimized, versioned signals; no raw IP, device or location values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: Annotated[str, Field(min_length=1, max_length=32)]
    device_reference: Annotated[bytes, Field(min_length=32, max_length=32)] | None = (
        None
    )
    ip_risk_reference: Annotated[bytes, Field(min_length=32, max_length=32)] | None = (
        None
    )
    new_device: bool = False
    recent_recovery: bool = False
    replay_detected: bool = False
    repeated_failures: Annotated[int, Field(ge=0, le=10_000)] = 0


class RiskEvaluator(Protocol):
    def evaluate(self, context: AuthenticationRiskContext) -> RiskState: ...
