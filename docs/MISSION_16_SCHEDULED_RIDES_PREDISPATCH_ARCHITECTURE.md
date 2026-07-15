# Mission 16 — Scheduled Ride Engine, Smart Pre-Dispatch and Airport Intelligence

Status: **CTO and CEO architecture approved, including the controlled pre-commitment replacement and third-party booking amendments. Mission 16 implementation was authorized on 2026-07-16.**

Date: 2026-07-16

## 1. Scope and outcome

Mission 16 designs a server-authoritative scheduled-ride reservation engine, smart pre-dispatch for drivers nearing completion of an existing trip, and airport-specific reservation intelligence. It extends—but does not modify—the approved immediate-dispatch authority.

The customer problem is uncertainty around time-critical planned travel, particularly airport journeys. Riders need an honest reservation state, early warning when supply deteriorates, and reliable recovery rather than an unsupported guarantee. Drivers need worthwhile planned opportunities without unpaid blocking, impossible timing, or punishment for traffic and flight disruption. Operations need explainable evidence and bounded intervention.

Success must be measured using reservation creation success, confirmation lead time, assignment stability, on-time arrival windows, reassignment recovery, rider notification latency, driver deadhead/idle impact, reservation completion, avoidable failure, and airport-specific pickup reliability. Final thresholds and any customer promise require Ethiopian field baselines and leadership approval.

Explicit exclusions:

- no production code, executable migration or route registration;
- no automatic pricing, reservation fee, cancellation fee, compensation or guarantee;
- no AI/ML ranking or prediction;
- no payment implementation;
- no external maps, flight-data, airport, messaging or identity provider connection;
- no deployment, real customer data or public activation;
- no change to immediate-ride matching or Mission 15 advisory authority.

## 2. Evidence and limitations

| Operator | Verified public behavior | Lesson for AYO | Limitation |
|---|---|---|---|
| Uber Reserve | Reservations may be offered to drivers days ahead; airport reservations can react to supplied flight information; early arrival/wait windows and cancellation conditions vary. Uber expressly notes that driver acceptance is not universally guaranteed. | Separate reservation acceptance from driver confirmation, model flight changes explicitly, and never promise supply merely because a reservation exists. | Policies vary by market and product; published commercial terms are not Ethiopian policy. |
| Uber scheduled rides | A scheduled request may simply be dispatched before pickup and does not guarantee a match. | AYO must identify whether a product is a reservation with advance assignment or a timed immediate request; do not blur them. | This simpler model provides less certainty and is not sufficient alone for time-critical AYO reservations. |
| Lyft | Drivers can browse/reserve scheduled rides in advance and must later go online in the compatible ride mode; scheduled airport pickups have separate eligibility. | Driver commitment is a stateful lifecycle, not a permanent assignment. Revalidate availability, mode, ETA and eligibility near execution. | Public detail does not disclose complete fallback or fairness algorithms. |
| Grab Advance Booking | Public material supports advance booking, airport use, early arrival/waiting and time-bounded cancellation policies; some markets add service guarantees. | Airport/time-critical products need explicit buffers, recovery and carefully bounded promises. | Guarantees and fees are market-specific commercial policy and cannot be imported into AYO. |
| Bolt | Public scheduled-ride mechanism detail was insufficient to verify a comparable lifecycle. | Do not infer private algorithms or copy unverifiable behavior. | Evidence gap recorded. |
| Yango | Public partner material describes stacked rides and airport queues in some markets. | Pre-dispatch and airport queues are distinct strategies with different constraints. | Priority and queue internals are not publicly disclosed and may create opaque hierarchy. |
| RIDE/Feres | Public material confirms Ethiopian airport service and advance/scheduled capability in some listings, but not internal reservation logic. | Airport access and assisted channels matter locally; product claims do not establish reliable architecture. | No verified matching, reassignment or guarantee mechanics were found. |

Primary sources:

- Uber Reserve and scheduled rides: <https://help.uber.com/en/riders/article/co-to-jest-uber%20reserve?nodeId=ccb9a8da-9e44-4038-921f-0360bbabc518>, <https://help.uber.com/riders/article/scheduling-a-ride-in-advance?nodeId=63165ec1-0910-409e-972f-0b8d8df1a605>
- Lyft scheduled pickups: <https://help.lyft.com/hc/en-us/driver/articles/115012924387-Scheduled-pickups-for-drivers>
- Grab Advance Booking: <https://www.grab.com/ph/transport/advance-booking/>
- Yango partner features: <https://yango.com/en_cm/driver/partner/>
- RIDE airport service: <https://ride8294.com/service-types/>
- Feres service: <https://feres.et/Home>
- Ethiopian Airlines Bole reporting-time context: <https://s1s2s3-www.ethiopianairlines.com/et/information/rules-and-regulations/conditions-of-carriage>
- Ethiopia business-travel/airport transport context: <https://www.trade.gov/country-commercial-guides/ethiopia-business-travel>
- Ethiopian Federal Police evidence that airport routes can close for major events: <https://www.federalpolice.gov.et/en/federal/police/bealert>

