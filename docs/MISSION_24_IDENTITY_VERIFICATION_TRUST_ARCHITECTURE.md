# Mission 24 — Identity, Verification and Trust Architecture

Date: 2026-07-16
Status: **Architecture approved by CTO/CEO on 2026-07-16. No implementation or activation authorized.**

## Recommendation

Extend the existing provider-neutral PostgreSQL Identity foundation with a deterministic
Identity Assurance Orchestrator. It coordinates proofing cases and consumes verified
evidence from contact, document, vehicle, device, operations and approved external seams.
It does not merge those domains or let one weak signal establish identity.

Identity owns the digital subject, authenticators, sessions, assurance and recovery.
Driver Onboarding owns application progress; Document Verification owns evidence/results;
Vehicle owns vehicle identity; Driver Eligibility composes approved requirements; Safety/
Fraud owns investigations and restrictions; Airport policy owns Trusted Driver eligibility;
Business/Booking owns organization and participant grants; Support owns cases/appeals.
AI may classify/assist but cannot approve identity/documents, suspend, restrict or recover.

## Assurance model

Every purpose selects an approved assurance profile rather than a universal “verified”
badge. A decision records decision/case/subject IDs, purpose, policy/version, evidence
references/versions/freshness/integrity, assurance achieved, reason and missing-evidence
codes, expiry/reverification, prohibited actions, reviewer/authority and audit time.

Phone proves bounded control of a number, not legal identity. Email proves mailbox control,
not possession factor for high assurance. Device trust is contextual and revocable, not
identity. Documents and biometrics remain separate sensitive evidence. Trusted Driver and
Airport Trusted Driver are eligibility programs, never permanent identity status.

## Lifecycle

Rider: pending registration -> contact verified -> active basic account -> optional/
required step-up proofing -> restricted/recovery/deletion paths -> appeal/redress.

Driver: identity created -> contact verified -> onboarding -> identity/document/vehicle
checks -> operations review where required -> eligible for configured services -> periodic/
event-driven reverification -> suspension/expiry/recovery/appeal. Approval of identity,
vehicle and service eligibility are separate decisions.

## Authentication and devices

Preserve phone OTP, email verification, Argon2id password, passkey, recovery code, staff
MFA and service-credential seams. Access tokens remain short-lived; refresh rotation/reuse
revocation and PostgreSQL session authority remain. Multi-device sessions have independent
device/session IDs, assurance, trust/risk and revocation. New device, recovery, credential
change and sensitive action may require deterministic step-up. Raw invasive fingerprints,
advertising IDs and unbounded precise location are prohibited.

## Business, family and diaspora

Business accounts separate organization, verified administrators, members, billing roles
and passenger authority. Family/diaspora bookings use typed booker, passenger, payer and
authorized-representative grants with consent, expiry and action scope. Relationship or
payment does not grant account recovery, passenger identity or unrestricted trip access.

## Research basis

NIST SP 800-63-4 (2025) separates proofing, authentication and federation, adds risk,
privacy, customer experience, redress, continuous metrics and AI considerations. OWASP
requires generic failures, secure recovery no weaker than authentication, reauthentication
after risk events and session invalidation. These guide controls but are not Ethiopian law.

Sources accessed 2026-07-16:

- https://www.nist.gov/publications/nist-sp-800-63-4-digital-identity-guidelines
- https://pages.nist.gov/800-63-4/sp800-63.html
- https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- https://pdp.eca.et/pdp-proclamation

## Failure, scale and rollout

Provider outage creates pending/manual-review status, never approval. PostgreSQL/audit
failure denies protected transitions. Evidence conflicts fail closed and preserve redress.
Use bounded cases, optimistic versions, row locks, idempotency, transactional outbox and
append-only decisions. Partition by subject/case and archive only under approved retention.
External providers remain adapters; no provider, biometrics, Fayda, messaging or document
service is selected.

Rollout: deterministic contact/session foundations -> shadow proofing workflow -> staff-
assisted onboarding -> separately approved provider pilot -> measured expansion. Every
stage is disabled by default and independently reversible.
