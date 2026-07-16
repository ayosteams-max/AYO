# Mission 25 — Pricing and Marketplace Economics Architecture

Date: 2026-07-16  
Status: **Architecture approved by CTO/CEO on 2026-07-16 for documentation
preservation. No implementation, numeric policy or activation authorized.**

## Problem, beneficiaries and success

AYO needs prices riders can understand, earnings drivers can trust and unit economics
the business can sustain without turning uncertainty, cancellations or scarcity into
hidden exploitation. Riders, drivers, Finance, Support and Operations benefit.
Success is measured by estimate accuracy, affordability, driver earnings per active
hour, contribution margin, disputes, cancellations, service availability and
role-appropriate explanation quality. The simpler launch option is static,
configuration-driven pricing with no demand adjustment; complexity is added only after
measurement and separate approval.

## Research findings and limitations

- Major mobility platforms use upfront prices based on expected time/distance and may
  adjust when a trip materially changes; this is evidence for disclosure and audit, not
  authority for AYO policy.
- Ethiopia's National Bank publishes licensed payment actors and current payment-system
  directives. Fare calculation must therefore remain separate from provider licensing,
  authorization, collection and settlement.
- Ethiopian tax, transport, airport, consumer, labour and invoice treatment is not
  established by this engineering research. Qualified Ethiopian legal, tax and
  operational approval is a launch blocker.

Sources accessed 2026-07-16: National Bank of Ethiopia payment-system directives and
licensed-provider registers; Uber public upfront-pricing and fare-calculation guidance.
Source limitations: competitor rules vary by jurisdiction and are not Ethiopian law;
web summaries do not establish AYO's tax obligations.

## Options and recommendation

| Option | Benefits | Costs and risks | Ethiopian fit | Position |
|---|---|---|---|---|
| Static versioned tariff | Simple, predictable, cheap to operate | May underreact to congestion/cost change | Strong pilot baseline | Recommended launch baseline |
| Capped deterministic adjustment | Can improve availability | Fairness, disclosure and emergency risks | Requires local evidence and policy | Extension only |
| Learned individualized pricing | Potential conversion optimization | Opacity, discrimination, drift, privacy | Poor and unnecessarily complex | Rejected |

Recommendation: one server-authoritative Pricing module consumes approved facts and
immutable policy snapshots, calculates with integer minor units, produces signed or
integrity-protected decisions and never moves money. Pricing policy is maker-checker
published and effective-dated. AI and Marketplace Health may recommend review but never
select or publish a price.

## Domain architecture

Pricing owns estimates, final fare calculations, corrections, commission calculations
and financial-policy interpretation. Separate Incentives owns programme definitions and
eligibility decisions; Pricing consumes a versioned entitlement. Mission 20 supplies
arrival/wait/evidence readiness only. Customer Recovery authorizes an approved remedy;
Pricing recalculates if needed. Wallet/Ledger alone posts value. Payments owns
authorization/collection/settlement/reconciliation. Support investigates; Dispatch and
Marketplace Health cannot price.

The design remains a modular-monolith boundary with durable PostgreSQL records,
transactional outbox, bounded queries, partitionable ride/campaign keys and provider-
neutral contracts. No service extraction is justified before measured load.

## Constitutional safeguards

- Currency is explicit; amounts use integer minor units and deterministic rounding.
- Nationality, ethnicity, language, protected traits and inferred willingness-to-pay are
  prohibited inputs.
- Published policies are immutable. Changes are prospective, approved, audited,
  staged and reversible by publishing a successor—not editing history.
- Missing, stale, ambiguous or contradictory material evidence fails closed to review
  or suppression; it cannot create a rider charge or driver penalty.
- Rider and driver projections disclose policy-approved components without exposing
  fraud controls or another person's private data.
- `ARRIVAL_WAITING_ENABLED` remains false. Mission 20 evidence cannot be used until its
  PostgreSQL integration, migration, concurrency, restart and recovery gates pass and
  activation receives separate approval.

## Explicit exclusions and gates

No runtime, migration, dependency, provider, price, fee, duration, tax rate, commission,
bonus, promotion, surge, refund, wallet/ledger mutation, production route, deployment or
activation is authorized. Numeric Ethiopian policy requires cost study, competitor and
affordability research, driver consultation, pilot simulation, qualified legal/tax
review and separate CTO/CEO approval.

## Mission evidence checklist

| Workflow step | Evidence | Status |
|---|---|---|
| Research | Problem, sources, constraints and uncertainty above | Complete for architecture |
| Options | Three approaches and recommendation above | Complete |
| Approval | CTO/CEO architecture approval recorded 2026-07-16 | Complete |
| Architecture | This document and linked artifacts | Approved documentation |
| Risks | Threat model and risk register | Approved documentation |
| Implementation onward | Explicitly outside Mission 25 | Not started |