No authoritative, current Bole ride-hailing staging/queue rules were found publicly. Airport operating permissions, waiting areas, driver eligibility, curb access, fees and enforcement therefore remain **Requires local authority/operator verification**.

## 3. Architectural recommendation

Add a separate `Scheduled Dispatch` strategy within the existing modular monolith and approved dispatch boundaries. It owns reservation intent, commitment, execution windows, planned driver commitments, reassignment and recovery. It calls the same provider-neutral eligibility, ETA, location, notification, audit and outbox contracts as immediate dispatch but uses separate policy, state and persistence records.

```text
Authenticated reservation command
  -> Reservation aggregate + quote reference + idempotency + outbox
  -> Planning windows / supply-risk assessment
  -> Optional advance driver commitment
  -> Revalidation checkpoints
  -> Smart pre-dispatch or fallback candidate search
  -> Driver en-route / ready / rider pickup
  -> Canonical ride execution

Failure at any planning stage
  -> bounded reassignment
  -> degraded timed immediate-dispatch fallback where policy allows
  -> honest no-driver / operational-review outcome
```

Reservation and ride execution are separate aggregates. A reservation represents a future service commitment workflow; the canonical ride aggregate begins its active ride lifecycle at the approved activation boundary. This avoids holding an ordinary active ride for days and keeps immediate-ride invariants intact.

## 4. Authority boundaries

| Module | Owns | Must not own |
|---|---|---|
| Reservation | Scheduled intent, requested pickup window, lifecycle, rider ownership, policy/quote references and recovery status | Fare calculation, driver verification, flight truth or notification delivery |
| Scheduled Dispatch | Planning cycles, candidate decisions, driver commitments, revalidation, reassignment and fallback | Immediate dispatch policy, pricing, safety policy or airport regulation |
| Ride | Active trip lifecycle once activated | Long-lived reservation planning |
| Driver Availability | Online/committed/current-trip leases, capability and compatible-work constraints | Reservation promise or scoring policy |
| Maps/ETA | Route duration/range, completion ETA, pickup ETA, freshness/confidence and provider evidence | Assignment or guarantee decision |
| Airport Intelligence | Verified airport zones/rules and flight-status context behind provider-neutral contracts | Passenger manifests, immigration data or unapproved queue priority |
| Marketplace Intelligence | Advisory supply/demand context | Reservation execution authority |
| Pricing | Quote and any future reservation commercial terms | Assignment or cancellation policy invention |
| Notification | Durable delivery and receipts | Lifecycle authority |
| Audit/Operations | Immutable decision evidence and approved intervention | Silent state mutation |

## 5. Reservation lifecycle

Proposed states:

```text
DRAFT (client only)
  -> REQUESTED
  -> ACCEPTED
  -> PLANNING
  -> DRIVER_COMMITTED
  -> REVALIDATING
  -> DRIVER_EN_ROUTE
  -> READY_FOR_PICKUP
  -> ACTIVATED_AS_RIDE
  -> FULFILLED
```

Terminal or recovery states:

```text
REQUESTED/ACCEPTED/PLANNING/DRIVER_COMMITTED/REVALIDATING
  -> RIDER_CANCELLED
  -> EXPIRED
  -> NO_DRIVER_AVAILABLE
  -> OPERATIONAL_REVIEW

DRIVER_COMMITTED/REVALIDATING/DRIVER_EN_ROUTE
  -> REASSIGNING -> DRIVER_COMMITTED | DRIVER_EN_ROUTE
  -> FALLBACK_DISPATCH -> DRIVER_EN_ROUTE | NO_DRIVER_AVAILABLE
```

Rules:

- The server generates reservation ID, timestamps, version and state.
- Every command carries an idempotency key and expected aggregate version.
- `ACCEPTED` means AYO durably accepted the reservation workflow, not that a driver is guaranteed.
- `DRIVER_COMMITTED` means a current driver commitment exists but remains subject to explicit revalidation and recovery policy.
- Assignment/commitment changes append history; prior driver records are never overwritten.
- Only one effective driver commitment exists per reservation, and incompatible commitment windows cannot overlap for a driver.
- Terminal transitions are server-time authoritative and retry safe.
- Rider-visible wording must map honestly to state and cannot claim guaranteed pickup without a separately approved guarantee/operations design.

## 6. Reservation API proposal

Future versioned endpoints, not implemented:

- `POST /api/v1/reservations`: authenticated rider, idempotency key, pickup/destination place references, service type, server quote ID, requested local time plus IANA time zone, optional approved airport/flight reference.
- `GET /api/v1/reservations/{id}`: owner-authorized minimized projection with ETag/version.
- `GET /api/v1/reservations?state=upcoming`: bounded owner list.
- `POST /api/v1/reservations/{id}/cancel`: idempotent expected-version command; commercial consequence requires an approved preview protocol.
- `POST /internal/v1/reservations/{id}/recover`: service permission, bounded and audited.
- Driver commitment offer/read/accept/release commands require authenticated driver identity and never accept caller-supplied driver IDs.

Input safeguards:

- Convert local requested time using a server-approved IANA zone and persist both intended local representation and UTC instant.
- Reject nonexistent/ambiguous local times unless the client explicitly selects a valid offset.
- Enforce configurable minimum/maximum booking horizon and service-area/operating-window rules.
- The quote must cover the reservation context and remain server-authoritative; no price is calculated here.
- Flight number is optional and normalized through a provider-neutral opaque reference. Never require passenger name, booking code, passport or itinerary document.

### 6.1 Booker, passenger, future payer and trusted-contact roles

A reservation must model people by purpose rather than treating the authenticated requester as every participant:

- **Booker:** the authenticated identity that creates and manages the reservation within granted authority. The booker may be the passenger or an authorized third party, including a diaspora family member.
- **Passenger:** the person who will take the ride and whose pickup identity/contact and consent govern service delivery. The passenger may have an AYO account, a verified contact-only profile or an assisted-booking record.
- **Payer:** a separate future financial role. Mission 16 may preserve an opaque future payer reference but must not authorize, capture, charge, refund or settle payment.
- **Trusted or emergency contact:** an optional purpose-limited person explicitly authorized by the passenger or under a separately approved support/safety process. This role receives no general reservation ownership.

Booker authentication does not prove passenger consent. Passenger identity does not grant the passenger access to the booker's account, and future payer identity must never become booking or passenger authority implicitly.

### 6.2 Third-party booking consent and confirmation

Third-party reservations begin in `PASSENGER_CONFIRMATION_PENDING` unless an approved assisted-booking exception applies. The server sends a purpose-limited confirmation challenge through a verified passenger contact method. Confirmation records method, time, policy version, reservation version and consent scope; it does not expose the booker's account or payment information.

Proposed confirmation outcomes:

```text
PASSENGER_CONFIRMATION_PENDING
  -> PASSENGER_CONFIRMED
  -> PASSENGER_DECLINED
  -> CONFIRMATION_EXPIRED
  -> ASSISTED_CONFIRMATION_REQUIRED
```

Confirmation must clearly state who booked, the intended pickup window, safe pickup/destination summaries, how to decline and how to reach support. AYO must not accept silence as consent. Reconfirmation is required after a material passenger-facing change such as passenger identity, pickup, destination, service type or scheduled window.

A passenger without an account may confirm possession of a phone/contact channel using a bounded OTP or call-centre verification flow behind existing provider-neutral authentication contracts. A phone number is a contact route, not durable proof of real-world identity. Exact verification strength, age/capacity rules and guardianship require leadership and Ethiopian legal/operational review.

### 6.3 Ownership and command authorization

- The booker owns booking-management rights only while authorized and the reservation policy permits the command.
- The passenger owns consent, pickup participation, passenger-facing communication preferences and the right to decline the ride.
- The passenger may cancel their participation at any time; commercial consequences are not defined in Mission 16.
- Booker edit/cancel rights become more restrictive after passenger confirmation, formal driver commitment and pickup activation.
- A booker cannot change the passenger without cancelling/recreating or executing a separately confirmed passenger-transfer workflow.
- Support/operations acts only through an audited, least-privilege assisted-booking capability and records the represented party and confirmation evidence.
- Trusted/emergency contacts cannot edit, cancel, track or disclose the reservation unless a narrowly approved permission and passenger authorization explicitly allow it.
- Future payer disputes or payment status cannot override reservation ownership or passenger consent.

Every command derives the actor from verified authentication or an approved assisted-channel session and evaluates actor role, reservation state, resource ownership, consent status and expected version.

### 6.4 Notifications and weak-connectivity behavior

Booker and passenger receive separate, purpose-specific notifications:

- The booker receives creation, passenger-confirmation status, material plan changes, commitment status and terminal outcome, excluding unnecessary live passenger/driver location.
- The passenger receives consent prompts, trip details, material edits, driver commitment/en-route/arrival, pickup verification and cancellation/recovery information.
- Driver reassignment notifications identify only that the plan changed; they do not expose candidate scores or another driver's information.
- Delivery failure never changes reservation authority. Each party can recover their authorized projection through app, low-data web/USSD only if later approved, SMS status, or call centre.
- For passengers without smartphones, use bounded SMS/voice/call-centre confirmation and pickup codes. Do not require map interaction, push delivery or persistent mobile data.
- Weak connectivity uses idempotent replies, server-time expiry, resend limits and an assisted fallback. Delayed confirmation is evaluated against current reservation version so stale replies cannot restore cancelled or materially changed bookings.

