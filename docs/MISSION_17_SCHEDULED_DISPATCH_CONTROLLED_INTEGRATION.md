# Mission 17 — Scheduled dispatch production validation and controlled integration

Date: 2026-07-16
Status: **CTO and CEO implementation scope approved; implementation in progress; no activation or commit approved.**

## Problem, beneficiaries and success

Mission 16 established the scheduled-dispatch domain but its PostgreSQL paths were not
executed locally and it had no authenticated backend boundary. Riders, third-party
bookers, passengers, drivers and operations benefit when reservation ownership,
commitment concurrency and recovery are proven against the production database engine.

Success means all relevant PostgreSQL 17 tests execute without skips; public contracts
derive identity only from verified authentication; workers are bounded, lock-safe and
restart-safe; immediate dispatch is unchanged; privacy-safe audit/outbox evidence stays
transactionally consistent; and all repository quality gates pass.

## Approved approach and alternatives

Use the existing modular-monolith authentication middleware, RBAC, PostgreSQL unit of
work, audit/outbox, worker-health and advisory-lock patterns. Add a separately flagged
scheduled router and composition object. This is simpler and safer than a new service or
broker, preserves transactional authority and can later be extracted through existing
contracts.

Alternatives rejected for this mission:

- Process-memory integration cannot prove concurrency, restart or transactional safety.
- A new microservice adds network failure and operational cost without measured need.
- Provider-specific notifications, maps or flight APIs create lock-in and exceed approval.
- Reusing immediate-dispatch endpoints would blur different lifecycle and ownership rules.

No new Python dependency is required. PostgreSQL 17.10 runs locally with synthetic data.

## Boundary and design

- `SCHEDULED_DISPATCH_ENABLED` defaults false and is rejected in production.
- A trusted `AuthorizationSubject` supplies booker, passenger, driver or staff identity.
- Resource ownership is checked inside the transactional scheduled application, in
  addition to route-level RBAC.
- Sensitive changes require multi-factor or phishing-resistant assurance.
- Public projections omit scores, thresholds, contacts, audit metadata and driver data.
- Commands are strict, bounded and retry-safe. Stable public errors reveal no internals.
- Reservation/audit/outbox/idempotency changes share one PostgreSQL transaction.
- Workers claim bounded checkpoint batches using `FOR UPDATE SKIP LOCKED`; a PostgreSQL
  advisory lock prevents overlapping runs. Failed work remains reconstructible.
- Notifications use a provider-neutral contract and idempotent local test adapter only.

## Risk and edge-case register

| Risk | Control and verification | Residual status |
|---|---|---|
| Caller impersonates a role | Ignore identity fields; trusted subject plus RBAC and ownership tests | Controlled |
| Duplicate/weak-network request | Actor-scoped idempotency hashes and replay tests | Controlled |
| Concurrent planning/commitment | Optimistic versioning, row locks and PostgreSQL exclusion constraint | Validate on PG17 |
| Account takeover changes passenger/time | Step-up assurance and security audit reason | Controlled |
| Bulk unsolicited third-party bookings | Bounded provider-neutral rate-limit boundary and consent expiry | Controlled |
| Current passenger harmed | Hard pre-dispatch completion/confidence rules; no rush or penalty signals | Controlled |
| Worker overlap/restart | Advisory locks, transactional claims, bounded retries and sweeper recovery | Validate on PG17 |
| Sensitive log/contact leakage | Allow-listed structured fields and public projections; log tests | Controlled |
| Airport provider outage | Freshness expiry and deterministic rider-time fallback | Controlled |
| Local policy uncertainty | Thresholds remain configurable; Ethiopian operational/legal review gates activation | Open before activation |

## Authentication-change checklist

Mission 17 does not change token verification or session issuance. Existing device trust,
multi-device sessions, refresh replay, revocation, clock skew and authentication audit
remain Mission 14 authority. It adds step-up enforcement at the trusted-subject boundary
for sensitive reservation mutation and tests basic versus multi-factor assurance. No
caller-provided role, device or risk claim is trusted.

## Approval and exclusions

CTO and CEO approved Mission 17 implementation in the mission instruction dated
2026-07-16. Excluded: payments, AI ranking, automatic pricing, external providers,
production secrets/data, deployment, public activation and remote push. Stop after all
checks for CTO/CEO review before any local commit.

## Validation evidence

- PostgreSQL: workspace-local PostgreSQL 17.10 (`server_version_num=170010`) on localhost with synthetic `ayo_test`; no external service or real data.
- Database/migrations: the entire integration suite executed with zero skips, including empty upgrade, metadata parity, repeated upgrade, reversible downgrade, runtime privileges, advisory locking, atomic idempotency, concurrent reservation creation, driver-window exclusion, rollback, outbox/audit consistency and checkpoint recovery.
- Full suite: 184 passed, zero skipped, one pre-existing documented wallet xfail; 86.62% branch coverage against the 70% repository gate.
- Static/security: Ruff format and lint passed; strict Mission 17 mypy passed; Bandit reported no findings; pip-audit reported no known vulnerabilities.
- Performance: construction plus deterministic ranking of 10,000 candidates completed in 310.97 ms on the development machine, below the 500 ms characterization guard. This is not a production SLO.
- Privacy: synthetic opaque contacts only; public schemas omit internal scores and contact data; structured logs reject tokens, phones, exact locations and flight-booking fields.

## Remaining activation risks

The feature flag remains false by default and forbidden in production. Before any controlled staging activation, leadership still needs Ethiopian airport/legal/operations validation, a production secrets ceremony, reviewed notification/maps/flight adapters, operational dashboards and alert thresholds, support procedures and retention decisions. The local PostgreSQL runtime is test tooling only and is ignored by Git.

## Documentation-only CTO/CEO amendment

The approved amendment records the future Customer Recovery and Trust Engine and AI Customer Support Engine in `docs/AYO_FUTURE_TRUST_AND_AI_SUPPORT_ENGINES.md`, the support architecture, roadmap and decision log. Both are deferred and have no Mission 17 runtime, schema, route, dependency, provider, financial or activation effect. Mission 17 remains scheduled-dispatch validation and controlled integration only.
