# AYO Database Migration Standard

## Repository Quality Contract

AYO-RQC-1 is the authoritative certification contract. Migration certification uses
the immutable PostgreSQL 17/PostGIS 3.6 image reference recorded in
`AYO_RQC_1_CONTROL_DECISIONS_2026-07-24.md` and must prove one head, empty and
approved-baseline upgrades, expected objects and grants, repeat upgrade, supported
rollback/re-upgrade, failure recovery, least privilege, backup/restore and restart
behavior. Required database-test skips are failures for certification.

Q1 aligns this standard but does not execute or claim PostgreSQL certification.

## Request Access & Interaction Provenance Increment 1

Revision `20260723_0051` adds the domain-neutral source-adapter registry, optimistic
channel-action capability declarations, hashed explicit continuity references and
append-only interaction provenance. It follows Service Area revision `20260723_0050`.

The revision is additive and does not alter Ride Request or historical business intent.
Database triggers prohibit update/delete of adapter versions, continuity evidence and
provenance records. Runtime rollback disables new Request Access command entry while
preserving evidence; destructive downgrade is prohibited. Production activation is not
approved.

## Mission 19 active ride revision

Revision `20260716_0013` adds the reversible Active Ride aggregate, append-only ordered
events, atomic command idempotency, role projection checkpoints, protected pickup
verification, evidence, confidence decisions, pickup recommendations and recovery
checkpoints. It registers five `active_ride.*` permissions. Runtime receives no
delete/truncate and no update on append-only events, evidence or confidence records.

Pre-activation rollback target: `20260716_0012`. Disable the feature and workers first;
do not downgrade after real usage without an approved reconciliation/export procedure.

## Scheduled integration revision

Revision `20260716_0012` adds only the hashed, expiring pickup-verification authority and scheduled RBAC permissions. It is additive and contains no personal test data. Mission 17 validated the full chain from an empty PostgreSQL 17.10 database, metadata parity, repeated upgrade and downgrade through `20260716_0010`.

Rollback before activation: stop scheduled workers, confirm no reservation is in pickup verification, back up synthetic/test data if needed, then run `alembic downgrade 20260716_0011` to remove Mission 17. To remove all scheduled persistence, continue to `alembic downgrade 20260716_0010`. The shared `btree_gist` extension is deliberately retained. Production rollback requires a separately reviewed data-preservation plan.

## Support foundation revision

Revision `20260715_0007` creates cases, append-only case events, separated messages and append-only AI interaction evidence plus scoped queue permissions. Runtime updates case state under optimistic concurrency, but cannot delete cases or mutate append-only evidence. Forward-fix, role separation, readiness locking and no-startup-migration rules remain unchanged.

## Decision and tool comparison

AYO uses Alembic for reviewed, versioned PostgreSQL migrations. It fits the
existing SQLAlchemy Core metadata and Python toolchain with the least additional
operational surface. Autogeneration may propose a change, but no generated change
is trusted until an engineer reviews its SQL, locking impact and recovery plan.

| Option | Core compatibility | Locking and rollback | Operations and scale |
|---|---|---|---|
| Alembic | Native SQLAlchemy metadata comparison | PostgreSQL transactional DDL; AYO adds advisory locking | One Python toolchain; explicit, auditable revisions |
| Flyway | SQL-first; duplicates Core metadata | Mature PostgreSQL locking; transaction behavior is configurable | Strong multi-language estate support, but adds Java/tool and licensing surface |
| Sqitch | SQL-first with dependency plans | Explicit deploy/revert/verify scripts | Auditable but more bespoke Python/metadata integration |
| Atlas | Declarative schema planning | Plans must still be reviewed for destructive changes | Capable, but adds another schema source and tool lifecycle |

Flyway's built-in locking is attractive, but not enough to justify an additional
platform for the current modular monolith. Alembic plus a small PostgreSQL-native
lock is the simplest reliable solution. A different tool should be reconsidered
only with measured multi-language or independent-schema release needs.

## Schema and execution model

- Business tables live in the dedicated `ayo` schema. The initial revision creates
  `ayo.rides` and the explicitly non-authoritative `ayo.legacy_wallets` prototype.
- `public.ayo_schema_version` records the migration head. It is controlled by the
  migration role and is not application business data.
- PostgreSQL 17 supplies `gen_random_uuid()` as a built-in function, so the initial
  migration installs no extension. PostGIS is deliberately outside Mission 4.
- Revisions form one linear history. Once used in a shared environment, a revision
  is immutable; corrections are new forward revisions.
- Migrations run only in an approved deployment job with `uv run --group migration
  python database/migrate.py`. They never run during API or worker startup.
- The runner takes a stable session advisory lock with a bounded wait. Concurrent
  deployments serialize; timeout fails the deployment before application cutover.
