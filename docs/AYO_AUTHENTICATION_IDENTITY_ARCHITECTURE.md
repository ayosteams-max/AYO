# AYO Authentication and Identity Architecture

## Research conclusion

AYO uses a hybrid, provider-neutral authentication architecture. PostgreSQL is the
durable identity/session authority. Customer authentication may later combine phone
OTP, password and passkeys according to measured Ethiopian accessibility and fraud;
no delivery or identity provider is selected here. Staff and administrator
production access must use phishing-resistant WebAuthn/passkeys plus approved
recovery and step-up.

Phone OTP is accessible but delivery-dependent, phishable and exposed to SIM risk.
Passwords work on older devices but add credential-stuffing and recovery risk.
Passkeys resist phishing and avoid shared secrets, but Android passkey support begins
at Android 9 and cannot be the sole Ethiopian customer path. Managed identity lowers
some operations but adds provider/data/availability lock-in; fully self-managed
delivery and keys raise security operations. AYO therefore owns durable domain
identity and provider-neutral seams while deferring providers and key custody.

Short-lived signed access-claim contracts reduce database round trips and weak-
network overhead. Durable rotating refresh sessions provide revocation and replay
evidence. Claims never grant privilege by themselves: sensitive actions require
server-authoritative identity/status/session/assurance and later authorization.

## Taxonomy and data ownership

`identities` owns only internal/public UUID, identity type, status and version.
Authentication methods, credential verifiers, challenges, devices, refresh
families/history, sessions, recovery and audit are separate. Rider/driver profiles,
documents, vehicles, wallet and ledger remain outside identity.

Types are anonymous, rider, driver, staff, administrator, service, future merchant
and service provider. Anonymous activity normally has no persisted identity. Service
identities never use customer sessions. States are pending, active, suspended,
locked, disabled, recovery_pending and deletion_pending. Transitions are explicit;
suspension, lock, disablement and recovery initiation revoke applicable sessions.

Method contracts cover phone OTP, email verification, Argon2id password, passkey,
recovery code, staff MFA and service credential. Low-entropy phone/email lookup
requires a future keyed-hash design; ordinary SHA-256 is prohibited. No contact is
stored in Mission 7.

## Access and refresh lifecycle

- Access claims carry UUID token/session/identity references, issuer, audience, key
  ID, identity type, assurance and UTC times. Maximum lifetime is 15 minutes; actual
  policy may be shorter. Clock skew defaults to 30 seconds and is bounded at 120.
  No codec, signing key or production verifier is implemented.
- Refresh material must be high entropy; only 32-byte fingerprints are stored. A
  family belongs to one identity and device session.
- Refresh locks the family, records the consumed fingerprint, replaces it and
  increments family/session counters atomically.
- Reuse of consumed material is replay: family and session are revoked and an audit
  event commits in the same transaction. Concurrent refresh therefore produces one
  rotation followed by replay revocation. Clients must serialize refresh attempts.
- Unknown material is safely denied. Persistence failure cannot authenticate.
- Key-ID verification and overlapping key rotation are required later. Production
  generation, custody, emergency revocation and KMS/HSM need separate approval.

## Device trust and multi-device sessions

Sessions can reference identity/device UUID, privacy-safe fingerprint and IP-risk
references, device category, app version, OS family, method, assurance, risk state,
token family and rotation counter. Raw IP, invasive hardware fingerprint,
advertising ID and precise location are prohibited.

Trust states are unknown, recognized, trusted and restricted. Trust is a server
conclusion based on verified method strength, prior history and privacy-reviewed
risk—not a client device name. One-device logout revokes one session. Logout-all,
suspension, security reset, high-risk recovery and controlled admin action revoke
the applicable identity set. Admin action later requires authorization, step-up,
reason and audit.

Remember-me may extend only an approved refresh lifetime within an absolute bound.
It never lengthens access claims or bypasses idle expiry, replay, risk or step-up.

## Challenges, passwords and safe failures

Challenges store injected-key HMAC verifiers, never OTP plaintext. They are bounded,
expiring, attempt-limited and single-use under a row lock. No production HMAC key or
delivery provider exists. Resend policy remains approval-gated.

Passwords use Argon2id v19 with 64 MiB, three iterations and four lanes, store only
encoded verifiers and detect upgrade needs. Future policy requires a provider-neutral
compromised-password checker, long passphrases, no arbitrary periodic change, strict
rate limits and audited recovery.

Login/recovery/reset exposes the same safe failure shape whether an identity is
absent, locked, disabled or incorrect. Internal audit retains only safe categories.
Provider timing/delivery anti-enumeration must be tested after provider approval.

## Risk, step-up and recovery

Versioned deterministic signals may include new device, assurance shortfall, replay,
recent recovery, failure velocity and privacy-safe network risk. No precise location
history or invasive fingerprinting. A future rules/AI score requires approved inputs,
evaluation, fairness, drift and appeal; it cannot issue identity or privilege.

Step-up is mandatory for sensitive administration, finance, payout, account
recovery and security changes. Recovery handles lost/changed phone, SIM swap, stolen
device, forgotten password, lost passkey, driver re-verification and workforce loss
as distinct cases. High-risk recovery enters recovery_pending, revokes sessions and
is audited. Support cannot bypass controls; high-risk support action requires later
dual approval. Security questions are not approved.

## Rate limits and audit taxonomy

Mission 6 token buckets protect login, OTP request/verification, refresh, reset,
recovery, device enrollment, revocation and repeated suspicious failures. Keys are
privacy-safe and operation-scoped; security-critical storage never fails open.
Thresholds require measured fraud and UX evidence.

Audit actions cover challenge created; authentication success/failure/denial;
session created/refreshed/revoked/all revoked; refresh replay; account locked or
suspended; recovery started/completed/denied; method added/removed; staff MFA; and
step-up required/succeeded/failed. Events contain opaque IDs and safe categories,
never credentials, contacts, raw device/network data, bodies or auth headers.

## Low-resource, outage and Ethiopian requirements

Flows must use bounded payloads, minimal round trips and no repeated background
refresh or unsupported heavy client crypto. Passkeys need a fallback on unsupported
Android without weakening staff security. Provider outage needs an approved safe
fallback; PostgreSQL outage denies required state changes. Redis remains deferred.

Qualified Ethiopian review must determine contact/device/network lawful basis,
notice, retention/deletion, SIM-change access, recovery proof, children/vulnerable
users, cross-border providers and AYO Pay assurance. OTP coverage, latency, cost and
SIM-swap operations require measured pilots.
