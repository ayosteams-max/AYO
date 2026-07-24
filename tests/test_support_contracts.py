from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.support.ai_policy import (
    AIAction,
    AIActionTier,
    ConfidenceBand,
    evaluate_ai_action,
)
from BACKEND.support.models import (
    MessageVisibility,
    RequesterType,
    RetentionClassification,
    RiskClassification,
    SupportAIInteraction,
    SupportCase,
    SupportCaseEvent,
    SupportCategory,
    SupportChannel,
    SupportEventType,
    SupportMessage,
    SupportPriority,
    SupportQueue,
    SupportStatus,
)


def case(**changes) -> SupportCase:
    now = datetime.now(UTC)
    values = {
        "requester_identity_id": uuid4(),
        "requester_type": RequesterType.RIDER,
        "source_channel": SupportChannel.IN_APP_CHAT,
        "category": SupportCategory.RIDE_STATUS,
        "correlation_id": uuid4(),
        "idempotency_key": "support-command-123",
        "created_at": now,
        "updated_at": now,
        "retention_classification": RetentionClassification.ROUTINE_SUPPORT,
    }
    return SupportCase.model_validate(values | changes)


def test_case_contract_and_lifecycle_are_bounded() -> None:
    active = case().transition(SupportStatus.IN_PROGRESS, at=datetime.now(UTC))
    resolved = active.transition(
        SupportStatus.RESOLVED,
        at=datetime.now(UTC),
        resolution_category="guidance_provided",
    )
    closed = resolved.transition(SupportStatus.CLOSED, at=datetime.now(UTC))
    assert closed.closed_at is not None
    with pytest.raises(ValueError, match="Invalid support transition"):
        closed.transition(SupportStatus.IN_PROGRESS, at=datetime.now(UTC))


def test_anonymous_and_emergency_rules() -> None:
    anonymous = case(
        requester_identity_id=None,
        requester_type=RequesterType.ANONYMOUS,
    )
    assert anonymous.requester_identity_id is None
    with pytest.raises(ValidationError, match="immediately escalated"):
        case(priority=SupportPriority.EMERGENCY)
    emergency = case(
        priority=SupportPriority.EMERGENCY,
        risk_classification=RiskClassification.SAFETY,
        status=SupportStatus.ESCALATED,
        assigned_queue=SupportQueue.SAFETY,
        escalation_reason="emergency_safety",
    )
    assert emergency.assigned_queue is SupportQueue.SAFETY
    with pytest.raises(ValidationError, match="High-risk"):
        case(risk_classification=RiskClassification.FRAUD)


@pytest.mark.parametrize(
    ("action", "tier", "allowed"),
    [
        (AIAction.FAQ_ANSWER, AIActionTier.GREEN, True),
        (AIAction.REFUND_RECOMMENDATION, AIActionTier.YELLOW, False),
        (AIAction.WALLET_MUTATION, AIActionTier.RED, False),
    ],
)
def test_ai_action_policy(action, tier, allowed) -> None:
    decision = evaluate_ai_action(action, ConfidenceBand.HIGH)
    assert decision.tier is tier
    assert decision.allowed is allowed


def test_yellow_needs_human_and_confidence_is_not_only_control() -> None:
    approved = evaluate_ai_action(
        AIAction.REFUND_RECOMMENDATION,
        ConfidenceBand.HIGH,
        human_approved=True,
    )
    uncertain = evaluate_ai_action(AIAction.FAQ_ANSWER, ConfidenceBand.LOW)
    conflict = evaluate_ai_action(
        AIAction.FAQ_ANSWER, ConfidenceBand.HIGH, information_conflict=True
    )
    assert approved.allowed
    assert uncertain.requires_follow_up and not uncertain.allowed
    assert conflict.requires_human and not conflict.allowed


def test_messages_reject_secrets_and_keep_internal_visibility() -> None:
    values = {
        "case_id": uuid4(),
        "visibility": MessageVisibility.INTERNAL_NOTE,
        "language_tag": "am-ET",
        "content": "Restricted operational note",
        "created_at": datetime.now(UTC),
    }
    assert (
        SupportMessage.model_validate(values).visibility
        is MessageVisibility.INTERNAL_NOTE
    )
    with pytest.raises(ValidationError, match="prohibited sensitive"):
        SupportMessage.model_validate(values | {"content": "OTP: 123456"})


def test_event_metadata_is_allowlisted() -> None:
    values = {
        "case_id": uuid4(),
        "event_type": SupportEventType.CREATED,
        "actor_type": RequesterType.ANONYMOUS,
        "correlation_id": uuid4(),
        "occurred_at": datetime.now(UTC),
    }
    assert SupportCaseEvent.model_validate(values).safe_metadata == {}
    with pytest.raises(ValidationError, match="prohibited field"):
        SupportCaseEvent.model_validate(values | {"safe_metadata": {"phone": "secret"}})


def test_ai_interaction_forbids_reasoning_and_naive_time() -> None:
    values = {
        "conversation_id": uuid4(),
        "case_id": uuid4(),
        "ai_service_identity_id": uuid4(),
        "confidence_band": "low",
        "action_category": "faq_answer",
        "correlation_id": uuid4(),
        "safe_outcome_category": "follow_up_required",
        "created_at": datetime.now(UTC),
    }
    assert SupportAIInteraction.model_validate(values).model_reference is None
    with pytest.raises(ValidationError):
        SupportAIInteraction.model_validate(values | {"chain_of_thought": "private"})
    with pytest.raises(ValidationError, match="timezone-aware"):
        SupportAIInteraction.model_validate(values | {"created_at": datetime.now()})