- The internal readiness checker compares the database revision and required
  objects with the reviewed head. It is not exposed through a public API.

## Database roles and permissions

Role provisioning is environment infrastructure and is not performed by Alembic.
Every environment uses distinct credentials stored in the approved secrets system.

- `ayo_migrator`: deployment-only login; owns the `ayo` schema and version table;
  may create, alter and drop AYO objects; has no superuser, role creation, database
  creation, replication or bypass-RLS privileges.
- `ayo_runtime`: application login; owns no schema or table; receives only `USAGE`
  on `ayo` and approved `SELECT`, `INSERT`, `UPDATE`, and `DELETE` grants. It has no
  `CREATE` on the database or schemas and cannot perform DDL.
- A separately approved read-only operations role may receive selected views later;
  direct broad table access is not assumed.

The migrator must set default privileges for runtime access to future approved
tables and sequences. Production connections require verified TLS. Migration
credentials are available only to the deployment job and are never supplied to
the API process. Privilege tests must be added when real environment roles are
provisioned; CI currently validates migration mechanics with an isolated owner.

## Rollback, failure and recovery

PostgreSQL transactional DDL rolls back a failed transactional revision, and the
runner releases its advisory lock in all outcomes. This does not make destructive
data changes safely reversible. AYO therefore uses these rules:

1. Prefer backward-compatible expand/migrate/contract releases and forward fixes.
2. Never promise an automatic downgrade for a destructive revision.
3. Before destructive DDL, document affected data, traffic locking, application
   compatibility, backup/PITR point, restore target, rehearsal result and approval.
4. On failure: stop deployment, preserve logs without sensitive values, verify the
   current revision and objects, diagnose, then apply a reviewed forward fix or
   restore the verified backup. Do not edit an applied revision.
5. Test backup restoration on a schedule and before high-risk changes. Recovery is
   incomplete until schema readiness and application/integration checks pass.

## Sensitive-data classification

| Data | Classification | Required controls | Retention and logging |
|---|---|---|---|
| Rider/driver names and identifiers | Restricted personal | TLS, encrypted storage, least privilege; field encryption where threat/legal review requires | Retention awaits Ethiopian legal approval; never log values |
| Pickup, destination and dispatch location context | Highly restricted location | Narrow service/operations access, audited access, encrypted transport/storage | Minimize precision and duration; never log raw locations |
| Payment method and fare/tip/bonus context | Restricted financial | Integrity controls, least privilege, auditable changes | Policy/legal retention; no payment credentials or full payloads in logs |
| `legacy_wallets.payload` | Critical but non-authoritative prototype | Isolate access; never use for settlement, payout or financial reporting | Do not migrate balances as trusted data; prohibit payload logging |
| Migration credentials and database secrets | Critical secret | Managed secrets, rotation, deployment-only access | Never store in Git, revisions, command output or logs |

Database encryption at rest and encrypted backups are infrastructure requirements.
Application-level encryption must be introduced only with an approved key lifecycle,
search/access design and recovery plan; ad hoc encryption would risk permanent data
loss. Retention values remain blocked on Ethiopian legal and operational review.

## Acceptance and operational checks

Mission 4 is accepted only when PostgreSQL 17 CI proves empty upgrade, metadata
parity, current revision readiness, idempotent repeated upgrade, bounded locking,
safe concurrent deployment, failure lock release and recovery. No skipped database
test counts as success. API route/behavior tests, Ruff, Bandit and pip-audit remain
mandatory. This mission does not cut over traffic, add authentication, configure
PostGIS, deploy infrastructure, or make the legacy wallet authoritative.

The next immutable revision, `20260715_0002`, adds `ayo.audit_events` and its
append-only runtime grants. It does not modify either applied revision, install an
extension, cut over application traffic, or change legacy wallet authority.

Revision `20260715_0003` adds durable `ayo.sessions` and
`ayo.rate_limit_buckets` storage with runtime DML but no deletion grants. It adds no
Redis service, authentication behavior, provider, extension or public route.

Revision `20260715_0004` adds bounded identity, method, credential, challenge,
device, refresh-family/history and recovery tables, and extends sessions with
privacy-safe device/assurance/family references. It adds no route, provider, token
key, automatic startup migration or traffic cutover.

Revision `20260715_0005` adds the policy-shaped PostgreSQL RBAC tables, reviewed
authorization-infrastructure permission registry, indexed active assignments and
least-privilege runtime grants. It adds no external policy engine or business role
matrix and does not attach authorization to the 12 compatibility routes.

Revision `20260715_0006` registers the authorization-ready, non-privileged
`support.*` permission set for future AI-first chat and voice support. It creates no
service identity, role, assignment, support workflow, AI model or provider.

## Backup and restore certification

