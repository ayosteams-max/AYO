# AYO Intelligence Phase 6 controlled evaluation status

**Status:** PRE-PRODUCTION engineering foundation; first experiment evidence is not admissible

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

No live provider call was made during this repair. A second controlled live evaluation
requires separate Founder/CEO authorization after CTO review.
