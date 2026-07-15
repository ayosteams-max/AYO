from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class AIActionTier(StrEnum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class AIAction(StrEnum):
    FAQ_ANSWER = "faq_answer"
    RIDE_STATUS_EXPLANATION = "ride_status_explanation"
    FARE_RULE_EXPLANATION = "fare_rule_explanation"
    TROUBLESHOOTING = "troubleshooting"
    INFORMATION_COLLECTION = "information_collection"
    CASE_CREATE = "case_create"
    LOW_RISK_CASE_UPDATE = "low_risk_case_update"
    CASE_ESCALATE = "case_escalate"
    SELF_SERVICE_GUIDANCE = "self_service_guidance"
    REFUND_RECOMMENDATION = "refund_recommendation"
    FARE_REVIEW_RECOMMENDATION = "fare_review_recommendation"
    COMPENSATION_RECOMMENDATION = "compensation_recommendation"
    ACCOUNT_RECOVERY_RECOMMENDATION = "account_recovery_recommendation"
    PAYMENT_INVESTIGATION = "payment_investigation"
    PAYOUT_INVESTIGATION = "payout_investigation"
    IDENTITY_CORRECTION_RECOMMENDATION = "identity_correction_recommendation"
    TEMPORARY_RESTRICTION_RECOMMENDATION = "temporary_restriction_recommendation"
    PAYMENT_MUTATION = "payment_mutation"
    PAYOUT_MUTATION = "payout_mutation"
    WALLET_MUTATION = "wallet_mutation"
    PERMANENT_ACCOUNT_ACTION = "permanent_account_action"
    VERIFIED_IDENTITY_MUTATION = "verified_identity_mutation"
    SECURITY_CONTROL_BYPASS = "security_control_bypass"
    SAFETY_OR_FRAUD_OVERRIDE = "safety_or_fraud_override"
    UNRESTRICTED_AUDIT_ACCESS = "unrestricted_audit_access"
    CROSS_CUSTOMER_DISCLOSURE = "cross_customer_disclosure"
    LEGAL_CLAIM_APPROVAL = "legal_claim_approval"
    EMERGENCY_GUARANTEE = "emergency_guarantee"


GREEN_ACTIONS = frozenset(
    {
        AIAction.FAQ_ANSWER,
        AIAction.RIDE_STATUS_EXPLANATION,
        AIAction.FARE_RULE_EXPLANATION,
        AIAction.TROUBLESHOOTING,
        AIAction.INFORMATION_COLLECTION,
        AIAction.CASE_CREATE,
        AIAction.LOW_RISK_CASE_UPDATE,
        AIAction.CASE_ESCALATE,
        AIAction.SELF_SERVICE_GUIDANCE,
    }
)
YELLOW_ACTIONS = frozenset(
    {
        AIAction.REFUND_RECOMMENDATION,
        AIAction.FARE_REVIEW_RECOMMENDATION,
        AIAction.COMPENSATION_RECOMMENDATION,
        AIAction.ACCOUNT_RECOVERY_RECOMMENDATION,
        AIAction.PAYMENT_INVESTIGATION,
        AIAction.PAYOUT_INVESTIGATION,
        AIAction.IDENTITY_CORRECTION_RECOMMENDATION,
        AIAction.TEMPORARY_RESTRICTION_RECOMMENDATION,
    }
)
RED_ACTIONS = frozenset(set(AIAction) - GREEN_ACTIONS - YELLOW_ACTIONS)


class ConfidenceBand(StrEnum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AIActionDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    requires_human: bool
    requires_follow_up: bool
    tier: AIActionTier
    safe_outcome: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$")]


def evaluate_ai_action(
    action: AIAction,
    confidence: ConfidenceBand,
    *,
    human_approved: bool = False,
    information_conflict: bool = False,
) -> AIActionDecision:
    if action in RED_ACTIONS:
        return AIActionDecision(
            allowed=False,
            requires_human=True,
            requires_follow_up=False,
            tier=AIActionTier.RED,
            safe_outcome="prohibited_action",
        )
    if action in YELLOW_ACTIONS:
        return AIActionDecision(
            allowed=human_approved,
            requires_human=not human_approved,
            requires_follow_up=False,
            tier=AIActionTier.YELLOW,
            safe_outcome="human_approved"
            if human_approved
            else "human_approval_required",
        )
    follow_up = (
        confidence in {ConfidenceBand.UNKNOWN, ConfidenceBand.LOW}
        or information_conflict
    )
    return AIActionDecision(
        allowed=not follow_up,
        requires_human=information_conflict,
        requires_follow_up=follow_up,
        tier=AIActionTier.GREEN,
        safe_outcome="follow_up_required" if follow_up else "approved_low_risk",
    )
