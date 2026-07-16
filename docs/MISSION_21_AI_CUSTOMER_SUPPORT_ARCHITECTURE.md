# Mission 21 — AI Customer Support, Dispute and Resolution Architecture

Date: 2026-07-16
Status: **Architecture approved for documentation preservation. No implementation or activation authorized.**

## 1. Decision and boundaries

Extend the existing Support module inside the modular monolith. A provider-neutral
language adapter handles untrusted language; a deterministic Support Case Orchestrator
alone validates state, authorization, evidence freshness, policy version, action class
and escalation. The AI has no database, network, generic tool or money access.

AI may classify, summarize, translate, retrieve purpose-scoped projections, explain
versioned policy, request missing information, recommend an allow-listed action and
prepare handoff. It cannot decide safety, identity, fraud, restrictions, material money,
refunds, compensation, wallet changes, payout disputes or legal conclusions. Customer
Recovery owns future remedies; Pricing owns fare calculation; wallet/ledger systems own
money movement; owning ride domains remain evidence authorities.

## 2. Components

- **Support Case Orchestrator:** server-authoritative lifecycle, ownership, deadlines,
  idempotency, optimistic concurrency, escalation and reopening.
- **Policy registry:** immutable effective-dated triage, escalation, language,
  allow-list, deadline and presentation policies; ambiguity fails closed.
- **Evidence gateway:** purpose- and role-scoped references to owning-domain projections;
  raw sensitive records are not copied into cases.
- **AI language adapter:** structured intent/summary/translation proposals with model,
  prompt, glossary and evaluation versions; all output is untrusted until validated.
- **Tool broker:** narrow typed read tools and non-consequential case tools, scoped to
  one authenticated case; denies unlisted parameters and records every attempt/result.
- **Safety router:** deterministic emergency/safety fast path that bypasses conversation
  and ordinary queues but never declares a person safe or closes an emergency.
- **Human work queues:** general Support, Safety, Identity, Fraud, Finance/Payout, Legal,
  Accessibility and Operations specialists with explicit acceptance and ownership.
- **Projection service:** rider/driver case status, requested evidence, response stage,
  handoff state, explanation, reopening and history; deterministic fallback remains
  available during AI/provider outage.

## 3. Category routing

Rider/driver guidance, harmless classification correction, known-outage explanation,
countdown/suppression explanation, lost-property contact setup, approved airport
guidance, recent-case reopen and non-financial apology are **proposed future allow-list
candidates**, not authorized actions. Safety, emergency, identity/recovery, fraud,
restriction/deactivation, material financial disputes, refunds/compensation, payout,
legal requests, coordinated abuse and contradictory evidence always route to the typed
human/specialist queue regardless of AI confidence.

Delivery and Marketplace may later supply evidence projections but keep separate order,
merchant, courier and remedy authorities. Mission 21 must not invent those lifecycles.

## 4. Evidence and explainability

An evidence graph stores typed references, not duplicated raw trails: source domain,
aggregate/reference ID, projection/version, purpose, sensitivity, freshness, integrity
status and access decision. Permitted sources include ride/dispatch/reservation events,
Mission 20 arrival/wait/notification/continuity/suppression evidence, Active Ride
Confidence, pickup/landmark/airport guidance, platform incidents, support messages,
uploaded-file metadata, prior decisions, policies and audits.

Every recommendation/proposal includes case and decision IDs, category, policy ID/version,
evidence references, calibrated confidence, reason codes, missing evidence, proposed and
prohibited actions, escalation status, grounded English/Amharic presentation boundary
and audit timestamp. Hidden chain-of-thought is neither required nor stored.

## 5. Emergency flow

Safety-language rules and a visible user action immediately create/mark a restricted
case, display locally verified configurable instructions, preserve minimum context and
route to a staffed specialist. Authorized location/contact sharing is separately
consented or lawfully configured and audited. Ordinary rate limits cannot block the
path. AI may translate only under stricter verified templates and may not delay routing,
determine safety, contact authorities autonomously or close an active emergency.
Ethiopian numbers, agencies, hours and procedures remain unset pending local validation.

## 6. Languages and degraded operation

Launch design supports Amharic and English, correctable detection, preserved original
text, visibly marked translations and versioned glossaries. Translation confidence is
separate from case confidence. Low-confidence or safety translation escalates. Future
languages implement the same contract after native-speaker evaluation.

