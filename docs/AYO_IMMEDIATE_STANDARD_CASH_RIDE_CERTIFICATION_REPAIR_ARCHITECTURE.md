# Immediate Standard Cash-Ride Certification Repair Architecture

**Status:** PRE-PRODUCTION implementation candidate. Final cash-ride certification, production activation and mobile implementation are not authorized.

**Authority:** CTO architecture approval and Founder/CEO implementation authorization, 2026-08-11.

## Problem

AYO's merged Ride Request, Dispatch, Active Ride, Pricing, Post Trip, Ledger and Support foundations did not yet prove one complete authoritative cash ride. The bounded defects were missing canonical pricing lineage at dispatch, overloaded cash evidence/accounting semantics and the absence of one purpose-scoped Support ride projection.

## Pricing lineage

Booking remains orchestration only. Pricing creates and owns the canonical `FareEstimate`, `EstimateAcceptance`, policy/version and final `FareCalculation`. A new booking confirmation records the existing preview `quote_id` plus `ride_request_id`, `fare_estimate_id`, `estimate_acceptance_id` and a deterministic lineage hash.

Canonical Dispatch fails closed with `dispatch.accepted_pricing_required` unless the persisted confirmation, estimate and acceptance bind the same rider and Ride Request, the accepted policy/version/amount match, acceptance preceded expiry, the dispatch-valid window remains current and the lineage hash verifies. The accepted lineage is immutable on the handoff. Dispatch calculates no money.

Post Trip uses a pricing-owned completion adapter. It reuses the exact final calculation on replay and refuses missing or contradictory ride/estimate/acceptance lineage. Post Trip never calculates a fare.

## Cash evidence, accounting and reconciliation

Three states remain separate:

- `CashEvidenceState` records physical collection claims only.
- `CashAccountingState` records whether a policy-authorized journal exists.
- `CashReconciliationState` records later remittance/clearing evidence.

`collection_corroborated` means only that approved evidence is sufficient to record the collection claim. It does not establish ownership, receipt by AYO, remittance, accounting authority or exhausted dispute rights.

`CashAccountingPolicy` is immutable, effective-dated, evidence-hashed and explicitly classified as production or non-production. It supports `PRINCIPAL_GROSS` and `AGENT_NET_REMITTANCE` without choosing either for production. `gross_cash_reported_minor` remains operational evidence. Only the selected approved policy may derive `platform_claim_minor`, `driver_entitlement_minor`, tax components and balanced journal instructions.

Synthetic principal and agent fixtures are non-production architecture tests. Production composition rejects a non-production policy. No production accounting model, commission, tax, remittance timing or Ethiopian tariff is selected.

Ledger remains the sole posting authority. Corrections and write-offs use linked compensating journals. Collection does not prove clearing; accounting posting does not prove remittance. Reconciliation requires distinct authorized evidence and a clearing journal.

## Support ride evidence

`SupportRideEvidenceProjection` is assembled at read time from authoritative repositories. It is bound to an authenticated staff/service subject, `support.trip.read_limited`, an authorized matching case/queue, a declared purpose and step-up for finance, fraud, safety or legal queues. Every allowed and denied query is audited.

The projection exposes only ride-safe identities, lifecycle, assignment, pricing lineage, bounded fare/payment/cash states, journal/receipt status and explicit missing-authority codes. It exposes no candidate ranking, identity document, session artifact, raw location history, unrestricted ledger data, secret or provider payload. Support owns no ride or financial state and has no mutation operation.

## Transactions, replay and recovery

No distributed transaction is introduced. Ride Request, Pricing estimate, acceptance, Booking confirmation, Dispatch, Active Ride, final Pricing, Post Trip evidence, cash evidence, accounting journal and reconciliation each retain bounded transactions and domain idempotency.

Recovery reloads immutable lineage before continuing. Matching replay returns the existing result. Changed evidence or a substituted lineage conflicts. A journal/state split may converge only after verifying the exact instruction-to-journal binding. Missing evidence is reported, never fabricated.

## Persistence

Migration `20260811_0059` is additive and reversible before activation. It adds nullable compatibility lineage columns to Booking and Dispatch, explicit cash evidence/policy/accounting records and no Support materialization. Historical financial evidence is never destructively deleted by an operational rollback.

## Smart City boundary and exclusions

Policy-versioned evidence and bounded-domain seams preserve future interoperability, but this candidate creates no generic Smart City finance framework or integration router. It adds no digital payment rail, payout, mobile feature, provider integration, production tariff, production accounting policy or production activation.

Final end-to-end certification has not been executed.
