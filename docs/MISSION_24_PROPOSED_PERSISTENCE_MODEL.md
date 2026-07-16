# Mission 24 — Proposed Persistence Model

Status: **No migration authorized.**

Preserve current identities, methods, challenges, devices, sessions, refresh families and
recovery/audit tables. Future additive domains may include proofing cases/events, evidence
references, trust decisions, driver onboarding requirements, document results, vehicle
verification results, eligibility snapshots, business organizations/memberships,
participant grants, appeals/reviews and transactional outbox/idempotency.

Sensitive binary evidence remains outside ordinary relational payloads behind encrypted
provider-neutral storage references. Rows carry optimistic version, policy/evidence
versions, effective/expiry times and retention class. Constraints prevent multiple active
conflicting decisions/grants. Corrections append; no history edits. Partition/index choices
follow measured access and retention, not speculative scale.
