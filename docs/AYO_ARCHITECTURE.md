# AYO Architecture

Status: target architecture proposal grounded in the repository as inspected on 2026-07-14. Product-policy choices remain subject to Founder and leadership approval.

This architecture is subordinate to `AYO_CONSTITUTION.md` and must preserve a credible path to 10 million users, governed first-class AI and independently scalable module boundaries.

## 1. Current architecture

Revision `20260723_0045` adds PRE-PRODUCTION canonical Subject, Account and explicit
legacy-identity mapping persistence. It preserves the mixed legacy `identities` authority
and historical references; no credential, login, session, full-RBAC, business-participation
migration or production activation is part of that revision.

AYO currently has an early synchronous FastAPI prototype:

```text
HTTP request
  -> BACKEND/routes
  -> BACKEND/services
  -> module-level Python dictionaries
```

Increment 19 Milestone 1 stops `BACKEND/main.py` from registering the legacy ride, driver-offer, ride-status and wallet routers. With no explicit secure activation, the default application exposes only root and health routes; obsolete process-local modules remain quarantined for later dependency-proven removal. Mission 12 added an isolated typed immediate-dispatch domain core, and Mission 13 added PostgreSQL 17 persistence, transactional repositories, immutable audit writes, a transactional outbox, RBAC contracts and bounded recovery. Mission 14 can register secure dispatch and internal-worker routers only through an explicit feature flag that defaults off and is prohibited in production configuration. Controlled activation requires explicit PostgreSQL, asymmetric-token-verifier, publisher and worker dependencies. Verified identity/session state and database RBAC are authoritative; token role claims are rejected. The outbox and recovery coordinators are scheduler-neutral, use bounded work and PostgreSQL locking, and are not started on import. No external identity, messaging or telemetry provider is connected. In-memory repositories and local publishers are test-only. `ayo_ai.py` remains disconnected from dispatch.

Mission 15 adds an unregistered deterministic Marketplace Intelligence module. It consumes privacy-minimized aggregate snapshots, evaluates immutable configurable rules, persists replayable advisory decisions and simulations, and emits safe metrics/logs. It cannot assign drivers, change fares, block dispatch or invoke AI. Dispatch remains authoritative; marketplace failure degrades to no recommendation. No production scheduler, API or data source is connected.

The repository has a locked Python environment, automated regression/contract tests, linting, security scanning and GitHub Actions CI. It now also contains an early Expo rider-interface prototype in `AYO-Mobile/`, including a provider-neutral destination-search seam; this is not a production client and has no authenticated persistence, live maps or provider connection. The system still has no deployed persistent database, external provider integrations, production mobile/web clients, background workers, deployment pipeline or production infrastructure. Existing product design documents remain aspirations rather than executable specifications unless explicitly identified as implemented.

Increment 19 Milestone 2 adds a disabled-by-default canonical authentication runtime over
the PostgreSQL identity/session foundations: normalized keyed contact lookup, Argon2id,
short-lived asymmetric access tokens, rotating opaque refresh families, server revocation,
rate limiting, audit, recovery preparation and secure mobile restoration. Contact delivery,
contact verification completion, recovery completion, production keys and activation remain
external approval and operations gates. Authentication identifies a subject; it does not
grant a role, verify legal identity or authorize a ride.

Increment 19 Milestone 3 extends that runtime with provider-neutral pending-contact
activation and an executable guest-to-member mobile transition. A bounded, single-use
local intent restores the exact internal path after verification but carries no booking or
authorization authority. Mobile state distinguishes the shared Identity Session from
capability-local participation and prevents simultaneous earning modes as a client guard;
durable server enforcement remains mandatory before any worker mode is activated.

### Current strengths

- Explicit fail-closed route activation boundaries.
- Input validation with Pydantic.
- Canonical ride lifecycle and financial foundations with typed authority boundaries.
- Eligibility filtering and understandable dispatch code.

### Current constraints

- Memory state disappears on restart and diverges across workers.
- Mutable dictionaries provide no transactions, concurrency control or durable audit trail.
- Canonical authenticated rider endpoints are not yet activated.
- Dispatch timeouts and fallback candidates do not execute.
- No production public trip-status projection is active.

## 2. Approved initial architectural direction

CTO review: approved 2026-07-15
CEO approval: approved 2026-07-15

AYO begins as a modular monolith, not as separately deployed microservices. This is the smallest production architecture that preserves strong transactions, clean domain ownership, low operating cost and a credible scaling path while AYO proves one complete ride flow.

```text
Rider App        Driver App        Admin Dashboard
     \               |                    /
              AYO API Edge
     authentication, rate limits, API versioning
                       |
          FastAPI Modular Monolith
 -------------------------------------------------
 Identity | Drivers | Rides | Dispatch | Pricing
 Pickup   | Safety  | Ledger | Payments | Support
 Notifications | Audit | Analytics Events
 -------------------------------------------------
                       |
          PostgreSQL + PostGIS
                       |
        Worker Queue / Cache / Outbox
                       |
 Maps | SMS | Push | Payment Provider Adapters
```

### Approved rules

