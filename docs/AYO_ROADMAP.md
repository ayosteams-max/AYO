# AYO Roadmap

Status: proposed dependency order. A mission starts only after explicit authorization. Product-policy values remain Founder/leadership decisions.

This roadmap is subordinate to `AYO_CONSTITUTION.md`. No mission or acceptance criterion may authorize a constitutional violation.

## Roadmap operating rules

- Finish and verify each mission before widening scope.
- Preserve working prototype behavior through characterization tests and compatibility adapters.
- Security, privacy, low-connectivity and observability are part of each mission, not a final cleanup phase.
- Any launch-blocking legal/operational question is tracked in `AYO_DECISION_LOG.md`.

## Mission 1 — Reproducible engineering foundation

**Objective:** Make the existing prototype safe to develop and verify without changing product behavior.

**Scope:** Repository hygiene, supported Python version, dependency manifest/lock, namespaced settings, local run commands, CI, lint/type/test framework, characterization tests for current endpoints and wallet defect regression evidence.

**Exclusions:** No database, authentication, API redesign, wallet repair or new product behavior.

**Technical work:** Add `.gitignore`, `pyproject.toml`, lock strategy, package markers as needed, `AYO_` configuration, test fixtures, CI and documented commands. Capture current route contracts and known defects.

**Tests:** Import/startup, configuration validation, OpenAPI route snapshot, ride happy path and invalid transitions, current wallet calculations, static checks.

**Security checks:** Secret scan, debug-off production default, dependency audit setup, ensure tests/logs contain no real personal data.

**Acceptance criteria:** Clean environment installs reproducibly; backend starts with documented command; CI runs deterministically; characterization tests pass; known defects are marked and not mistaken for approved behavior.

**Dependencies:** None.

## Mission 2 — Domain contracts and persistence seam

**Objective:** Separate domain behavior from in-memory storage so persistence can change safely.

**Scope:** Typed ride, offer, driver and ledger-facing domain contracts; repository interfaces; explicit public response schemas; service dependency injection.

**Exclusions:** No PostgreSQL cutover, identity system or provider integration.

**Technical work:** Introduce domain modules/interfaces, wrap existing dictionaries behind adapters, stop returning internal dictionaries, use full opaque IDs for new internal models while preserving compatibility routes.

**Tests:** Repository contract tests, serialization/privacy tests, state-transition unit tests and parity tests against characterized behavior.

**Security checks:** Verify public responses exclude dispatch queues/private fields; validate identifiers and non-finite numeric input.

**Acceptance criteria:** Routes depend on interfaces rather than global stores; in-memory adapters still run; public/internal models are distinct; no behavior regression outside documented fixes.

**Dependencies:** Mission 1.

## Mission 3 — PostgreSQL, migrations and audit foundation

**Objective:** Establish durable transactional storage as the source of truth.

**Scope:** PostgreSQL/PostGIS, migrations, core account/driver/vehicle/ride/offer/audit tables, transaction boundaries, local test database and backup/restore basics.

**Exclusions:** No production identity flow, payments or mobile client.

**Technical work:** Implement repositories, constraints, UTC timestamps, version fields, full IDs, append-only ride history and transactional outbox table. Define prototype-data reconciliation rather than blindly trusting in-memory financial state.

**Tests:** Migration up/down policy, repository integration, concurrency, unique constraints, transaction rollback and restore smoke test.

**Security checks:** Least-privilege DB roles, encrypted connections, safe migrations, sensitive-column classification and audit access restrictions.

**Acceptance criteria:** Rides/offers survive restart and work across workers; invalid references/transitions are constrained; audit history and outbox commit atomically; restore procedure succeeds.

**Dependencies:** Mission 2.

## Mission 4 — Identity, sessions and permissions

**Objective:** Ensure every action has an authenticated, authorized actor.

**Scope:** Proposed phone OTP, account states, rider/driver/staff roles, rotating sessions, device records, resource authorization and staff MFA foundation.

**Exclusions:** No full driver document verification or social login unless separately approved.

**Technical work:** OTP provider interface, challenge/session storage, auth middleware/dependencies, permission policies, revocation/recovery events and rate limits.

**Tests:** OTP expiry/reuse/limits, token rotation/replay, logout/revocation, horizontal/vertical authorization and suspended-account behavior.

