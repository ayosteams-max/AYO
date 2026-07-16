# Implementation Increment 4 — Canonical Ride Request and Pickup Foundation

Date: 2026-07-16
Status: **Implemented locally; awaiting CTO/CEO review. Not activated or committed.**

## Authority and outcome

This increment creates a durable, server-authoritative pre-dispatch aggregate for an
authenticated Rider's Immediate Standard request. It owns canonical pickup/destination
definitions, deterministic service-zone validation, pre-assignment cancellation,
idempotency, audit evidence and transactional internal events. It does not call or replace
Dispatch, Active Ride, Pricing, Payments, Mission 20 or any provider.

Only `immediate_standard` and cash-compatible intent metadata are accepted. Unsupported
service types fail schema and database constraints. The authenticated subject supplies
identity; no command contains a rider identity. Cross-rider access returns a privacy-safe
denial. Support access remains an explicit permission boundary and has no public route.

## State, location and validation

The aggregate uses `DRAFT`, `REQUESTED`, `VALIDATING`, `READY_FOR_DISPATCH`,
`VALIDATION_FAILED`, `CANCELLED` and `EXPIRED` with typed transitions and optimistic
versions. `READY_FOR_DISPATCH` means validation evidence is complete; it is not assignment
and does not start dispatch.

Pickup stores coordinate, accuracy, observation time, source, optional address/landmark,
entrance, exact-stop, airport and reference-photo metadata references, note, safety status,
map confidence and policy version. Destination stores equivalent minimum canonical
location metadata. No photo, route, ETA, distance, fare, walking or arrival behavior exists.

Service zones are versioned configuration records with active dates, supported service
types, rectangular containment and optional prohibited rectangles. This is a dependency-
free pilot representation, not an Addis policy polygon. A future reviewed PostGIS or
provider adapter may replace containment behind the domain contract when complex geometry
is operationally required.

Validation records decision/policy/zone versions, reasons, invalid fields, evidence
freshness and audit reference. It checks active Rider state, product/zone support,
prohibition, accuracy, freshness, separation and conflicting active requests. AI has no
authority. Missing or inactive configuration fails closed.

## Reliability, privacy and rollback

Creation and cancellation idempotency keys are bound to Rider and operation. Same payload
returns the canonical result; changed payload is rejected; PostgreSQL conflict handling
serializes concurrent duplicates. Aggregate updates use expected versions. Events and
outbox are atomic and contain state/product metadata—not notes or precise locations.

Migration `20260716_0016` upgrades from the current head, supports clean database upgrade,
metadata parity, serialized deployment and downgrade to `20260716_0015`. Rollback keeps
the feature unexposed, stops future consumers, drains or discards unprocessed internal
events under operations approval, then downgrades after dependent data is handled.

## Exclusions and open policy

No driver matching, offers, assignment, ride execution, routing, maps provider, pricing,
fees, payments, wallets, Scheduled/Airport products, Mission 20 runtime, walking guidance,
AI automation or public endpoint is implemented. Ethiopian launch zones, prohibited pickup
areas, address standards, landmark governance, accuracy/freshness thresholds, consent,
retention and operational cancellation reasons require separate leadership and qualified
local review before configuration publication.
