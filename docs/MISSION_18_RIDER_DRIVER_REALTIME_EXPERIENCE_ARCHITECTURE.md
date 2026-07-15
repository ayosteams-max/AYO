# Mission 18 — Rider and Driver Real-Time Experience Architecture

Date: 2026-07-16
Status: **Proposed architecture for CTO/CEO review; no implementation authorized.**

## 1. Mission boundary and constitutional case

### Problem, beneficiaries and success

After dispatch accepts a request, riders and drivers need one calm, recoverable view of
what is true and what to do next. Today AYO has durable immediate/scheduled dispatch,
authentication, outbox, recovery and notification foundations, but its complete active
ride experience and canonical post-assignment lifecycle are not yet approved.

Riders benefit from certainty, safe pickup and visible recovery. Drivers benefit from
clear offers, honest earnings information, safe actions and protection from failures
outside their control. Operations benefit from an auditable lifecycle instead of client
interpretation.

Proposed success measures are lower request-to-assignment uncertainty and support
contact, high pickup-verification and trip-completion rates, fast reconnect recovery,
low stale-command rates, and equivalent task success in Amharic, low-data mode and on
the supported oldest Android tier. Exact launch thresholds require field baselines.

The simpler alternative—periodically fetch a ride record and map its status directly to
screens—cannot safely handle reordering, command retries, reassignment, third-party
passengers or two-device convergence. A single provider-specific socket is also
insufficient because delivery is not authority and weak networks are expected.

### Scope and exclusions

This document defines product journeys, presentation states, authoritative lifecycle,
contracts, synchronization, verification, cancellation/no-show classifications,
airport/premium experience, accessibility, security, metrics and testing. It extends,
but does not replace, Missions 12–17.

No code, migration, dependency, provider selection, fare/fee/refund policy, payment or
wallet mutation, AI/support/recovery engine, external map/flight/communications service,
deployment, production activation or real personal data is authorized.

## 2. Current foundation and ownership rule

- Immediate dispatch owns search, offers, timeout/reassignment and assignment.
- Scheduled dispatch owns reservation consent, planning, commitment, revalidation,
  reassignment and activation as a ride.
- Authentication supplies trusted subjects; caller identity and role claims are ignored.
- PostgreSQL, transactional audit/outbox and workers are durable authority.
- Notifications are delivery attempts, never proof of state.
- Marketplace Intelligence is advisory and cannot execute transitions.
- Support cases, future Customer Recovery and Trust, and future AI support remain
  separate authorities with purpose-limited access.

Mission 18 proposes an **Active Ride Orchestrator** module inside the modular monolith.
It owns the canonical ride after assignment/activation, including arrival, pickup
verification, trip progress, completion and typed termination. Dispatch transfers
authority through an idempotent `assignment_confirmed` or `reservation_activated`
command in the same durable transaction/outbox chain. Extraction later is possible
through the same contracts; no microservice is justified now.

Clients display authorized projections and submit commands. They never author fares,
assignments, identity, verification success, trip completion, payment status, driver
eligibility, cancellation responsibility or recovery outcomes.

## 3. Experience principles and shared screen grammar

Every active screen has:

1. a plain-language headline stating what is happening;
2. one next-action line stating what AYO or the person will do;
3. one primary action, with destructive actions behind confirmation;
4. a compact connection/state-freshness indicator only when degraded;
5. persistent Safety and Help access that never hides behind a map gesture; and
6. price-change and driver-change notices that require acknowledgement when material.

Presentation states are not raw domain states. Copy is localized and versioned. Internal
candidate lists, scores, thresholds, worker names, event offsets and sensitive identity
never appear. Maps support the task but do not replace the textual status.

## 4. Rider experience

| Presentation state | Primary message/action | Required clarity and recovery |
|---|---|---|
| Destination selected | Confirm pickup/destination | Editable place labels and accessibility needs |
| Fare reviewed | Review estimate, ETA and service; **Request AYO** | Quote expiry/conditions; no hidden total change |
| Request pending | “Sending your request…” | Idempotent retry; never create a second ride |
| Searching | “Finding your best driver…” | Honest estimate and cancel access |
| Search expanding | “Checking a wider area” | Explain possible longer pickup; price unchanged unless a new quote is explicitly accepted |
| Assigned | Driver/vehicle match card | Photo, first name, plate, vehicle, verified service attributes, ETA; driver-change banner |
| Driver approaching | Live approach plus textual ETA | Pickup entrance guidance, masked contact, edit restrictions |
| Driver arrived | “Your driver is here” | Vehicle-match checklist, waiting-window communication, PIN ready |
| Verify pickup | “Confirm this is your AYO” | PIN/approved fallback; no trip start until server verifies |
| Trip started | “Trip started” | Destination, route/ETA, safety/share/help |
| In progress | Progress and next meaningful update | Delay/off-route check-in without alarmist copy |
| Destination approaching | “Arriving soon” | Safe exit reminder and destination confirmation |
| Completed | Final trip summary | Server final fare status, receipt availability, rating; payment state may remain pending |
| Cancellation | Reason selection then consequence preview | No unapproved fee promise; responsibility is not decided by UI |
| No driver | Clear final search outcome | Retry, change service/time or support; no infinite spinner |
| Reassignment | “We’re finding a replacement” | Why at public reason level; old driver removed; new identity shown only after assignment |
| Recovering connection | Last confirmed state with timestamp | Actions show queued/sending/confirmed/failed; emergency access remains local |

Scheduled/third-party rides add a persistent “Booked by … / Passenger …” role summary,
shown only to authorized participants. The booker sees bounded status, not unnecessary
live passenger location. A contact-only passenger receives the minimum confirmation,
driver-match and pickup instructions through an approved future channel or assisted
operator. Decline/cancel authority follows Mission 16, not whoever holds the device.

Ratings are separate rider and driver submissions with optional structured feedback.
One party cannot see the other party’s rating before submitting or expiry. A rating is
feedback, not an automatic safety or livelihood decision.

## 5. Driver experience

