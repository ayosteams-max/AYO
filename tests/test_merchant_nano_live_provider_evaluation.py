import json
from datetime import date

import pytest
from pydantic import ValidationError

from BACKEND.merchant_intelligence.live_provider_evaluation import (
    EVIDENCE_PATH,
    MAX_CALLS,
    MAX_OUTPUT_TOKENS,
    MODEL_ID,
    PHASE_6_CONFIGURATION,
    TIMEOUT_SECONDS,
    ProviderHttpResult,
    _write_evidence,
)
from BACKEND.merchant_intelligence.nano_live_provider_evaluation import (
    PHASE_7_CONFIGURATION,
    run_phase_7_evaluation,
)
from BACKEND.merchant_intelligence.provider_evaluation import GateName, GateStatus


class FakeTransport:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []
        self.timeouts: list[float] = []

    def post(self, payload: bytes, *, timeout_seconds: float) -> ProviderHttpResult:
        parsed = json.loads(payload)
        self.payloads.append(parsed)
        self.timeouts.append(timeout_seconds)
        body = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": parsed["input"]}],
                }
            ],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        return ProviderHttpResult(status_code=200, body=json.dumps(body).encode())


def _gate(result, name: GateName):
    return next(item for item in result.report.gates if item.gate is name)


def test_nano_configuration_is_exact_frozen_and_separate_from_phase6():
    assert PHASE_6_CONFIGURATION.model_id == MODEL_ID == "gpt-5.4-mini-2026-03-17"
    assert PHASE_6_CONFIGURATION.evidence_path == EVIDENCE_PATH
    assert PHASE_6_CONFIGURATION.input_price_usd_per_million == 0.75
    assert PHASE_6_CONFIGURATION.output_price_usd_per_million == 4.50
    assert PHASE_6_CONFIGURATION.documented_rate_limit == (
        "Account tier is not verified by Phase 6."
    )
    assert PHASE_7_CONFIGURATION.model_id == "gpt-5.4-nano-2026-03-17"
    assert PHASE_7_CONFIGURATION.input_price_usd_per_million == 0.20
    assert PHASE_7_CONFIGURATION.output_price_usd_per_million == 1.25
    assert PHASE_7_CONFIGURATION.evidence_path.as_posix() == (
        "artifacts/intelligence/phase7/controlled_openai_nano_evaluation.json"
    )
    assert "phase6" not in PHASE_7_CONFIGURATION.evidence_path.parts
    assert PHASE_7_CONFIGURATION.documented_rate_limit == (
        "Account tier is not verified by this controlled evaluation."
    )
    assert "Phase 6" not in PHASE_7_CONFIGURATION.documented_rate_limit
    with pytest.raises(ValidationError):
        PHASE_7_CONFIGURATION.model_id = "floating-alias"


def test_nano_runner_preserves_locked_20_call_request_boundary():
    transport = FakeTransport()
    result = run_phase_7_evaluation(transport, evaluated_on=date(2026, 8, 10))
    assert len(transport.payloads) == len(result.observations) == MAX_CALLS == 20
    assert all(timeout == TIMEOUT_SECONDS == 2 for timeout in transport.timeouts)
    assert all(
        payload["model"] == PHASE_7_CONFIGURATION.model_id
        for payload in transport.payloads
    )
    assert all(payload["store"] is False for payload in transport.payloads)
    assert all(payload["tools"] == [] for payload in transport.payloads)
    assert all(payload["reasoning"] == {"effort": "none"} for payload in transport.payloads)
    assert all(payload["max_output_tokens"] == MAX_OUTPUT_TOKENS for payload in transport.payloads)
    assert all(
        set(json.loads(payload["input"])) == {"locale", "headline", "body"}
        for payload in transport.payloads
    )
    assert all("prompt" not in payload for payload in transport.payloads)


def test_nano_result_is_sanitized_and_cannot_promote_governance(tmp_path):
    result = run_phase_7_evaluation(FakeTransport(), evaluated_on=date(2026, 8, 10))
    assert result.provider_id == "openai"
    destination = tmp_path / PHASE_7_CONFIGURATION.evidence_path
    _write_evidence(result, destination)
    serialized = destination.read_text(encoding="utf-8")
    assert json.loads(serialized) == result.model_dump(mode="json")
    assert result.report.lifecycle_state == "evaluated"
    assert result.report.eligible_for_admission_recommendation is False
    assert _gate(result, GateName.AMHARIC_HUMAN_REVIEW).status is GateStatus.UNKNOWN
    for prohibited in (
        "api_key",
        "authorization",
        "raw_response",
        "transport",
        "request_id",
    ):
        assert prohibited not in serialized.lower()


def test_phase6_and_phase7_gate_statuses_are_identical_for_same_fake_evidence():
    from BACKEND.merchant_intelligence.live_provider_evaluation import (
        run_controlled_evaluation,
    )

    phase6 = run_controlled_evaluation(FakeTransport(), evaluated_on=date(2026, 8, 10))
    phase7 = run_phase_7_evaluation(FakeTransport(), evaluated_on=date(2026, 8, 10))
    assert [(gate.gate, gate.status) for gate in phase6.report.gates] == [
        (gate.gate, gate.status) for gate in phase7.report.gates
    ]
    assert phase6.report.eligible_for_admission_recommendation is False
    assert phase7.report.eligible_for_admission_recommendation is False


def test_phase7_artifact_refuses_preexecution_overwrite(monkeypatch, tmp_path):
    from BACKEND.merchant_intelligence import nano_live_provider_evaluation as module

    existing = tmp_path / "controlled_openai_nano_evaluation.json"
    existing.write_text('{"existing":true}\n', encoding="utf-8")
    replacement = PHASE_7_CONFIGURATION.model_copy(update={"evidence_path": existing})
    monkeypatch.setattr(module, "PHASE_7_CONFIGURATION", replacement)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        module.main()
    assert existing.read_text(encoding="utf-8") == '{"existing":true}\n'