Provider/channel selection, SMS wording and voice retention remain separate approval decisions.

### 6.5 Driver-visible passenger information and pickup verification

The driver receives only what is necessary to perform pickup after the appropriate offer/commitment stage: approved passenger display name or alias, accessibility/luggage notes explicitly provided for the trip, a privacy-preserving contact relay when available, pickup instructions and a bounded pickup verification mechanism. The driver does not receive the booker's location, account details, relationship, future payer identity, raw phone number, itinerary, passport data or emergency-contact details.

Pickup verification should use a short-lived server-generated code or mutually confirmed in-app prompt. It must support passenger read-aloud/call-centre assistance, bounded attempts, expiry and safe recovery. It is not a substitute for safety judgement; mismatch routes to support and never pressures the passenger to enter the vehicle.

### 6.6 Support, privacy and fraud controls

- Support views clearly distinguish booker, passenger, represented party, future payer reference and trusted contact; agents cannot impersonate one role as another.
- Handoff preserves consent evidence, notification receipts, pickup verification state and every actor's commands without exposing credentials.
- Contact data is purpose-limited, encrypted, access-controlled and retained only under approved policy. Future travel patterns are especially sensitive.
- Prevent account takeover with step-up authentication for passenger/contact replacement, high-risk edits and repeated third-party bookings.
- Rate limit booking invitations and confirmation attempts; detect unsolicited-booking harassment, OTP abuse, enumeration, bulk reservations and repeated passenger declines.
- Confirm that the passenger contact is not already associated with contradictory active reservations, without disclosing account existence to the booker.
- A suspicious booking may require step-up or support review, but fraud signals cannot silently cancel a passenger's transport without an approved consequential-action policy and appeal/recovery path.
- Assisted/call-centre bookings use recorded agent identity, call/session reference, represented-party declaration and explicit read-back confirmation. Call recording is not assumed or authorized.

## 7. Planning and execution windows

Use policy-defined checkpoints relative to scheduled pickup rather than one long-running job:

1. **Long-range planning:** validate serviceability and classify supply risk; do not lock a driver unnecessarily.
2. **Commitment window:** offer the reservation to suitable drivers when confidence is useful and driver opportunity cost is bounded.
3. **Revalidation window:** verify driver account, vehicle, availability, location/route confidence, current workload and communication health.
4. **Departure window:** calculate when the driver must start toward pickup using routed ETA, uncertainty buffer, pickup-zone rules and early-arrival policy.
5. **Pickup window:** track arrival/readiness and transition to the canonical ride lifecycle.

All durations, horizons, buffers, retries and maximum reassignments are versioned policy. Defaults cannot become customer promises without measurement and approval.

## 8. Deterministic scheduled-driver strategy

Hard filters precede ranking:

- active verified driver/vehicle and scheduled-service eligibility;
- compatible service, airport credential/zone eligibility where applicable;
- no overlapping committed work under worst-case travel and recovery buffers;
- current-trip completion estimate and route confidence sufficient for pre-dispatch;
- location/availability evidence within configured freshness bounds;
- approved rider-driver safety exclusions;
- no unresolved commitment breach or operational restriction;
- driver explicitly opted into or accepted the scheduled opportunity where policy requires.

Recommended lexicographic priority:

1. Meet pickup-window reliability under conservative routed ETA range.
2. Preserve the driver's current trip and safety.
3. Minimize probability/range of lateness and recovery time.
4. Minimize unpaid deadhead and excessive early waiting.
5. Apply bounded opportunity fairness among materially equivalent reliable candidates.
6. Prefer a stable existing commitment when revalidation remains healthy.
7. Stable seeded tie-break for genuine equivalence.

Do not use acceptance rate, protected characteristics, willingness to accept lower earnings, opaque popularity or raw ratings as ranking weights. New verified drivers start neutral; scheduled eligibility may require service/airport training, but not historical reputation that new drivers cannot possess.

Each decision records policy version, eligible/excluded reason families, ETA range/freshness, commitment impact, fairness band, chosen strategy and deterministic tie-break evidence. Public responses receive only approved safe reasons.

### 8.1 Soft planning and formal commitment

Scheduled dispatch has two deliberately different driver-selection phases:

- **Soft-planned candidate:** an internal, non-binding planning preference used to test likely supply and prepare recovery. The driver has not received or accepted a binding commitment. It does not reserve the driver, promise the driver earnings, expose passenger details or tell the rider that a driver is confirmed.
- **Formally committed driver:** a driver who has received and accepted the approved commitment offer, or entered another explicitly approved binding commitment transition. The commitment reserves the configured time window and creates rider/driver notification and stability obligations.

