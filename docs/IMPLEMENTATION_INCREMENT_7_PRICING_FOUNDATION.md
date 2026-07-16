# Implementation Increment 7 — Versioned ETB Pricing and Fare Calculation

**Status:** Implemented locally under CTO/CEO authorization; awaiting review. No public
route, production tariff, automatic commit, deployment or push is authorized.

## Authority and pilot boundary

Pricing is the sole calculation authority for estimates, final fares, corrections,
Driver earning components and AYO commission components. It cannot mutate Ride Request,
Dispatch or Active Ride and cannot authorize collection, settlement or money movement.
Payments remains the future provider-interaction authority; Ledger alone will post value;
Wallet will display ledger-derived projections. Support investigates, Incentives decides
programme eligibility, and AI remains advisory.

The implemented product boundary is Immediate Standard, ETB, cash-compatible intent, one
pickup and one destination. Policies are synthetic/configuration-driven. Scheduled,
Airport, surge, promotion, referral, loyalty, paid waiting, cancellation consequences,
digital payments, refunds and production tariffs fail closed or have no runtime path.

## Immutable policy lifecycle

Pricing policies use `DRAFT -> APPROVED -> PUBLISHED -> RETIRED` metadata and immutable
version identities. They include effective dates, service zone/type, ETB components,
commission basis points, a zero-by-default tax placeholder, rounding increment and linked
predecessor. The maker cannot approve; the checker cannot publish. Runtime application
credentials receive read-only policy access, so published numeric terms cannot be edited
through normal runtime authority. A correction requires a new policy version or linked
calculation, never history mutation.

No numeric value in production is approved by this implementation. Tests use conspicuously
synthetic policies only.

## Estimate and acceptance

An estimate requires an owned `READY_FOR_DISPATCH` Immediate Standard request with
cash-compatible intent, a matching currently published policy and fresh bounded route
metrics. `RouteMetricProvider` accepts distance/duration evidence only; it never supplies
a fare total. Inputs record provider/version, provenance, timestamp and data quality.

The immutable estimate stores policy and request lineage, metrics, component breakdown,
Rider total, Driver gross estimate, commission estimate, projected Driver net, expiry,
reason codes, translation keys, audit and correlation/causation references. Acceptance
derives Rider identity from trusted context, copies the exact ETB amount and policy
version, validates expiry and is PostgreSQL-idempotent. It moves no money and does not
guarantee identical final inputs.

## Final calculation and correction

Final calculation requires the accepted estimate and a matching canonical Active Ride in
`COMPLETED`, including request/rider/driver/dispatch lineage. The accepted policy version
is reused even if a newer policy exists. Fresh final distance and duration inputs produce
an append-only component breakdown and estimate-to-final difference. Settlement readiness
is explicitly false; the cash projection says only `amount_expected`, `not_recorded` and
`not_started` for collection/reconciliation.

## Complete calculation lineage and reproducibility

Every estimate, final calculation and correction stores an immutable calculation-lineage
snapshot beside its completed component breakdown. The snapshot captures the formula
version; immutable policy and predecessor IDs; maker, checker and publisher identities and
timestamps; distance and duration values and their distinct sources; route-metric provider,
version, provenance and observation time; every rate and threshold; rational numerators and
denominators; pre-minimum and pre-rounding values; minimum adjustment; rounding increment;
commission and tax-placeholder operands; canonical input hash; and audit, correlation and
causation event identities.

The engine can reproduce the complete breakdown solely from this snapshot and rejects an
unknown formula version. Automated tests compare the reproduced result with the persisted
result. The canonical hash excludes incidental event identities, so the same approved
financial inputs produce the same hash and amounts. Corrections preserve predecessor
calculation lineage and create a new event-linked snapshot; they never obscure the original.

Future Ledger, Wallet, Tax, Finance, Audit and regulatory-reporting consumers receive the
persisted Pricing result and its lineage as an authoritative financial fact. They must not
recalculate a fare or infer missing amounts. AI output is absent from calculation inputs and
cannot supply a formula, policy, amount, component, approval or correction.

## Permanent financial traceability

