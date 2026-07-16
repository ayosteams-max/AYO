# Mission 23 — Dispatch Optimization, Marketplace Health and Fairness Architecture

Date: 2026-07-16
Status: **Architecture approved by CTO on 2026-07-16. No implementation or activation authorized.**

## Recommendation

Add a provider-neutral Dispatch Coordination Policy inside the existing modular monolith,
not a new dispatcher. It classifies work and delegates commands to the owning Immediate,
Scheduled, pre-dispatch or airport boundary. A separate read-only Marketplace Health
Engine aggregates privacy-minimised outcomes and emits recommendations. Neither assigns
drivers, changes commitments, prices rides, issues incentives, restricts accounts or
alters Active Ride/Mission 20 state.

## Deterministic pipeline

`validate -> classify -> zone/product -> hard eligibility -> safety/compliance -> fresh
availability -> bounded candidates -> bounded ETA/pickup cost -> owning-policy rank ->
offer -> atomic acceptance/lock -> assignment or recovery -> audit`.

Every step records policy/version, freshness, bounded reason categories, decision ID and
audit references. Hard filters precede ranking. Predictions are typed evidence, never an
executable decision. Missing/conflicting configuration fails closed or uses an approved
deterministic fallback.

## Optimization hierarchy

- Immediate: fastest suitable reliable pickup; no delay for marginal score gain.
- Scheduled: commitment reliability, health and fallback; replace committed drivers only
  through approved recovery rules.
- Pre-dispatch: current trip first, explicit acceptance, realistic completion/buffer and
  automatic release.
- Airport: separate Standard/Premium queue, terminal, zone and access policy.
- Fairness: monitor opportunity among materially equivalent candidates without weakening
  safety, eligibility, rider wait or commitment locks.

## Research and options

Uber explains that quickest is not always closest and short batching may reduce collective
wait; its 2025 engineering article describes learned marketplace-balance optimization.
Grab models supply/demand by space/time cells and frames allocation as passenger speed plus
driver livelihood. These support simulation, not Ethiopian policy or learned launch control.

Options: exclusive sequential offers are the recommended simple launch default. Bounded
batching may improve tail waits but adds driver race/distraction and must shadow first. A
global learned optimizer is deferred for explainability, data, bias and drift reasons.

Sources accessed 2026-07-16:

- https://www.uber.com/jm/en/marketplace/matching/
- https://www.uber.com/us/en/blog/reinforcement-learning-for-modeling-marketplace-balance/
- https://engineering.grab.com/understanding-supply-demand-ride-hailing-data
- https://www.uber.com/us/en/marketplace/principles/

## Scale and rollout

Reuse PostgreSQL row/advisory locks, optimistic versions, idempotency and transactional
outbox. Partition conceptually by city/service zone and ride ID. Caches accelerate
published policies, availability and aggregates but never become authority. Hot zones use
bounded shortlists, budgets, backpressure and degraded ETA bands. Extraction requires
measured contention, lag, cost, isolation or ownership evidence; no scale claim is made.

Sequence: offline simulation -> shadow decisions -> dashboards -> non-executing
recommendations -> separately approved bounded experiment. Every stage has prior-policy
rollback and no financial/account action.

## Explainability and privacy

Every decision can produce decision/ride IDs, dispatch type, policy version, bounded
candidate-set summary, eligibility outcomes, strategy, selected-driver reason, rejected/
suppressed categories, confidence/freshness, commitment/fairness checks, recovery actions,
timestamps and audit references. Rider, Driver, Support and Operations receive separate
role-redacted renderings. Live locations, current/future destinations, performance history,
flight context and fairness analytics are used only for approved purpose/phase and reduced
to derived evidence wherever possible. Raw location retention requires separate Ethiopian
legal/operational approval.
