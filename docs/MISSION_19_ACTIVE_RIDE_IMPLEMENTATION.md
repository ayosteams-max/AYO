# Mission 19 — Active Ride Orchestrator and Real-Time Core Implementation

Date: 2026-07-16
Status: **Implemented locally; awaiting CTO/CEO review. Not committed or activated.**

## Approved outcome and exclusions

Mission 19 implements the first server-authoritative post-assignment ride core. Immediate
Dispatch still owns matching/assignment. Scheduled Dispatch still owns reservations,
commitments and pre-dispatch. Active Ride owns approach, arrival, pickup verification,
start, progress, completion and evidence/recovery after an assignment is transferred.

The feature flag `ACTIVE_RIDE_ENABLED` defaults false and is rejected in production.
There is no external stream, map, traffic, airport, event, push, SMS or voice provider;
no broker; no payment/wallet/refund/cancellation-fee behavior; no AI authority; no
deployment; no production secret or real personal data; and no mobile redesign.

## Lifecycle and compatibility

`ActiveRideState` implements the approved linear lifecycle and typed branches for
reassignment, cancellation pending/cancelled, no-show review, no-driver, operational
recovery and review. A versioned transition table rejects unsupported edges.

`translate_legacy_status` is the only compatibility mapping from prototype `RideStatus`.
`DRIVER_DECLINED` is deliberately rejected as ambiguous rather than silently converted.
Implementation-stage integration must invoke `create_from_assignment` only from a
committed Dispatch/Scheduled assignment with driver and assignment IDs.

## Synchronization and projections

Each authoritative mutation increments aggregate version and a ride-scoped monotonic
sequence in the same PostgreSQL transaction as its append-only event, idempotency result,
projection checkpoint and transactional outbox event. Commands bind authenticated actor,
opaque command ID, expected version, type and request hash. Exact retries return the
stored outcome; changed reuse conflicts; stale versions fail.

Snapshots return separate rider/driver allow-listed projections. Event replay returns at
most 100 ordered events and a polling hint. Acknowledgement stores a valid role
checkpoint. Polling remains recovery authority. `FutureRideEventStream` is disabled.

Rider projections contain public state, pickup/service, opaque assigned-driver reference,
ETA freshness, driver-change/action/price-notice boundaries and support/safety access.
Driver projections contain opaque rider reference, policy-approved destination boundary,
pickup/action/progress and estimated-earnings boundary. Neither contains scores,
candidate lists, trust, private audit, PIN digest or unnecessary contact/location data.

## Pickup verification and evidence

The server creates a cryptographically random short PIN. Only an authorized rider can
request it; it is HMAC-protected at rest with a composition-supplied secret, bound to the
ride and assignment, single-use, short-lived, attempt-limited, cooldown-protected and
invalidated on reassignment. Server confirmation is required before trip start.
Authenticated, verified-contact and assisted passenger modes use opaque delivery
references. A disabled provider-neutral QR contract cannot authorize start by itself.

Cancellation/no-show records store typed observation, actor role, safe reason,
responsibility boundary and opaque evidence references. Default responsibility is
`insufficient_evidence`; there is no automatic blame or financial action.

## Confidence and pickup intelligence

Active Ride Confidence emits immutable deterministic decisions with rule version, level,
reason, freshness/data quality, expiry and non-executing recommendation. Missing/stale
location becomes `INSUFFICIENT_DATA`; verified external delay is protective. It cannot
mutate the ride. Initial rules cover location staleness/conflict, movement away,
unexpected stop, ETA growth, verification failure, stagnation and provider outage.

Dynamic Pickup Intelligence emits expiring primary/fallback guidance, walking range,
entrance/terminal/zone, accessibility, freshness, confidence and reason codes. Divided
road, closure, cached and unavailable-provider scenarios degrade confidence. Material
change stays `proposed` until an authorized response; creation never moves pickup.

## Database schema

Migration `20260716_0013` is additive and reversible:

- `active_rides`: aggregate authority and sequence/version;
- `active_ride_events`: unique ordered append-only replay;
- `active_ride_idempotency_records`: actor/command atomic retry result;
- `active_ride_projection_checkpoints`: role convergence checkpoints;
- `active_ride_pickup_verifications`: protected challenge state;
- `active_ride_evidence`: cancellation/no-show/recovery references;
- `active_ride_confidence_decisions`: immutable advisory evaluations;
- `active_ride_pickup_recommendations`: recommendation/change status;
- `active_ride_recovery_checkpoints`: bounded restart-safe work.

Mutations, event, idempotency, projection and outbox share a Unit of Work. Runtime gets
update only on mutable aggregate/projection/verification/recommendation/checkpoint tables,
and no delete/truncate. Existing append-only audit privileges remain unchanged.

## API boundary

Disabled routes under `/api/active-rides` cover snapshot, ordered replay,
acknowledgement, en-route, arrival, pickup challenge/verification, start, progress,
approaching, completion request/completion, rider/driver cancellation, no-show evidence,
recovery, confidence, pickup recommendation and material-change response.

Authentication supplies identity. RBAC separates read, rider command, driver command and
worker permissions. Application ownership is rechecked. Existing request-size and
PostgreSQL token-bucket boundaries add read, command and verification limits. Public
errors sanitize internal conflicts.

## Workers, observability and privacy

