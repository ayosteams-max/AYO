from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from BACKEND.merchant_intelligence.provider_evaluation import (
    MERCHANT_ACK_EVALUATION_CORPUS,
    CandidateTechnicalProfile,
    EvidenceApplicability,
    EvidenceCategory,
    EvidenceConclusion,
    GateName,
    GateStatus,
    GovernanceLifecycle,
    HumanAmharicReview,
    ManualGovernanceRecord,
    ObservationOutcome,
    ProviderObservation,
    ProviderPolicyEvidence,
    evaluate_offline_candidate,
)

TODAY = date(2026, 8, 10)
PROVIDER = "synthetic_provider"
MODEL = "synthetic-model-v1"


def profile(**changes: object) -> CandidateTechnicalProfile:
    values: dict[str, object] = {
        "provider_id": PROVIDER,
        "model_id": MODEL,
        "exact_model_version_pinned": True,
        "server_side_only": True,
        "mobile_credentials_absent": True,
        "arbitrary_client_prose_forbidden": True,
        "structured_output_supported": True,
        "tools_disabled": True,
        "stateless": True,
        "provider_neutral_edge_adapter": True,
        "production_disabled": True,
        "automatic_retry_disabled": True,
        "automatic_failover_absent": True,
        "input_price_usd_per_million_tokens": 1.0,
        "output_price_usd_per_million_tokens": 2.0,
        "documented_rate_limit": "synthetic comparative evidence",
        "lifecycle_risk": "synthetic model may be retired",
    }
    values.update(changes)
    return CandidateTechnicalProfile.model_validate(values)


def policy(
    *,
    applicability: EvidenceApplicability = EvidenceApplicability.AYO_ACCOUNT_VERIFIED,
    conclusion: EvidenceConclusion = EvidenceConclusion.SATISFIES,
    valid_until: date = date(2026, 9, 9),
) -> tuple[ProviderPolicyEvidence, ...]:
    return tuple(
        ProviderPolicyEvidence(
            provider_id=PROVIDER,
            model_id=MODEL,
            category=category,
            applicable_product="Synthetic text API",
            applicable_plan_or_tier="AYO test account",
            source="https://example.com/official-policy",
            reviewed_on=TODAY,
            valid_until=valid_until,
            conclusion=conclusion,
            applicability=applicability,
            summary="Synthetic policy evidence for deterministic tests.",
            uncertainty="No uncertainty in this synthetic fixture.",
        )
        for category in (
            EvidenceCategory.PRIVACY,
            EvidenceCategory.TRAINING_DATA_USE,
            EvidenceCategory.RETENTION,
            EvidenceCategory.REGIONAL_DATA_LOCATION,
            EvidenceCategory.SECURITY_COMPLIANCE,
        )
    )


def observations(**changes: object) -> tuple[ProviderObservation, ...]:
    return tuple(
        ProviderObservation(
            provider_id=PROVIDER,
            model_id=MODEL,
            scenario_id=scenario.scenario_id,
            outcome=changes.get("outcome", ObservationOutcome.RESPONSE),
            latency_ms=changes.get("latency_ms", 100),
            locale=changes.get("locale", scenario.locale),
            headline=changes.get("headline", scenario.expected_headline),
            body=changes.get("body", scenario.expected_body),
        )
        for scenario in MERCHANT_ACK_EVALUATION_CORPUS
    )


def reviews() -> tuple[HumanAmharicReview, ...]:
    return tuple(
        HumanAmharicReview(
            provider_id=PROVIDER,
            model_id=MODEL,
            scenario_id=scenario.scenario_id,
            reviewer="Named native reviewer",
            reviewed_on=TODAY,
            semantic_correctness=True,
            naturalness=True,
            grammar=True,
            terminology=True,
            actionability_correctness=True,
        )
        for scenario in MERCHANT_ACK_EVALUATION_CORPUS
        if scenario.locale == "am"
    )


def report(**changes: object):
    values: dict[str, object] = {
        "profile": profile(),
        "policy_evidence": policy(),
        "observations": observations(),
        "amharic_reviews": reviews(),
        "evaluated_on": TODAY,
        "assumed_input_tokens": 100,
        "assumed_output_tokens": 50,
    }
    values.update(changes)
    return evaluate_offline_candidate(**values)


def gate(result, name: GateName):
    return next(item for item in result.gates if item.gate is name)