**Security checks:** Threat model account takeover/SIM swap, protect OTP verifiers, secure cookies/tokens, staff MFA, audit all sensitive auth events.

**Acceptance criteria:** Anonymous mutation is denied; actors cannot access another user's resources; staff permissions are least-privileged; sessions are visible/revocable; security tests pass.

**Dependencies:** Mission 3; OTP/provider and Ethiopian identity assumptions require verification.

## Mission 5 — Driver onboarding and operational verification

**Objective:** Admit only eligible, currently verified drivers and vehicles.

**Scope:** Driver/vehicle profiles, document uploads, review queue, status/expiry, availability gate and controlled operations views.

**Exclusions:** No automated biometric enforcement or unverified background-check promise.

**Technical work:** Encrypted object storage, signed access, malware/type checks, verification workflow, expiry reminders and eligibility rules.

**Tests:** Workflow transitions, expiry/suspension, unauthorized document access, upload abuse and availability gating.

**Security checks:** Document privacy threat model, reviewer audit, retention controls, least privilege and safe upload processing.

**Acceptance criteria:** Only approved drivers/vehicles become available; every decision has reviewer/reason/time; documents are not public or logged; renewal/suspension takes effect promptly.

**Dependencies:** Mission 4; local document/background-check requirements verified.

## Mission 6 — Canonical ride lifecycle and idempotent commands

**Objective:** Make the full non-financial ride state machine durable and concurrency-safe.

**Scope:** Quote/request/search/offer/assign/en-route/arrive/start/complete/cancel exception states, actor permissions, history and idempotency.

**Exclusions:** No advanced dispatch ranking, live provider payments or final policy values.

**Technical work:** State-machine module, transactional command handlers, optimistic/pessimistic concurrency where appropriate, idempotency records and `/api/v1` contracts.

**Tests:** Every allowed/forbidden transition, duplicate/out-of-order commands, concurrent accept/complete/cancel, stale clients and authorization.

**Security checks:** Actor/state authorization, tamper-evident audit links, prevent client-authoritative fare/identity and minimize responses.

**Acceptance criteria:** One transition wins under races; retries return the same result; history is complete; clients can recover authoritative state; compatibility plan is documented.

**Dependencies:** Missions 3–5; cancellation/no-show policies may remain disabled until approved.

## Mission 7 — Smart Pickup and map-provider abstraction

**Objective:** Produce safe, serviceable pickup/destination inputs and provider-neutral route capabilities.

**Scope:** Geocoding/routing interfaces, service areas, verified/recommended/restricted pickup model, operations maintenance and shortlist route calls.

**Exclusions:** No proprietary navigation engine or nationwide coverage promise.

**Technical work:** Provider adapters, PostGIS zones, classification/version/provenance, caching/fallback, cost/latency metrics and localized pickup instructions.

**Tests:** Boundary/time restrictions, provider timeout/fallback, stale cache, classification override/audit and cost-bounded shortlist behavior.

**Security checks:** API-key protection, location minimization, access audit, SSRF/input protections and provider data-contract review.

**Acceptance criteria:** Restricted pickups are blocked or redirected per approved rules; classifications are auditable; routes/ETAs work behind an interface; paid calls are bounded and measured.

**Dependencies:** Missions 3 and 6; launch-area restrictions operationally verified.

## Mission 8 — Reliable immediate dispatch

**Objective:** Match immediate rides quickly to the closest suitable available driver.

**Scope:** Geospatial shortlist, eligibility/freshness, paid ETA reranking, atomic reservation, timed sequential offers, decline/expiry fallback and driver availability updates.

**Exclusions:** No scheduled rides, pre-dispatch or opaque ML ranking.

**Technical work:** Dispatch policy/version, offer worker, outbox/jobs, reservation constraints, retry/fallback, reason codes and dispatch metrics.

**Tests:** No candidates, stale GPS, vehicle mismatch, timeout/decline, concurrent reservations, worker retry, provider degradation and fairness tie behavior.

**Security checks:** Prevent offer theft/enumeration, authorize assigned driver, rate-limit location/offers, detect replay and avoid leaking candidate data.

**Acceptance criteria:** One driver holds an active reservation; expired offers cannot be accepted; fallback executes; no double assignment; pickup-time/cost metrics are observable.

**Dependencies:** Missions 5–7; leadership approves tie-breakers and offer information.

