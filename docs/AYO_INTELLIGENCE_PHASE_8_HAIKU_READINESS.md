# AYO Intelligence Phase 8 Anthropic Haiku readiness

**Status:** PRE-PRODUCTION readiness merged and locked; one admissible technical evaluation completed; awaiting CTO review; admission recommendation not eligible

**Research and revalidation date:** 2026-08-10

## Problem and success threshold

The Phase 6 OpenAI mini and Phase 7 OpenAI nano screens each returned 18 of the
20 fixed scenarios and failed the locked reliability, exact-preservation,
locale-adherence and two-second p95 gates. Phase 8 prepares one genuinely
different provider edge to test whether Anthropic's fastest dated Haiku snapshot
has a stronger chance of meeting the same bounded workload. It does not change
the deterministic Phase 1/2 fallback or grant command, provider, admission,
activation or production authority.

The screen remains exactly `merchant_ack_corpus_v1`: 20 canonical synthetic
scenarios, one sequential attempt each, no retry or failover, strict structured
output, exact string comparison, 100% reliability/exactness/locale adherence and
p95 latency at most 2,000 ms.

## Current official evidence

Anthropic's current documentation identifies
`claude-haiku-4-5-20251001` as the Claude API's exact Haiku 4.5 model ID.
Anthropic states that a model ID identifies a pinned version whose model remains
constant for that ID; the shorter `claude-haiku-4-5` form is an alias and is not
used by AYO. Haiku 4.5 remains listed as current, with standard pricing of USD
1.00 per million input tokens and USD 5.00 per million output tokens.

The first-party Messages API uses `POST /v1/messages`, `x-api-key`, and the
required `anthropic-version: 2023-06-01` header. Structured Outputs are GA for
Haiku 4.5 through `output_config.format` with a JSON schema. The provider
guarantees schema conformance, not canonical semantic equality; AYO therefore
continues to compare `locale`, `headline` and `body` exactly.

AYO also requires `stop_reason: "end_turn"` before parsing a response as successful.
Anthropic documents that refusals can return HTTP 200 and that `refusal` and
`max_tokens` may bypass Structured Output guarantees. Every other, missing or
future stop reason therefore fails closed as `MALFORMED`, even when its text is
otherwise valid canonical JSON; no retry or token-limit increase follows.

Anthropic compiles a structured-output schema into a grammar. The first use of a
new schema can incur compilation latency and the compiled grammar may be cached
for up to 24 hours. A future authorized run must count the first canonical
scenario honestly. There is no warm-up, preflight generation or schema-only
provider call in the runner.

Official sources reviewed on 2026-08-10:

- https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions
- https://platform.claude.com/docs/en/about-claude/models/overview
- https://platform.claude.com/docs/en/api/messages/create
- https://platform.claude.com/docs/en/manage-claude/authentication
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- https://platform.claude.com/docs/en/about-claude/pricing
- https://platform.claude.com/docs/en/about-claude/model-deprecations
- https://platform.claude.com/docs/en/api/service-tiers

Public documentation does not establish AYO account access, billing, rate tier,
ZDR, retention, region/data location, security/compliance terms or applicable
contract. Those policy/account gates remain `UNKNOWN`. Priority Tier is neither
assumed nor required; the first screen is designed for ordinary Messages API
service with no `service_tier` request field.

## Bounded architecture

The existing OpenAI controlled runner is provider-neutral only after an
observation has been constructed. Its HTTPS request, response parsing and
provider identity are intentionally OpenAI-specific. Phase 8 therefore does not
refactor the post-merge-locked Phase 6/7 machinery or force Anthropic through an
OpenAI protocol abstraction.

The engineering-only Anthropic edge:

1. reads the locked Phase 5 corpus;
2. constructs one stateless Messages request for each canonical scenario;
3. uses the exact dated model, fixed host/path, two-second timeout and no tools,
   thinking, history, service-tier selection, retry or failover;
4. constrains direct output to a closed `locale`/`headline`/`body` schema;
5. converts only parsed bounded fields and token counts into the existing
   `ProviderObservation` and `ControlledEvaluationResult` contracts;
6. delegates all hard-gate calculation to the locked Phase 5 evaluator; and
7. persists sanitized UTF-8 evidence atomically through the existing writer at
   `artifacts/intelligence/phase8/controlled_anthropic_haiku_evaluation.json`.

The artifact path is separate from Phase 6 and Phase 7, is gitignored and causes
a pre-credential/pre-call refusal if evidence already exists. Credentials,
headers, request IDs and raw transport bodies cannot enter the evidence model.
The manual entry point expects `ANTHROPIC_API_KEY`; no credential or account was
created or accessed during readiness work.