def test_corpus_is_fixed_complete_bilingual_and_privacy_minimal():
    assert len(MERCHANT_ACK_EVALUATION_CORPUS) == 20
    assert len({item.reason for item in MERCHANT_ACK_EVALUATION_CORPUS}) == 10
    assert {item.locale for item in MERCHANT_ACK_EVALUATION_CORPUS} == {"en", "am"}
    assert all(
        sum(
            item.locale == locale and item.reason == reason
            for item in MERCHANT_ACK_EVALUATION_CORPUS
        )
        == 1
        for locale in ("en", "am")
        for reason in {item.reason for item in MERCHANT_ACK_EVALUATION_CORPUS}
    )
    serialized = " ".join(
        f"{item.scenario_id} {item.expected_headline} {item.expected_body}"
        for item in MERCHANT_ACK_EVALUATION_CORPUS
    ).lower()
    for prohibited in (
        "merchantid",
        "orderid",
        "pickupid",
        "latitude",
        "longitude",
        "phone",
    ):
        assert prohibited not in serialized
    with pytest.raises(ValidationError):
        type(MERCHANT_ACK_EVALUATION_CORPUS[0]).model_validate(
            {
                **MERCHANT_ACK_EVALUATION_CORPUS[0].model_dump(),
                "user_prompt": "arbitrary",
            }
        )


def test_complete_current_account_evidence_passes_hard_gates_but_only_evaluates():
    result = report()
    assert all(item.status is GateStatus.MET for item in result.gates)
    assert result.eligible_for_admission_recommendation is True
    assert result.lifecycle_state == "evaluated"
    assert result.metrics.sample_count == 20
    assert result.metrics.success_rate == 1
    assert result.metrics.exact_preservation_rate == 1
    assert result.metrics.locale_adherence_rate == 1
    assert result.metrics.p95_latency_ms == 100
    assert result.metrics.projected_usd_per_1k == pytest.approx(0.2)


@pytest.mark.parametrize(
    "category,gate_name",
    [
        (EvidenceCategory.PRIVACY, GateName.PRIVACY),
        (EvidenceCategory.TRAINING_DATA_USE, GateName.TRAINING_DATA_USE),
        (EvidenceCategory.RETENTION, GateName.RETENTION),
        (EvidenceCategory.REGIONAL_DATA_LOCATION, GateName.REGIONAL_DATA_LOCATION),
        (EvidenceCategory.SECURITY_COMPLIANCE, GateName.SECURITY_COMPLIANCE),
    ],
)
def test_each_policy_category_is_an_independent_mandatory_gate(category, gate_name):
    evidence = tuple(item for item in policy() if item.category is not category)
    result = report(policy_evidence=evidence)
    assert gate(result, gate_name).status is GateStatus.UNKNOWN
    assert result.eligible_for_admission_recommendation is False


def test_general_availability_unknown_and_stale_evidence_cannot_admit():
    general = report(
        policy_evidence=policy(
            applicability=EvidenceApplicability.GENERAL_PROVIDER_POLICY
        )
    )
    assert gate(general, GateName.PRIVACY).status is GateStatus.UNKNOWN
    assert general.eligible_for_admission_recommendation is False
    stale = report(evaluated_on=date(2026, 9, 10))
    assert gate(stale, GateName.EVIDENCE_FRESHNESS).status is GateStatus.FAIL
    assert stale.eligible_for_admission_recommendation is False
    unresolved = report(policy_evidence=policy(conclusion=EvidenceConclusion.UNKNOWN))
    assert gate(unresolved, GateName.PRIVACY).status is GateStatus.UNKNOWN
    assert unresolved.eligible_for_admission_recommendation is False


def test_policy_evidence_requires_auditable_applicability_and_dates():
    payload = policy()[0].model_dump(mode="json")
    for required in (
        "provider_id",
        "model_id",
        "category",
        "applicable_product",
        "applicable_plan_or_tier",
        "source",
        "reviewed_on",
        "valid_until",
        "conclusion",
        "applicability",
        "summary",
        "uncertainty",
    ):
        invalid = dict(payload)
        invalid.pop(required)
        with pytest.raises(ValidationError):
            ProviderPolicyEvidence.model_validate(invalid)


@pytest.mark.parametrize(
    "field,gate_name",
    [
        ("server_side_only", GateName.SERVER_SIDE_ONLY),
        ("mobile_credentials_absent", GateName.MOBILE_CREDENTIALS_ABSENT),
        ("arbitrary_client_prose_forbidden", GateName.ARBITRARY_CLIENT_PROSE_FORBIDDEN),
        ("structured_output_supported", GateName.STRUCTURED_OUTPUT),
        ("exact_model_version_pinned", GateName.EXACT_MODEL_VERSION),
        ("tools_disabled", GateName.TOOL_FREE),
        ("stateless", GateName.STATELESS),
        ("provider_neutral_edge_adapter", GateName.PROVIDER_NEUTRAL),
        ("production_disabled", GateName.PRODUCTION_DISABLED),
        ("automatic_retry_disabled", GateName.AUTOMATIC_RETRY_DISABLED),
        ("automatic_failover_absent", GateName.AUTOMATIC_FAILOVER_ABSENT),
    ],
)
def test_technical_profile_requirements_are_hard_gates(field, gate_name):
    result = report(profile=profile(**{field: False}))
    assert gate(result, gate_name).status is GateStatus.FAIL
    assert result.eligible_for_admission_recommendation is False