The **soft-planning window** begins at a configurable checkpoint before the formal commitment window. It may maintain one preferred candidate plus a bounded recovery shortlist, but it must not repeatedly churn candidates to chase tiny score changes.

The **formal commitment lock** begins when the commitment transaction succeeds. From that point, ordinary score comparison stops. The incumbent is stable unless a typed reliability, safety or operational trigger is confirmed.

### 8.2 Controlled pre-commitment replacement

Before the formal commitment lock, a soft-planned candidate may be replaced only when every condition passes:

1. The original driver has not received or accepted a binding commitment.
2. The candidate improvement exceeds the configured **material-improvement threshold**.
3. Reliability improvement exceeds the configured **stability margin**, expressed in approved pickup-window success/risk and conservative ETA bands—not merely a higher blended score.
4. Rider punctuality or reservation recovery capacity clearly improves.
5. The change does not create unfair opportunity churn or repeatedly disfavor the same driver cohort.
6. The reservation has not exhausted its configured **maximum soft replacement count**.
7. The decision records policy version, comparable components, reason codes and audit evidence.

The material-improvement threshold is a versioned multi-part rule, proposed to require both a minimum conservative lateness-risk reduction and a minimum pickup-window reliability improvement. Numeric values require field calibration and approval. A marginal distance, ETA or score change never suffices by itself.

The stability margin prevents replacement when measurement uncertainty overlaps or when the current candidate remains safely inside the required pickup window. Ties and near-ties retain the incumbent soft candidate.

Soft replacement fairness safeguards include bounded per-reservation replacement count, cohort opportunity monitoring, no acceptance-rate penalty, no hidden driver reputation decrement, and suppression when the same driver's soft opportunities are repeatedly displaced without material reliability gain. Because soft planning is non-binding, drivers normally receive no driver-specific notification. If product design later exposes soft interest to drivers, that exposure itself becomes a commitment-like promise and requires a separate approval; silent withdrawal after such exposure is prohibited.

The rider is not notified about internal soft-candidate changes. The rider sees only honest planning/confirmation states. Operations may receive an alert when replacement count or churn guardrails approach exhaustion.

Proposed soft-replacement reason codes:

- `material_lateness_risk_reduction`
- `material_pickup_reliability_gain`
- `recovery_capacity_improved`
- `soft_candidate_ineligible`
- `soft_candidate_plan_conflict`
- `stability_margin_not_met`
- `soft_replacement_limit_reached`
- `fairness_churn_guardrail`

Audit events:

- `reservation.soft_candidate_selected`
- `reservation.soft_candidate_replaced`
- `reservation.soft_candidate_retained`
- `reservation.soft_replacement_suppressed`

Audit metadata contains opaque reservation/candidate decision IDs, policy version, reason code and component bands—not precise location, protected data, raw scores broadly visible to staff or another driver's identity.

### 8.3 Post-commitment replacement

After formal commitment begins, replacement is allowed only for a confirmed typed trigger:

- `driver_cancelled`
- `driver_offline_or_unreachable`
- `vehicle_breakdown`
- `major_lateness_risk`
- `conflicting_commitment`
- `eligibility_failure`
- `safety_failure`
- `emergency`
- `confirmed_operational_failure`

The trigger must be supported by current evidence and evaluated under the commitment policy version. Low-confidence data causes revalidation or operations review, not silent removal. A committed driver is never removed because another candidate becomes slightly closer, has a marginally better ETA, or receives a slightly higher score.

Post-commitment replacement closes the old commitment with a reason, preserves its history, moves the reservation to `REASSIGNING`, and creates a new commitment only through the normal transactional path. The driver and rider receive timely, calm, role-appropriate notification. Safety-sensitive wording and disclosure are minimized; another driver's data is never revealed.

The **maximum replacement count** is configured separately for soft and formal phases. Formal exhaustion routes to fallback dispatch, no-driver outcome or operational review rather than an unbounded loop.

## 9. Smart pre-dispatch

Pre-dispatch may consider a driver currently completing a trip only when all safeguards pass:

- current ride is in a late, stable phase and remains authoritative;
- completion-time range plus route to scheduled pickup fits the pickup window with configured buffer;
- no action, route diversion, notification or incentive encourages rushing or compromises the current rider;
- the next rider sees an honest status and conservative ETA, not a false “driver is coming” state;
- the driver sees the next opportunity only at an approved low-distraction moment and may decline without hidden penalty;
- stale current-trip, traffic, route or network evidence invalidates pre-dispatch and triggers ordinary reassignment planning;
- at most one future commitment per driver initially.

Pre-dispatch commitment states are `PROVISIONAL`, `CONFIRMED`, `RELEASED`, `EXPIRED` and `CONVERTED`. A provisional commitment never blocks immediate recovery if the current trip deviates beyond policy.

