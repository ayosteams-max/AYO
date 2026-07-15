# AYO Immediate Dispatch Architecture Proposal

Status: **CTO and CEO approved on 2026-07-15 for Mission 12 immediate-dispatch implementation.**
Mission: 11 design package, bounded to architecture, contracts, wireframes, state machines, security, database design and technical documentation.
Date: 2026-07-15

## 1. Executive recommendation

Build immediate dispatch as a server-authoritative module in AYO's approved modular monolith. Accept each rider command idempotently, persist the ride and state history atomically, publish work through a transactional outbox, find candidates in bounded stages, reserve one driver atomically, and expose a versioned rider-safe status projection. Use deterministic, explainable matching first. Preserve a versioned `DispatchStrategy` boundary so future statistical or ML ranking can be evaluated in shadow mode and safely replaced without changing ride, offer, mobile or persistence contracts.

This is the strongest long-term architecture because it solves today's reliability problem without premature microservices or AI infrastructure, while preserving clear extraction points for the future. It follows AYO's permanent priorities: closest suitable available driver, fast pickup, fair driver opportunity, staged geographic filtering before paid routing, server-authoritative financial/state data, simple UI, weak-network recovery and independently scalable modules.

The client must not construct an authoritative ride. It sends intent. The server owns the public ride ID, accepted timestamp, rider identity, quote/fare reference, location snapshots, state, ETA provenance and dispatch outcome.

## 2. Authority and approval status

The CTO approved this architecture and the CEO gave final approval on 2026-07-15. The CEO also approved roadmap resequencing: Mission 12 is immediate-dispatch implementation and Mission 13 is scheduled-ride dispatch/pre-dispatch. Mission 12 expressly excludes scheduled rides and pre-dispatch. Irreversible database migration, payments and security-sensitive production activation remain separate stop gates.

This package deliberately spans concepts otherwise sequenced across Roadmap Missions 6–9 and 11. Approval must either preserve those prerequisite missions or explicitly authorize a bounded vertical-slice sequence. It must not silently treat the current synchronous prototype as the production baseline.

## 3. Research comparison

### 3.1 Evidence table

| Operator | Verified public evidence | Useful lesson for AYO | Limitation |
|---|---|---|---|
| Uber | Public marketplace material says closest is not always quickest, describes traffic/geographic constraints and batched matching that reduces system-wide wait; its rider-session engineering models explicit request/dispatch event state. | Optimize routed pickup time and marketplace outcome, keep explicit lifecycle state, and consider batching only after measurement. | Global-scale design and claims do not establish Ethiopian launch thresholds. |
| Grab | Engineering material frames allocation as fast rider fulfillment plus better driver livelihood in continuously changing supply/demand. | Measure rider and driver outcomes together; do not optimize rider latency by creating excessive driver deadhead or poor offers. | Published evidence is conceptual and from mature Southeast Asian markets. |
| Bolt | Privacy material says matching may use ETA, proximity, historical activity and driver preferences; it may suppress immediate rematches after rejection/cancellation. Public policy ties some cancellation fees to driver effort and provides review. | Separate eligibility/preferences from ranking, prevent rejection loops, compensate material driver effort, and make policy explainable/appealable. | Rules vary by country; none are approved for Ethiopia or AYO. |
| Lyft | Public material explains ETA-driven matching, real-time and historical ETA signals, eligibility filtering such as EV range, mutual blocking/favorite-driver concepts, and research on exclusive versus non-exclusive notification tradeoffs. | Accurate ETA is foundational; hard eligibility precedes ranking; notification fan-out needs contention and driver-locking controls. | Some evidence concerns scheduled rides, EVs or research simulations, not AYO's launch case. |
| Yango Ethiopia | Official pages advertise in-app and phone booking, cash/digital options, real-time tracking, advance price visibility and driver/vehicle details. Its Addis phone service works without internet. | Treat assisted booking and cash as first-class Ethiopian access paths; keep rider status understandable across app/SMS/call-center channels. | Marketing pages disclose no matching algorithm, fairness method or internal reliability data. |
| RIDE 8294 | Official site/store listings advertise app plus dispatch-center booking, Addis operations, cash-oriented service and a large driver network. | An assisted dispatch channel and human recovery path are locally relevant; operational scale claims must be independently verified. | Driver-count and service claims are self-published; dispatch internals and measured outcomes are not public. |
| Feres | Official pages advertise app plus 6090 call center, driver/car details, tracking and multiple payment methods. Published terms describe conditional cancellation fees and exemptions for driver delay. | Preserve assisted access, transparent cancellation preview and driver-late/platform-failure exemptions. | Technical architecture, matching and reliability metrics are not public; terms may not reflect current Ethiopian operations without local verification. |

Primary references:

