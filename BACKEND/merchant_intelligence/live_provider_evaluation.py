from __future__ import annotations

import http.client
import json
import os
import sys
import tempfile
import time
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, Final, Protocol, TextIO

from pydantic import BaseModel, ConfigDict, Field

from BACKEND.merchant_intelligence.provider_evaluation import (
    MERCHANT_ACK_EVALUATION_CORPUS,
    CandidateTechnicalProfile,
    EvaluationReport,
    EvaluationScenario,
    ObservationOutcome,
    ProviderObservation,
    evaluate_offline_candidate,
)

PROVIDER_ID: Final = "openai"
MODEL_ID: Final = "gpt-5.4-mini-2026-03-17"
CORPUS_VERSION: Final = "merchant_ack_corpus_v1"
MAX_CALLS: Final = 20
TIMEOUT_SECONDS: Final = 2.0
MAX_OUTPUT_TOKENS: Final = 256
INPUT_PRICE_USD_PER_MILLION: Final = 0.75
OUTPUT_PRICE_USD_PER_MILLION: Final = 4.50
_HOST: Final = "api.openai.com"
_PATH: Final = "/v1/responses"
EVIDENCE_PATH: Final = Path(
    "artifacts/intelligence/phase6/controlled_openai_evaluation.json"
)
_INSTRUCTIONS: Final = (
    "Return exactly the supplied canonical merchant explanation. Preserve locale, "
    "headline, body, facts, and actionability exactly. Add nothing. Use the required "
    "JSON schema. Do not use tools."
)
_FORMAT: Final[dict[str, Any]] = {
    "type": "json_schema",
    "name": "merchant_operational_explanation",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "locale": {"type": "string", "enum": ["en", "am"]},
            "headline": {"type": "string", "maxLength": 80},
            "body": {"type": "string", "maxLength": 240},
        },
        "required": ["locale", "headline", "body"],
    },
}


class ProviderHttpResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status_code: int = Field(ge=100, le=599)
    body: bytes


class EvaluationTransport(Protocol):
    def post(self, payload: bytes, *, timeout_seconds: float) -> ProviderHttpResult: ...


