# Courier Pickup Architecture and Launch Admission Package

**Date:** 2026-07-24
**Status:** APPROVED — 2026-07-24
**Increment 1:** IMPLEMENTATION AUTHORIZED — PRE-PRODUCTION ONLY
**Production:** NOT APPROVED

## Executive decision

The repository already has one canonical Courier Pickup capability. It owns the
post-assignment, pre-custody journey: travel toward the merchant, courier-declared
arrival, merchant-acknowledged arrival and waiting evidence. This package refines that
owner. It creates neither a P2-specific Pickup domain nor a second Pickup authority.

Retain the existing truthful core:

```text
courier_assigned
        |
        v
travelling_to_merchant
        |
        v
arrived_at_merchant
        |
        v
waiting_for_pickup
```

Any active attempt may end before custody as
`pickup_attempt_ended_before_custody`, carrying a reason from a closed, versioned
taxonomy. Delay, excessive waiting, disputed arrival and stale readiness are evidence,
not lifecycle states.

`waiting_for_pickup` means only that the assigned courier's arrival has been
acknowledged under policy. It never means sealing, merchant release, custody
acceptance, pickup completion or delivery.

## Problem, beneficiaries and success

Dispatch ends at a valid assignment; Custody begins only after merchant-acknowledged
waiting. AYO needs an auditable bridge that works without continuous GPS and without
moving Dispatch or Custody authority. Couriers benefit from fair waiting evidence,
merchants from explicit acknowledgement, and operations from deterministic exception
and correction evidence.

A future increment succeeds only if it demonstrates:

- no admission without a current valid assignment;
- no state/event implying custody before Custody acceptance;
- one immutable attempt per assignment attempt, including reassignment;
- deterministic correction and closure under concurrency;
- reliable arrival/acknowledgement in approved smartphone and limited-device trials;
- no continuous location history or hidden blame attribution; and
- atomic state, audit and outbox evidence under retry and restart.

## Canonical ownership

| Responsibility | Canonical owner | Pickup relationship |
|---|---|---|
| Commerce Order | Universal Ordering | Reference only |
| Preparation readiness/correction | Preparation | Consume versioned evidence when policy requires |
| Eligibility, offer, assignment, reassignment | Courier Dispatch | Consume assignment; request review only |
| Travel, arrival, acknowledgement, pre-custody waiting | Courier Pickup | Sole owner |
| Route computation/navigation | Routing | Provider-neutral references only |
| Seal, verification, release, custody acceptance | Custody | Begins after valid Pickup evidence |
| Delivery execution | Delivery | Begins only after Custody |
| Compensation, penalties, refunds, recovery | Finance/Recovery owners | May consume evidence |
| Communication delivery | Communication owner | May translate approved outcomes |

Pickup must never own courier identity/participation, merchant master data,
Preparation, Dispatch, Custody, Delivery, Routing, Pricing, Payments, Recovery or
communication.

## Pickup admission

A Pickup attempt is admitted from a current Dispatch assignment and keyed by the
assignment attempt, not merely by order or dispatch case. Required evidence is:

- assignment and assignment-attempt reference/version;
- assigned courier Subject and participation/authority reference;
- merchant organization and provider-neutral merchant-location reference;
- Commerce Order or fulfilment reference/version;
- Dispatch case and policy/version;
- Preparation readiness reference/version where product policy requires it;
- correlation and causation identifiers; and
- no known authoritative assignment closure or supersession.

A named, versioned product policy decides whether travel may begin immediately after
assignment or only after readiness. No one rule is inferred across food, freight and
other logistics. Missing, stale, contradictory or unauthorized evidence fails closed.

Reassignment creates a new Pickup attempt. The prior attempt remains append-only.
The existing implementation's uniqueness by dispatch/order is therefore a documented
compatibility gap for a later, separately authorized additive migration.

## Lifecycle and transitions

