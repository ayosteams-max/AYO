# Mission 26 — Cash Rides and Reconciliation Architecture

Pricing records expected ETB cash due. Ride completion creates a cash-collection claim,
not proof. Driver and rider acknowledgements, ride state, dispute evidence and Operations
review may corroborate it. Ledger then represents approved cash held by driver, driver
earning, AYO commission/receivable and other approved components through balanced entries.

Cash states are `EXPECTED`, `CLAIMED_COLLECTED`, `CORROBORATED`, `DISPUTED`,
`RECONCILED` or `WRITTEN_OFF` under approved authority. Offline claims are signed to the
authenticated session, idempotent and reconciled against the server snapshot. Conflicts
never silently reduce driver availability or rider access.

Collection of commission obligations, offsets against future digital earnings, limits,
write-offs and enforcement are unresolved leadership/legal/finance policies. No hidden
debt collection or automatic punishment is authorized.