- Identity, Drivers, Rides, Dispatch, Pricing, Pickup, Safety, Ledger, Payments, Support, Notifications, Audit and Analytics Events are internal modules, not independently deployed services initially.
- Keep module contracts, ownership and private state clean so a selected module can be extracted later only when traffic, security risk, team ownership or operational evidence justifies it.
- Do not introduce microservices merely to claim scalability. Independent scalability means each module has a credible path to scale or extraction, not that it must be deployed separately on day one.
- Use provider-neutral interfaces and open standards where practical, including PostgreSQL/PostGIS, OCI-compatible container images, OpenTelemetry and portable event/data formats.
- Keep AYO cloud-portable and isolate provider SDKs behind adapters. Avoid unnecessary AWS-specific dependencies in domain logic, data models and public contracts.
- AWS Cape Town remains a provisional MVP recommendation only. Final provider selection requires real latency/reliability tests from Ethiopian networks, actual provider pricing and required legal/operational verification.
- Use confidential computing only for narrowly identified workloads whose threat or verified requirement justifies its added cost and complexity. Tier 1 and Tier 2 remain the default for the MVP.
- No infrastructure deployment is authorized by this clarification.

### Decision rationale

The modular monolith reduces distributed-system failure modes, duplicated operations and early cloud cost while preserving one transactional boundary for the first ride flow. Clean internal modules keep later extraction possible without forcing riders and drivers to pay the reliability cost of premature service boundaries.

### Alternatives considered

- **Separate microservices initially:** rejected because the current team, traffic and ownership evidence do not justify independent deployments, network contracts, distributed transactions and duplicated observability/on-call burden.
- **Unstructured monolith:** rejected because shared private state and unclear module ownership would prevent safe scaling and extraction.
- **Serverless functions for every module:** rejected as a mandatory pattern because it can fragment domain logic and increase provider lock-in; individual adapters/workers may use serverless compute later when evidence supports it.

### Principal risks

- Weak boundaries could turn the modular monolith into a tightly coupled system. Mitigate with explicit module APIs, ownership rules and architecture tests.
- A single deployment may scale cold modules with hot ones. Accept for MVP; measure module load and extract only with evidence.
- One database can become a coupling/bottleneck point. Preserve schema/table ownership, bounded queries, indexes and migration discipline; split only when measured need justifies it.
- Provider-neutral abstractions can become lowest-common-denominator layers. Abstract stable capabilities and keep provider-specific optimizations inside adapters rather than hiding all differences.

## 3. Module responsibilities

### Identity and access

Accounts, OTP challenges, sessions, device records, roles, permissions, account state and security events. Authenticated identity is injected into commands; clients never choose their authoritative identity.

Authorization is a separate internal module. PostgreSQL is authoritative for
roles, permissions, grants and identity-role assignments. Its policy decision
contract accepts a trusted subject, action/permission and resource so enforcement
can later move behind an internal standard interface without changing semantics.
Mission 8 uses core RBAC only: no hierarchy, ABAC engine, external policy service
or client/token-authoritative privilege.

Middleware accepts only trusted Authentication output. Route decorators and
dependencies are HTTP enforcement points; sensitive services repeat checks at
their own boundary. Missing identity requires authentication, unmatched permission
denies by default and persistence failure never grants access. The 12 prototype
routes remain unchanged until an approved Authentication transport establishes
their caller; this is not production-launch approval.

### Drivers and vehicles

Driver profile, verification cases, documents, vehicles, eligibility, service types and availability. Sensitive documents belong in encrypted object storage, not general application logs or API responses.

### Rides and lifecycle

Ride aggregate, participants, pickup/destination, state history, cancellations and completion. The module owns the state machine and rejects invalid or duplicate transitions.

### Dispatch

Immediate, scheduled and pre-dispatch strategies behind separate policies. It owns offers, reservations, expiry, fallback order and dispatch audit reasons. Geographic candidate retrieval uses PostGIS or an equivalent index; paid routing is limited to a shortlist.

### Smart Pickup

Versioned pickup points and zones with verified, recommended and restricted classifications, provenance, operating constraints and override/audit workflow.

### Maps and ETA

Provider-neutral geocoding, map matching, route and ETA interfaces. Cache only when safe; record provider/version and freshness used for operational decisions.

### Pricing

Server-authoritative quotes and final fare calculation. Pricing rules are versioned and auditable. Policy values require leadership approval.

### Ledger and payouts

Immutable double-entry journal, driver account views, bonus postings, cash obligations, payout requests and reconciliation. The displayed driver balance is a derived view of AYO's internal accounting records.

### Payments

Provider adapters, payment attempts, signed webhook ingestion, idempotency, refunds and reconciliation. AYO integrates only through appropriately licensed providers unless legal approval establishes another model.

### Safety, fraud and support

Safety events, SOS workflow, incident access controls, GPS integrity signals, risk actions, support cases and disputes. High-impact automatic actions require explainability, review and appeal paths appropriate to policy.

### Notifications

Template/version management, user preferences, push/SMS/in-app channels, delivery attempts, retries and deduplication. Notifications inform state; they do not become the source of truth.

## 4. Data and consistency

