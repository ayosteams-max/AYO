# Courier Pickup Increment 1 Implementation

**Implemented:** 2026-07-24
**Environment:** PRE-PRODUCTION ONLY
**Production:** NOT APPROVED
**Successor increments:** NOT AUTHORIZED

## Implemented foundation

The existing canonical Courier Pickup module was evolved additively:

- Pickup attempts bind to Dispatch assignment ID/version and attempt number;
- the four approved forward states remain unchanged;
- `pickup_attempt_ended_before_custody` is the sole pre-custody terminal outcome;
- `AYO_COURIER_PICKUP_EXCEPTION_TAXONOMY_V1` is closed;
- `AYO_COURIER_PICKUP_POLICY_V1` validates optional source-owned location-reference
  freshness without storing coordinates or location history;
- arrival, merchant acknowledgement, waiting, terminal and correction evidence are
  immutable;
- arrival/waiting corrections append evidence and update the effective projection;
- reassignment can create a new attempt without overwriting the old attempt;
- actor/action idempotency, expected-version concurrency, audit and transactional
  outbox are preserved atomically in the Unit of Work;
- correction and closure permissions are action-scoped; and
- valid Custody acceptance ends Pickup authority.

Revision `20260724_0056` removes one-order/one-dispatch uniqueness, introduces one
assignment per attempt, adds evidence/correlation fields and least-privilege
permissions, and preserves historical rows as legacy attempts.

## Boundaries

Courier Pickup owns only post-assignment travel, arrival, acknowledgement and
pre-custody waiting evidence. It does not implement or own Dispatch, Routing,
navigation, tracking, Preparation, merchant release, Custody, Delivery, Pricing,
Payments, communication, Recovery or production activation.

Optional location evidence is an opaque source reference/version with a policy
freshness check. It is not sole arrival authority and no coordinates, route or movement
history are retained.

## Verification status

The 2026-07-24 verification gate found **IMPLEMENTED — CERTIFICATION INCOMPLETE**.
The complete non-PostgreSQL suite passes with 399 passed, 201 PostgreSQL-dependent
skips and one expected xfail. The nondeterministic Dispatch quote fixture was
corrected by using its controlled clock without weakening production expiry checks.

The authoritative repository-wide branch-coverage result is 56%, below the unchanged
70% gate. Live PostgreSQL 17 certification remains pending because
`AYO_TEST_DATABASE_URL`, PostgreSQL and the backup/restore client tools are unavailable
in the current environment. Full evidence and executable certification commands are
recorded in
`AYO_COURIER_PICKUP_INCREMENT_1_VERIFICATION_CERTIFICATION_2026-07-24.md`.

The milestone remains PRE-PRODUCTION. Production and Increment 2 remain prohibited.
