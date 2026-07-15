# Mission 13 — Production Dispatch Persistence and Secure API Foundation

Status: CTO/CEO approved for implementation on 2026-07-16. Production deployment and activation are excluded.

## Problem, users and success

Mission 12 proved deterministic immediate-dispatch behavior but process memory cannot survive restarts, coordinate concurrent workers or provide durable audit evidence. Riders benefit from duplicate-safe recovery, drivers benefit from exclusive and consistent offers, and operations benefit from an inspectable state trail.

Success means one durable authoritative ride per accepted idempotent command, one active offer per ride and driver, atomic state/audit/outbox changes, authenticated ownership at every API boundary, bounded restart recovery, reversible schema deployment and passing concurrency/migration/security tests.

The simpler alternative—retaining process memory—cannot meet durability, concurrency or restart-recovery requirements. Separate microservices or a broker are unnecessary at this stage; PostgreSQL transactions and an outbox are the simplest reliable design.

## Approved design

- Extend the modular monolith and PostgreSQL 17 `ayo` schema; do not introduce SQLite, Redis, a broker or a new runtime dependency.
- Add mypy as a development-only static-analysis dependency because this mission explicitly requires reproducible type checks. It has no runtime access or production removal cost and can be removed with its lock entry if a repository-wide replacement is approved.
- Keep legacy prototype `ayo.rides` isolated. New authoritative tables use explicit `dispatch_` names so no unsafe legacy values are promoted.
- Persist ride requests, attempts, offers, assignments, idempotency records and outbox messages. Reuse the immutable shared `audit_events` table in the same transaction.
- Use row locks, optimistic ride versions, partial unique indexes and database constraints to prevent double assignment or overlapping active offers.
- Store place references/display snapshots, integer-minor-unit quote snapshots and versioned reason metadata. Do not persist protected characteristics or expose scoring internals publicly.
- Treat candidate discovery as a provider-neutral gateway. The PostgreSQL repository owns reservation/state consistency; future driver-location/map providers supply bounded candidate snapshots.
- Use authenticated `AuthorizationSubject` identity only. Rider and driver endpoints enforce explicit RBAC permissions and resource ownership; request bodies contain no rider or driver identity.
- Use a database-claimed, bounded recovery worker. Offer expiry, abandoned search closure and outbox delivery are retry-safe after process restart. External delivery remains unconfigured.

## Alternatives

1. Extend legacy `rides`: rejected because it contains floats, caller names and JSON dispatch queues that violate authoritative money and concurrency rules.
2. Event sourcing: rejected for current complexity and operational cost; immutable audit plus normalized current state and outbox provides sufficient traceability.
3. Database triggers for orchestration: rejected because domain behavior becomes harder to test and explain. Constraints protect invariants while services/repositories own transitions.
4. Immediate broker/microservice: rejected without measured throughput or team-boundary need. Transactional outbox preserves a later extraction path.

## Security, privacy and reliability assumptions

- A separately approved authentication layer resolves a trusted subject before these handlers. Headers/body role claims are never trusted.
- RBAC assignments are managed through the existing authorization foundation. This mission registers permissions but does not invent production role assignments.
- API responses expose ride state and minimal offer information only to the owning identity. Candidate lists, trust inputs, fairness values, reason details and other drivers are internal.
- Idempotency keys are accepted only through a bounded header and stored as SHA-256 fingerprints.
- Audit/outbox metadata is bounded and privacy-minimized. Exact live coordinates, credentials and sensitive fraud signals are excluded.
- Worker operations use server database time semantics and bounded batches. Concurrent workers may race safely; one wins the row lock/state transition.

## Schema and rollback strategy

The migration is additive and reversible before production activation. Downgrade drops only Mission 13 indexes/tables and seeded dispatch permissions in dependency order. It never touches legacy rides, identities or shared audit history. Once real data exists, destructive downgrade is prohibited; use a reviewed forward migration/export plan instead.

No migration will be run against a production database, and no secret or external connection is configured in this mission.

## Risks and gates