- PostgreSQL is the transactional source of truth; PostGIS supports geographic queries.
- Durable domain records use full opaque IDs, UTC timestamps and actor/correlation metadata.
- Ride transitions, offer acceptance, fare finalization and ledger postings use database transactions and constraints.
- Commands carry idempotency keys. Unique constraints prevent duplicate trip completion, provider webhook and payout posting.
- Use an outbox pattern to publish notifications and worker jobs only after the associated transaction commits.
- Ledger records are append-only. Corrections are compensating entries with links and reasons.
- Cache is an optimization, never the authority for money, ride ownership or safety state.
- Analytics consume privacy-minimized events or replicas; analytics outages must not block ride operations.

## 5. API and client contracts

- Introduce `/api/v1` while preserving old prototype routes temporarily through adapters.
- Separate commands from public read models. Never serialize internal database/domain dictionaries directly.
- Use authenticated actor context and resource-level authorization.
- Return machine-readable error codes and current authoritative state for retry recovery.
- Support idempotency, optimistic concurrency/version fields and bounded pagination.
- WebSocket or managed real-time updates improve experience; polling remains a low-connectivity fallback.

## 6. Deployment and operations

Begin with one API deployment, one worker deployment and managed PostgreSQL in a single launch region, with encrypted backups and tested restore procedures. Add replicas, regional failover or service extraction only after measured need and recovery requirements are approved.

Deployments require health/readiness checks, structured logs, metrics, traces, alerting, schema migration controls and a rollback strategy. Personal data, precise locations, credentials and payment details must be excluded from telemetry.

## 7. Safe migration path

1. **Characterize the prototype.** Add tests around current route behavior and record known defects without changing contracts accidentally.
2. **Stabilize packaging/configuration.** Add reproducible dependencies, namespaced settings, CI and production-safe defaults.
3. **Introduce domain interfaces.** Place ride, driver and wallet persistence behind repositories while the in-memory implementation still works.
4. **Add PostgreSQL alongside memory.** Create migrations and durable models. Backfill only non-production prototype data if useful; otherwise start clean.
5. **Move rides and offers transactionally.** Preserve old endpoints with adapters while new `/api/v1` DTOs and state-machine commands become authoritative.
6. **Replace wallet aggregates with a ledger.** Do not migrate unsafe balances as trusted value without reconciliation and leadership approval. Add immutable postings and derived views.
7. **Add identity and authorization before exposure.** Old anonymous mutation endpoints must not remain internet-accessible.
8. **Introduce workers/outbox.** Move offer expiry, fallback dispatch, notifications and provider callbacks to reliable jobs.
9. **Add provider adapters and clients.** Keep external integrations behind tested contracts and feature flags.
10. **Retire compatibility code.** Remove old in-memory paths only after parity tests, data reconciliation, monitoring and rollback windows succeed.

This path evolves working code rather than rewriting the repository wholesale.

### Approved Mission 2 persistence boundary

The application layer depends on `RideRepository` and the explicitly temporary
`LegacyWalletRepository`, not on global dictionaries or a database library.
Repository adapters own storage and return isolated copies so callers cannot
silently mutate persisted state. FastAPI dependencies provide the currently
configured adapters at the HTTP boundary, while service functions also accept an
explicit repository for deterministic tests and non-HTTP callers.

The PostgreSQL migration path is:

1. Add PostgreSQL adapters that implement the existing contracts without changing
   routes or domain services.
2. Run the same repository contract and API parity tests against memory and
   PostgreSQL adapters.
3. Introduce an explicit transaction/unit-of-work boundary for operations that
   span ride and financial state before switching authoritative writes.
4. Select adapters through validated environment composition, migrate only
   trusted/reconciled data, and retain a time-bounded rollback path.
5. Remove in-memory production composition only after concurrency, failure,
   migration and recovery evidence passes.

The legacy wallet contract is a quarantine boundary, not approval of the current
accounting model. Prototype wallet balances must not be imported as trusted value;
the later ledger mission replaces this contract with immutable postings and
derived balances.

### Mission 3 PostgreSQL persistence platform

AYO uses a reusable synchronous persistence kernel based on PostgreSQL 17,
SQLAlchemy 2.x Core and Psycopg 3. Domain models and existing repository protocols
remain independent of SQLAlchemy. The kernel owns engine construction, bounded
pooling, validated namespaced configuration, safe health probing, structured
database events and transaction lifecycle.

`SqlAlchemyUnitOfWork` composes named, typed repository factories around one
connection and transaction. Product modules add their repositories to composition;
they do not inherit a generic CRUD repository. This provides a common transaction
platform for future Ride, Driver, Dispatch, Delivery, Marketplace and other modules
without erasing their domain-specific contracts.

The initial PostgreSQL adapters are:

- `PostgresRideRepository`, implementing the existing ride contract with an
  internal UUID key, compatibility public ID, UTC timestamps and integer optimistic
  version.
- `PostgresLegacyWalletRepository`, a non-authoritative JSON compatibility store
  used only to prove the persistence seam. It is not a ledger and cannot establish
  trusted opening balances.

PostgreSQL metadata currently defines the proposed tables solely for adapter and
test development. Production startup never calls `create_all`; no production schema
or migration has been authorized. Existing routes continue using the in-memory
composition until migrations, data policy, integration verification and a separate
cutover approval are complete.

