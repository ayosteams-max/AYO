# Mission 26 — Testing, Certification and Rollout Strategy

Future implementation gates include:

- Unit/property tests proving debits equal credits, no mixed-currency balance, exact
  rounding, compensations and state transitions.
- PostgreSQL 17 integration for atomic posting, constraints, rollback, concurrent
  reservation/payout and idempotent retries.
- Migration upgrade/downgrade, backup/restore and projection rebuild.
- Provider contract/sandbox tests for signatures, replay, timeout, delayed/out-of-order
  callbacks, unknown outcomes, refund, payout and reconciliation.
- Authorization/ownership, step-up, maker-checker, negative tests and sensitive-log scan.
- Cash disputes, offline replay, duplicate trip completion, refund/chargeback collision,
  commission/incentive settlement and manual-adjustment tests.
- Load/soak benchmarks for posting, wallet reads, hot accounts, outbox/backpressure and
  reconciliation; thresholds require evidence before approval.

Rollout stages: ledger shadow from synthetic events; Finance-reviewed parallel books;
internal test accounts; provider sandbox; bounded pilot with daily reconciliation; then
measured expansion. Never import prototype balances automatically. Opening positions need
evidence, Finance dual approval and a separately audited journal.

Rollback stops new instructions/provider submission, preserves journals, drains or
quarantines inbox/outbox, reconciles in-flight operations and compensates only through
approved entries. A database restore cannot be used to erase already externally settled
events; reconciliation governs recovery.
