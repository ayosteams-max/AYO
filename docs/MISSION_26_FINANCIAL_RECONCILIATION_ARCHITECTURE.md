# Mission 26 — Financial Reconciliation Architecture

Reconciliation independently compares: AYO payment attempts, provider transaction and
settlement reports, bank statements, ledger clearing accounts, cash claims and payout/
refund evidence. Each source retains provenance, retrieval time, statement period and
integrity hash.

Matches use stable provider references, amount, currency, direction and bounded time;
fuzzy matching may recommend candidates but cannot close an exception. Outcomes are
`MATCHED`, `MISSING_PROVIDER`, `MISSING_LEDGER`, `AMOUNT_MISMATCH`, `CURRENCY_MISMATCH`,
`DUPLICATE`, `TIMING_DIFFERENCE` or `REVIEW_REQUIRED`.

Exceptions have owner, severity, deadline, evidence, resolution and compensating-journal
reference. Re-runs are idempotent and do not erase prior findings. Daily operational
reconciliation and accounting-period controls are proposals whose frequencies/SLOs need
Finance/provider evidence. Material unresolved variances block payout/close according to
an approved, non-punitive policy.
