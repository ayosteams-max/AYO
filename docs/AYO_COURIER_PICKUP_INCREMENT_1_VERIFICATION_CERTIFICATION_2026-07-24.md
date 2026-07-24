# Courier Pickup Increment 1 Verification and Certification

**Recorded:** 2026-07-24
**Environment:** PRE-PRODUCTION ONLY
**Production:** NOT APPROVED
**Final status:** IMPLEMENTED — CERTIFICATION INCOMPLETE

## Gate decision

Courier Pickup Increment 1 is behaviorally implemented, but it is not certified.
Two mandatory gates remain open:

1. live PostgreSQL 17 migration, concurrency, immutability, privilege, restart and
   backup/restore certification did not execute; and
2. the authoritative repository-wide branch-coverage gate is 56%, below 70%.

Neither gate was lowered, excluded or reinterpreted.

## Evidence already established

- The complete non-PostgreSQL suite passes: 399 passed, 201 skipped and one expected
  xfail.
- Focused Dispatch and Courier Pickup regression tests pass: 16 passed.
- Pickup tests prove authorized travel and arrival, append-only false-arrival
  correction, stale location-reference rejection, wrong merchant-scope rejection,
  permission denial and the permanent Custody cutoff.
- Existing focused tests also cover admission, lifecycle, idempotency, assignment
  scoping, invalid transitions and migration-head discovery.
- Ruff, scoped MyPy, Bandit, dependency audit, scoped secret scan and
  `git diff --check` pass.
- No coordinates, continuous location history, customer contact data, payment data,
  recordings, transcripts, device fingerprints or unrestricted notes were added.
- Arrival location remains an optional opaque source reference subject to freshness
  validation. It is not the sole authority for arrival.

## PostgreSQL 17 gate

### Environment finding

`AYO_TEST_DATABASE_URL` is not configured. This host has no PostgreSQL server,
PostgreSQL client tools or Docker executable available. The repository can run the
certification against an externally supplied database, and CI declares a PostgreSQL
17 service, but repository tooling cannot provision that service in this workspace.

An approved disposable PostgreSQL 17 database, credentials and these client tools
are required:

- `pg_dump`
- `pg_restore`
- the clean-database provisioning tools required by the restore script

### Executable certification

After setting a disposable test URL, execute:

```powershell
$env:AYO_TEST_DATABASE_URL = "postgresql+psycopg://ayo_test:<test-password>@127.0.0.1:5432/ayo_test"
.venv\Scripts\python.exe -m pytest -m integration --no-cov -q
.venv\Scripts\python.exe -m pytest -m migration --no-cov -q
.venv\Scripts\python.exe database/certify_restore.py
.venv\Scripts\python.exe -m pytest -m audit --no-cov -q
.venv\Scripts\python.exe -m pytest -m persistence_kernel --no-cov -q
```

The gate remains open until evidence covers revision `20260724_0056`: single head,
upgrade, schema objects and grants, approved rollback and re-upgrade, assignment
integrity, concurrent transitions, database immutability, transaction rollback,
least privilege, restart recovery, backup and clean restore. In particular, the
current repository has migration coverage for Pickup but no complete live
Pickup-specific repository/concurrency certification suite; those tests must be
added or extended before certification can close.

## Coverage analysis

`pyproject.toml` is authoritative: pytest measures branch coverage over all
`BACKEND` and fails below 70%. It is not a changed-files or increment-only gate.
The complete run measured 56%.

Focused branch coverage measured with the approved Pickup tests:

| Component | Coverage |
|---|---:|
| `BACKEND/courier_pickup/models.py` | 100% |
| `BACKEND/courier_pickup/engine.py` | 93% |
| `BACKEND/courier_pickup/application.py` | 60% |
| `BACKEND/persistence/courier_pickup_repository.py` | 0% |

The repository module contributes 104 statements and 42 branches that cannot be
exercised by the in-memory tests and remained wholly uncovered without PostgreSQL.
Live PostgreSQL tests should materially improve Pickup coverage, but no evidence
supports claiming they will raise the whole backend from 56% to 70%.

The remaining application gaps include repository read/detail paths, merchant
acknowledgement success and correction paths, terminal outcomes, replay/version
conflicts and transactional failure paths. They are meaningful and should receive
behavioral tests. The global shortfall also includes unrelated historical backend
modules introduced without enough tests. This is repository-quality debt, not
authority to exclude those modules or weaken the gate.

Repository-wide MyPy is also not clean: it reports 291 existing errors across 34
test files. The changed Pickup/Dispatch scope passes MyPy. Unrelated typing debt was
not altered or waived during this mission.

## Dispatch fixture correction

`test_dispatch_api_worker.py` used a controlled `NOW` but called `create_ride`
without passing it. Its seven-day quote expired against wall-clock time on
2026-07-23. `DispatchApplication.create_ride` now accepts an optional clock value
and forwards it to the existing fail-closed domain validation. Production callers
retain the wall-clock default. The test passes its controlled clock.

The correction does not extend quote validity, accept expired quotes or introduce
test-only production behavior.

## Security and transaction evidence still required

Live PostgreSQL evidence remains required for:

- database rejection of unauthorized evidence, audit and history mutation;
- one active attempt per assignment under concurrent admission;
- accept/close/correct/reassign/Custody concurrency outcomes;
- aggregate, evidence, audit, event, outbox and idempotency atomicity under forced
  failure;
- runtime-role and merchant/courier/assignment scope enforcement;
- restart persistence, outbox recovery and idempotent retry; and
- restored triggers, constraints, indexes, grants and migration head.

## Gate recommendation

Keep Courier Pickup Increment 1 PRE-PRODUCTION and keep production prohibited.
Do not begin Increment 2. Supply an approved disposable PostgreSQL 17 environment,
complete the missing Pickup integration/concurrency evidence, and remediate the
repository-wide coverage debt without exclusions or threshold changes. Re-run every
gate before requesting certification.
