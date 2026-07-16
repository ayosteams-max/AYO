# Mission 26 — Payment Orchestration and Provider Boundary

Provider-neutral contracts cover create/confirm/cancel payment, refund, payout, status
query, webhook verification and settlement report ingestion. Mobile money, bank and card
adapters normalize state but retain raw provider evidence in restricted storage.

Payment attempt lifecycle: `CREATED -> AUTHORIZATION_PENDING -> AUTHORIZED ->
CAPTURE_PENDING -> CAPTURED`, with `FAILED`, `CANCELLED`, `EXPIRED` and
`OUTCOME_UNKNOWN`. Refund and payout are independent lifecycles. Client callbacks never
confirm funds. Only authenticated provider evidence plus reconciliation policy advances
external status; Ledger posts the corresponding approved journal separately.

Every request uses an AYO idempotency key and provider correlation reference. Timeout
after submission becomes unknown, followed by status query/reconciliation; it must not
create a new financial request blindly. Adapter outage has bounded retries, circuit
breaking, backpressure and honest pending UX. No provider is selected by this mission.

Card integration should prefer provider-hosted/tokenized collection to minimize PCI
scope. AYO never stores CVV or PIN. Mobile-money and bank credentials remain with the
licensed provider. Webhooks require current provider-specific signature/key-rotation
rules and replay windows before any future implementation.
