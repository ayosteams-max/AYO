# Courier Pickup Models and Boundary Specification

**Status:** APPROVED — 2026-07-24; INCREMENT 1 PRE-PRODUCTION ONLY

## Aggregate and invariants

The proposed aggregate is `CourierPickupAttempt`, identified by Pickup-attempt and
source assignment-attempt references. Multiple immutable attempts may refer to one
dispatch case/order.

- One attempt belongs to one assignment attempt.
- Only the assigned, authorized courier starts travel/declares arrival.
- Only an authorized actor for the merchant location acknowledges.
- Closed/superseded assignment evidence fails closed.
- A terminal attempt never reopens.
- Waiting never implies custody.
- Reassignment creates a new attempt.
- Corrections retain original evidence.

## Arrival and acknowledgement evidence

Arrival records attempt, assignment/version, courier Subject, merchant
organization/location, declaration time, optional source-location evidence
reference/version/freshness, policy/version, authority, correlation/causation, audit
and outbox references.

Acknowledgement additionally records authenticated staff Subject,
organization/location scope, authority basis/version and acknowledgement time.
Arrival and acknowledgement remain separate facts. Waiting observations record the
policy and source timestamps and do not assign fault.

## Actor model

| Action | Required authority |
|---|---|
| Start travel / declare arrival | assigned courier; active participation/action scope |
| Acknowledge | authenticated merchant staff; merchant/location/action scope |
| Support-assisted input | support actor plus represented party and authority basis |
| Correct | explicit correction permission, reason and dual attribution |

Shared identities are prohibited. Revocation fails closed. Support cannot convert an
unverified report into merchant acknowledgement.

## Corrections

Corrections append target-evidence reference, structured reason, correcting actor,
authority, effective time and correlation/causation. Downstream correction events are
mandatory. Wrong merchant master data is corrected by Merchant; wrong assignment by
Dispatch.

## Transactions and failure

One command, aggregate update, evidence, audit and outbox commit in one Unit of Work.
Every command supplies expected version. Idempotency is actor/action/aggregate scoped.
Competing progress/correction/closure inputs produce one legal winner; stale commands
fail explicitly. At-least-once events deduplicate by source event/reference/version.

`commerce.courier_pickup.ready_for_custody_verification` is emitted only from current
merchant-acknowledged waiting. It proves neither seal, release nor custody.

## Universal Access and privacy

Rich-device, basic text/voice, merchant and support adapters issue the same commands.
Limited channels may omit optional corroboration but never create another truth.

Permitted data is purpose-bound operational evidence and opaque source references.
Forbidden data includes continuous location, device fingerprints, recordings,
transcripts, unrestricted notes, customer contact data, payment data and covert
surveillance.
