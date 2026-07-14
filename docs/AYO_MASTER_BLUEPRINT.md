# AYO Master Blueprint

Version: 1.0  
Status: product-system blueprint  
Authority: the permanent principles below are approved for this repository. Detailed commercial and operating policies remain with the Founder and AYO leadership.

This blueprint is subordinate to `AYO_CONSTITUTION.md`. Any conflict is resolved in favor of the Constitution.

## 1. Purpose and launch outcome

AYO will begin as an Ethiopia-first mobility platform and may later become a super app. The first objective is not maximum feature count. It is one complete, production-quality ride flow that riders trust, drivers can rely on for fair earnings, and operations can safely support.

The launch flow is successful when an authenticated rider can choose a valid pickup and destination, receive a transparent server-generated quote, request a ride, be matched with a suitable authenticated driver, complete the trip safely under weak-network conditions, settle the payment or cash obligation correctly, and receive support—with every important state and financial movement durably recorded.

## 2. Permanent principles

- Solve problems, not features.
- Reliability, safety and driver earnings are more important than being the cheapest.
- Immediate rides optimize for the closest suitable available driver and fast pickup.
- Scheduled rides use separate matching logic and may optimize reliability ahead of time.
- Smart pre-dispatch may prepare a suitable next trip when a driver is nearing completion, without compromising the current trip or misleading either party.
- Dispatch is staged: inexpensive geographic filtering first, paid route/ETA calls only for a shortlist.
- Smart Pickup classifies locations as verified, recommended or restricted.
- Build for cash, licensed provider integrations, weak networks, mixed devices and applicable Ethiopian rules.
- The driver balance is AYO's internal accounting ledger, not independently issued electronic money.
- Every financial movement has an immutable ledger record.
- Security, privacy and legal compliance are release constraints, not optional refinements.
- The interface stays extremely simple while the system carries the complexity.
- Complete the ride vertical before expanding horizontally.
- Major policy decisions belong to the Founder and AYO leadership. Unapproved details in this document are proposals, not policy.

## 3. Actors and product surfaces

### Rider app

The rider app solves booking, confidence and safety with the fewest necessary decisions:

- Phone-based onboarding and secure session management.
- Pickup and destination selection with Smart Pickup guidance.
- Simple ride-type choice, ETA and transparent fare quote.
- Payment-method selection appropriate to supported providers and cash.
- Search, driver confirmation, live arrival/trip state and retry-safe cancellation.
- Driver/vehicle identity, privacy-preserving communication and trip sharing.
- SOS/safety entry point, receipts, ratings, support and dispute status.
- Localized, accessible, low-data behavior with clear offline/pending states.

The rider never sees internal driver queues, fraud scores, private driver location history or operational notes.

#### Approved normal-ride journey

```text
Open AYO
  -> Confirm pickup
  -> Choose destination
  -> See price and ETA
  -> Request ride
```

The journey should use one primary action per screen whenever practical, request no unnecessary onboarding information and progressively disclose advanced options. Pending, confirmed, failed and offline states must be unmistakable. Measure booking completion time, abandonment, user errors and support contacts, then simplify repeated points of confusion.

### Driver app

The driver app prioritizes safe operation and predictable earnings:

- Guided onboarding, document status and verification outcomes.
- Online/offline/paused controls with current eligibility.
- Incoming offer showing policy-approved pickup, trip, payment and estimated earning information.
- Clear countdown, accept/decline, navigation and arrival/start/complete controls.
- Rider contact through privacy-preserving channels.
- Safety reporting, SOS and support.
- Trip-by-trip earnings, commission, cash obligations, bonuses, adjustments and payout status derived from the ledger.
- Resilient location and command synchronization on weak networks.

Actions intended while driving must be minimized; complex tasks are available only while stopped or in a safe state.

#### Approved core driver journey

```text
Go online
  -> Receive clear offer
  -> Accept or decline
  -> Navigate
  -> Arrive
  -> Start
  -> Complete
```

The driver flow must remain understandable under time pressure and weak connectivity. It must clearly communicate command acknowledgement and authoritative state without encouraging interaction while driving.

### Product design system

AYO's visual experience must be modern, calm, trustworthy and premium while remaining fast, accessible and reliable.

The reusable design system must define:

- Spacing, layout and responsive behavior.
- Typography that supports Amharic and English without broken layouts.
- Consistent icons, components, states and interaction patterns.
- Accessible contrast, readable type and large touch targets.
- Loading, empty, pending, confirmed, failed and offline states.
- Performance budgets for affordable and older Android devices.
- Accessibility patterns for disabled and older users and people travelling with children or luggage.