| Presentation state | Primary message/action | Guardrails |
|---|---|---|
| Offline | “You’re offline” / Go online | Explain eligibility issue without sensitive internals |
| Available | “You’re online” | Map is secondary; earnings summary not distracting |
| Offer | Pickup area, pickup ETA, policy-approved destination disclosure, expected duration/earnings, service requirements | Large Accept/Decline, audible/haptic cue, server countdown, no hidden decline penalty |
| Offer responding | “Sending your response…” | Idempotent response; expiry may win and is calmly explained |
| Accepted | “Ride confirmed” | Assignment version and next action |
| Navigate to pickup | Route and safe next manoeuvre | Masked relay; no typing while moving |
| Arrived | Confirm arrival when server/geofence evidence permits | Wait timer uses server time; unsafe/unreachable path available |
| Verify passenger | Ask for short-lived PIN and match passenger role | Attempt limits; no code displayed to driver in advance |
| No-show | Contact attempts, wait evidence, typed reason | Server eligibility; no driver-authored blame/fee |
| In trip | Navigation, destination and safety | No next-trip interaction that encourages rushing |
| Approaching destination | Safe arrival guidance | Completion remains a deliberate, server-validated command |
| Complete | Trip summary and earnings breakdown | Payment/wallet status separate and explicitly pending if unavailable |
| Next opportunity | Ordinary offer or clearly labelled pre-dispatch | Current passenger protected; decline has no hidden penalty |
| Recovering | Last confirmed task and offline-safe navigation | Never infer accept/start/complete from a tap without confirmation |

The offer discloses airport/scheduled/premium/accessibility requirements and whether it
starts after the current ride. Destination disclosure and expected-trip-duration rules
are leadership policy decisions and must be uniform, explainable and tested for driver
safety/fairness. Drivers never see passenger phone number, private notes, full surname,
booker financial identity or unnecessary exact destination before approved disclosure.

### Earnings completion projection

The server supplies a versioned, immutable-reference breakdown in integer minor units:
trip fare basis; time/distance components when applicable; airport/premium component;
approved bonus; tolls/extras; AYO commission; applicable taxes; total driver earnings;
and future wallet/payment status. Each line has a public reason label and status
(`estimated`, `final`, `pending`, `adjusted`). Rider fare and driver earnings are
separate projections linked by ride/pricing version; neither is described as identical.
Mission 18 does not calculate or post money.

## 6. Authoritative state machines

### Canonical ride lifecycle

```text
REQUEST_ACCEPTED
  -> SEARCHING <-> OFFERING
  -> ASSIGNED
  -> DRIVER_EN_ROUTE
  -> DRIVER_ARRIVED
  -> PICKUP_VERIFICATION_PENDING
  -> PICKUP_VERIFIED
  -> IN_PROGRESS
  -> DESTINATION_APPROACHING
  -> COMPLETION_PENDING
  -> COMPLETED
```

Typed branches:

```text
SEARCHING/OFFERING -> NO_DRIVER_AVAILABLE
pre-pickup active state -> REASSIGNING -> SEARCHING/OFFERING/ASSIGNED
pre-completion nonterminal state -> CANCELLATION_PENDING -> CANCELLED
DRIVER_ARRIVED/PICKUP_VERIFICATION_PENDING -> NO_SHOW_REVIEW ->
  CANCELLED | PICKUP_VERIFICATION_PENDING | OPERATIONAL_REVIEW
any nonterminal state -> OPERATIONAL_RECOVERY -> prior safe state |
  REASSIGNING | CANCELLED | OPERATIONAL_REVIEW
```

`DESTINATION_APPROACHING` is a server-derived progress marker, not permission to
complete. `CANCELLATION_PENDING`, `NO_SHOW_REVIEW` and `OPERATIONAL_RECOVERY` prevent a
client from presenting an allegation as adjudicated fact. Every transition records
aggregate version, actor/service, server time, command/idempotency key, public and
restricted reason codes, causation/correlation and policy version.

### Ownership by transition

| Transition family | Authority |
|---|---|
| Request, quote acceptance | Ride Request/Pricing authorities |
| Search, offer, assignment, reassignment/no-driver | Immediate or Scheduled Dispatch |
| Scheduled consent/commitment/activation | Scheduled Dispatch |
| En-route/arrived evidence and pickup verification | Active Ride Orchestrator using Dispatch assignment and Verification policy |
| Start/progress/approaching/completion | Active Ride Orchestrator; Pricing may finalize monetary projection separately |
| Cancellation/no-show classification | Active Ride Orchestrator with policy evidence; Recovery/Support may review but not rewrite history |
| Payment/wallet result | Future approved financial authority only |
| Rating | Feedback domain; Safety/Support consumes only authorized evidence |

The existing prototype `RideStatus` is compatibility behavior, not the final Mission 18
contract. Implementation must introduce a compatible translation and prove parity; it
must not silently reinterpret old statuses.

### Rider presentation machine

`reviewing -> submitting -> searching -> assigned -> approaching_pickup -> arrived ->
verify_pickup -> in_trip -> approaching_destination -> completed`, with overlays for
`reassigning`, `cancelling`, `recovering`, `action_required`, `no_driver` and `support`.
An overlay never advances canonical state.

### Driver presentation machine

`offline <-> available -> offer -> responding -> assigned -> to_pickup -> arrived ->
verify_passenger -> in_trip -> completing -> available/offline`, with overlays for
`pre_dispatch_offer`, `cancelling`, `no_show`, `recovering`, `safety` and `support`.
Offer expiry returns to the latest server-authorized availability; a local countdown
cannot accept after expiry.

## 7. Real-time synchronization architecture

### Recommendation: snapshot + ordered event stream + HTTPS commands

The contract is transport-neutral:

- `RideSnapshot`: complete authorized projection, `ride_id`, `aggregate_version`,
  `last_sequence`, `server_time`, `generated_at`, state, next allowed actions and
  freshness for location/ETA/price subprojections.
- `RideEventEnvelope`: opaque `event_id`, ride-scoped monotonic `sequence`, aggregate
  version, event type/schema version, occurred/server time, causation/correlation,
  privacy-filtered payload and optional snapshot-required flag.
- `ClientCommandEnvelope`: opaque `command_id`, idempotency key, expected aggregate
  version, device session reference, command type/schema version and bounded payload.
- `CommandReceipt`: accepted/duplicate/rejected/indeterminate, current version/sequence,
  stable public error, and whether snapshot refresh is required.
- `ClientAck`: highest contiguous sequence applied, projection version and device
  session; an acknowledgement is delivery evidence, never state authority.

