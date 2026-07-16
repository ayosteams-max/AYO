# Mission 20 — Smart Arrival, Waiting and Fair Cancellation Research

Date: 2026-07-16  
Status: **Workflow Steps 1–4 approved by CTO/CEO on 2026-07-16; bounded implementation
authorized after the required risk register. Financial policy, providers and production
activation remain excluded.**

## Scope and authority

This mission investigates how AYO can protect genuine driver waiting time while
protecting riders from false arrival, fake waiting and unfair cancellation
consequences. It also investigates landmark and airport context. It does not approve a
waiting duration, fee, refund, compensation, automatic cancellation, airport promise,
provider, retention period or production activation.

The controlling boundaries are Constitution Articles 1–4, 6–8 and 10–13; AP-003,
AP-004, AP-007, AP-008, AP-020 and AP-022; PA-035 and PA-036; LD-003; EV-007, EV-008,
EV-010, EV-012 and EV-014. Immediate and Scheduled dispatch remain separate. Active
Ride owns the post-assignment lifecycle; this proposed capability may produce evidence
but may not own dispatch, pricing, financial postings, refunds, blame or support
adjudication.

## Step 1 — research brief

### Problem, beneficiaries and simpler solution

GPS-only arrival can start a timer while a driver is on the wrong road, outside a safe
entrance, moving past the pickup, or affected by drift. A driver can also lose unpaid
time when a rider is genuinely late. Airports, large landmarks, weak connectivity and
ambiguous entrances amplify both failures.

- Riders benefit from early, comprehensible guidance, one synchronized countdown,
  suppressed consequences when evidence is unreliable, and a review path.
- Drivers benefit from verified arrival evidence, protection against unpaid genuine
  waiting, and records of external or platform disruption.
- Support and operations benefit from versioned evidence and explanations rather than
  reconstructing disputes from raw location trails.

The simpler solution is a driver-tapped “arrived” button and fixed timer. It is not
adequate because the driver controls the consequential trigger and GPS/pickup errors are
not bounded. The simplest reliable solution is a deterministic, server-authoritative
evidence engine using a small set of corroborating signals, conservative suppression,
and human review. Learned models are not justified initially.

The approved research amendment adds **Smart Pickup Readiness**. Driver ETA alone does
not answer whether the rider needs a timely prompt. AYO should continuously form a
bounded, confidence-bearing readiness estimate from approved, fresh signals and may
advise the rider to start moving when driver ETA and estimated rider-to-pickup time make
that useful. Readiness is advisory evidence: it must not prove that a rider is inside a
specific private place, establish blame, start waiting, or authorize a consequence.

### Current repository truth

- Mission 19 provides a disabled-by-default PostgreSQL-backed Active Ride aggregate,
  ordered events, idempotent commands, assignment-bound pickup verification, evidence
  records, deterministic confidence decisions and advisory pickup recommendations.
- The lifecycle already separates `driver_en_route`, `driver_arrived`, pickup
  verification, no-show review and operational review. `driver_arrived` is currently a
  lifecycle state, not sufficient proof for a fee or fault decision.
- Scheduled reservations retain their own policy, commitment, pre-dispatch and airport
  context and activate into Active Ride through an explicit boundary.
- No real maps/ETA, flight, landmark, notification, pricing/ledger, refund, or mobile
  waiting implementation exists. Current product documents express intent only.
- PA-035 and PA-036 expressly prohibit implementation until separate approval. LD-003
  (cancellation, wait and no-show policy) remains open.

### External evidence and limitations

Competitor behavior is evidence, not AYO policy:

- Uber states that wait fees are automatic rather than manually triggered, begin only
  after arrival and a grace period, vary by city/product, and may not apply at airports
  or venues. Uber also acknowledges that GPS-based arrival does not always match real
  coordinates. Accessed 2026-07-16: https://help.uber.com/riders/article/ooteaja-tasud?nodeId=22b6db22-0f86-4765-ac72-da549a2302d7
- Uber describes an early-arrival safeguard in which the grace period starts at the
  original ETA or arrival, whichever is later, plus disability waivers and separate
  cancellation versus wait-time treatment. Accessed 2026-07-16:
  https://help.uber.com/en/driving-and-delivering/article/how-are-wait-time-fees-calculated?nodeId=7f41997f-a853-46ae-8001-8ab9dee504b0
- Lyft similarly varies grace periods by product, excludes certain assisted/healthcare
  journeys and supports disability-related waivers. Accessed 2026-07-16:
  https://help.lyft.com/business/hc/en-us/articles/13805094213139-About-wait-time-fees

These public help pages do not disclose arrival algorithms, measured false-positive
rates, Ethiopian performance, or fraud controls. They therefore support product
principles only, not implementation thresholds.

Ethiopia-specific requirements remain unresolved. Ethiopia's Personal Data Protection
Proclamation No. 1321/2024 is material to precise location, automated decisions,
retention, access and dispute evidence, but qualified Ethiopian privacy counsel must
verify the authoritative text and AYO's obligations. Addis Ababa/Bole airport pickup,
parking, holding-area and access rules require written confirmation from the airport,
transport authority and local operations. Consumer rules for disclosure, cancellation,
waiting, cash collection and refunds require qualified local review. Map quality,
network delivery, common device accuracy, Amharic/English landmark comprehension and
actual pickup behavior require launch-area field measurement; web evidence is not an
adequate substitute.