Calculation lineage and lifecycle traceability are distinct immutable contracts. Every
Pricing artifact carries a `FinancialTraceability` snapshot. An estimate records the Ride
Request and Fare Estimate identities. Once a canonical ride is completed, each final or
corrected calculation records the authoritative Ride Request, Dispatch Handoff, Assignment,
Active Ride, Fare Estimate and Fare Calculation identities. A correction adds its own Fare
Calculation identity and an explicit predecessor-calculation identity while copying the
unchanged upstream chain.

The implementation now enforces this as a hard persistence contract. Pricing rejects
missing or contradictory lineage, rejects forged upstream IDs and rejects any attempt to
append a correction without a distinct predecessor chain. Missing lineage, mismatched
lineage or cross-ride contamination fail closed. The same immutable chain is made available
through the Ride-ID financial journey projection so Support, Finance and Audit can
reconstruct the full financial journey without inference or recalculation.

Reserved nullable identities provide schema-compatible seams for future Ledger Transaction,
Wallet Projection and Settlement Instruction artifacts. They remain empty in Increment 7;
Pricing cannot invent or populate identifiers owned by future authorities. Those authorities
must append their own immutable artifacts and carry this chain forward rather than update a
Pricing record or reconstruct historical relationships.

The separately permissioned financial-journey projection starts with one Active Ride ID and
returns the explicit authoritative Ride Request, Dispatch Handoff and Assignment identities,
plus all linked estimates and append-only calculations. It validates every stored calculation
chain against the canonical ride and fails closed on conflict. Support, Finance and Audit
roles require the `pricing.trace.read` permission; absence and unknown rides share the same
privacy-safe denial. The projection exposes no payment execution authority.

Corrections require authorized Staff/Administrator context and approved evidence reason.
They append a `CORRECTED` calculation linked to the predecessor; the original remains
unchanged. No refund, adjustment, cash claim or ledger instruction is created.

## Money, rounding and transparency

All persisted money is integer minor units. Pydantic and PostgreSQL reject negative,
fractional, mixed-currency and excessive inputs. Distance and duration multiplication use
integer half-up rational rounding followed by the policy's integer increment. Stable JSON
input hashing binds actor, operation and idempotency key; changed replay fails.

Rider projections show total and approved fare/tax components but omit internal commission.
Driver projections separately disclose gross, commission and projected net. Ownership is
checked for both projections. Stable reason codes, versioned translation keys and
parameters are authoritative; no financial prose is stored in domain state. Official
financial wording still requires human-reviewed language packs.

## Persistence and events

Revision `20260716_0019` adds:

- `pricing_policies`
- `fare_estimates`
- `fare_estimate_acceptances`
- `fare_calculations`
- `pricing_calculation_components`
- `pricing_idempotency`
- `pricing_events`
- `pricing_outbox`

Estimate creation/acceptance, final inputs/final calculation and correction events are
privacy-minimised, transactional and replay-safe. They carry no payment authorization.
Outbox consumers remain inactive and require independent idempotent inboxes and flags.

## Inactive evidence and ecosystem seams

`CertifiedPricingEvidenceReference` preserves a typed, unused boundary for a future
separately approved Mission 20 evidence input. No waiting, no-show or cancellation amount
can be supplied today, and a timer has no financial meaning. Mission 20 remains disabled.

Completion/calculation events preserve inactive seams for Wallet/Ledger, Driver Support
Bonus, AYO Status, AYO Family, Growth, Trust, Promotions and Referrals. Pricing may later
calculate an authorized amount but cannot decide programme eligibility. No consumer is
implemented, and no event changes status, rewards, trust, family sharing or balances.

## Rollback and remaining decisions

Rollback disables any future consumer, drains/quarantines revision-19 outbox work,
retains or exports required calculation evidence, and downgrades to revision 18. Empty and
existing-head upgrades, metadata parity and single-head behavior are tested.

Before any production policy or activation, leadership and qualified Ethiopian specialists
must approve actual tariffs, affordability evidence, Driver operating costs and earnings,
commission, rounding/display convention, tax treatment, receipts, cash operations,
material-difference thresholds, correction authority, retention and dispute procedures.