## Mission 9 — Pricing, immutable ledger and cash reconciliation

**Objective:** Calculate trusted fares and account for every trip/cash obligation correctly.

**Scope:** Versioned quotes/final fares, double-entry ledger, trip earning/commission/tip/bonus postings, cash collected/owed views and reconciliation cases.

**Exclusions:** No live digital payment or payout provider yet; no unapproved dynamic-pricing policy.

**Technical work:** Money type, pricing rules interface, journal/accounts/postings, unique business/idempotency references, derived balances, compensating entries and finance views.

**Tests:** Balanced postings, rounding/currency, duplicate completion, concurrency, correction/reversal, cash/digital scenarios, property-based financial invariants and reconciliation mismatch.

**Security checks:** Server-authoritative amounts, separation of duties, append-only controls, audit access, no float/non-finite money and finance threat model.

**Acceptance criteria:** Every movement is balanced and immutable; retries cannot duplicate earnings; the known commission defect is impossible; balances reconcile to postings; policy/version is traceable.

**Dependencies:** Mission 6; pricing/commission/cash policies approved and tax/accounting treatment verified.

## Mission 10 — Licensed payment integration and driver payouts

**Objective:** Settle supported digital payments and payouts safely through provider adapters.

**Scope:** Payment intents, signed webhooks, confirmation/refund, payout workflow, provider reconciliation and failure operations.

**Exclusions:** AYO-issued electronic money, unsupported instruments or silent provider lock-in.

**Technical work:** Adapter contracts, secrets, webhook inbox/idempotency, retry/circuit breaker, settlement postings, payout reservation/failure/reversal and dashboards.

**Tests:** Valid/invalid/replayed webhooks, delayed/out-of-order events, provider timeout, duplicate payout, refund, reconciliation and sandbox end-to-end.

**Security checks:** Provider/licensing due diligence, signature verification, PCI/data-scope minimization, key rotation, approval controls and penetration testing.

**Acceptance criteria:** Client callbacks cannot settle funds; provider events process once; ledger and provider reconcile; failures are recoverable; payout status is honest and auditable.

**Dependencies:** Mission 9; licensed providers/contracts and legal model verified.

## Mission 11 — Rider and driver launch applications

**Objective:** Deliver the complete, simple ride experience on supported mixed devices and networks.

**Scope:** Onboarding, booking, Smart Pickup, offers, lifecycle controls, location sync, receipts, driver ledger views, localization/accessibility and offline reconciliation.

**Exclusions:** Express/Eat/Marketplace/Home/Pay and nonessential social/gamification features.

**Technical work:** Mobile architecture, secure storage, network queue/idempotency, polling/realtime fallback, performance budgets and staged release instrumentation.

**Tests:** Device matrix, accessibility, localization, packet loss/latency, process death, duplicate taps, stale state, battery/data use and end-to-end ride.

**Security checks:** Mobile threat model, token/key storage, certificate/network controls, privacy review, rooted/emulated device risk treatment and app security testing.

**Acceptance criteria:** A complete ride succeeds on the approved low-end device/network matrix; all money/state remains server-authoritative; UI communicates pending/failure clearly; crash/performance gates pass.

**Dependencies:** Missions 4–10.

## Mission 12 — Immediate dispatch implementation

**Objective:** Implement the approved server-authoritative immediate-dispatch architecture so one authenticated rider request is created once, matched transparently to the fastest suitable driver and recovered safely across retries, offer failures and weak networks.

**Scope:** Server-authoritative ride creation, idempotent commands, deterministic immediate matching, neutral new-driver reputation, explainable decisions, exclusive time-bounded offers, rejection/expiry reassignment, privacy-safe audit and weak-network recovery.

**Exclusions:** Scheduled rides, pre-dispatch, opaque/ML ranking, payment implementation, irreversible database migration and security-sensitive production activation without a separate gate.

**Technical work:** Canonical immediate-ride/offer/driver state, provider-neutral candidate/ETA contracts, bounded candidate funnel, configurable versioned scoring, idempotency outcomes, optimistic concurrency, automatic offer progression, audit evidence and recovery projections.

**Tests:** Duplicate/conflicting retries, every transition, stale clients, no candidates, timeout/rejection, concurrent acceptance/reservation/cancellation, neutral reputation, prohibited inputs, audit privacy, worker replay and poor-network recovery.