Clean hierarchy, generous spacing, minimal clutter and minimal text are defaults. Beauty never overrides speed, clarity, accessibility or reliability.

Before rider or driver UI implementation, present user journeys, wireframes, the design-system proposal, accessibility checks, weak-network/interrupted-session behavior and measurable usability targets for CTO review and CEO approval.

### Admin and operations dashboard

The dashboard supports operations without becoming an unrestricted database browser:

- Role-specific queues for driver verification, live ride assistance, safety, support, disputes, finance reconciliation and provider operations.
- Search and case views with data minimization and reason-based access.
- Ride timeline, offer timeline, pricing version and immutable ledger references.
- Controlled interventions using explicit commands, reasons, approvals and audit logs.
- System health, dispatch, provider, payout and safety alerts.
- No silent history editing; corrections create new events or compensating entries.

Staff roles, export permissions and high-risk approvals require leadership and security approval.

## 4. Identity and access

Every rider, driver and staff member has a unique account and explicit state. Phone OTP is the proposed primary launch method, subject to provider reliability and security validation. Sessions are revocable, devices are recorded as risk context, and staff use MFA.

Authorization is role- and resource-based. A rider may access their rides; a driver may act only on an offer/ride assigned to them; staff access only the cases and fields required by role. Authentication context supplies identity—request bodies do not establish it.

Account recovery, suspension, deletion and appeal flows must be defined before launch. Identity document and biometric use requires Ethiopian legal and operational verification.

## 5. Driver onboarding and verification

The onboarding pipeline separates submission from approval:

```text
draft -> submitted -> automated checks -> manual review
      -> approved / more information required / rejected / suspended
```

The system records driver identity, licence, vehicle registration, insurance or other required evidence, vehicle/service eligibility, consent, expiry and reviewer decisions. Documents are encrypted, access-restricted and retained only as legally/operationally justified.

Only currently approved drivers with an eligible vehicle and valid required documents may become available. Exact document requirements, background checks and renewal rules require local verification.

## 6. Dispatch system

### Suitability gate

Before ranking, exclude drivers who are offline, busy/unreservable, unverified, suspended, outside service boundaries, incompatible with ride type, affected by a safety restriction, or providing location data too stale/unreliable for dispatch.

### Immediate dispatch

Immediate rides prioritize fast pickup:

1. Use a geographic index to find a bounded nearby suitable set cheaply.
2. Apply hard eligibility and freshness checks.
3. Route only a small shortlist through the paid routing provider.
4. Rank primarily by predicted pickup time/distance, then approved reliability and fairness tie-breakers.
5. Reserve one driver atomically and issue a time-bounded offer.
6. On decline/expiry/failure, advance safely through the shortlist or expand the search.

The ranking decision records inputs, provider freshness, policy version and reason codes. Exact weights, batch/sequential offer policy and fairness rules require leadership approval.

### Scheduled dispatch

Scheduled rides are a separate strategy, not immediate dispatch with a delayed timestamp. They may:

- Validate serviceability and pickup restrictions at booking.
- Reconfirm rider, driver supply, payment and road conditions before pickup.
- Plan a reliability window and candidate pool in advance.
- Assign or reserve according to an approved lead-time policy.
- Escalate shortages early to operations and communicate clearly to the rider.

Scheduled booking must never promise certainty the operating model cannot deliver. Lead times, cancellation rules and guarantee wording require leadership and local operational approval.

### Smart pre-dispatch

Pre-dispatch considers a driver nearing the end of an active trip for a compatible next ride. It must:

- Use a predicted completion position/time and confidence threshold.
- Protect the current rider and prohibit unsafe driver interaction.
- Avoid assignment when delay risk, route uncertainty, weak location quality or safety signals are high.
- Show honest timing to the next rider and driver.
- Allow fallback without penalizing drivers for system prediction errors.

Initial production launch may keep pre-dispatch behind a feature flag until immediate dispatch is stable.

## 7. Ride lifecycle state machine

Proposed canonical lifecycle:

```text
DRAFT
  -> QUOTED
  -> REQUESTED
  -> SEARCHING
  -> DRIVER_OFFERED
  -> DRIVER_ASSIGNED
  -> DRIVER_EN_ROUTE
  -> DRIVER_ARRIVED
  -> IN_PROGRESS
  -> COMPLETED
  -> SETTLEMENT_PENDING
  -> SETTLED
```

Terminal/exception paths include `NO_DRIVER_FOUND`, `RIDER_CANCELLED`, `DRIVER_CANCELLED`, `EXPIRED`, `PAYMENT_FAILED`, `DISPUTED` and safety-controlled states.

Every transition specifies allowed prior states, authorized actor, prerequisites, timestamp, idempotency behavior and emitted event. The database transaction updates state and records history together. Clients retry commands safely and recover by reading authoritative state.