def test_corpus_schema_locale_exactness_latency_and_reliability_are_hard_gates():
    malformed = list(observations())
    malformed[0] = malformed[0].model_copy(
        update={"outcome": ObservationOutcome.MALFORMED}
    )
    result = report(observations=tuple(malformed))
    assert gate(result, GateName.RELIABILITY).status is GateStatus.FAIL
    assert gate(result, GateName.EXACT_PRESERVATION).status is GateStatus.FAIL
    changed = list(observations())
    changed[0] = changed[0].model_copy(update={"body": "Changed wording"})
    assert (
        gate(report(observations=tuple(changed)), GateName.EXACT_PRESERVATION).status
        is GateStatus.FAIL
    )
    wrong_locale = list(observations())
    wrong_locale[0] = wrong_locale[0].model_copy(update={"locale": "am"})
    assert (
        gate(report(observations=tuple(wrong_locale)), GateName.LOCALE_ADHERENCE).status
        is GateStatus.FAIL
    )
    slow = list(observations())
    slow[-2:] = [item.model_copy(update={"latency_ms": 2_001}) for item in slow[-2:]]
    assert (
        gate(report(observations=tuple(slow)), GateName.LATENCY).status
        is GateStatus.FAIL
    )
    incomplete = observations()[:-1]
    assert (
        gate(report(observations=incomplete), GateName.CORPUS_COMPLETE).status
        is GateStatus.FAIL
    )


def test_metrics_never_override_a_failed_hard_gate():
    result = report(profile=profile(production_disabled=False))
    assert result.metrics.success_rate == 1
    assert result.metrics.exact_preservation_rate == 1
    assert result.eligible_for_admission_recommendation is False


def test_amharic_requires_complete_named_human_review_and_never_auto_approves():
    missing = report(amharic_reviews=())
    assert gate(missing, GateName.AMHARIC_HUMAN_REVIEW).status is GateStatus.UNKNOWN
    assert (
        "NEEDS_NATIVE_AMHARIC_REVIEW"
        in gate(missing, GateName.AMHARIC_HUMAN_REVIEW).reason
    )
    partial = reviews()[:-1]
    assert (
        gate(report(amharic_reviews=partial), GateName.AMHARIC_HUMAN_REVIEW).status
        is GateStatus.UNKNOWN
    )


def test_candidate_and_model_evidence_cannot_collide_or_substitute():
    wrong = observations()[0].model_copy(update={"model_id": "different-model"})
    with pytest.raises(ValueError, match="identity mismatch"):
        report(observations=(wrong, *observations()[1:]))
    with pytest.raises(ValueError, match="duplicate candidate scenario"):
        report(observations=(*observations(), observations()[0]))
    with pytest.raises(ValueError, match="outside the fixed"):
        report(
            observations=(
                observations()[0].model_copy(
                    update={"scenario_id": "arbitrary_prompt"}
                ),
            )
        )


def test_evaluation_has_no_automatic_governance_transition_or_production_approval():
    assert report().lifecycle_state == "evaluated"
    with pytest.raises(ValidationError, match="Founder approval"):
        ManualGovernanceRecord(
            provider_id=PROVIDER,
            model_id=MODEL,
            state=GovernanceLifecycle.FOUNDER_APPROVED,
            recorded_by="CTO reviewer",
            recorded_on=TODAY,
            evidence_reference="offline-report-v1",
        )
    with pytest.raises(ValidationError, match="cannot approve production"):
        ManualGovernanceRecord(
            provider_id=PROVIDER,
            model_id=MODEL,
            state=GovernanceLifecycle.ELIGIBLE_FOR_PREPRODUCTION_ACTIVATION,
            recorded_by="CTO reviewer",
            recorded_on=TODAY,
            evidence_reference="offline-report-v1",
            founder_approval_reference="founder-record-v1",
            production_approved=True,
        )


def test_models_are_strict_frozen_and_offline_evaluation_exposes_no_executor():
    item = MERCHANT_ACK_EVALUATION_CORPUS[0]
    with pytest.raises(ValidationError):
        item.reason = "ACK_CONFIRMED"
    output = report()
    assert not any(
        hasattr(output, name)
        for name in ("execute", "generate", "dispatch", "retry", "activate", "provider")
    )
    assert set(CandidateTechnicalProfile.model_fields).isdisjoint(
        {"credential", "api_key", "prompt", "callback", "command", "tool"}
    )


def test_offline_evaluator_has_no_network_credential_runtime_or_router_surface():
    source = Path("BACKEND/merchant_intelligence/provider_evaluation.py").read_text(
        encoding="utf-8"
    )
    for prohibited in (
        "import requests",
        "import httpx",
        "import socket",
        "api_key",
        "os.environ",
        "MerchantGenerativeExplanationProvider",
        "generate_merchant_explanation",
        "tool_call",
        "vector_database",
        "embedding",
        "model_router",
    ):
        assert prohibited not in source