**Security checks:** Trusted actor identity, ride/offer ownership, replay/race resistance, location minimization, fake-location boundaries, opaque identifiers, decision-policy integrity and no client-authoritative fare/ETA/state.

**Acceptance criteria:** One idempotent request creates one ride; one assignment wins; the fastest safe reliable candidate is offered under explainable policy; decline/expiry progresses automatically; new drivers are neutral; clients recover authoritative state; audit evidence is complete and privacy safe.

**Dependencies:** Approved Mission 11 dispatch architecture and applicable identity, ride-lifecycle, map/ETA, driver-verification and quote authority. Production activation remains gated where prerequisites are not deployed.

## Mission 13 — Production dispatch persistence and secure API foundation

**Objective:** Make immediate dispatch durable, transactionally consistent, authenticated and recoverable across process restarts without activating production traffic.

**Scope:** PostgreSQL ride/attempt/offer/assignment/idempotency/audit persistence, transactional outbox, authenticated rider/driver API boundaries, RBAC and ownership enforcement, offer expiry, automatic reassignment, abandoned-search handling and bounded restart recovery.

**Exclusions:** Scheduled rides, pre-dispatch, payments, AI ranking, deployment, secrets, external production services, real customer data, irreversible migration and public production activation.

**Technical work:** Additive reversible PostgreSQL migration, constraints/partial indexes, transactional repository, outbox records, sanitized API projections, trusted-subject boundaries, dispatch permissions and scheduler-neutral worker.

**Tests:** Migration/schema parity and downgrade, transaction rollback, concurrent idempotency and acceptance, exclusive offers/assignments, timeout/reassignment, restart recovery, authorization/ownership, response minimization and audit/outbox consistency.

**Security checks:** Deny-by-default RBAC, server-derived rider/driver identity, resource ownership, least-privilege database grants, privacy-safe audit/outbox payloads, input bounds, dependency audit and static analysis.

**Acceptance criteria:** Durable state matches domain contracts; business state, audit and outbox commit atomically; retries create one ride; one active offer/assignment wins; worker recovery is bounded and retry safe; no internal score or other-driver data is public; downgrade works before activation.

**Dependencies:** Approved Mission 12 immediate-dispatch foundation plus existing PostgreSQL, identity, authentication and authorization foundations. Production authentication resolver/key activation remains separately gated.

Scheduled rides and smart pre-dispatch are assigned to Mission 16 and implemented locally; activation remains gated below.

## Mission 14 — Secure authentication, internal dispatch activation and outbox delivery

**Objective:** Securely connect durable immediate dispatch for local and controlled staging verification without public activation.

**Scope:** Provider-neutral asymmetric token verification, trusted-subject construction, configuration-gated dispatch routes, database RBAC and ownership, request/rate limits, retry-safe outbox delivery, non-overlapping recovery coordination, privacy-safe logs/metrics and worker health/readiness.

**Exclusions:** External identity or messaging services, production secrets, public deployment, real customer data, payments, scheduled rides, pre-dispatch, AI ranking and irreversible migration.

**Acceptance criteria:** Dispatch remains disabled by default; forged, expired and malformed tokens fail closed; role claims never grant authority; authenticated rider-to-driver assignment persists end to end; public responses reveal no scoring data; outbox/recovery work is idempotent, bounded and restart safe; migration downgrade and security checks pass.

The former Mission 14 production-resilience and controlled-launch scope is deferred and requires a separately numbered leadership authorization after secure staging evidence exists.

**Exclusions:** Multi-region complexity or super-app expansion without measured need.

**Technical work:** SLOs, dashboards, runbooks, deployment pipeline, infrastructure controls, recovery automation, data-retention jobs and pilot feature controls.

**Tests:** Load/soak, failover/provider outage, backup restore, security penetration, incident tabletop, payment reconciliation and rollback rehearsal.

**Security checks:** Release-gate review against `AYO_SECURITY_BASELINE.md`, vulnerability closure, access review, key rotation drill, breach notification plan and independent assessment.

**Acceptance criteria:** Approved SLOs and recovery objectives are demonstrated; critical alerts have owners; restores/reconciliation work; legal/operational launch decisions are recorded; pilot has stop/rollback criteria.

**Dependencies:** Approved Missions 12 and 13 plus controlled PostgreSQL test/staging infrastructure. Production activation remains separately gated.

