# Mission 24 — Rider and Driver Identity Lifecycles

## Case states

`CREATED -> CONTACT_PENDING -> EVIDENCE_PENDING -> REVIEW_PENDING -> VERIFIED | MORE_
EVIDENCE_REQUIRED | HUMAN_REVIEW_REQUIRED -> ACTIVE/ELIGIBLE`, with typed `EXPIRED`,
`REVERIFICATION_REQUIRED`, `DENIED`, `APPEALED`, `SUPERSEDED` and `CLOSED` branches.

Only the owning deterministic orchestrator transitions cases. Reviewer decisions require
role, assurance, reason and expected version. Expiry never silently suspends unrelated
account capabilities; Eligibility/Safety applies approved consequences. Reverification
appends a new case and preserves prior evidence lineage.

Riders normally require minimum-friction contact/account assurance; higher-risk actions
select stronger purpose-specific proofing. Drivers require separate identity, driver-
licence, vehicle, insurance/registration and operational approvals. No single badge hides
which requirement, jurisdiction, vehicle, service or validity period was verified.