### Proposed success measures (targets require approval and baseline)

Measure in shadow mode before any consequence is enabled:

- verified-arrival precision, with a deliberately higher threshold than recall;
- false-arrival and false-wait rate, split by GPS quality, device, map confidence,
  landmark, airport, service and Immediate/Scheduled origin;
- percentage of genuine waits recognized and driver minutes left uncompensated;
- rider notification delivery/acknowledgement and countdown divergence;
- readiness precision/calibration, useful-prompt rate, prompt-to-movement outcome,
  duplicate/suppressed prompt rate and opt-out/complaint rate;
- pickup completion, cancellation and support-contact rates;
- low-confidence/manual-review rate and review turnaround;
- dispute overturn/refund recommendation rate by reason and responsibility class;
- fairness differences across accessibility context, language, service and geography;
- battery, mobile-data, server latency, provider cost and stale-signal rate.

The CTO should approve numerical acceptance thresholds only after a labeled synthetic
suite and Ethiopian shadow/field baseline. No metric may be optimized by increasing
unsafe pickup behavior or suppressing legitimate appeals.

### Threats and constraints

- GPS drift, spoofing, replay, clock skew, stale/out-of-order observations and shared
  devices can fabricate or hide presence.
- A driver may stop near but not at the reachable pickup, circle the geofence, disable
  location or leave after triggering a timer. A rider may claim presence from another
  location or exploit notification failure.
- A geofence cannot prove safe access, line-of-sight, passenger identity or fault.
- Raw location trails are highly sensitive. Decisions should retain bounded derived
  facts and opaque evidence references; owning domains retain source data under an
  approved schedule and purpose-scoped access.
- Weak connectivity requires server time, bounded freshness, idempotent ingestion and a
  visible “timer status uncertain” state. Missing data must suppress consequences, not
  be interpreted against either party.
- Heading is unreliable at low speed and must never be a sole arrival condition.
- “Inside a building or venue” is an uncertain contextual inference, not a verified
  fact. The rider-facing explanation should ask the rider to head to the approved pickup
  rather than expose or overstate that inference. Missing, stale or ambiguous rider
  signals produce `insufficient_data` and suppress readiness prompts.
- Readiness notifications require policy-versioned confidence thresholds, minimum
  resend intervals, material-change rules and per-ride caps. Delivery is not proof that
  the rider saw or acted on a message.
- Airport/venue policy must be versioned by approved zone and product. Airport Premium
  may select an approved policy but must not modify Standard policy implicitly.
- Waiting policy must be selected from versioned configuration, never hard-coded. The
  selector must support airport, hotel, hospital, shopping-centre and residential
  context; Immediate or Scheduled origin; accessibility requirements; severe weather;
  and approved operational overrides. Missing, expired or conflicting configuration
  must fail closed by preventing consequence eligibility.

### Open verification and leadership questions

1. CEO/Operations: Should this engine remain evidence-only in its first release, with
   every low-confidence or consequence case reviewed, or may a later approved policy
   automate narrowly defined outcomes?
2. CEO/Legal/Operations: Approve actual free-wait, warning, accessibility, Scheduled,
   airport and Premium values within the approved configuration dimensions. No defaults
   are proposed as launch values.
3. CTO: Approve the proposed deterministic boundary, ownership contracts, shadow-mode
   sequence and the rule that raw GPS alone cannot verify arrival.
4. CEO: Confirm “prevent cancellations, do not profit from them,” no hidden punishment
   scores, no double wait/cancellation charge, and a clear appeal/review path as product
   policy.
5. Legal/Privacy: Approve lawful basis, notice, automated-decision safeguards, access,
   retention/deletion, cross-border processing and dispute-evidence handling.
6. Airport/Operations: Provide authoritative airport/venue zones, access rules, holding
   behavior, safe entrances and escalation contacts.
7. Product/Design: Approve user journeys, Amharic/English wording, accessibility,
   offline states and countdown behavior before mobile implementation.

## Step 2 — findings and options

### Option A — manual arrival plus fixed geofence

**Pros:** lowest build and operating cost; simple to explain; no new provider required.  
**Cons:** driver-controlled consequential trigger, high drift/wrong-road exposure, weak
airport/landmark behavior and poor abuse resistance.  
**Scale/maintenance:** simple and horizontally scalable, but creates support and trust
cost rather than solving it.  
**Customer/safety/Ethiopian fit:** works on weak devices but is unfair where maps,
entrances and GPS are uncertain. Not recommended.

### Option B — deterministic multi-signal evidence engine (recommended)

Use server time and versioned policy to combine fresh assigned-driver location accuracy,
distance to an approved pickup zone, recent movement/stopping duration, approach/heading
when reliable, pickup/map confidence, assignment validity, notification health and
known platform/external disruption. Require corroboration; treat each signal as
fallible. Maintain explicit unverified, verified, active, ending, paused, invalidated
and evidence-ready outcomes. Emit a confidence score band, stable reason codes, policy
version, minimum evidence references and a role-appropriate explanation. Low confidence
or conflict routes to review; it never silently becomes charge eligibility.