Events are append-only projections from committed domain/outbox events. Sequence is
monotonic per ride, not global. Clients apply only the next contiguous sequence,
ignore exact duplicate event IDs, reject lower aggregate versions, buffer a small
bounded gap briefly, then fetch a snapshot. Payload evolution is additive and versioned;
unknown noncritical events trigger refresh, never a guessed transition.

On foreground/reconnect/app restart: load encrypted minimum local snapshot, mark it
“last updated,” authenticate, request `snapshot?after_sequence=n`, reconcile allowed
queued commands, then start streaming. A server `resync_required` response discards
unconfirmed incremental state and replaces it with a snapshot.

### Transport comparison

| Option | Strength | Weakness | Mission 18 recommendation |
|---|---|---|---|
| WebSocket | Full duplex, low-latency foreground events/acks | Connection lifecycle, proxy/network churn, heartbeat/battery and scaling complexity | Preferred later foreground stream after prototype/load proof; commands still use HTTPS |
| SSE | Simple one-way ordered text stream with reconnect/event ID semantics | Native mobile support/auth/proxy behavior varies; client commands remain separate | Valid interchangeable adapter/pilot, especially web/ops; do not make domain contract SSE-specific |
| Controlled polling | Universal HTTP behavior and easy recovery | Higher latency/data/battery if fixed/aggressive | Mandatory fallback with state-aware cadence, jitter, ETag/version and server retry hints |
| Push notification | Wakes/background-notifies efficiently | Delayed, collapsed, duplicated or absent; privacy/provider constraints | Wake-up hint only: carry opaque ride/event reference, then fetch snapshot |

Staged approach:

1. **Stage A:** HTTPS commands + snapshot/long or adaptive polling; prove semantics on
   weak networks and old Android before adding persistent transport.
2. **Stage B:** provider-neutral foreground stream adapter (WebSocket recommended for
   native two-way telemetry/acks; SSE remains a compatible server-to-client adapter).
3. **Stage C:** separately approved push adapter for wake-up only.
4. Revisit a broker/provider only when measured connections, fan-out, lag, availability
   or operating cost exceed the modular-monolith/outbox delivery boundary.

Polling cadence is fastest only during offer/arrival/verification, backs off during long
trips, pauses appropriately in background and adds jitter. Android guidance warns that
network requests wake power-intensive radios; fixed high-frequency polling is rejected.

### Offline command boundary

Queue only low-risk, explicitly retryable commands: acknowledgement, rating draft,
privacy-safe telemetry batch, and a cancellation *request* that visibly remains pending.
Offer accept/decline may be retained only within server expiry and must show “sending,”
never accepted locally. Arrival, pickup verification, trip start and completion require
online server confirmation or a separately approved cryptographic offline-authority
protocol; Mission 18 proposes none. Emergency calling and locally displayed trip details
remain available without AYO connectivity.

## 8. API and event contract proposal

All routes are versioned, authenticated, resource-authorized, rate/size bounded and
disabled by default until implementation approval. Identity derives from the trusted
subject. Stable public failures include `authentication_required`, `access_denied`,
`ride_not_found`, `state_conflict`, `command_expired`, `verification_failed`,
`verification_locked`, `rate_limited`, `resync_required`, `temporarily_unavailable`.

| Contract | Purpose |
|---|---|
| `GET /v1/active-rides/{ride_id}` | Role-specific snapshot; conditional by version/ETag |
| `GET /v1/active-rides/{ride_id}/events?after=` | Bounded replay/poll fallback |
| `STREAM /v1/active-rides/{ride_id}` | Provider-neutral authorized event stream |
| `POST /v1/active-rides/{ride_id}/commands` | Typed idempotent commands with expected version |
| `POST /v1/active-rides/{ride_id}/acks` | Highest contiguous applied sequence |
| `POST /v1/active-rides/{ride_id}/pickup-verifications` | Attempt using server challenge reference |
| `POST /v1/active-rides/{ride_id}/support-entry` | Purpose-scoped case handoff reference |
| `POST /v1/active-rides/{ride_id}/share-grants` | Short-lived revocable trip-share capability |

Core public events include `search_status_changed`, `driver_assigned`,
`driver_reassignment_started`, `driver_location_updated`, `eta_updated`,
`driver_arrived`, `pickup_verification_required/succeeded`, `trip_started`,
`trip_progress_updated`, `destination_approaching`, `trip_completed`,
`cancellation_requested/completed`, `no_show_review_started/resolved`,
`no_driver_available`, `price_projection_changed`, `receipt_available`, and
`recovery_status_changed`. Each role receives a separate allow-listed payload.

Location events are coalescible and need not be replayed point-by-point; the newest
authorized snapshot wins. Lifecycle/price/identity-change events are not coalesced.

### Active Ride Confidence Engine contract

Mission 18 adds a deterministic, explainable **Active Ride Confidence Engine** as a
non-blocking observer of immediate, scheduled, pre-dispatch, airport, premium,
third-party and assisted rides. It is production authority only for its own health
classification and recommendation record. It is not ride-lifecycle, dispatch, pricing,
financial, blame, cancellation or safety authority.

The engine consumes privacy-minimised, freshness-bearing projections rather than
reading another module's private tables. Inputs may include lifecycle progress,
pickup/route/ETA observations, rider and driver connectivity, location accuracy and
freshness, pickup verification attempts, masked communication delivery, scheduled and
pre-dispatch feasibility, airport-zone context, provider health, outbox/worker lag and
approved traffic, road-closure, weather, event or emergency context.

Every immutable evaluation contains:

```text
ConfidenceDecision {
  confidence_decision_id
  ride_id
  rule_set_id
  rule_set_version
  health_level
  reason_codes[]
  signal_freshness[]
  data_quality_status
  generated_at
  expires_at
  recommended_actions[]
}
```

Health is an independent projection, never a ride state:

- `HEALTHY`: required fresh signals are consistent with expected progress;
- `WATCH`: a bounded early anomaly exists but stability/materiality gates are not met;
- `AT_RISK`: sustained, material evidence indicates likely service degradation;
- `CRITICAL`: configured operational intervention thresholds are met, without implying
  fault, danger or permission to cancel; and
- `INSUFFICIENT_DATA`: required signals are missing, stale, contradictory or too low
  confidence to classify safely.