## 8. Future extraction boundaries

Express, Eat, Marketplace and Home may share identity, payment-provider adapters, notifications, support and platform observability, but each needs its own order/lifecycle domain. Do not force those products into the ride aggregate.

AYO Pay is a regulatory and architectural boundary. Future stored-value or payment services require explicit leadership strategy and Ethiopian legal/licensing verification. The ride driver's internal ledger must not be presented as independently issued electronic money.

Extraction is an evidence-based migration, not an architectural milestone by itself. A module may become an independently deployed service only after CTO review and CEO approval confirms at least one justified trigger: materially different scaling, a stronger security/isolation boundary, clear independent team ownership, or operational/reliability evidence that deployment separation improves customer outcomes.

## Smart Arrival, Rider Readiness and Waiting boundary

Mission 20 is a disabled-by-default module inside the modular monolith. It consumes the
authoritative Active Ride identity/version and Dynamic Pickup recommendation/version,
then produces deterministic arrival, readiness, waiting and consequence-suppression
evidence. It never transitions the ride lifecycle or performs a financial action.

Its PostgreSQL boundary uses append-oriented arrival/readiness/evidence records,
versioned immutable policy snapshots, optimistic waiting-session state, typed pause and
invalidation events, notification evidence and the shared transactional outbox.
Configuration resolution uses explicit effective dates and deterministic contextual
precedence and fails closed on missing or equally specific conflicting policies.
External maps, landmarks, airports and notification transports remain provider-neutral
inputs or intents. Migration 0014 is reversible; production activation remains gated on
PostgreSQL 17 validation and separate CTO/CEO review.

Landmark guidance may expose multiple verified bilingual named entrances and exact
stopping positions. Precise rider walking guidance remains an injected, expiring route
projection rather than Mission 20 map authority. A future verified pickup-photo field is
limited to opaque metadata and accessible descriptions; image storage, moderation,
provider selection and publication are not part of Mission 20. CTO/CEO approval covers
local preservation only: PostgreSQL 17 certification remains pending, the feature flag
must remain false, and production activation, public exposure, deployment and push are
prohibited.

## Proposed AI Customer Support boundary

Mission 21 proposes extending the existing PostgreSQL Support module with a deterministic
Support Case Orchestrator, purpose-scoped evidence gateway, provider-neutral untrusted
language adapter, least-privilege tool broker, emergency router and typed human/specialist
queues. AI may propose language and allow-listed recommendations but cannot transition
cases or become authority for safety, identity, fraud, restrictions, pricing, recovery,
money movement, payouts or legal conclusions. See
`MISSION_21_AI_CUSTOMER_SUPPORT_ARCHITECTURE.md` and its linked design artifacts.

The proposal is documentation only. No runtime, schema, dependency, provider, public
route, financial action or activation is authorized pending CTO/CEO architecture review.

Future support UX may consume versioned plain-language “why” explanations, canonical
role-redacted timelines, coarse privacy-safe visual replay and idempotent appeals with
governed evidence metadata. These remain presentation seams: owning domains retain
evidence authority, Support applies purpose/RBAC redaction, and replay cannot expose raw
GPS trails or restricted safety, identity or fraud material.

The same boundary preserves provider-neutral future adapters for voice/optional voice AI,
video, screen sharing, co-browsing and purpose-expiring live support location. Explicit
participant grants support family and diaspora cases. Versioned knowledge, quality and
satisfaction projections remain advisory analytics; any learning from human-reviewed
resolutions is prohibited until separately approved and governed. None of these seams
authorizes media capture, providers, UI, tracking, automated sanctions or model authority.

## Approved Rider and Driver UX architecture

Mission 22 defines role-specific presentation machines over the existing server-
authoritative Immediate, Scheduled, Active Ride, Dynamic Pickup and future certified
Mission 20 projections. Clients render versioned snapshots, interpolate display-only
countdowns from server time, submit idempotent commands and recover through snapshot
reconciliation. They cannot advance lifecycle, verify arrival, authorize waiting,
calculate money, determine blame or become safety/AI authority.

The presentation boundary supports bilingual landmark entrances, precise walking and
driver stopping guidance, accessibility, airport Standard/Premium separation, Ethiopian
complex pickups and low-network/offline recovery. Mission 20 screens remain hidden while
`ARRIVAL_WAITING_ENABLED` is false and until PostgreSQL certification plus separate
activation approval. See `MISSION_22_RIDER_DRIVER_UX_ARCHITECTURE.md`.

CTO approval covers documentation architecture only. It does not approve production
code, routes, providers, deployment or activation. Mission 20 still requires successful
PostgreSQL integration, migration upgrade/downgrade, recovery, restart and concurrency
certification before its flag can be considered for separate activation approval.

## Approved Dispatch Optimization and Marketplace Health architecture

Mission 23 coordinates existing dispatch authorities through a versioned deterministic
policy boundary and adds a read-only advisory Marketplace Health Engine. Immediate,
Scheduled, Smart Pre-Dispatch, Airport, Active Ride, Mission 20, Availability, Eligibility,
Safety, Pricing, Incentives and Support retain their approved ownership. Mission 23 is not
a second dispatcher and cannot assign, break commitments, price, bonus, punish, restrict
or activate Mission 20. See `MISSION_23_DISPATCH_OPTIMIZATION_ARCHITECTURE.md`.

