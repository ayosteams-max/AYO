from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RefreshRotationOutcome(StrEnum):
    ROTATED = "rotated"
    REPLAY_DETECTED = "replay_detected"
    DENIED = "denied"


class RefreshRotationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome: RefreshRotationOutcome
    family_id: UUID
    session_id: UUID
    rotation_counter: int