- Uber matching: <https://www.uber.com/jm/en/marketplace/matching/>
- Uber marketplace principles: <https://www.uber.com/us/en/marketplace/principles/>
- Uber rider session state: <https://www.uber.com/en-GB/blog/sessionizing-data/>
- Grab allocation: <https://engineering.grab.com/understanding-supply-demand-ride-hailing-data>
- Bolt driver privacy/matching: <https://bolt.eu/en-az/privacy/rides/privacy-for-drivers/>
- Bolt marketplace guidelines: <https://bolt.eu/en/legal/rides/marketplace-guidelines-passengers/>
- Lyft ETA and matching: <https://www.lyft.com/blog/posts/how-lyft-uses-ai-to-get-you-where-you-want-to-go-faster>
- Lyft safety/mutual non-rematching: <https://www.lyft.com/blog/posts/lyfts-commitment-to-safety>
- Lyft collaborative notification research: <https://arxiv.org/abs/2603.21531>
- Yango Ethiopia: <https://yango.com/en_et/> and <https://yango.com/en_et/rider/calltaxi/>
- RIDE 8294: <https://ride8294.com/> and <https://ride8294.com/ride-for-passenger/>
- Feres: <https://feres.et/Home> and <https://feres.co/terms/user>
- GSMA Ethiopia connectivity context: <https://www.gsma.com/somic/wp-content/uploads/2025/09/The-State-of-Mobile-Internet-Connectivity-2025-Understanding-Mobile-Internet-Use-in-LMICs.pdf>

### 3.2 Why the AYO proposal is stronger for AYO

“Better” means better fitted to AYO's approved principles and measurable launch conditions, not a claim that AYO has already outperformed competitors.

- It makes no hidden client, AI or provider result authoritative.
- It optimizes closest **suitable** driver through routed pickup ETA, but adds explicit rider-age and driver-opportunity guardrails rather than opaque popularity or acceptance-rate punishment.
- It uses cheap PostGIS/geographic filtering before paid route matrices, controlling cost and provider exposure.
- It treats app retry, process death, SMS/call-center recovery, cash and weak connectivity as normal Ethiopian conditions.
- It records policy/model versions and bounded reason codes for every offer and assignment.
- It avoids premature broadcast matching, ML, Redis, brokers and microservices, while defining evidence-based migration triggers.
- It separates product policy from code: cancellation amounts, offer windows, radii, weights and safety promises remain versioned leadership configuration after field measurement.

## 4. Domain boundaries

Keep one deployable modular monolith initially with enforced internal contracts:

| Module | Owns | Must not own |
|---|---|---|
| Ride | Ride aggregate, rider-visible lifecycle, command idempotency, state history and current assignment reference | Candidate ranking internals, provider credentials, client identity claims |
| Dispatch | Dispatch cycle, candidate stages, offer lifecycle, reservations, assignment decision, policy version and reason codes | Rider fare authority, driver verification source, raw payment data |
| Driver availability | Authoritative online/availability lease, last safe location reference, vehicle/capability eligibility and active-work constraint | Ride state or pricing |
| Maps/ETA | Provider-neutral routing, map matching, route matrix, freshness, confidence and provider/version evidence | Dispatch policy or final assignment |
| Pricing | Quote/fare, currency, expiry and rule version | Client display strings or dispatch ranking policy |
| Identity/authorization | Authenticated rider/driver/service identity and resource permissions | Ride commands inferred from caller-supplied IDs |
| Notification | Provider-neutral low-data offer/status delivery and receipts through outbox consumers | Assignment authority |
| Audit/operations | Privacy-safe decision evidence, overrides, incident and support views | Silent mutation of ride/offer history |

Extraction is allowed only after measured scaling, isolation, team-ownership or reliability evidence and renewed approval. Network calls between these modules are unnecessary initially.

## 5. Ride Request API proposal

### 5.1 Contract principles

- Base path: `/api/v1` for the future production contract. Preserve `/api` compatibility separately until an approved migration; never silently change the prototype.
- Authentication supplies the rider identity. No `rider_id` or `rider_name` is accepted from the body.
- Every command requires `Idempotency-Key`, scoped to authenticated actor + command + canonical request hash, with bounded retention longer than the maximum client retry window.
- Requests use stable server-issued references, not display strings or client-calculated money.
- Responses carry `ride_id`, `version`, server UTC timestamps and stable error/reason codes. Human text is localized client-side from approved codes.
- Creation returns `202 Accepted` after durable acceptance, not after finding a driver.
- Status reads are bounded, rider-safe projections; candidate queues, scores, precise driver locations and internal fraud flags never leave the server.
- Push/SMS is a hint. A versioned status read is authoritative.

### 5.2 Create request

`POST /api/v1/rides`

Headers:

| Header | Requirement |
|---|---|
| `Authorization` | Authenticated rider session |
| `Idempotency-Key` | 128+ bits of client-generated randomness, persisted before first send |
| `Accept-Language` | Optional UI preference; never policy authority |
| `X-Client-Version` | Bounded operational compatibility signal, privacy reviewed |

Conceptual request fields:

| Field | Rules |
|---|---|
| `pickup_place_id` | Server/provider-neutral place reference already validated for serviceability and Smart Pickup classification |
| `destination_place_id` | Server/provider-neutral destination reference |
| `service_type_code` | Versioned server catalog value such as the future canonical equivalent of AYO Go |
| `quote_id` | Unexpired server quote covering service type, locations, currency and pricing version |
| `client_request_created_at` | Optional diagnostic UTC time, never lifecycle authority; bounded skew and privacy-safe |