Nine explicit worker kinds cover stale ride, lifecycle recovery, pending command, PIN
expiry, no-show timer, confidence reevaluation, pickup expiry, outbox and projection
repair. Each uses a kind-specific transactional advisory lock, bounded ordered claim,
`FOR UPDATE SKIP LOCKED`, attempt count, restart-safe completion and worker health. The
registry requires explicit composition and never starts a scheduler automatically.

Metrics cover transitions, duplicate/stale outcomes through command results,
verification, confidence levels and pickup responses. Tokens, full phones, PINs/digests,
precise location, payment credentials, notes and evidence bodies are excluded from logs
and outbox.

## Rollback and remaining activation risks

Before activation: keep `ACTIVE_RIDE_ENABLED=false`, stop controlled worker invocation,
verify no downstream active-ride outbox dependency, then downgrade to `20260716_0012`.
This removes only Mission 19 permissions and tables. Never downgrade after real use
without approved export/reconciliation.

Production PIN secret ceremony, concrete worker processors/schedules and alert thresholds,
driver/vehicle public-profile source, maps/ETA, retention, safety/support operations,
airport rules and mobile usability remain separate activation gates.

## Approved documentation amendment: future arrival and waiting intelligence

The future **Smart Arrival, Waiting and Fair Cancellation Engine** is a deterministic,
evidence-producing advisory boundary. It protects driver time while ensuring a rider has
a fair, clearly communicated chance to reach the approved pickup point. It is not part of
the Mission 19 runtime and cannot set a fee, refund, compensation, wallet entry, blame or
cancellation outcome.

Its proposed state model is `ARRIVAL_UNVERIFIED`, `ARRIVAL_VERIFIED`,
`FREE_WAIT_ACTIVE`, `FREE_WAIT_ENDING`, `WAIT_PAUSED`, `WAIT_INVALIDATED` and
`EVIDENCE_READY`. Arrival verification requires the assigned driver to be stopped or
reasonably stationary inside the approved pickup zone, sufficient GPS and pickup-point
confidence, and an unexpired assignment. During waiting, evidence must show the driver
remained available in the approved area. Uncertain GPS, pickup mismatch, map/platform
failure or verified external disruption pauses or invalidates consequence eligibility.

Before arrival, reliable driver ETA and rider walking ETA may produce an early walking
prompt. Both projections must name the same approved pickup point and show one
server-authoritative free-wait countdown. A rider receives a warning before any future
paid-wait or no-show consequence could be considered. No fixed duration is approved:
policies are versioned and configurable by city, service, airport, premium, assisted,
scheduled and accessibility context, subject to local legal and operational rules.

The engine records only evidence for future Pricing, Customer Recovery, Support and
operations review. Consequence eligibility requires a valid pickup recommendation,
verified arrival and continued availability, reasonable notification delivery, an
accurate visible timer, and no serious uncertainty or verified AYO/external failure.
Drivers retain compensation eligibility review when verified traffic, roadblock,
airport queue, weather, map/network/platform outage or emergency caused delay. AYO's
governing product principle is: **prevent cancellations, do not profit from them**.

Proposed events are `rider_start_walking_advised`, `driver_arrival_verified`,
`waiting_timer_started`, `waiting_timer_paused`, `waiting_timer_invalidated`,
`free_wait_period_ending`, `no_show_evidence_ready`,
`waiting_consequence_suppressed` and `pickup_mismatch_detected`. Every record includes
ride/assignment/pickup-policy versions, safe timestamps, source freshness, confidence,
responsibility boundary and privacy-minimised evidence references.

Reason-code families are `arrival.*`, `waiting.*`, `notification.*`, `pickup_mismatch.*`,
`data_quality.*`, `platform.*`, `external_disruption.*`, `accessibility.*` and
`evidence_sufficiency.*`. Responsibility remains one of rider, driver, AYO, external,
shared or insufficient evidence; the engine does not turn that classification into a
financial or punitive result.

## Approved documentation amendment: future Landmark Intelligence

The future **Landmark Intelligence Layer** adds locally meaningful place context to map
coordinates without becoming map, pickup or lifecycle authority. A canonical landmark
record carries a stable ID, coordinate/area reference, category, English and Amharic
canonical names, aliases and phonetic/search forms, entrances/gates, side-of-road and
legal approach data, accessibility attributes, provenance, confidence, freshness,
verification state and merge lineage.

Rider suggestions and driver-confirmed knowledge enter as untrusted observations.
Operations approval, corroboration, fraud/rate controls and versioned review are required
before promotion. Duplicate merging preserves aliases and audit lineage. Learning uses
privacy-safe aggregates rather than individual travel histories. Cached guidance includes
freshness; insufficient or ambiguous confidence falls back to coordinates and asks for
clarification.

Dynamic Pickup Intelligence may consume a landmark recommendation for an entrance,
gate, terminal or approach, but still performs safety, legal-access, accessibility,
road-direction and freshness checks. It never silently moves a confirmed pickup point;
a material change requires clear rider and driver confirmation through Active Ride.
External maps, search, traffic and local operations sources remain replaceable adapters.

Proposed events are `landmark_matched`, `landmark_confidence_low`,
`landmark_ambiguity_detected`, `landmark_correction_proposed` and
`landmark_correction_approved`. Reason-code families are `landmark.match.*`,
`landmark.ambiguity.*`, `landmark.freshness.*`, `landmark.access.*`,
`landmark.language.*`, `landmark.provenance.*`, `landmark.correction.*` and
`landmark.fraud_control.*`.
