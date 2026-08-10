# AYO Intelligence Phase 7 nano evaluation readiness

**Status:** PRE-PRODUCTION architecture candidate; no Phase 7 provider call has occurred

**Research date:** 2026-08-10

## Problem and success threshold

Phase 6 measured OpenAI `gpt-5.4-mini-2026-03-17` at 90% reliability,
exact preservation and locale adherence, with p95 latency of 2,054 ms. Those results
failed the locked 100% completeness-dependent technical gates and the p95 latency limit
of 2,000 ms. Phase 7 asks whether the smaller, faster dated nano snapshot can meet the
same rules on the same 20 synthetic scenarios. It does not change any gate or confer
provider recommendation, admission, activation or production approval.

## Current official evidence

OpenAI's model catalog lists the exact `gpt-5.4-nano-2026-03-17` snapshot. The model
supports `v1/responses`, Structured Outputs and reasoning effort `none`. Current standard
text pricing is USD 0.20 per million input tokens and USD 1.25 per million output tokens.
Snapshots pin behavior relative to a floating alias but remain subject to future provider
deprecation, so lifecycle evidence must be reviewed again before execution.

Official sources reviewed on 2026-08-10:

- https://developers.openai.com/api/docs/models/gpt-5.4-nano
- https://openai.com/index/introducing-gpt-5-4-mini-and-nano/

The fixed 20-call run permits at most 5,120 output tokens. Using a deliberately
conservative planning allowance of 8,000 input tokens across the fixed corpus, the
estimated maximum cost at current rates is USD 0.008. This is comparative planning
evidence, not an approved budget or a guarantee of billed usage.

## Recommendation and alternatives

Use the exact nano snapshot for one technical evaluation only after this configuration
candidate is reviewed, merged and post-merge locked. It is the smallest controlled next
comparison because it preserves the already reviewed OpenAI HTTPS edge, account/credential
path, strict schema and measurement method while testing the explicit latency/cost
hypothesis.

- Re-running the mini snapshot was rejected: its exact evidence is already admitted and
  repeating it would not test the faster-model hypothesis.
- Moving now to Anthropic Haiku or Google Gemini Flash-Lite was deferred: either would add
  a new credential, account-policy assessment, request/response edge and cross-provider
  confound before the same-provider model-size hypothesis is measured.
- A generic multi-provider router was rejected as unnecessary runtime architecture.

Provider choice for this experiment is not provider recommendation. Privacy, training
use, retention, region/data location, security/compliance and account applicability remain
unresolved and cannot become favorable merely because a credential exists or an API call
works.

## Minimal architecture delta

The Phase 6 implementation hard-coded its model, pricing and evidence path, and the
repository ignored only Phase 6 artifacts. Safe Phase 7 execution therefore requires a
source candidate before any call.

The candidate extracts only those three candidate-specific values into an immutable
configuration accepted by the same locked request, observation, Phase 5 evaluation and
UTF-8 atomic evidence pipeline. The original `run_controlled_evaluation` entry point still
uses the exact Phase 6 configuration. A small engineering-only nano entry point fixes:

- model: `gpt-5.4-nano-2026-03-17`;
- pricing: USD 0.20 input / USD 1.25 output per million tokens;
- evidence: `artifacts/intelligence/phase7/controlled_openai_nano_evaluation.json`.

It refuses to start if that evidence path already exists. Phase 7 JSON is gitignored and
cannot overwrite Phase 6 Run 2 evidence. The fixed corpus, maximum 20 sequential calls,
two-second timeout, zero retry, zero failover, `store: false`, `tools: []`, stateless
request, strict schema, exact preservation and Phase 5 hard gates remain unchanged.

The entry point is manual engineering tooling only. It is not imported by routes,
application startup, Phase 4 runtime, workers, schedulers or mobile. The runtime feature
flag remains disabled by default.

## Risks and stop conditions

- Exact snapshot availability and pricing can drift; re-check official evidence before
  the separately authorized execution.
- Existing account access to the snapshot is not proven by public availability. Model
  rejection must stop the run without substitution.
- An existing Phase 7 artifact blocks execution rather than permitting overwrite.
- A partial run consumes its attempted-call allowance; no resume or retry is automatic.
- Technical exact Amharic output cannot satisfy native review.
- Even perfect technical results do not resolve policy/account gates or progress manual
  governance.

No Phase 7 call was made while preparing this readiness candidate. Live execution is
blocked until separate CTO review, merge authorization, merge and post-merge lock.