`DataQualityStatus` is `GOOD`, `DEGRADED`, `STALE`, `CONFLICTING` or `UNAVAILABLE`.
Signal freshness records source class, observed time, age band and confidence—not raw
unnecessary coordinates or provider payloads. Server time and immutable rule versions
make replay deterministic.

Proposed versioned reason-code families are:

- movement/ETA: `driver_unexpected_stop`, `driver_moving_away_from_pickup`,
  `pickup_eta_materially_increasing`, `rider_wait_exceeds_prediction`,
  `repeated_route_recalculation`, `prolonged_traffic_standstill`,
  `unexpected_route_deviation`;
- data/connectivity: `driver_device_offline`, `rider_device_offline`,
  `driver_location_stale`, `rider_location_stale`, `gps_low_confidence`,
  `location_observations_conflict`, `communication_delivery_failed`;
- pickup/verification: `pickup_locations_diverge`, `airport_zone_confusion`,
  `pickup_verification_repeated_failure`, `pickup_guidance_low_confidence`;
- lifecycle/reservation: `lifecycle_progress_stalled`,
  `scheduled_reliability_degrading`, `predispatch_transition_unrealistic`;
- platform/provider: `backend_event_lag`, `worker_delay`, `map_provider_unavailable`,
  `eta_provider_unavailable`; and
- protective context: `verified_external_delay`, `weak_network_observed`,
  `insufficient_fresh_evidence`, `stability_margin_not_met`.

Reason codes describe evidence, not responsibility. Verified traffic, road closure,
weather, emergency, weak network, map/provider or AYO platform failure must add a
protective context and cannot silently reduce driver reliability or create a hidden
rider/driver punishment signal. Protected characteristics and proxies for them are
prohibited inputs.

Rules specify minimum evidence, freshness, material threshold, observation duration,
hysteresis/stability margin, cooldown, maximum notification frequency, expiry and
recovery threshold. Escalation generally requires consecutive or sustained evidence;
one noisy observation moves to `WATCH` or `INSUFFICIENT_DATA`, not accusation. A higher
level is retained only until stable recovery evidence crosses a separately configured
exit threshold. Notification deduplication uses ride, public reason family, recipient
and policy window; material worsening may bypass cooldown once.

Approved recommendation values are `refresh_eta`, `request_location_observation`,
`recommend_clearer_pickup`, `notify_rider_verified_delay`,
`notify_driver_pickup_confusion`, `prepare_reassignment`,
`suppress_low_confidence_predispatch`, `alert_operations`,
`prepare_support_context`, `prepare_recovery_evidence` and
`request_human_safety_review`. Recommendations cannot execute themselves. Dispatch or
Scheduled Dispatch independently validates any preparation/activation; the Active Ride
Orchestrator validates lifecycle actions; Safety owns human review; Notification owns
delivery policy. “Prepare reassignment” must not revoke or replace a driver.

Proposed public/internal events are `ride_confidence_evaluated`,
`ride_confidence_level_changed`, `ride_confidence_recommendation_created`,
`ride_confidence_recommendation_expired`, `ride_confidence_alert_suppressed`,
`ride_confidence_recovered` and `ride_confidence_data_insufficient`. Only role-appropriate
plain-language outcomes reach clients. Privacy-safe audit records contain opaque ride,
decision, rule/reason and action references without raw location or communication data.

Failure is fail-open for ride creation and normal lifecycle progress: unavailable or
expired confidence output becomes `INSUFFICIENT_DATA`; normal domain authorities
continue. A governed future AI strategy may receive the same versioned snapshot in
shadow mode, emit non-executing comparisons, and never replace deterministic production
classification until a separate mission approves evaluation, fairness and activation.

## 9. Pickup and trip verification

### Default layered flow

1. Rider/passenger checks first name, photo, plate, vehicle and approved accessibility
   attributes against the assigned-driver projection.
2. Server issues a short-lived, ride/assignment/attempt-bound PIN challenge to the
   passenger channel; store only a protected verifier, never plaintext logs.
3. Driver enters the passenger-provided PIN. Server rate-limits attempts, uses constant-
   behavior public errors, invalidates on success/expiry/reassignment and records audit.
4. Server issues `pickup_verified`; only then can `start_trip` be authorized.

The PIN is not shown to the driver before entry. It is sufficiently random for the
configured length, short-lived, single-use, assignment-bound and protected by attempt
limits/cooldown. Reassignment always rotates it. QR encodes a signed opaque challenge,
not identity or phone data, and is an optional camera-accessible convenience.

Fallbacks are policy-controlled, stepped up and auditable:

- verbal confirmation uses a fresh support-mediated challenge, not phone-number digits;
- no-smartphone/assisted passengers receive a code through their verified contact or
  an authorized call-centre session;
- a third-party booker cannot silently verify pickup remotely unless explicitly
  authorized for an assisted passenger and presence/risk checks pass;
- accessibility mode offers large type, screen-reader labels, voice prompts and a
  support-assisted path without weakening authorization;
- weak network keeps the challenge visible to the passenger but verification remains
  pending until server confirmation.

Repeated guessing, mismatched device/session, improbable location, changed assignment
or suspicious velocity invokes lock/reissue or human support. No client “start” event,
GPS proximity alone or QR scan alone is sufficient authority.

## 10. Cancellation, no-show and recovery design

UI collects a typed observable reason; the server records evidence separately from the
eventual responsibility class:

- rider responsibility;
- driver responsibility;
- AYO/platform responsibility;
- verified external disruption;
- shared responsibility; or
- insufficient evidence.

| Scenario | Immediate experience | Evidence/recovery boundary |
|---|---|---|
| Rider cancels before assignment | Confirm and end search promptly | No assumed fee; dispatch cancels pending offers atomically |
| Rider cancels after assignment | Show driver en-route context and future-policy placeholder | Preserve assignment, timing/contact evidence; pricing/recovery extension only |
| Driver cancels | Rider sees replacement search or clear terminal outcome | Typed reason; external causes protect driver; automatic reassignment bounded |
| Cannot reach/unsafe pickup | Offer safer pickup guidance or support | Map/location confidence, contact attempts and safety reason; no forced approach |
| Rider no-show | Server timer, bounded contact attempts, evidence review | Driver cannot self-award fee; passenger privacy retained |
| Breakdown | Reassign and give calm status | Driver fault is not presumed; recovery recommendation seam |
| Road closure/emergency | Safer pickup/recovery or cancellation | External disruption classification; no hidden penalty |
| Platform failure | Restore snapshot and reconcile commands | AYO responsibility candidate, incident reference, no fabricated completion |
| Scheduled failure | Mission 16 recovery then active-ride transfer if assigned | Reservation and ride histories remain linked, not merged |

