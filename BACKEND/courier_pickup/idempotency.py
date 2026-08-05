import hashlib
import json
import unicodedata
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from BACKEND.courier_pickup.models import (
    CourierPickupAction,
    CourierPickupExceptionReason,
    CourierPickupView,
)

DIGEST_VERSION = 1
RESPONSE_SCHEMA_VERSION = 1
SNAPSHOT_MAX_BYTES = 65_536
_DOMAIN_SEPARATOR = b"AYO_COURIER_PICKUP_COMMAND_V1\0"


def _uuid(value: UUID | None) -> str | None:
    return None if value is None else str(value)


def _text(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("idempotency timestamps must be timezone-aware")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class CourierPickupCommandDigestV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    digest_schema_version: int = DIGEST_VERSION
    pickup_id: UUID
    actor_identity_id: UUID
    acting_for_identity_id: UUID | None
    action: CourierPickupAction
    expected_version: int
    merchant_id: UUID | None
    assigned_courier_identity_id: UUID
    assignment_id: UUID
    assignment_version: int
    location_evidence_reference: UUID | None
    location_evidence_version: int | None
    location_evidence_observed_at: datetime | None
    reason: CourierPickupExceptionReason | None
    assignment_source_reference: UUID
    assignment_source_version: int
    pickup_policy_code: str
    pickup_policy_version: int

    def canonical_bytes(self) -> bytes:
        if self.digest_schema_version != DIGEST_VERSION:
            raise ValueError("unsupported Courier Pickup digest version")
        payload: dict[str, Any] = {
            "digest_schema_version": self.digest_schema_version,
            "pickup_id": _uuid(self.pickup_id),
            "actor_identity_id": _uuid(self.actor_identity_id),
            "acting_for_identity_id": _uuid(self.acting_for_identity_id),
            "action": _text(self.action.value),
            "expected_version": self.expected_version,
            "merchant_id": _uuid(self.merchant_id),
            "assigned_courier_identity_id": _uuid(self.assigned_courier_identity_id),
            "assignment_id": _uuid(self.assignment_id),
            "assignment_version": self.assignment_version,
            "location_evidence_reference": _uuid(self.location_evidence_reference),
            "location_evidence_version": self.location_evidence_version,
            "location_evidence_observed_at": _timestamp(
                self.location_evidence_observed_at
            ),
            "reason": None if self.reason is None else _text(self.reason.value),
            "assignment_source_reference": _uuid(self.assignment_source_reference),
            "assignment_source_version": self.assignment_source_version,
            "pickup_policy_code": _text(self.pickup_policy_code),
            "pickup_policy_version": self.pickup_policy_version,
        }
        return json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False
        ).encode("utf-8")

    def hexdigest(self) -> str:
        return hashlib.sha256(_DOMAIN_SEPARATOR + self.canonical_bytes()).hexdigest()


class CourierPickupReplaySnapshotV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    response_schema_version: int = RESPONSE_SCHEMA_VERSION
    response: CourierPickupView

    def encode(self) -> dict[str, Any]:
        if self.response_schema_version != RESPONSE_SCHEMA_VERSION:
            raise ValueError("unsupported Courier Pickup response schema version")
        value = self.model_dump(mode="json")
        encoded = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        if len(encoded) > SNAPSHOT_MAX_BYTES:
            raise ValueError("Courier Pickup replay snapshot exceeds size limit")
        return value

    @classmethod
    def decode(cls, value: object) -> CourierPickupView:
        try:
            snapshot = cls.model_validate(value)
            parsed = snapshot.model_dump(mode="json")
            canonical = json.dumps(
                parsed,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise ValueError("malformed Courier Pickup replay snapshot") from error
        if snapshot.response_schema_version != RESPONSE_SCHEMA_VERSION:
            raise ValueError("unsupported Courier Pickup response schema version")
        if value != parsed:
            raise ValueError("malformed Courier Pickup replay snapshot")
        if len(canonical) > SNAPSHOT_MAX_BYTES:
            raise ValueError("Courier Pickup replay snapshot exceeds size limit")
        return snapshot.response