## Alternatives and risks

- A generic provider router was rejected as premature product/runtime
  architecture.
- Refactoring the locked OpenAI runner into a universal transport was rejected
  because its protocol and parsing are intentionally provider-specific.
- Copying the Phase 5 evaluator was rejected; it remains the single hard-gate
  authority.
- Priority Tier was rejected as an assumption. Any special AYO entitlement is a
  later evidence and governance question.

Material remaining risks are cold schema-compilation latency, shared-capacity
queueing, exact-text failure despite valid JSON, model retirement, unavailable
AYO account access, unknown rate limits and unresolved privacy/training/
retention/region/security evidence. Machine-exact Amharic remains
`NEEDS_NATIVE_AMHARIC_REVIEW` and cannot create human approval.

## Isolation and stop condition

The Phase 8 module is not imported by routes, `main.py`, application composition,
startup, workers, schedulers, mobile or UI. It has no product feature flag or
runtime provider composition. `MERCHANT_GENERATIVE_EXPLANATION_ENABLED` remains
false by default.

This readiness candidate made zero Anthropic, OpenAI or other provider calls. At that
time, live evaluation required separate Founder/CEO authorization after review, merge
authorization, merge and post-merge lock.

## Readiness history

AP-069 records the pre-execution readiness decision truthfully: no Phase 8 call had
occurred when the architecture was approved. The candidate was subsequently reviewed,
merged and post-merge locked without changing the fixed corpus, two-second timeout,
zero-retry/failover rule, exact-preservation policy or Phase 5 hard gates.

## Live evaluation — completed with admissible evidence

Founder/CEO authorized one controlled execution on 2026-08-11. It ran from authoritative
main `8b4413be4c914fcb71315a2946c9c171abb6efc2`, tree
`534ae673489814506aef7b3152a87d2143373774`, against Anthropic
`claude-haiku-4-5-20251001` and `merchant_ack_corpus_v1`. The exact gitignored UTF-8
artifact is bound to governance by SHA-256
`5cc2746feffec07df8274432ab113c1194e232ede9add5d751d214b30d3e1a73`;
the raw provider outputs are not committed.

The 20 sequential attempts used zero retries and zero failover and produced 13 responses,
seven timeouts, zero malformed outputs and zero provider errors. Exact preservation,
locale adherence and reliability were each 13/20 (65%). English returned 6/10 and
Amharic returned 7/10 exact, locale-correct responses; the remaining scenarios timed out.
Latency was 1,041 ms minimum, 1,537 ms median, 2,057 ms p95, 2,088 ms p99 and 2,088 ms
maximum. Usage was 4,011 input and 657 output tokens; estimated cost was USD 0.007296.

## Admission result — not eligible

The locked p95 gate is at most 2,000 ms, so 2,057 ms fails. Exact preservation, locale
adherence and reliability also fail because timeouts cannot count as successful outputs.
Evidence freshness fails because qualifying mandatory policy evidence remains absent.
Privacy, training/data use, retention, regional/data location, security/compliance and
Amharic human review remain unknown. `NEEDS_NATIVE_AMHARIC_REVIEW` remains required;
7/10 exact machine Amharic responses are not native-language certification.

The technical gates met were server-side-only, mobile credentials absent, arbitrary
client prose forbidden, structured output, exact model version, automatic retry disabled,
automatic failover absent, tool-free, stateless, provider-neutral, production disabled
and corpus complete. The result remains
`eligible_for_admission_recommendation=false`. The candidate is technically evaluated,
but it is not recommended, admitted, Founder-approved, eligible for pre-production
activation, activated or production-approved. CTO review of this evidence remains
required.

## Bounded prior-run comparison

Phase 8 Haiku returned 13/20 responses and 65% reliability, exact preservation and
locale adherence, compared with 18/20 and 90% in each of the Phase 6 mini and Phase 7
nano runs. Its 2,057 ms p95 was 3 ms slower than mini's 2,054 ms and 16 ms faster than
nano's 2,073 ms; all three failed the locked two-second p95 gate. Estimated Phase 8 cost
was USD 0.007296, between mini's USD 0.00831975 and nano's USD 0.002202. Under these
exact controlled runs, changing provider did not resolve the observed AYO reliability,
exact-preservation, locale or latency failures. This bounded result does not establish
universal model performance or permanent provider rejection.

No additional Phase 8 run is authorized. No provider has been recommended, admitted,
activated or connected to AYO product runtime. Broader generative rephrasing and Phase 9
remain unauthorized.
