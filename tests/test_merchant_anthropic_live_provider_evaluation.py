import json
from datetime import date

import pytest

from BACKEND.merchant_intelligence.anthropic_live_provider_evaluation import (
    ANTHROPIC_API_VERSION,
    CORPUS_VERSION,
    EVIDENCE_PATH,
    INPUT_PRICE_USD_PER_MILLION,
    MAX_CALLS,
    MAX_OUTPUT_TOKENS,
    MODEL_ID,
    OUTPUT_PRICE_USD_PER_MILLION,
    PROVIDER_ID,
    TIMEOUT_SECONDS,
    AnthropicHttpsTransport,
    run_phase_8_evaluation,
)
from BACKEND.merchant_intelligence.live_provider_evaluation import (
    PHASE_6_CONFIGURATION,
    ProviderHttpResult,
    _write_evidence,
    persist_then_summarize,
    run_controlled_evaluation,
)
from BACKEND.merchant_intelligence.nano_live_provider_evaluation import (
    PHASE_7_CONFIGURATION,
    run_phase_7_evaluation,
)
from BACKEND.merchant_intelligence.provider_evaluation import (
    GateName,
    GateStatus,
    ObservationOutcome,
)


class FakeTransport:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []
        self.timeouts: list[float] = []

    def post(self, payload: bytes, *, timeout_seconds: float) -> ProviderHttpResult:
        parsed = json.loads(payload)
        self.payloads.append(parsed)
        self.timeouts.append(timeout_seconds)
        canonical = parsed["messages"][0]["content"]
        body = {
            "model": MODEL_ID,
            "content": [{"type": "text", "text": canonical}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        return ProviderHttpResult(status_code=200, body=json.dumps(body).encode())


class OpenAIFakeTransport:
    def post(self, payload: bytes, *, timeout_seconds: float) -> ProviderHttpResult:
        del timeout_seconds
        parsed = json.loads(payload)
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


class TimeoutTransport:
    def __init__(self) -> None:
        self.calls = 0

    def post(self, payload: bytes, *, timeout_seconds: float) -> ProviderHttpResult:
        del payload, timeout_seconds
        self.calls += 1
        raise TimeoutError


class ChangedTextTransport(FakeTransport):
    def post(self, payload: bytes, *, timeout_seconds: float) -> ProviderHttpResult:
        result = super().post(payload, timeout_seconds=timeout_seconds)
        body = json.loads(result.body)
        output = json.loads(body["content"][0]["text"])
        output["headline"] = "Changed"
        body["content"][0]["text"] = json.dumps(output)
        return ProviderHttpResult(status_code=200, body=json.dumps(body).encode())


def _gates(result):
    return [(gate.gate, gate.status) for gate in result.report.gates]


def test_phase8_identity_pricing_and_artifact_are_fixed_and_separate():
    assert PROVIDER_ID == "anthropic"
    assert MODEL_ID == "claude-haiku-4-5-20251001"
    assert CORPUS_VERSION == "merchant_ack_corpus_v1"
    assert ANTHROPIC_API_VERSION == "2023-06-01"
    assert INPUT_PRICE_USD_PER_MILLION == 1.0
    assert OUTPUT_PRICE_USD_PER_MILLION == 5.0
    assert EVIDENCE_PATH.as_posix() == (
        "artifacts/intelligence/phase8/controlled_anthropic_haiku_evaluation.json"
    )
    assert PHASE_6_CONFIGURATION.evidence_path != EVIDENCE_PATH
    assert PHASE_7_CONFIGURATION.evidence_path != EVIDENCE_PATH


def test_phase8_has_exactly_one_canonical_call_per_scenario_and_no_warmup():
    transport = FakeTransport()
    result = run_phase_8_evaluation(transport, evaluated_on=date(2026, 8, 10))
    assert len(transport.payloads) == len(result.observations) == MAX_CALLS == 20
    assert all(timeout == TIMEOUT_SECONDS == 2 for timeout in transport.timeouts)
    assert all(payload["model"] == MODEL_ID for payload in transport.payloads)
    assert all(
        payload["max_tokens"] == MAX_OUTPUT_TOKENS for payload in transport.payloads
    )
    assert all(len(payload["messages"]) == 1 for payload in transport.payloads)
    assert all(
        payload["messages"][0]["role"] == "user" for payload in transport.payloads
    )
    assert all(
        set(json.loads(payload["messages"][0]["content"]))
        == {"locale", "headline", "body"}
        for payload in transport.payloads
    )


def test_phase8_request_omits_tools_thinking_history_and_service_tier():
    transport = FakeTransport()
    run_phase_8_evaluation(transport, evaluated_on=date(2026, 8, 10))
    for payload in transport.payloads:
        assert not {
            "tools",
            "thinking",
            "service_tier",
            "metadata",
            "prompt",
            "previous_response_id",
        }.intersection(payload)
        assert set(payload) == {
            "model",
            "max_tokens",
            "system",
            "messages",
            "output_config",
        }


def test_phase8_strict_schema_admits_only_canonical_language_fields():
    transport = FakeTransport()
    run_phase_8_evaluation(transport, evaluated_on=date(2026, 8, 10))
    schema = transport.payloads[0]["output_config"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"locale", "headline", "body"}
    assert set(schema["required"]) == {"locale", "headline", "body"}
    assert schema["properties"]["locale"]["enum"] == ["en", "am"]


def test_phase8_reuses_phase5_gate_semantics_without_governance_promotion():
    phase8 = run_phase_8_evaluation(FakeTransport(), evaluated_on=date(2026, 8, 10))
    phase6 = run_controlled_evaluation(
        OpenAIFakeTransport(), evaluated_on=date(2026, 8, 10)
    )
    phase7 = run_phase_7_evaluation(
        OpenAIFakeTransport(), evaluated_on=date(2026, 8, 10)
    )
    assert _gates(phase8) == _gates(phase6) == _gates(phase7)
    assert phase8.report.lifecycle_state == "evaluated"
    assert phase8.report.eligible_for_admission_recommendation is False
    amharic = next(
        gate
        for gate in phase8.report.gates
        if gate.gate is GateName.AMHARIC_HUMAN_REVIEW
    )
    assert amharic.status is GateStatus.UNKNOWN


def test_phase8_timeout_is_recorded_once_per_scenario_without_retry_or_failover():
    transport = TimeoutTransport()
    result = run_phase_8_evaluation(transport, evaluated_on=date(2026, 8, 10))
    assert transport.calls == MAX_CALLS == 20
    assert all(
        observation.outcome is ObservationOutcome.TIMEOUT
        for observation in result.observations
    )
    assert result.report.eligible_for_admission_recommendation is False


def test_phase8_changed_canonical_text_fails_exact_preservation_without_repair():
    result = run_phase_8_evaluation(
        ChangedTextTransport(), evaluated_on=date(2026, 8, 10)
    )
    exact_gate = next(
        gate for gate in result.report.gates if gate.gate is GateName.EXACT_PRESERVATION
    )
    assert exact_gate.status is GateStatus.FAIL
    assert result.report.metrics.exact_preservation_rate == 0
    assert all(observation.headline == "Changed" for observation in result.observations)


def test_phase8_result_is_utf8_atomic_and_sanitized(tmp_path):
    result = run_phase_8_evaluation(FakeTransport(), evaluated_on=date(2026, 8, 10))
    destination = tmp_path / EVIDENCE_PATH
    _write_evidence(result, destination)
    serialized = destination.read_text(encoding="utf-8")
    assert "\\u" not in serialized
    assert json.loads(serialized) == result.model_dump(mode="json")
    for prohibited in (
        "api_key",
        "x-api-key",
        "authorization",
        "raw_response",
        "request_id",
        "transport_metadata",
    ):
        assert prohibited not in serialized.lower()


def test_console_failure_cannot_destroy_phase8_evidence(tmp_path):
    result = run_phase_8_evaluation(FakeTransport(), evaluated_on=date(2026, 8, 10))
    destination = tmp_path / EVIDENCE_PATH

    class FailingConsole:
        def write(self, value):
            del value
            raise UnicodeEncodeError("cp1252", "\u1218", 0, 1, "undefined")

    with pytest.raises(UnicodeEncodeError):
        persist_then_summarize(result, destination=destination, stream=FailingConsole())
    assert json.loads(destination.read_text(encoding="utf-8")) == result.model_dump(
        mode="json"
    )


def test_existing_phase8_artifact_refuses_before_credential_or_transport(
    monkeypatch, tmp_path
):
    from BACKEND.merchant_intelligence import (
        anthropic_live_provider_evaluation as module,
    )

    existing = tmp_path / "controlled_anthropic_haiku_evaluation.json"
    existing.write_text('{"existing":true}\n', encoding="utf-8")
    monkeypatch.setattr(module, "EVIDENCE_PATH", existing)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        module.main()
    assert existing.read_text(encoding="utf-8") == '{"existing":true}\n'


def test_transport_redacts_credential_and_runner_has_no_command_surface():
    secret = "approved-test-credential"
    assert secret not in repr(AnthropicHttpsTransport(secret))
    result = run_phase_8_evaluation(FakeTransport(), evaluated_on=date(2026, 8, 10))
    assert secret not in result.model_dump_json()
    assert set(run_phase_8_evaluation.__annotations__) == {
        "transport",
        "evaluated_on",
        "return",
    }
    assert not any(
        hasattr(result, name)
        for name in ("execute", "retry", "failover", "activate", "credential")
    )


def test_transport_uses_only_fixed_anthropic_messages_boundary(monkeypatch):
    from BACKEND.merchant_intelligence import (
        anthropic_live_provider_evaluation as module,
    )

    captured: dict[str, object] = {}

    class Response:
        status = 200

        def read(self):
            return b"{}"

    class Connection:
        def __init__(self, host, *, timeout):
            captured["host"] = host
            captured["timeout"] = timeout

        def request(self, method, path, *, body, headers):
            captured.update(method=method, path=path, body=body, headers=headers.copy())

        def getresponse(self):
            return Response()

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr(module.http.client, "HTTPSConnection", Connection)
    credential = "approved-test-credential"
    result = AnthropicHttpsTransport(credential).post(b"{}", timeout_seconds=2)
    assert result.status_code == 200
    assert captured == {
        "host": "api.anthropic.com",
        "timeout": 2,
        "method": "POST",
        "path": "/v1/messages",
        "body": b"{}",
        "headers": {
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "x-api-key": credential,
        },
        "closed": True,
    }
