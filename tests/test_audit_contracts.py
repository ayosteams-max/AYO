from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome


def audit_event(**changes) -> AuditEvent:
    values = {
        "actor_type": ActorType.SYSTEM,
        "action": "ride.state.changed",
        "resource_type": "ride",
        "resource_id": "RIDE-123",
        "outcome": AuditOutcome.SUCCESS,
        "correlation_id": uuid4(),
        "source_module": "rides",
    }
    values.update(changes)
    return AuditEvent(**values)


def test_contract_has_uuid_identifiers_utc_timestamps_and_links() -> None:
    causation_id = uuid4()
    event = audit_event(
        actor_type=ActorType.DRIVER,
        actor_id="driver_01",
        causation_id=causation_id,
        request_id=uuid4(),
        safe_metadata={"state_from": "offered", "state_to": "accepted"},
    )

    assert isinstance(event.event_id, UUID)
    assert event.occurred_at.tzinfo is UTC
    assert event.recorded_at.tzinfo is UTC
    assert event.causation_id == causation_id
    assert event.safe_metadata["state_to"] == "accepted"


def test_aware_timestamp_is_normalized_to_utc_and_naive_is_rejected() -> None:
    offset_time = datetime.now(UTC).astimezone(timezone(timedelta(hours=3)))
    assert audit_event(occurred_at=offset_time).occurred_at.tzinfo is UTC

    with pytest.raises(ValidationError, match="timezone-aware"):
        audit_event(occurred_at=datetime(2026, 7, 15))


@pytest.mark.parametrize(
    "metadata",
    [
        {"password": "sensitive-value-one"},
        {"otp_code": "123456"},
        {"access_token": "sensitive-value-two"},
        {"authorization": "Bearer-secret"},
        {"phone_number": "+251900000000"},
        {"request_body": "anything"},
    ],
)
def test_prohibited_metadata_is_rejected_without_echoing_value(metadata) -> None:
    with pytest.raises(ValidationError) as error:
        audit_event(safe_metadata=metadata)

    assert next(iter(metadata.values())) not in str(error.value)
    assert "prohibited field" in str(error.value)


def test_metadata_allowlist_rejects_unknown_nested_and_unsafe_values() -> None:
    for metadata in (
        {"arbitrary": "value"},
        {"category": {"nested": "value"}},
        {"category": "https://secret.example"},
        {"category": 1.5},
    ):
        with pytest.raises(ValidationError):
            audit_event(safe_metadata=metadata)


def test_contract_is_immutable_and_taxonomies_are_complete() -> None:
    event = audit_event()
    with pytest.raises(ValidationError):
        event.outcome = AuditOutcome.FAILED

    assert {item.value for item in ActorType} >= {
        "anonymous",
        "rider",
        "driver",
        "staff",
        "administrator",
        "system",
        "service",
    }
    assert {item.value for item in AuditOutcome} == {
        "success",
        "denied",
        "failed",
        "cancelled",
    }