class OpenAIHttpsTransport:
    """Credential-owning evaluation edge. It is never composed into product runtime."""

    __slots__ = ("_credential",)

    def __init__(self, credential: str) -> None:
        if not credential.strip():
            raise ValueError("OpenAI credential is unavailable")
        self._credential = credential

    def __repr__(self) -> str:
        return "OpenAIHttpsTransport(credential=<redacted>)"

    def post(self, payload: bytes, *, timeout_seconds: float) -> ProviderHttpResult:
        connection = http.client.HTTPSConnection(_HOST, timeout=timeout_seconds)
        try:
            connection.request(
                "POST",
                _PATH,
                body=payload,
                headers={
                    "Authorization": f"Bearer {self._credential}",
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            body = response.read()
            return ProviderHttpResult(status_code=response.status, body=body)
        finally:
            connection.close()


class ControlledEvaluationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: str
    model_id: str
    corpus_version: str
    evaluated_on: date
    observations: tuple[ProviderObservation, ...]
    report: EvaluationReport
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)


def _write_evidence(
    result: ControlledEvaluationResult,
    destination: Path,
    *,
    replace: Any = os.replace,
) -> None:
    """Persist complete sanitized evidence before it becomes externally visible."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    serialized = result.model_dump_json(indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
        replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def write_evidence(result: ControlledEvaluationResult) -> None:
    _write_evidence(result, EVIDENCE_PATH)


def _console_summary(result: ControlledEvaluationResult, stream: TextIO) -> None:
    counts = {
        outcome.value: sum(
            observation.outcome is outcome for observation in result.observations
        )
        for outcome in ObservationOutcome
    }
    stream.write(
        "phase6_evidence_saved "
        f"path={EVIDENCE_PATH.as_posix()} calls={len(result.observations)} "
        f"response={counts['response']} malformed={counts['malformed']} "
        f"timeout={counts['timeout']} provider_error={counts['provider_error']}\n"
    )


def persist_then_summarize(
    result: ControlledEvaluationResult,
    *,
    destination: Path = EVIDENCE_PATH,
    stream: TextIO = sys.stdout,
) -> None:
    _write_evidence(result, destination)
    _console_summary(result, stream)


def _request_payload(scenario: EvaluationScenario) -> bytes:
    canonical = {
        "locale": scenario.locale,
        "headline": scenario.expected_headline,
        "body": scenario.expected_body,
    }
    request = {
        "model": MODEL_ID,
        "store": False,
        "instructions": _INSTRUCTIONS,
        "input": json.dumps(canonical, ensure_ascii=False, separators=(",", ":")),
        "reasoning": {"effort": "none"},
        "tools": [],
        "text": {"format": _FORMAT, "verbosity": "low"},
        "max_output_tokens": MAX_OUTPUT_TOKENS,
    }
    return json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode()


def _output_text(response: Mapping[str, Any]) -> str:
    output = response.get("output")
    if not isinstance(output, list) or len(output) != 1:
        raise ValueError("response must contain one output item")
    item = output[0]
    if not isinstance(item, Mapping) or item.get("type") != "message":
        raise ValueError("response output is not one message")
    content = item.get("content")
    if not isinstance(content, list) or len(content) != 1:
        raise ValueError("response message must contain one content item")
    part = content[0]
    if not isinstance(part, Mapping) or part.get("type") != "output_text":
        raise ValueError("response content is not output text")
    text = part.get("text")
    if not isinstance(text, str):
        raise ValueError("response text is absent")
    return text


def _usage(response: Mapping[str, Any]) -> tuple[int, int]:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return (0, 0)
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        return (0, 0)
    return (max(input_tokens, 0), max(output_tokens, 0))


def _observation(
    scenario: EvaluationScenario,
    transport: EvaluationTransport,
) -> tuple[ProviderObservation, int, int]:
    started = time.monotonic()
    try:
        result = transport.post(
            _request_payload(scenario), timeout_seconds=TIMEOUT_SECONDS
        )
    except TimeoutError:
        latency = min(round((time.monotonic() - started) * 1_000), 60_000)
        return (
            ProviderObservation(
                provider_id=PROVIDER_ID,
                model_id=MODEL_ID,
                scenario_id=scenario.scenario_id,
                outcome=ObservationOutcome.TIMEOUT,
                latency_ms=latency,
            ),
            0,
            0,
        )
    except (OSError, http.client.HTTPException):
        latency = min(round((time.monotonic() - started) * 1_000), 60_000)
        return (
            ProviderObservation(
                provider_id=PROVIDER_ID,
                model_id=MODEL_ID,
                scenario_id=scenario.scenario_id,
                outcome=ObservationOutcome.PROVIDER_ERROR,
                latency_ms=latency,
            ),
            0,
            0,
        )
    latency = min(round((time.monotonic() - started) * 1_000), 60_000)
    if latency > TIMEOUT_SECONDS * 1_000:
        return (
            ProviderObservation(
                provider_id=PROVIDER_ID,
                model_id=MODEL_ID,
                scenario_id=scenario.scenario_id,
                outcome=ObservationOutcome.TIMEOUT,
                latency_ms=latency,
            ),
            0,
            0,
        )
    if result.status_code < 200 or result.status_code >= 300:
        return (
            ProviderObservation(
                provider_id=PROVIDER_ID,
                model_id=MODEL_ID,
                scenario_id=scenario.scenario_id,
                outcome=ObservationOutcome.PROVIDER_ERROR,
                latency_ms=latency,
            ),
            0,
            0,
        )
    try:
        response = json.loads(result.body)
        if not isinstance(response, Mapping):
            raise ValueError("provider response is not an object")
        parsed = json.loads(_output_text(response))
        if not isinstance(parsed, Mapping) or set(parsed) != {
            "locale",
            "headline",
            "body",
        }:
            raise ValueError("provider output schema mismatch")
        locale = parsed["locale"]
        headline = parsed["headline"]
        body = parsed["body"]
        observation = ProviderObservation(
            provider_id=PROVIDER_ID,
            model_id=MODEL_ID,
            scenario_id=scenario.scenario_id,
            outcome=ObservationOutcome.RESPONSE,
            latency_ms=latency,
            locale=locale,
            headline=headline,
            body=body,
        )
        input_tokens, output_tokens = _usage(response)
        return observation, input_tokens, output_tokens
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return (
            ProviderObservation(
                provider_id=PROVIDER_ID,
                model_id=MODEL_ID,
                scenario_id=scenario.scenario_id,
                outcome=ObservationOutcome.MALFORMED,
                latency_ms=latency,
            ),
            0,
            0,
        )


def run_controlled_evaluation(
    transport: EvaluationTransport, *, evaluated_on: date
) -> ControlledEvaluationResult:
    if len(MERCHANT_ACK_EVALUATION_CORPUS) != MAX_CALLS:
        raise RuntimeError("controlled evaluation corpus must contain exactly 20 items")
    observations: list[ProviderObservation] = []
    input_tokens = 0
    output_tokens = 0
    for scenario in MERCHANT_ACK_EVALUATION_CORPUS:
        observation, used_input, used_output = _observation(scenario, transport)
        observations.append(observation)
        input_tokens += used_input
        output_tokens += used_output
    profile = CandidateTechnicalProfile(
        provider_id=PROVIDER_ID,
        model_id=MODEL_ID,
        exact_model_version_pinned=True,
        server_side_only=True,
        mobile_credentials_absent=True,
        arbitrary_client_prose_forbidden=True,
        structured_output_supported=True,
        tools_disabled=True,
        stateless=True,
        provider_neutral_edge_adapter=True,
        production_disabled=True,
        automatic_retry_disabled=True,
        automatic_failover_absent=True,
        input_price_usd_per_million_tokens=INPUT_PRICE_USD_PER_MILLION,
        output_price_usd_per_million_tokens=OUTPUT_PRICE_USD_PER_MILLION,
        documented_rate_limit="Account tier is not verified by Phase 6.",
        lifecycle_risk="Pinned snapshot lifecycle remains subject to provider deprecation.",
    )
    frozen_observations = tuple(observations)
    report = evaluate_offline_candidate(
        profile=profile,
        policy_evidence=(),
        observations=frozen_observations,
        amharic_reviews=(),
        evaluated_on=evaluated_on,
        assumed_input_tokens=input_tokens // MAX_CALLS,
        assumed_output_tokens=output_tokens // MAX_CALLS,
    )
    cost = (
        input_tokens * INPUT_PRICE_USD_PER_MILLION
        + output_tokens * OUTPUT_PRICE_USD_PER_MILLION
    ) / 1_000_000
    return ControlledEvaluationResult(
        provider_id=PROVIDER_ID,
        model_id=MODEL_ID,
        corpus_version=CORPUS_VERSION,
        evaluated_on=evaluated_on,
        observations=frozen_observations,
        report=report,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=cost,
    )


def main() -> int:
    credential = os.environ.get("OPENAI_API_KEY")
    if credential is None or not credential.strip():
        raise SystemExit("approved OpenAI credential is unavailable")
    result = run_controlled_evaluation(
        OpenAIHttpsTransport(credential), evaluated_on=date.today()
    )
    persist_then_summarize(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
