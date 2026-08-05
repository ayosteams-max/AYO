from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from BACKEND.courier_pickup.idempotency import (
    DIGEST_VERSION,
    SNAPSHOT_MAX_BYTES,
    CourierPickupCommandDigestV1,
    CourierPickupReplaySnapshotV1,
)
from BACKEND.courier_pickup.models import (
    CourierPickupAction,
    CourierPickupRecord,
    CourierPickupState,
    CourierPickupView,
)

PICKUP_ID = UUID("10000000-0000-4000-8000-000000000001")
ACTOR_ID = UUID("10000000-0000-4000-8000-000000000002")
MERCHANT_ID = UUID("10000000-0000-4000-8000-000000000003")
ASSIGNMENT_ID = UUID("10000000-0000-4000-8000-000000000004")
LOCATION_ID = UUID("10000000-0000-4000-8000-000000000005")
NOW = datetime(2026, 8, 5, 12, 34, 56, 123456, tzinfo=UTC)


def command(**changes) -> CourierPickupCommandDigestV1:
    values = {
        "pickup_id": PICKUP_ID,
        "actor_identity_id": ACTOR_ID,
        "acting_for_identity_id": None,
        "action": CourierPickupAction.MARK_ARRIVED,
        "expected_version": 2,
        "merchant_id": None,
        "assigned_courier_identity_id": ACTOR_ID,
        "assignment_id": ASSIGNMENT_ID,
        "assignment_version": 3,
        "location_evidence_reference": LOCATION_ID,
        "location_evidence_version": 4,
        "location_evidence_observed_at": NOW,
        "reason": None,
        "assignment_source_reference": ASSIGNMENT_ID,
        "assignment_source_version": 3,
        "pickup_policy_code": "AYO_COURIER_PICKUP_POLICY_V1",
        "pickup_policy_version": 1,
    }
    values.update(changes)
    return CourierPickupCommandDigestV1.model_validate(values)


def view() -> CourierPickupView:
    record = CourierPickupRecord(
        pickup_id=PICKUP_ID,
        dispatch_id=UUID("10000000-0000-4000-8000-000000000006"),
        assignment_id=ASSIGNMENT_ID,
        assignment_version=3,
        attempt_number=1,
        order_id=UUID("10000000-0000-4000-8000-000000000007"),
        merchant_id=MERCHANT_ID,
        assigned_courier_identity_id=ACTOR_ID,
        assignment_message_id=UUID("10000000-0000-4000-8000-000000000008"),
        state=CourierPickupState.ARRIVED,
        version=3,
        assigned_at=NOW,
        travelling_at=NOW,
        arrived_at=NOW,
        merchant_acknowledged_at=None,
        waiting_duration_seconds=None,
        updated_at=NOW,
    )
    return CourierPickupView(pickup=record, events=(), evidence=())


def test_canonical_digest_has_stable_vector_and_semantic_sensitivity() -> None:
    value = command()
    assert value.digest_schema_version == DIGEST_VERSION
    assert value.canonical_bytes() == (
        b'{"digest_schema_version":1,"pickup_id":"10000000-0000-4000-8000-000000000001",'
        b'"actor_identity_id":"10000000-0000-4000-8000-000000000002",'
        b'"acting_for_identity_id":null,"action":"mark_arrived","expected_version":2,'
        b'"merchant_id":null,"assigned_courier_identity_id":"10000000-0000-4000-8000-000000000002",'
        b'"assignment_id":"10000000-0000-4000-8000-000000000004","assignment_version":3,'
        b'"location_evidence_reference":"10000000-0000-4000-8000-000000000005",'
        b'"location_evidence_version":4,"location_evidence_observed_at":"2026-08-05T12:34:56.123456Z",'
        b'"reason":null,"assignment_source_reference":"10000000-0000-4000-8000-000000000004",'
        b'"assignment_source_version":3,"pickup_policy_code":"AYO_COURIER_PICKUP_POLICY_V1",'
        b'"pickup_policy_version":1}'
    )
    expected_digest = bytes(
        (
            150,
            251,
            181,
            95,
            169,
            181,
            6,
            155,
            145,
            84,
            178,
            68,
            229,
            230,
            83,
            69,
            217,
            25,
            228,
            108,
            223,
            72,
            8,
            8,
            3,
            215,
            64,
            105,
            26,
            225,
            210,
            151,
        )
    ).hex()
    assert value.hexdigest() == expected_digest
    for changed in (
        {"location_evidence_reference": UUID(int=99)},
        {"location_evidence_version": 5},
        {"location_evidence_observed_at": NOW.replace(microsecond=0)},
        {"expected_version": 3},
    ):
        assert command(**changed).hexdigest() != value.hexdigest()


