# Mission 14 — Secure Authentication, Internal Dispatch Activation and Outbox Delivery

Status: CTO/CEO approved for implementation on 2026-07-16. Commit and push require a separate post-check approval.

## Problem and success criteria

Mission 13 deliberately left dispatch unregistered. Controlled development/staging use now needs a fail-closed authentication boundary, explicit activation controls, abuse limits, reliable local outbox processing and non-overlapping recovery execution without connecting any production identity or messaging provider.

Success means forged/expired/malformed/wrong-issuer/wrong-audience tokens fail safely; trusted subjects contain only verified identity claims; database RBAC remains authoritative; dispatch stays disabled by default; local activation is environment-gated and size/rate limited; outbox delivery is idempotent and retry safe; worker health is observable; and an authenticated rider-to-driver assignment passes end to end without leaking internal dispatch data.

## Evidence and standards

RFC 7519 defines `iss`, `aud`, `exp`, `nbf` and `jti`. RFC 8725 requires explicit algorithm verification and audience/issuer validation and warns against algorithm confusion. PyJWT exposes fixed-algorithm asymmetric verification and standard claim validation. AYO will not discover a key URL from an unverified token; a configured provider-neutral key source resolves only an allowlisted `kid` and algorithm.

## Authentication design

- Add a `TokenVerifier` protocol returning a typed verified identity result.
- Implement asymmetric JWT verification with PyJWT's cryptography support. Only configured asymmetric algorithms are accepted; symmetric `HS*` and `none` are prohibited.
- Require signature, `iss`, `aud`, `exp`, `nbf`, `iat`, `sub`, `sid`, `jti`, identity type and assurance level. Enforce a 15-minute maximum lifetime and bounded clock skew.
- Reject token role/permission/scope claims. Authorization remains database RBAC, never token-authoritative.
- Resolve `kid` through a configured rotating key provider. Unknown keys, stale providers and verification errors fail closed. Multiple concurrently valid keys support rotation.
- After cryptographic verification, load identity and session from PostgreSQL and require active, matching records before constructing `AuthorizationSubject`.
- Never log bearer tokens, key material or claim payloads. Security logs use safe outcome/reason codes and correlation IDs only.

PyJWT with the `crypto` extra is a new runtime dependency. It is preferred to handwritten JWS parsing because algorithm/claim validation is security-critical, widely standardized and removable behind `TokenVerifier`. Alternatives considered: direct `cryptography` implementation (too error-prone) and external identity SDKs (provider lock-in before provider selection).

## Activation and API controls

- `dispatch_enabled` defaults false.
- Activation is allowed only in `development`, `test` or `staging`; production configuration fails startup unless a future separately approved production gate changes the policy.
- Application construction requires explicit composition, verifier and worker dependencies when enabled. Missing dependencies fail startup.
- Bearer authentication middleware precedes existing deny-by-default RBAC. Rider/driver IDs and permissions cannot come from request data or token role claims.
- A bounded request-size middleware rejects oversized bodies before parsing.
- Existing PostgreSQL token buckets remain the authoritative rate-limit boundary. Keys are one-way hashes of authenticated identity plus operation; storage failure fails closed.
- Public errors use stable calm codes and never expose database, scoring or token-validation detail.

## Outbox delivery

- Add `OutboxPublisher` and immutable `OutboxMessage` contracts.
- PostgreSQL claims bounded ready rows with `FOR UPDATE SKIP LOCKED`, a worker identity and stale-claim recovery.
- Publishing occurs outside the claim transaction. The immutable message UUID is the provider idempotency key.
- Success marks the row published only for the claiming worker. Failure records a safe error category, clears the claim and schedules exponential backoff.
- Default policy: maximum 5 attempts, 5-second base, doubling to a 5-minute cap. Exhausted messages are dead-lettered, retained and observable.
- The controlled local/test publisher deduplicates message UUIDs and performs no network operation.
- Approved event types are ride requested, driver offer created/expired/declined, driver assigned and no driver available. Existing internal names are normalized to this versioned set without exposing score data.

## Recovery scheduling and locking

- Add a scheduler-neutral coordinator with a PostgreSQL transaction advisory lock. If another worker holds the lock, the run is skipped rather than overlapped.
- The lock spans the bounded recovery run. Existing row locks and idempotent transitions remain the second line of concurrency protection.
- Health records last start/success, last safe failure category, consecutive failures, running/skipped state and outbox lag. Readiness is internal and reports unhealthy on stale success or excessive lag.
- No background thread starts merely by importing the app. A controlled process/scheduler must call `run_once` explicitly.

## Observability and privacy

Structured logs contain event name, outcome, correlation ID and opaque ride/event IDs where required. They exclude tokens, exact locations, display addresses, key material and personal attributes.

A provider-neutral metrics sink records ride creation outcomes, idempotency conflicts, offer acceptance/decline/expiry, reassignment, no-driver, worker lag, outbox retry/dead-letter and authentication/authorization failures. The included in-memory sink is test/local only; no external telemetry provider is connected.

## Migration and rollback

Mission 14's additive reversible migration adds dead-letter timing to the outbox and seeds no production secrets or identities. Before real data, downgrade removes only the new column/index and Mission 14-specific permission if added. Feature rollback is immediate: disable dispatch, stop scheduler invocation and retain durable rows for investigation.

No deployment, external identity/JWKS fetch, messaging provider, production secret, real identity or irreversible migration is authorized.

## Risks and remaining gates

- Bearer tokens remain replayable until expiry; future proof-of-possession requires separate evidence and approval.
- Key freshness depends on the eventual key-provider adapter. This mission tests rotation with configured local public keys only.
- Database-backed rate limiting favors correctness over availability; database failure intentionally denies protected operations.
- Local publisher verification does not prove provider latency or webhook behavior.
- Production roles, issuer/audience, keys, retention, alert thresholds and staging infrastructure require separate secure configuration and approval.

## Implementation result and approval gate

Implemented on 2026-07-16 and intentionally left uncommitted. Dispatch defaults disabled and production activation raises a configuration error. Controlled activation exposes rider ride creation/status, driver offer lookup/response, and service/admin worker routes using the existing sanitized contracts. Internal recovery and outbox execution require `dispatch.worker.recover`; health/readiness requires `dispatch.admin.health.read`.

Migration `20260716_0009` adds nullable `dead_lettered_at`, replaces the pending-outbox partial index so dead letters are excluded, and seeds the health-read permission. Its downgrade deletes that permission grant/code, restores the prior index and drops the nullable column. Operational rollback is to disable `DISPATCH_ENABLED`, stop scheduler calls, retain rows for diagnosis, and downgrade only before any future incompatible consumer relies on the new permission or column.

Verification passed: Ruff formatting and lint, strict mypy across all Mission 14 security/activation paths, 138 tests with PostgreSQL integration and migration upgrade/downgrade parity, authenticated rider-to-driver end to end, concurrent worker and idempotency coverage, Bandit with zero findings, pip-audit with no known vulnerabilities, and 87.65% branch coverage. One pre-existing wallet characterization remains an expected xfail and is outside this mission.

No deployment, provider connection, production key, real identity, public activation, commit or push occurred. Production readiness still requires an approved identity/key adapter, secure secret delivery, external-publisher adapter and provider tests, durable telemetry/alerting, load and abuse testing, backup/restore evidence, retention/legal review, staging rollout evidence and a separate production authorization.
