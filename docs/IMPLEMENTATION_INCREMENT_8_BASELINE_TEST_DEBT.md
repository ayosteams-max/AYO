# Implementation Increment 8 Baseline Test Debt Inventory

Status: controlled technical-debt record for Increment 8 preservation.
Date: 2026-07-17
Scope: repository baseline test debt observed during Increment 8 certification.

## 1. Baseline summary

- Full repository run without PostgreSQL test URL: 207 passed, 105 skipped, 1 xfailed, coverage gate failed.
- Full repository run with PostgreSQL test URL: 312 passed, 0 skipped, 1 xfailed, coverage 85.99% (threshold 70%).

This inventory records the 105 skips as baseline debt and does not authorize skip acceptance for PostgreSQL-required certification gates.

## 2. Skip inventory (105 total)

All 105 skips share the explicit reason:
`AYO_TEST_DATABASE_URL is required for PostgreSQL integration tests`.

### Category A: Environment-gated (105)

- Classification: environment-gated.
- Reason: disposable PostgreSQL integration database URL was not provided to the default local run.
- Marker families affected: integration, migration, audit, authentication, authorization, support, session persistence.
- Representative files:
  - tests/integration/test_ledger_foundation.py
  - tests/integration/test_migrations.py
  - tests/integration/test_pricing_foundation.py
  - tests/integration/test_authorization_foundation.py
  - tests/integration/test_authentication_foundation.py
  - tests/integration/test_support_foundation.py

### Category B: Platform-gated (0)

- Classification: none currently recorded for this baseline.

### Category C: Intentionally deferred (0 skips)

- Classification: not applicable for skipped tests in this baseline.

### Category D: Obsolete (0)

- Classification: none identified.

## 3. Existing xfail inventory

- tests/test_services.py::test_cash_commission_is_not_lost_on_repeated_wallet_refresh
- Current status: expected failure retained as known prototype defect.
- Classification: intentionally deferred defect outside Increment 8 runtime scope.

## 4. Recommendation and cleanup gate

Recommendation:
- Keep default local developer runs allowed to skip PostgreSQL integration tests when no disposable database is configured.
- Treat any CTO/CEO certification, release, or preservation gate as requiring PostgreSQL-enabled execution with zero unexpected skips in the targeted suites.

Future cleanup gate:
- Introduce a dedicated CI lane and local helper command that always sets a disposable PostgreSQL URL and runs all integration/migration markers.
- Reclassify skip inventory only when:
  1. environment bootstrap is fully automated for local and CI;
  2. integration suites run with zero unexpected skips under that bootstrap;
  3. marker-level policy is documented in repository testing standards.