Conceptual `202` response fields:

| Field | Authority/use |
|---|---|
| `ride_id` | Opaque server UUID |
| `version` | Monotonic aggregate version |
| `status` | `SEARCHING` after accepted durable transaction/outbox |
| `accepted_at` | Server UTC timestamp |
| `pickup` / `destination` | Minimized immutable display snapshot plus non-sensitive reference |
| `service_type` | Validated code and localized display key |
| `quote` | ID, integer minor units, ISO currency, expiry and rule version; no float |
| `search_estimate` | Optional range/percentile with generated-at and confidence; absent when not calibrated |
| `pickup_eta` | Null until an assignment/candidate result is authoritative |
| `links` | Status and permitted command relations |

Duplicate same-key/same-body requests return the same semantic response. Same-key/different-body returns `409 IDEMPOTENCY_KEY_REUSED`. Unknown/expired quote returns a stable `409 QUOTE_EXPIRED` with a safe refresh link; it never silently reprices and submits.

### 5.3 Reads and commands

- `GET /api/v1/rides/{ride_id}`: authenticated owner/staff-resource check; supports `If-None-Match`/ETag using version.
- `GET /api/v1/rides/active`: returns at most the rider's permitted active ride projection and supports startup recovery.
- `POST /api/v1/rides/{ride_id}/cancellations`: idempotent command with approved reason code and expected ride version. Returns a cancellation preview/confirmation protocol if a fee could apply; exact API shape awaits policy approval.
- `GET /api/v1/rides/{ride_id}/events?after_version=N`: bounded rider-safe recovery feed. Prefer long-poll/SSE only after platform measurements; polling remains fallback.
- Driver offer accept/decline commands require authenticated assigned driver context, offer ID, offer version and idempotency key. The driver never supplies an authoritative ride/driver pairing.

Stable error groups include validation, authentication, authorization, stale version, quote expired, outside service area, pickup restricted, active ride conflict, temporary unavailable, no driver, rate limited and safe generic internal failure. Responses never echo sensitive coordinates, tokens, provider errors or fraud rules.

## 6. Server-authoritative request flow

```text
Authenticated rider command
  -> validate idempotency + active-ride invariant
  -> validate quote, service type, pickup/destination and policy versions
  -> transaction:
       create ride(UUID, accepted_at, SEARCHING, version=1)
       append ride state history
       store idempotency outcome
       append dispatch-requested outbox event
       append privacy-safe audit event
  -> commit
  -> return 202 rider projection

Outbox worker
  -> lease dispatch event
  -> create/continue versioned dispatch cycle
  -> bounded candidate pipeline
  -> offer/reservation transaction(s)
  -> assignment or bounded no-driver outcome
  -> outbox rider/driver status hints
```

The transaction is the acceptance boundary. Notification delivery, routing providers and AI never decide whether the ride exists. Workers are at-least-once; handlers are idempotent. Lease expiry enables recovery after worker death. Poison events move to an operationally owned failure state after bounded attempts; they are never dropped silently.

## 7. Dispatch engine

### 7.1 Dispatch cycle

Each immediate ride creates one active dispatch cycle per approved attempt sequence. A cycle stores policy version, current stage, deadline, attempt count and last safe outcome. It progresses through bounded stages:

1. Validate ride is still `SEARCHING`, quote/service area remains actionable and rider has not cancelled.
2. Obtain eligible driver IDs through a cheap indexed geographic query and active availability leases.
3. Apply hard eligibility and safety exclusions.
4. Request paid/provider routing only for the bounded shortlist.
5. Produce explainable scores under the active deterministic policy.
6. Atomically reserve the winning candidate if driver and ride remain available.
7. Create a time-bounded offer and notify the driver.
8. On decline/expiry/delivery failure, release reservation and progress without immediately rematching the same pair.
9. On authenticated acceptance, atomically assign driver + ride, close competing work and publish assignment.
10. If stages/deadline exhaust, transition to `NO_DRIVER_AVAILABLE` with reason family and rider options.

At most one current assignment and one active exclusive offer per ride are allowed initially. A driver has at most one active reservation/assignment incompatible with another ride. Non-exclusive/broadcast offers remain a future measured option because they add contention, distraction and fairness complexity.

### 7.2 Candidate funnel

```text
All availability leases
  -> service-area/geocell + freshness filter
  -> hard eligibility and active-work exclusion
  -> bounded nearest-by-straight-line shortlist
  -> route/ETA matrix for smaller shortlist
  -> deterministic score + fairness guardrails
  -> atomic reservation
  -> one time-bounded offer
```

PostGIS is the approved durable geospatial foundation. A coarse cell index/geohash/H3 accelerator may be added only after profiling and dependency review; it is not required to design the domain. Straight-line distance is a cheap prefilter, never final pickup ETA.

## 8. Driver matching and scoring

### 8.1 Hard filters before scoring

A driver must satisfy all applicable constraints:

