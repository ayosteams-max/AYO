# AYO Intelligence Phase 8 Anthropic Haiku readiness

**Status:** PRE-PRODUCTION architecture/readiness only; no live provider call authorized

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

This readiness candidate makes zero Anthropic, OpenAI or other provider calls.
Live evaluation requires separate Founder/CEO authorization after review, merge
authorization, merge and post-merge lock. No Phase 9 work is authorized.
