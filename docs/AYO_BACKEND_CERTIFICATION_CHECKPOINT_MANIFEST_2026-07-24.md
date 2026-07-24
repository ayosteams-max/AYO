# Backend Certification Checkpoint Manifest

**Recorded:** 2026-07-24
**Base:** `85ddc15834d34cd664c728c0560b16964e950d8d`
**Scope:** PRE-PRODUCTION backend snapshot
**Status:** Approved by evidence for isolated reconstruction

## Decision

The machine-readable authority is
`quality/backend_checkpoint_manifest.json`. It admits the current Python backend,
backend tests, migration chain, backend quality configuration, evidence definitions
and the exact document list stated there. Each admitted category records its
purpose, owner, approval basis and dependency.

No dirty-workspace mobile file is admitted. Existing mobile material inherited
from the base commit is untouched and outside certification scope; exclusion is
not deletion. `BIBLE/`, `DESIGN/`, `DOCUMENTS/` and every document not named in
the explicit document list are likewise not copied from the accumulated
workspace.

## Document adjudication

The included set contains:

- active canonical authority: Constitution, architecture, blueprint, platform
  principles, roadmap, decision log, workflow and migration governance;
- approved Courier Pickup architecture, authorization, implementation and open
  verification records;
- approved Repository Quality Contract control/gate records and Q1/Q2 evidence;
- open Q3 evidence, PostgreSQL preflight and checkpoint adjudication records;
- the controlled migration `0016` exception and reconstruction evidence.

The contract proposal is excluded because the approved CTO gate and control
decision records now carry current authority. Other proposed, ambiguous,
duplicate/generated and local-scratch documents are excluded. Superseded history
is included only where an explicitly listed authorization or chronology record
is needed to explain the current state.

## Shared-file snapshot decision

The current approved snapshots of `BACKEND/main.py`, application and persistence
composition, persistence tables, shared tests, `pyproject.toml`, `uv.lock`, CI,
Decision Log, Engineering Workflow and Roadmap are indivisible. They contain
dependent changes from several approved increments. Reconstructing line fragments
would manufacture chronology and can leave invalid intermediate states.

They are therefore assigned to the earliest coherent snapshot commit that needs
their complete current state:

1. backend runtime, dependencies and migration lineage;
2. backend tests and deterministic quality evidence;
3. CI, evidence definitions and checkpoint controls;
4. exact canonical governance document set.

Q3 audit-contract runtime corrections travel with the backend snapshot; Q3 tests
travel with the test snapshot. Commit messages describe reconstruction snapshots,
not original implementation dates.

## Exclusions and open gates

Caches, virtual environments, coverage output, test output, local evidence,
screenshots, device logs, secrets, `.env`, tool installations and ambiguous
documents are excluded. The approved deletion of `tests/test_ride_flow.py` is
preserved because that file exercised prohibited legacy unauthenticated routes.

The checkpoint must continue to state:

- Q3 is OPEN until whole-BACKEND branch coverage reaches 70.00%;
- PostgreSQL 17/PostGIS 3.6 certification is OPEN and is not executed here;
- Engineering Certification is OPEN;
- production activation is prohibited.

No material backend or document path remains in `review_required`. A commit may
still be withheld if isolated validation discovers a material contradiction.

## Blocker closure

The 2026-07-24 blocker review classified all three `generic-api-key` findings as
false positives:

- the committed scheduled-rides architecture line is API-design prose and contains
  no assigned credential value;
- both immediate-dispatch findings are deterministic, local idempotency fixtures
  with no external authority or secret value.

The exact file and safe line shapes are allowlisted in `.gitleaks.toml`. No rule,
directory or broad test/document class is excluded.

Scheduled ranking now separates mandatory deterministic correctness from timing
characterization. Correctness verifies eligibility filtering, governed tie
ordering and identical output for identical inputs independently of elapsed time.
The 10,000-candidate characterization records five samples, their median, the
unchanged 500 ms reference, available platform details and whether instrumentation
is detected. A single uncontrolled wall-clock sample no longer fails the functional
suite. The reference is not a production SLO; any future hard performance gate
requires a separately governed controlled job or reproducible statistical rule.