Future `PricingConsequenceEvaluator`, `FinancialAdjustmentPort` and
`RecoveryRecommendationPort` consume an immutable incident/evidence reference and
return a separate authorized result. Until approved, screens say consequence is pending
or no fee policy is available; they never promise refund, fee or compensation.

## 11. Airport and premium experience

Two journey templates cover City → Airport and Airport → City; service levels are
Airport Standard and Airport Premium. Before request, compare vehicle/service attributes,
price explanation, reliability features, luggage/accessibility suitability and estimated
pickup/arrival range. Premium means only leadership-approved concrete service attributes,
not an unsupported guarantee.

Before formal assignment, show “AYO is preparing your airport ride” and an estimate—
never a driver identity. After assignment, show actual driver, vehicle and updated ETA.
Airport pickup adds terminal/zone, entrance/landmark, walking guidance, meeting-point
confirmation and low-data text instructions. City-to-airport emphasizes leave time and
destination terminal confirmation.

`FlightContextPort`, `AirportZonePort`, `RoutingPort` and `PickupGuidancePort` are
provider-neutral. Flight data is freshness-labelled context, not truth that silently
changes a reservation. Delayed flight, stale/unknown status and missed pickup produce
versioned notices, reconfirmation or Mission 16 recovery. Waiting windows and their
consequences remain leadership/airport-operations decisions. Booker/passenger views
follow Mission 16 minimum disclosure.

Reliability measures: airport-zone validation, conservative ETA range, commitment
status, context freshness, explicit meeting instructions, reassignment notice and fast
support handoff. AYO must validate Bole terminal/pickup operations locally before launch.

## 12. Maps and navigation boundary

Contracts expose provider-neutral typed results:

- `LocationObservation` (coarse/exact authorization, accuracy, source, observed/received
  time, spoof-risk reference and expiry);
- `RoutePreview` (polyline reference, distance/time range, version/freshness);
- `DriverApproachProjection` and `TripProgressProjection`;
- `PickupGuidance` (entrance, side-of-road, verified/recommended/restricted status,
  accessibility and localized text);
- `AirportZoneContext`; and
- `CachedMapManifest` with bounded region/version/expiry.

Map providers supply tiles/geocoding/routing through adapters. AYO owns place identity,
pickup classification, local entrance guidance, confidence, policy and fallbacks.
When maps fail, textual place/landmark, driver/rider status, direction/distance range and
support remain usable. Cached state is visibly timestamped and never portrayed as live.
Exact location is disclosed only during the necessary ride phase and retained according
to an approved policy; decorative “nearby cars” cannot expose real driver positions.

### Dynamic Pickup Intelligence

Mission 18 expands Smart Pickup through a deterministic **Dynamic Pickup Intelligence**
layer. It recommends the safest *verified*, clearest, most accessible and operationally
feasible pickup—not a guaranteed-safe location—and never changes canonical pickup or
ride state itself. The Active Ride Orchestrator consumes recommendations; Dispatch may
consume pickup feasibility but remains assignment authority; Scheduled Dispatch may
consume pickup reliability and airport context.

Provider-neutral inputs may include approved map and legal-access data, road direction,
walking burden, driver approach, congestion, temporary closures, terminal/curb rules,
zone capacity, accessibility needs, verified lighting/safety context, aggregated
successful-pickup evidence, location confidence, local operations guidance, event or
emergency restrictions and versioned cached guidance. Every input carries provenance,
observed/effective time, expiry and confidence. No provider or operations assertion is
unquestionable truth.

The versioned output is:

```text
PickupRecommendation {
  recommendation_id
  ride_or_reservation_id
  policy_id
  policy_version
  primary_pickup_place
  fallback_pickup_place?
  localized_walking_instructions
  localized_driver_approach_guidance
  entrance_or_gate_name?
  terminal_or_zone?
  walking_time_estimate_range?
  confidence_level
  reason_codes[]
  source_freshness[]
  generated_at
  expires_at
}
```

Pickup confidence is `VERIFIED`, `HIGH`, `MEDIUM`, `LOW` or
`INSUFFICIENT_DATA`. `VERIFIED` means the place/rule and effective window were approved
by an authorized source; it does not promise live access or safety. Proposed reason
codes include `verified_pickup_zone`, `legal_road_access`,
`aligned_driver_approach`, `reduced_crossing_risk`, `reduced_walking_burden`,
`accessible_route_available`, `entrance_confirmed`, `terminal_context_fresh`,
`congestion_aware_fallback`, `temporary_closure_avoided`,
`historical_pickup_success_aggregated`, `locations_on_divided_road`,
`entrance_ambiguous`, `accessibility_conflict`, `zone_capacity_constrained`,
`source_stale`, `provider_unavailable` and `cached_guidance_only`.

This applies to airports, shopping centres, hotels, hospitals, schools, apartments,
stadiums/events, transport terminals, gated communities, closures and complex roadside
pickups. Rules minimize walking subject to legal access, safety and accessibility;
accessibility needs can prohibit an otherwise shorter walk. Recommendations never direct
people into prohibited or unverified unsafe areas.

A material change is never silent. The server proposes the new point, explains the
public reason and walking/approach effect, sends the same version to authorized rider and
driver views, and requires policy-approved confirmation before the Active Ride
Orchestrator changes pickup. Repeated changes are capped; marginal oscillation is
suppressed by distance/time materiality and stability margins. If confirmation or fresh
data is unavailable, keep the last confirmed pickup and show the fallback or support.

Historical learning is deterministic aggregation of confirmed successful pickup
outcomes with minimum cohort size, bounded retention, provenance and operations review;
no personal route history or protected characteristic is exposed. This is not AI.

Airport behavior adds terminal-aware pickup, city-to-airport drop-off entrance,
airport-to-city zone selection, congestion-aware fallback, walking-time range, delayed-
flight context, driver staging/queue compatibility, premium guidance, third-party
traveller instructions and a reduced-data sharing projection. Airport policies are
separately versioned and locally verified. Without a fresh verified airport/operations
source, AYO labels guidance cached/uncertain and never claims live curb access.

