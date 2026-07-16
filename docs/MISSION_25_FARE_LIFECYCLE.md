# Mission 25 — Fare Lifecycle

## States

`ESTIMATE_REQUESTED -> ESTIMATE_PRODUCED -> ESTIMATE_ACCEPTED -> TRIP_ASSIGNED ->
TRIP_STARTED -> FARE_INPUTS_RECORDED -> TRIP_COMPLETED -> FINAL_CALCULATED`.

`FINAL_CALCULATED -> REVIEW_REQUIRED | FINALIZED`; `FINALIZED -> DISPUTED`;
`DISPUTED -> CORRECTED | FINALIZED`; an approved result may produce
`SETTLEMENT_INSTRUCTION_PREPARED`. Correction creates a new linked calculation and
never edits the prior one. Expired/rejected estimates terminate without settlement.

## Decision envelope

Every estimate/final/correction records decision and ride IDs, policy ID/version,
city/zone/service, currency, distance/time basis, approved minimum, airport, waiting,
tolls/extras, promotion, tax, rider total, driver gross, commission, projected driver
net, confidence/data quality, expiry, reason codes and audit references. Estimates also
record accepted version; finals explain every material delta.

Commands require authenticated role, ownership/authority, idempotency key and expected
version. Server time controls expiry. Duplicate commands return the original result;
stale versions conflict safely. Missing policy/currency/rounding or contradictory inputs
route to review without producing a collectible amount.