## Mission 15 — Deterministic marketplace intelligence

**Status:** Architecture and implementation approved; deterministic advisory implementation complete and awaiting final review. Runtime activation remains separately gated.

**Objective:** Measure rider, driver and marketplace outcomes and produce transparent operational recommendations without becoming dispatch, pricing, payment or safety authority.

**Proposed scope:** Versioned deterministic health/fairness/opportunity components, neutral new-driver treatment, external-delay protection, rule-based demand ranges, airport/event/weather contexts, surge recommendation only, immutable explanations and an offline simulation framework.

**Exclusions:** AI/ML ranking, automatic fare or incentive changes, payments, deployment, real customer data, external production providers and direct modification of immediate dispatch.

**Activation dependency:** Leadership-approved Ethiopian operating thresholds, local legal/operational review and a controlled shadow-data activation mission. No recommendation currently affects dispatch or pricing.

## Mission 16 — Scheduled Ride Engine, Smart Pre-Dispatch and Airport Intelligence

**Status:** CTO and CEO architecture approved; implementation completed locally on 2026-07-16. Activation and deployment are not authorized.

**Objective:** Make planned and airport rides reliably recoverable through honest reservation states, staged driver commitment, smart pre-dispatch and deterministic reassignment without weakening immediate dispatch or the current trip.

**Implemented scope:** Reservation aggregate/lifecycle, scheduled-dispatch policy, soft-planned candidates with controlled material replacement, formal commitment locking, planning/revalidation checkpoints, smart pre-dispatch near trip completion, airport/flight provider-neutral context, reassignment/fallback/recovery, diaspora/authorized third-party booking with separate booker/passenger/future-payer/trusted-contact roles, explainable decisions and future AI strategy seams.

**Exclusions:** Pricing/fees/guarantees, payment, AI ranking, external providers, deployment, real data and public activation.

**Activation dependency:** Ethiopian airport/legal/operational verification, reviewed API and worker activation, provider adapters and explicit CTO/CEO activation approval.

## Mission 17 — Scheduled Dispatch Production Validation and Controlled Integration

**Status:** Implementation and PostgreSQL 17.10 validation approved and committed locally as `9494cb3bcf89a05b56c930b4c0873475fa76030a`. No public activation or deployment is authorized.

**Delivered scope:** Executed the complete PostgreSQL suite without skips; added a disabled-by-default authenticated scheduled API boundary, purpose-specific ownership and step-up controls, bounded rate limits, local notification contracts, transactional reservation audit/outbox behavior, pickup verification, controlled worker composition, advisory locks, checkpoint recovery, health state, privacy-safe observability and synthetic end-to-end validation.

**Exclusions preserved:** Payments, AI ranking, automatic pricing, external flight/maps/messaging providers, production secrets/data, deployment, public route activation and remote push.

**Activation dependency:** CTO/CEO review, Ethiopian legal/airport/operations validation, production provider reviews, secrets ceremony and a separately approved controlled environment activation.

## Mission 18 — Rider and driver real-time experience

**Status:** Architecture approved; Mission 19 implementation completed locally and awaiting CTO/CEO review. No activation, commit or deployment is authorized.

**Objective:** Give riders and drivers a clear, safe and weak-network-resilient experience from request through assignment, pickup verification, trip completion, cancellation, recovery and rating while preserving server authority.

**Scope:** Canonical active-ride lifecycle and ownership; rider/driver journeys and presentation states; provider-neutral snapshot/event/command synchronization; adaptive polling and future foreground-stream boundaries; pickup verification; cancellation/no-show evidence; a deterministic non-blocking Active Ride Confidence Engine; Dynamic Pickup Intelligence with explicit confidence and material-change confirmation; airport/premium and third-party experience; maps, notification, support and safety boundaries; accessibility, privacy, metrics and simulation. See `MISSION_18_RIDER_DRIVER_REALTIME_EXPERIENCE_ARCHITECTURE.md`.

**Exclusions:** No code, migration, dependency, provider, payment/wallet mutation, fee/refund policy, AI/recovery engine, deployment, production activation or real personal data during the architecture mission.

**Dependencies:** Missions 12–17. Implementation must remain staged and separately approved.