- authenticated, active account and current operational verification;
- valid licence, vehicle, insurance and service-type capability under locally verified rules;
- online availability lease fresh within approved bounds;
- location fresh, plausible and within accuracy bounds;
- no incompatible active reservation, offer, assignment or trip;
- in the ride's service area and permitted pickup zone/time;
- no approved rider-driver safety block or serious unresolved restriction;
- device/app capability sufficient for the offer where required;
- fraud/risk decision does not require exclusion or step-up/manual handling.

Hard filters generate bounded reason codes and audit evidence. Protected characteristics, language, nationality, ethnicity, inferred wealth and willingness to accept lower pay are prohibited ranking inputs. Language may be an explicit rider accessibility requirement only after leadership/legal approval and must not become a proxy for protected status.

### 8.2 Deterministic launch score

Do not approve numeric weights until Ethiopian field data exists. Approve the structure and guardrails first. Recommended ordering:

1. Safety and serviceability gates (hard constraints, not weights).
2. Minimize routed pickup ETA among suitable drivers.
3. Prefer more reliable/fresher location and route evidence.
4. Apply bounded rider-wait aging so long-waiting riders are not perpetually displaced.
5. Apply bounded driver-opportunity correction among materially equivalent pickup outcomes.
6. Minimize deadhead distance/time and avoid sending drivers across barriers or restricted pickups.
7. Respect explicit driver service/destination preferences where product policy allows.
8. Stable randomized tie-break among genuinely equivalent candidates, seeded/audited to avoid identifier bias.

Conceptual score, not approved policy:

```text
candidate utility = pickup reliability/ETA quality
                  + bounded rider-age priority
                  + bounded driver-opportunity adjustment
                  - deadhead and uncertainty penalties
```

The engine records component bands and reason codes, not raw sensitive features in broad logs. Rating is not a general reward weight at launch: ratings are noisy and can encode bias. Use only an approved quality/safety eligibility threshold with minimum sample, decay, appeals and anti-retaliation controls. Do not punish rejected offers via an opaque acceptance-rate score. Declining is a driver choice; abuse is handled through separately approved evidence and policy.

### 8.3 Offer design

Offers should disclose policy-approved pickup area/distance/time, trip type, estimated trip information, payment method class and expected earnings information before acceptance. Exact destination disclosure, earnings components and timeout require CEO/CTO/legal/operations approval. Driver interaction must be safe while moving: large controls, audio/haptic signal, minimal reading, and no repeated high-distraction broadcast storm.

## 9. Two-sided fairness engine

Fairness is a guardrail and measurement system around dispatch, not one opaque score.

### Rider fairness

- Measure request-to-offer and request-to-assignment distributions by zone, time, service type, accessibility need and network condition.
- Never use protected characteristics or inferred ability to pay in dispatch priority.
- Age waiting requests within bounded stages so dense-zone throughput does not starve edge-zone riders.
- Do not promise identical wait times where supply differs; show honest uncertainty and no-driver outcomes.
- Audit service-area/pickup restrictions for geographic proxy discrimination and operational justification.

### Driver fairness

- Measure eligible online time, offers, acceptances, completed trips, deadhead, utilization and net earnings opportunity by comparable zone/time/service cohort.
- Track opportunity debt only among eligible drivers offering comparable pickup outcomes; never send a materially farther driver merely to equalize counts.
- Separate driver choice (decline) from platform opportunity. Do not covertly reduce future access because a driver rejected an unattractive offer.
- Apply cooldown/rematch suppression after declines/cancellations to avoid loops and coercive repeated offers.
- Provide reason categories and an appeal/human-review path for restrictions or material automated disadvantage.

### Guardrail governance

Before rollout define maximum permitted pickup-ETA degradation for fairness adjustment, minimum cohort size, privacy thresholds, disparity alert levels and rollback triggers. Compare shadow policies through simulation/replay, then controlled experiments. Leadership approves the tradeoff because it affects rider experience and driver livelihood.

## 10. State machines

### 10.1 Canonical ride aggregate

```text
REQUEST_ACCEPTED
  -> SEARCHING
      -> OFFERING
          -> ASSIGNED
              -> DRIVER_EN_ROUTE
                  -> DRIVER_ARRIVED
                      -> TRIP_STARTED
                          -> TRIP_COMPLETED

SEARCHING/OFFERING -> NO_DRIVER_AVAILABLE
REQUEST_ACCEPTED/SEARCHING/OFFERING/ASSIGNED/... -> RIDER_CANCELLED (policy-gated)
OFFERING/ASSIGNED/EN_ROUTE/ARRIVED -> DRIVER_CANCELLED (policy-gated/rematch where safe)
nonterminal -> SAFETY_HOLD / OPERATIONAL_REVIEW only under approved authority
```

`OFFERING` may remain dispatch-internal while the rider projection says `SEARCHING`; the canonical history still records it. Every transition specifies allowed predecessors, authenticated actor/system authority, prerequisites, expected version, idempotency behavior, timestamp, reason code, audit/outbox events and compensation/recovery behavior. Terminal history is immutable.

### 10.2 Offer state

```text
CREATED -> SENT -> DELIVERED -> ACCEPTED
                    |
                    +-> DECLINED
                    +-> EXPIRED
CREATED/SENT/DELIVERED -> REVOKED
```