Final cancellation/no-show/wait-time policies require leadership approval.

## 8. Smart Pickup

Pickup quality is a safety and reliability system, not only an address field.

- **Verified:** reviewed pickup point with known coordinates, label, access instructions and operating context.
- **Recommended:** system/operator-suggested point expected to improve safety or pickup reliability but not fully verified.
- **Restricted:** pickup prohibited or constrained by safety, law, traffic, private access, airport rules, time or vehicle type.

The system stores zones/points, classification, provenance, confidence, effective times, restrictions, localized instructions and review history. Rider UI suggests simple alternatives. Driver UI receives safe approach details. Overrides, if allowed, require defined conditions and audit records.

Airport, venue and restricted-road classifications require local operational verification and ongoing maintenance.

## 9. Maps, routing and ETA

Provider-neutral interfaces cover geocoding, reverse geocoding, map matching, routing, traffic ETA and distance matrices. Provider selection is a commercial/technical decision, not embedded in domain logic.

- Geographic filtering precedes paid routing.
- Cache stable results carefully; active ETA respects freshness.
- Track provider latency, error rate, cost, coverage and ETA accuracy by area/device/network.
- Maintain fallbacks for provider degradation and weak connectivity.
- Do not treat straight-line distance as pickup ETA or fare distance.
- Store only necessary route/location history under a verified retention policy.

## 10. Fare calculation and pricing

A server-controlled, versioned pricing engine produces quotes and final fares. Rider and driver applications display results but never decide authoritative fare values.

Approved factor categories are:

- Base fare.
- Route distance and estimated trip time.
- Pickup difficulty and traffic conditions.
- Waiting time and service level.
- Airport or venue fees.
- Driver supply and rider demand.
- Approved bonuses, discounts and taxes.

Only documented, leadership-approved factors may be enabled. Nationality, ethnicity, language and other protected personal characteristics are prohibited pricing inputs.

AYO does not compete by being the cheapest. Pricing must fund reliable service, safety and sustainable driver earnings. The rider sees the estimated total and important conditions before confirming; the driver sees policy-approved expected earnings information.

Trip completion produces a final-fare calculation from trusted trip/provider inputs and records its rule version and explanation components. Client-provided money is never authoritative.

Every quote and final fare records the pricing-rule version and its explanation components. Dynamic pricing requires approved limits and must never exploit emergencies.

Rates, commission, dynamic-pricing limits, waiting, cancellations, taxes, rounding and quote-expiry policy all require leadership and, where applicable, legal/operational verification. Research Ethiopian competitors, rider affordability, fuel, maintenance, vehicle depreciation, insurance, tax, payment fees, driver time/utilization, safety and support costs before recommending actual prices. Do not implement final fare values until CTO review and CEO approval are recorded.

## 11. Cash reconciliation

Cash is a first-class launch reality:

- The trip records the server-authoritative cash amount expected from the rider.
- The driver confirms collection using a retry-safe command; exceptions become support/reconciliation cases.
- Ledger postings record driver cash collected, AYO commission/fees due, bonuses/adjustments and any permitted offset against future digital amounts.
- Operations reconcile cash obligations and adjustments from immutable records.
- The UI clearly separates cash held by the driver, amounts owed to AYO, digital earnings and payout availability.

How cash obligations are collected, offset, limited or enforced is a leadership policy requiring Ethiopian legal, tax and operational verification.

## 12. Driver ledger, bonuses and payouts

The ledger is append-only and double-entry. It records trip earnings, commission, tips, cash obligations, provider receipts, bonuses, adjustments, refunds, reversals, payout reservations and settlements. Every posting links to a business event and idempotency key.

Balances are derived views, including available, pending, restricted and cash-obligation amounts. Posted entries are never edited; mistakes use authorized compensating entries. Bonus definitions are versioned, explainable, budget-controlled and approved by leadership.

Payout is a state machine: requested, eligibility checked, reserved, submitted to provider, confirmed/failed, reconciled. Payout frequency, minimums, fees and provider choice require approval and local verification.

## 13. Payment-provider integration layer

AYO uses adapters around licensed payment providers so domain logic does not depend on one API. Each adapter normalizes payment intent, confirmation, refund, payout, status query and signed webhook events.

Required controls include signature verification, replay windows, unique provider event IDs, idempotent processing, secret rotation, timeouts, retries with backoff, circuit breaking, reconciliation and operational dashboards. Provider success pages or client callbacks never settle money by themselves; verified server callbacks/status checks do.

Provider licensing, supported instruments, customer-funds handling and contractual responsibilities require Ethiopian legal and commercial verification.

## 14. Safety and emergency systems

