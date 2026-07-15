# AYO Architecture

Status: target architecture proposal grounded in the repository as inspected on 2026-07-14. Product-policy choices remain subject to Founder and leadership approval.

This architecture is subordinate to `AYO_CONSTITUTION.md` and must preserve a credible path to 10 million users, governed first-class AI and independently scalable module boundaries.

## 1. Current architecture

AYO currently has an early synchronous FastAPI prototype:

```text
HTTP request
  -> BACKEND/routes
  -> BACKEND/services
  -> module-level Python dictionaries
```

`BACKEND/main.py` always registers the legacy ride, driver-offer, ride-status and wallet routers. Mission 12 added an isolated typed immediate-dispatch domain core, and Mission 13 added PostgreSQL 17 persistence, transactional repositories, immutable audit writes, a transactional outbox, RBAC contracts and bounded recovery. Mission 14 can register the secure dispatch and internal-worker routers only through an explicit feature flag that defaults off and is prohibited in production configuration. Controlled activation requires explicit PostgreSQL, asymmetric-token-verifier, publisher and worker dependencies. Verified identity/session state and database RBAC are authoritative; token role claims are rejected. The outbox and recovery coordinators are scheduler-neutral, use bounded work and PostgreSQL locking, and are not started on import. No external identity, messaging or telemetry provider is connected. The in-memory dispatch repository and local publisher are test-only; the unsafe legacy `rides` path is not authoritative dispatch storage. `ayo_ai.py` remains disconnected from dispatch.

Mission 15 adds an unregistered deterministic Marketplace Intelligence module. It consumes privacy-minimized aggregate snapshots, evaluates immutable configurable rules, persists replayable advisory decisions and simulations, and emits safe metrics/logs. It cannot assign drivers, change fares, block dispatch or invoke AI. Dispatch remains authoritative; marketplace failure degrades to no recommendation. No production scheduler, API or data source is connected.

The repository has a locked Python environment, automated regression/contract tests, linting, security scanning and GitHub Actions CI. It now also contains an early Expo rider-interface prototype in `AYO-Mobile/`, including a provider-neutral destination-search seam; this is not a production client and has no authenticated persistence, live maps or provider connection. The system still has no deployed persistent database, external provider integrations, production mobile/web clients, background workers, deployment pipeline or production infrastructure. Existing product design documents remain aspirations rather than executable specifications unless explicitly identified as implemented.

### Current strengths

- Clear route/service separation for a prototype.
- Input validation with Pydantic.
- Basic ride-status transition checks.
- Decimal use inside the wallet service.
- Eligibility filtering and understandable dispatch code.

### Current constraints

- Memory state disappears on restart and diverges across workers.
- Mutable dictionaries provide no transactions, concurrency control or durable audit trail.
- Financial completion is caller-controlled and non-atomic.
- Dispatch timeouts and fallback candidates do not execute.
- Internal dispatch fields are returned by the public status endpoint.
- The provided virtual environment has no application dependencies.

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
