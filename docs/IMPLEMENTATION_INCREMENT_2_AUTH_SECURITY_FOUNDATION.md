# Implementation Increment 2 — Authentication, Sessions, Authorization and Ownership

Date: 2026-07-16
Status: **Implementation approved by CTO/CEO on 2026-07-16 for local preservation.**

## Scope and architecture compliance

This increment certifies and completes the provider-neutral identity security foundation:
account lifecycle, Argon2id password verification, expiring challenges for password reset
and phone/email verification, short-lived asymmetric access-token verification, durable
sessions/devices, refresh rotation and replay revocation, RBAC, resource ownership,
rate limiting and security audit. It adds no external OTP/email/key provider and exposes
no new public authentication route until provider/key/operations approval.

No ride, dispatch, pricing, payment, wallet or business workflow is implemented. Mission
20 remains disabled.

## Implemented gap

The existing verified subject resolver was dispatch-path-specific and the generic
authorization enforcer had RBAC but no reusable ownership contract. The resolver now
works for any protected route. `ResourceOwnershipResolver` obtains the authoritative
owner from server-side state; ownership-required routes deny by default without a
resolver, reject a non-owner with a privacy-safe error, and write an immutable audit
event without exposing the actual owner. Permission and ownership remain separate checks.

## Existing certified controls

- Account states and server-validated transitions; restrictive states revoke sessions.
- Argon2id password hashing; compromised-password checker remains a provider boundary.
- Phone/email/reset challenges are expiring, single-use, attempt-limited and HMAC-protected.
- Access tokens reject symmetric/unknown keys, unsafe claims, roles/permissions in tokens,
  wrong issuer/audience, expiry and excessive clock skew.
- Refresh tokens are stored as fingerprints, rotate transactionally and revoke the token
  family/session on replay; concurrent reuse yields one rotation and one replay result.
- One-device and all-device revocation are distinct; sessions are durable and bounded.
- PostgreSQL token-bucket rate limits and RBAC assignments are deterministic and audited.
- Administration cannot bypass its own RBAC permissions.

## Deferred activation inputs

Production token signing/key management, OTP/email delivery, compromised-password data,
staff phishing-resistant authenticators, account-recovery staffing and Ethiopian identity/
retention rules require separate provider/legal/operations approval. The foundation
fails closed without them rather than supplying development secrets.

## Verification evidence

- Authentication/authorization/session PostgreSQL markers: 16 passed, no skips.
- Identity, asymmetric-token, session/rate-limit and RBAC contracts: 25 passed.
- Ownership-focused authorization suite: 11 passed, including owner, non-owner,
  missing-resolver, permission and immutable-audit behavior.
- Full repository suite on PostgreSQL 17.10: 237 passed, one expected legacy-wallet
  `xfail`, 86.05% branch coverage against the 70% repository threshold.
- Ruff formatting and lint passed. Strict targeted mypy passed for both modified runtime
  modules; global pre-existing typing debt remains recorded under Increment 1.
- Bandit reported no medium/high issue; dependency audit found no known vulnerability.
- `git diff --check` passed and `ARRIVAL_WAITING_ENABLED` remains `False`.