Rider and driver safety capabilities include:

- Clearly accessible SOS and safety-help entry points.
- Live trip sharing with user-selected trusted contacts.
- Route/stop anomaly signals and safety check-ins.
- Privacy-preserving communication.
- Incident reporting, evidence handling and restricted safety cases.
- Trained operations escalation with response timelines and audit trails.

AYO must not claim direct emergency response capabilities until integrations and operating procedures are verified. Emergency contacts, police/medical escalation, recording and evidence rules require local legal/operational approval.

## 15. Fraud and GPS-spoofing prevention

Use layered signals rather than one opaque score:

- Account, session and device anomalies.
- Impossible travel, mock-location indicators and sensor/provider inconsistencies.
- Repeated collusion patterns, fake-trip geometry and abnormal ride/payment behavior.
- OTP, promotion, payment, payout and document abuse signals.

Actions scale from additional verification and limited functionality to manual review or suspension. Consequential decisions record reasons and support appeal. Do not punish users or drivers solely from a noisy GPS signal, especially under weak-network/device conditions.

## 16. Ratings, support and disputes

Ratings are tied to completed trips, protected from duplicate/revenge abuse and used cautiously. They must not silently determine livelihoods without context, minimum evidence and appeal mechanisms.

Support uses categorized cases linked to the ride/payment/ledger timeline. Disputes preserve original records, evidence, actions, approvals and resolution. Financial corrections post compensating ledger entries. Safety cases follow stricter access and escalation rules.

Refund, driver adjustment, deactivation and appeal policy requires leadership approval and legal/operational review.

## 17. Notifications

Use push, SMS and in-app channels according to urgency, connectivity, consent and cost. Notifications are generated from committed domain events through an outbox and retryable delivery pipeline.

Templates are localized and versioned. Delivery is deduplicated and tracked. Critical state is always recoverable from the API; a missed notification cannot corrupt the ride. Users control nonessential notifications, while essential transactional/safety communications follow verified policy.

## 18. Observability, backups and disaster recovery

Measure user outcomes and system health without leaking sensitive data:

- Ride funnel, search time, pickup ETA error, cancellation and completion.
- Driver offer latency/acceptance, utilization and earnings reliability.
- API/worker latency, errors, queue age and database health.
- Provider latency/errors/cost, payment mismatch and payout failure.
- Safety alert acknowledgement and case handling.

Use structured logs, metrics, traces, correlation IDs, alerting and owned runbooks. Precise locations, credentials and document/payment data stay out of routine telemetry.

Backups are encrypted, access-controlled and restore-tested. Recovery objectives, retention, failover design and user communication are approved based on measured business impact. A backup is not trusted until restoration is exercised.

## 19. Low-connectivity behavior

- Keep payloads small and screens useful on mixed/older devices.
- Cache safe read data and map context with clear freshness.
- Queue permitted client commands with stable idempotency keys.
- Show `pending`, `sent`, `confirmed` and `failed` states honestly.
- Reconnect and reconcile against authoritative server state.
- Tolerate duplicate, delayed and out-of-order messages server-side.
- Provide polling fallback when real-time channels fail.
- Never allow offline clients to authoritatively finalize fare, payment, identity or safety decisions.

Test using realistic Ethiopian bandwidth, latency, packet loss, device memory, battery and background-execution constraints.

## 20. Future expansion boundaries

Expansion begins only after the ride flow meets approved reliability, safety, financial and operational gates.

- **AYO Express:** parcel order, custody, proof-of-delivery and recipient flows; may reuse identity, dispatch primitives, providers and ledger platform.
- **AYO Eat:** merchants, menus, preparation, courier pickup and multi-party settlement; separate order lifecycle.
- **AYO Marketplace:** catalogue, seller, fulfilment, returns and consumer-protection domain; not a ride subtype.
- **AYO Home:** service professionals, scheduling, scope/quote and completion evidence; separate trust and dispute model.
- **AYO Pay:** separate regulated strategy and architecture. It must not emerge accidentally from the driver ledger or shared balance UI.

Shared platform capabilities may include identity, consent, notifications, provider adapters, audit, support and observability. Each product retains its own lifecycle, policy and financial accounting boundaries.

## 21. Leadership decisions required before launch

- Launch geography, service types and operating hours.
- Pricing, commission, cancellation, waiting and incentive policies.
- Driver information shown at offer time and dispatch fairness rules.
- Scheduled-ride promise and pre-dispatch rollout.
- Payment/cash collection, payout and reconciliation operations.
- Safety response model and support service levels.
- Data retention and product-expansion gates.

These must be resolved in `AYO_DECISION_LOG.md`; engineering must not infer them from implementation convenience.