Acceptance succeeds only if the offer is current, unexpired, assigned to the authenticated driver, ride is offerable and reservation still belongs to that pair. One database transaction wins; late or duplicate acceptance returns the authoritative result without double assignment.

### 10.3 Driver operational state

```text
OFFLINE -> AVAILABLE
AVAILABLE -> RESERVED -> OFFERED -> ASSIGNED
OFFERED -> AVAILABLE          (decline/expiry/revoke)
ASSIGNED -> EN_ROUTE_PICKUP -> WAITING_FOR_RIDER -> ON_TRIP
ON_TRIP -> AVAILABLE or OFFLINE (driver preference/eligibility)
any operational state -> UNAVAILABLE / SUSPENDED under authorized rules
```

Driver app connectivity is not equivalent to availability. Availability uses a short server lease renewed with bounded, privacy-minimized location updates. Lease expiry makes a driver ineligible for new offers but does not mutate an active trip blindly; active-trip outage recovery follows a separate safe rule.

### 10.4 Rider client projection

```text
IDLE
 -> SUBMITTING
 -> SEARCHING
 -> DRIVER_FOUND
 -> DRIVER_EN_ROUTE
 -> DRIVER_ARRIVED
 -> IN_TRIP
 -> COMPLETED

SUBMITTING -> NOT_SENT / RETRYABLE_FAILURE / RECOVERING
SEARCHING -> SEARCH_DELAYED / NO_DRIVER / CANCEL_PENDING
any active state -> RECOVERING after restart or stale version
```

The client projection never advances from a timer alone. Animation and estimated time are presentation of authoritative state, not proof of dispatch progress.

## 11. Searching-screen wireframes

Exact visual approval remains required. These conceptual wireframes preserve one primary status, premium calm design and honest failure states.

### Normal searching

```text
┌──────────────────────────────────────┐
│ ←                         AYO RIDE   │
│                                      │
│           ◌  ◌  ●  ◌  ◌             │
│                                      │
│       Finding your best driver…      │
│   Comparing suitable nearby drivers  │
│                                      │
│   Estimated match: 2–4 min           │ <- only calibrated server range
│                                      │
│ ┌──────────────────────────────────┐ │
│ │ Shield  We protect your trip     │ │ <- exact supportable copy pending
│ │ details while we search.         │ │
│ └──────────────────────────────────┘ │
│                                      │
│ Pickup                 Destination   │
│ Current verified pin   Meskel Sq.    │
│                                      │
│              Cancel request          │ <- policy preview before any fee
└──────────────────────────────────────┘
```

Animation uses a lightweight native/reanimated transform, pauses in background and respects reduced motion. If reduced motion is enabled, use a static progress glyph plus changing accessible status text. Do not animate a fake map or fake nearby vehicles.

### Weak network/recovery

```text
┌──────────────────────────────────────┐
│ Connection is weak                  │
│ Your request was received.          │ <- only if server receipt exists
│ Reconnecting to get the latest      │
│ driver status…                      │
│                                      │
│ [Try status refresh]                │
│ Ride ID: short support-safe suffix  │
└──────────────────────────────────────┘
```

If no server receipt exists, say “Request not sent” and do not show Searching. Never silently queue a stale ride request without an approved expiry/reconfirmation policy.

### No driver

```text
┌──────────────────────────────────────┐
│ No suitable driver is available yet │
│ We did not confirm a ride.           │
│                                      │
│ [Search again]                       │
│ Change ride type                     │
│ Adjust pickup                        │
│ Contact support / assisted booking   │ <- only when operationally staffed
└──────────────────────────────────────┘
```

No-driver copy must not blame drivers or promise a wait time. Alternatives are returned as server-approved capabilities, not hard-coded buttons.

## 12. Cancellation policy proposal

Cancellation is a leadership, legal and operational policy. Approve principles before values:

- Free cancellation before driver assignment.
- After assignment, present the exact consequence before confirmation; no surprise charge.
- A fee may be considered only after an approved grace period and material driver time/distance, using server-authoritative evidence.
- No rider fee when the driver is materially later than the disclosed bound, is moving away/unreachable under defined evidence, has wrong vehicle/identity, asks the rider to cancel, cannot access pickup, platform/map failure caused the issue, the rider reports a credible safety concern, or law requires exemption.
- If the driver reaches the verified pickup and waits the approved period, no-show treatment may compensate verified effort, with dispute/appeal support.
- Driver cancellation requires a truthful reason taxonomy. Safety, vehicle failure, road closure and rider mismatch are distinct from avoidable cancellation; never force unsafe completion.
- After driver cancellation, rematch only with rider consent/status clarity and prevent immediate same-pair rematch.
- Repeated abuse detection uses patterns plus human review; one cancellation does not trigger punitive automation.
- Every charge/compensation is server-calculated, quoted before confirmation where possible, ledger-posted immutably and reversible only by compensating entry.

Do not copy Bolt's, Feres's or any competitor's minute thresholds or fees. Research Addis pickup times, driver operating cost, map accuracy, support capability and Ethiopian consumer/transport law first.

