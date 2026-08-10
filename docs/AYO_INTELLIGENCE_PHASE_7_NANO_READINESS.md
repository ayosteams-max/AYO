# AYO Intelligence Phase 7 nano evaluation readiness

**Status:** PRE-PRODUCTION readiness merged and locked; one admissible technical evaluation completed; admission recommendation not eligible

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

No Phase 7 call was made while preparing this readiness candidate. At that time, live
execution was blocked until separate CTO review, merge authorization, merge and
post-merge lock.

## Readiness history

AP-067 records the pre-execution readiness decision truthfully: no Phase 7 call had
occurred when the configuration was approved. The candidate was subsequently reviewed,
merged and post-merge locked without changing the fixed corpus, two-second timeout,
zero-retry/failover rule, exact-preservation policy or Phase 5 hard gates.

## Live evaluation — completed with admissible evidence

Founder/CEO authorized one controlled execution on 2026-08-10. It ran from authoritative
main `1a2181c82ce600d6dc383adec3a8123e4189c4f7`, tree
`1e7c81a13e8f65394c12e974f6142c4a0d79b4c6`, against OpenAI
`gpt-5.4-nano-2026-03-17` and `merchant_ack_corpus_v1`. The exact gitignored UTF-8
artifact is bound to governance by SHA-256
`bd7a28bb7bd323a4be0981f3248df9081a5fdced87db3ec7e4f100b8f2ba3544`;
the raw provider outputs are not committed.

The 20 sequential attempts used zero retries and zero failover and produced 18 responses,
two timeouts, zero malformed outputs and zero provider errors. Exact preservation, locale
adherence and reliability were each 18/20 (90%). English and Amharic each returned 9/10
exact, locale-correct responses and one timeout. Latency was 1,021 ms minimum, 1,604 ms
median, 2,073 ms p95, 2,126 ms p99 and 2,126 ms maximum. Usage was 2,760 input and 1,320
output tokens; estimated cost was USD 0.002202.

## Admission result — not eligible

The locked p95 gate is at most 2,000 ms, so 2,073 ms fails. Exact preservation, locale
adherence and reliability also fail because timeouts cannot count as successful outputs.
Evidence freshness fails because qualifying mandatory policy evidence remains absent.
Privacy, training/data use, retention, regional/data location, security/compliance and
Amharic human review remain unknown. `NEEDS_NATIVE_AMHARIC_REVIEW` remains required;
9/10 exact machine Amharic responses are not native-language certification.

The technical gates met were server-side-only, mobile credentials absent, arbitrary
client prose forbidden, structured output, exact model version, automatic retry disabled,
automatic failover absent, tool-free, stateless, provider-neutral, production disabled
and corpus complete. The result remains
`eligible_for_admission_recommendation=false`. The candidate is technically evaluated,
but it is not recommended, admitted, Founder-approved, eligible for pre-production
activation, activated or production-approved.

## Bounded Phase 6 comparison

Phase 6 mini (`gpt-5.4-mini-2026-03-17`) and Phase 7 nano each produced 18/20 responses
and 90% reliability, exact preservation and locale adherence. Nano reduced estimated cost
from USD 0.00831975 to USD 0.002202 but recorded p95 latency of 2,073 ms, 19 ms slower
than mini's 2,054 ms. Under these exact controlled runs, the smaller model did not resolve
the observed AYO latency/reliability failure. This does not establish that nano is
universally slower, that another snapshot would behave identically or that OpenAI is
permanently rejected.

No additional Phase 7 run is authorized. No provider has been recommended, admitted,
activated or connected to AYO product runtime. Broader generative rephrasing and Phase 8
remain unauthorized.