**Amendment boundary:** Ride confidence may classify evidence and recommend approved action but cannot assign blame, change price, cancel, conclude safety or execute reassignment. Pickup Intelligence recommends versioned primary/fallback guidance but cannot silently move pickup or override Active Ride, Dispatch or Scheduled Dispatch authority. Both fail safely when stale or unavailable and remain provider-neutral.

## Mission 19 — Active Ride Orchestrator and real-time core implementation

**Status:** Implemented and under quality-gate review; do not commit automatically.

**Delivered scope:** Canonical post-assignment lifecycle and compatibility translator; sanitized role projections; versioned snapshots, ordered replay, acknowledgements and adaptive polling; idempotent authenticated commands; protected pickup PIN and assisted/QR boundaries; cancellation/no-show evidence; deterministic Active Ride Confidence; Dynamic Pickup Intelligence; reversible PostgreSQL authority/outbox; disabled API; bounded lock-safe workers; metrics and synthetic two-device validation. See `MISSION_19_ACTIVE_RIDE_IMPLEMENTATION.md`.

**Exclusions preserved:** Payments/wallet/refunds/fees, AI authority, external real-time/maps/traffic/airport/event/messaging providers, public activation, production secrets/data, deployment and complete mobile redesign.

**Approved documentation amendment:** Future Smart Arrival, Waiting and Fair Cancellation
will verify arrival, synchronize a visible configurable free-wait window and produce
fairness-protected evidence only. Future Landmark Intelligence will add bilingual,
confidence-bearing local landmark/entrance knowledge to Dynamic Pickup. Neither is
implemented or assigned financial, cancellation, map, lifecycle or production authority.
Ethiopian waiting values require local testing, legal/operational review and separate
leadership approval.

## Deferred future engines — sequencing not yet approved

### Smart Arrival, Waiting and Fair Cancellation Engine

**Status:** Approved future architecture direction only; no runtime, fee, compensation or
mission sequence authorized.

**Objective:** Protect verified driver waiting time while giving riders early movement
guidance, a fair visible free-wait countdown and reliable notification. Produce versioned
arrival/waiting/no-show evidence and suppress consequences when pickup, data, platform or
external conditions make them unfair.

### Landmark Intelligence Layer

**Status:** Approved future architecture direction only; no provider, schema, mission
sequence or production data collection authorized.

**Objective:** Combine coordinates with privacy-safe, locally meaningful English/Amharic
landmarks, aliases, entrances, gates and approach knowledge. Keep user submissions
untrusted until corroborated and approved; fall back to coordinates when confidence is
insufficient.

### Customer Recovery and Trust Engine

**Status:** Future architecture direction only; no mission number, implementation or financial authority assigned.

**Objective:** Investigate confirmed operational failures using minimum approved evidence and recommend fair, versioned, idempotent recovery or typed human escalation. Preserve rider and driver fairness by separating rider, driver, AYO, external, shared and insufficient-evidence responsibility.

**Potential future scope:** Priority rebooking, refund/credit/discount eligibility recommendations, apology/status communication, fault-free driver compensation recommendation, support/fraud/incident review and duplicate-claim protection. Actual refunds, credits, payouts and wallet/payment mutations remain separate approval-gated systems.

### AI Customer Support Engine

**Status:** Future architecture direction only; no implementation, model, provider or channel selected.

**Objective:** Acknowledge immediately and resolve routine verified cases within seconds through approved structured evidence, tools and low-risk workflows, without making users repeat known information. Serious, ambiguous, financial, safety, legal, identity, fraud and vulnerable-person cases require seamless human escalation.

**Potential future scope:** Multilingual Amharic/English support across provider-neutral app, SMS, voice and call-centre interfaces; deterministic fallback; minimum-data retrieval; auditable explanations; and later human-supervised learning from confirmed outcomes.

**Shared gate:** Each engine requires a separately authorized research and architecture mission, Ethiopian legal/operational review, explicit policy and financial limits, privacy/retention approval, abuse controls, human-operations design and CTO/CEO approval. See `docs/AYO_FUTURE_TRUST_AND_AI_SUPPORT_ENGINES.md`.

## Post-launch expansion gate

Express, Eat, Marketplace, Home or Pay planning may begin only after leadership confirms that the ride flow meets sustained reliability, safety, driver-earnings, support, security, financial-reconciliation and operational targets. Each expansion requires its own blueprint, state model, legal review and roadmap; shared platform capability does not erase product boundaries.
