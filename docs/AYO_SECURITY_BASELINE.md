# AYO Security Baseline

Status: mandatory engineering baseline. It does not replace Ethiopian legal review, provider requirements, threat modelling or independent security assessment.

This baseline implements the security obligations of `AYO_CONSTITUTION.md`. Where controls differ, the stronger lawful protection applies and the decision must be recorded.

## 1. Security principles

- Deny by default and grant least privilege.
- Authenticate the actor; authorize every object and action.
- Keep identity, precise location, payment and safety data to the minimum needed.
- Treat client input, device signals, webhooks and provider callbacks as untrusted.
- Make security-sensitive and financial commands atomic, idempotent and auditable.
- Do not trade security, privacy or legal compliance for delivery speed.
- Separate public product behavior from internal operational detail.
- Apply the Tiered Secure Computing principle in `AYO_COMPUTE_STRATEGY.md`; do not use confidential computing where Tier 1 or Tier 2 controls adequately address the threat.

## 2. Authentication

- Use a reviewed phone-OTP flow suitable for Ethiopia, with cryptographically secure challenges, short expiry, one-time use and attempt/send limits.
- Store OTPs only as protected verifiers; never log OTP values.
- Issue short-lived access tokens and rotating refresh sessions, or an equivalently reviewed session design.
- Require stronger authentication and MFA for staff, support, finance and administrators.
- Reauthentication is required for sensitive profile, payout and security changes.
- Account recovery must resist SIM swap and social-engineering attacks and create user-visible security events.

## 3. Permissions

- Derive rider, driver and staff identity from the authenticated session, never a body/path ID alone.
- Enforce resource-level authorization for every ride, wallet, document, incident and support case.
- Use explicit roles and fine-grained permissions; separate support, safety, driver-verification, finance and system-administration duties.
- High-risk administrative actions require reason capture; payouts, policy overrides and sensitive exports should use approval controls appropriate to risk.
- Test horizontal and vertical privilege escalation.

## 4. Secrets and configuration

- Keep credentials in a managed secret store; never commit them or place them in images, mobile apps, source, logs or tickets.
- Use separate credentials and provider accounts per environment.
- Rotate secrets and signing keys on a defined schedule and immediately after suspected exposure.
- Namespace settings with `AYO_`, validate at startup and use secure production defaults. Debug mode and public interactive docs are off in production.
- Restrict database and cloud credentials by workload identity and least privilege.

## 5. Encryption and key management

- TLS is required for all external and service-to-service traffic; validate provider certificates.
- Encrypt databases, object storage, queues, logs and backups at rest with managed keys.
- Add field-level protection or tokenization for especially sensitive identity, document and payment references when threat modelling requires it.
- Passwords, if introduced, use a current memory-hard password hashing scheme with unique salts.
- Keys are versioned, access-audited and recoverable under a tested rotation plan.
- Payment card data should be tokenized and kept out of AYO systems wherever a licensed provider can hold it.

## 6. Sessions and devices

- Maintain server-side session/device records with creation, last use, expiry, revocation and risk metadata.
- Rotate refresh credentials; detect replay and revoke the affected token family.
- Allow users to view and revoke active sessions.
- Apply idle and absolute lifetimes based on role and risk.
- Treat device identity, attestation and fingerprinting as risk signals, not infallible proof.
- Notify users of significant new-device, recovery, payout and credential events.

## 7. Rate limiting and abuse protection

- Apply layered limits by IP/network, account, device, endpoint and risk signal.
- Protect OTP send/verify, login, ride creation, offer decisions, location updates, support contact, payout and webhook endpoints separately.
- Use progressive delay, challenges or temporary controls without creating unsafe lockouts for legitimate users.
- Bound payload size, pagination, upload type/size and request duration.
- Monitor distributed abuse and retain review/appeal paths for consequential controls.

## 8. Audit logs

Record append-only, access-controlled security and business audit events for:

- Authentication, recovery, session and device changes.
- Permission, staff access and administrative actions.
- Driver verification decisions and document access.
- Ride creation, offers, state transitions and overrides.
- Pricing version, fare finalization and cancellation decisions.
- Every ledger, bonus, reconciliation, refund and payout movement.
- Safety incidents, SOS access and case actions.
- Provider webhook validation and processing outcome.

Events include UTC time, actor, action, target, result, reason, correlation ID and safe source context. Do not put secrets, OTPs, full identity documents, full payment credentials or unnecessary precise locations in logs. Protect logs from alteration and define retention/access policy with legal review.

## 9. Payment and ledger integrity

