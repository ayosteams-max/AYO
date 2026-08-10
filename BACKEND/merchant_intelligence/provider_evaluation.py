from __future__ import annotations

import math
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from BACKEND.merchant_intelligence.canonical_language import (
    canonical_merchant_intelligence_language,
)
from BACKEND.merchant_intelligence.generative import (
    Locale,
    MerchantGenerativeExplanationHttpRequest,
    Reason,
)

CorpusVersion = Annotated[str, Field(pattern=r"^merchant_ack_corpus_v[1-9][0-9]*$")]
ProviderId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")]
ModelId = Annotated[str, Field(min_length=1, max_length=120)]


class EvidenceCategory(StrEnum):
    PRIVACY = "privacy"
    TRAINING_DATA_USE = "training_data_use"
    RETENTION = "retention"
    REGIONAL_DATA_LOCATION = "regional_data_location"
    SECURITY_COMPLIANCE = "security_compliance"
    COST = "cost"
    RATE_LIMIT_SCALE = "rate_limit_scale"
    MODEL_LIFECYCLE = "model_lifecycle"


class EvidenceConclusion(StrEnum):
    SATISFIES = "satisfies"
    DOES_NOT_SATISFY = "does_not_satisfy"
    UNKNOWN = "unknown"
    CONDITIONALLY_AVAILABLE = "conditionally_available"


class EvidenceApplicability(StrEnum):
    GENERAL_PROVIDER_POLICY = "general_provider_policy"
    AYO_ACCOUNT_VERIFIED = "ayo_account_verified"


class ProviderPolicyEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: ProviderId
    model_id: ModelId
    category: EvidenceCategory
    applicable_product: str = Field(min_length=1, max_length=120)
    applicable_plan_or_tier: str = Field(min_length=1, max_length=120)
    source: HttpUrl
    reviewed_on: date
    valid_until: date
    conclusion: EvidenceConclusion
    applicability: EvidenceApplicability
    summary: str = Field(min_length=1, max_length=500)
    uncertainty: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def chronological(self) -> ProviderPolicyEvidence:
        if self.valid_until < self.reviewed_on:
            raise ValueError("evidence validity cannot precede review")
        return self

    def is_current(self, on: date) -> bool:
        return self.reviewed_on <= on <= self.valid_until