If AI is slow or unavailable, the app shows the current stage and offers deterministic
menus, immediate case creation and human/safety routing. No blank or indefinite loading
state is allowed. Weak-network commands are idempotent and resumable from snapshots.

## 7. Scale, consistency and observability

Use PostgreSQL transactions, append-only events, optimistic versions and transactional
outbox. Partition/archive only after measured growth; do not add a broker, vector store
or microservice prematurely. All commands carry idempotency keys and expected versions.
Metrics cover queue age, transition failures, under-escalation, unsupported claims,
citation validity, language quality, overrides, reopenings, provider latency/uptime/cost
and privacy/tool denials without sensitive message/location labels.

## 8. Rollout and rollback

Stages: deterministic menus; shadow classification; agent-assist summaries; agent-assist
recommendations; separately approved low-risk automation; measured expansion. Each stage
is disabled by default and reversible to the prior deterministic stage. Provider outage
always falls back without preventing case creation or emergency escalation.

No runtime, migration, dependency, provider, financial action or activation is approved
by this architecture proposal.

## 9. Future customer-support experience extension points

These future UI projections consume existing authoritative evidence and create no new
decision or collection authority:

- A “Why did AYO decide this?” projection renders policy version, reason codes, cited
  evidence, missing evidence, prohibited actions and appeal status in plain English or
  Amharic.
- A rich ride timeline composes ordered, versioned references from ride, dispatch,
  scheduled, Mission 20, pickup, notification, outage and support domains without copying
  their raw records into Support.
- Privacy-safe visual replay may render coarse, purpose-limited segments and confidence
  states. It must not expose raw GPS trails, post-trip location, hidden fraud/safety
  signals or one party’s restricted evidence to another.
- One-tap appeal creates an idempotent reopen/appeal command linked to the cited decision
  and may attach separately governed evidence metadata. Content storage, scanning,
  consent and retention remain separate approval gates.
- Support, rider and driver views use the same canonical event references and ordering
  with role- and purpose-specific redaction. Consistent facts do not mean identical
  access to sensitive fields.
- Simple-language explanations use versioned, legally reviewed message components.
  Generative wording cannot change policy meaning, omit appeal rights or turn a proposal
  into an authoritative decision.

Future clients receive versioned projections and never direct evidence-gateway or model-
tool access. No UI implementation is authorized here.

## 10. Future channel, collaboration and learning seams

All future channels enter through a provider-neutral `SupportChannelAdapter` and append
to the same authenticated case; channel content never bypasses triage, policy, evidence
scope or specialist routing.

- **Voice and optional voice AI:** consent-aware session metadata, transcript provenance,
  language confidence and human takeover. Voice AI remains an untrusted language
  interface and cannot authenticate by voice, decide a case or delay emergency routing.
- **Video and screen sharing:** separately consented, time-bounded sessions with visible
  indicators, revocation and role-scoped access. Recording defaults off; capture/storage
  requires separate policy and provider approval.
- **Co-browsing:** allow-listed screen/field assistance only. Support cannot read hidden
  fields, credentials, payment secrets or unrelated app areas, or perform a consequential
  action as the user.
- **Live support location:** explicit purpose, precision, recipient, expiry and revoke
  controls; safety sharing uses its restricted boundary. It is not a general tracking
  feed or independently authoritative evidence.
- **Family and diaspora cases:** explicit booker, passenger, payer and authorized-
  representative roles with separate consent, visibility and action rights. Relationship
  claims never substitute for identity or account ownership.
- **Quality and satisfaction analytics:** versioned rubrics and privacy-minimised
  aggregates may measure service quality. Scores cannot become hidden rider/driver
  punishment, safety truth, employment action or case authority.
- **Versioned knowledge base:** articles have owner, jurisdiction/language, citations,
  effective dates, review/expiry and withdrawal state; stale/conflicting material fails
  closed.
- **Governed learning:** training or tuning is prohibited by default. A future pipeline
  may use only separately approved, human-reviewed resolutions with lawful purpose,
  minimisation, de-identification, provenance, withdrawal/deletion governance and
  independent evaluation. Human review does not automatically make a label correct.

No channel provider, model, recording, streaming, storage, UI or learning pipeline is
authorized by these extension seams.