## 13. No-driver policy

Use bounded, observable search stages rather than endless animation:

1. Search the primary serviceable radius/candidate cap.
2. Expand within an approved maximum only if pickup ETA and driver deadhead remain acceptable.
3. Degrade paid routing carefully: cached/freshness-bounded route evidence may support retry; straight-line estimates must be labeled and cannot silently assign through known barriers.
4. Stop at the cycle deadline and transition authoritatively to `NO_DRIVER_AVAILABLE`.
5. Offer server-enabled options: retry with a new request attempt, change service type, adjust pickup to a verified point, schedule later when that product is approved, or use staffed assisted booking/support.
6. Release any payment authorization and close/reserve ledger state through idempotent compensation.

Measure no-driver rate by zone/time/service, stage expansion benefit, rider abandonment, driver deadhead and false-availability causes. Do not use dynamic pricing or incentives as an automatic remedy without separate approved policy.

## 14. ETA architecture

Define three different products:

- **Search-to-match estimate:** time until a driver is likely assigned. Derived from current eligible supply, demand/queue, offer acceptance/timeout behavior and recent comparable outcomes. Show a range/percentile, or omit when uncalibrated.
- **Pickup ETA:** routed time for the assigned driver to the verified pickup, updated with freshness and confidence.
- **Trip ETA:** routed pickup-to-destination travel time, separate from pickup ETA and quote duration.

Provider-neutral interfaces return duration, distance, generated time, data freshness, provider/model/rule version, confidence/quality flags and failure category. Dispatch first uses coarse geographic distance, then paid route matrices for a bounded shortlist. Cache keys use coarse/approved location treatment and short TTL; sensitive raw locations are never broad log dimensions.

Accuracy gates include median absolute error, p90 absolute error, signed bias, coverage of displayed ranges, freshness, provider timeout rate and error by zone/time/network. Calibrate against completed operational ground truth. Compare providers with Addis field routes, overpasses, one-way streets, informal access, closures and airport/venue rules. Provider outage must yield honest degraded status, not invented precision.

## 15. Poor-network retry and recovery

### Rider client

- Generate and persist the idempotency key before sending; store only the minimum active command envelope in approved secure storage.
- Disable duplicate submit while allowing safe retry of the same command/key after timeout.
- Distinguish `not sent`, `sending`, `server accepted`, `status stale`, `offline` and `failed` visibly.
- On uncertain timeout, recover by idempotency lookup/active-ride read before offering a new request.
- On app restart, read the active authoritative ride; never reconstruct status from navigation parameters.
- Apply exponential backoff with jitter and a maximum interval; foreground/manual refresh may accelerate within rate limits.
- Treat push/SMS/realtime signals as hints and fetch by version. Ignore older versions and deduplicate events.
- Do not store precise location or fare longer than required; encrypt sensitive approved storage and clear terminal data under retention policy.

### Driver client

- Offer receipt, accept and decline use offer/version/idempotency keys.
- An accept timeout enters `acceptance_unknown` and resolves from server before the driver acts on the trip.
- Cache only the minimum active offer/trip data needed for recovery; expiry is server time with bounded clock-skew handling.
- Location upload is batched/adaptive with accuracy, age and monotonic sequence; the server rejects impossible/out-of-order movement.
- Never present a trip as assigned solely because a local tap succeeded.

### Server

- Commands are idempotent and optimistic-concurrency checked; assignment uses row/constraint locking so one outcome wins.
- Outbox consumers and notification delivery are replay-safe.
- Long polling or SSE may reduce polling later, but ordinary status polling remains the failure fallback.
- Retry budgets, circuit breakers and provider timeouts are explicit. Required authority/storage failure fails closed and yields honest availability status.

## 16. Database design proposal

This is a logical design, not an executable migration.

### Core tables

| Table | Principal fields/invariants |
|---|---|
| `rides` | internal UUID PK; unique opaque public UUID; rider identity FK; pickup/destination snapshot refs; service/quote IDs; status; version; accepted/updated/terminal UTC timestamps; zero or one active assignment |
| `ride_state_history` | append-only UUID; ride ID; from/to state; actor type/reference; reason code; command/idempotency reference; policy version; UTC timestamp; unique transition event ID |
| `command_idempotency` | actor scope; command type; key fingerprint; canonical request hash; outcome resource/status reference; created/expires; unique scoped key; never raw token/key logs |
| `dispatch_cycles` | ride ID; attempt number; state/stage; dispatch policy version; deadline; lease owner/expiry; timestamps; one active cycle per ride |
| `dispatch_candidates` | cycle ID; driver ID; eligibility outcome; coarse/routed metrics; score component bands; reason codes; data freshness; policy/model version; bounded retention/access |
| `driver_availability` | driver ID; availability state; lease expiry; location sequence; point/geography; accuracy; observed/received times; vehicle/capability version; one row per driver |
| `driver_reservations` | ride/cycle/driver IDs; status; version; expiry; unique active reservation per driver and per ride |
| `ride_offers` | offer UUID; ride/cycle/driver IDs; status/version; created/sent/delivered/responded/expires times; reason code; unique active offer constraints |
| `ride_assignments` | ride ID unique; driver ID; offer ID unique; assigned time; status/version; unique active assignment per driver |
| `dispatch_policy_versions` | immutable approved configuration metadata, effective window, checksum, approval refs; no secrets |
| `outbox_events` | event UUID; aggregate/type/version; bounded payload; created/available/leased/published fields; unique aggregate event identity |

