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

## Mission 12 — Safety, support, ratings and disputes

**Objective:** Give riders, drivers and operations safe, auditable help before public launch.

**Scope:** SOS/help, trip sharing, incident/support cases, privacy-preserving contact, ratings, disputes, compensating financial resolution and role-restricted operations queues.

**Exclusions:** Unverified emergency-service promises and fully autonomous punitive decisions.

**Technical work:** Case model, safety escalation, evidence controls, notification integration, rating integrity, support SLAs and approved resolution commands.

**Tests:** SOS delivery/degradation, unauthorized case access, evidence retention, duplicate/retaliatory rating controls, dispute/adjustment audit and escalation exercises.

**Security checks:** Safety/privacy threat model, staff least privilege, access reasons, sensitive export controls, insider-risk monitoring and incident tabletop.

**Acceptance criteria:** Safety events reach an owned queue and are acknowledged; access is audited; disputes never edit ledger history; operating procedures are trained and exercised.

**Dependencies:** Missions 6, 9–11; emergency, recording, support and appeal policies legally/operationally verified.

## Mission 13 — Scheduled rides and smart pre-dispatch

**Objective:** Improve planned-ride reliability and driver utilization after immediate dispatch is stable.

**Scope:** Scheduled booking/reconfirmation, advance candidate planning, shortage escalation and feature-flagged end-of-trip pre-dispatch.

**Exclusions:** Guarantees, penalties or ranking policy not approved by leadership.

**Technical work:** Separate strategy modules, forecasting inputs, predicted completion confidence, reservation windows, communications and experiment controls.

**Tests:** Early/late completion, cancellation, no supply, stale forecasts, overlap prevention, current-trip protection, driver interaction safety and rollback.

**Security checks:** Location-purpose limitation, explainable decisions, no covert driver tracking, authorization and feature-flag audit.

**Acceptance criteria:** Scheduled logic does not degrade immediate dispatch; pre-dispatch never double-books or harms the active trip; reliability/utilization improvement meets approved gates.

**Dependencies:** Stable Missions 8 and 11–12; leadership approves promises, lead times and rollout metrics.

## Mission 14 — Production resilience and controlled launch

**Objective:** Prove AYO can operate, recover and respond safely in the approved launch area.

**Scope:** Observability, alerts/on-call, encrypted backups/restores, capacity/load testing, DR exercises, release/rollback, incident response, privacy/legal launch checklist and controlled pilot.

**Exclusions:** Multi-region complexity or super-app expansion without measured need.

**Technical work:** SLOs, dashboards, runbooks, deployment pipeline, infrastructure controls, recovery automation, data-retention jobs and pilot feature controls.

**Tests:** Load/soak, failover/provider outage, backup restore, security penetration, incident tabletop, payment reconciliation and rollback rehearsal.

**Security checks:** Release-gate review against `AYO_SECURITY_BASELINE.md`, vulnerability closure, access review, key rotation drill, breach notification plan and independent assessment.

**Acceptance criteria:** Approved SLOs and recovery objectives are demonstrated; critical alerts have owners; restores/reconciliation work; legal/operational launch decisions are recorded; pilot has stop/rollback criteria.

**Dependencies:** Missions 1–12; Mission 13 only if included in launch scope.

## Post-launch expansion gate

Express, Eat, Marketplace, Home or Pay planning may begin only after leadership confirms that the ride flow meets sustained reliability, safety, driver-earnings, support, security, financial-reconciliation and operational targets. Each expansion requires its own blueprint, state model, legal review and roadmap; shared platform capability does not erase product boundaries.
