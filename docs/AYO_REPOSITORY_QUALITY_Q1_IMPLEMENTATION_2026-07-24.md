# Repository Quality Initiative Q1 Implementation

**Date:** 2026-07-24
**Contract:** AYO-RQC-1
**Status:** IMPLEMENTED — PRE-PRODUCTION ALIGNMENT ONLY
**Production:** NOT APPROVED
**Q2–Q13:** NOT AUTHORIZED

## Outcome

Q1 aligned repository configuration, CI governance, engineering workflow,
validation commands, marker governance and certification-evidence structure to the
approved contract. It deliberately did not remediate known MyPy or coverage failures
and did not execute PostgreSQL certification.

## Implemented alignment

- `pyproject.toml` now makes `BACKEND` plus `tests` the canonical MyPy scope.
- Whole-`BACKEND` branch coverage and the exact 70.00% floor remain unchanged.
- CI uses the approved immutable PostgreSQL 17/PostGIS 3.6 image-index digest.
- CI uses Gitleaks `v8.30.1` and verifies the official Linux x64 archive checksum
  before execution.
- CI emits machine-readable test, coverage, Bandit, dependency and secret-scan
  reports and stages them by commit.
- The evidence schema binds a certification package to one commit, workflow,
  command/result set and review state.
- Engineering Governance owns the canonical marker registry.
- Repository branch policy records the two-reviewer, CODEOWNER/repository-owner and
  emergency-bypass controls without inventing GitHub account identifiers.
- Canonical local and CI validation commands use the same gate terminology.

## Boundaries

No runtime code, schema, migration, API, product capability or production
configuration was introduced. Q1 did not execute PostgreSQL, improve coverage or fix
tests-inclusive MyPy errors.

## Known red gates

Alignment makes the approved tests-inclusive MyPy scope enforceable; the previously
measured errors remain Q2 remediation work. Whole-backend branch coverage remains
below 70.00%. PostgreSQL certification remains unexecuted. Q1 does not claim any of
these gates pass.

## Remaining administration

An authorized repository administrator must record verified GitHub account/team
identifiers before a functional CODEOWNERS mapping can be created and must apply and
export host branch/ruleset settings. Temporary CI artifacts must be transferred to an
approved immutable store because ordinary CI retention is not the authoritative
`ENGINEERING_CERTIFICATION_EVIDENCE` retention mechanism.

## Stop

Q1 stops here. Q2, PostgreSQL certification, MyPy/coverage remediation, Custody,
Delivery, other product work and production remain prohibited.