The predicted completion provider is a replaceable contract returning a time range, confidence, observed time and reason evidence. The deterministic policy uses the conservative end of the range. A future AI predictor may supply a shadow range only after separate approval; lifecycle and fallback remain unchanged.

## 10. Airport Intelligence

Airport is a specialized reservation context, not a universal score boost.

Provider-neutral contracts:

- `AirportPolicyProvider`: versioned terminal/pickup zones, access windows, vehicle/driver eligibility, waiting/staging constraints and authoritative source.
- `FlightStatusProvider`: opaque flight reference, scheduled/estimated/actual arrival, cancellation/diversion, terminal and freshness/confidence.
- `AirportDemandContext`: aggregated arrival-bank and verified queue/capacity signals; advisory only.
- `AirportPickupReadiness`: rider-triggered ready state where airport operations require it.

Flight transitions:

```text
SCHEDULED -> EARLY | DELAYED -> LANDED
          -> CANCELLED | DIVERTED | UNKNOWN
```

Architecture rules:

- Flight status adjusts planning windows; it does not silently rewrite the rider's contractual pickup without an auditable policy transition.
- Stale/unavailable flight data falls back to scheduled time plus conservative policy and asks the rider to confirm readiness where appropriate.
- Cancelled/diverted flights move the reservation to a policy-controlled review/cancellation path; no fee or refund is inferred.
- Terminal/zone changes revalidate access and driver route.
- Queue position, if later approved, must be explicit, first-class and auditable; no purchased or hidden priority.
- Airport drivers cannot be stranded in staging solely to protect a reservation when reliability can be maintained through later dispatch.
- Flight data is minimized; passenger identity and itinerary contents are prohibited.

Bole-specific pickup zones, access authority, parking/waiting rules, licensed vehicle requirements, airport fees and operational contacts require verification with Ethiopian Airports, transport authorities and local operations before implementation.

## 11. Reliability and reassignment

Reliability is produced by checkpoints and recovery capacity, not by assigning a driver as early as possible.

Health signals:

- commitment acknowledgement and communication delivery;
- driver eligibility/vehicle status changes;
- availability/location freshness;
- current-trip completion and pickup-route ETA ranges;
- airport/flight/zone changes;
- supply depth and recovery candidates;
- worker/outbox lag and provider health.

Reassignment triggers are typed and configurable: driver release, eligibility loss, commitment timeout, predicted lateness, route/zone invalidation, current-trip overrun, stale/unreachable driver, flight change or operator-approved intervention.

Reassignment transaction:

1. Lock reservation and current commitment.
2. Confirm trigger and expected versions.
3. Close commitment with safe reason.
4. Append audit/history and outbox event.
5. Move reservation to `REASSIGNING`.
6. Start/continue an idempotent planning cycle excluding unsuitable prior attempts for a bounded cooling period.
7. Commit one replacement or enter fallback/no-driver/review state.

Never revoke a healthy commitment merely for a marginal score improvement. Reassignment churn damages trust and driver planning; a configurable stability margin protects incumbents.

This section's reassignment transaction applies to formally committed drivers. Soft-planned candidate changes follow Section 8.2 and never masquerade as formal reassignment.

## 12. Recovery and weak-network behavior

Use the existing transactional outbox, bounded workers, advisory locks and restart-safe patterns:

- durable jobs keyed by reservation/checkpoint/policy version;
- `FOR UPDATE SKIP LOCKED` bounded claims and stale-claim recovery;
- idempotent state commands and unique active commitment constraints;
- server-time deadlines, not client timers;
- exponential retry for transient provider/notification failure;
- dead-letter plus operational alert for exhausted critical work;
- periodic sweeper reconstructs missing checkpoint work from authoritative reservation state;
- late/out-of-order flight, driver and rider events are evaluated against version and observed time;
- client push/SMS is a hint; polling/upcoming-reservation read is authoritative;
- offline driver acceptance is not final until server-confirmed; expiry returns authoritative state.

The recovery worker must prioritize imminent pickups, but starvation is prevented with aging and bounded per-run partitions. Provider outage degrades to conservative ranges/manual confirmation or fallback dispatch; it never invents precision.

## 13. Persistence proposal

Additive PostgreSQL tables for a later reviewed migration:

- `ride_reservations`: owner, requested pickup local/UTC, zone, service, quote reference, state/version, policy version, airport context reference and timestamps;
- `reservation_participants`: purpose-specific booker/passenger/future-payer/trusted-contact references, verification/consent state and minimum contact-channel reference; no payment credentials;
- `reservation_consents`: append-only passenger confirmation/decline/expiry, method, policy/version, represented party and material-change scope;
- `reservation_state_history`: append-only transitions, actor, reason and causation;
- `reservation_planning_cycles`: window, strategy/policy version, stage, deadlines and outcome;
- `reservation_driver_commitments`: driver, state/version, commitment window, expiry, reason and linked planning cycle;
- `reservation_soft_plans`: preferred candidate, selection/replacement count, policy version, stability/material-improvement bands, expiry and immutable supersession link;
- `reservation_attempts`: candidate decision summary, safe reasons and outcome;
- `reservation_checkpoints`: type, due/claimed/completed times, attempt and safe failure;
- `reservation_flight_context`: minimal opaque flight reference, provider/version, status times, terminal, freshness and expiry;
- `reservation_idempotency_records`: actor/key hash/request hash/outcome/expiry;
- existing audit and outbox tables for every material transition.

Constraints:

- one active reservation per configured rider time overlap policy;
- one effective driver commitment per reservation;
- at most one current soft-planned candidate per reservation and separate bounded soft/formal replacement counters;
- no incompatible driver commitment-window overlap, enforced transactionally with a PostgreSQL exclusion constraint/range or serialized availability ledger;
- one active planning cycle per reservation;
- unique checkpoint identity and idempotency key;
- immutable state history and attempts;
- UTC instants plus IANA zone/local-time intent;
- money only by quote reference/integer minor units in Pricing-owned records.

The recommended overlap mechanism is a PostgreSQL range exclusion constraint for active driver commitment windows, with transaction-level revalidation. A generic distributed lock is not sufficient authority. A later migration must prove upgrade/downgrade and concurrency behavior on PostgreSQL 17 before approval.

## 14. Events

Versioned outbox event families:

- `reservation.requested`
- `reservation.passenger_confirmation_requested`
- `reservation.passenger_confirmed`
- `reservation.passenger_declined`
- `reservation.passenger_confirmation_expired`
- `reservation.accepted`
- `reservation.planning_started`
- `reservation.driver_committed`
- `reservation.soft_candidate_selected`
- `reservation.soft_candidate_replaced`
- `reservation.soft_replacement_suppressed`
- `reservation.driver_released`
- `reservation.revalidation_due`
- `reservation.reassignment_started`
- `reservation.driver_en_route`
- `reservation.ready_for_pickup`
- `reservation.activated_as_ride`
- `reservation.fulfilled`
- `reservation.no_driver_available`
- `reservation.cancelled`
- `reservation.operational_review_required`
- `reservation.flight_context_changed`

Payloads contain opaque IDs, version, state/reason codes and necessary timestamps—not addresses, precise location, passenger identity, flight itinerary, scoring details or secrets.

## 15. Security, privacy and fraud boundaries

- Rider/driver/service identity derives from verified authentication and existing RBAC.
- Proposed permissions separate rider reservation actions, driver commitment responses, recovery worker, restricted operations intervention and airport-policy administration.
- Ownership is enforced in service and persistence layers; opaque IDs do not replace authorization.
- Flight/provider callbacks require signature verification, replay windows and idempotent event IDs when a provider is eventually approved.
- Minimize flight data; never store passenger-name record, ticket, passport, nationality or travel companions.
- Do not reveal the scheduled rider's exact destination or identity before the approved driver-offer stage.
- Rate limit creation, mutation, driver browsing/offers and provider ingestion.
- Detect reservation hoarding, overlapping commitments, fake flight references, GPS manipulation and collusion as risk evidence; consequential action belongs to approved fraud/safety policy with appeal.
- Logs/metrics exclude precise locations and sensitive travel patterns. Access to upcoming reservations is especially restricted because it exposes future absence/location.
- Retention, airport data, cross-border flight provider processing and travel-pattern profiling require qualified Ethiopian privacy/legal review under Personal Data Protection Proclamation No. 1321/2024.
- Booker, passenger, future payer and trusted-contact identifiers are purpose-separated; authorization must never infer one role from another.
- Third-party booking and passenger-contact replacement are security-sensitive actions with step-up, consent, rate-limit and audit requirements.

## 16. Observability and service objectives

Measure without creating policy:

- reservation acceptance/confirmation/reassignment/no-driver outcomes;
- time from request to commitment;
- commitment stability and release reasons;
- pickup on-time distribution against the approved window;
- current-trip prediction and pickup ETA calibration;
- pre-dispatch conversion/fallback and impact on current trips;
- driver early-wait/deadhead and opportunity distribution;
- airport flight-change/ready/terminal recovery;
- checkpoint/outbox lag, retry/dead-letter and restart recovery;
- notification freshness and rider state-read recovery;
- provider cost/latency/freshness by adapter.

Targets require baseline measurement and leadership-approved customer promises. No “guaranteed,” “always,” or compensation wording is authorized by this architecture.

## 17. Future AI extension points

Stable interfaces may later accept shadow implementations for:

- trip-completion time range;
- scheduled demand/supply forecast;
- lateness risk;
- candidate ranking;
- flight-to-curb readiness range.