`PickupIntelligencePort` composes replaceable `MapDataPort`, `RoutingPort`,
`TrafficContextPort`, `AirportZonePort`, `VenueOperationsPort` and cached adapters. AI
Support may explain the authorized public recommendation; Customer Recovery may later
consume immutable confirmed pickup-failure evidence. Neither can silently alter it.

Proposed events are `pickup_recommendation_created`,
`pickup_recommendation_material_change_proposed`,
`pickup_recommendation_change_confirmed`, `pickup_recommendation_change_declined`,
`pickup_recommendation_fallback_selected`, `pickup_recommendation_expired` and
`pickup_guidance_degraded`.

## 13. Support and safety entry points

Every active screen has a consistent Safety button and Help entry. The secure backend
creates a purpose-scoped handoff containing actor, ride reference, lifecycle version,
selected issue and minimum recent evidence references—not raw history or chat content.

- **Safety:** local emergency-service action (after Ethiopian operational/legal review),
  AYO safety case, trusted-contact trip share and discreet incident report.
- **AI support chat/voice:** labelled future/unavailable until separately approved;
  deterministic help/human fallback always visible.
- **Human escalation:** creates/routes a support case; never exposes restricted queues.
- **Lost item:** post-completion case with masked relay and expiry.
- **Recovery:** opens a case/recommendation request after a confirmed service failure;
  no automatic refund or blame.

Trip-share grants are short-lived, revocable, read-only and show a reduced projection.
They use high-entropy capability plus access controls, exclude contact/payment/support
notes, stop precise updates at the approved terminal point and are audited.

## 14. Accessibility, language and performance

- English and Amharic use semantic message keys, plural/date/number rules and layout
  tests; no concatenated sentences. Future languages are additive.
- Minimum 48dp touch targets, scalable text without clipping, logical focus order,
  screen-reader state announcements, non-colour status cues and WCAG-aligned contrast.
- Primary controls remain reachable one-handed; motion is optional/reduced and no
  safety meaning depends on animation.
- Driver moving mode uses glanceable high-contrast cards and voice/haptic prompts;
  complex interaction is parked-only.
- Low-data mode reduces map refresh/polyline detail and batches location while preserving
  lifecycle events, text status and verification.
- Render from local projection immediately, then reconcile; bounded caches and list
  sizes protect memory. No continuous decorative animation or high-frequency polling.
- No-smartphone and assisted flows receive equivalent status/consent through future
  provider-neutral channels and support sessions, not weaker identity assumptions.

Proposed lab targets (not production SLOs): cached active screen interactive within
1.0 s and cold authorized projection within 2.5 s at p95 on the oldest supported test
device; lifecycle update visible within 2 s p95 on healthy foreground transport and
within 10 s p95 on polling fallback; reconnect snapshot convergence within 5 s p95 on
recoverable 3G; command acknowledgement within 3 s p95; no duplicate authoritative
transition under retry. Field baselines and device/network matrix must validate targets.

## 15. Privacy and security threat model

| Threat | Control | Residual/approval need |
|---|---|---|
| Forged state/event | TLS, authenticated stream, server sequence/version, allow-listed schemas; clients never author events | Device compromise remains |
| Command replay | Actor/resource binding, idempotency, nonce/expiry, expected version and audit | Offline authority deliberately excluded |
| Unauthorized ride view | RBAC/ABAC ownership, participant purpose, short-lived stream auth, revocation | Support break-glass policy required |
| Account takeover | Existing session/device controls; step-up for participant/contact/share changes | Authentication policy remains Mission 14 authority |
| PIN guessing/replay | Protected verifier, random short-lived assignment-bound code, limits/rotation | Exact length/limits need safety testing |
| Fake GPS/spoofing | Accuracy/freshness, server plausibility and multi-signal risk; never sole proof | Signals inform review, not automatic punishment |
| Location overexposure | Phase/role-based precision, minimization, coalescing, retention limit | Ethiopian privacy review required |
| Masked-relay abuse | Ride-scoped expiring alias, rate limits, recording/consent policy gate | Provider not selected |
| Screenshot leakage | Minimize displayed data, obscure selected sensitive views in app switcher where platform permits, warn rather than promise prevention | OS/other-camera capture cannot be prevented |
| Third-party privacy | Separate booker/passenger/payer/contact roles and projections | Consent/support policy approval needed |
| Support insider access | Purpose-scoped case, queue permission, field redaction, audited break-glass | Staffing/monitoring required |
| Stream exhaustion | Connection quotas, bounded replay, backpressure, heartbeat/idle expiry | Load test before activation |

Never log tokens, PINs, full phone numbers, exact unnecessary locations, raw route
histories, private support content, payment credentials or unrestricted third-party data.
Metrics use opaque IDs, bounded dimensions and aggregation thresholds.

## 16. Observability and product metrics

Metrics are split by service type, city/zone, app/version, language, device capability
band and network class only where privacy/fairness review permits and sample sizes are
safe. They do not use protected characteristics for dispatch or pricing.

- request-to-assignment and assignment-to-arrival duration;
- pickup and verification success/failure/lockout;
- rider/driver cancellation by public reason and evidence class;
- no-show, reassignment and no-driver outcomes;
- reconnect success/time, replay gap, snapshot resync and stale-event rejection;
- screen-load and command acknowledgement/failure/indeterminate rates;
- location/ETA freshness and polling/stream data use;
- support/safety contact rate and resolution handoff;
- trip start/completion and incomplete-trip recovery;
- rider/driver rating completion and privacy-safe satisfaction trends;
- airport on-time assignment/arrival, zone-guidance success and recovery rate.
- rides by confidence level and duration in `WATCH`, `AT_RISK` or `CRITICAL`;
- issue detected before support contact, warning-to-recovery success and reassignment
  preparedness without activation;
- confidence false-positive/appeal rate, stability/cooldown suppression and stale-data
  suppression;
- rider/driver notification usefulness, confidence-related support-contact reduction,
  airport pickup-risk detection and weak-network recovery;
- pickup recommendation acceptance, material-change frequency, fallback use,
  accessibility rejection and successful pickup by recommendation confidence.

