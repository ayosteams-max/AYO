# AYO Support and Internal Operations Architecture

Status: CEO/CTO-approved Mission 9 implementation baseline (2026-07-15).

## Decision and research conclusion

AYO uses a bounded support-case workflow inside the FastAPI modular monolith, with PostgreSQL 17 as authority. This is smaller and safer than a full ticketing suite or event-driven platform while preserving provider-neutral seams. Case state is mutable under optimistic concurrency; case events, messages and AI interaction evidence are append-only through repositories. No broker, vector database, model, speech, telephony, messaging or ticketing provider is selected.

Alternatives considered were a simple workflow, full ticketing, event-driven management, third-party ticketing, and AI-first, human-first or hybrid orchestration. A simple table lacked audit and resource controls; full/event-driven or third-party platforms add premature complexity or lock-in; AI-only is unsafe and human-only raises cost and friction. The bounded hybrid workflow is the smallest reliable choice.

Evidence reviewed includes NIST AI RMF and its Generative AI Profile for governed human oversight, OWASP guidance on sensitive-information disclosure and excessive agency, Zendesk's immutable ticket-audit pattern as an industry reference, and W3C BCP 47 language-tag guidance. These inform the design; competitor behavior is not copied as policy.

## Model and lifecycle

`support_cases` stores structured case state and opaque related-resource references, never copied ride, payment, identity, location or audit records. `support_case_events` holds bounded workflow history. `support_case_messages` separates customer-visible messages and restricted notes. `support_ai_interactions` stores provider-neutral references, confidence, action/outcome and takeover metadata—never hidden reasoning.

Statuses are `new`, `gathering_information`, `in_progress`, `waiting_for_customer`, `waiting_for_internal_team`, `escalated`, `resolved`, `closed`, and `cancelled`. The domain contract permits transitions. Closed/cancelled are terminal; resolved may close or reopen. Emergency cases must begin escalated in safety. AYO never represents AI as emergency services.

Queues are general, safety, fraud, finance, identity and legal. Queue and agent assignment are server-authoritative. Restricted queues remain separated.

## AI action policy and escalation

- Green: approved FAQs/guidance, explanations, structured collection, case creation, low-risk updates and escalation. Low/unknown confidence or conflict requires clarification or takeover.
- Yellow: refund, fare, compensation, recovery, payment, payout, identity-correction or temporary-restriction recommendations require an approved human/verified workflow.
- Red: financial/wallet mutation, permanent account action, verified-identity mutation, control bypass, safety/fraud override, unrestricted audit access, cross-customer disclosure, legal approval and emergency guarantees are prohibited.

Confidence is never the only control. AI uses a dedicated service identity and the existing eight permissions, and reads only assigned cases. Six new queue permissions are human-operation boundaries and are excluded from the AI permission set. Escalation to a restricted queue clears AI assignment.

## Authorization, audit and transactions

Customers access only cases linked to their identity. Anonymous creation is supported, but retrieval needs a future approved possession/recovery design. AI requires assignment plus permission. Staff require the case queue's permission. No public route exists.

Creation, domain event and Mission 5 audit commit in one Unit of Work; rollback removes all. Idempotency suppresses duplicate creation/success evidence. Version checks reject stale concurrent updates. Denials are bounded audited events. Logs may use opaque IDs/correlation IDs, never bodies or restricted metadata.

## Privacy, language and voice readiness

Messages are bounded to 2,000 characters and carry BCP 47-style language tags (`am-ET`, `en-ET`). Credentials, OTPs, tokens, payment security values and private keys are rejected. Internal notes are excluded from customer queries. Precise histories, unrestricted transcripts, recordings and source records are prohibited.

Recordings/transcripts are not retained by default. Future retention requires purpose, consent, redaction, access controls, Ethiopian legal review and an approved period. Speech-derived critical values require confirmation and recognition failure must offer human support. Exchanges must remain bounded and retryable for poor networks.

Retention classes distinguish routine, sensitive, safety, financial, identity and legal-hold-candidate cases. Exact Ethiopian retention/deletion/legal-hold periods require professional approval.

## Availability and operations

PostgreSQL failure denies restricted reads and visibly fails required writes. Clients retry interrupted creation with idempotency keys. Measure latency/errors, stale updates, queue age, escalation/takeover time, denials, redaction rejection and database saturation before adding Redis, brokers or vector search.

Runtime may select/insert/update cases but not delete. It may select/insert—but not update/delete—events, messages and AI interactions. Migration ownership remains separate; startup migration and destructive downgrade remain prohibited.

## Unresolved launch decisions

CEO/CTO and Ethiopian professional verification remain required for staffing/emergency procedures, anonymous recovery proof, recording/transcript consent, retention/legal hold, support disclosures, accessibility operations, and every provider/model selection.