`database/certify_restore.py` operates only on the disposable database named by
`AYO_TEST_DATABASE_URL`. It creates a sibling ending in `_restore_cert`, restores a
custom-format `pg_dump`, verifies the AYO schema-version row and removes the target in
all outcomes. It rejects PostgreSQL system databases and never drops the source.
PostgreSQL client executables must be on `PATH`; credentials stay in protected
environment configuration and must not be printed or committed.
# Mission 15 marketplace intelligence migration

Revision `20260716_0010` adds only advisory marketplace tables: immutable rule versions, replayable decision explanations and simulation results. It is additive, contains no customer data conversion and does not alter dispatch or pricing tables.

Revision `20260720_0028` adds one partial unique index over authentication method type and
keyed lookup reference. It first fails if duplicate normalized authentication lookups exist,
requiring reviewed identity reconciliation rather than automatic merging. Its downgrade is
prohibited because dropping canonical identity uniqueness would reintroduce duplicate-account
risk. Authentication remains disabled unless secure runtime dependencies are injected.

Revision `20260720_0029` adds append-only booking route evidence and confirmation records.
It preserves the provider evidence, Pricing-owned quote, and canonical ride-request binding
without starting dispatch. Its downgrade is prohibited because deleting immutable booking
evidence would violate the approved audit boundary.

Revision `20260720_0030` adds durable worker capability sessions, a database-enforced one-active-
earning-role invariant, and versioned Route Intelligence/decision reasons on canonical dispatch
candidate and offer evidence. It preserves prior records through explicit legacy evidence labels.
The revision is forward-only because deleting worker-session or dispatch-decision history would
remove operational and fairness audit evidence.

Upgrade in a disposable/approved environment:

```powershell
python database/migrate.py upgrade
```

Rollback before any future activation depends on retained advisory history:

```powershell
alembic downgrade 20260716_0009
```

The downgrade drops simulation, decision and rule tables in dependency order. Production application, deployment and real-data use remain unauthorized.
Revision `20260720_0031` adds immutable post-trip evidence packages, dual-party cash collection
confirmations, private one-shot ratings, reusable preference signals, immutable receipts and the
post-trip settlement/archive projection. Runtime receives no delete permission; history correction
remains append-only. It does not activate a provider or production settlement.

Revision `20260720_0032` adds the reusable Merchant Platform foundation: owner-bound merchant
profiles, branches, staged verification evidence, configurable partner programmes, bounded
enrolments, generic draft catalogue items, representative-assistance evidence, idempotency and a
minimized outbox. It contains no order, delivery, payment, inventory or live-commerce state and is
disabled unless explicit secure activation dependencies are supplied.

Revision `20260720_0033` adds hierarchical merchant categories, universal typed catalogue items,
provider-neutral media references, integer ETB base-price preparation, availability/visibility,
tags/keywords, optimistic lifecycle state, idempotency and minimized outbox evidence. The Phase 1
draft table is retained for audit/compatibility and receives no new Phase 2 writes. No customer
publication, order, basket, checkout, payment, delivery, inventory or promotion state is added.
## Increment 20 Phase 3 — Customer ordering

Revision `20260720_0034` adds append-only canonical commerce orders, order-line and immutable
evidence records, customer-scoped idempotency, and a safe transactional outbox. Runtime receives
`SELECT, INSERT` only; Phase 3 provides no update/delete path. The migration also registers
`ordering.create_own` and `ordering.read_own`. Production activation remains separately gated.
## Increment 20 Phase 4 — Merchant order management

Revision `20260721_0035` adds order versions, merchant/state indexing, immutable order timeline,
separate rejection evidence and merchant-action idempotency. Existing orders receive a version-one
creation event. Runtime receives narrowly scoped order state/version and idempotency-response update
rights; there is no deletion path. The migration registers `merchant_orders.read_own` and
`merchant_orders.decide_own`. Production activation remains separately prohibited.
## Increment 20 Phase 5 — Merchant preparation

Revision `20260721_0036` adds the current preparation projection, immutable preparation events,
merchant preparation idempotency and bounded indexes/constraints. It registers
`merchant_preparation.read_own` and `merchant_preparation.manage_own`. Runtime grants are restricted
to the required select/insert/projection update and idempotency response operations. Production
activation remains prohibited.

Revision `20260721_0037` adds the independent Courier Dispatch request projection, immutable dispatch
events, idempotency evidence, owner-scoped status permission and versioned policy evidence. It consumes
Merchant Ready evidence without allowing Merchant Preparation to assign a courier. Runtime remains
disabled and prohibited in production pending a separate activation approval.
Revision `20260721_0038` adds the independent Courier Pickup projection, arrival timestamps, waiting
duration, immutable events, idempotency evidence and owner/assigned-courier permissions. It does not
implement pickup verification, parcel custody or delivery and remains disabled in production.
Revision `20260721_0039` adds reusable custody records, hashed one-time pickup challenges, immutable
custody events, idempotency evidence and least-privilege merchant/courier permissions. Production use
remains prohibited.
Revision `20260721_0040` adds universal delivery credentials, lifecycle evidence, idempotency, reminder
evidence and provider-neutral notification intents. It introduces no settlement or production provider.
Revision `20260721_0041` adds the disabled-by-default Field Operations foundation: verified partner
operational profiles, configurable professional roles, hierarchical territories, time-bounded assignments,
assistance cases, append-only activity/audit evidence and idempotency. It stores only opaque photo/QR/evidence
references and grants no participant-account ownership, legal approval, financial, dispatch or AI authority.

