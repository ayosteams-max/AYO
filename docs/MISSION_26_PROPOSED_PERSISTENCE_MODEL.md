# Mission 26 — Proposed Persistence Model

Documentation only; no migration is authorized.

| Concept | Purpose/key invariants |
|---|---|
| `ledger_books`, `ledger_accounts` | versioned chart, single currency, immutable identity |
| `ledger_journals`, `ledger_entries` | append-only balanced posting and correction lineage |
| `financial_instructions` | authority, policy, business event and idempotency |
| `balance_snapshots` | rebuildable optimization, never authority |
| `wallet_projection_checkpoints` | role views with source journal watermark |
| `payment_attempts`, `provider_operations` | canonical/provider states and correlation |
| `provider_webhook_inbox` | verified raw reference, replay identity and processing state |
| `refunds`, `payouts`, `payout_reservations` | independent recoverable workflows |
| `cash_collection_claims` | participant claims and corroboration state |
| `reconciliation_runs`, `reconciliation_items` | source hashes, matches and exceptions |
| `manual_adjustment_requests` | maker/checker evidence and compensating instruction |
| `chargeback_cases` | provider deadlines/evidence and accounting links |
| `financial_audit_records`, `financial_outbox` | atomic audit/event delivery |

Database constraints must validate currency/minor units, positive entry magnitude,
debit/credit side, unique idempotency/business event, immutable posted records and journal
balance before commit. Posting plus audit/outbox is atomic. External calls never share a
database transaction. Restricted provider payloads and tokens are encrypted and retained
separately from routine projections.

Capacity uses bounded pagination, account/journal indexes, outbox leasing with
`SKIP LOCKED`, backpressure and measured time/book partitioning. Recovery requires PITR,
restore drills, journal-to-projection rebuild, provider re-reconciliation and documented
RPO/RTO approval. Do not claim scale before benchmarks.
