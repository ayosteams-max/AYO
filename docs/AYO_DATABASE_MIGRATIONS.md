# AYO Database Migration Standard

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