CTO approval covers architecture documentation only. Implementation, migrations,
providers, production routes and activation require separate approval. AI remains
advisory, and Mission 20 remains disabled pending all PostgreSQL certification gates.

## Approved Identity, Verification and Trust architecture

Mission 24 extends the existing PostgreSQL identity/session foundation with a deterministic
purpose-specific assurance orchestrator and separate driver onboarding, document, vehicle,
eligibility, Trusted Driver, business/participant and appeal boundaries. Authentication,
proofing and eligibility remain distinct. AI/OCR may extract, classify or recommend but
cannot approve identity/documents, recover or suspend accounts, grant Trusted/Airport
eligibility or bypass Safety/Fraud/Authorization. See
`MISSION_24_IDENTITY_VERIFICATION_TRUST_ARCHITECTURE.md`.

Approval covers documentation architecture only. Providers, proofing operations,
biometrics, migrations, production routes and activation remain separately gated.

## Approved Pricing and Marketplace Economics architecture

Mission 25 defines a deterministic server-authoritative Pricing boundary for versioned
estimates, final fares, corrections, commission and approved financial-policy
interpretation. Incentives remains a separate eligibility/programme authority;
Customer Recovery authorizes approved remedies; Payments collects/reconciles; and
Wallet/Ledger alone moves value. Mission 20 supplies arrival, waiting and consequence-
readiness evidence only and never calculates a fee. See
`MISSION_25_PRICING_MARKETPLACE_ECONOMICS_ARCHITECTURE.md`.

Approval covers documentation architecture only. It contains no numeric Ethiopian
price, duration, fee, tax, commission,
incentive or surge policy. No runtime, migration, provider, public route, financial
action or activation is authorized. AI and Marketplace Health
remain advisory only. Mission 20 remains disabled and PostgreSQL-certification blocked.

## Approved Payments, Wallet, Ledger and Financial Integrity architecture

Mission 26 defines an immutable PostgreSQL double-entry subledger as the exclusive
future authority for money movement. Pricing calculates approved amounts; Payments owns
external attempts and provider evidence; Reconciliation compares provider, bank, cash
and ledger facts; Wallets are derived role-specific projections; Customer Recovery
authorizes approved remedies; Finance controls accounting and manual adjustments. AI has
no authorization or execution capability. See
`MISSION_26_PAYMENTS_WALLET_LEDGER_FINANCIAL_INTEGRITY_ARCHITECTURE.md`.

The mutable legacy wallet remains quarantined prototype behavior and cannot seed trusted
opening balances without reconciliation and approval. ETB is the primary currency;
multi-currency and AYO Pay are future legal/regulatory boundaries. No runtime, migration,
provider, wallet, ledger, transaction, public route or activation is authorized pending
separate implementation approval. Mission 20 remains disabled and certification-blocked.

## Implementation Phase 1 planning boundary

The proposed Phase 1 plan integrates approved architecture as one complete Immediate
Standard cash ride before advanced activation. It sequences PostgreSQL/audit,
authentication, driver eligibility, ride/pickup, Immediate Dispatch, Active Ride,
Pricing, immutable cash accounting, mobile MVP and support/operations with independent
quality and approval gates. See `IMPLEMENTATION_PHASE_1_MASTER_PLAN.md`. The plan creates
no Mission 27 and authorizes no implementation, provider, migration or production use.

### Increment 2 authentication and ownership checkpoint

The provider-neutral authentication/session/RBAC foundation now includes reusable
server-resolved ownership enforcement. Ownership-required routes deny when the resolver
is absent or the authenticated identity is not the owner, and denial is audited without
revealing another identity. The verified subject resolver is no longer dispatch-specific.
No provider, public authentication route, business workflow or production activation is
authorized. See `IMPLEMENTATION_INCREMENT_2_AUTH_SECURITY_FOUNDATION.md`.

### Increment 3 driver trust checkpoint

The driver trust domain now separates driver onboarding, immutable document-evidence
references, vehicle approval, driver-to-vehicle authorization and versioned eligibility.
PostgreSQL and authenticated server context are authoritative; human reviewers retain all
approval authority and eligibility fails closed. Capability metadata does not grant
Trusted Driver or Airport eligibility. See
`IMPLEMENTATION_INCREMENT_3_DRIVER_TRUST_FOUNDATION.md`. No public activation is approved.

### Increment 4 canonical ride-request checkpoint

The canonical ride-request domain now owns only authenticated Immediate Standard
pre-dispatch requests, pickup/destination definitions, service-zone validation,
pre-assignment cancellation and privacy-minimised events. `READY_FOR_DISPATCH` is evidence
readiness, not assignment and does not invoke Dispatch. Configuration and PostgreSQL are
authoritative; AI and clients cannot validate ownership or product eligibility. See
`IMPLEMENTATION_INCREMENT_4_CANONICAL_RIDE_REQUEST.md`. No public route is activated.

#### Approved enterprise ownership reconciliation — 2026-07-23

