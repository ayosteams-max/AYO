# Mission 12 — Immediate Dispatch Implementation

Status: reversible domain milestone complete; stopped before durable migration and security-sensitive production activation.

## Scope delivered

- Server-authoritative, immutable ride creation with UUID, authenticated rider context supplied by the service boundary, server time and integer-minor-unit quote snapshots.
- Atomic request idempotency with canonical request hashing, conflict detection and one-active-ride enforcement.
- Deterministic immediate dispatch with explicit hard eligibility filters, bounded fairness, stable tie-breaking and versioned reason codes.
- Neutral reputation for drivers below the configurable completed-trip threshold; no hidden new-driver penalty.
- Exclusive driver offers, server-time expiry, decline/timeout reassignment and prevention of repeated offers to an attempted driver.
- Retry-safe acceptance, active-ride recovery and bounded expired-offer recovery for delayed or duplicated Ethiopian-network requests.
- Privacy-minimized immutable audit events and repository contracts for future durable transactional storage.

Scheduled rides, pre-dispatch, payments, public API activation, production authentication wiring, executable database migrations, provider calls and AI ranking are explicitly excluded.

## Architecture and rollback

The implementation is an internal module behind typed contracts. `ImmediateDispatchService` contains orchestration, the scoring module is deterministic and side-effect free, and persistence is a repository port. The included in-memory adapter exists only for tests and local verification and is not production authority.

No schema, route, dependency or deployed state changed. Rollback is deletion of the isolated module and its tests; existing runtime behavior is unchanged. A future PostgreSQL/PostGIS implementation must atomically persist ride, idempotency, offer, driver reservation and audit/outbox records and must have its own reviewed forward/rollback migration plan.

## Verification

- Ruff format and lint: passed.
- Mission 12 tests: 13 passed.
- Full Pytest suite: 67 passed, 38 integration tests skipped without `AYO_TEST_DATABASE_URL`, 1 pre-existing expected failure; coverage 73.15% against the 70% gate.
- Bandit: no issues identified after replacing invariant assertions with explicit conflicts.
- `pip-audit`: no known vulnerabilities found.
- Repository whitespace validation: passed.

Tests cover idempotent retry/conflicting reuse, quote expiry, eligibility, neutral reputation, bounded fairness, reassignment, timeout, offer ownership, concurrent reservation, recovery and no-driver outcomes.

## Security and privacy review

- Rider identity is not accepted from the public command object.
- Money uses integer minor units; quote identity, version and expiry are required.
- Protected characteristics are absent from candidate and scoring contracts.
- Idempotency keys are fingerprinted before storage/audit; precise coordinates and sensitive risk signals are not written to audit metadata.
- Reservation and transitions are repository-atomic in the test adapter and expressed as atomic requirements in the production port.

This milestone does not claim production security because authentication, authorization, rate limiting, durable audit/outbox storage and operational key management are not yet wired.

## Remaining risks and technical debt

- The old prototype dispatch path coexists and remains the only registered runtime path.
- The new core is process-local until a durable transactional adapter and worker are approved.
- Cross-process concurrency, crash recovery, outbox replay and database isolation require integration tests against PostgreSQL.
- ETA values enter through trusted candidate inputs; staged provider routing and freshness guarantees remain unimplemented.
- Policy values are configurable defaults, not launch-approved Ethiopian operating policy.
- Local integration tests cannot run without the project test database URL.

## Approval gate

The next critical step is a reviewed PostgreSQL schema/migration, transactional repository/outbox adapter, authenticated API boundary and background expiry worker. That step changes durable and security-sensitive production boundaries, so work stops here for CTO/CEO approval before it begins.