- Integrate payments through appropriately licensed providers and contractually supported APIs.
- Verify webhook signatures, timestamps and replay protections before processing.
- Store provider event IDs and enforce idempotency with unique constraints.
- Pricing, commission, bonuses, refunds and payout eligibility are server-authoritative.
- Represent money in defined currency minor units or a controlled decimal type; reject non-finite and unsupported values.
- Every movement creates balanced, immutable ledger postings in the same transaction as its business reference.
- Corrections use compensating entries. Never edit or delete posted financial history.
- Reconcile AYO records with providers and cash obligations; investigate mismatches before settlement.
- Separate payout initiation, approval where required, provider completion and ledger settlement states.
- Clearly represent the driver balance as an internal accounting ledger, subject to legally verified wording.

## 10. Location privacy and integrity

- Collect precise location only when necessary for availability, dispatch, active rides, safety or legally approved operations.
- Make collection state visible and stop it when the operational purpose ends.
- Restrict raw location access by purpose and role; audit sensitive access.
- Return only the precision and duration required by each client. Do not expose backup-driver locations or internal candidate queues.
- Define retention, aggregation, deletion and law-enforcement request procedures with Ethiopian legal review.
- Encrypt location in transit and at rest; keep it out of routine logs and analytics exports.
- Detect impossible travel, mock location, emulator/root risk, sensor inconsistency and route anomalies as signals. Avoid automatic punitive decisions based on a single signal.

## 11. Application, API and supply-chain controls

- Validate inputs and model explicit public response schemas.
- Use parameterized data access and safe output encoding.
- Apply CORS, trusted-host, proxy, security-header and error-disclosure policies by environment.
- Protect file uploads using type/size validation, malware scanning, isolated storage and signed short-lived access.
- Pin and lock dependencies; scan source, secrets, dependencies, containers and infrastructure definitions in CI.
- Require review and passing tests before production deployment. Produce an artifact inventory/SBOM when the delivery pipeline is established.
- Run independent penetration tests before public launch and after material identity, payment or safety changes.

## 12. Safety and privacy operations

- Safety tools use restricted roles, access reasons, audit trails and case-level controls.
- Emergency workflows must state what AYO can actually do; do not promise unverified emergency-service integration.
- Privacy notices and consent must be understandable, localized where required and consistent with actual collection.
- Support access is masked/minimized; production data must not be copied casually into development.
- Define user data access, correction, retention and deletion processes after legal validation.

## 13. Incident response

Maintain an owned, tested response process covering:

1. Detection and severity classification.
2. Immediate user-safety protection and evidence preservation.
3. Containment, credential/key revocation and isolation.
4. Investigation using tamper-resistant logs and a documented timeline.
5. Recovery, reconciliation and heightened monitoring.
6. Leadership, provider, insurer, regulator and user notification according to verified obligations.
7. Post-incident review with tracked corrective actions and no-blame learning.

Keep current escalation contacts, provider emergency contacts, decision authority, secure communication channels and offline copies of essential runbooks. Exercise account takeover, payment compromise, location exposure, malicious staff access and regional outage scenarios.

## 14. Release gates

No public production release may proceed until:

- Threat models cover identity, ride lifecycle, dispatch, payments/ledger, location and safety.
- Authentication and resource authorization tests pass.
- No known critical/high vulnerability lacks explicit risk acceptance by authorized leadership.
- Financial invariants, idempotency, concurrency and reconciliation tests pass.
- Secrets, encryption, backups, restore and incident procedures are verified.
- Monitoring and on-call ownership are operational.
- Ethiopian legal/operational verification items in the decision log are resolved or formally accepted by authorized leadership.
# Authentication and session security baseline

- Rotate refresh tokens after every successful use and atomically invalidate the
  predecessor. Consumed-token reuse is treated as replay, audited and followed by
  token-family revocation.
- Store no raw access/refresh token, password, OTP, authorization header, private
  key or low-entropy contact hash. Validation and logs must not echo credentials.
- Protect against hijacking with short access lifetimes, durable server revocation,
  bounded idle/absolute expiry, rotation, replay detection, step-up and suspicious
  activity controls. Device trust never relies only on client assertions.
- Support multiple devices, one-device logout, logout-all, suspension/security
  reset revocation and controlled administrator revocation. Administrative action
  requires reason, authority, audit and later authorization enforcement.
- Use constant-shape customer failures where practical to prevent enumeration.
  Preserve useful internal safe categories in audit records without exposing
  account existence, lock state or verification details.
- Treat raw IP addresses, phone/email values and device identifiers as classified
  personal data. Generic authentication/audit metadata may use only approved,
  privacy-safe risk references with verified purpose and retention.
- Detect suspicious login using versioned, explainable signals such as new-device
  state, authentication strength, replay, bounded network-risk reference and recent
  recovery—not precise location histories or invasive fingerprinting.
- Require phishing-resistant authentication for staff/administrators and step-up
  for administration, finance, payout, recovery and security changes.
- Bound clock-skew tolerance and never allow skew to extend refresh-session absolute
  expiry. Server/database time is authoritative for security state.
- Production cryptographic keys, pepper/HMAC keys and provider credentials require
  approved managed key ownership, rotation, access and recovery design.