### Constraints and indexes

- UUIDs are full server-generated opaque values. UUIDv7 may improve index locality but requires a separately reviewed generator; PostgreSQL `gen_random_uuid()` UUIDv4 is acceptable and simpler initially. Never truncate public IDs.
- Partial unique indexes enforce one active ride per rider where policy requires, one active cycle/offer/reservation/assignment per ride, and one incompatible active work item per driver.
- Spatial GiST index supports bounded availability queries; B-tree indexes cover state/deadline, driver lease expiry, ride rider/status and outbox availability.
- State transitions and assignment are transactionally version checked. Database constraints backstop service invariants.
- Candidate evidence is high-volume and sensitive. Retain only what audit/fairness/support genuinely needs; partition/archive only after measured volume and approved retention.
- Raw precise location must not appear in general audit/log tables. Access is role-scoped and audited.
- No float for money. ETA/distance use rigorously defined integer units or bounded decimal types with explicit semantics.

## 17. Security and fraud model

### Threats and controls

| Threat | Required controls |
|---|---|
| Caller creates rides for another rider | Authenticated server context; resource authorization; no body identity |
| Duplicate ride through taps/timeouts/replay | Persisted idempotency, active-ride constraints, request hash conflict, rate limits |
| Offer theft or enumeration | Opaque IDs, authenticated assigned-driver authorization, short expiry, generic errors, rate limits |
| Double assignment/race | Transactional reservation/assignment, unique constraints, expected versions, replay tests |
| Fake GPS/location replay | Device/account risk signals, sequence/freshness/accuracy, plausible-speed checks, map matching, step-up/manual review; never one signal alone |
| Driver/rider collusion or fake trips | Relationship/device/payment graph signals only under approved fraud design; completion evidence; bounded human review and appeal |
| Client fare/ETA tampering | Quote ID and server recomputation/validation; signed/authenticated transport; client values display-only |
| Provider compromise/outage | Adapter allowlists, SSRF controls, secret isolation/rotation, timeouts/circuit breaker, response validation, fallback and cost limits |
| Dispatch manipulation/insider abuse | Least privilege, policy version approvals, override reasons, append-only decision/audit evidence, separation of duties |
| AI/model poisoning or bias | Governed feature registry, dataset provenance, offline/shadow evaluation, prohibited inputs, drift/disparity alerts, rollback and human appeal |
| Location privacy leakage | Minimized precision/purpose, encrypted transport/storage, field-level response filtering, retention deletion, audited access, no raw logs |
| Notification data exposure | Minimal payloads, no destination/precise coordinates on lock screen, authenticated fetch for details |
| Denial of service/resource exhaustion | Per-identity/device/network risk limits, bounded candidate queries, queue backpressure, provider budgets, graceful overload |

Authentication risk handling must preserve the existing device/session/replay architecture. Dispatch risk signals cannot silently authenticate, authorize, punish, price or permanently suspend. High-impact automated restrictions require reason, evidence, review and appeal.

## 18. Future AI integration

AI is optional and replaceable. Define interfaces around decisions, not vendors:

- `PickupEtaEstimator`: deterministic/provider baseline, later calibrated statistical model.
- `SearchTimeEstimator`: empirical range baseline, later demand/supply model.
- `CandidateRanker` / `DispatchStrategy`: deterministic launch policy, later ML/RL candidate behind identical bounded input/output contract.
- `FraudRiskEvaluator`: versioned risk recommendation; enforcement remains approved deterministic policy/human review.
- `SupplyForecast`: advisory input for operations and later scheduled/pre-dispatch, never immediate ride existence authority.

Every model candidate needs purpose, owner, training/evaluation provenance, version, input allowlist, prohibited inputs, missing-data behavior, latency/cost budget, calibration, bias/fairness tests, adversarial tests, drift alerts, deterministic fallback and rollback. Run offline replay, simulation, then shadow mode where model output cannot affect riders/drivers. Promotion requires an approved experiment showing material benefit without breaching rider wait, driver earnings/opportunity, safety, privacy, reliability or cost guardrails.

Record selected reason codes and model/policy version, not hidden chain-of-thought or unnecessary personal features. Generative AI has no role in assignment. Reinforcement learning is not justified until AYO has representative data, a validated simulator, safe counterfactual evaluation and leadership-approved welfare objectives.

## 19. Scale path: Ethiopia to global markets

### Launch topology

- Modular monolith, PostgreSQL/PostGIS, transactional outbox and horizontally scaled stateless API/workers.
- Partition workload logically by operating city/market and service area from day one; do not hard-code Addis or ETB.
- ISO currency/language/time-zone identifiers, UTC storage and localized display.
- Dispatch policies are immutable and versioned per market/service/effective window.
- Provider-neutral maps/notification/payment interfaces and market-specific legal/operational configuration.

