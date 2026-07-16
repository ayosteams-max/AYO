# Implementation Increment 3 — Driver Trust Foundation

Date: 2026-07-16
Status: **Implemented locally; awaiting CTO/CEO review. Not activated or committed.**

## Outcome and authority

This increment establishes PostgreSQL-authoritative driver onboarding, document-evidence
metadata, vehicle identity/approval separation, driver-to-vehicle authorization and a
versioned fail-closed eligibility projection. It solves the operational need to know
whether a specific driver and vehicle have current approved evidence without using a
generic verified flag.

Identity and Operations remain the human decision authorities. AI/OCR/provider outputs
may become evidence inputs only after separate approval and can never approve a driver,
document, vehicle, restriction or appeal. Eligibility uses deterministic approved inputs;
it does not use ratings, popularity, dispatch performance or AI scores. No ride, dispatch,
Airport product, Trusted Driver product or public activation is introduced.

## State and evidence design

`OnboardingState` implements the approved typed lifecycle from `DRAFT` through review,
approval, rejection, suspension, expiry, reverification and appeal. The transition table
rejects shortcuts. Optimistic versions prevent concurrent reviewers from silently
overwriting one another.

Document rows retain an immutable reference and privacy-safe document-reference hash,
type, issuer metadata, dates, policy version, human reviewer, reason codes and linked
replacement/supersession references. Ordinary relational payloads contain no image,
biometric or OCR content. Duplicate references are rejected per driver.

Vehicle approval and driver authorization are independent records. Capability and airport
input metadata are inert future inputs; they grant neither Airport Standard nor Airport
Premium eligibility.

## Eligibility and expiry

Each immutable eligibility decision records its ID, driver/vehicle, policy version,
status, reason codes, missing evidence, bounded expiry, recomputation time and audit
reference. Missing, expired, duplicate-current, contradictory or stale inputs fail closed.
Expiring evidence produces `REVERIFICATION_REQUIRED`; prior decisions are never rewritten.
Account restrictions are explicit inputs and cannot be hidden in a score.

## Security, privacy and recovery

- Ownership resolves from PostgreSQL; a role alone does not establish ownership.
- Reviewer identity comes only from the authenticated authorization subject.
- Sensitive evidence has a separate permission from privacy-minimised own metadata.
- Idempotency is PostgreSQL-backed and rejects key reuse with a changed request.
- Events and outbox rows are append-only evidence; transaction rollback is atomic.
- No external verification provider is configured; missing-provider behavior is fail closed.
- Rollback removes only Increment 3 schema and permissions after dependent data is handled.

## Constitutional review

The design is a bounded modular-monolith domain, uses indexed owner/current projections,
append-only decisions and provider-neutral references, and can later partition history by
time/driver without changing authority. It is the simplest implementation that preserves
human authority, auditability, concurrency safety and a credible horizontal scale path.

## Exclusions and unresolved launch gates

No rider proofing, biometrics, Fayda, OCR, external document provider, production document
storage, public driver activation, ride/dispatch/pricing/payment/wallet/incentive behavior,
Trusted Driver, Airport eligibility, deployment or Mission 20 activation is included.
Ethiopian document types, issuing-authority codes, expiry/inspection rules, reviewer
training, appeal SLA, retention, field verification and legal privacy requirements require
qualified local and leadership approval before production policy is seeded.
