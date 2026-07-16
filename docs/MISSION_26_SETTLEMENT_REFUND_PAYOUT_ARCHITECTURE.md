# Mission 26 — Settlement, Refund and Payout Architecture

## Settlement and commission

Pricing supplies a finalized instruction. Ledger posts rider/provider receivable or cash,
driver payable, AYO commission, taxes and incentives using Finance-approved mappings.
Provider settlement later clears receivables against bank/fee/variance accounts. A
captured payment, provider settlement and bank receipt are distinct facts.

## Refunds and chargebacks

Customer Recovery authorizes a remedy; Pricing supplies any recalculation; Payments
attempts provider refund; Ledger records refund payable/issued and reverses economics via
linked compensating journals. States: `AUTHORIZED`, `SUBMISSION_PENDING`, `SUBMITTED`,
`CONFIRMED`, `FAILED`, `OUTCOME_UNKNOWN`, `RECONCILIATION_REQUIRED`. Failure never erases
the obligation.

Chargebacks are provider claims with evidence deadlines. Payments specialists and Finance
own response/accounting; Fraud advises. A chargeback does not silently establish rider or
driver blame. Double refund/chargeback recovery requires explicit reviewed policy.

## Driver payouts and incentives

Available payout is a derived eligible liability less explicit holds/obligations under
approved law and policy. Payout lifecycle separates request, risk review, reservation,
provider submission, provider confirmation, failure/release and reconciliation. A retry
reuses the business identity. Incentive eligibility is not payment; only a validated
Pricing instruction and Ledger posting recognize it. No payout timing or limit is set.
