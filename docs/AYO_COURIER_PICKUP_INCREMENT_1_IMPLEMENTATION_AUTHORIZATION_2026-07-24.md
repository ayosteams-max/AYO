# Courier Pickup Increment 1 Implementation Authorization

**Approval date:** 2026-07-24
**Architecture:** APPROVED
**Increment 1:** IMPLEMENTATION AUTHORIZED — PRE-PRODUCTION ONLY
**Production:** NOT APPROVED
**Successors:** NOT AUTHORIZED
**Expiry:** None; effective until properly superseded

## Approvers

| Authority | Name | Role | Decision |
|---|---|---|---|
| CTO | OpenAI ChatGPT | Project CTO (Technical Oversight) | APPROVED |
| Founder | Ibrahim Hambentu Shibiru | Founder & CEO | APPROVED |

## Ownership and boundaries

Existing Courier Pickup remains the sole canonical owner of post-assignment travel,
courier arrival, applicable merchant acknowledgement, pre-custody waiting and
assignment-scoped Pickup-attempt evidence. No P2-specific or second Pickup owner may
be created.

Dispatch retains eligibility, offers, assignment, reassignment and Dispatch outcomes.
Preparation retains readiness/correction. Custody retains sealing, verification,
merchant release and custody acceptance. Delivery retains post-custody execution.
Routing, communication, Finance, Payments, Recovery and Support retain their owners.

## Approved lifecycle and attempts

`courier_assigned -> travelling_to_merchant -> arrived_at_merchant ->
waiting_for_pickup`.

Assignment is admitted from valid Dispatch evidence. Travel implies neither routing
nor tracking. Arrival is a governed declaration. Waiting records presence before
custody. No state implies release, custody or delivery.

Each valid assignment may create at most one active Pickup attempt bound to assignment
reference/version. Reassignment closes the old attempt append-only and creates a new
one. Prior evidence, correlation and causation remain.

The sole pre-custody terminal outcome is
`pickup_attempt_ended_before_custody`. It assigns no automatic blame.

## Policy and taxonomy

`AYO_COURIER_PICKUP_POLICY_V1` is named, versioned, configurable and PRE-PRODUCTION
only. It may govern admission, travel start, arrival/acknowledgement evidence, waiting
start, excessive-wait evidence, reassignment, stale readiness and limited-device
constraints. Permanent production values are not authorized.

`AYO_COURIER_PICKUP_EXCEPTION_TAXONOMY_V1` is closed and versioned:

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

Unrestricted free text is prohibited. A later approved bounded note remains internal.
Customer wording, Recovery, compensation, penalties and communication remain outside.

## Arrival, acknowledgement, waiting and corrections

Arrival may use authenticated courier declaration, merchant acknowledgement, limited
fresh source-owned location corroboration and explicitly authorized support evidence.
Location is optional and never sole authority. Continuous tracking and route history
are prohibited.

Courier arrival, merchant acknowledgement and waiting start are separate facts.
Missing acknowledgement does not erase courier arrival. Waiting evidence may include
start, acknowledgement, readiness reference, duration, order-not-ready,
stale-readiness and correction. Pickup decides no compensation, sanction, refund,
Recovery or ranking.

False arrival, waiting error, wrong location, duplicate attempt, wrong courier,
incorrect acknowledgement and invalid assignment linkage are corrected append-only.
Original evidence remains immutable; authority/reason are explicit; downstream
consumers receive a correction event. Silent mutation is prohibited.

Courier and merchant actions require authenticated individual identity, active
revocable authority, action scope and least privilege. Courier actions require
participation authority. Merchant staff require organization/location scope and dual
attribution. Support assistance records support Subject, authority basis, acting-for
attribution, reason and immutable audit. Shared accounts are prohibited.

## Custody, channel and location limits

Pickup may establish travel, arrival, acknowledgement, waiting and readiness for
future custody verification. It cannot establish seal verification, release, custody
acceptance or delivery. Valid custody acceptance permanently ends Pickup authority
for that handoff.

Pickup is channel-neutral. Future smartphone, merchant, voice, SMS, limited-device and
support adapters use the same attempt. Increment 1 implements no channel runtime.
Pickup owns no route, navigation, tracking or permanent location history.

## Authorized scope

Only Increment 1 is authorized:

- valid Dispatch assignment admission and assignment-scoped attempts;
- the approved lifecycle and terminal outcome;
- closed/versioned exception taxonomy;
- courier arrival, merchant acknowledgement and waiting evidence;
- optional source-owned location references;
- append-only corrections and reassignment boundary handling;
- custody-acceptance boundary;
- named/versioned PRE-PRODUCTION policy;
- immutable records, optimistic concurrency and actor/action idempotency;
- immutable audit/history, domain events and transactional outbox;
- least privilege;
- additive PostgreSQL migration, focused documentation and PostgreSQL certification.

Implementation must verify one active attempt per assignment; invalid/closed/stale
assignment rejection; no transition after custody; concurrent arrival/closure and
waiting/correction safety; idempotent retries; stale versions/evidence; reassignment
consistency; immutable corrections; and audit/outbox atomicity.

## Exclusions

Not authorized: eligibility, offers, assignment or ranking; routing, navigation or
tracking; release, sealing, barcode/QR verification or custody acceptance; delivery;
Preparation changes; Pricing, Tax, Promotions, Payments, earnings, waiting
compensation, penalties, refunds or Recovery; customer notifications; Voice, SMS or
USSD runtime; courier/merchant onboarding; production; Increment 2 or successors.

## Privacy and production gates

Do not retain unnecessary continuous location, customer contact data, recordings,
transcripts, fingerprints, unrestricted notes, covert surveillance, payment
credentials, navigation history or advertising identifiers.

Production requires separate approval after Ethiopian labour, transport, privacy and
commercial review; authority contracts; courier, merchant and applicable basic-phone
trials; false-arrival/fairness review; PostgreSQL 17 concurrency,
migration/rollback/restart/backup certification; security testing; production policy;
and incident/rollback readiness.

## Supersession and stop

This remains effective until superseded by an approved ADR, governance decision,
recorded Founder & CEO directive, or legal/regulatory requirement. No retroactive
rewrite is permitted.

This record performs no implementation and grants no production authority.