| From | Authorized fact/command | To |
|---|---|---|
| admitted `courier_assigned` | assigned courier starts travel | `travelling_to_merchant` |
| `travelling_to_merchant` | assigned courier declares arrival | `arrived_at_merchant` |
| `arrived_at_merchant` | location-scoped merchant actor acknowledges | `waiting_for_pickup` |
| any pre-custody state | authoritative closure with reason | `pickup_attempt_ended_before_custody` |

The terminal attempt never reopens. A new assignment produces a new attempt.

Corrections are append-only:

- before merchant acknowledgement, a proven false arrival may append
  `arrival_declaration_corrected` and restore the effective projection to
  `travelling_to_merchant`;
- before Custody admission, an erroneous acknowledgement may append
  `merchant_acknowledgement_corrected` and restore the effective projection to
  `arrived_at_merchant`;
- after Custody admission, Pickup records dispute/correction evidence but cannot
  reverse Custody; and
- wrong merchant location or courier attribution is not silently rewritten. The
  attempt ends for governed review and the source owner corrects its authority.

Original actor, timestamp and evidence survive every correction.

## Arrival, merchant acknowledgement and waiting

The assigned courier declares arrival. Optional source-owned, purpose-limited location
evidence may corroborate it under policy. GPS absence is not evidence of non-arrival,
and location alone cannot replace merchant acknowledgement for the initial food
profile.

Merchant acknowledgement:

- confirms an authorized merchant-location actor acknowledges the courier's presence;
- establishes policy-defined waiting evidence;
- does not assert readiness, sealing, release or custody; and
- records the individual actor plus merchant organization/location.

Courier arrival time, acknowledgement time and any policy-derived waiting observation
remain separate facts. Excessive wait is immutable evidence, not merchant fault and
not an entitlement to compensation.

## Assignment, readiness and custody boundaries

- Assignment closed before arrival: append attempt closure; late input cannot restore
  authority.
- Reassignment while travelling/waiting: close the old attempt and admit a new one
  from the new assignment. Pickup never overwrites Dispatch history.
- Courier cannot continue: record an outcome and request Dispatch review; Dispatch
  alone decides reassignment.
- Preparation readiness correction: preserve source evidence and apply product policy
  to hold, close or refer. Pickup never mutates Preparation.
- Authoritative cancellation before custody: close the attempt without cancelling the
  order or deciding recovery.
- Custody may begin only from current
  `commerce.courier_pickup.ready_for_custody_verification` evidence. Custody performs
  verification, release and physical acceptance.

## Policy model

Approved canonical name: `AYO_COURIER_PICKUP_POLICY_V1`.

It is named, versioned, configurable and product-scoped. It governs travel admission,
arrival evidence, acknowledgement windows, excessive-wait observation, stale
readiness handling, reassignment handling and limited-device command support. No
production duration, distance, GPS threshold or automatic sanction is approved here.

## Actors and staff authority

Identity comes from authenticated server context. Shared accounts are prohibited.

- Courier actions require active participation and scope for the assigned attempt.
- Merchant acknowledgement requires active organization-, location- and action-scoped
  staff authority.
- Support-assisted input records the support Subject and represented party/authority
  basis; support cannot fabricate merchant acknowledgement.
- Operational correction requires separate least-privilege permission and reason.

All authority is revocable and evaluated at action time.

## Universal Access and limited devices

Pickup is channel-neutral. Smartphone, basic-phone SMS, voice, merchant portal and
support adapters may later translate interactions into the same canonical commands.
Capability negotiation may offer a safer reduced evidence workflow on limited devices;
it must not create another lifecycle. Lack of GPS cannot create an adverse outcome.
No channel runtime is authorized.

## Routing and location boundary

Pickup retains provider-neutral merchant-location and optional evidence references.
Routing owns routes/navigation. A location source owns current courier-location
evidence. Pickup is not a long-term courier-location history owner and must not
continuously track a courier.

## Event and transaction boundary

