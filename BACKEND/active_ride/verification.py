from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class QrPickupChallenge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    challenge_reference: UUID
    ride_id: UUID
    assignment_id: UUID
    expires_at: datetime


class QrPickupChallengeProvider(Protocol):
    """Optional provider-neutral signed challenge; never sufficient alone to start."""

    def issue(
        self, *, ride_id: UUID, assignment_id: UUID, expires_at: datetime
    ) -> QrPickupChallenge: ...

    def validate(
        self, challenge: str, *, ride_id: UUID, assignment_id: UUID
    ) -> bool: ...


class DisabledQrPickupChallengeProvider:
    def issue(
        self, *, ride_id: UUID, assignment_id: UUID, expires_at: datetime
    ) -> QrPickupChallenge:
        del ride_id, assignment_id, expires_at
        raise RuntimeError("QR pickup verification is not configured")

    def validate(self, challenge: str, *, ride_id: UUID, assignment_id: UUID) -> bool:
        del challenge, ride_id, assignment_id
        return False