Structured operational logs include correlation, opaque ride/event/command IDs, state
transition/reason code, sequence/version, adapter and result. Alerts target stuck active
states, sequence lag, verification abuse, assignment/arrival deterioration, outbox lag
and authorization anomalies without exposing personal data.

## 17. Testing and simulation plan

### Automated layers

- exhaustive domain transition/property tests and illegal-transition tests;
- rider/driver projection contract and cross-role privacy tests;
- event reorder, loss, duplicate, gap, stale version and unknown-schema tests;
- idempotent/concurrent commands, offer-expiry races and cancellation/reassignment races;
- reconnect, app kill/restart, token expiry/revocation and polling/stream failover;
- stale/spoofed GPS, map outage, ETA confidence and cached guidance;
- PIN/QR expiry, replay, guessing, reassignment rotation, assisted and no-smartphone flow;
- no-show evidence, unsafe pickup, breakdown, platform/external disruption classification;
- immediate, scheduled, third-party, diaspora, pre-dispatch and airport matrices;
- current-passenger protection and ordinary-offer decline without hidden penalty;
- screen-reader, large text, contrast, reduced motion, Amharic expansion and one-handed use;
- supported oldest Android, memory/battery/data, 2G/3G loss/latency and clock drift;
- RBAC/ownership, IDOR, rate/size abuse, stream hijack, replay and log privacy;
- high-concurrency fan-out, hot ride/driver, bounded replay/backpressure and restart recovery.
- confidence replay determinism, level hysteresis, false-positive suppression, expired
  decisions, stale-data downgrade and notification-frequency bounds;
- driver moving away, prolonged stop, ETA growth, device offline, backend/worker lag and
  provider-outage confidence scenarios with protective external-delay attribution;
- rider/driver opposite sides of a divided road, shopping-centre entrance ambiguity,
  inaccessible recommendations and repeated pickup-change oscillation;
- airport-zone closure and congestion fallback without an unsupported live-policy claim;
- map outage and weak-network cached guidance with visible freshness warnings;
- two-device material pickup correction: proposed to both, confirmation, one canonical
  transition and deterministic rejection of stale recommendation versions;
- operational recovery after failed pickup, including confidence evidence handoff without
  automatic blame, cancellation, refund or fare change.

### Synthetic two-device acceptance simulation

With synthetic identities and authoritative database/outbox:

```text
rider requests
-> driver receives versioned offer
-> driver accepts idempotently
-> both snapshots converge on assignment
-> driver reaches pickup
-> passenger supplies assignment-bound PIN
-> server verifies and authorizes trip start
-> ordered progress reaches both clients through different transports
-> driver requests completion
-> server final state and separate fare/earnings projections reach both
-> receipts/ratings become available without private/internal data leakage
```

Repeat with reordered/duplicate events, dropped stream, app restart, delayed push,
polling only, reassignment during approach, stale GPS, PIN replay, cancellation race and
server restart. Compare final database, audit, outbox, both client projections and command
receipts for one convergent outcome.

### Benchmark and readiness targets

- projection generation p95 < 50 ms in service-level benchmark;
- bounded replay of 100 lifecycle events p95 < 100 ms excluding network;
- 10,000 candidates are not fanned to clients; one ride projection remains bounded;
- zero cross-role private fields in schema snapshots;
- zero duplicate canonical transitions across retry/concurrency suites;
- 100% legal state-machine edge coverage and required accessibility task completion;
- transport soak demonstrates bounded memory, reconnect jitter and no polling herd.

These are architecture acceptance targets, not claimed results or production SLOs.

## 18. Research and competitor comparison

Sources were accessed 2026-07-16. Product availability varies by market; public pages do
not reveal private architecture. Complaints are hypotheses for Ethiopian testing, not
verified platform-wide facts.

### Verified public behavior

- Uber publicly describes driver/vehicle details before pickup, GPS trip tracking,
  masked communication, PIN verification, trip sharing, RideCheck and in-app safety
  access. Its help page says a correct PIN gates trip start where enabled.
- Bolt publicly describes pickup codes, masked numbers, trip sharing/support and a
  scheduled driver workflow with readiness, arrival and waiting steps. Its cancellation
  help shows rules vary by city and emphasizes notification of consequences.
- Yango publicly describes driver profile verification, a ride safety centre, PIN
  matching, SOS/route sharing, real-time offers and earnings/navigation in its driver app.
- DiDi's public filings describe before/during/after safety protocols, emergency contacts,
  real-time trip sharing and post-trip ratings; they do not expose its client sync design.
- RIDE's public store/site material advertises app or dispatch-centre booking,
  pre-booking, airport use and 24/7 service.
- Feres publicly documents app plus call-centre access, driver approach tracking,
  driver/vehicle details, GPS tracking, multiple payment choices and ratings.
- Public Lyft/Grab material was not sufficiently accessible in this research pass to
  verify detailed current market behavior; their architectural internals remain unknown.

### Architectural inference and complaint evidence

Live maps and notifications imply event delivery but do **not** prove competitors’
consistency, transport or database design. Public user commentary in Ethiopia reports
friction when drivers call for verbal landmark directions and concerns about airport
pickup/overcharging; these are anecdotal signals requiring structured local research.

### AYO recommendation and improvement opportunity

AYO should combine the strongest visible patterns—identity/vehicle match, pickup code,
live status, masked contact, sharing and persistent safety access—with explicit snapshot
recovery and low-data text guidance. AYO improves transparency by distinguishing
“sending” from “confirmed,” driver change from ETA change, estimated from final money,
and operational evidence from fault. It protects drivers through typed external-delay
classification and no hidden decline penalty, and treats assisted/diaspora passengers
and airport meeting guidance as first-class rather than exceptions.

No competitor claim authorizes AYO policy. Cancellation fees, destination disclosure,
wait windows, emergency operations, premium promise and data retention need Ethiopian
field, legal and leadership validation.

### Research sources