Revision `20260721_0042` evolves assistance cases into the canonical owner-confirmed, independently
reviewed lifecycle. It adds optimistic state transitions, immutable case/review evidence, configurable
conduct evidence, duplicate-subject protection and bounded review/quality indexes. Existing Phase 1 cases
are mapped conservatively with migration evidence. No financial, incentive or production capability is added.
## Increment 21 Phase 3 — Field Representative Performance

Revision `20260721_0043` adds append-only performance evidence, readiness assertions, recommendation-only records, audit events and idempotency reservations. Runtime receives SELECT/INSERT only; no UPDATE or DELETE privilege is granted. Database checks preserve valid evidence ranges, time windows and the permanent `recommendation_only` authority boundary.

## Persistence kernel revision 0044

Revision `20260723_0044` adds the domain-neutral persistence backbone:
purpose-scoped command idempotency, immutable domain events and their transactional
outbox envelopes. Domain-event rows are append/read only for runtime. Outbox and
idempotency lifecycle rows permit bounded updates but not deletion or truncation.
The migration is intentionally forward-only after activation because destructive
downgrade would erase command, event or delivery history.

## 2026-07-23 PostgreSQL 17 certification

The complete linear chain to `20260721_0043` was certified on a fresh PostgreSQL 17.10
database. Empty upgrade, SQLAlchemy metadata parity, repeatability, advisory-lock
concurrency, simulated failure recovery and revision-bounded historical downgrade tests
passed. The migration suite contains 22 passing tests. A custom-format logical backup was
restored into a disposable sibling database and the exact head was verified before the
target was removed. A controlled fast database restart preserved version `17.10`, head
`20260721_0043` and application readiness.

Application startup does not run migrations. Use `python -m database.migrate` only as a
controlled deployment job with the separately configured migrator identity. Historical
reversibility tests stop at their target revisions and do not cross later forward-only
migrations; later corrections use reviewed forward migrations.

## Canonical Subject and Account compatibility revision 0045

Revision `20260723_0045` adds pre-production canonical Subject, Account and explicit
legacy-identity mapping persistence. It does not rename or delete `identities`, rewrite
historical references, create credentials/sessions, or activate authentication. Accounts
begin only as `pending_activation`. Runtime has no delete/truncate privilege; the
migration is forward-only because mappings and their audit/event lineage are historical
evidence. On 2026-07-23 PostgreSQL 17.10 certification passed: the 23-test migration suite
reached head 0045 with exact metadata parity and zero skips; a controlled server restart
preserved head, Subject, pending Account, mapping, audit, event and outbox evidence.

## R1 Passenger Mobility Ride Request revision 0049

Revision `20260723_0049` evolves the existing canonical Ride Request table in place.
Legacy Increment 4 rows remain model version 1; R1 Passenger Mobility rows use model
version 2 with canonical requester/passenger Subject references, validated location
references, optional stops, schedule intent, passenger count, and intent-only
preferences. The revision makes legacy-only columns nullable without deleting or
rewriting history and installs Subject foreign keys plus model-shape constraints.

The migration is forward-only because Ride Request, audit, event, outbox, and idempotency
history is immutable enterprise evidence. The PostgreSQL 17.10 migration certification
suite passed all 27 tests at head `20260723_0049`, including empty upgrade, metadata
parity, upgrade from revision 0048, repeatability, locking, and failure recovery.
# Courier Dispatch Increment 1 — revision `20260723_0055`

Additive PRE-PRODUCTION revision `20260723_0055` extends the existing Courier Dispatch
case with terminal states and actor/action idempotency, and adds independent offer,
assignment and immutable decision-evidence tables. It preserves Phase 6 data and
retains one linear migration head. Production migration execution is not approved.

# Courier Pickup Increment 1 — revision `20260724_0056`

Additive PRE-PRODUCTION revision `20260724_0056` evolves Courier Pickup from one record
per order/dispatch to immutable assignment-scoped attempts. It adds the approved
terminal state, policy/version, terminal reason, correlation/causation, immutable
evidence and action-scoped idempotency while retaining legacy rows. It does not add
tracking, routing, custody or delivery. Live PostgreSQL certification remains pending
a configured `AYO_TEST_DATABASE_URL`; production execution is not approved.