### Capacity controls

- Bounded candidate caps, radius stages, route-matrix calls, offer fan-out, retry counts and per-cycle deadline.
- Backpressure and admission control; overload never produces duplicate or false assignments.
- Metrics by market/zone without high-cardinality raw location labels.
- Load tests model hot zones, event surges, worker death, database failover, provider latency and reconnect storms.

### Evidence-based extraction triggers

Extract availability/dispatch only if measured write/query load, isolation needs, independently owned teams or deployment/reliability evidence justify it. Add Redis only as an ephemeral accelerator when PostgreSQL latency/load breaches approved thresholds; it cannot be sole assignment or availability authority. Add a durable broker only when outbox polling throughput/recovery evidence requires it. Shard/partition by market only after measured index/table/lock pressure and tested routing/rebalancing plans. Multi-region active-active assignment is a later complexity requiring explicit consistency design and approval.

## 20. Observability and success gates

Measure before optimizing:

- request acceptance latency and idempotency replay/conflict rates;
- dispatch cycle latency, time to first delivered offer and time to assignment;
- fulfillment/no-driver/cancellation/rematch rates;
- pickup ETA and search-range calibration/error;
- candidate counts per stage, routing calls/cost, cache freshness and provider failures;
- offer delivery/accept/decline/expiry and driver distraction indicators;
- rider wait distribution and driver opportunity/deadhead/utilization/earnings distributions;
- stale lease, fake-location and risk-review outcomes without exposing sensitive signals;
- database lock/conflict/outbox lag, worker retry/dead-letter and recovery time;
- mobile retry, duplicate tap, process-death recovery, data/battery/crash/accessibility outcomes.

Proposed SLO numbers require baseline load and CTO/CEO approval. Never claim world-class performance from local fixtures.

## 21. Verification and test design

Before implementation approval, the test plan must cover:

- every allowed/forbidden ride, driver and offer transition;
- same-key retry, conflicting reuse, duplicate tap, timeout-after-commit and process restart;
- concurrent accepts, cancel-versus-accept, expiry-versus-accept and two rides reserving one driver;
- authentication/ownership, offer theft, enumeration, rate limits and audit safety;
- no candidates, stale/inaccurate GPS, restricted pickup, vehicle mismatch and provider outage;
- outbox replay, worker crash, lease expiry, database failure and notification duplication/delay;
- route shortlist bounds and provider cost budgets;
- fairness invariants, prohibited feature tests, reason/version traceability and appeal evidence;
- cancellation fee/compensation invariants after policy approval;
- packet loss, latency, offline/reconnect, stale push, app process death and low-end Android performance;
- Amharic/English layout, screen reader, reduced motion, touch targets and sunlight contrast;
- load, stress and soak using credible launch and growth workloads;
- migration forward compatibility, rollback/forward-fix, backup/restore and zero-downtime constraints.

## 22. Risks and required decisions

### Resolved implementation gates and remaining launch blockers

CTO review, CEO confirmation and roadmap resequencing were resolved on 2026-07-15 by AP-025. The following remain blockers to production activation, not to the approved reversible domain implementation:

1. Authenticated mobile rider context, durable canonical ride lifecycle and quote authority must be connected.
2. Pickup/destination references are not production serviceable.
3. Driver verification/availability operating rules need Ethiopian professional verification.
4. Cancellation, no-show, no-driver, offer disclosure/timeout and ranking tradeoffs need leadership approval.
5. Location privacy/retention, transport obligations, insurance and consumer protection need qualified Ethiopian review before launch.

### Material residual risks

- Map quality and address ambiguity may dominate matching quality more than ranking sophistication.
- Sparse supply makes fairness and pickup speed conflict; explicit guardrails cannot create supply.
- Assisted/call-center booking adds identity, fraud and operational ownership complexity.
- Cash increases fake-trip, collection and reconciliation risk.
- Driver location freshness and inexpensive Android battery/network constraints can degrade eligibility.
- Ratings, cancellation and historical activity can encode structural bias if used without strong governance.
- Provider outages and cost spikes require honest degraded behavior.
- Premature broadcast offers can distract drivers and lock supply; exclusive sequential offers may be slower under low acceptance.
- AI optimization can exploit the wrong objective unless rider, driver, safety and fairness constraints are explicit.

## 23. Approval record and remaining gates

The CTO approved the module boundaries, API authority, state machines, transactional/outbox model, candidate pipeline, deterministic scoring structure, fairness framework, logical schema, security model, weak-network recovery, AI gates, scale path and test strategy on 2026-07-15. The CEO approved the architecture, roadmap resequencing and the bounded Mission 12 implementation scope on the same date.

Approved Mission 12 scope: server-authoritative creation, idempotency, deterministic immediate dispatch, timeout/reassignment, audit, Ethiopian-network recovery, explainable decisions and neutral reputation for new drivers until sufficient completed-trip history exists.

Excluded: scheduled rides, pre-dispatch, payment implementation, irreversible database migration and security-sensitive production activation. Stop at those gates.