Pickup consumes versioned Dispatch assignment/closure evidence and, where policy
requires, Preparation readiness/correction. Authoritative cancellation and source
authority invalidation are also inputs.

Approved minimal event boundary:

- `commerce.courier_pickup.attempt_admitted`
- `commerce.courier_pickup.travel_started`
- `commerce.courier_pickup.arrival_declared`
- `commerce.courier_pickup.merchant_arrival_acknowledged`
- `commerce.courier_pickup.ready_for_custody_verification`
- `commerce.courier_pickup.wait_observed`
- `commerce.courier_pickup.attempt_ended_before_custody`
- explicit arrival, acknowledgement and attempt correction events
- `commerce.courier_pickup.dispatch_review_requested`

Each command uses expected-version optimistic concurrency, actor/action-scoped
idempotency, immutable audit/evidence and transactional outbox in one Unit of Work.
Source admission deduplicates by source event/reference/version. Delivery is at least
once; consumers deduplicate. No distributed transaction is required.

## Closed exception taxonomy

Approved `AYO_COURIER_PICKUP_EXCEPTION_TAXONOMY_V1`:

- `assignment_closed_or_revoked`
- `merchant_location_unreachable`
- `merchant_not_found`
- `merchant_unavailable`
- `order_not_ready`
- `readiness_corrected`
- `courier_unable_to_continue`
- `authority_or_identity_failure`
- `duplicate_or_invalid_attempt`
- `other_review_required`

No unrestricted free text is allowed. Internal reasons remain separate from
customer-safe wording. Pickup does not decide Recovery, compensation or sanctions.

## Privacy and surveillance restrictions

Pickup stores minimum operational references/timestamps. It must not store continuous
location history, device fingerprints, recordings, transcripts, unrestricted notes,
customer contact details, payment data or covert worker-surveillance data.

Optional location corroboration remains source-owned. Pickup stores only its
purpose-bound reference, source version, freshness class, evaluation time and outcome.
Exact coordinates are not copied unless separately approved. Production retention
requires qualified Ethiopian privacy, labour, transport and records review.

## Alternatives and evidence

Alternatives considered:

1. Travel/waiting in Dispatch — rejected; assignment authority would absorb
   post-assignment operations.
2. Arrival in Custody — rejected; presence/waiting precedes physical acceptance.
3. GPS-only arrival — rejected; weak-connectivity/basic-phone exclusion,
   surveillance risk and no merchant acknowledgement.
4. One Pickup record per order — rejected; reassignment needs immutable attempts.
5. Selected — retain the existing owner/four-state core and add attempt identity,
   one honest terminal outcome and append-only evidence.

PostgreSQL transaction isolation and row locking support deterministic competing
updates when implementations retry serialization failures and atomically persist
state/audit/outbox. Worker-platform research supports keeping waiting data reviewable
and avoiding opaque automatic blame.

Primary evidence:

- PostgreSQL 17, [Transaction Isolation](https://www.postgresql.org/docs/17/transaction-iso.html)
- PostgreSQL 17, [Explicit Locking](https://www.postgresql.org/docs/17/explicit-locking.html)
- ILO, [Algorithmic management of work](https://www.ilo.org/publications/algorithmic-management-work-and-its-implications-different-contexts)
- ILO, [Delivery platforms and working conditions](https://www.ilo.org/publications/platform-economy-and-transformations-world-work-case-delivery-platform-1)

## Governance closure

The architecture gate closed on 2026-07-24. Increment 1 authority is controlled by
`AYO_COURIER_PICKUP_INCREMENT_1_IMPLEMENTATION_AUTHORIZATION_2026-07-24.md`.
The earlier review-ready state remains preserved in repository chronology. Production
and successor increments require separate governance.

## Gate

**APPROVED. INCREMENT 1 IMPLEMENTATION AUTHORIZED — PRE-PRODUCTION ONLY.**

No production activation or successor increment is authorized.
