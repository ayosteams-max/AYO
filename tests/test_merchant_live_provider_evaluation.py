import json
from datetime import date

import pytest

from BACKEND.merchant_intelligence.live_provider_evaluation import (
    CORPUS_VERSION,
    EVIDENCE_PATH,
    MAX_CALLS,
    MAX_OUTPUT_TOKENS,
    MODEL_ID,
    TIMEOUT_SECONDS,
    OpenAIHttpsTransport,
    ProviderHttpResult,
    _write_evidence,
    persist_then_summarize,
    run_controlled_evaluation,
)
from BACKEND.merchant_intelligence.provider_evaluation import (
    GateName,
    GateStatus,
    ObservationOutcome,
)


class FakeTransport:
    def __init__(self, responses=None):
        self.payloads = []
        self.timeouts = []
        self.responses = list(responses or [])

    def post(self, payload: bytes, *, timeout_seconds: float) -> ProviderHttpResult:
        self.payloads.append(json.loads(payload))
        self.timeouts.append(timeout_seconds)
        response = (
            self.responses.pop(0) if self.responses else self.payloads[-1]["input"]
        )
        if isinstance(response, Exception):
            raise response
        if isinstance(response, ProviderHttpResult):
            return response
        body = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": response}],
                }
            ],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        return ProviderHttpResult(status_code=200, body=json.dumps(body).encode())


def gate(result, name):
    return next(item for item in result.report.gates if item.gate is name)


def test_fixed_corpus_one_call_each_and_no_arbitrary_prompt_or_runtime_features():
    transport = FakeTransport()
    result = run_controlled_evaluation(transport, evaluated_on=date(2026, 8, 10))
    assert len(result.observations) == len(transport.payloads) == MAX_CALLS == 20
    assert result.corpus_version == CORPUS_VERSION
    assert all(timeout == TIMEOUT_SECONDS == 2 for timeout in transport.timeouts)
    assert all(payload["model"] == MODEL_ID for payload in transport.payloads)
    assert all(payload["store"] is False for payload in transport.payloads)
    assert all(payload["tools"] == [] for payload in transport.payloads)
    assert all(
        payload["reasoning"] == {"effort": "none"} for payload in transport.payloads
    )
    assert all(
        payload["max_output_tokens"] == MAX_OUTPUT_TOKENS
        for payload in transport.payloads
    )
    assert all(
        set(json.loads(payload["input"])) == {"locale", "headline", "body"}
        for payload in transport.payloads
    )
    assert all("prompt" not in payload for payload in transport.payloads)


def test_valid_responses_feed_phase5_without_governance_promotion_or_human_review():
    result = run_controlled_evaluation(FakeTransport(), evaluated_on=date(2026, 8, 10))
    assert all(
        item.outcome is ObservationOutcome.RESPONSE for item in result.observations
    )
    assert result.report.metrics.sample_count == 20
    assert result.report.metrics.success_rate == 1
    assert result.report.metrics.exact_preservation_rate == 1
    assert result.report.metrics.locale_adherence_rate == 1
    assert result.report.lifecycle_state == "evaluated"
    assert result.report.eligible_for_admission_recommendation is False
    assert gate(result, GateName.AMHARIC_HUMAN_REVIEW).status is GateStatus.UNKNOWN
    assert gate(result, GateName.PRIVACY).status is GateStatus.UNKNOWN


@pytest.mark.parametrize(
    "response,outcome",
    [
        ("not json", ObservationOutcome.MALFORMED),
        (
            ProviderHttpResult(status_code=429, body=b"discarded"),
            ObservationOutcome.PROVIDER_ERROR,
        ),
        (TimeoutError(), ObservationOutcome.TIMEOUT),
    ],
)
def test_failure_is_recorded_once_without_retry(response, outcome):
    transport = FakeTransport([response])
    result = run_controlled_evaluation(transport, evaluated_on=date(2026, 8, 10))
    assert result.observations[0].outcome is outcome
    assert len(transport.payloads) == 20


def test_changed_text_and_locale_are_honest_nonexact_evidence():
    changed = json.dumps({"locale": "am", "headline": "Changed", "body": "Changed"})
    result = run_controlled_evaluation(
        FakeTransport([changed]), evaluated_on=date(2026, 8, 10)
    )
    assert result.observations[0].outcome is ObservationOutcome.RESPONSE
    assert result.report.metrics.exact_preservation_rate == pytest.approx(19 / 20)
    assert result.report.metrics.locale_adherence_rate == pytest.approx(19 / 20)
    assert gate(result, GateName.EXACT_PRESERVATION).status is GateStatus.FAIL
    assert gate(result, GateName.LOCALE_ADHERENCE).status is GateStatus.FAIL


