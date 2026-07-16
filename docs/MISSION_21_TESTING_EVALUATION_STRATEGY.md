# Mission 21 — Testing and Evaluation Strategy

Status: **Architecture proposal; thresholds require representative baselines and approval.**

## Deterministic system tests

- Every valid/invalid state transition, owner transfer, deadline breach, reopen and close.
- Authentication, RBAC, ownership, step-up, case isolation and prohibited tool/action.
- Idempotency, stale version, concurrency, retry, out-of-order and transactional outbox.
- Evidence freshness/integrity/citation and missing/contradictory evidence escalation.
- Emergency bypass, no AI closure, provider outage and deterministic fallback.
- Weak-network resume, app restart, duplicate message and visible loading/fallback states.
- Retention, deletion, legal hold, masking, audit access and cross-border policy denial.
- Timeline ordering and factual consistency across rider, driver and Support views with
  role-specific redaction; no raw GPS or restricted safety/fraud leakage in replay.
- Appeal idempotency, decision linkage, evidence-metadata validation and preservation of
  the original decision history.
- Plain-language “why” fidelity, citation completeness, appeal-right visibility and
  equivalent policy meaning in Amharic and English.
- Consent, visible participants, recording-off default, revoke/expiry and human takeover
  for future voice, video and screen-sharing references.
- Co-browse field/action allow-lists and credential/payment-secret isolation.
- Live-location purpose, precision, recipient, expiry and deletion enforcement.
- Family/diaspora role and cross-role authorization matrices.
- Knowledge version, expiry, conflict and withdrawal behavior.
- Quality/CSAT purpose limitation, fairness and gaming resistance.
- Learning-dataset approval, provenance, de-identification, poisoned-label resistance and
  deletion/withdrawal propagation.

## AI evaluation corpus

Use synthetic and consented/approved de-identified cases only. Maintain balanced rider/
driver, Amharic/English, code-switching, accessibility, airport, cash, weak-network,
fraud, safety and adversarial prompt-injection sets. Human-reviewed gold labels include
intent, category, escalation, evidence citations, unsupported claims, translation meaning
and permitted/prohibited actions. Production content is not training data without
separate approval.

## Stage gates

Measure classification precision/recall by category/language; emergency and safety
under-escalation; hallucinated/unsupported claims; citation precision and completeness;
translation adequacy; resolution/ownership time; reopen/repeat-contact; satisfaction;
rider/driver parity and overturns; human override; provider latency/uptime/cost; privacy
and unauthorized-tool attempts. Targets must be approved after shadow baselines. Known
emergency-routing defects, financial/account authority violations, cross-case leakage or
uncited consequential claims are zero-tolerance blockers.

Rollout advances only when the current stage passes for a representative observation
window and Operations can staff the fallback. Regression, drift, incident or provider
degradation automatically returns to the prior deterministic stage.

Future channel gates measure transcription/translation accuracy, emergency handoff,
human takeover, consent/revoke correctness and outage fallback. Quality scores use a
versioned human rubric; satisfaction is an aggregate service signal, never a ground-
truth label for individual blame or automated sanctions.
