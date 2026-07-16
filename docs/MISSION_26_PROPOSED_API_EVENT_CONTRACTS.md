# Mission 26 — Proposed API and Event Contracts

Documentation only; no route is authorized.

| Proposed operation | Authorized caller | Boundary |
|---|---|---|
| prepare/post ledger instruction | Pricing/Payments/Recovery service | validated balanced journal or rejection |
| get wallet projection | owning user/business or scoped staff | derived, role-redacted view |
| create/get payment attempt | booking/payment workflow | provider-neutral state; no ledger authority |
| request/get refund | Recovery/owning user query | authorization and attempt states separated |
| request/get payout | verified driver | reserved/pending/confirmed projection |
| submit cash claim | ride participant | claim only, never proof |
| ingest provider webhook | verified adapter endpoint | append-only inbox acknowledgement |
| run/get reconciliation | Finance worker/role | exception set; no silent adjustment |
| propose/approve adjustment | separate Finance roles | compensating instruction only |
| retrieve journal/report | Finance/Audit scoped role | immutable, paginated, redacted |

All commands require authenticated context, RBAC/ownership, purpose, strict size/schema,
idempotency, expected version, server time and rate limits. Financial amounts use string
or integer-minor-unit wire types—never binary floating point. Events are transactional-
outbox records with event ID, aggregate/version, currency, policy/instruction reference
and privacy-safe audit correlation. Consumers deduplicate and tolerate out-of-order
delivery through aggregate versions.
