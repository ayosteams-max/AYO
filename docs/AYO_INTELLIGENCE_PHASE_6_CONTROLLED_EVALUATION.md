# AYO Intelligence Phase 6 controlled evaluation status

**Status:** PRE-PRODUCTION engineering foundation; Run 2 technical evidence is admissible but not eligible for admission recommendation

**Date:** 2026-08-10

## Purpose and boundary

Phase 6 adds a manual engineering-only OpenAI evaluation edge for the fixed
`merchant_ack_corpus_v1`. It is not imported by application startup, routes, mobile, or
Phase 4 runtime. It accepts no arbitrary prompt, uses no tools, memory, retrieval, retry,
failover, or background work, and cannot progress provider governance.

The exact technical candidate was OpenAI `gpt-5.4-mini-2026-03-17`, selected as a dated
current snapshot after the earlier provisional `gpt-5-mini-2025-08-07` became deprecated.
This technical choice is not provider recommendation, admission, activation, or production
approval. Account-specific retention, regional processing, and related policy controls
remain unverified.

## First experiment status

The first authorized experiment attempted all 20 fixed synthetic scenarios sequentially,
with one request per scenario, a two-second timeout, no retry, and no failover. After the
loop and transient Phase 5 evaluation completed, Windows attempted to encode the sanitized
multilingual JSON through a `cp1252` console. Amharic could not be encoded, and no durable
result was captured.

The experiment is therefore `EXECUTED_BUT_EVIDENCE_NOT_ADMISSIBLE`. No outcome count,
latency, exactness, locale, reliability, token usage, cost, or hard-gate result may be
reconstructed or inferred. No provider is technically evaluated with admissible evidence,
recommended, admitted, activated, or production-approved.

## Evidence-capture repair

Future authorized execution writes the complete sanitized result as deterministic UTF-8
JSON to `artifacts/intelligence/phase6/controlled_openai_evaluation.json`. The generated
artifact is gitignored. A temporary file is created in the same directory, flushed and
fsynced, then atomically replaces the final path. Failure before replacement preserves any
previous complete evidence. Persistence occurs before an optional ASCII-only console
summary, so console encoding cannot determine evidence survival.

The evidence model contains only provider/model/corpus identity, evaluation date, bounded
`ProviderObservation` values, the Phase 5 `EvaluationReport`, bounded token totals, and a
cost estimate. It excludes credentials, authorization headers, raw transports, raw provider
responses, request IDs, user data, operational identifiers, commands, tools, and runtime
authority.

No live provider call was made during this repair.

## Run 2 admissible technical evaluation

Founder/CEO separately authorized Run 2 on 2026-08-10. It used authoritative main
`517d7d0ccc3d40cb0831c64b0d03ca01d1adb83c`, tree
`47208b0cb691d6c8486fa2c2e2e90b95aebf34e0`, the same exact model and corpus, and the
locked one-call-per-scenario controls. The complete sanitized artifact was durably captured
as UTF-8 and admitted by CTO review. Its exact bytes are bound by SHA-256:

`53644f537440ca1f5b6cc59d33e31a2d91ffaab7ec72e81a0d251d55c17391fb`

Run 2 made 20 attempts with zero retry and zero failover. It recorded 18 responses, two
timeouts, zero malformed outputs and zero provider errors. All 18 responses preserved the
canonical text and locale exactly: English returned 8/10 with two timeouts; Amharic
returned 10/10. Overall exact preservation, locale adherence and reliability were each
18/20 (90%). Latency was 1,228 ms minimum, 1,588 ms median, 2,054 ms p95, 2,093 ms p99
and 2,093 ms maximum. Usage was 2,819 input tokens and 1,379 output tokens; estimated cost
was USD 0.00831975.

The locked p95 requirement is at most 2,000 ms, so 2,054 ms is a failure. Exact
preservation, locale adherence and reliability also fail because all 20 scenarios are
required. Evidence freshness failed because mandatory qualifying policy evidence was not
provided. Privacy, training/data use, retention, regional/data location,
security/compliance and native Amharic review remain unknown. Exact Amharic reproduction
does not satisfy human linguistic review; `NEEDS_NATIVE_AMHARIC_REVIEW` remains in force.

The candidate is technically evaluated with admissible evidence but is not eligible for
admission recommendation. It is not recommended, admitted, Founder-approved, eligible for
pre-production activation, activated or production-approved. No provider is connected to
product runtime, no user/product data was used, and no further live run is authorized.
The raw generated artifact remains gitignored and is not committed.
