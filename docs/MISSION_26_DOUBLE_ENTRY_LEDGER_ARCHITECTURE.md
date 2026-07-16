# Mission 26 — Immutable Double-Entry Ledger Architecture

## Model

A ledger book contains accounts; a journal groups two or more entries; every entry has
account, debit/credit side, integer minor-unit amount and currency. Journals reference
business event, instruction, actor/service, reason, idempotency key, effective/recorded
time and predecessor when compensating. Posted journals are immutable.

Account classes include assets, liabilities, revenue, expense and clearing/contra
accounts. The chart of accounts and accounting mappings are versioned and Finance-
approved. Operational wallet labels do not dictate accounting classification.

## Posting states and controls

`DRAFT_INSTRUCTION -> VALIDATED -> POSTED` or `REJECTED`. A posted journal may be
`COMPENSATED` only by a new balanced journal. Reservations/holds use explicit accounts or
approved encumbrance records; they never alter available balance without trace.

Database constraints enforce positive entry amounts, known currency, balanced journal,
unique business-event/idempotency identity and immutable posted rows. Posting, audit and
outbox are one transaction. Backdated effective time never changes recorded time or a
closed accounting period without Finance-approved adjustment policy.

## Wallet projections

Driver views separate cash held, commission obligation, digital earnings, pending,
reserved and payout availability. Rider views separate pending collection, refund and
approved credit status. Business views separate funding, authorization, spend and
invoice/reconciliation state. Projections rebuild from entries and checkpoint hashes;
they never become source of truth.