class EvaluationScenario(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    corpus_version: CorpusVersion
    scenario_id: str = Field(pattern=r"^[a-z0-9_]{3,100}$")
    locale: Locale
    recommendation: str
    reason: Reason
    user_action_available: bool
    tone: str
    expected_headline: str
    expected_body: str
    expected_action_label: str | None = None


_VISIBLE_SEMANTICS: tuple[tuple[Reason, str, bool, str], ...] = (
    ("ACK_ALLOWED_BY_CAPABILITY", "acknowledge_arrival", True, "informative"),
    ("ACK_IN_PROGRESS", "acknowledging_arrival", False, "informative"),
    ("ACK_CONFIRMED", "arrival_acknowledged", False, "positive"),
    (
        "ACK_RESULT_UNCERTAIN_RECONCILIATION_AVAILABLE",
        "check_acknowledgement_status",
        True,
        "caution",
    ),
    (
        "ACK_RECONCILIATION_IN_PROGRESS",
        "checking_acknowledgement_status",
        False,
        "informative",
    ),
    (
        "ACK_SAME_ATTEMPT_RETRY_AVAILABLE",
        "retry_same_acknowledgement",
        True,
        "caution",
    ),
    (
        "ACK_RETRY_ALLOWED_BY_CAPABILITY",
        "retry_acknowledgement",
        True,
        "caution",
    ),
    (
        "ACK_RESULT_UNCERTAIN_NO_CURRENT_ACTION",
        "acknowledgement_issue",
        False,
        "caution",
    ),
    (
        "ACK_SAME_ATTEMPT_RETRY_NOT_CURRENTLY_ALLOWED",
        "acknowledgement_issue",
        False,
        "caution",
    ),
    (
        "ACK_REJECTED_NO_CURRENT_ACTION",
        "acknowledgement_issue",
        False,
        "caution",
    ),
)


def _build_corpus() -> tuple[EvaluationScenario, ...]:
    scenarios: list[EvaluationScenario] = []
    for locale in ("en", "am"):
        for reason, recommendation, actionable, tone in _VISIBLE_SEMANTICS:
            MerchantGenerativeExplanationHttpRequest.model_validate(
                {
                    "promptVersion": "merchant_ack_explanation_v1",
                    "locale": locale,
                    "recommendation": recommendation,
                    "reason": reason,
                    "userActionAvailable": actionable,
                    "tone": tone,
                }
            )
            language = canonical_merchant_intelligence_language(locale, reason)
            scenarios.append(
                EvaluationScenario(
                    corpus_version="merchant_ack_corpus_v1",
                    scenario_id=f"{locale}_{reason.lower()}",
                    locale=locale,
                    recommendation=recommendation,
                    reason=reason,
                    user_action_available=actionable,
                    tone=tone,
                    expected_headline=language.headline,
                    expected_body=language.body,
                    expected_action_label=language.action_label,
                )
            )
    return tuple(scenarios)


MERCHANT_ACK_EVALUATION_CORPUS = _build_corpus()


class ObservationOutcome(StrEnum):
    RESPONSE = "response"
    MALFORMED = "malformed"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"


class ProviderObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: ProviderId
    model_id: ModelId
    scenario_id: str
    outcome: ObservationOutcome
    latency_ms: int = Field(ge=0, le=60_000)
    locale: Locale | None = None
    headline: str | None = Field(default=None, max_length=80)
    body: str | None = Field(default=None, max_length=240)


class CandidateTechnicalProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: ProviderId
    model_id: ModelId
    exact_model_version_pinned: bool
    server_side_only: bool
    mobile_secret_absent: bool
    arbitrary_client_prose_forbidden: bool
    structured_output_supported: bool
    tools_disabled: bool
    stateless: bool
    provider_neutral_edge_adapter: bool
    production_disabled: bool
    automatic_retry_disabled: bool
    automatic_failover_absent: bool
    input_price_usd_per_million_tokens: float | None = Field(default=None, ge=0)
    output_price_usd_per_million_tokens: float | None = Field(default=None, ge=0)
    documented_rate_limit: str | None = Field(default=None, max_length=240)
    lifecycle_risk: str = Field(min_length=1, max_length=240)


class HumanAmharicReview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: ProviderId
    model_id: ModelId
    scenario_id: str
    reviewer: str = Field(min_length=2, max_length=120)
    reviewed_on: date
    semantic_correctness: bool
    naturalness: bool
    grammar: bool
    terminology: bool
    actionability_correctness: bool

    @property
    def approved(self) -> bool:
        return all(
            (
                self.semantic_correctness,
                self.naturalness,
                self.grammar,
                self.terminology,
                self.actionability_correctness,
            )
        )


class GateName(StrEnum):
    PRIVACY = "privacy"
    TRAINING_DATA_USE = "training_data_use"
    RETENTION = "retention"
    REGIONAL_DATA_LOCATION = "regional_data_location"
    SECURITY_COMPLIANCE = "security_compliance"
    EVIDENCE_FRESHNESS = "evidence_freshness"
    SERVER_SIDE_ONLY = "server_side_only"
    MOBILE_SECRET_ABSENT = "mobile_secret_absent"
    ARBITRARY_CLIENT_PROSE_FORBIDDEN = "arbitrary_client_prose_forbidden"
    STRUCTURED_OUTPUT = "structured_output"
    EXACT_MODEL_VERSION = "exact_model_version"
    AUTOMATIC_RETRY_DISABLED = "automatic_retry_disabled"
    AUTOMATIC_FAILOVER_ABSENT = "automatic_failover_absent"
    CORPUS_COMPLETE = "corpus_complete"
    EXACT_PRESERVATION = "exact_preservation"
    LOCALE_ADHERENCE = "locale_adherence"
    LATENCY = "latency"
    RELIABILITY = "reliability"
    TOOL_FREE = "tool_free"
    STATELESS = "stateless"
    PROVIDER_NEUTRAL = "provider_neutral"
    AMHARIC_HUMAN_REVIEW = "amharic_human_review"
    PRODUCTION_DISABLED = "production_disabled"


class GateStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class GateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    gate: GateName
    status: GateStatus
    reason: str = Field(min_length=1, max_length=240)


class ComparativeMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sample_count: int = Field(ge=0)
    success_rate: float = Field(ge=0, le=1)
    exact_preservation_rate: float = Field(ge=0, le=1)
    locale_adherence_rate: float = Field(ge=0, le=1)
    timeout_rate: float = Field(ge=0, le=1)
    malformed_rate: float = Field(ge=0, le=1)
    provider_error_rate: float = Field(ge=0, le=1)
    median_latency_ms: int | None = Field(default=None, ge=0)
    p95_latency_ms: int | None = Field(default=None, ge=0)
    p99_latency_ms: int | None = Field(default=None, ge=0)
    projected_usd_per_1k: float | None = Field(default=None, ge=0)
    projected_usd_per_100k: float | None = Field(default=None, ge=0)
    projected_usd_per_1m: float | None = Field(default=None, ge=0)


class EvaluationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: ProviderId
    model_id: ModelId
    corpus_version: CorpusVersion
    evaluated_on: date
    gates: tuple[GateResult, ...]
    metrics: ComparativeMetrics
    eligible_for_admission_recommendation: bool
    lifecycle_state: Literal["evaluated"] = "evaluated"


_MANDATORY_POLICY_CATEGORIES = (
    EvidenceCategory.PRIVACY,
    EvidenceCategory.TRAINING_DATA_USE,
    EvidenceCategory.RETENTION,
    EvidenceCategory.REGIONAL_DATA_LOCATION,
    EvidenceCategory.SECURITY_COMPLIANCE,
)


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _policy_gate(
    category: EvidenceCategory,
    evidence: dict[EvidenceCategory, ProviderPolicyEvidence],
    evaluated_on: date,
) -> GateResult:
    item = evidence.get(category)
    gate = GateName(category.value)
    if item is None:
        return GateResult(
            gate=gate, status=GateStatus.UNKNOWN, reason="missing evidence"
        )
    if not item.is_current(evaluated_on):
        return GateResult(gate=gate, status=GateStatus.FAIL, reason="stale evidence")
    if item.applicability is not EvidenceApplicability.AYO_ACCOUNT_VERIFIED:
        return GateResult(
            gate=gate,
            status=GateStatus.UNKNOWN,
            reason="provider availability is not verified for the AYO account",
        )
    if item.conclusion is EvidenceConclusion.SATISFIES:
        return GateResult(gate=gate, status=GateStatus.PASS, reason="verified")
    if item.conclusion is EvidenceConclusion.DOES_NOT_SATISFY:
        return GateResult(
            gate=gate, status=GateStatus.FAIL, reason="requirement not met"
        )
    return GateResult(
        gate=gate, status=GateStatus.UNKNOWN, reason="evidence unresolved"
    )


def evaluate_offline_candidate(
    *,
    profile: CandidateTechnicalProfile,
    policy_evidence: tuple[ProviderPolicyEvidence, ...],
    observations: tuple[ProviderObservation, ...],
    amharic_reviews: tuple[HumanAmharicReview, ...] = (),
    evaluated_on: date,
    assumed_input_tokens: int = 0,
    assumed_output_tokens: int = 0,
) -> EvaluationReport:
    """Evaluate recorded synthetic evidence only; this function has no I/O surface."""
    identities = (
        {(item.provider_id, item.model_id) for item in policy_evidence}
        | {(item.provider_id, item.model_id) for item in observations}
        | {(item.provider_id, item.model_id) for item in amharic_reviews}
    )
    if identities - {(profile.provider_id, profile.model_id)}:
        raise ValueError("candidate evidence identity mismatch")
    if len({item.category for item in policy_evidence}) != len(policy_evidence):
        raise ValueError("duplicate candidate policy evidence")
    if len({item.scenario_id for item in observations}) != len(observations):
        raise ValueError("duplicate candidate scenario observation")
    if len({item.scenario_id for item in amharic_reviews}) != len(amharic_reviews):
        raise ValueError("duplicate candidate human review")
    if assumed_input_tokens < 0 or assumed_output_tokens < 0:
        raise ValueError("token assumptions must be non-negative")

    corpus = {
        scenario.scenario_id: scenario for scenario in MERCHANT_ACK_EVALUATION_CORPUS
    }
    unknown_observations = {item.scenario_id for item in observations} - corpus.keys()
    if unknown_observations:
        raise ValueError("observation is outside the fixed evaluation corpus")
    amharic_ids = {
        scenario.scenario_id
        for scenario in MERCHANT_ACK_EVALUATION_CORPUS
        if scenario.locale == "am"
    }
    unknown_reviews = {item.scenario_id for item in amharic_reviews} - amharic_ids
    if unknown_reviews:
        raise ValueError("human review is outside the Amharic evaluation corpus")
    policy = {item.category: item for item in policy_evidence}
    gates = [
        _policy_gate(category, policy, evaluated_on)
        for category in _MANDATORY_POLICY_CATEGORIES
    ]
    mandatory = [policy.get(category) for category in _MANDATORY_POLICY_CATEGORIES]
    gates.append(
        GateResult(
            gate=GateName.EVIDENCE_FRESHNESS,
            status=(
                GateStatus.PASS
                if all(
                    item is not None and item.is_current(evaluated_on)
                    for item in mandatory
                )
                else GateStatus.FAIL
            ),
            reason="all mandatory policy evidence is current"
            if all(
                item is not None and item.is_current(evaluated_on) for item in mandatory
            )
            else "mandatory policy evidence is missing or stale",
        )
    )

    profile_gates = (
        (GateName.SERVER_SIDE_ONLY, profile.server_side_only),
        (GateName.MOBILE_SECRET_ABSENT, profile.mobile_secret_absent),
        (
            GateName.ARBITRARY_CLIENT_PROSE_FORBIDDEN,
            profile.arbitrary_client_prose_forbidden,
        ),
        (GateName.STRUCTURED_OUTPUT, profile.structured_output_supported),
        (GateName.EXACT_MODEL_VERSION, profile.exact_model_version_pinned),
        (GateName.AUTOMATIC_RETRY_DISABLED, profile.automatic_retry_disabled),
        (GateName.AUTOMATIC_FAILOVER_ABSENT, profile.automatic_failover_absent),
        (GateName.TOOL_FREE, profile.tools_disabled),
        (GateName.STATELESS, profile.stateless),
        (GateName.PROVIDER_NEUTRAL, profile.provider_neutral_edge_adapter),
        (GateName.PRODUCTION_DISABLED, profile.production_disabled),
    )
    gates.extend(
        GateResult(
            gate=gate,
            status=GateStatus.PASS if passed else GateStatus.FAIL,
            reason="verified" if passed else "requirement not met",
        )
        for gate, passed in profile_gates
    )

    valid_observations = [item for item in observations if item.scenario_id in corpus]
    corpus_complete = len(valid_observations) == len(corpus) == 20
    exact = [
        item
        for item in valid_observations
        if item.outcome is ObservationOutcome.RESPONSE
        and item.locale == corpus[item.scenario_id].locale
        and item.headline == corpus[item.scenario_id].expected_headline
        and item.body == corpus[item.scenario_id].expected_body
    ]
    locale_matches = [
        item
        for item in valid_observations
        if item.locale == corpus[item.scenario_id].locale
    ]
    latencies = [item.latency_ms for item in valid_observations]
    p95 = _percentile(latencies, 0.95)
    success_count = sum(
        item.outcome is ObservationOutcome.RESPONSE for item in valid_observations
    )
    gates.extend(
        (
            GateResult(
                gate=GateName.CORPUS_COMPLETE,
                status=GateStatus.PASS if corpus_complete else GateStatus.FAIL,
                reason="all 20 canonical scenarios recorded"
                if corpus_complete
                else "corpus evidence incomplete",
            ),
            GateResult(
                gate=GateName.EXACT_PRESERVATION,
                status=GateStatus.PASS if len(exact) == 20 else GateStatus.FAIL,
                reason="all outputs exact"
                if len(exact) == 20
                else "one or more outputs changed canonical text",
            ),
            GateResult(
                gate=GateName.LOCALE_ADHERENCE,
                status=GateStatus.PASS
                if len(locale_matches) == 20
                else GateStatus.FAIL,
                reason="all locales exact"
                if len(locale_matches) == 20
                else "one or more locale mismatches",
            ),
            GateResult(
                gate=GateName.LATENCY,
                status=GateStatus.PASS
                if p95 is not None and p95 <= 2_000
                else GateStatus.FAIL,
                reason="p95 within 2-second bound"
                if p95 is not None and p95 <= 2_000
                else "p95 absent or exceeds 2-second bound",
            ),
            GateResult(
                gate=GateName.RELIABILITY,
                status=GateStatus.PASS if success_count == 20 else GateStatus.FAIL,
                reason="all scenarios returned"
                if success_count == 20
                else "one or more scenarios failed",
            ),
        )
    )

    approved_reviews = {
        review.scenario_id for review in amharic_reviews if review.approved
    }
    amharic_approved = approved_reviews == amharic_ids
    gates.append(
        GateResult(
            gate=GateName.AMHARIC_HUMAN_REVIEW,
            status=GateStatus.PASS if amharic_approved else GateStatus.UNKNOWN,
            reason="native human review complete"
            if amharic_approved
            else "NEEDS_NATIVE_AMHARIC_REVIEW",
        )
    )

    sample_count = len(valid_observations)
    divisor = sample_count or 1
    input_price = profile.input_price_usd_per_million_tokens
    output_price = profile.output_price_usd_per_million_tokens
    per_call = None
    if input_price is not None and output_price is not None:
        per_call = (
            assumed_input_tokens * input_price + assumed_output_tokens * output_price
        ) / 1_000_000
    metrics = ComparativeMetrics(
        sample_count=sample_count,
        success_rate=success_count / divisor,
        exact_preservation_rate=len(exact) / divisor,
        locale_adherence_rate=len(locale_matches) / divisor,
        timeout_rate=sum(
            item.outcome is ObservationOutcome.TIMEOUT for item in valid_observations
        )
        / divisor,
        malformed_rate=sum(
            item.outcome is ObservationOutcome.MALFORMED for item in valid_observations
        )
        / divisor,
        provider_error_rate=sum(
            item.outcome is ObservationOutcome.PROVIDER_ERROR
            for item in valid_observations
        )
        / divisor,
        median_latency_ms=_percentile(latencies, 0.5),
        p95_latency_ms=p95,
        p99_latency_ms=_percentile(latencies, 0.99),
        projected_usd_per_1k=None if per_call is None else per_call * 1_000,
        projected_usd_per_100k=None if per_call is None else per_call * 100_000,
        projected_usd_per_1m=None if per_call is None else per_call * 1_000_000,
    )
    eligible = all(gate.status is GateStatus.PASS for gate in gates)
    return EvaluationReport(
        provider_id=profile.provider_id,
        model_id=profile.model_id,
        corpus_version="merchant_ack_corpus_v1",
        evaluated_on=evaluated_on,
        gates=tuple(gates),
        metrics=metrics,
        eligible_for_admission_recommendation=eligible,
    )


class GovernanceLifecycle(StrEnum):
    UNASSESSED = "unassessed"
    EVALUATED = "evaluated"
    ADMISSION_RECOMMENDED = "admission_recommended"
    FOUNDER_APPROVED = "founder_approved"
    ELIGIBLE_FOR_PREPRODUCTION_ACTIVATION = "eligible_for_preproduction_activation"


class ManualGovernanceRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: ProviderId
    model_id: ModelId
    state: GovernanceLifecycle
    recorded_by: str = Field(min_length=2, max_length=120)
    recorded_on: date
    evidence_reference: str = Field(min_length=1, max_length=240)
    founder_approval_reference: str | None = Field(default=None, max_length=240)
    production_approved: bool = False

    @model_validator(mode="after")
    def manual_boundaries(self) -> ManualGovernanceRecord:
        if (
            self.state
            in {
                GovernanceLifecycle.FOUNDER_APPROVED,
                GovernanceLifecycle.ELIGIBLE_FOR_PREPRODUCTION_ACTIVATION,
            }
            and not self.founder_approval_reference
        ):
            raise ValueError("Founder approval reference is required")
        if self.production_approved:
            raise ValueError("Phase 5 cannot approve production")
        return self