R1 Passenger Mobility is the sole logical enterprise owner of canonical Ride Request.
The Increment 4 module and persistence model are classified as the migration source: they
remain the current PRE-PRODUCTION implementation evidence and must not be deleted,
reinterpreted, or duplicated. P1 AYO Ride owns product experience/orchestration; Dispatch,
Pricing, Route/Navigation, Trip execution, Tracking, Identity, Household, and Finance retain
their specialist authorities. CTO Architecture Review and Ibrahim Hambentu Shibiru,
Founder & CEO, approved this architecture on 2026-07-23 for PRE-PRODUCTION ONLY. It
authorizes no code, schema, migration, runtime, or activation change. See
`ADR_R1_MOBILITY_CANONICAL_RIDE_REQUEST_OWNERSHIP_2026-07-23.md`.

### Increment 5 Immediate Dispatch handoff and localization checkpoint

A durable one-way handoff now carries an authoritative `READY_FOR_DISPATCH` Immediate
Standard request into the existing Immediate Dispatch domain. Dispatch rechecks current
Driver Trust evidence, ranks suitable candidates by pickup cost first, owns bounded
sequential offers and creates a PostgreSQL-locked assignment. Ride Request never assigns
a driver. Cancellation/acceptance races, duplicate delivery, response loss and restart
recover from transactional authoritative state.

The shared localization boundary persists BCP 47 preferences and versioned language-pack
metadata while domains retain stable reason codes and translation keys. Language choice
is presentation-only; critical legal, safety, identity, pricing, financial and emergency
wording requires human review. See
`IMPLEMENTATION_INCREMENT_5_DISPATCH_HANDOFF_LOCALIZATION.md`. No public route, provider,
Active Ride, Pricing, Mission 20 or production feature is activated.

### Increment 6 Active Ride lifecycle checkpoint

Active Ride now accepts a one-way start only from an authoritative Immediate Dispatch
assignment and owns the canonical post-assignment state machine, immutable sequenced
timeline, optimistic commands, PostgreSQL locks, replay verification, recovery projection
and transactional outbox. Explicit driver/rider cancellation and support/system
interruption states record facts without financial or blame authority. Ride Request and
Dispatch retain their existing responsibilities.

Versioned completion and progress events preserve inactive, idempotent consumer seams for
AYO Wallet/Ledger, AYO Status, AYO Family, Growth Engine, Driver Support Bonus and Trust
Engine. These systems receive no activation or authority from the seam. See
`IMPLEMENTATION_INCREMENT_6_ACTIVE_RIDE_LIFECYCLE.md`. Mission 20 remains disabled.

### Increment 7 Pricing calculation checkpoint

Pricing now owns a versioned, effective-dated ETB calculation boundary for synthetic
Immediate Standard policies, immutable estimates and Rider acceptance, completed-ride
final calculation, transparent Rider/Driver projections and append-only corrections.
All money uses integer minor units and deterministic rounding. Route providers supply
evidence only; clients and AI cannot provide authoritative totals.

Each Pricing result includes a formula-versioned immutable lineage snapshot covering
policy approval/publication, route input sources and provider version, all numeric operands,
component and rounding derivation, canonical input hash, correction predecessor and event
correlation/causation. The stored result is reproducible solely from that snapshot. Ledger,
Wallet, Tax, Finance, Audit and regulatory reporting must consume the authoritative Pricing
output without recalculating it; opaque AI reasoning is never a financial input.

Permanent Financial Traceability is carried as immutable data, not reconstructed later.
Pricing estimates preserve Ride Request and Estimate references; completed and corrected
calculations preserve Ride Request, Dispatch Handoff, Assignment, Active Ride, Estimate and
Calculation references. Corrections append a predecessor-linked record. The persistence layer
now fails closed on missing, mismatched, forged or cross-ride lineage, and the Ride-ID
journey projection returns the complete explicit chain for Support, Finance and Audit without
changing any upstream authority. Future Ledger, Wallet and Settlement artifacts must extend
the same chain with their own immutable IDs.

Pricing produces no payment authorization, cash proof, ledger posting, wallet balance,
refund, bonus, waiting or cancellation consequence. Transactional events expose inactive
consumer seams only. See `IMPLEMENTATION_INCREMENT_7_PRICING_FOUNDATION.md`. No numeric
production tariff or public feature is activated; Mission 20 remains disabled.

# Authentication architecture requirements

Authentication uses PostgreSQL as durable identity/session authority and the
approved Audit, Session, Rate-Limit, Migration and Unit-of-Work foundations.
Identity, credentials, authentication methods, roles/permissions, sessions,
devices, verification, recovery and product profiles remain separate modules and
tables. Rider, driver, staff, administrator and service identities cannot be
selected or elevated by client-controlled claims.

AYO supports multiple device sessions per identity. Every session has an opaque
device-session reference, token family, assurance level and risk state. One-device
logout revokes only that session; logout-all, suspension, security reset and
approved administrator action revoke the applicable session set durably. Device
trust combines server-observed history, authentication strength and privacy-safe
risk references; a client device name alone is never trust evidence.

Access tokens are short-lived. High-entropy refresh tokens rotate on every use;
only fingerprints are stored. Reuse of consumed refresh material is a replay signal
that revokes its token family and requires a safe reauthentication path. Absolute
and idle expiration are server enforced, with bounded clock skew. Signing and
verification contracts must support key rotation, but production keys require an
approved key-management design.

