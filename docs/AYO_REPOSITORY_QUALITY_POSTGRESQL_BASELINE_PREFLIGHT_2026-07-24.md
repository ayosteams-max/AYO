# PostgreSQL 17/PostGIS 3.6 Baseline Execution Preflight

Date: 2026-07-24
Environment: PRE-PRODUCTION ONLY
Mission status: **AUTHORIZED BUT NOT EXECUTED — EXECUTION-INTEGRITY BLOCKED**
PostgreSQL baseline gate: **OPEN**
Q3 coverage gate: **OPEN — 60.70%**

## Executive summary

The bounded PostgreSQL baseline mission was admitted, but database provisioning
and test execution did not begin. Two mandatory execution-integrity prerequisites
are absent:

1. no reviewed clean commit or isolated clean worktree contains the code that the
   mission is intended to test; and
2. the workstation has no Docker, Podman or nerdctl runtime and no configured
   disposable PostgreSQL connection.

Running the approved CI service against the current committed `HEAD` would test an
older repository state that does not contain Courier Pickup Increment 1 or
migration `20260724_0056`. Running tests against the current dirty worktree would
not produce commit-bound evidence. Neither substitution is permitted by
AYO-RQC-1 or this mission.

No database was started, no credentials were created, no migrations were applied,
no PostgreSQL-dependent test was executed and no coverage result was regenerated.
Production remains prohibited.

## Commit and worktree evidence

| Evidence | Observed value |
| --- | --- |
| Branch | `main` |
| Committed `HEAD` | `85ddc15834d34cd664c728c0560b16964e950d8d` |
| Registered worktrees | One: `C:/Projects/AYO` |
| Tracked dirty entries | 80 |
| Untracked entries | 1,054 |
| `BACKEND/courier_pickup/application.py` in `HEAD` | No |
| `database/migrations/versions/20260724_0056_courier_pickup_increment1.py` in `HEAD` | No |
| Clean reviewed certification target | Not available |

The counts describe the preflight observation only. Existing user work was not
reset, cleaned, stashed, committed, moved or published.

## Approved image and execution environment

The authoritative repository CI configuration and quality commands agree on:

```text
postgis/postgis:17-3.6-alpine@sha256:88c78b602e7f2340ed46a090b78c96e9291d249517d50ea03a1cafb82d33ebe2
```

This is the approved immutable image-index digest. It was verified as repository
configuration, but the image was **not pulled or run**.

| Requirement | Preflight result |
| --- | --- |
| Docker | Not installed |
| Podman | Not installed |
| nerdctl | Not installed |
| WSL executable | Present; no approved OCI runtime established |
| `psql` | Not installed |
| `pg_isready` | Not installed |
| `AYO_TEST_DATABASE_URL` | Unset |
| Approved disposable database | Not available |
| Container identity | Not created |
| PostgreSQL version observed | Not observed |
| PostGIS version observed | Not observed |

The repository's approved CI workflow can provision the exact service image, but
commit-bound execution requires a reviewed commit containing the intended source.
The current workspace must not be published merely to trigger CI.

## Database, migration and test results

| Requested evidence | Result |
| --- | --- |
| Database startup and health | Not executed |
| Clean initialization | Not executed |
| PostgreSQL/PostGIS version query | Not executed |
| Migration application | Not executed |
| Schema, role and privilege checks | Not executed |
| Previous PostgreSQL-dependent skips | 201, from the accepted Q3 baseline |
| Database test pass/fail/error/skip result | Not generated |
| Full regression result | Not generated |
| Coverage before | 60.697674% accepted Q3 baseline |
| Coverage after | Not generated |
| Covered statement gain | Not measured |
| Covered branch gain | Not measured |

The previous 201 skips are not reclassified. Their environment condition has not
been satisfied, and no skip was removed or bypassed.

## Defect triage

### A — Environment or setup defect

- No approved local OCI runtime is available.
- No disposable database URL is configured.

These are infrastructure blockers. Installing or substituting a database image
was not attempted.

### Execution-integrity blocker

- The only worktree is not clean.
- Its committed `HEAD` omits material current increment source and migration files.

This is not an application defect. The smallest safe correction is to create a
reviewed commit containing only the intended repository state, then execute the
pinned CI workflow or create an isolated worktree from that commit. This report
does not authorize committing or publishing the existing mixed workspace.

No migration, schema, repository, Unit-of-Work, concurrency, test, application or
domain defect can be inferred because the database tests did not run.

## Certification boundary

The PostgreSQL baseline remains **OPEN / NOT EXECUTED**. The following are not
certified:

- PostgreSQL 17 or PostGIS 3.6 runtime compatibility;
- migration upgrade, rollback or re-upgrade;
- SQL constraints, triggers, indexes, grants or least privilege;
- real transaction atomicity or isolation;
- optimistic concurrency with database writers;
- immutable database evidence;
- tenant isolation at the database boundary;
- restart durability;
- backup and restore;
- disaster recovery, high availability, monitoring, load or production hardening.

Q3 remains **OPEN at 60.70%**, with the previously recorded exact gap of 2,440
covered elements. Engineering Certification remains open.

## Evidence artifacts and files changed

No certification manifest was created because there is no valid commit-bound
execution to identify. No generated output is represented as
`ENGINEERING_CERTIFICATION_EVIDENCE`.

This mission added this preflight report only.

No runtime source, schema, migration, API, test, CI or product file was changed.

## Required next bounded step

Prepare one reviewed clean commit that contains the intended Q3 and implemented
increment state without unrelated changes. From an isolated worktree at that exact
commit, trigger the existing pinned CI workflow (preferred on this workstation) or
use an approved local OCI runtime. Retain the run reference and generated manifest
against that commit.

No PostgreSQL, coverage, Q3 or Engineering Certification pass should be recorded
until that execution produces the required evidence.
