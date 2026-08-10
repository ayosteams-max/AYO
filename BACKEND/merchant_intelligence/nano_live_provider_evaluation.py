from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Final

from BACKEND.merchant_intelligence.live_provider_evaluation import (
    ControlledEvaluationConfiguration,
    ControlledEvaluationResult,
    EvaluationTransport,
    OpenAIHttpsTransport,
    persist_then_summarize,
    run_configured_evaluation,
)

PHASE_7_CONFIGURATION: Final = ControlledEvaluationConfiguration(
    model_id="gpt-5.4-nano-2026-03-17",
    evidence_path=Path(
        "artifacts/intelligence/phase7/controlled_openai_nano_evaluation.json"
    ),
    input_price_usd_per_million=0.20,
    output_price_usd_per_million=1.25,
)


def run_phase_7_evaluation(
    transport: EvaluationTransport, *, evaluated_on: date
) -> ControlledEvaluationResult:
    return run_configured_evaluation(
        PHASE_7_CONFIGURATION, transport, evaluated_on=evaluated_on
    )


def main() -> int:
    if PHASE_7_CONFIGURATION.evidence_path.exists():
        raise SystemExit("Phase 7 evidence already exists; refusing to overwrite")
    credential = os.environ.get("OPENAI_API_KEY")
    if credential is None or not credential.strip():
        raise SystemExit("approved OpenAI credential is unavailable")
    result = run_phase_7_evaluation(
        OpenAIHttpsTransport(credential), evaluated_on=date.today()
    )
    persist_then_summarize(result, destination=PHASE_7_CONFIGURATION.evidence_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