def test_digest_rejects_naive_timestamps_unknown_fields_and_versions() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        command(location_evidence_observed_at=NOW.replace(tzinfo=None)).hexdigest()
    with pytest.raises(ValidationError):
        command(unapproved="value")
    with pytest.raises(ValueError, match="unsupported"):
        command(digest_schema_version=2).hexdigest()


def test_digest_normalizes_uuid_utc_unicode_and_explicit_nulls() -> None:
    canonical = command()
    equivalent = command(
        pickup_id=str(PICKUP_ID).upper(),
        actor_identity_id=str(ACTOR_ID).upper(),
        location_evidence_observed_at=NOW.astimezone(timezone(timedelta(hours=3))),
        pickup_policy_code="AYO_COURIER_PICKUP_POLICY_V1",
    )
    assert equivalent.canonical_bytes() == canonical.canonical_bytes()
    assert equivalent.hexdigest() == canonical.hexdigest()
    assert b'"acting_for_identity_id":null' in canonical.canonical_bytes()
    assert b'"merchant_id":null' in canonical.canonical_bytes()
    assert b'"reason":null' in canonical.canonical_bytes()
    assert b"2026-08-05T12:34:56.123456Z" in canonical.canonical_bytes()
    assert (
        command(pickup_policy_code="Cafe\u0301").canonical_bytes()
        == command(pickup_policy_code="Caf\u00e9").canonical_bytes()
    )


def test_tracing_metadata_is_not_part_of_digest_schema() -> None:
    fields = set(CourierPickupCommandDigestV1.model_fields)
    assert "correlation_id" not in fields
    assert "causation_id" not in fields
    with pytest.raises(ValidationError):
        command(correlation_id=UUID(int=90))
    with pytest.raises(ValidationError):
        command(causation_id=UUID(int=91))


def test_snapshot_round_trip_is_bounded_and_fail_closed() -> None:
    encoded = CourierPickupReplaySnapshotV1(response=view()).encode()
    assert len(str(encoded).encode()) < SNAPSHOT_MAX_BYTES
    assert CourierPickupReplaySnapshotV1.decode(encoded) == view()
    with pytest.raises(ValueError, match="malformed"):
        CourierPickupReplaySnapshotV1.decode({**encoded, "unexpected": True})
    with pytest.raises(ValueError, match="unsupported"):
        CourierPickupReplaySnapshotV1.decode({**encoded, "response_schema_version": 2})
    malformed = {
        **encoded,
        "response": {**encoded["response"], "request_hash": "not-public"},
    }
    with pytest.raises(ValueError, match="malformed"):
        CourierPickupReplaySnapshotV1.decode(malformed)
    serialized = str(encoded).lower()
    for forbidden in (
        "latitude",
        "longitude",
        "location_payload",
        "password",
        "credential",
        "token",
        "authentication_context",
        "canonical_command",
        "request_hash",
    ):
        assert forbidden not in serialized
    oversized = view().model_copy(
        update={
            "pickup": view().pickup.model_copy(
                update={"policy_code": "x" * SNAPSHOT_MAX_BYTES}
            )
        }
    )
    with pytest.raises(ValueError, match="size limit"):
        CourierPickupReplaySnapshotV1(response=oversized).encode()
