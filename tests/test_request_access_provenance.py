from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.request_access.models import (
    AccessChannel,
    InteractionMethod,
    InteractionProvenanceEnvelope,
    ProvenancePurpose,
)

pytestmark = pytest.mark.request_access
NOW = datetime(2026, 7, 23, 12, tzinfo=UTC)


def _envelope(**changes) -> InteractionProvenanceEnvelope:
    subject_id = changes.pop("subject_id", uuid4())
    values = {
        "purpose": ProvenancePurpose.INITIATION,
        "target_domain": "mobility",
        "target_type": "mobility.ride_request",
        "target_id": str(uuid4()),
        "target_version": 1,
        "command_type": "mobility.ride_request.create",
        "channel": AccessChannel.MOBILE_APP,
        "interaction_method": InteractionMethod.SELF_SERVICE,
        "adapter_id": uuid4(),
        "adapter_version": 1,
        "authenticated_account_id": uuid4(),
        "authenticated_subject_id": subject_id,
        "acting_subject_id": subject_id,
    }
    values.update(changes)
    return InteractionProvenanceEnvelope(**values)


def test_envelope_is_channel_neutral_and_closed_to_unapproved_metadata() -> None:
    envelope = _envelope()

    assert envelope.target_type == "mobility.ride_request"
    assert not hasattr(envelope, "transcript")
    with pytest.raises(ValidationError, match="Extra inputs"):
        InteractionProvenanceEnvelope(
            **envelope.model_dump(),
            transcript="prohibited surveillance content",  # type: ignore[call-arg]
        )


def test_continuation_requires_explicit_reference() -> None:
    with pytest.raises(ValidationError, match="explicit continuity"):
        _envelope(purpose=ProvenancePurpose.CONTINUATION)

    continued = _envelope(
        purpose=ProvenancePurpose.CONTINUATION,
        continuity_reference="explicit-continuity-reference-123456",
    )
    assert continued.continuity_reference is not None


def test_delegated_interaction_requires_owner_issued_authority_reference() -> None:
    with pytest.raises(ValidationError, match="authority reference"):
        _envelope(interaction_method=InteractionMethod.DELEGATED)

    delegated = _envelope(
        interaction_method=InteractionMethod.DELEGATED,
        delegated_authority_reference="household/active/relationship-123",
    )
    assert delegated.delegated_authority_reference is not None
    assert delegated.delegated_authority_reference.startswith("household/")


def test_support_assistance_requires_dual_attribution() -> None:
    with pytest.raises(ValidationError, match="dual attribution"):
        _envelope(interaction_method=InteractionMethod.SUPPORT_ASSISTED)

    assisted = _envelope(
        interaction_method=InteractionMethod.SUPPORT_ASSISTED,
        support_agent_subject_id=uuid4(),
        support_agent_account_id=uuid4(),
    )
    assert assisted.support_agent_subject_id is not None


def test_correction_is_append_only_lineage_not_mutation() -> None:
    correction = _envelope(
        purpose=ProvenancePurpose.CORRECTION,
        supersedes_provenance_id=uuid4(),
        correction_classification="adapter_classification_error",
    )

    with pytest.raises(ValidationError, match="frozen"):
        correction.channel = AccessChannel.SMS  # type: ignore[misc]