- [Uber safety commitment](https://www.uber.com/us/en/safety/our-commitment/),
  [rider safety](https://www.uber.com/us/en/ride/safety/) and
  [Verify Your Trip](https://help.uber.com/riders/article/what-is-verify-your-trip?nodeId=9a2a4bc6-002b-4461-8e9e-8ea29974795d).
- [Bolt rider safety](https://bolt.eu/en/rides/safety/),
  [pickup-code support](https://bolt.eu/en/support/articles/33400/),
  [scheduled driver workflow](https://bolt.eu/en-cy/support/articles/7769413257746/)
  and [cancellation support](https://bolt.eu/en/support/articles/360019447640/).
- [Yango Safety Centre](https://yango.com/en_int/news/yango-ride-rolls-out-new-in-app-safety-centre-across-25-markets),
  [rider safety](https://yango.com/en_int/lp/safety/latam/rider/) and
  [driver app](https://yango.com/en/driver/).
- [DiDi Global 2026 Form 20-F](https://ir.didiglobal.com/static-files/f1804651-ad87-4bcf-9053-2b80f643a372).
- [RIDE official website](https://ride8294.com/) and
  [Google Play driver listing](https://play.google.com/store/apps/details?id=com.multibrains.taxi.driver.ridepassengeret).
- [Feres official website](https://feres.et/Home).
- [RFC 6455 WebSocket](https://www.rfc-editor.org/info/rfc6455/),
  [WHATWG Server-Sent Events](https://html.spec.whatwg.org/dev/server-sent-events.html),
  [Android network/battery guidance](https://developer.android.com/develop/connectivity/network-ops/network-access-optimization)
  and [Firebase messaging delivery behavior](https://firebase.google.com/docs/cloud-messaging/android/receive-messages).

Future validation should add direct Lyft/Grab evidence and moderated Ethiopian
rider/driver, airport, accessibility and call-centre studies.

## 19. Options and recommendation

| Approach | Cost/complexity | Reliability and scale | Customer/driver effect | Security/vendor fit |
|---|---|---|---|---|
| Poll raw status only | Low initially | Poor convergence semantics; wasteful at low latency | Ambiguous retries/reassignment | Neutral vendor but unsafe authority mapping |
| Provider-specific real-time SDK | Medium; recurring vendor cost | Fast path but provider outage/lock-in | Good when healthy, weak fallback risk | External trust/data decision premature |
| **Provider-neutral snapshot/events/commands with staged transports** | Medium | Durable recovery, bounded replay, horizontal path | Clear pending/confirmed/offline behavior | Recommended; transport replaceable and least-data |
| Separate real-time microservice now | High | Scalable but unmeasured operational burden | No proven UX gain over modular boundary | Premature failure/security surface |

Recommendation: approve the provider-neutral model and staged HTTPS → foreground stream
→ wake-up push path. Revisit transport/provider or service extraction only after measured
foreground update latency, reconnect failure, concurrent connections, outbox lag or cost
breaches an approved threshold.

## 20. Risks and edge cases

| Risk | Likelihood/impact | Mitigation/verification | Residual owner |
|---|---|---|---|
| Screen and server diverge | Medium/High | Versions, sequence gaps, snapshots, two-device simulation | CTO |
| Weak network causes unsafe assumption | High/High | Explicit pending state; high-risk commands need confirmation | CTO/Product |
| Driver distraction | Medium/High | Moving-mode controls/voice and parked-only tasks | Safety/Operations |
| Wrong passenger/stolen ride | Medium/High | Layered match + assignment-bound PIN + limits | Safety |
| Unfair cancellation classification | Medium/High | Separate observation/responsibility; human review and appeal | CEO/Operations |
| Airport promise exceeds operations | Medium/High | Concrete service attributes and local validation | CEO/Airport Ops |
| Location privacy leakage | Medium/High | Role/phase precision, minimization, expiry, tests | Privacy/Legal |
| Stream capacity/cost spike | Medium/Medium | Bounded connections/replay, adaptive polling, load gates | CTO |
| Amharic/accessibility confusion | Medium/High | Professional language and disabled-user field testing | Product/Operations |
| Prototype-state migration defect | Medium/High | Compatibility mapping, characterization and rollback | CTO |

No critical risk is accepted for implementation by this document. Safety operations,
privacy/retention and user-facing policy values must be resolved before activation.

## 21. Staged implementation plan (requires new approval)

1. **Contract and compatibility foundation:** canonical Active Ride aggregate, prototype
   status translator, role projections, command/event schemas and exhaustive tests.
2. **Rider/driver core UI with HTTP recovery:** local projection store, snapshots,
   idempotent commands, adaptive polling, assignment through completion, accessibility.
3. **Pickup/cancellation/recovery controls:** PIN/assisted verification, typed evidence,
   no-show and reassignment experiences; no financial consequences.
4. **Foreground real-time adapter:** WebSocket pilot against the transport contract,
   reconnect/load/battery proof; retain polling.
5. **Airport/premium and scheduled handoff:** approved service attributes, zone guidance,
   third-party projections and pre-dispatch display.
6. **Separately approved providers/activation:** maps, masked relay, push wake-up and
   operational safety/support only after research, contracts and privacy review.

Each stage runs the full workflow and stops at its own gate. Rollback disables the new
feature/transport and returns clients to compatible snapshot polling; authoritative
history is never deleted or rewritten.

## 22. Decisions required at review gate

CTO review is requested for the Active Ride ownership boundary, lifecycle, compatibility
translation, sequence/snapshot model, staged transport, offline command limits,
verification controls, privacy model and scale targets.

CEO/leadership decisions are required for:

- driver destination/expected-duration disclosure by market and service;
- cancellation/no-show waiting and future consequence communication;
- Airport Standard/Premium concrete promise and waiting windows;
- pickup PIN default/risk policy and assisted-verification operations;
- trip-sharing defaults and emergency/support operating model;
- rating visibility/window and feedback policy;
- supported oldest Android tier and accessibility/language launch standard; and
- which performance/usability targets become launch gates.

Qualified Ethiopian legal/operations review is required for emergency wording/process,
location/contact retention, masked communications, call-centre consent, accessibility,
airport/terminal operations, transport obligations and any future fee/refund policy.

## 23. Architecture evaluation

The proposal has a credible 10-million-user path through ride-scoped sequences, bounded
replay, coalesced location, backpressure, horizontally scalable stateless delivery and
extractable contracts. It survives provider outage through snapshots/polling, is secure
by default, observable and testable, and can replace transports without rewriting ride
authority. It is more complex than raw polling only where needed to prevent ambiguity,
duplication and unsafe state. No deployment or scale claim is made.

Mission 18 stops here for CTO/CEO architecture review.
