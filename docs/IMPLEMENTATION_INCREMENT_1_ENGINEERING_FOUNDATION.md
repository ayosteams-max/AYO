# Implementation Increment 1 — Engineering Foundation and PostgreSQL Certification

Date: 2026-07-16
Status: **Implementation approved by CTO/CEO on 2026-07-16 for local preservation.**

## Scope and compliance

This increment certifies the existing PostgreSQL 17, Alembic, health, audit,
idempotency, transaction, CI and local-development foundations. It adds repeatable
backup/restore certification only. It does not implement or activate authentication,
rides, dispatch, pricing, payments, wallet or other business logic. Mission 20 remains
disabled.

## Architecture finding

The repository already contains a bounded SQLAlchemy engine, explicit unit of work,
append-only audit contract, command idempotency constraints, schema readiness checker,
advisory-locked Alembic runner, linear reversible migrations and PostgreSQL 17 CI. Empty
upgrade, metadata parity, repeated upgrade, privilege, concurrent deployment, failure
recovery and bounded downgrade tests are existing approved foundations.

The identified gap was an automated backup/restore gate. `database/certify_restore.py`
uses standard PostgreSQL client tools, rejects system databases, creates a deterministic
disposable sibling, restores an archive, verifies `ayo_schema_version`, and cleans up.
CI now runs it after migration tests. No dependency or provider was added.

## Risks and rollback

The certification database account is intentionally privileged only in isolated CI/local
test infrastructure; production uses separate least-privilege migrator and runtime roles.
Logical restore does not replace infrastructure-level PITR, encrypted-backup or regional
disaster-recovery rehearsal. Rollback removes the CI step, tool, unit test and this
documentation; it changes no application schema or customer data.

## Verification evidence

- PostgreSQL `17.10` isolated local cluster accepted connections.
- Migration suite: 9 passed with no skips, including empty upgrade, metadata parity,
  runtime privileges, repeated upgrade, bounded/advisory-lock concurrency, failure
  recovery and reversible Dispatch/Scheduled/Active Ride boundaries.
- Full suite: 235 passed, 1 expected known legacy-wallet defect, 86.02% branch coverage.
- Backup/restore: custom dump restored to `ayo_test_restore_cert`, schema head
  `20260716_0014` verified, target removed.
- Restart: fast shutdown/checkpoint and clean startup completed; schema head remained
  `20260716_0014` and readiness accepted connections.
- Ruff formatting/lint passed; targeted strict mypy for the new tool passed.
- Bandit found no medium/high issues after documenting safe argv-only subprocess use.
- Dependency audit reported no known vulnerabilities.

Repository-wide mypy is not a configured CI gate and currently reports 34 pre-existing
typing errors across legacy/business modules after resolving its duplicate-module
invocation ambiguity. This increment does not alter those business modules; the debt must
be addressed in a separately scoped quality increment before strict global typing can be
claimed.