Staff and administrator access requires phishing-resistant authentication before
production. Sensitive administration, finance, payout, recovery and security
changes require recent step-up authentication. Remember-me may extend only the
refresh session within approved absolute limits; it never creates a long-lived
access token or bypasses risk, revocation or step-up controls.

Suspicious-login evaluation accepts minimized, privacy-safe IP/device risk
references and versioned signals, not raw invasive fingerprints. The deterministic
rules foundation must remain compatible with a future reviewed risk-scoring system;
no AI or score may silently authenticate, authorize or block a person without
approved policy and human/appeal safeguards.

# Rider booking evidence boundary

The Milestone 4 runtime composes existing authorities. Provider-neutral Route Intelligence
returns normalized endpoints, accuracy, confidence, route geometry, distance, ETA, traffic,
restriction and toll evidence. Service Zone independently validates claimed and normalized
endpoints. Pricing creates the authoritative expiring quote. Authenticated confirmation stores
an immutable evidence binding and invokes canonical Ride Request; success stops at
`ready_for_dispatch`.

Search/preview remain public under Explore Before Commitment. Confirmation requires the
canonical Rider subject and `ride_request.create`. Client identity, safety verification,
service zone, pricing policy, fare factors and totals are never authoritative. Stable
idempotency and server expiry support safe weak-network retry. The waiting response explicitly
states dispatch has not started. See
`IMPLEMENTATION_INCREMENT_19_MILESTONE_4_COMPLETE_RIDER_BOOKING_RUNTIME.md`.

# Canonical Immediate Dispatch runtime

Milestone 5 extends the canonical request through `ready_for_dispatch → searching → offering →
assigned`. AYO Route Intelligence supplies bounded pickup route/ETA/traffic/restriction evidence;
Dispatch never contacts providers. Driver Trust and the durable Worker Session authority enforce
driver/vehicle eligibility and one active earning capability. Only an authenticated, online Ride
Driver session in the matching service zone is offer/accept eligible.

Hard safety/role/freshness filters precede deterministic pickup-ETA-first scoring. Reliability,
cancellation history, workload and fair-opportunity evidence are bounded, versioned secondary
signals. PostgreSQL locks, versions, actor-scoped idempotency and unique indexes guarantee one
exclusive offer and canonical assignment. Transactional outbox intents notify rider/driver while
polling remains authoritative. The runtime stops before navigation and Active Ride.

The legacy duplicate Dispatch ride-creation aggregate is not an authority for Milestone 4
bookings. See `IMPLEMENTATION_INCREMENT_19_MILESTONE_5_INTELLIGENT_DRIVER_DISPATCH.md`.

# Request Access & Interaction Provenance architecture

The approved PRE-PRODUCTION governance architecture is indexed at
`AYO_REQUEST_ACCESS_INTERACTION_PROVENANCE_ARCHITECTURE.md` with ADR
`ADR_REQUEST_ACCESS_INTERACTION_PROVENANCE_2026-07-23.md`.

It is a shared supporting capability for channel-adapter contracts, domain-owned
channel-action declarations and immutable interaction provenance. It does not own
Identity, delegation, Ride Request, availability or fulfilment. Architecture governance
was approved on 2026-07-23 by OpenAI ChatGPT, Project CTO (Technical Oversight), and
Ibrahim Hambentu Shibiru, Founder & CEO.

The architecture-gate status was **APPROVED FOR PRE-PRODUCTION GOVERNANCE ONLY**, with
implementation blocked pending separate authorization. That historical state is
preserved.

On 2026-07-23, OpenAI ChatGPT, Project CTO (Technical Oversight), and Ibrahim Hambentu
Shibiru, Founder & CEO, separately authorized **Request Access & Interaction Provenance
Increment 1** for PRE-PRODUCTION implementation. The approved ADR remains authoritative.
Production activation and later increments are not approved. See
`REQUEST_ACCESS_INTERACTION_PROVENANCE_INCREMENT_1_IMPLEMENTATION_AUTHORIZATION_2026-07-23.md`.

Increment 1 is implemented in the modular monolith at additive revision
`20260723_0051`. The shared component owns only typed adapter/capability contracts,
explicit continuity and immutable interaction provenance. It does not alter Ride Request
or another canonical business aggregate. Current state is **IMPLEMENTED - POSTGRESQL
CERTIFICATION INCOMPLETE**; production and real channel activation remain prohibited.

# Enterprise Experience & Release Governance architecture

The proposed enterprise profile is indexed at
`AYO_ENTERPRISE_EXPERIENCE_RELEASE_GOVERNANCE_ARCHITECTURE.md` with ADR
`ADR_ENTERPRISE_EXPERIENCE_RELEASE_GOVERNANCE_2026-07-23.md`.

It creates no new capability. Enterprise Change Management coordinates release plans;
Knowledge, S9 Information Stewardship, Authority Routing, human authorities,
Localization and owning Products/domains retain their existing responsibilities.
Existing governed Intelligence remains advisory.

Status: **READY FOR CTO AND FOUNDER & CEO ARCHITECTURE REVIEW**. Implementation and
production activation are not authorized.