**Pros:** explainable, testable, provider-neutral, conservative, compatible with the
modular monolith and existing advisory/evidence boundaries; can work without ML.  
**Cons:** requires field calibration, operations data, careful state/time semantics and
support capacity; imperfect maps still constrain recall.  
**Cost:** medium build; low-to-medium operations initially, with map/ETA and notification
cost bounded through adapters, caching and staged calls.  
**Scale/maintenance:** append-only decisions and current-state projections can partition
by ride; bounded per-ride signal windows avoid unbounded computation. Keep it an
internal module until measured isolation/scale triggers justify extraction.  
**Customer/safety/Ethiopian fit:** best balance for weak networks, cash, mixed devices,
landmarks and auditable disputes, provided local field and legal gates are completed.

### Option C — learned arrival/fraud classifier

**Pros:** may improve complex-pattern accuracy after sufficient labeled outcomes.  
**Cons:** no trustworthy AYO labels exist; higher privacy, bias, drift, explainability,
monitoring and human-appeal burden; unsafe cold start.  
**Cost/scale/maintenance:** highest build and ongoing evaluation cost; model/provider
lock-in can be avoided but not the operational burden.  
**Customer/safety/Ethiopian fit:** premature. Consider only as shadow advice after the
deterministic system has representative, consented, quality-controlled Ethiopian data
and a measured accuracy gap that justifies complexity.

### Recommendation and deliberate deferrals

Approve Option B for a later architecture phase, initially in non-consequential shadow
mode. Keep one deterministic engine for arrival/wait evidence while selecting distinct,
versioned policies for Immediate, Scheduled, airport, Airport Premium, accessibility and
assisted contexts. This preserves separate dispatch logic: the engine consumes the
activated ride's origin/context but never ranks or assigns drivers.

The approved amendment adds a deterministic Rider Readiness decision beside arrival
evidence. It classifies `moving_toward_pickup`, `likely_on_time`,
`possibly_inside_building_or_venue`, `unlikely_on_time` or `insufficient_data`, with a
confidence score, reason codes, source freshness, audit reference and safe explanation.
Only an approved notification policy may turn a fresh, sufficiently confident decision
into a bounded prompt such as “Your driver is 2 minutes away. Please head to the pickup
point now.” Cooldowns, material-change checks and per-ride caps prevent spam.

Waiting duration and behavior are selected from immutable, versioned configuration
using explicit ride and pickup context. Configuration supports airports, hotels,
hospitals, shopping centres, residential pickups, Immediate rides, Scheduled rides,
accessibility requirements, severe weather and operational policy. Selection is
auditable and deterministic for the same policy snapshot; it never embeds a duration or
financial consequence in application code.

Landmarks should first be operations-curated, bilingual, versioned place/entrance
records with provenance and expiry. Rider/driver submissions remain untrusted
observations. The pickup authority must recheck safety, legal access, accessibility and
road approach; no recommendation silently relocates a confirmed pickup.

Defer learned models, automatic financial consequences, automatic refunds, live
provider selection, user-generated landmark promotion, fixed policy values and airport
commercial promises. Pricing remains the only future authority for a fee and the ledger
the only authority for value movement. Support/Recovery may recommend review or refund
under separately approved authority.

### Survivability review

The recommendation has a credible path to 10 million users through bounded per-ride
state, partitionable append-only decisions, stateless workers and provider adapters; it
degrades conservatively during provider outage; uses explicit contracts and reason
codes; is automatically testable and least-privilege compatible; supports aggregate
metrics without precise-location logs; can roll out in shadow mode and be disabled
without changing ride authority; and remains replaceable because maps, notification and
future model inputs are adapters. It improves trust only if field thresholds and human
operations are funded. It is the simplest solution that meets the stated fairness and
audit requirements.

### Revisit triggers

Revisit the recommendation if Ethiopian shadow data shows an approved false-arrival or
dispute threshold cannot be met; map/provider outage makes evidence unavailable too
often; review volume exceeds approved staffing; battery/data/provider cost breaches its
budget; a legal decision prohibits the intended processing; or a learned shadow model
shows a material, stable fairness-adjusted gain that cannot be achieved with simpler
rules.

## Workflow evidence and stop gate

| Step | Evidence | Status |
|---|---|---|
| 1 | This research brief and cited sources | Complete |
| 2 | Options, recommendation, risks, measures and decisions requested | Complete |
| 3 | CTO/CEO amendment approving research and requested additions | Complete 2026-07-16 |
| 4 | Architecture proposal and CTO architecture approval | Complete 2026-07-16 |
| 5 | Risk register and test mapping | Required before coding |
| 6–10 | Implementation through completion report | Authorized within approved exclusions |

Implementation must follow `MISSION_20_SMART_ARRIVAL_WAITING_CANCELLATION_ARCHITECTURE.md`,
complete Step 5 before coding and stop for CTO/CEO review before any implementation
commit or activation.
