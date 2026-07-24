# Repository Quality Initiative Q3 — Coverage Remediation Checkpoint

**Date:** 2026-07-24
**Environment:** PRE-PRODUCTION ONLY
**Status:** COVERAGE GATE OPEN — CTO AND FOUNDER REVIEW REQUIRED
**Production:** NOT APPROVED

## Scope and result

Q3 added meaningful tests for:

- fail-closed activation of every optional platform without secure dependencies;
- food-product availability authority, configuration concurrency and evidence;
- canonical order composition, catalogue staleness, modifiers, availability context
  and customer/public read boundaries; and
- merchant registration, delegated assistance, ownership, verification, catalogue,
  program, dashboard and cross-tenant authorization boundaries.

No runtime source, API, schema, migration, business rule, security architecture,
coverage setting or exclusion was changed.

| Measure | Initial | Current | Contract |
|---|---:|---:|---:|
| Whole-BACKEND combined branch coverage | 55.71% | 57.12% | 70.00% |
| Covered lines | 13,398 | 13,659 | — |
| Covered branches | 1,215 | 1,323 | — |
| Tests passing without PostgreSQL | 399 | 438 | — |
| PostgreSQL-dependent skips | 201 | 201 | 0 during certification |

The governed coverage gate remains open. Q3 must not be described as complete.

## High-value module improvements

| Module | Initial | Current |
|---|---:|---:|
| `BACKEND/eat_availability/application.py` | 0% | 95% |
| `BACKEND/ordering/application.py` | 15% | 99% |
| `BACKEND/merchant/application.py` | 15% | 97% |
| `BACKEND/main.py` | 64% | 74% |

## Defects and constraints discovered

1. `EatAvailabilityApplication.configure` emits audit metadata containing
   `merchant_id`, `policy_version` and `state`, but the canonical audit allowlist
   rejects at least the first two fields. A legitimate configuration command
   therefore fails at audit construction. Q3 records this runtime defect but does
   not alter production behaviour.
2. The local run skips 201 PostgreSQL-dependent tests because
   `AYO_TEST_DATABASE_URL` is unavailable. Persistence repositories account for a
   material portion of the uncovered BACKEND surface.
3. The scheduled-ranking characterization benchmark failed once under coverage
   instrumentation and passed on later identical runs. Its fixed 500 ms wall-clock
   assertion is nondeterministic under instrumentation and remains engineering
   debt.

## Validation

| Gate | Result |
|---|---|
| Whole-BACKEND coverage | **FAIL** — 57.12% is below 70.00% |
| Repository-wide MyPy | PASS — zero errors in 439 files |
| Ruff format | PASS after formatting new tests |
| Ruff lint | PASS |
| Bandit | PASS |
| Regression suite without coverage | PASS — 438 passed, 201 skipped, 1 known xfail |
| `git diff --check` | See final checkpoint validation |

## Recommendation and stop

Do not approve Q3 as complete and do not begin engineering certification.
Authorize a bounded continuation of Q3 that:

1. corrects the verified audit-allowlist incompatibility through the normal
   architecture/change gate;
2. adds unit-level persistence contract tests that do not pretend to replace live
   PostgreSQL evidence; and
3. continues risk-ranked application tests for Identity, Payments, Settlement,
   Request Access, Service Area and mobility.

Live PostgreSQL execution remains a separate authorized certification mission.
No PostgreSQL certification or successor product capability began here.
