from __future__ import annotations

import http.client
import json
import os
import time
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, Final, Protocol

from BACKEND.merchant_intelligence.live_provider_evaluation import (
    ControlledEvaluationResult,
    ProviderHttpResult,
    persist_then_summarize,
)
from BACKEND.merchant_intelligence.provider_evaluation import (
    MERCHANT_ACK_EVALUATION_CORPUS,
    CandidateTechnicalProfile,
    EvaluationScenario,
    ObservationOutcome,
    ProviderObservation,
    evaluate_offline_candidate,
)

PROVIDER_ID: Final = "anthropic"
MODEL_ID: Final = "claude-haiku-4-5-20251001"
CORPUS_VERSION: Final = "merchant_ack_corpus_v1"
MAX_CALLS: Final = 20
TIMEOUT_SECONDS: Final = 2.0
MAX_OUTPUT_TOKENS: Final = 256
ANTHROPIC_API_VERSION: Final = "2023-06-01"
INPUT_PRICE_USD_PER_MILLION: Final = 1.0
OUTPUT_PRICE_USD_PER_MILLION: Final = 5.0
_HOST: Final = "api.anthropic.com"
_PATH: Final = "/v1/messages"
EVIDENCE_PATH: Final = Path(
    "artifacts/intelligence/phase8/controlled_anthropic_haiku_evaluation.json"
)

_INSTRUCTIONS: Final = (
    "Return exactly the supplied canonical merchant explanation. Preserve locale, "
    "headline, body, facts, and actionability exactly. Add nothing. Return only the "
    "required structured output."
)
_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "locale": {"type": "string", "enum": ["en", "am"]},
        "headline": {"type": "string", "maxLength": 80},
        "body": {"type": "string", "maxLength": 240},
    },
    "required": ["locale", "headline", "body"],
}


class AnthropicEvaluationTransport(Protocol):
    def post(self, payload: bytes, *, timeout_seconds: float) -> ProviderHttpResult: ...


class AnthropicHttpsTransport:
    """Credential-owning manual evaluation edge; never product runtime."""

    __slots__ = ("_credential",)

    def __init__(self, credential: str) -> None:
        if not credential.strip():
            raise ValueError("Anthropic credential is unavailable")
        self._credential = credential

    def __repr__(self) -> str:
        return "AnthropicHttpsTransport(credential=<redacted>)"

    def post(self, payload: bytes, *, timeout_seconds: float) -> ProviderHttpResult:
        connection = http.client.HTTPSConnection(_HOST, timeout=timeout_seconds)
        try:
            connection.request(
                "POST",
                _PATH,
                body=payload,
                headers={
                    "anthropic-version": ANTHROPIC_API_VERSION,
                    "content-type": "application/json",
                    "x-api-key": self._credential,
                },
            )
            response = connection.getresponse()
            return ProviderHttpResult(status_code=response.status, body=response.read())
        finally:
            connection.close()


def _request_payload(scenario: EvaluationScenario) -> bytes:
    canonical = {
        "locale": scenario.locale,
        "headline": scenario.expected_headline,
        "body": scenario.expected_body,
    }
    request = {
        "model": MODEL_ID,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "system": _INSTRUCTIONS,
        "messages": [
            {
                "role": "user",
                "content": json.dumps(
                    canonical, ensure_ascii=False, separators=(",", ":")
                ),
            }
        ],
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": _SCHEMA,
            }
        },
    }
    return json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode()


def _output_text(response: Mapping[str, Any]) -> str:
    content = response.get("content")
    if not isinstance(content, list) or len(content) != 1:
        raise ValueError("response must contain one content block")
    block = content[0]
    if not isinstance(block, Mapping) or block.get("type") != "text":
        raise ValueError("response content is not one text block")
    text = block.get("text")
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


def _failure(
    scenario: EvaluationScenario,
    outcome: ObservationOutcome,
    latency_ms: int,
) -> tuple[ProviderObservation, int, int]:
    return (
        ProviderObservation(
            provider_id=PROVIDER_ID,
            model_id=MODEL_ID,
            scenario_id=scenario.scenario_id,
            outcome=outcome,
            latency_ms=latency_ms,
        ),
        0,
        0,
    )


def _observation(
    scenario: EvaluationScenario,
    transport: AnthropicEvaluationTransport,
) -> tuple[ProviderObservation, int, int]:
    started = time.monotonic()
    try:
        result = transport.post(
            _request_payload(scenario), timeout_seconds=TIMEOUT_SECONDS
        )
    except TimeoutError:
        latency = min(round((time.monotonic() - started) * 1_000), 60_000)
        return _failure(scenario, ObservationOutcome.TIMEOUT, latency)
    except (OSError, http.client.HTTPException):
        latency = min(round((time.monotonic() - started) * 1_000), 60_000)
        return _failure(scenario, ObservationOutcome.PROVIDER_ERROR, latency)

    latency = min(round((time.monotonic() - started) * 1_000), 60_000)
    if latency > TIMEOUT_SECONDS * 1_000:
        return _failure(scenario, ObservationOutcome.TIMEOUT, latency)
    if result.status_code < 200 or result.status_code >= 300:
        return _failure(scenario, ObservationOutcome.PROVIDER_ERROR, latency)

    try:
        response = json.loads(result.body)
        if not isinstance(response, Mapping):
            raise ValueError("provider response is not an object")
        if response.get("model") != MODEL_ID:
            raise ValueError("provider response model identity mismatch")
        parsed = json.loads(_output_text(response))
        if not isinstance(parsed, Mapping) or set(parsed) != {
            "locale",
            "headline",
            "body",
        }:
            raise ValueError("provider output schema mismatch")
        observation = ProviderObservation(
            provider_id=PROVIDER_ID,
            model_id=MODEL_ID,
            scenario_id=scenario.scenario_id,
            outcome=ObservationOutcome.RESPONSE,
            latency_ms=latency,
            locale=parsed["locale"],
            headline=parsed["headline"],
            body=parsed["body"],
        )
        input_tokens, output_tokens = _usage(response)
        return observation, input_tokens, output_tokens
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _failure(scenario, ObservationOutcome.MALFORMED, latency)


def run_phase_8_evaluation(
    transport: AnthropicEvaluationTransport, *, evaluated_on: date
) -> ControlledEvaluationResult:
    """Evaluate the fixed corpus once; no retry, failover, warm-up, or resume."""
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
        documented_rate_limit=(
            "AYO account tier is not verified by this controlled evaluation."
        ),
        lifecycle_risk=(
            "Pinned snapshot remains subject to Anthropic deprecation and serving "
            "infrastructure evolution."
        ),
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
    estimated_cost = (
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
        estimated_cost_usd=estimated_cost,
    )


def main() -> int:
    if EVIDENCE_PATH.exists():
        raise SystemExit("Phase 8 evidence already exists; refusing to overwrite")
    credential = os.environ.get("ANTHROPIC_API_KEY")
    if credential is None or not credential.strip():
        raise SystemExit("approved Anthropic credential is unavailable")
    result = run_phase_8_evaluation(
        AnthropicHttpsTransport(credential), evaluated_on=date.today()
    )
    persist_then_summarize(result, destination=EVIDENCE_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
