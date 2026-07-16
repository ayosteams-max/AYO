# Mission 21 — Proposed Persistence Model

Status: **Non-runtime proposal. No migration is authorized.**

Proposed PostgreSQL-owned records:

- `support_cases`: category, state, priority, owner/queue, policy snapshot, optimistic
  version, deadlines and reopen lineage.
- `support_case_events`: append-only typed transitions and ownership/deadline events.
- `support_participants`: purpose-scoped identity/role references, never caller claims.
- `support_messages`: original content, language, translated-content reference/status and
  sensitivity/retention class.
- `support_evidence_references`: owning domain/type/ID/version, purpose, freshness,
  integrity and access decision; no unnecessary raw duplication.
- `support_decisions`: recommendation/proposal schema, citations, confidence, reason and
  missing-evidence codes, prohibited actions and escalation.
- `support_ai_interactions`: bounded input/output references, provider/model/prompt/
  glossary versions, tool attempts/results and safety filters under approved retention.
- `support_handoffs`: summary, verified roles, timeline references, unresolved questions,
  flags, language/contact state, queue/priority and acceptance.
- `support_uploaded_evidence`: metadata, quarantine/scan status, provenance and retention;
  content storage is a separate design gate.
- `support_idempotency`, `support_policy_snapshots`, `support_access_audit` and shared
  transactional outbox records.

Future timeline and visual-replay screens do not require a duplicated ride-history
store. They compose versioned references at read time or from bounded, rebuildable,
role-redacted projections. Appeals append an appeal/reopen event and evidence metadata;
they never edit the disputed decision. Plain-language explanations retain template,
glossary and policy versions plus the exact presented text under approved retention.

Case transactions atomically append the transition, update expected version, persist
decision/reference changes, audit access and enqueue intents. Corrections append events;
history is never rewritten. Legal hold blocks deletion but not access minimisation.
Retention classes separate routine, financial, identity, fraud, safety/emergency,
uploaded metadata, AI interaction and immutable audit obligations. Exact periods require
Ethiopian legal/operational approval.

Future channel records remain reference-oriented: channel/session type, provider-neutral
reference, consent/purpose, participants, start/end/revocation, transcript provenance,
access audit and retention class. Media, screens and live-location samples are not copied
into the case database. Family/diaspora participation uses explicit role grants.

Knowledge articles are immutable versions with owner, citations, locale/jurisdiction,
effective/review/expiry dates and withdrawal state. Quality and satisfaction records
retain rubric/survey version and privacy-safe linkage. A future learning dataset requires
separate approval, dataset/source versions, human-review status, lawful purpose,
de-identification evidence and deletion/withdrawal lineage.
