# Mission 25 — Cash and Payment Reconciliation Boundary

Fare calculation, payment authorization, collection, settlement, cash confirmation,
reconciliation, refund instruction and ledger posting are separate state machines.
Pricing produces an amount and settlement instruction proposal; it never contacts a
provider or marks value paid.

Cash records claims and corroborating evidence from authorized parties. A driver button
alone is not unquestioned settlement proof; mismatches become reconciliation cases with
role-safe evidence and no silent balance mutation. Future Telebirr/mobile money,
bank/card, diaspora payment and AYO Wallet integrate behind licensed provider-neutral
contracts with authenticated callbacks, replay protection and reconciliation.

Wallet/Ledger alone posts immutable idempotent entries; corrections use compensating
entries. Provider outage does not change a fare and cannot convert an unconfirmed
collection into success.