def test_transport_redacts_credential_and_result_cannot_serialize_it():
    secret = "approved-test-credential"
    transport = OpenAIHttpsTransport(secret)
    assert secret not in repr(transport)
    result = run_controlled_evaluation(FakeTransport(), evaluated_on=date(2026, 8, 10))
    assert secret not in result.model_dump_json()
    assert "api_key" not in result.model_dump_json().lower()


def test_runner_has_no_prompt_corpus_retry_failover_or_command_surface():
    parameters = set(run_controlled_evaluation.__annotations__)
    assert parameters == {"transport", "evaluated_on", "return"}
    result = run_controlled_evaluation(FakeTransport(), evaluated_on=date(2026, 8, 10))
    assert not any(
        hasattr(result, name)
        for name in (
            "execute",
            "acknowledge",
            "reconcile",
            "retry",
            "activate",
            "dispatch",
            "prompt",
            "credential",
        )
    )


def test_utf8_atomic_evidence_round_trip_preserves_english_and_amharic(tmp_path):
    result = run_controlled_evaluation(FakeTransport(), evaluated_on=date(2026, 8, 10))
    destination = tmp_path / "artifacts" / "intelligence" / "phase6" / "evidence.json"
    _write_evidence(result, destination)
    raw = destination.read_bytes()
    assert raw.endswith(b"\n")
    decoded = raw.decode("utf-8")
    assert "\\u" not in decoded
    parsed = json.loads(decoded)
    assert parsed == result.model_dump(mode="json")
    amharic = next(
        item for item in result.observations if item.scenario_id.startswith("am_")
    )
    persisted_amharic = next(
        item
        for item in parsed["observations"]
        if item["scenario_id"] == amharic.scenario_id
    )
    assert persisted_amharic["headline"] == amharic.headline
    assert persisted_amharic["body"] == amharic.body


def test_atomic_replace_and_failed_replace_preserve_prior_evidence(tmp_path):
    result = run_controlled_evaluation(FakeTransport(), evaluated_on=date(2026, 8, 10))
    destination = tmp_path / "phase6" / "evidence.json"
    destination.parent.mkdir(parents=True)
    destination.write_text('{"prior":"valid"}\n', encoding="utf-8")

    def fail_replace(source, target):
        assert source.parent == target.parent == destination.parent
        assert source.exists()
        raise OSError("simulated replace failure")

    with pytest.raises(OSError, match="simulated replace failure"):
        _write_evidence(result, destination, replace=fail_replace)
    assert destination.read_text(encoding="utf-8") == '{"prior":"valid"}\n'
    assert list(destination.parent.glob("*.tmp")) == []

    _write_evidence(result, destination)
    assert json.loads(destination.read_text(encoding="utf-8")) == result.model_dump(
        mode="json"
    )


def test_cp1252_console_failure_is_secondary_to_durable_utf8_evidence(tmp_path):
    result = run_controlled_evaluation(FakeTransport(), evaluated_on=date(2026, 8, 10))
    destination = tmp_path / "phase6" / "evidence.json"

    class FailingConsole:
        def write(self, value):
            del value
            raise UnicodeEncodeError("cp1252", "\u1218", 0, 1, "undefined")

    with pytest.raises(UnicodeEncodeError):
        persist_then_summarize(
            result,
            destination=destination,
            stream=FailingConsole(),
        )
    parsed = json.loads(destination.read_text(encoding="utf-8"))
    assert parsed == result.model_dump(mode="json")
    assert len(result.observations) == 20


def test_evidence_schema_excludes_secrets_transport_and_runtime_authority(tmp_path):
    result = run_controlled_evaluation(FakeTransport(), evaluated_on=date(2026, 8, 10))
    destination = tmp_path / "phase6" / "evidence.json"
    _write_evidence(result, destination)
    serialized = destination.read_text(encoding="utf-8").lower()
    for prohibited in (
        "api_key",
        "authorization",
        "bearer",
        "environment",
        "transport",
        "request_id",
        "raw_response",
    ):
        assert prohibited not in serialized
    assert set(type(result).model_fields) == {
        "provider_id",
        "model_id",
        "corpus_version",
        "evaluated_on",
        "observations",
        "report",
        "input_tokens",
        "output_tokens",
        "estimated_cost_usd",
    }
    assert not {
        "api_key",
        "authorization",
        "credential",
        "environment_secret",
        "raw_response",
        "transport",
    }.intersection(type(result).model_fields)
    assert EVIDENCE_PATH.parts[:3] == ("artifacts", "intelligence", "phase6")