# P2 AYO Eat Merchant Decision Lifecycle

Architecture index entry:

- package: `AYO_P2_EAT_INCREMENT_2_MERCHANT_DECISION_ARCHITECTURE.md`;
- ADR: `ADR_P2_EAT_MERCHANT_DECISION_LIFECYCLE_2026-07-23.md`;
- authorization:
  `AYO_P2_EAT_INCREMENT_2_IMPLEMENTATION_AUTHORIZATION_2026-07-23.md`;
- canonical owner: Merchant Order Management;
- status: APPROVED on 2026-07-23;
- implementation: AUTHORIZED for Increment 2 PRE-PRODUCTION ONLY; and
- production/future increments: NOT AUTHORIZED.

No separate Merchant Acceptance domain is admitted.

# P2 AYO Eat Preparation Lifecycle refinement

- package: `AYO_P2_EAT_INCREMENT_3_PREPARATION_ARCHITECTURE.md`;
- ADR: `ADR_P2_EAT_PREPARATION_LIFECYCLE_2026-07-23.md`;
- canonical owner: existing Preparation / Merchant Preparation;
- decision: additive Preparation case consuming accepted Merchant Decision evidence,
  while Universal Ordering retains the Commerce Order;
- status: APPROVED on 2026-07-23; and
- implementation: Increment 3 AUTHORIZED (PRE-PRODUCTION ONLY); production and future
  increments NOT AUTHORIZED.

No P2-specific Preparation capability is admitted.

## Increment 3 approval closure

- approved: 2026-07-23;
- CTO: OpenAI ChatGPT, Project CTO (Technical Oversight);
- Founder: Ibrahim Hambentu Shibiru, Founder & CEO;
- architecture/ADR: APPROVED;
- implementation: Increment 3 AUTHORIZED (PRE-PRODUCTION ONLY);
- authorization:
  `AYO_P2_EAT_INCREMENT_3_IMPLEMENTATION_AUTHORIZATION_2026-07-23.md`; and
- production/future increments: NOT AUTHORIZED.

Readiness remains separate from assignment, pickup, custody and delivery.

Increment 3 is implemented in the modular monolith through additive revision
`20260723_0054`. The canonical case consumes accepted Merchant Decision evidence and
owns only Preparation state/evidence. Current state is **IMPLEMENTED IN PRE-PRODUCTION;
POSTGRESQL CERTIFICATION INCOMPLETE**. Production and Increment 4 remain unauthorized.

# P2 AYO Eat Readiness-to-Handoff profile

- package: `AYO_P2_EAT_INCREMENT_4_READINESS_HANDOFF_ARCHITECTURE.md`;
- ADR: `ADR_P2_EAT_READINESS_HANDOFF_BOUNDARY_2026-07-23.md`;
- decision: no new capability; compose existing Preparation, Courier Dispatch,
  Courier Pickup, Custody and Delivery authorities through versioned evidence;
- status: APPROVED on 2026-07-24;
- authorization:
  `AYO_COURIER_PICKUP_INCREMENT_1_IMPLEMENTATION_AUTHORIZATION_2026-07-24.md`;
- Increment 1: IMPLEMENTATION AUTHORIZED — PRE-PRODUCTION ONLY; and
- production/successor increments: NOT AUTHORIZED.

# Courier Dispatch refinement and launch admission

- package: `AYO_COURIER_DISPATCH_ARCHITECTURE_LAUNCH_ADMISSION_PACKAGE.md`;
- ADR: `ADR_COURIER_DISPATCH_REFINEMENT_2026-07-23.md`;
- ownership/lifecycle/events:
  `AYO_COURIER_DISPATCH_OWNERSHIP_LIFECYCLE_EVENT_MODEL.md`;
- canonical owner: existing Courier Dispatch;
- decision: refine offers, assignment recovery and pre-pickup cancellation without
  absorbing Preparation, Pickup, Custody, Delivery or eligibility source facts;
- status: APPROVED on 2026-07-23;
- authorization:
  `AYO_COURIER_DISPATCH_INCREMENT_1_IMPLEMENTATION_AUTHORIZATION_2026-07-23.md`;
- Increment 1: IMPLEMENTATION AUTHORIZED — PRE-PRODUCTION ONLY; and
- production/successor increments: NOT AUTHORIZED.

Increment 1 is implemented additively at revision `20260723_0055`. Current technical
state is **IMPLEMENTED IN PRE-PRODUCTION; POSTGRESQL CERTIFICATION PENDING**. This does
not authorize production or Increment 2.

# Courier Pickup refinement and launch admission

- package: `AYO_COURIER_PICKUP_ARCHITECTURE_LAUNCH_ADMISSION_PACKAGE.md`;
- ADR: `ADR_COURIER_PICKUP_REFINEMENT_2026-07-24.md`;
- canonical owner: existing Courier Pickup;
- decision: preserve its four-state post-assignment/pre-custody lifecycle and propose
  assignment-attempt identity, append-only corrections and one terminal outcome;
- status: READY FOR CTO AND FOUNDER & CEO ARCHITECTURE REVIEW; and
- implementation/production: NOT AUTHORIZED.