AI output is typed, versioned, confidence-bounded and never mutates state directly. It first runs offline evaluation, then shadow comparison against deterministic policy. Deterministic hard filters, lifecycle, transaction authority, audit, fallback and policy caps remain unchanged. No AI can use protected traits, infer willingness to accept worse earnings, or make pricing/safety/legal decisions. AI implementation requires a separate mission and approval.

## 18. Options and recommendation

| Option | Benefit | Risk/cost | Decision |
|---|---|---|---|
| Convert scheduled requests into immediate rides at a timer | Simplest | Little advance certainty; weak airport/time-critical reliability | Retain only as explicit fallback |
| Assign and hard-block a driver days ahead | Visible certainty | Strands supply, increases churn and broken commitments | Reject |
| Separate reservation aggregate with staged commitment/revalidation/recovery | Honest states, reliable recovery, protects driver time, scalable | More lifecycle and worker complexity | **Recommend** |
| Broadcast reservation to many drivers | Fast interest discovery | Contention, distraction, ambiguous commitment and fairness | Reject initially |
| AI optimizer | Potential future prediction | No AYO data, opaque livelihood/reliability risk | Explicitly exclude |

## 19. Edge cases requiring tests after approval

- duplicate/conflicting reservation commands and time-zone/DST ambiguity;
- rider cancels during every state, without inventing fee outcomes;
- driver commitment races and overlapping-window exclusion;
- driver goes offline, loses eligibility or changes vehicle mode;
- current ride overruns, detours, pauses or loses network;
- reservation edited after commitment;
- flight early/delayed/cancelled/diverted/unknown and provider events out of order;
- terminal/pickup zone changes and airport closure;
- road closure, major event and provider outage;
- notification lost but authoritative read succeeds;
- worker crash before/after each transaction/outbox step;
- repeated reassignment, exhaustion and operational review;
- immediate and scheduled work competing for one driver;
- repeated marginal soft-candidate improvements do not cause churn;
- material soft replacement succeeds only before commitment and within replacement limits;
- committed driver remains despite a slightly better candidate;
- every typed post-commitment replacement trigger and low-confidence revalidation path;
- diaspora booker with account passenger, contact-only passenger and no-smartphone passenger;
- passenger declines, confirmation expires, contact changes or stale confirmation arrives after edit/cancel;
- booker/passenger/trusted-contact/support authorization matrix and account-takeover attempts;
- pickup-code replay, brute force, lost contact channel and call-centre recovery;
- neutral new-driver participation and fairness parity;
- prohibited data/scoring leakage;
- 10-million-user partition/load path by market and pickup-time bucket.

## 20. Leadership decisions required

- Confirm reservation product promise: best-effort, confirmed-driver, or future separately backed guarantee.
- Approve booking horizon, pickup-window semantics and edit/cancellation experience; no fees are proposed.
- Approve driver commitment/decline/release expectations and compensation review principles.
- Approve when pre-dispatch is allowed and the material reliability/stability guardrails.
- Approve scheduled-versus-immediate supply protection and fairness policy.
- Approve airport product scope and obtain Bole/local airport authority verification.
- Approve assisted call-centre reservation parity and identity verification approach.
- Assign local legal/privacy review for future-location and flight-context processing.
- Approve soft-planning duration, formal commitment boundary, material-improvement/stability measures and soft/formal replacement-count limits.
- Approve passenger confirmation strength, no-smartphone assisted flow, booker/passenger edit and cancellation rights, and trusted-contact scope.
- Approve whether drivers ever see a non-binding soft opportunity; the recommendation is no for the initial design.

## 21. Ten-question architecture evaluation

The design partitions by market and pickup-time bucket for a credible 10-million-user path; tolerates maps/flight/notification outages through conservative deterministic fallback; is explicit and replayable; is testable with clocks/providers/repositories replaced by contracts; is deny-by-default; defines observable checkpoint and outcome metrics; uses additive versioned migrations; can extract Scheduled Dispatch later without changing the ride lifecycle; improves planned-trip reliability while protecting drivers; and remains simpler than microservices, broadcast matching or AI.

Accepted complexity is the separate reservation aggregate and checkpoint lifecycle. It is necessary because a future commitment has different truth, timing and recovery semantics from an active immediate ride.

## 22. Architecture review gate

CTO review is requested for aggregate separation, state transitions, overlap constraints, checkpoint/recovery design, deterministic scoring, pre-dispatch safeguards, airport-provider boundaries, security and scale.

After CTO review, CEO approval is requested for the reservation promise, driver commitment/fairness policy, airport scope, user-facing lifecycle and implementation sequencing.

Both approvals were recorded and implementation was authorized on 2026-07-16. External provider connection, pricing/payment policy, deployment and real data remain separately gated.