- Driver availability/location persistence is owned by a future approved Drivers/Location milestone; this mission consumes a gateway and cannot independently prove map/ETA quality.
- Authentication token verification is not activated here; tests use trusted server subjects. Production resolver configuration and key management remain an activation gate.
- Outbox delivery to push/messaging providers is excluded. Undelivered messages remain durable for a later adapter.
- Search-abandonment duration and final rider-facing no-driver policy remain configurable technical defaults, not launch policy.
- Ethiopian privacy, retention and transport-operation review remains required before launch.

Stop before deployment, secrets, external providers, real data or public production activation.

## Implementation milestone report

### Files and components

The implementation adds `PostgresDispatchRepository`, `DispatchApplication`, `DispatchRecoveryWorker`, a non-registered secure dispatch router, Alembic revision `20260716_0008`, SQLAlchemy metadata, RBAC permission registry entries and unit/integration tests. The existing shared audit repository and unit-of-work kernel are reused.

### Database schema

- `dispatch_ride_requests`: authoritative rider/place/quote/state snapshots, optimistic version and search expiry.
- `dispatch_attempts`: ordered unique candidate attempts with ETA, policy and reason-code evidence.
- `dispatch_driver_offers`: exclusive active offers with server expiry and immutable score snapshot.
- `dispatch_assignments`: one assignment per ride/offer and one unreleased assignment per driver.
- `dispatch_idempotency_records`: rider-scoped key fingerprints, canonical request hashes and response ride links.
- `dispatch_outbox`: durable bounded events with availability, claim, publish and retry fields.
- `audit_events`: existing append-only shared table, written in the same transaction.

Partial unique indexes enforce one active ride per rider, one active offer per ride/driver and one unreleased assignment per driver. Foreign keys, state/lifetime/value checks and integer-minor-unit money protect database invariants.

### API endpoints

The non-activated router defines:

- `POST /dispatch/rides`
- `GET /dispatch/rides/active`
- `GET /dispatch/offers/{offer_id}`
- `POST /dispatch/offers/{offer_id}/accept`
- `POST /dispatch/offers/{offer_id}/decline`

Rider and driver IDs come only from a trusted `AuthorizationSubject`. Permissions are `dispatch.rider.request` and `dispatch.driver.offer.respond`. Offer ownership is checked after RBAC, and public models omit score, trust, fairness, candidate and other-driver details.

### Verification results

- Ruff lint and format: passed; 113 files formatted.
- Mypy changed-boundary check: passed, 4 source files.
- Full PostgreSQL 17/unit suite: 114 passed, 1 pre-existing expected failure; 87.62% coverage against 70%.
- Integration/migration subset: 47 passed, including upgrade parity, reversible downgrade, privileges, concurrency and recovery.
- Bandit: zero findings across 7,009 lines; two existing justified `nosec` labels.
- `pip-audit`: no known vulnerabilities.
- Deterministic scoring microbenchmark: 10,000 runs × 20 candidates in 1.351885 seconds; mean 0.135188 ms per bounded scoring run on this workstation. This is a local baseline, not a production SLO.

The only warnings are the existing Pydantic settings deprecation and restricted pytest cache path; neither affects test correctness.

### Rollback

Before activation and real data, downgrade from `20260716_0008` to `20260715_0007`. The downgrade removes seeded dispatch role grants/permissions, indexes and Mission 13 tables in dependency order. It does not alter identities, legacy rides or pre-existing audit infrastructure. The downgrade test passed on disposable PostgreSQL 17.

After any real dispatch data exists, do not run the destructive downgrade. Use a reviewed forward fix and explicit data-retention/export plan.

### Remaining risks and work

- The router and worker are not registered or scheduled; production activation is intentionally absent.
- Authentication token/key resolution and production role assignments are not configured.
- Driver/location/map candidate supply and outbox delivery adapters are not connected.
- Search-time and operating-policy defaults still require Ethiopian operational/privacy review.
- Production load, soak, backup/restore and operational monitoring remain launch-gate work.
