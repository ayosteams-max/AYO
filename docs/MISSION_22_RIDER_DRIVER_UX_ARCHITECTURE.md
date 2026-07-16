# Mission 22 — Rider & Driver Experience (UX) Architecture

Date: 2026-07-16
Status: **Architecture approved by CTO on 2026-07-16. Documentation only; no production implementation authorized.**

## 1. Outcome and authority

AYO needs one calm, bilingual, recoverable experience from first launch through booking,
pickup, trip and support. The client renders server-authorized projections and sends
idempotent commands. It never assigns drivers, verifies arrival, starts waiting,
calculates money, determines blame, resolves safety, or promotes AI advice to authority.

Mission 18/19 Active Ride owns post-assignment lifecycle. Immediate and Scheduled
Dispatch remain separate. Dynamic Pickup owns pickup recommendations. Mission 20 owns
arrival/readiness/waiting/evidence projections but remains disabled and PostgreSQL-
uncertified. Pricing, Safety, Identity, Support/Recovery and Ledger retain their existing
authorities. UX labels planned or unavailable behavior honestly.

## 2. Shared experience grammar

Every task screen provides: a plain-language status; the next expected action; one clear
primary action; visible Safety and Help; server-state freshness when degraded; pending/
confirmed/failed command status; accessible text equivalent for maps; and Amharic/
English localization. Maps support decisions but never become the only instruction.

Presentation state is derived from a versioned role-safe snapshot plus overlays such as
`RECOVERING`, `STALE`, `ACTION_PENDING`, `SAFETY`, `ACCESSIBILITY` and `SUPPORT`. An
overlay cannot advance canonical state. Destructive or consequential actions require
server confirmation and a plain consequence preview sourced from policy—not UI guesses.

## 3. Rider journey

1. **First launch:** choose language, concise value statement, permission education, and
   “continue with limited permissions.” Phone authentication is delegated to Identity.
2. **Home:** current pickup label, destination search, saved/recent places and prominent
   Ride action. Future services remain absent until shipped.
3. **Pickup confirmation:** coordinate plus landmark/entrance; verified/recommended/
   restricted status; exact point, side-of-road and accessibility guidance; never move a
   confirmed pickup silently.
4. **Ride review:** service, quote/expiry, pickup ETA range, payment-method status and
   accessibility request; one `Request AYO` action.
5. **Submitting/searching:** durable request receipt, honest search stage and cancel
   request. Retry reuses the idempotency key and never creates a second ride.
6. **Assigned/approaching:** driver/vehicle match, textual ETA/freshness, pickup entrance,
   masked contact, share/help and material driver/pickup change explanation.
7. **Readiness/arrival:** advisory “head to pickup” guidance only when Mission 20 is
   certified and enabled; otherwise ordinary Active Ride status. No hidden readiness
   penalty or private-building assertion.
8. **Waiting/pickup:** verified-arrival label, visible server countdown, paused/invalidated
   explanation, vehicle match and PIN. No fee claim or rider blame.
9. **Trip:** destination, progress, safety/share/help and low-distraction status.
10. **Completion:** server fare/payment status, receipt availability, feedback, lost item
    and support. Pending finance is labeled pending.

## 4. Driver journey

1. **First launch/onboarding:** language, partner promise, staged account/document/vehicle
   requirements from Identity/Driver authorities, permission education and resumable
   checklist. No false promise of approval or earnings.
2. **Offline/online:** eligibility status, explicit Go Online, connection/location quality
   and actionable reason when unavailable without exposing risk internals.
3. **Offer:** pickup area, ETA, service/scheduled/airport/accessibility requirements and
   only policy-approved destination/earnings information. Large Accept/Decline; server
   countdown; ordinary decline has no hidden punishment.
4. **Accepted/to pickup:** authoritative assignment, exact stopping point, entrance,
   curb/heading guidance and safe navigation handoff. No typing while moving.
5. **Arrival/wait:** Mission 20 verification status, pickup mismatch action, server timer,
   paused/invalidated reason and rider-present/PIN path. Driver cannot self-authorize
   arrival, waiting, no-show, blame or fees.
6. **Trip/completion:** minimal driving UI, safety, destination and deliberate server-
   confirmed completion; earnings projection is separate from rider fare and ledger.
7. **Recovery:** last confirmed task with timestamp and safe retry. No local inference of
   accepted, arrived, started or completed.

## 5. Smart pickup and waiting presentation

When certified, Mission 20 projections map as follows:

| Projection | Rider presentation | Driver presentation |
|---|---|---|
| `ARRIVAL_UNVERIFIED` | Driver is approaching / checking pickup | “Arrival not yet verified”; remain safely stopped |
| `ARRIVAL_VERIFIED` | “Your driver is at the approved pickup” | Verified confirmation and next action |
| `FREE_WAIT_ACTIVE` | Shared countdown and pickup guidance | Same deadline/countdown and continuity status |
| `FREE_WAIT_ENDING` | Calm urgency, exact remaining time | Same facts; contact/pickup actions |
| `WAIT_PAUSED` | Timer paused with public reason | Timer paused; corrective action if available |
| `WAIT_INVALIDATED` | Waiting evidence invalidated; no consequence claim | Explain evidence issue and Support path |
| `EVIDENCE_READY` | Review/evidence status only | Review/evidence status only; no automatic blame/fee |

Countdown uses `server_time`, deadline and freshness, recomputed locally for display but
reconciled on every snapshot. Background notifications are hints, never timer authority.
Rider, Driver and Support see fact-consistent role-redacted projections.

## 6. Landmark, walking and exact-stop UX

Pickup cards support multiple bilingual named points: main gate, emergency entrance,
terminal, taxi bay, side entrance and venue-defined point. Each displays provenance/
freshness at an appropriate level, exact stopping pin/heading/curb guidance for drivers,
and route distance/time/instructions for riders when a fresh approved walking projection
exists. Emergency entrances are never routine recommendations unless operations marks
them lawful and safe.

Ambiguity shows choices or coordinate fallback; it never guesses. Walking guidance shows
destination name and material route change, accessibility suitability, expiry and a
“guidance unavailable—use confirmed point” fallback. Future reference photos remain
metadata-only and separately approval-gated.

## 7. Airport experiences

**Airport Standard** emphasizes correct terminal/zone, staging/access status, luggage-
friendly pickup instructions, ordinary vehicle match and its own configured waiting
policy. **Airport Premium** may add only approved service presentation and a distinct
policy identity; it never changes Standard promises, invents priority, or implies an
unapproved fee. Both show zone closure/congestion/flight-context freshness and fallback
pickup guidance. Financial components come only from Pricing.

## 8. Ethiopian complex pickup patterns

The same named-point model covers hospitals, hotels, shopping centres, universities,
stadiums, residential compounds and Merkato-style markets. The UI prioritizes locally
understood bilingual names, entrances, sides of road and short instructions over long
street addresses. Venue-specific states include closed/ambiguous entrance, road access
constraint, high pedestrian density, unsafe stop and operations-verified fallback.
Exact venue policies and terminology require Addis Ababa field research and operations
approval.

## 9. Weak-network, offline and power recovery

Persist only an encrypted minimum last-confirmed projection and queued low-risk command
receipts. On restart/foreground: show the timestamped cached state, authenticate, fetch
snapshot after the last sequence, discard speculative deltas, reconcile queued commands
and resume adaptive polling/streaming. Offer acceptance, arrival, wait start, PIN, trip
start/completion and cancellation outcome are never confirmed offline.

Every loading state names the operation and offers a safe fallback. Battery saver/device
sleep may reduce visual updates but cannot alter server deadlines. Emergency calling and
minimum trip/vehicle details remain locally accessible subject to platform capability.

## 10. Trust, safety and privacy UX

Safety and Help remain visible before pickup and during trip. Emergency activation is
immediate and does not wait for AI conversation. Location sharing is explicit,
purpose-limited, revocable and role-safe. Reports distinguish “submitted,” “under
review,” and “resolved”; UI never declares guilt or safety. Sensitive driver/rider
details, risk signals, raw trails and post-trip location remain hidden. Permission denial
has a functional fallback and an explanation of consequences without coercion.

## 11. Accessibility and localization

Support dynamic text, screen readers, logical focus, 44/48dp-class touch targets per
platform guidance, high contrast, reduced motion, color-independent status, haptic/text
alternatives, bright-sun driver mode and parked-only complex interaction. Accessibility
requests are explicit server context, never inferred from protected traits. English and
Amharic layouts allow expansion and code-switching; truncation cannot hide price,
countdown, safety, pickup or consequence information.

## 12. Delivery stages

1. Validate journeys and bilingual content with clickable prototypes and synthetic data.
2. Usability/accessibility testing on supported low-end Android and iPhone targets.
3. Implement only after separate CTO approval, starting with deterministic booking and
   Active Ride projections; keep Mission 20 UI feature-gated off.
4. Enable each certified server projection independently after backend gates and product
   approval. Production and store assets show only shipped behavior.
