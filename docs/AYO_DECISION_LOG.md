# AYO Decision Log

## 2026-07-15 — Mission 9 support foundation (approved)

Problem: provide safe, low-cost support that can later serve AI chat/voice and human agents without high-risk AI authority or provider lock-in.

Decision: use a bounded PostgreSQL 17 workflow in the modular monolith, append-only case events/messages/AI evidence, hybrid orchestration, explicit green/yellow/red actions, ownership/assignment/queue authorization, optimistic concurrency and transactional audits. Add six human queue permissions; exclude them from the AI permission set. Add no provider, broker, Redis or vector database.

Alternatives: a minimal case table lacks privacy/audit controls; full/event-driven or third-party ticketing adds premature complexity/lock-in; AI-only is unsafe; human-only raises cost and friction. Revisit on measured volume, queue latency, search quality or integration economics.

Risks: anonymous recovery, queue policy, emergency procedures, language/voice accuracy, transcript consent and Ethiopian retention/legal-hold rules remain unapproved. Provider/model selection requires a separate decision.

This log prevents proposals from becoming policy by accident. Dates use ISO format. Decision owners are the Founder and AYO leadership unless another accountable owner is explicitly assigned.

`AYO_CONSTITUTION.md` is the highest project authority. Decisions recorded here are valid only when they comply with it.

## A. Approved permanent decisions

These decisions are supplied as permanent AYO principles and govern engineering work.

| ID | Date recorded | Decision | Consequence |
|---|---|---|---|
| AP-001 | 2026-07-14 | Solve problems, not features. | Work starts from a user/driver/operations problem and measurable outcome. |
| AP-002 | 2026-07-14 | Reliability, safety and driver earnings are more important than being the cheapest. | Price competition cannot override safety, reliability or sustainable driver outcomes. |
| AP-003 | 2026-07-14 | Immediate rides prioritize the closest suitable available driver and fast pickup. | Geographic/eligibility filtering and pickup ETA lead immediate dispatch. |
| AP-004 | 2026-07-14 | Scheduled rides use separate matching logic and may optimize reliability in advance. | Scheduled rides are a separate strategy, not a delayed immediate request. |
| AP-005 | 2026-07-14 | Support smart pre-dispatch near the end of a driver's current trip. | Architecture preserves predicted-completion matching, with current-trip and safety protections. |
| AP-006 | 2026-07-14 | Dispatch is staged: cheap geographic filtering first, paid routing only for a shortlist. | Provider cost and latency are bounded and observable. |
| AP-007 | 2026-07-14 | Smart Pickup uses verified, recommended and restricted classifications. | Pickup data has provenance, versioning, operating constraints and auditability. |
| AP-008 | 2026-07-14 | Build for Ethiopian cash, licensed payment-provider integrations, weak networks, mixed devices and local regulations. | Cash and degraded connectivity are core paths; provider/legal assumptions require verification. |
| AP-009 | 2026-07-14 | The driver balance is an internal AYO accounting ledger, not independently issued electronic money. | Product wording and architecture must not imply unapproved stored-value issuance. |
| AP-010 | 2026-07-14 | Every financial movement has an immutable ledger record. | Posted history is append-only; corrections use compensating entries. |
| AP-011 | 2026-07-14 | Security, privacy and legal compliance are never sacrificed for speed. | Unresolved critical controls block release. |
| AP-012 | 2026-07-14 | Keep UX extremely simple while the underlying system remains powerful. | Complexity belongs in reliable system behavior, not user decision burden. |
| AP-013 | 2026-07-14 | Build one complete production-quality ride flow before many incomplete features. | Ride vertical and operations gates precede super-app expansion. |
| AP-014 | 2026-07-14 | Major decisions remain with Founder and leadership. | Unapproved product policy must be labeled as a proposal or verification item. |
| AP-015 | 2026-07-14 | Adopt `docs/AYO_CONSTITUTION.md` as the highest authority for the AYO project. | Every engineering decision and code change requires constitutional compliance; lower-level conflicts are resolved in its favor. |
| AP-016 | 2026-07-14 | Establish the leadership structure: CEO owns vision, strategy and final business decisions; CTO owns architecture, quality, security, scalability and engineering approvals; Codex is responsible for implementation only. | Major architecture/product proposals require documented CTO review and CEO approval before implementation. Technical decisions must state rationale, alternatives and risks first. |
| AP-017 | 2026-07-14 | Amend Constitution Article 1: never build technology merely because it is possible; build it to solve a real customer problem. | Every feature proposal must clearly identify the problem, beneficiary, success measure, risks and simpler alternatives. Unclear proposals must not be built. |
| AP-018 | 2026-07-14 | Adopt `docs/AYO_ENGINEERING_WORKFLOW.md` as the mandatory ten-step process for every mission. | Research and option comparison precede CTO/CEO approval; approved architecture and risk analysis precede production code; tests, security/performance verification and documentation are mandatory; work stops for approval before the next mission. |
| AP-019 | 2026-07-14 | Add Tiered Secure Computing as a constitutional security architecture principle. | AYO uses standard secure controls for ordinary workloads, stronger isolation for highly sensitive workloads, and attested confidential computing only where its added protection justifies cost and complexity. Provider/deployment choices still require CTO review and CEO approval. |
| AP-020 | 2026-07-15 | CTO and CEO approve AYO's initial modular-monolith architecture: clean internal FastAPI modules over PostgreSQL/PostGIS with queue/cache/outbox and provider adapters; modules are not separately deployed initially. | Microservices require evidence from traffic, security risk, team ownership or operations. Use open standards/provider-neutral interfaces, preserve cloud portability, keep AWS Cape Town provisional pending Ethiopian latency and actual pricing, limit confidential computing to justified workloads, and deploy no infrastructure under this decision. |
| AP-021 | 2026-07-15 | CTO and CEO approve “Build systems that can survive success” and “Measure first. Build second. Optimize third.” as permanent engineering principles. | Every architecture decision must pass the ten-question survivability review or be redesigned. Hypothetical optimization and complexity without measurable benefit are prohibited; simple, reliable, well-tested systems are preferred. |
| AP-022 | 2026-07-15 | CTO and CEO approve smart, fair and transparent pricing as a permanent product principle. | Pricing is server-controlled and versioned, uses only approved factors, protects reliability/safety/sustainable driver earnings, records explanations, prohibits protected-characteristic inputs and emergency exploitation, and requires Ethiopian market/cost research plus separate CTO/CEO approval before final fare values are implemented. |
| AP-023 | 2026-07-15 | CTO and CEO approve beautiful and premium product design as a permanent product principle. | AYO uses a reusable design system and a modern, calm, trustworthy visual language; beauty may never weaken performance, clarity, accessibility or reliability, including on older Android devices and Amharic/English layouts. |
| AP-024 | 2026-07-15 | CTO and CEO approve extremely easy rider and driver access as a permanent product principle. | Core flows use the fewest reasonable steps, one primary action where practical, progressive disclosure, explicit connectivity/state feedback and measured usability; journeys, wireframes, design system, accessibility, low-connectivity behavior and targets require review before UI implementation. |

## B. Provisional assumptions

These guide planning only. They are not approved product policy and must be confirmed, changed or rejected by the named authority before their dependent release.

| ID | Assumption | Why it is currently useful | Required decision owner / resolution point |
|---|---|---|---|
| PA-002 | Use phone OTP as the primary rider/driver authentication method. | Aligns with the current Ethiopia-first mobile concept. | Leadership, security and local provider review before Mission 4. |
| PA-003 | Use one API deployment plus background workers initially. | Supports reliable jobs without premature microservices. | Engineering/operations before production infrastructure. |
| PA-004 | Use sequential, time-bounded immediate ride offers after shortlist ranking. | Matches current prototype intent and avoids uncontrolled multi-driver acceptance. | Founder/operations before Mission 8. |
| PA-005 | Keep scheduled rides and smart pre-dispatch out of the first public ride flow unless immediate dispatch is stable. | Reduces launch risk while preserving the target design. | Leadership at launch-scope review. |
| PA-006 | Use push plus SMS fallback for selected transactional/safety events. | Helps under mixed connectivity but affects cost and consent. | Product/operations after provider evaluation. |
| PA-007 | Use integer minor units or a controlled decimal type and double-entry accounting. | Prevents binary-float errors and supports audit/reconciliation. | Finance/engineering design review before Mission 9. |
| PA-008 | Start in one approved geographic service area and region. | Simplifies operations, map classification and incident response. | Founder/operations launch decision. |
| PA-009 | Preserve current prototype endpoints temporarily through compatibility adapters while `/api/v1` becomes authoritative. | Enables safe migration without wholesale rewrite. | Engineering before Mission 6. |
| PA-010 | Do not trust or migrate prototype in-memory wallet balances as real value. | Current accounting has a confirmed commission defect and no durable provenance. | Founder/finance/engineering before any data migration. |
| PA-011 | Use a single-cloud, managed-service MVP; provisionally prefer AWS Cape Town, with Google Cloud Johannesburg as the strongest benchmark alternative. | Three-AZ AWS availability, mature managed services and Cape Town Nitro Enclaves provide a low-complexity MVP plus narrow Tier 3 path; GCP may win on measured Ethiopia latency or confidential AI. | CTO review, CEO approval, Ethiopia carrier benchmark, provider quote and legal verification before architecture/deployment. |

Resolved assumption: `PA-001` was approved and superseded by permanent decision `AP-020` on 2026-07-15. The cloud-provider portion of `PA-011` remains provisional.

## C. Requires Ethiopian legal or operational verification before launch

These are launch blockers for the affected capability. The log records the question, not a legal conclusion.

| ID | Verification required | Affected capability | Evidence/owner needed |
|---|---|---|---|
| EV-001 | Confirm AYO's legal classification and permitted wording for the driver internal ledger, offsets and payout availability. | Ledger, driver app, cash reconciliation. | Qualified Ethiopian legal counsel and finance approval. |
| EV-002 | Confirm which payment/mobile-money providers are appropriately licensed and what activities AYO may perform. | Digital collection, refunds, payouts, future Pay. | Legal/commercial due diligence and signed provider terms. |
| EV-003 | Confirm rules for handling customer funds, settlement timing, safeguarding, receipts and failed/refunded payments. | Payments and ledger. | Legal, finance/accounting and provider guidance. |
| EV-004 | Confirm transport-platform licensing, launch-area permits and driver/vehicle eligibility documents. | Driver onboarding and ride operations. | Ethiopian transport counsel/regulator and local operations. |
| EV-005 | Confirm driver relationship, commission, incentives, suspension, deactivation and appeal obligations. | Driver policy and operations. | Labour/transport legal review and leadership policy. |
| EV-006 | Confirm tax, withholding, invoicing and record-retention obligations for cash/digital trips and driver earnings. | Pricing, ledger, reconciliation and reporting. | Ethiopian tax/accounting specialists. |
| EV-007 | Confirm privacy notice, consent, lawful basis, data-subject rights, cross-border processing and breach-notification requirements. | All identity/location/analytics systems. | Ethiopian privacy counsel and security/privacy owner. |
| EV-008 | Confirm retention and access rules for precise location, route history, identity documents, support evidence and audit logs. | Maps, safety, verification, support. | Legal/privacy and operations; approved retention schedule. |
| EV-009 | Confirm whether/how selfie, biometric, device fingerprint and background-check data may be collected and used. | Onboarding, fraud and account recovery. | Legal/privacy review plus vetted providers/process. |
| EV-010 | Verify airport, venue, road and restricted pickup operating rules and who can authorize classifications. | Smart Pickup and scheduled/airport rides. | Local authorities/venue operators and AYO operations. |
| EV-011 | Define truthful emergency/SOS capability, escalation contacts, response limits and any recording/evidence rules. | Safety systems. | Legal, emergency-service/local operations and leadership. |
| EV-012 | Confirm consumer-protection requirements for fare display, dynamic pricing, cancellation, waiting, refunds and complaints. | Pricing and support. | Consumer/transport legal review and leadership policy. |
| EV-013 | Confirm insurance requirements and incident responsibilities for platform, drivers, vehicles, riders and parcels if expanded. | Ride launch and future Express. | Insurance/legal/operations review. |
| EV-014 | Validate local SMS/push delivery, map coverage, payment availability, device/network assumptions and support capacity in the launch area. | End-to-end operational readiness. | Field testing and provider/service-level evidence. |
| EV-015 | Define lawful government/law-enforcement request handling and emergency disclosure procedures. | Identity, location, safety and audit data. | Legal counsel and restricted internal procedure. |

## D. Open leadership decisions

Record decisions here before implementation depends on them:

| ID | Decision needed | Deadline/dependency | Status |
|---|---|---|---|
| LD-001 | Launch city/area, service types and operating hours. | Before Smart Pickup field work and production sizing. | Open |
| LD-002 | Fare components, rate values, commission, rounding and dynamic-pricing limits. | Before Mission 9. | Open |
| LD-003 | Rider/driver cancellation, wait-time and no-show policy. | Before enabling exception transitions publicly. | Open |
| LD-004 | Driver offer information, timeout, fairness tie-breakers and decline treatment. | Before Mission 8 acceptance. | Open |
| LD-005 | Cash-obligation collection/offset policy and driver limits. | Before Mission 9 launch. | Open |
| LD-006 | Bonus/incentive approval, budget and appeal policy. | Before bonus postings are enabled. | Open |
| LD-007 | Payout schedule, minimum, fee and failure handling. | Before Mission 10. | Open |
| LD-008 | Safety/support operating hours, escalation authority and service levels. | Before Mission 12 launch. | Open |
| LD-009 | Scheduled-ride promise, lead time and cancellation rules. | Before Mission 13. | Open |
| LD-010 | Quantitative ride-flow gate for starting super-app expansion. | Before any Express/Eat/Marketplace/Home/Pay build. | Open |

## E. Decision record template

Copy this section for future decisions:

```text
ID:
Date:
Status: proposed | approved | rejected | superseded
Owner/approver:
CTO review status:
CEO approval status:
Problem:
Who benefits:
Success measure:
Decision:
Why this decision:
Alternatives considered:
Simpler solution considered:
Consequences and risks:
Legal/security/privacy review:
Effective date:
Supersedes / superseded by:
```

## F. Engineering implementation decisions

### ED-001 — Python foundation toolchain

- **Date:** 2026-07-15
- **Status:** Approved for Mission 1, Milestone 2 by CEO and CTO instruction.
- **Problem:** The FastAPI prototype had no dependency manifest, lock file,
  automated tests, consistent formatting/linting, security scanning or CI gate.
- **Decision:** Use standard `pyproject.toml` metadata with an exact `uv.lock`;
  Python 3.13; Ruff for formatting, import ordering and linting; pytest with
  coverage for automated tests; Bandit and pip-audit for source and dependency
  scanning; and a least-privilege GitHub Actions workflow running the same locked
  commands as local development.
- **Why:** This is the smallest coherent toolchain that gives cross-platform
  locking, fast installation, one formatter/linter, mature FastAPI-compatible
  testing and two complementary security checks. CI actions are immutable-SHA
  pinned and the external `uv` bootstrap version is explicitly pinned.
- **Alternatives considered:** Poetry offers an integrated workflow but adds
  project-specific packaging metadata and commands AYO does not currently need.
  `pip-tools` is mature and pip-native but requires separate input/output files
  and more platform-specific lock handling. Black + isort + Flake8 are proven but
  create three overlapping configurations where Ruff provides the required
  behavior. Safety was considered for dependency scanning; pip-audit is maintained
  under the Python Packaging Authority and integrates with Python environments.
- **Risks:** `uv` is an additional bootstrap tool; exact locks still require
  deliberate update reviews; scanners do not prove code is secure; the current
  70% coverage floor is a starting guardrail, not a quality target; and current
  FastAPI testing requires the newer `httpx2` package. The generic `DEBUG`
  collision and wallet accounting defect remain intentionally unfixed.
- **Revisit when:** Python/platform support changes, cross-platform locking becomes
  unreliable, a tool is unmaintained or has a material supply-chain incident,
  false results impede delivery, or measured CI cost warrants a simpler proven
  replacement.

### ED-002 — Domain contracts and persistence boundaries

- **Date:** 2026-07-15
- **Status:** Approved through the CEO and CTO Mission 2 instruction.
- **Problem:** Ride and wallet business behavior depended directly on module-level
  dictionaries, preventing safe persistence replacement, isolated testing and
  multi-worker operation.
- **Decision:** Place a typed `Ride` aggregate and repository protocols inside the
  modular monolith; inject repositories at HTTP/service boundaries; keep
  thread-safe, copy-isolating memory adapters for current behavior; and quarantine
  the prototype wallet behind an explicitly named legacy repository contract.
- **Why:** Ports and adapters provide a narrow PostgreSQL migration seam without a
  rewrite or premature service split. Copy isolation makes persistence explicit
  and prevents accidental mutations from bypassing an adapter.
- **Alternatives considered:** Importing an ORM directly into services is initially
  shorter but couples business behavior to PostgreSQL/ORM sessions and complicates
  unit tests. A generic base repository reduces code but obscures aggregate-specific
  operations and transaction semantics. Microservices add network and operational
  failure modes without measured justification.
- **Risks:** Memory adapters remain process-local; the compatibility API still
  exposes internal ride fields; ride completion is not atomic with wallet mutation;
  ride IDs remain short; and the legacy wallet is neither immutable nor a valid
  production ledger. These are explicit prerequisites for later approved missions.
- **Revisit when:** PostgreSQL contract tests show missing transaction/concurrency
  semantics, domain rules require richer aggregate methods, or measured workload
  evidence justifies extraction from the modular monolith.

### ED-003 — Reusable PostgreSQL persistence foundation

- **Date:** 2026-07-15
- **Status:** Architecture and implementation approved by CEO and CTO; local
  PostgreSQL integration execution remains environment-blocked pending a reachable
  PostgreSQL 17 server or CI run.
- **Problem:** AYO needs durable, transactional persistence shared by future product
  modules without coupling domains to an ORM or redesigning persistence for each
  super-app capability.
- **Decision:** Use PostgreSQL 17 with synchronous SQLAlchemy Core and Psycopg 3;
  bounded `QueuePool`; a reusable transaction/Unit-of-Work kernel with typed
  repository composition; UTC `TIMESTAMPTZ`; internal UUID primary keys; integer
  optimistic versions; namespaced secret configuration; safe structured database
  events; and internal readiness probing. Existing repository protocols and public
  routes remain unchanged.
- **Why:** Synchronous Core matches current contracts, retains explicit SQL and
  transaction control, supports later Alembic migrations and avoids unmeasured async
  or ORM lifecycle complexity. Domain-specific repositories preserve ownership;
  the shared kernel centralizes only genuinely common infrastructure.
- **Alternatives considered:** Direct Psycopg reduces one abstraction but increases
  mapping, instrumentation and schema boilerplate. SQLAlchemy ORM risks persistence
  objects leaking into domain logic. Async SQLAlchemy requires contract/lifecycle
  changes without measured concurrency evidence.
- **Risks:** PostgreSQL adapters are not active until migrations and cutover;
  PostgreSQL-specific tests could not run locally because no server was present and
  the approved installer download returned HTTP 403; CI uses the official
  PostgreSQL 17.10 Bookworm service. Short public ride IDs and the legacy wallet
  defect remain. Test metadata is not a migration or production schema authority.
- **Revisit when:** Measured pool or thread saturation supports async conversion,
  transaction boundaries require new domain contracts, database topology changes,
  or a product module demonstrates a missing shared persistence primitive.

### ED-004 — Versioned PostgreSQL schema migrations

- **Date:** 2026-07-15
- **Status:** Implemented and verified; awaiting CEO and CTO final approval.
- **Problem:** AYO needs repeatable, auditable schema evolution without granting
  DDL to application traffic or allowing concurrent deployments to race.
- **Decision:** Use Alembic with reviewed SQLAlchemy Core metadata and immutable
  revision files. Execute it only through a deployment entry point that holds a
  PostgreSQL session advisory lock. Keep one linear migration head, a dedicated
  `ayo` schema, a public Alembic version table controlled by the migration role,
  and a read-only internal readiness check. Prefer forward fixes; destructive
  changes require backup, restore planning and approval.
- **Why:** Alembic is the smallest mature fit for AYO's existing Python and
  SQLAlchemy Core stack. It provides transactional PostgreSQL migrations and
  metadata comparison while keeping generated changes reviewable. AYO adds the
  bounded advisory lock Alembic does not provide itself.
- **Alternatives considered:** Flyway has strong SQL-first history and PostgreSQL
  locking but adds a separate Java/tool licensing surface and duplicates schema
  knowledge. Sqitch provides dependency-oriented SQL and verification but requires
  more bespoke integration. Atlas offers declarative planning but adds another
  schema system and less direct alignment with the existing metadata.
- **Risks:** Advisory-lock identity must remain stable across deployment tooling;
  roles still require environment-specific provisioning; autogeneration can miss
  intent and is never authoritative without review; and transactional DDL cannot
  make destructive data changes inherently reversible.
- **Revisit when:** Multiple independently owned database schemas need separate
  release trains, Alembic no longer supports the approved stack, or measured
  deployment needs justify a centralized migration platform.

### ED-005 — Transactional append-only audit events

- **Date:** 2026-07-15
- **Status:** Implemented and verified; awaiting CEO and CTO final approval.
- **Problem:** Security, safety, financial and administrative actions need durable,
  attributable evidence that shares the business transaction without turning
  operational logs into an unbounded sensitive-data store.
- **Decision:** Use typed application-generated events appended to PostgreSQL in
  the same Unit of Work as successful business changes. Provide a bounded separate
  transaction only for denied/failed activity before a business transaction. The
  runtime role receives `SELECT` and `INSERT`, never `UPDATE`, `DELETE` or
  `TRUNCATE`. Metadata is allowlisted and validated before persistence. Keep the
  record shape compatible with later CDC/outbox export, but add no exporter now.
- **Why:** This is the smallest design that captures business meaning and atomicity
  while remaining understandable across AYO modules. Database triggers cannot
  reliably supply request/actor intent, and full event sourcing would make audit
  history the business source of truth without a demonstrated need.
- **Tamper-evidence decision:** Do not add an in-database hash chain. A global chain
  would serialize writes, scoped chains add gap/concurrency ambiguity, and hashes
  controlled by the same database owner provide limited protection against an
  owner-level attacker. Append-only privileges and monitored access are the first
  control. Externally anchored signing/export requires later key/provider approval.
  AYO must not call this storage tamper-proof.
- **Alternatives considered:** Trigger/database-native audit captures direct SQL
  but lacks safe application context and adds privileged database code. A separate
  audit transaction can survive business rollback but creates false success
  records, so it is limited to pre-transaction denied/failed outcomes. A
  transactional outbox is valuable when an approved external consumer exists but
  premature today. Full event sourcing has the highest rebuild and governance cost.
- **Risks:** A database owner can still alter history; retention periods require
  Ethiopian professional review; runtime privileges must be provisioned and tested
  per environment; append volume needs capacity monitoring; and allowlists require
  reviewed evolution as modules are added.
- **Revisit when:** External regulatory evidence, a SIEM/export consumer, owner-level
  tamper threats, or measured audit volume justifies signed checkpoints, CDC,
  partitioning, archival or a separately controlled evidence store.

### ED-006 — Durable sessions and distributed rate-limit foundation

- **Date:** 2026-07-15
- **Status:** Implemented and verified; awaiting CEO and CTO final approval.
- **Problem:** Future authentication needs revocation that survives process/cache
  failure and rate limits shared across horizontally scaled API workers without
  introducing authentication behavior early.
- **Decision:** Keep PostgreSQL 17 authoritative for server-side session records and
  revocation. Store only SHA-256 fingerprints of high-entropy session identifiers.
  Implement a provider-neutral transactional token bucket using PostgreSQL row
  locking and decimal arithmetic. Surface storage failures; never silently allow a
  request when a required limiter is unavailable. Defer Redis until measured load
  justifies an ephemeral accelerator, never the sole revocation source.
- **Why:** PostgreSQL is already operated and provides atomic `ON CONFLICT` plus row
  updates across all workers. Token bucket permits bounded bursts and smooth refill,
  avoiding fixed-window boundary spikes with less storage than exact sliding logs.
  This is the smallest durable design and adds no provider or dependency.
- **Alternatives considered:** PostgreSQL-only sessions are selected; Redis-only
  sessions make revocation vulnerable to cache loss/outage. Hybrid sessions can
  reduce read latency later but add invalidation and failover complexity. Fixed
  windows are simplest but allow boundary bursts; exact sliding windows cost more
  storage/work; database request logs are too write-heavy; Redis atomic counters or
  Lua token buckets are the likely scale accelerator but require another service.
- **Risks:** Hot rate-limit keys serialize on one PostgreSQL row; database outage
  blocks required protected operations; SHA-256 is safe only because source tokens
  must be high entropy; lifecycle/timeout policy remains for Authentication approval;
  and stale-bucket/session retention needs a separately controlled cleanup job.
- **Revisit when:** Measured limiter latency, database write load, pool saturation or
  hot-key contention breaches approved SLOs; then add a provider-neutral Redis
  accelerator with PostgreSQL-backed revocation and tested outage behavior.

### ED-007 — Authentication and identity security architecture

- **Date:** 2026-07-15
- **Status:** CEO and CTO approved; implemented and verified in Mission 7.
- **Problem:** AYO needs accessible customer authentication and stronger workforce
  authentication without making SMS, a device label, token claims or an external
  provider the authority for identity and privilege.
- **Decision:** Use a hybrid method architecture with PostgreSQL-authoritative
  identity and rotating refresh sessions, short-lived access-token contracts,
  durable replay/family revocation, multiple privacy-safe device sessions and
  provider-neutral OTP/email/password/passkey/service interfaces. Require
  phishing-resistant authentication for staff/administrators and step-up for
  sensitive actions. No production provider or signing/KMS key is selected.
- **Why:** Phone OTP may be accessible in Ethiopia but is phishable and exposed to
  SIM/delivery risk; passkeys are phishing-resistant but Android passkey support
  begins at Android 9 and cannot be the only customer path. Passwords add recovery
  and credential-stuffing burden. The hybrid contract permits progressive adoption
  without provider lock-in while preserving a simple rider/driver journey.
- **Alternatives considered:** Managed identity reduces implementation operations
  but adds provider/data/availability lock-in and still needs AYO domain sessions.
  Fully self-managed delivery is not approved. Opaque access tokens simplify
  immediate revocation but add a database/cache lookup to every request. Short-lived
  signed access claims plus durable refresh/session checks scale horizontally while
  limiting exposure; sensitive operations still require authoritative status and
  step-up checks. Redis is unnecessary until measured.
- **Risks:** No production token codec, KMS, OTP/SMS/email/passkey provider or
  compromised-password service exists; Ethiopian contact/retention and recovery
  policy needs professional verification; access claims can be stale until expiry;
  support recovery is a high-risk fraud path; and low-end/older devices require
  fallback methods without weakening staff security.
- **Revisit when:** Provider research, Ethiopian delivery measurements, Android
  device distribution, fraud evidence, AYO Pay regulation or latency/load results
  justify a different customer method, managed identity or opaque access tokens.

### ED-008 — Policy-shaped PostgreSQL RBAC authorization

- **Date:** 2026-07-15
- **Status:** CEO and CTO approved; implemented and verified in Mission 8 against
  PostgreSQL 17 with all required CI gates passing.
- **Problem:** AYO needs least-privilege access control without coupling
  Authentication to privilege or prematurely adding a distributed policy system.
- **Decision:** Implement core RBAC in PostgreSQL with permission codes, roles,
  role-permission grants and expiring/revocable identity-role assignments. Use a
  subject/action/resource decision contract, trusted-context middleware, FastAPI
  decorator/dependency enforcement and mandatory service checks. Deny by default,
  audit decisions and administration, and add no hierarchy, OPA, Cedar, managed
  provider or ABAC engine.
- **Why:** RBAC is understandable and auditable for current AYO boundaries. The
  policy-shaped contract prevents route coupling and preserves later extraction or
  an AuthZEN-compatible transport without another critical dependency today.
- **Alternatives considered:** ABAC adds attribute-policy complexity; OPA and Cedar
  add languages and operations; Zanzibar-style ReBAC solves relationship graphs
  AYO does not have; token-only permissions become stale; route-only checks are
  bypassable by workers and internal callers.
- **Compatibility decision:** Preserve all 12 prototype routes until approved
  Authentication transport supplies trusted request identity. Test production
  enforcement in isolated applications using real PostgreSQL. This does not approve
  the compatibility routes for launch.
- **Risks:** Database checks and decision auditing add load; business role matrices
  and separation of duties remain leadership policy; future ownership and risk
  constraints may need narrowly reviewed contextual rules.
- **Revisit when:** Measured latency breaches an approved SLO, relationships become
  graph-shaped, independent services need a network PDP, or policy complexity can
  no longer remain safely testable in the core evaluator.

### ED-009 — Least-privileged future AI support authorization boundary

- **Date:** 2026-07-15
- **Status:** Approved product requirement; permission registration implemented.
  Production identity/role provisioning and AI implementation remain unapproved.
- **Problem:** Future AI-first chat and voice support needs useful customer-service
  access without turning an AI system into unrestricted staff or an escalation path.
- **Decision:** Reserve eight bounded `support.*` permissions for assigned cases,
  limited trip/account views, payment-status reads, escalation and safe guidance.
  Future AI support must use a dedicated service identity, deny by default, audit
  every action with correlation, minimize data and escalate high-risk categories.
- **Explicit exclusions:** No administrator/staff role, identity mutation, payment
  or payout mutation, permanent account action, control override, unrestricted
  audit access, cross-customer disclosure, AI/chat/voice/provider implementation or
  voice/transcript retention approval.
- **Why:** Explicit capabilities are understandable, testable and revocable. A
  broad `support.agent` permission or staff impersonation would violate least
  privilege and make resource-level data isolation harder to prove.
- **Risks:** Permission names alone do not implement assigned-case ownership or
  field filtering; prompt injection and model/provider data handling need separate
  threat models; voice privacy and Ethiopian retention obligations need professional
  verification; escalation operations require trained human capacity.
- **Revisit when:** The Support domain contracts and customer journeys are approved,
  provider/data-flow research is complete, or measured operations justify narrower
  permissions. Expansion requires CEO/CTO approval and a forward migration.

### ED-010 — Provider-neutral rider destination search boundary

- **Date:** 2026-07-15
- **Status:** Founder/CEO and CTO implementation instruction approved; implemented and verified, awaiting final mission approval.
- **Problem:** The rider home flow needs destination search without locking AYO to a map provider or presenting prototype data as durable production state.
- **Decision:** Use a typed, abortable and bounded destination-search gateway behind a dedicated Expo Router stack screen. Keep the current catalog in an explicitly named offline adapter and defer remote provider selection, authenticated saved/recent persistence and maps to their approved missions.
- **Why:** The boundary supports Google, OpenStreetMap or an AYO backend adapter without UI rewrites, adds no dependency and keeps weak-network behavior lightweight.
- **Alternatives considered:** Provider calls in UI create lock-in and credential risk; a new state/search dependency is unnecessary; backend and provider selection exceed this mission.
- **Risks:** The offline catalog is not a production source of truth; real provider attribution, localization, result ranking, durable personal places and precise-location handling remain unimplemented.
- **Revisit when:** The map-provider/backend contract is approved, measured search quality or latency misses its target, or authenticated saved/recent storage is authorized.

### PA-012 — Mission 11 rider-request and dispatch sequencing clarification

- **Date:** 2026-07-15
- **Status:** Proposal awaiting CTO review and CEO approval; no architecture or implementation authorized.
- **Conflict identified:** The requested “Mission 11 — Driver Request & AI Dispatch Foundation” combines Roadmap Mission 11 launch-app UI with work governed by Mission 6 (canonical request/idempotency), Mission 8 (immediate dispatch) and Mission 9 (server-authoritative quote/fare). Roadmap Mission 11 depends on Missions 4–10.
- **Proposed resolution:** Do not connect the mobile client to the unsafe prototype or create a client-authoritative ride object. Review `docs/MISSION_11_DRIVER_REQUEST_DISPATCH_RESEARCH.md` and decide whether to preserve roadmap order or explicitly authorize a bounded vertical-slice re-sequencing. The recommended direction is an authenticated, idempotent server request plus deterministic provider-neutral dispatch strategy; AI remains a future governed adapter.
- **Authority needed:** CTO technical/dependency review followed by CEO product and sequencing approval. Exact ETA meaning, search/safety wording, cancellation/no-driver behavior and any ranking/livelihood tradeoff require leadership decisions; location/privacy obligations require qualified Ethiopian review before launch.

### PA-013 — Mission 11 immediate-dispatch architecture package

- **Date:** 2026-07-15
- **Status:** Superseded by the approvals and bounded implementation authorization recorded in AP-025 on 2026-07-15.
- **Proposal:** Adopt the server-authoritative modular-monolith design in `docs/AYO_DISPATCH_ARCHITECTURE_PROPOSAL.md`: authenticated idempotent request acceptance, atomic ride/history/idempotency/outbox transaction, bounded staged dispatch, deterministic explainable matching, atomic reservation/assignment, two-sided fairness guardrails, provider-neutral ETA, weak-network recovery and governed future AI strategy ports.
- **Explicit exclusions:** No runtime code, executable migration, provider selection, policy value, production dependency, infrastructure, AI model or production integration. Do not connect the mobile app to the unsafe legacy ride endpoint.
- **Approval sequence clarification:** The required CTO technical review and subsequent CEO confirmation were recorded in AP-025.

### AP-025 — Mission 12 immediate-dispatch implementation authorization

- **Date:** 2026-07-15
- **Status:** CTO architecture approval and CEO final architecture, roadmap-resequencing and implementation approval recorded.
- **Decision:** Mission 12 becomes Immediate Dispatch Implementation. Mission 13 remains Scheduled Ride Dispatch and Pre-Dispatch. Implement server-authoritative ride creation, request idempotency, deterministic immediate dispatch, driver-offer timeout and automatic reassignment, audit logging, weak-network retry/recovery, explainable decisions and neutral new-driver reputation until sufficient completed-trip history exists.
- **Explicit exclusions/gates:** No scheduled rides or pre-dispatch in Mission 12. Stop before irreversible database migration, payment implementation or security-sensitive production activation.
- **Rationale:** This preserves the approved deterministic-first, provider-neutral modular-monolith architecture and prevents client-authoritative state, opaque livelihood penalties and premature AI/dispatch complexity.

### AP-026 — Mission 13 production dispatch persistence and secure API foundation

- **Date:** 2026-07-16
- **Status:** CTO and CEO implementation approval recorded.
- **Decision:** Add reversible PostgreSQL dispatch persistence, transactional repositories and outbox, authenticated rider/driver API contracts with RBAC and ownership enforcement, and bounded server-controlled expiry/recovery. Preserve all Mission 12 deterministic, fairness, privacy and neutral-new-driver rules.
- **Explicit exclusions/gates:** No scheduled rides, pre-dispatch, payments, AI ranking, deployment, secrets, external production services, real customer data or public production activation. Stop before an irreversible migration.
- **Rationale:** Durable atomic state is required for safe retries, concurrent workers and Ethiopian-network recovery. Extending the modular monolith with PostgreSQL transactions is simpler and safer than process memory, legacy ride storage or premature distributed infrastructure.
- **Alternatives and risks:** Do not promote the float/JSON-based legacy `rides` table. Event sourcing and a broker are unnecessary now. Candidate discovery remains a provider-neutral dependency; authentication resolver/key activation and Ethiopian privacy/operational review remain launch gates.

### AP-027 — Mission 14 secure internal dispatch activation

- **Date:** 2026-07-16
- **Status:** CTO and CEO implementation approval recorded; commit/push require a post-check approval.
- **Decision:** Implement provider-neutral asymmetric JWT verification, trusted database-backed subjects, disabled-by-default non-production dispatch registration, request/rate limits, transactional outbox delivery, non-overlapping recovery scheduling and privacy-minimized observability.
- **Explicit exclusions/gates:** No external identity or messaging connection, production secrets, public activation, deployment, real personal data, payments, scheduled/pre-dispatch, AI ranking or irreversible change.
- **Rationale:** Controlled staging requires cryptographic identity and durable delivery/recovery boundaries, but provider connections and production trust configuration would materially expand security authority.
- **Alternatives and risks:** Handwritten JWT verification is rejected; use a removable standards-based library behind an interface. Token roles remain non-authoritative. PostgreSQL outbox/locks are simpler than a broker before measured need. Bearer replay, key freshness, rate-limit availability and operational thresholds remain production risks.

### PA-028 — Mission 15 deterministic marketplace intelligence architecture

- **Date:** 2026-07-16
- **Status:** CTO and CEO architecture/implementation approval recorded; deterministic advisory implementation complete and awaiting final review.
- **Problem:** AYO needs measurable marketplace health, driver-opportunity protection and transparent operational recommendations without weakening fastest-pickup dispatch, silently manipulating livelihoods or allowing analytics to become pricing authority.
- **Proposal:** Add an advisory deterministic module described in `docs/MISSION_15_MARKETPLACE_INTELLIGENCE_ARCHITECTURE.md`. It evaluates privacy-minimized versioned snapshots with fixed-point rules, explicit guardrails and reason codes; predicts demand through capped rule-based factors; recommends but never activates surge; protects externally caused driver delays; and provides offline replay/simulation behind stable future-strategy contracts.
- **Explicit exclusions:** No implementation, executable migration, automatic pricing, payment, AI/ML ranking, production data/provider, deployment, individual churn targeting or direct authority over ride assignment, eligibility, safety/fraud action or incentives.
- **Rationale:** A single blended optimizer hides rider/driver/business trade-offs and is hard to contest. Separate advisory components preserve Mission 12 immediate-pickup authority, neutral new-driver standing, auditability, deterministic fallback and an extraction/AI path without premature infrastructure.
- **Risks and decisions required:** Leadership must approve fairness and material-equivalence policy, airport/event/weather ownership, emergency suppression and any future human-approved commercial response. Ethiopian legal/operational review is required for earnings analytics, location aggregation, retention and airport/event practice.

### PA-029 — Mission 16 scheduled rides, smart pre-dispatch and airport intelligence

- **Date:** 2026-07-16
- **Status:** CTO and CEO architecture approved and implementation authorized; implemented locally on 2026-07-16. Activation and deployment remain unapproved.
- **Problem:** Time-critical planned rides need more reliable preparation and recovery than a delayed immediate request, without blocking drivers too early, harming a current trip or making an unsupported guarantee.
- **Proposal:** Use the separate reservation aggregate and staged deterministic scheduled-dispatch architecture in `docs/MISSION_16_SCHEDULED_RIDES_PREDISPATCH_ARCHITECTURE.md`: durable acceptance, soft planning with material-improvement/stability guardrails, formal commitment lock, protected smart pre-dispatch, airport/flight context interfaces, transactional reassignment, timed immediate fallback, restart-safe recovery and purpose-separated third-party booker/passenger/future-payer/trusted-contact roles.
- **Implemented decision:** Added the isolated deterministic scheduled domain, additive reversible PostgreSQL migration, exclusion-constrained driver commitments, privacy-minimised participant/consent authority, checkpoint recovery and tests. Immediate dispatch was not modified.
- **Explicit exclusions:** No pricing/fee/compensation/guarantee, payment, AI ranking, provider connection, deployment, public activation or real personal/flight data.
- **Rationale:** Immediate rides and future reservations have different timing and truth. Assigning too early wastes driver capacity; dispatching only at pickup time provides little reliability. Staged commitment with revalidation and fallback is the simplest design that protects both sides.
- **Risks/decisions required:** Leadership must define the reservation promise, booking/pickup window, material replacement thresholds/counts, driver commitment policy, scheduled-versus-immediate fairness, passenger consent/assisted-booking policy and airport scope. Bole rules and travel/location/contact privacy require qualified local verification.

### PA-030 — Mission 17 controlled scheduled-dispatch integration

- **Date:** 2026-07-16
- **Status:** CTO and CEO approved; implementation and PostgreSQL validation completed and committed locally as `9494cb3bcf89a05b56c930b4c0873475fa76030a`; activation remains gated.
- **Problem:** Mission 16 requires PostgreSQL 17 concurrency proof and a secure, disabled-by-default authenticated integration boundary before controlled use.
- **Decision:** Reuse the modular-monolith authentication, RBAC, PostgreSQL unit-of-work, audit/outbox and advisory-lock foundations through an isolated scheduled composition described in `docs/MISSION_17_SCHEDULED_DISPATCH_CONTROLLED_INTEGRATION.md`.
- **Alternatives:** Process memory cannot validate authority; a microservice/broker is premature; provider-specific notification/maps/flight connections exceed scope.
- **Exclusions:** Payments, AI ranking, automatic pricing, external providers, production secrets/data, deployment, public activation and remote push.
- **Revisit trigger:** Measured scheduled workload, isolation failures or independent scaling needs justify extraction only after CTO/CEO review.

### PA-031 — Deferred Customer Recovery and Trust Engine

- **Date:** 2026-07-16
- **Status:** CTO/CEO future architecture direction recorded; no implementation, mission sequencing, financial action or activation authorized.
- **Problem:** Confirmed routine failures need faster, fairer recovery without automatically approving every complaint or unfairly blaming riders or drivers.
- **Direction:** Design a future evidence-based advisory engine with responsibility classes, versioned reason codes, configurable limits, idempotency, duplicate/abuse controls, minimum-data evidence and mandatory human review for serious, ambiguous, high-value, fraudulent, financial or irreversible matters. See `docs/AYO_FUTURE_TRUST_AND_AI_SUPPORT_ENGINES.md`.
- **Driver fairness:** Verified traffic, road closure, emergency, platform failure and other external causes cannot create hidden punishment or unjust driver liability.
- **Explicit exclusions:** No runtime, migration, route, provider, payment/wallet action, automated refund/credit/payout or production activation.
- **Approval gate:** Recovery policy, responsibility thresholds, financial limits, evidence retention and Ethiopian legal/operations review require a separately approved mission.

### PA-032 — Deferred AI Customer Support Engine

- **Date:** 2026-07-16
- **Status:** CTO/CEO future architecture direction recorded; no model, provider, runtime or activation authorized.
- **Problem:** Users need immediate acknowledgement and fast routine resolution without repeating known facts, while serious or uncertain cases require safe human ownership.
- **Direction:** Design a future AI-first, policy-controlled support orchestrator using minimum approved context, structured cases, audited tools, low-risk pre-authorized workflows, deterministic fallback and evidence-rich human handoff. Support Amharic/English and provider-neutral app, SMS, voice and call-centre channels.
- **Mandatory escalation:** Safety, harassment/assault, legal, identity, account takeover, fraud/collusion, payment disputes/payouts, high-value compensation, ambiguous evidence, repeated unresolved cases, vulnerable passengers and emergencies.
- **Explicit exclusions:** No runtime, dependency, route, provider/model selection, payment/wallet action, automated refund, learning pipeline or production activation.
- **Approval gate:** A separate research/architecture mission must approve evaluations, language quality, privacy/retention, human operations, tool authority, model/provider and Ethiopian legal/operational requirements.

### PA-033 — Mission 18 rider and driver real-time experience

- **Date:** 2026-07-16
- **Status:** Architecture proposal prepared for CTO/CEO review; no implementation, migration, dependency, provider selection, commit or activation authorized.
- **Problem:** The dispatch foundations need a single clear rider/driver experience and canonical post-assignment lifecycle that converges after retries, network loss, reassignment and app restart without allowing clients or notifications to become authority.
- **Proposal:** Add an Active Ride Orchestrator boundary and role-specific presentation projections described in `docs/MISSION_18_RIDER_DRIVER_REALTIME_EXPERIENCE_ARCHITECTURE.md`. Use authoritative snapshots, ride-scoped ordered events, idempotent HTTPS commands, bounded replay and staged transport adapters. Begin with adaptive polling, add a foreground stream only after measurement, and use future push solely to wake clients for a snapshot refresh.
- **Alternatives:** Raw status polling is simpler but cannot safely express ordered recovery and two-device convergence. A provider-specific SDK creates premature lock-in. A new real-time microservice adds unmeasured operational and security cost.
- **Product/safety direction requested:** Layer driver/vehicle matching with a short-lived assignment-bound pickup PIN; keep safety/help visible; distinguish pending from confirmed actions; separate cancellation evidence from responsibility; protect ordinary offer declines and verified external delays from hidden punishment; treat airport, assisted and third-party flows as first-class.
- **Explicit exclusions:** No fare/fee/refund policy, financial mutation, AI/support/recovery implementation, external maps/communications/flight/real-time provider, deployment, public activation or real data.
- **Approval/verification needed:** CTO approval is required for lifecycle/ownership, synchronization, compatibility and threat controls. CEO/leadership and Ethiopian legal/operations approval are required for driver disclosure, waiting/cancellation policy, airport/premium promise, emergency/support operations, retention and launch targets.
- **Revisit trigger:** Consider provider selection, broker or service extraction only when measured connection scale, event lag, reconnect failure, latency, provider resilience or operating cost breaches an approved threshold.
- **Approved architecture amendment:** Add a deterministic Active Ride Confidence Engine that owns only versioned health classifications and non-executing operational recommendations, plus Dynamic Pickup Intelligence that owns only confidence-bearing primary/fallback pickup recommendations. Missing/stale evidence reduces confidence; verified external/platform causes protect drivers; alert hysteresis and cooldown prevent churn/fatigue; material pickup changes require authorized communication and confirmation. Neither component may alter ride state, assignment, price, blame, safety outcome or financial recovery.
- **Amendment events:** Propose auditable confidence evaluation/level/recommendation/suppression/recovery events and pickup recommendation/proposal/confirmation/fallback/degradation events. Exact schemas, thresholds, retention and activation remain implementation-stage CTO/CEO gates.

### AP-034 — Mission 19 Active Ride implementation

- **Date:** 2026-07-16
- **Status:** Mission 18 implementation authority recorded; implementation complete locally and awaiting CTO/CEO review before commit or activation.
- **Decision:** Implement the post-assignment Active Ride Orchestrator inside the modular monolith with PostgreSQL authority, explicit compatibility translation, role projections, HTTPS snapshot/polling commands, assignment-bound PIN, evidence boundaries, deterministic confidence/pickup advisory components and controlled workers. See `docs/MISSION_19_ACTIVE_RIDE_IMPLEMENTATION.md`.
- **Authority separation:** Dispatch owns matching/assignment; Scheduled Dispatch owns reservations/commitment/pre-dispatch; Active Ride owns only post-assignment lifecycle. Confidence and Pickup Intelligence are advisory and cannot execute assignment, cancellation, blame, safety, fare or financial changes.
- **Alternatives:** External stream/broker/maps are deferred; raw prototype status mutation cannot provide ordering, ownership or recovery; a separate service is premature without measured isolation/scale need.
- **Security/privacy:** Disabled by default and production-forbidden; trusted authentication plus RBAC and ownership; bounded inputs/rates/replay; no PIN, token, exact-location trail or evidence body in logs/outbox; runtime delete is prohibited.
- **Revisit trigger:** Consider streaming/provider/service extraction only after controlled polling, connection, event-lag, recovery, battery/data and operating-cost measurements breach approved thresholds.

### PA-035 — Deferred Smart Arrival, Waiting and Fair Cancellation Engine

- **Date:** 2026-07-16
- **Status:** CTO/CEO documentation direction recorded; no implementation, migration, dependency, fee, refund, wallet action, production activation or fixed waiting value authorized.
- **Problem:** Drivers need protection for genuine waiting while riders need early guidance, accurate arrival evidence and a fair, visible opportunity to reach the pickup point.
- **Direction:** Add a deterministic evidence boundary with typed unverified/verified arrival, active/ending/paused/invalid waiting and evidence-ready states. Start a timer only after stationary arrival inside the approved pickup zone with sufficient data confidence; invalidate or suppress consequence evidence for driver lateness/movement away, pickup mismatch, AYO/map/network failure, serious uncertainty or verified external disruption.
- **Authority separation:** Active Ride owns lifecycle; Dynamic Pickup owns recommendations; Pricing alone may later evaluate approved financial policy; Recovery/Support consume minimum evidence; the future engine cannot cancel, blame, charge, refund, compensate or punish.
- **Product principle:** AYO should prevent cancellations, not profit from them. No hidden punishment scores. Driver eligibility review is protected for verified traffic, roadblock, airport queue, weather, emergency and platform/provider failure.
- **Open gate:** Waiting windows and consequence policies must be configurable by city/product/context. Ethiopian launch values require field measurement, qualified legal/operational review and separate CTO/CEO approval.

### PA-036 — Deferred Landmark Intelligence Layer

- **Date:** 2026-07-16
- **Status:** CTO/CEO documentation direction recorded; no implementation, schema, dependency, map provider, production data collection or activation authorized.
- **Problem:** Coordinates alone often fail to express the locally understood entrance, gate, side of road or named landmark needed for reliable Ethiopian pickup and destination guidance.
- **Direction:** Model canonical versioned landmarks with English/Amharic names, aliases and phonetic forms, entrances/access direction, confidence/freshness, provenance and merge lineage. Treat rider/driver suggestions as untrusted until corroborated and operations-approved; use privacy-safe aggregation and fraud controls; fall back to coordinates when ambiguous.
- **Authority separation:** Landmark Intelligence advises Dynamic Pickup; Dynamic Pickup rechecks safety, legal access, accessibility and road direction; Active Ride controls material-change confirmation. No landmark source silently changes a confirmed pickup or becomes authoritative merely because a provider or user supplied it.
- **Open gate:** Local-language search quality, operations verification, retention, abuse thresholds and authoritative Ethiopian airport/venue sources require research and separate approval before implementation.

### PA-037 — Mission 20 research recommendation

- **Date:** 2026-07-16
- **Status:** Mission 20 architecture approved by CTO and CEO on 2026-07-16; implementation authorized within the documented evidence-only boundaries. No fixed policy value, provider, financial action, production activation, commit or push is authorized by this decision.
- **Problem:** GPS-only or driver-triggered arrival can create false waiting and unfair cancellation evidence, while genuine driver waiting can remain unpaid and unauditable.
- **Recommendation:** Subject to approval, design a deterministic, server-authoritative multi-signal evidence engine in the modular monolith, first in non-consequential shadow mode. Require corroborating pickup, movement/stopping, freshness and map-confidence evidence; suppress consequences on uncertainty or failure; emit versioned confidence, reasons, explanations and minimum audit references; send ambiguous cases to human review.
- **Authority separation:** Immediate and Scheduled dispatch remain separate. Active Ride owns lifecycle, Dynamic Pickup owns pickup recommendations, Pricing owns any future fee policy, the ledger owns value movement, and Support/Recovery own separately approved review workflows. Mission 20 may produce evidence only unless later authority is explicitly approved.
- **Alternatives:** A manual-arrival/fixed-geofence timer is simpler but too easy to abuse and unsafe under GPS/entrance ambiguity. A learned classifier is premature without representative Ethiopian labeled outcomes and adds privacy, bias, drift and explainability burden.
- **Approved amendment:** Add Smart Pickup Readiness as confidence-bearing advisory evidence using driver ETA, bounded rider movement/timing and venue context. Notifications must be confidence-gated, localized, capped and cooldown-controlled. Add immutable, versioned Dynamic Waiting Policy configuration for airport, hotel, hospital, shopping-centre, residential, Immediate, Scheduled, accessibility, severe-weather and operational contexts; no duration is hard-coded.
- **Product boundaries retained:** No GPS-only arrival, hidden punishment score, double wait/cancellation charge or readiness-based blame. “Prevent cancellations, do not profit from them” and a clear review path remain governing proposals for final policy approval.
- **Open gates:** LD-003; EV-007, EV-008, EV-010, EV-012 and EV-014; actual policy values; airport/venue authority; accessibility treatment; privacy/retention; user journeys and wording; support staffing; final implementation review and separate production activation. See `docs/MISSION_20_SMART_ARRIVAL_WAITING_CANCELLATION_RESEARCH.md` and `docs/MISSION_20_SMART_ARRIVAL_WAITING_CANCELLATION_ARCHITECTURE.md`.

### PA-038 — Mission 21 AI Customer Support, Dispute and Resolution research

- **Date:** 2026-07-16
- **Status:** Research direction approved by CTO and CEO on 2026-07-16 for future architecture work. Architecture design and implementation remain unauthorized; no schema, migration, dependency, provider, model, channel, financial action, commit beyond this documentation record, push or activation is authorized.
- **Problem:** Riders and drivers need routine support within seconds without allowing probabilistic AI to invent policy, conceal evidence, mishandle emergencies or make unfair safety, identity, fraud, livelihood or financial decisions.
- **Recommendation:** Preserve the existing PostgreSQL Support authority and add, subject to a future architecture approval, a provider-neutral language adapter plus deterministic policy orchestrator, purpose-scoped evidence views, narrow idempotent tools, calibrated per-language confidence, explicit green/yellow/red routing and warm human handoff. Generative output may classify, summarize and phrase grounded explanations; it is never decision authority.
- **Authority separation:** Owning domains remain authoritative for ride state, arrival/wait evidence, pricing, ledger, identity, fraud, safety and account access. Customer Recovery may separately recommend recovery. Mission 21 cannot refund, compensate, sanction, recover an account or make an emergency/legal determination.
- **Alternatives:** A FAQ bot is safe and cheap but insufficiently contextual; retain it as fallback. A broad autonomous agent has higher apparent containment but unacceptable nondeterminism, privacy, prompt-injection, fairness and audit risk and is rejected.
- **Open gates:** Separately authorized architecture mission; initial auto-resolvable workflows; human/safety staffing and truthful SLOs; Ethiopian emergency and consumer procedures; Amharic/English and future-language evaluation; privacy/retention/model-feedback rules; recovery and financial authority; provider comparison; CTO architecture review and CEO product/operating approval. See `docs/MISSION_21_AI_CUSTOMER_SUPPORT_DISPUTE_RESEARCH.md`.

### AP-039 — Mission 20 local implementation checkpoint

- **Date:** 2026-07-16
- **Status:** CTO/CEO implementation approval granted for local preservation only. The module remains disabled by default; PostgreSQL 17 certification is pending; production activation, public routes, deployment and push are prohibited.
- **Decision:** Implement the evidence-only engine inside the modular monolith with deterministic multi-signal arrival, privacy-minimised readiness, versioned configuration resolution, immutable waiting snapshots, evidence/suppression recommendations, provider-neutral landmark/airport contracts, PostgreSQL persistence and transactional outbox intents.
- **Authority separation:** Active Ride remains lifecycle authority; Dynamic Pickup remains pickup authority; Pricing alone may later own fees; Support/Recovery own governed resolution. Mission 20 cannot cancel, blame, charge, refund, compensate or mutate a wallet/ledger.
- **Verification:** Ruff, focused strict mypy, the non-integration suite and branch threshold, Bandit, dependency audit and benchmark pass. PostgreSQL integration, concurrency, restart/recovery and migration upgrade/downgrade remain uncertified because PostgreSQL 17 is unavailable and its official installer download returned HTTP 403. Skips are not accepted as evidence.
- **Gate:** A scoped local preservation commit is authorized. Restore an approved PostgreSQL 17 test service and run all database gates without Mission 20 skips before any separate certification or activation decision. Enabling `ARRIVAL_WAITING_ENABLED`, public exposure, deployment and push remain unauthorized.

### PA-040 — Mission 21 architecture and threat-model proposal

- **Date:** 2026-07-16
- **Status:** Mission 21 architecture approved by CTO for documentation continuation only; no implementation, migration, dependency, provider, financial action, commit, push or activation authorized.
- **Proposal:** Extend the existing Support modular-monolith boundary with a deterministic case orchestrator, immutable policy snapshots, purpose-scoped evidence references, provider-neutral untrusted language adapter, least-privilege typed tool broker, restricted emergency router, explicit human/specialist queues and bilingual role-safe projections. See `docs/MISSION_21_AI_CUSTOMER_SUPPORT_ARCHITECTURE.md`.
- **Authority:** AI may understand, summarize, translate, retrieve authorized evidence, explain policy and recommend an allow-listed action. It cannot own state transitions or decide safety, identity, fraud, restrictions, material finance, refund/compensation, payout, money movement or legal conclusions. Owning domains and authorized humans/specialists retain authority regardless of confidence.
- **Alternatives:** FAQ-only support remains the outage/low-complexity fallback but cannot meet contextual resolution goals. A broad autonomous agent is rejected because generic tools and probabilistic authority create unacceptable privacy, prompt-injection, fairness, safety and audit risk.
- **Open gates:** Initial low-risk allow-list, queue staffing/SLOs, Ethiopian emergency procedures, privacy/retention/cross-border rules, Amharic evaluation, upload security, provider/model selection and calibrated stage thresholds require separate approval before implementation.
- **Approved documentation amendment:** Preserve future UI projection seams for cited plain-language “why” explanations, canonical rich timelines, privacy-safe coarse visual replay, idempotent one-tap appeals with governed evidence metadata, and fact-consistent role-redacted Support/rider/driver views. These seams add no raw-location exposure, provider, storage, decision authority or implementation authorization.
- **Approved channel/learning amendment:** Preserve provider-neutral future seams for voice/optional voice AI, video, screen sharing, co-browsing, purpose-expiring live location, typed family/diaspora participants, versioned knowledge, advisory quality/CSAT analytics and separately approved learning from eligible human-reviewed resolutions. These seams confer no provider, recording, tracking, UI, training, consequential score or AI decision authority.

### PA-041 — Mission 22 Rider and Driver UX architecture

- **Date:** 2026-07-16
- **Status:** Architecture approved by CTO on 2026-07-16 for documentation preservation only. No code, provider, UI deployment, production feature or activation is authorized.
- **Proposal:** Adopt role-specific presentation machines and shared UX grammar over versioned server projections, with idempotent commands, explicit pending/confirmed states, snapshot recovery, bilingual landmark/walking/exact-stop guidance, accessibility, separate airport Standard/Premium journeys, Ethiopian complex pickup patterns, first-use onboarding and persistent Trust/Safety access. See `docs/MISSION_22_RIDER_DRIVER_UX_ARCHITECTURE.md`.
- **Authority:** Immediate/Scheduled Dispatch, Active Ride, Dynamic Pickup, Mission 20, Pricing, Safety, Identity, Support/Recovery and Ledger retain their approved domains. UX and AI remain presentation/advice only.
- **Store strategy:** Differentiate through verifiable AYO strengths rather than competitor names or unshipped claims. Every asset must map to the submitted build and release evidence; Mission 20 cannot appear while disabled or uncertified.
- **Open gates:** Ethiopian field usability, Amharic content, accessibility, airport/venue terminology, safety operations, supported-device targets, Rider/Driver app packaging and prototype success thresholds require leadership/operations review before implementation.
- **Sequencing:** Stop after Mission 22 documentation. No later scope may be inferred without explicit leadership authorization.

### PA-042 — Mission 23 Dispatch Optimization architecture

- **Date:** 2026-07-16
- **Status:** Architecture approved by CTO on 2026-07-16 for documentation preservation. No runtime, migration, dependency, provider, route, production feature or activation authorized.
- **Proposal:** Coordinate existing dispatch domains through a deterministic versioned policy pipeline and a separate read-only Marketplace Health Engine; preserve exclusive sequential Immediate offers as launch default, Scheduled commitment locks, current-trip-first pre-dispatch, separate airport products, aggregate fairness monitoring and provider-neutral prediction shadowing. See `docs/MISSION_23_DISPATCH_OPTIMIZATION_ARCHITECTURE.md`.
- **Authority:** Mission 23 does not assign drivers or own offers/commitments/lifecycle. AI/predictions advise only and cannot remove, punish, price, bonus, restrict, override safety or bypass commitments. Marketplace health cannot execute its recommendations.
- **Alternatives:** Uncontrolled broadcast and a global learned optimizer are rejected for launch because delay, contention, distraction, data, bias, explainability and recovery costs are not justified. Bounded batch strategies require simulation and separate approval.
- **Open gates:** Addis zone definitions, offer/radius timing, airport operations, working-time/fatigue rules, opportunity/earnings metrics, privacy retention, simulation thresholds and any experiment require CTO/CEO and local operational/legal approval.

### PA-043 — Mission 24 Identity, Verification and Trust architecture

- **Date:** 2026-07-16
- **Status:** Architecture approved by CTO/CEO on 2026-07-16 for documentation preservation. No runtime, migration, dependency, identity/document/biometric provider, production route or activation authorized.
- **Proposal:** Preserve PostgreSQL identity/session authority and add a deterministic purpose-specific assurance orchestrator with separate rider/driver lifecycles, onboarding, document/vehicle results, eligibility projections, device/recovery controls, Trusted/Airport Driver policy, business/family/diaspora grants and independent appeal. See `docs/MISSION_24_IDENTITY_VERIFICATION_TRUST_ARCHITECTURE.md`.
- **Authority:** Authentication proves authenticator control; proofing binds approved evidence for a purpose; Eligibility/Safety decides service access. AI/OCR remains advisory and cannot approve identity/documents, recover/suspend accounts or grant eligibility.
- **Alternatives:** A single “verified” flag is rejected because it hides purpose, evidence, expiry and appeal. Provider-owned identity authority is deferred because legal, lock-in, outage, bias and data-sovereignty obligations are unresolved.
- **Open gates:** Ethiopian rider/driver proof requirements, Fayda boundary, document authorities, biometrics/liveness, OTP/provider operations, Trusted Driver policy, airport requirements, retention/cross-border rules and appeal staffing require leadership, local operations and qualified legal approval.

### PA-044 — Mission 25 Pricing and Marketplace Economics architecture

- **Date:** 2026-07-16
- **Status:** Architecture approved by CTO/CEO on 2026-07-16 for documentation preservation. No runtime, migration, dependency, provider, numeric policy, financial action, production route, deployment, push or activation is authorized.
- **Problem:** AYO needs rider-price clarity, sustainable driver earnings and auditable economics without allowing uncertainty, AI, Support, dispatch or payment channels to create hidden or unauthorized financial consequences.
- **Proposal:** Use immutable effective-dated pricing policies and deterministic minor-unit calculations for estimate/final/correction lineage; keep Incentives eligibility, Recovery authorization, Payment collection/reconciliation and Wallet/Ledger posting as separate authorities. See `docs/MISSION_25_PRICING_MARKETPLACE_ECONOMICS_ARCHITECTURE.md`.
- **Alternatives:** Static versioned tariffs are the recommended pilot baseline. Capped deterministic demand adjustment remains a separately approved extension; individualized learned pricing is rejected for opacity, discrimination, privacy and drift risk.
- **Authority:** Pricing alone calculates fares and financial-policy outcomes. Mission 20 supplies evidence only; Support investigates; Customer Recovery authorizes approved remedies; Wallet/Ledger alone moves value. AI and Marketplace Health advise only.
- **Open gates:** Ethiopian cost/affordability study, driver consultation, tax/legal/transport/airport review, cash reconciliation procedure, numeric policy, incentive/fatigue rules, demand-adjustment decision and simulation thresholds require separate leadership approval. Mission 20 certification/activation remains unchanged.

### PA-045 — Mission 26 Payments, Wallet, Ledger and Financial Integrity architecture

- **Date:** 2026-07-16
- **Status:** Architecture approved by CTO/CEO on 2026-07-16 for documentation preservation. No runtime, migration, dependency, provider, wallet/ledger, transaction, commit, push or activation is authorized.
- **Problem:** The legacy mutable wallet cannot safely represent cash, provider receipts, driver earnings, refunds or payouts and cannot be migrated as trusted value.
- **Proposal:** Use an immutable balanced PostgreSQL double-entry subledger with derived Driver/Rider/Business wallet projections; provider-neutral Payment attempts; independent cash/provider/bank reconciliation; compensating corrections; maker-checker adjustments; ETB-primary, currency-separated readiness. See `docs/MISSION_26_PAYMENTS_WALLET_LEDGER_FINANCIAL_INTEGRITY_ARCHITECTURE.md`.
- **Authority:** Pricing calculates; Payments orchestrates external attempts; Ledger alone posts money movement; Wallet derives views; Recovery authorizes remedies; Finance reconciles/accounts. AI cannot authorize or execute transactions.
- **Alternatives:** Mutable aggregates and provider-owned truth are rejected for audit/concurrency/lock-in gaps. Blockchain is rejected as unnecessary complexity.
- **Open gates:** NBE/legal classification, safeguarding/customer-funds treatment, provider licensing/contracts, accounting/chart mappings, cash obligations, payout/refund/chargeback policy, AML/CFT, PCI scope, retention, diaspora/FX and AYO Pay strategy require qualified approval.

### PP-046 — Implementation Phase 1 master-plan proposal

- **Date:** 2026-07-16
- **Status:** Master Plan approved by CTO/CEO on 2026-07-16. Only Increment 1 — Engineering Foundation and PostgreSQL Certification — is authorized; later increments remain gated.
- **Problem:** Approved missions need one dependency-safe implementation order that produces a complete pilot ride instead of activating disconnected features.
- **Proposal:** Certify foundations first, then identity/eligibility, ride/pickup, Immediate Dispatch, Active Ride, Pricing, immutable cash ledger, mobile MVP and support/operations; keep advanced features behind independent gates. See `docs/IMPLEMENTATION_PHASE_1_MASTER_PLAN.md`.
- **Boundary:** No Mission 27 is created. Mission 20 remains disabled and all PostgreSQL certification gates remain mandatory.

### AP-047 — Implementation Increment 1 foundation certification

- **Date:** 2026-07-16
- **Status:** Implementation approved by CTO/CEO on 2026-07-16 for local preservation. No push, deployment or business-feature activation authorized.
- **Decision:** Preserve the existing PostgreSQL/Alembic/audit/idempotency/health foundation and close the identified recovery gap with a standard-client, disposable backup/restore certification tool wired into CI.
- **Evidence:** PostgreSQL 17.10; migration 9/9; full suite 235 passed and one expected legacy-wallet xfail; 86.02% branch coverage; actual dump/restore and clean restart retained head `20260716_0014`; Ruff passed; dependency audit clean; no medium/high Bandit finding.
- **Boundary:** No authentication, ride, dispatch, pricing, payment, wallet or business behavior changed. Mission 20 remains disabled. Global strict mypy retains 34 pre-existing business-module errors and is not represented as passing.

### AP-048 — Implementation Increment 2 authentication security foundation

- **Date:** 2026-07-16
- **Status:** Implementation approved by CTO/CEO on 2026-07-16 for local preservation. No push, provider, public activation or business workflow authorized.
- **Decision:** Certify the existing PostgreSQL identity/session/challenge/token/RBAC/rate-limit foundation; make the verified subject resolver route-neutral; add deny-by-default server-resolved ownership enforcement with privacy-safe audit.
- **Authority:** Authentication establishes verified identity/session context; RBAC grants capability; owning domains resolve resource ownership. Clients cannot select identity, role, permission or owner. AI has no authority.
- **Exclusions:** No rides, dispatch, pricing, payments, wallet, provider connection, production signing key or Mission 20 activation.

### IP-049 — Implementation Increment 3 driver trust foundation

- **Date:** 2026-07-16
- **Status:** Implemented locally under explicit CTO/CEO authorization; awaiting review. No commit, push, provider or activation is authorized.
- **Decision:** Use typed onboarding transitions, immutable provider-neutral evidence references, separate vehicle approval/driver authorization and append-only versioned eligibility decisions with PostgreSQL optimistic concurrency and idempotency.
- **Authority:** Authenticated human Operations/Identity reviewers decide evidence and onboarding outcomes. Deterministic policy computes eligibility. AI, OCR and providers have no approval authority.
- **Alternatives:** A generic verified flag and provider-authoritative result were rejected as unauditable and unsafe; storing document images in ordinary relational payloads was rejected for privacy and operating risk.
- **Open gates:** Ethiopian document/issuer validity, inspection and expiry policy, reviewer procedure, appeals, retention, legal/privacy review and provider selection remain leadership/local-specialist decisions.

### IP-050 — Implementation Increment 4 canonical ride-request foundation

- **Date:** 2026-07-16
- **Status:** Implemented locally under explicit CTO/CEO authorization; awaiting review. No commit, push, public route or production activation is authorized.
- **Decision:** Add a PostgreSQL-authoritative Immediate Standard pre-dispatch aggregate with canonical pickup/destination metadata, configuration-driven rectangular service zones, deterministic validation, Rider-bound idempotency, optimistic versions, audit and transactional outbox.
- **Authority:** Authentication supplies Rider identity; Ride Request owns pre-dispatch request validity; Dispatch remains the only assignment authority; Pricing remains the only fare authority; Mission 20 remains disabled.
- **Alternatives:** Reusing the legacy in-memory ride object was rejected as non-durable and caller-shaped. PostGIS was deferred because reviewed pilot geometry does not yet justify a dependency; the containment contract preserves a replacement boundary.
- **Open gates:** Ethiopian service/prohibited zones, pickup accuracy/freshness values, address/landmark governance, consent, retention and cancellation reasons require separate leadership and local operational/legal approval.

### IP-051 — Implementation Increment 5 Immediate Dispatch handoff and localization

- **Date:** 2026-07-16
- **Status:** Implemented locally under explicit CTO/CEO authorization; awaiting review. No commit, push, public route, provider or production activation is authorized.
- **Decision:** Use a minimal versioned one-way handoff into the existing Immediate Dispatch authority; revalidate Driver Trust evidence; rank eligible candidates by deterministic pickup cost first; use bounded sequential offers and PostgreSQL assignment locks. Add a separate global presentation contract based on BCP 47 preferences, versioned translation keys and pack metadata.
- **Authority:** Ride Request owns validation and pre-assignment cancellation; Driver Trust owns eligibility evidence; Immediate Dispatch owns candidates, offers and assignment. Localization cannot alter domain state. AI has no assignment or critical-translation authority. Active Ride, Pricing and Mission 20 remain inactive.
- **Alternatives:** Direct assignment by Ride Request and uncontrolled broadcast offers were rejected because they duplicate authority and create races. Hard-coded English/Amharic prose was rejected because it couples authoritative data to presentation and blocks safe global extension.
- **Open gates:** Ethiopian dispatch timeouts, pickup-cost provider/policy, availability retention, destination disclosure, fatigue/commitment rules, approved initial languages, fallback order and human translation governance require leadership and local operational review.

### IP-052 — Implementation Increment 6 Active Ride lifecycle foundation

- **Date:** 2026-07-16
- **Status:** Implemented locally under explicit CTO/CEO authorization; awaiting review. No automatic commit, push, public route or production activation is authorized.
- **Decision:** Evolve the existing Active Ride authority with a canonical post-assignment state path, explicit cancellation/interruption states, source assignment lineage, immutable sequenced transition events, locked projections, ride-bound idempotency, replay validation and transactional outbox.
- **Authority:** Ride Request owns the pre-dispatch request; Immediate Dispatch owns assignment; Active Ride alone owns post-assignment state. Completion is evidence for future consumers, not authorization for Pricing, Wallet/Ledger, Growth, Bonus, Family, Status or Trust action. AI has no state authority.
- **Alternatives:** A second lifecycle aggregate was rejected because it would conflict with Mission 19 authority. Destructively replacing older readable states was rejected because it breaks existing consumers; new handoffs use only the canonical path while compatibility is retained.
- **Open gates:** Ethiopian cancellation reasons, pickup confirmation evidence, interruption/resumption operations, event/location retention, Family consent, future consumer policies and load thresholds require separate approval.

### IP-053 — Implementation Increment 7 versioned ETB Pricing foundation

- **Date:** 2026-07-16
- **Status:** Implemented locally under explicit CTO/CEO authorization; awaiting review. No automatic commit, push, production tariff, provider, public route or activation is authorized.
- **Decision:** Add an immutable effective-dated Immediate Standard ETB policy lifecycle, integer-only deterministic engine, owned expiring estimates, policy-locked acceptance, completed canonical-ride final calculation, role-safe breakdowns, append-only correction lineage and transactional pricing outbox. Every financial result also carries a complete formula-versioned calculation snapshot containing policy approval lineage, sourced route inputs, provider version, numeric operands, components, rounding, canonical input hash, corrections and event lineage, and is mechanically reproducible without AI or undocumented calculation.
- **Authority:** Pricing calculates only. Ride Request, Dispatch and Active Ride remain upstream fact authorities; Incentives owns eligibility; Payments interacts with providers; Ledger alone moves value; Wallet derives views. Mission 20 supplies no runtime input while disabled. AI and clients cannot determine money.
- **Alternatives:** Client-side totals and floating-point money were rejected as manipulable and non-deterministic. Mutable tariffs/calculations and downstream fare recalculation were rejected as retroactive, divergent and unauditable. Opaque AI-derived amounts were rejected. A provider-specific routing integration was deferred because approved synthetic evidence is sufficient for this foundation.
- **Open gates:** Ethiopian tariff/cost/affordability evidence, Driver consultation, commission, tax, rounding/display, material-difference review, cash procedure, correction roles, retention and dispute policy require separate leadership and qualified local review.
- **Permanent traceability amendment:** Every Pricing artifact stores an immutable lifecycle-reference snapshot. Final/corrected records explicitly carry Ride Request, Dispatch Handoff, Assignment, Active Ride, Estimate and Calculation identities; corrections append predecessor links. The persistence layer now rejects missing, mismatched, forged or cross-ride lineage and requires a distinct predecessor chain for corrections. Future Ledger, Wallet and Settlement artifacts must carry this chain forward without overwriting Pricing or reconstructing relationships. A separately permissioned Ride-ID journey projection is available to authorized Support, Finance and Audit and fails closed on conflicting lineage.

### IP-054 — Implementation Increment 8 financial ledger foundation

- **Date:** 2026-07-17
- **Status:** Implemented locally under explicit CTO/CEO authorization; awaiting review. No commit, push, payment provider, wallet product, settlement, payout, refund, promotion, referral, loyalty, tax execution or production activation is authorized.
- **Decision:** Add an immutable PostgreSQL double-entry ledger foundation with append-only books/accounts/journals/entries, transaction-safe idempotent posting, deterministic replay payloads, append-only ledger events/outbox, strict traceability validation against authoritative Pricing calculation lineage and compensating-journal linkage for corrections.
- **Authority:** Ledger records financial truth only and executes no payment. Pricing remains amount authority; future Payments orchestrates external attempts; future Wallet projects derived views; Reconciliation/Finance own external mismatch and accounting workflows. AI may explain ledger data but has no ledger mutation authority.
- **Alternatives:** Mutable balance aggregates were rejected as race-prone and unauditable. Provider-owned financial truth was rejected for lock-in and incomplete cash semantics. Distributed-ledger/blockchain options were rejected as unjustified complexity/cost.
- **Open gates:** Ethiopian legal/accounting approvals for chart mappings, safeguarding/funds treatment, AML/CFT and tax-reporting boundaries; provider licensing/contracts; payout/refund policy; multi-currency/FX policy; operational reconciliation procedures and production activation criteria.

### WG-001 — Migration 0016 controlled PRE-PRODUCTION correction

- **Date:** 2026-08-04
- **Status:** Founder and CTO approved Batch 0 reconciliation only. PostgreSQL certification, production, deployment and later reconciliation batches remain unauthorized.
- **Decision:** Admit corrected migration blob `3c1e4b8400567b154582ffbb5f7426d933db1d23` as a one-time PRE-PRODUCTION historical replay correction. Preserve original blob `c09fc7efec392e8068c7adf62e32fbe2f7b4ecfd` as distinct history.
- **Reason:** Revision `0016` executes before canonical Subject exists, so a later forward migration cannot repair a clean replay failure inside `0016`. The correction temporarily excludes only future `ayo.canonical_subjects` foreign keys and restores them to metadata after historical table creation.
- **Permanent rule:** After this checkpoint, revision `0016` is immutable. Every later schema correction uses a new forward migration. No history rewrite, renumbering or silent retroactive change is permitted.
- **Boundary:** This decision creates no PostgreSQL certification, production readiness, deployment, backup, cleanup or Batch 1 authority.

### AP-055 — PRE-PRODUCTION merchant operational Pickup read ownership

- **Date:** 2026-08-09
- **Status:** Founder/CEO implementation authorization granted for the bounded read-only foundation; awaiting CTO review. Merge, visible merchant order/ACK UI, ACK facade/provider composition and production activation remain unauthorized.
- **Problem:** Merchant ACK command custody exists, but the mobile merchant shell previously had no authoritative order/Pickup operation context or normal owner for the canonical merchant Pickup status read. Route identifiers therefore could not safely become command evidence.
- **Decision:** Treat an order identifier only as an untrusted lookup request under the currently selected authenticated merchant. Promote a fresh operation context only after the existing canonical merchant Pickup endpoint succeeds and returns a strictly parsed server Pickup identifier. Maintain identity continuity, operation generation, single-flight refresh, immediate freshness retirement and request-generation/abort stale-response containment in a bounded provider mounted at the authenticated operational shell.
- **Authority and efficiency:** The existing Pickup endpoint independently verifies merchant ownership, APPROVED state, merchant/order binding and read permission, so an additional merchant-order detail or list GET would add latency without adding authority. The backend remains final authority. A definitive bounded 404 creates no Pickup context; transient failure may retain display-only stale data but never fresh command authority.
- **Alternatives:** Inventing a global “current order,” selecting an arbitrary list result, accepting route-supplied Pickup identity, or adding a generic store were rejected. A detail-plus-status two-GET flow was rejected as redundant under the existing endpoint contract.
- **Boundary:** No ACK scope/controller/facade, command attempt, POST, UI, localization, Custody client, polling, persistence, backend, schema, dependency or production change is authorized by this decision.

### AP-056 — PRE-PRODUCTION bounded merchant arrival-acknowledgement capability

- **Date:** 2026-08-09
- **Status:** Founder/CEO implementation authorization granted for the bounded provider/presentation capability; awaiting CTO review. Merge, visible interaction and production activation remain unauthorized.
- **Problem:** The admitted merchant Pickup reader and ACK controller had no safe composition boundary for future presentation. Exposing either trusted reader/writer or command custody would let presentation manufacture authority or bypass operation isolation.
- **Decision:** Mount one stable ACK scope/controller inside the merchant operational Pickup-provider lifetime. Use public read state only as a reactivity signal, re-read the infrastructure-only trusted operation in layout lifecycle, and expose a frozen capability containing bounded state, pure availability reads and controller-delegated ACK/reconcile calls. Bind each emitted capability to a private trusted-publication token so a stale Merchant A/order/Pickup capability cannot act on a replacement operation.
- **Authority and resilience:** Command identity comes only from the trusted identity runtime; merchant/order/Pickup/version/action evidence comes only from the canonical trusted Pickup operation. The controller retains attempt/key, dispatch provenance, consumed-version suppression, uncertainty and retry custody. Unexpected failures remain fail-closed through the controller's existing `outcome_unknown` settlement, so no second facade latch is introduced.
- **Alternatives:** Presentation access to the raw scope/controller/service, a generic command framework, deriving authority from display-only state, provider reconstruction per snapshot, and automatic read/retry/reconciliation were rejected as authority leaks or custody regressions.
- **Boundary:** No visible UI, localization, Custody client, persistence, polling, backend, schema, dependency, workflow or production activation is added.

### AP-057 — PRE-PRODUCTION merchant operational order read and selection surface

- **Date:** 2026-08-09
- **Status:** Founder/CEO implementation authorization granted after CTO live-main verification; awaiting CTO review. Merge, visible merchant ACK interaction and production activation remain unauthorized.
- **Problem and beneficiary:** An authenticated merchant could enter the merchant area but saw only a placeholder, leaving no real server-authorized order entry path into the admitted Pickup reader. Merchants need a calm, bounded way to choose a real order before any later ACK control can be safely reachable. Success is one bounded list read on entry, explicit selection, one selected-order Pickup read, zero mutation and zero cross-merchant/identity carryover.
- **Decision:** Use the existing authenticated `GET /mobile/merchants/{merchant_id}/orders?limit=25` contract through the canonical authenticated-read transport. Strictly parse the complete merchant-safe view and expose only order ID, state, version and creation time. Reject the entire list if any row is malformed, because silently omitting a real operational order would present incomplete truth. Explicit selection alone invokes the admitted PR #64 `inspectOrder(orderId)`; no first/newest/global order is inferred.
- **Alternatives:** A list-plus-detail flow was rejected because the list already contains every field needed for selection and a detail GET would add weak-network latency without authority. Raw UUID entry, route-owned order authority, automatic first-order selection, per-row Pickup reads, polling, persistence and a generic store were rejected as authority, privacy, cost or complexity regressions.
- **Security, privacy and resilience:** Backend authentication, merchant ownership, APPROVED state and `merchant_orders.read_own` remain authoritative. Customer identity, lines, pricing and internal rejection evidence are parsed but not exposed. The PostgreSQL projection now allowlists the existing strict `MerchantOrderRecord` public fields, so `customer_identity_id`, `availability_evaluation_id`, `composition_hash` and `access_interaction_id` remain excluded unless that approved public model intentionally changes. Merchant/identity replacement clears list, selection and Pickup inspection. Transient refresh can retain display-only stale orders; stale display never grants Pickup or ACK authority. A narrow read-side `clearInspection()` retires PR #64 state when selection disappears.
- **Ethiopian/operational fit and residual risk:** The surface uses one bounded initial GET, no N+1 reads, no polling and English/Amharic copy suitable for weak networks and mixed devices. Courier-pickup Amharic wording is marked `NEEDS_NATIVE_AMHARIC_REVIEW` before production. One narrow backend correctness repair restores the already-approved merchant-safe projection without expanding the `MerchantOrderView` wire contract. No customer PII exposure, new endpoint, schema, migration, dependency or lockfile change, Custody, payment, mutation feature or production activation is added.

### AP-058 — PRE-PRODUCTION merchant ACK presentation-state publication ownership

- **Date:** 2026-08-09
- **Status:** Founder/CEO implementation authorization granted after CTO live inspection; awaiting CTO review. Visible merchant ACK interaction, merge and production activation remain unauthorized.
- **Problem:** The bounded ACK capability already prevented stale publications from delegating commands, but its exported state mirrored a stable shared controller without proving which merchant/order/Pickup publication owned that operation. A future presentation consumer could therefore misattribute one publication's submitting, applied or uncertain status to another.
- **Decision:** Privately bind controller presentation state only when an explicit ACK or reconciliation invocation delegates for the current semantic publication. Expose that state only when all publication dimensions match: merchant, order, Pickup, context generation, Pickup version and identity-continuity handle. During freshness absence or replacement expose neutral idle; exact semantic restoration may reveal retained controller custody again. Command authority, scope/controller lifetime and the public capability shape remain unchanged.
- **Boundary:** This adds no visible UI, localization, network request, command semantic, backend, schema, dependency, persistence or production activation.

### AP-059 — First visible PRE-PRODUCTION merchant arrival acknowledgement

- **Date:** 2026-08-10
- **Status:** Founder/CEO implementation authorization granted; awaiting CTO review. Merge and production activation remain unauthorized.
- **Problem:** Merchants can select a canonical order and inspect trusted courier-arrival truth, but cannot yet explicitly acknowledge arrival from the merchant surface.
- **Decision:** Add one calm localized action to the selected Pickup panel. Presentation consumes only the locked publication-scoped capability state and its actionability predicates; explicit taps delegate ACK, reconciliation or same-attempt retry to that capability. No render, mount, effect, timer or background path invokes a command.
- **Boundary:** No command identity or infrastructure escapes to UI. No backend, schema, dependency, persistence, Custody, payment, courier/rider, automatic retry/reconciliation, polling or production activation is added. Amharic operational wording remains subject to native review.

### AP-060 — AYO Intelligence Phase 1 bounded operational recommendation

- **Date:** 2026-08-10
- **Status:** Founder/CEO implementation authorization granted; awaiting CTO review. Merge, visible intelligence presentation, model integration and production activation remain unauthorized.
- **Problem:** Future merchant guidance needs to explain trusted acknowledgement state and the next safe action without receiving or reconstructing command authority.
- **Decision:** Add one deterministic, synchronous and immutable recommendation function over privacy-minimal presentation evidence: ACK status and the bounded capability's two actionability predicates. It emits typed recommendation and reason keys only. Capability predicates remain final action authority; unknown or contradictory evidence fails closed. The intelligence has no command callback, controller, scope, identifier, attempt, key, service or transport.
- **Boundary:** This first intelligence capability advises only. It adds no LLM/model, arbitrary prose, external request, autonomous action, UI, localization, persistence, backend, schema, dependency, polling or timer. Future natural-language intelligence must consume the bounded recommendation rather than command internals. PRE-PRODUCTION only.

### AP-061 — AYO Intelligence Phase 2 bounded natural-language explanation

- **Date:** 2026-08-10
- **Status:** Founder/CEO implementation authorization granted; awaiting CTO review. Merge, generative-model integration and production activation remain unauthorized.
- **Problem:** The merchant ACK panel exposes correct bounded state and controls, but merchants need a concise explanation of what is happening, why, and what safe next action is available without giving a language layer command authority.
- **Decision:** Convert only the locked Phase 1 recommendation into deterministic English/Amharic headline, body and optional descriptive action-label semantics. Replace competing ACK state prose in the existing panel with this single guidance source while leaving all buttons and invocation ownership in the locked presentation capability. Exhaustive reason mapping and an exhaustive capability-state adapter prevent silent drift; malformed combinations fail closed to hidden neutral language.
- **Boundary:** Phase 2 has no command callback, identifier, model/LLM, prompt, external network, persistence, polling, timer or autonomous action. Amharic operational wording remains `NEEDS_NATIVE_AMHARIC_REVIEW`. PRE-PRODUCTION only. Any future generative intelligence must consume this bounded language contract rather than command internals.

### AP-062 — AYO Intelligence Phase 3 bounded generative explanation gateway

- **Date:** 2026-08-10
- **Status:** Founder/CEO implementation authorization granted; awaiting CTO review. Merge, live-provider activation, broader intelligence and production activation remain unauthorized.
- **Problem:** A future model may help phrase an already-bounded merchant operational explanation, but arbitrary model output cannot become operational truth, authority or a dependency of the merchant workflow.
- **Decision:** Add one stateless provider-neutral explanation gateway over privacy-minimal Phase 1 semantics and the locked Phase 2 localized result. The request and response schemas are strict, bounded and immutable; every failure returns Phase 2 immediately. The initial validation policy accepts generated text only when it exactly preserves the locked Phase 2 wording because schema or lexical checks cannot prove arbitrary prose semantically safe.
- **Authority and privacy:** Trusted capabilities and Phase 1 retain facts and action authority; Phase 2 retains deterministic language authority and fallback. The gateway exposes no tool, callback, identifier, command custody, PII, location, payment data, memory, RAG or persistence. It is provider-neutral and has no model SDK, external request or secret.
- **Boundary:** PRE-PRODUCTION foundation only. No live provider, UI integration, background work, backend, schema, migration, dependency or production activation is added. Any live provider, expanded semantic acceptance policy or generative UX requires separate CTO review and Founder/CEO authorization.

### AP-063 — AYO Intelligence Phase 4 secure live-provider execution boundary

- **Date:** 2026-08-10
- **Status:** Founder/CEO implementation authorization granted; awaiting CTO review. Live-provider activation, merge, broader rephrasing and production activation remain unauthorized.
- **Problem:** The locked provider-neutral mobile gateway had no authenticated, abuse-bounded server execution path through which a future external text provider could be called without placing secrets or generic model access in mobile.
- **Decision:** Add one disabled-by-default PRE-PRODUCTION merchant-explanation endpoint accepting only the strict Phase 3 semantic keys. Authentication and the existing merchant read permission gate access; strict schema/coherence and request-size checks run before one rate-limited, two-second provider attempt. Model-bound deterministic language is derived from the server-owned English/Amharic Phase 2 contract, so mobile cannot submit prose; dual mobile/server copies carry an explicit exact-equivalence test obligation. The AYO-owned provider interface is merchant-explanation-specific and exposes no arbitrary prompt, model, tools, command, memory or provider metadata. Cancellation propagates and no automatic provider retry occurs.
- **Safety boundary:** Secrets remain server-side; no provider credential or provider-specific adapter is introduced. Phase 3 continues to treat output as untrusted and requires exact Phase 2 headline/body preservation, while Phase 2 remains the immediate weak-network/outage fallback. No tool calling, command authority, memory, RAG, identifier enrichment, persistence, schema, migration, dependency, visible UI or production activation is added. Broader generative rephrasing requires separate authorization.

### AP-064 — AYO Intelligence Phase 5 provider evaluation and admission governance

- **Date:** 2026-08-10
- **Status:** CTO technical review `APPROVED WITH CONDITIONS` on 2026-08-10; Founder/CEO implementation approval granted for this exact offline scope. Awaiting post-implementation CTO review. No live evaluation, provider admission, activation, production approval or merge is authorized.
- **Problem:** Changing model, policy, retention, regional, reliability, language and cost claims cannot safely be compared by brand, benchmarks or documentation alone, and evaluation must not silently become admission or activation.
- **Decision:** Add a bounded, typed offline evaluator and a versioned synthetic corpus containing the ten currently provider-callable merchant ACK reasons in English and Amharic (20 scenarios). Strict immutable evidence binds provider, exact model, product/tier, official source, review/validity dates, applicability, conclusion and uncertainty. Explicit hard gates independently cover privacy, training/data use, retention, regional/data location, security, exact preservation, locale, two-second p95 latency, reliability, server-only integration, no mobile credentials/client prose, structured output, pinned version, tool-free/stateless operation, provider neutrality, no automatic retry/failover, native Amharic human review, evidence freshness and production-disabled state. Comparative metrics cannot override a failed gate.
- **Authority:** Evaluation, admission recommendation, Founder approval, pre-production activation eligibility and production approval are separate manual governance states with no automatic transitions. Manual progression is structurally constrained: each advanced record embeds the same exact eligible, current evaluation and its immediately preceding manual record; Founder states also require explicit Founder evidence. General provider availability is not AYO account eligibility. Native Amharic quality requires named, dated human evidence. The evaluator has no live provider callback, credential, command, tool, runtime activation, memory or RAG authority.
- **Alternatives:** Documentation-only comparison was rejected as insufficiently enforceable. Live adapters were rejected because account, privacy, retention, region, language, latency, reliability and admission evidence is absent. A generic multi-provider router was rejected as premature production complexity. The approved offline typed foundation is the smallest enforceable option.
- **Boundary:** Synthetic data and version-controlled evidence only; Phases 1–4 and product runtime remain unchanged. No live call, provider SDK, mobile change, endpoint, schema, migration, dependency, persistence, background monitoring or production configuration is introduced. Future controlled live evaluation requires separate Founder/CEO authorization after CTO review; broader generative rephrasing remains unauthorized.

### AP-065 — AYO Intelligence Phase 6 controlled synthetic provider evaluation

- **Date:** 2026-08-10
- **Status:** CTO technical review and Founder/CEO approval covered one controlled 20-call synthetic evaluation and this evidence-capture repair. The first attempt is `EXECUTED_BUT_EVIDENCE_NOT_ADMISSIBLE`; no second run is authorized.
- **Decision:** Use one engineering-only OpenAI edge with the exact `merchant_ack_corpus_v1`, the pinned `gpt-5.4-mini-2026-03-17` snapshot, sequential calls, one call per scenario, a two-second timeout, no retry, no failover, no tools and no storage. Sanitized observations feed the locked Phase 5 evaluator without automatic governance progression or runtime activation.
- **Evidence integrity:** The first attempt completed all 20 calls and transient evaluation, but its console-dependent JSON sink failed when Windows `cp1252` could not encode Amharic. No results may be reconstructed or inferred. Future separately authorized execution must first persist deterministic UTF-8 JSON through a same-directory temporary file, flush and fsync it, and atomically replace the gitignored engineering artifact before any optional ASCII-only console summary. Credentials, authorization headers, raw provider transport/responses, request identifiers, user data and operational identifiers are excluded.
- **Authority:** No admissible technical evaluation, provider recommendation, admission, activation or production approval resulted. Native Amharic review and account-policy gates remain separate. This repair made zero live provider calls. A second controlled evaluation requires separate Founder/CEO authorization; broader generative rephrasing remains unauthorized.

### AP-066 — AYO Intelligence Phase 6 Run 2 admissible technical provider evaluation

- **Date:** 2026-08-10
- **Status:** Founder/CEO authorized one Run 2 execution; CTO admits its technical evidence. The evaluated candidate is not eligible for admission recommendation. No further run, recommendation, admission, activation, runtime integration, production approval or Phase 7 is authorized.
- **Evidence identity:** Authoritative main `517d7d0ccc3d40cb0831c64b0d03ca01d1adb83c`, tree `47208b0cb691d6c8486fa2c2e2e90b95aebf34e0`; OpenAI `gpt-5.4-mini-2026-03-17`; `merchant_ack_corpus_v1`; 20 fixed synthetic scenarios; evidence-byte SHA-256 `53644f537440ca1f5b6cc59d33e31a2d91ffaab7ec72e81a0d251d55c17391fb`. The raw UTF-8 artifact remains gitignored and uncommitted.
- **Observed result:** Exactly 20 sequential attempts, zero retries and zero failover produced 18 responses, two timeouts, zero malformed outputs and zero provider errors. Exact preservation, locale adherence and reliability were each 18/20 (90%). English was 8/10 exact and locale-correct with two timeouts; all 10 returned Amharic scenarios were exact and locale-correct. Latency was 1,228 ms minimum, 1,588 ms median, 2,054 ms p95, 2,093 ms p99 and 2,093 ms maximum. Usage was 2,819 input and 1,379 output tokens; estimated cost was USD 0.00831975.
- **Hard gates:** `MET`: server-side-only, mobile credentials absent, arbitrary client prose forbidden, structured output, exact model version, automatic retry disabled, automatic failover absent, tool-free, stateless, provider-neutral, production disabled and corpus complete. `FAIL`: evidence freshness, exact preservation, locale adherence, latency and reliability. The locked latency gate is p95 at most 2,000 ms; observed p95 2,054 ms remains a failure. `UNKNOWN`: privacy, training/data use, retention, regional/data location, security/compliance and Amharic human review. `NEEDS_NATIVE_AMHARIC_REVIEW` remains required.
- **Decision and boundary:** `eligible_for_admission_recommendation=false`. Strong exact behavior on successful requests, including 10/10 Amharic machine responses, does not override two timeouts, 90% completeness-dependent rates, the failed latency gate or unresolved policy/account and native-language gates. Technically evaluated does not mean recommended, admitted, Founder-approved, activation-eligible, activated or production-approved. Only synthetic canonical text was used; no user/product data, tools, memory, runtime integration or automatic governance progression exists. No hard gate was relaxed, and no further live run is authorized.

### AP-067 — AYO Intelligence Phase 7 faster-model evaluation readiness

- **Date:** 2026-08-10
- **Status:** CTO technical review and Founder/CEO approval authorize only a readiness candidate before execution. No Phase 7 provider call has occurred. Live execution remains blocked pending review, merge authorization, merge and post-merge lock of this candidate.
- **Problem:** Phase 6's exact `gpt-5.4-mini-2026-03-17` evidence failed the locked two-second p95, reliability, exact-preservation and locale gates. A smaller current model may be faster, but the locked harness hard-coded the Phase 6 model, pricing and artifact path and therefore cannot safely run a distinct experiment unchanged.
- **Decision:** Reuse the locked OpenAI request, fixed `merchant_ack_corpus_v1`, strict schema, observation, Phase 5 evaluator and UTF-8 atomic persistence through one immutable candidate configuration. Phase 7 fixes only OpenAI `gpt-5.4-nano-2026-03-17`, current USD 0.20/M input and USD 1.25/M output pricing, and a separate gitignored `artifacts/intelligence/phase7/controlled_openai_nano_evaluation.json` path. Existing evidence causes a pre-call stop; Phase 6 behavior and evidence remain intact.
- **Alternatives:** Re-running mini would not test the faster-model hypothesis. Switching provider was deferred because it adds account, credential, policy and edge-adapter variables. A copied second harness and generic model router were rejected as duplication and premature runtime architecture.
- **Boundary:** The same 20 synthetic scenarios, sequential execution, maximum one call per scenario, two-second timeout, no retry/failover, `store: false`, no tools, statelessness, exact preservation and all Phase 5 hard gates remain authoritative. No runtime/mobile integration, user data, gate change, recommendation, admission, activation or production approval exists. Native Amharic review and policy/account gates remain unresolved. Broader generative rephrasing remains unauthorized.

### AP-068 — AYO Intelligence Phase 7 nano admissible technical evaluation

- **Date:** 2026-08-10
- **Status:** Founder/CEO authorized one Phase 7 execution and CTO admits its technical evidence. The evaluated candidate is not eligible for admission recommendation. No further Phase 7 run, recommendation, admission, Founder approval, activation eligibility, activation, runtime integration, production approval or Phase 8 is authorized.
- **Evidence identity:** Execution used authoritative main `1a2181c82ce600d6dc383adec3a8123e4189c4f7`, tree `1e7c81a13e8f65394c12e974f6142c4a0d79b4c6`; OpenAI `gpt-5.4-nano-2026-03-17`; `merchant_ack_corpus_v1`; 20 fixed synthetic scenarios; evidence-byte SHA-256 `bd7a28bb7bd323a4be0981f3248df9081a5fdced87db3ec7e4f100b8f2ba3544`. The raw UTF-8 artifact remains gitignored and uncommitted.
- **Observed result:** Exactly 20 sequential attempts with zero retries and zero failover produced 18 responses, two timeouts, zero malformed outputs and zero provider errors. Exact preservation, locale adherence and reliability were each 18/20 (90%). English and Amharic each produced 9/10 exact, locale-correct responses and one timeout. Latency was 1,021 ms minimum, 1,604 ms median, 2,073 ms p95, 2,126 ms p99 and 2,126 ms maximum. Usage was 2,760 input and 1,320 output tokens; estimated cost was USD 0.002202.
- **Hard gates:** `MET`: server-side-only, mobile credentials absent, arbitrary client prose forbidden, structured output, exact model version, automatic retry disabled, automatic failover absent, tool-free, stateless, provider-neutral, production disabled and corpus complete. `FAIL`: evidence freshness, exact preservation, locale adherence, latency and reliability. The locked latency gate is p95 at most 2,000 ms; observed p95 2,073 ms remains a failure. `UNKNOWN`: privacy, training/data use, retention, regional/data location, security/compliance and Amharic human review. `NEEDS_NATIVE_AMHARIC_REVIEW` remains required.
- **Decision and comparison:** `eligible_for_admission_recommendation=false`. Nano materially reduced estimated cost from Phase 6 mini's USD 0.00831975 to USD 0.002202, but both exact snapshots produced 18/20 responses and 90% reliability, exact preservation and locale adherence; nano p95 was 19 ms slower than mini's 2,054 ms. The smaller model did not resolve the observed AYO latency/reliability failure under these locked experiments. This bounded result does not establish universal model performance or permanent provider rejection.
- **Boundary:** Only synthetic canonical text was used. No user/product data, tool, memory, raw provider response, runtime integration or automatic governance progression exists. Technically evaluated does not mean recommended, admitted, Founder-approved, activation-eligible, activated or production-approved. The two timeouts remain admissible evidence; no further Phase 7 run is authorized, and broader generative rephrasing remains unauthorized.

### AP-069 — AYO Intelligence Phase 8 Anthropic Haiku controlled-evaluation readiness

- **Date:** 2026-08-10
- **Status:** Founder/CEO and CTO approve architecture/readiness only for Anthropic `claude-haiku-4-5-20251001`. No account, credential, provider call, recommendation, admission, activation, production use, runtime integration or Phase 9 is authorized. Any live evaluation requires separate approval after candidate review, merge authorization, merge and post-merge lock.
- **Problem and research decision:** The Phase 6 mini and Phase 7 nano evidence each failed the locked reliability, exact-preservation, locale and p95 latency gates. Phase 8 research selected Anthropic's fastest exact dated Haiku snapshot as the next technical-evaluation candidate because current official evidence supports pinned model identity and GA Structured Outputs. Candidate status is not provider recommendation.
- **Architecture:** Preserve `merchant_ack_corpus_v1`, `ProviderObservation`, the Phase 5 evaluator, immutable sanitized result and UTF-8 atomic writer. Add only a separate engineering Anthropic Messages API edge fixed to `POST /v1/messages`, `anthropic-version: 2023-06-01`, the exact dated model and a closed `locale`/`headline`/`body` schema. The existing OpenAI runners remain unchanged. Phase 8 evidence is isolated at `artifacts/intelligence/phase8/controlled_anthropic_haiku_evaluation.json` and an existing artifact refuses execution before credential access or a call.
- **Locked boundary:** Exactly 20 sequential canonical requests maximum, one attempt per scenario, two-second timeout, zero retry/failover, no tools, thinking, history, arbitrary prompt or service-tier assumption. The first canonical request must bear any structured-schema compilation cost; no warm-up or preflight call exists. Only `stop_reason: "end_turn"` may become a successful response; every abnormal, missing or future completion reason fails closed as `MALFORMED` before content parsing, even if its text is valid canonical JSON. Schema validity never replaces exact canonical comparison. All Phase 5/6/7 hard gates remain unchanged.
- **Unresolved evidence:** Current USD 1/M input and USD 5/M output pricing is comparative only. AYO account access, rate limits, billing, privacy, training use, retention/ZDR, region/data location and security/compliance remain `UNKNOWN`. Native Amharic review remains `NEEDS_NATIVE_AMHARIC_REVIEW`. No Priority Tier entitlement is assumed.
- **Isolation:** The readiness runner is manual engineering tooling only and is not imported by routes, `main.py`, startup, workers, schedulers, mobile or UI. No provider is connected to product runtime and production remains disabled. See `docs/AYO_INTELLIGENCE_PHASE_8_HAIKU_READINESS.md`.

### AP-070 — AYO Intelligence Phase 8 Haiku admissible technical evaluation

- **Date:** 2026-08-11
- **Status:** Founder/CEO authorized one Phase 8 execution; awaiting CTO review of its technical evidence. The evaluated candidate is not eligible for admission recommendation. No further Phase 8 run, recommendation, admission, Founder approval, activation eligibility, activation, runtime integration, production approval or Phase 9 is authorized.
- **Evidence identity:** Execution used authoritative main `8b4413be4c914fcb71315a2946c9c171abb6efc2`, tree `534ae673489814506aef7b3152a87d2143373774`; Anthropic `claude-haiku-4-5-20251001`; `merchant_ack_corpus_v1`; 20 fixed synthetic scenarios; evidence-byte SHA-256 `5cc2746feffec07df8274432ab113c1194e232ede9add5d751d214b30d3e1a73`. The raw UTF-8 artifact remains gitignored and uncommitted.
- **Observed result:** Exactly 20 sequential attempts with zero retries and zero failover produced 13 responses, seven timeouts, zero malformed outputs and zero provider errors. Exact preservation, locale adherence and reliability were each 13/20 (65%). English returned 6/10 and Amharic returned 7/10 exact, locale-correct responses; the remaining scenarios timed out. Latency was 1,041 ms minimum, 1,537 ms median, 2,057 ms p95, 2,088 ms p99 and 2,088 ms maximum. Usage was 4,011 input and 657 output tokens; estimated cost was USD 0.007296.
- **Hard gates:** `MET`: server-side-only, mobile credentials absent, arbitrary client prose forbidden, structured output, exact model version, automatic retry disabled, automatic failover absent, tool-free, stateless, provider-neutral, production disabled and corpus complete. `FAIL`: evidence freshness, exact preservation, locale adherence, latency and reliability. The locked latency gate is p95 at most 2,000 ms; observed p95 2,057 ms remains a failure. `UNKNOWN`: privacy, training/data use, retention, regional/data location, security/compliance and Amharic human review. `NEEDS_NATIVE_AMHARIC_REVIEW` remains required.
- **Decision and comparison:** `eligible_for_admission_recommendation=false`. Haiku returned 13/20 responses and 65% reliability, exact preservation and locale adherence, below the 18/20 and 90% recorded by both Phase 6 mini and Phase 7 nano. Haiku p95 was 3 ms slower than mini and 16 ms faster than nano, while all three exceeded the locked two-second gate. The provider change did not resolve the observed AYO gates under these exact controlled runs; this does not establish universal model performance or permanent provider rejection.
- **Boundary:** Only synthetic canonical text was used. No user/product data, tool, memory, raw provider transport, runtime integration or automatic governance progression exists. Technically evaluated does not mean recommended, admitted, Founder-approved, activation-eligible, activated or production-approved. The seven timeouts remain admissible evidence; no further Phase 8 run or Phase 9 is authorized. CTO review of this documentation-only evidence record is the next gate.

### AP-071 — AYO Intelligence Phase 9 deterministic-first Merchant ACK architecture

- **Date:** 2026-08-11
- **Status:** CTO final architecture decision approved; Founder/CEO approved this exact architecture scope. Documentation-only governance candidate awaiting review and merge authorization. No source/runtime implementation, provider call, credential access, provider recommendation/admission/activation, diagnostic execution or Phase 10 is authorized.
- **Research evidence:** Phase 6 mini returned 18/20 with 90% reliability/exactness/locale and 2,054 ms p95; Phase 7 nano returned 18/20, 90% and 2,073 ms p95; Phase 8 Haiku returned 13/20, 65% and 2,057 ms p95. All returned responses preserved canonical content and locale, while timeout/latency dominated failures. Historical transports created a fresh HTTPS connection per scenario and did not decompose network/provider latency. These bounded experiments reject the candidates under the locked screen but do not establish universal provider performance.
- **Decision:** The required synchronous path is trusted Merchant ACK capability/state validation, Phase 1 deterministic recommendation, Phase 2 deterministic English/Amharic language and immediate merchant presentation. Phase 1 remains the decision layer and Phase 2 the explanation layer without semantic change. Generative inference is removed from this use case's product path; no synchronous or asynchronous Merchant ACK generation is approved because deterministic Phase 2 already solves the bounded problem and no incremental user value is demonstrated.
- **Authority and failure:** Intelligence may interpret authority and explain authority but may never create authority. Capability/controller/backend domains retain command authority. Contradictory, stale, missing, malformed, unsupported or incoherent evidence fails closed without optimistic inference, command dispatch, automatic acknowledgement, retry, reconciliation or fabricated availability.
- **Tooling and runtime boundary:** Phase 3–8 history and Phase 6/7/8 runners remain valid engineering-only, inactive, synthetic-corpus-governed evidence disconnected from product runtime. They must not become a generic router, marketplace, selector, retry/failover engine or runtime provider infrastructure. Historical fresh-connection evidence is not reinterpreted. No Merchant ACK source/runtime implementation is currently required.
- **Performance, localization and future diagnostics:** The complete required merchant-visible outcome retains the at-most-2,000-ms requirement with no external generative-network dependency. The Phase 9 provider p95 signal around 1,000 ms is non-binding research only, not a gate, SLO, admission criterion or production target. English/Amharic remain centralized in Phase 2; human Amharic status is `UNKNOWN` and `NEEDS_NATIVE_AMHARIC_REVIEW`. A separately authorized diagnostic may measure payload, DNS, connect, TLS, write, provider wait/TTFT, completion, download, parse/validation and total while keeping every result above 2,000 ms a product failure; no diagnostic ceiling is approved.
- **Geography, security and future gates:** Australian/Melbourne-path evidence must not be extrapolated to Addis Ababa. Future qualification requires representative AYO server geography, privacy-safe coarse network labels, African-region and eventual Ethio Telecom/Safaricom Ethiopia evidence, cold/warm and time-of-day analysis. Diagnostics remain synthetic and exclude credentials, authorization headers, personal IPs, raw provider responses, real product/user data, precise location and ungoverned request IDs. Any future provider work requires a proven unmet customer problem, measurable value, research/alternatives, sanitized design, CTO and Founder/CEO approval, synthetic execution authorization, policy/account evidence, applicable native-language review, explicit performance/geography criteria and separate evaluation/recommendation/admission/activation/production gates.
- **Risks and alternatives:** Risks are deterministic semantic/language drift, outstanding native Amharic review, misuse of research runners, revived generative UI churn and insufficient end-to-end measurement; mitigations are versioned exhaustive mappings, equivalence tests, fail-closed unknown states, native review, inactive composition and representative UX measurement. Synchronous generation, asynchronous Merchant ACK generation, provider caches, generic routing/failover and local/regional inference now are rejected as unreliable, unproven or unnecessary; deleting Phase 3–8 history is rejected because it would erase valid evidence. See `docs/AYO_INTELLIGENCE_PHASE_9_DETERMINISTIC_FIRST_ARCHITECTURE.md`.

### AP-072 — Immediate Standard cash-ride bounded certification repair

- **Date:** 2026-08-11
- **Status:** CTO approved the corrected bounded architecture and Founder/CEO authorized implementation only. Final certification, production accounting selection, mobile work, production activation, Phase 10 and merge remain separately gated.
- **Problem:** Booking preview pricing was not bound to canonical persisted Pricing acceptance, canonical Dispatch admitted any validated `ready_for_dispatch` request without accepted-pricing evidence, Post Trip lacked a concrete final-pricing bridge, cash confirmation overloaded physical evidence with accounting/settlement meaning and Support lacked one minimized authoritative ride projection.
- **Decision:** Preserve all existing domain ownership. Booking orchestrates Pricing estimate/acceptance and stores immutable references; Dispatch verifies and persists accepted pricing lineage before idempotency completion or handoff creation; a Pricing-owned adapter supplies final calculation to Post Trip. Separate cash evidence, accounting and reconciliation. A versioned cash-ride-specific policy produces balanced journal instructions for principal or agent models, with all synthetic fixtures visibly non-production and no production model selected. Add a read-time case/purpose/permission-bound Support projection with complete allowed/denied access audit.
- **Authority and failure:** Pricing alone determines fare. Post Trip owns collection evidence. Approved financial policy determines economic claims. The accounting-post boundary reloads canonical inputs and derives the complete instruction under trusted composition-owned production mode; callers cannot select economics or journal lines. Ledger alone posts immutable balanced journals. Reconciliation requires `cash.reconciliation.execute`, immutable obligation-bound evidence and an application-created clearing journal linked to the original accounting journal; unrelated journals cannot clear an obligation. Support is read-only and distinguishes accounting and reconciliation journal identities. Missing, stale, conflicting, cross-ride, cross-user, unbalanced or unauthorized evidence fails closed; replay may return only an exactly bound prior result.
- **Persistence and recovery:** Add reversible migration `20260811_0059` for Booking/Dispatch lineage and cash evidence/policy/accounting/reconciliation records. Existing domain transactions/outboxes remain separate; no distributed transaction or generic router is introduced. Restart recovery verifies exact persisted lineage and journal binding before continuation.
- **Boundary:** This is one PRE-PRODUCTION Immediate Standard cash-ride repair. No digital payment rail, payout, real Ethiopian tariff, commission/tax/remittance policy, production accounting model, generic Smart City financial framework, provider call, credential access, mobile implementation or final end-to-end certification is authorized. See `docs/AYO_IMMEDIATE_STANDARD_CASH_RIDE_CERTIFICATION_REPAIR_ARCHITECTURE.md`.
- **Known documentation debt:** AP-071 still describes its then-current candidate as awaiting merge although Phase 9 is now post-merge locked. That historical status wording is not rewritten by this bounded candidate and requires a separate governance-document reconciliation if leadership wants current-status annotations.

### AP-073 — Immediate Standard Rider/Driver public contract and weak-network recovery

- **Date:** 2026-08-11
- **Status:** CTO reviewed and approved; Founder/CEO implementation authorization recorded. PRE-PRODUCTION implementation candidate; Mobile MVP, production activation and merge remain separately gated.
- **Problem:** The certified Immediate Standard cash-ride authority chain already exposes bounded Booking, Dispatch, Active Ride and Post Trip routes, but a lost Booking-confirmation response had no authenticated authoritative read keyed by the rider's durable client intent. A later weak-network mobile client must not create a replacement ride, infer completion or access repositories after timeout or process restart.
- **Decision:** Reuse the existing public routes and domain applications. Add one rider-owned Booking confirmation recovery read keyed by `client_request_id`, backed by a join that binds both the canonical Ride Request and Booking confirmation to the authenticated rider. Return only confirmation, Ride Request, immutable FareEstimate/EstimateAcceptance/pricing-lineage references, public state and the next recovery action. Do not create a Ride Journey aggregate, generic projection/realtime/offline framework, mobile screen, provider or schema.
- **Alternatives:** Mutation-only replay remains supported but is insufficient as the sole authoritative recovery read. Client reconstruction is rejected because it moves authority to the device. A new aggregate/framework is rejected as duplicate authority and unnecessary cross-domain consistency risk. WebSockets/push are deferred because bounded polling solves the current recovery problem more simply.
- **Authority and failure:** Booking orchestrates; Pricing owns fare lineage; Dispatch owns offers/assignment; Active Ride owns lifecycle; Post Trip owns cash evidence/receipts; Ledger and accounting remain internal authorities. Missing, foreign or contradictory confirmation evidence fails closed. Complete pricing lineage is mandatory for the public response. Cash evidence never implies digital settlement or AYO ownership.
- **Risks and evidence:** Cross-rider lookup, response loss, duplicate tap, changed replay, stale version, polling load, partial historical lineage and misleading cash wording are mapped to authorization, idempotency, bounded query, fail-closed response and focused contract/PostgreSQL tests. Mobile device persistence, low-end device/network certification, Amharic review, support operations, legacy-route retirement and controlled activation remain separate gates.
- **Reference:** `docs/AYO_IMMEDIATE_STANDARD_PUBLIC_CONTRACT_WEAK_NETWORK_ARCHITECTURE.md`.

### AP-074 — Server-authoritative Immediate Standard booking consent metadata

- **Date:** 2026-08-13
- **Status:** Founder/CEO and CTO authorized bounded implementation; PRE-PRODUCTION review candidate. No public policy content or production activation is authorized.
- **Problem:** First confirmation accepted a client-supplied consent-policy version without proving it matched a policy declared and bound by the server at preview time.
- **Decision:** An explicitly composed immutable server registry owns version, document identity, content hash, effective interval, required acknowledgment, and immediate-mandatory rotation. Preview binds the complete metadata into canonical evidence and returns only bounded metadata. Confirmation validates acknowledgment and the exact still-current binding before side effects. Empty, duplicate, ambiguous, invalid, legacy, altered, unknown, or rotated evidence fails closed. Tests may inject deterministic synthetic manifests; runtime defaults to no active public policy.
- **Boundary:** No legal prose is invented or published. No public policy endpoint, schema, migration, mobile/provider capability, deployment, flag activation, or production policy is included. Legal and native-language review remain mandatory pre-activation gates. See `docs/AYO_BOOKING_CONSENT_AUTHORITY_ARCHITECTURE.md`.

### AP-075 — PRE-PRODUCTION Mobile Booking intent foundation

- **Date:** 2026-08-14
- **Status:** CTO implementation authorization was granted for the original bounded local product candidate. The feature branch was subsequently published as draft PR #86, and its exact PRE-PRODUCTION evidence was admitted by the automatic push and pull-request CI runs `31783323478` and `31783326846`. PR #86 was later merged by regular merge commit `3078642ba5f5f7fcd48a8bdf96d1a2cca7c286fd`; release and production activation remain separate gates.
- **Decision:** Add a presentation-neutral immutable mobile Booking preview intent, descriptor-safe exact request/response validation, authenticated place/preview transport, bounded one-intent memory store, deterministic preview engine and non-visual context. The provider binds its internally constructed engine to the same opaque continuity obtained from authenticated session composition; context cannot inject controller, continuity, state or store. The pure engine remains importable for bounded tests but is not authenticated authority by itself. Cryptographic UUID generation, exact generated-value validation, immediate-collision rejection and one normalized deeply frozen request preserve preview identity without unbounded identifier history. Flight ownership precedes transport execution, identical calls join one promise, conflicting calls fail closed and scope-owned finalization survives synchronous and asynchronous failures. Success transitions atomically from `previewing` to `confirmation_locked`.
- **Authority:** Backend Booking remains authoritative for routing, fare, consent, preview validity, confirmation and recovery. Production mobile source contains no confirmation/recovery endpoint, parser, state or capability. Identity replacement, logout, cancellation, unmount, retirement and clearing erase evidence and suppress late completion. The provider remains an unwired foundation.
- **Original product boundary:** No confirmation identifier or idempotency key, passive confirmation contract, outcome-unknown reconciliation, screen, durable storage, process-death recovery claim, policy prose, native-language legal approval, production registry, provider, payment, notification, analytics, dependency, lockfile, backend, schema, migration, deployment or activation change. The original product decision did not include CI-governance work. See `docs/AYO_MOBILE_BOOKING_INTENT_FOUNDATION_ARCHITECTURE.md`.
- **Subsequent publication and evidence governance:** The aggregate candidate includes workflow-only evidence-capture, correction, staged-verifier and final-admission commits; the original product increment itself introduced no workflow change. PR #86 was merged by regular merge commit `3078642ba5f5f7fcd48a8bdf96d1a2cca7c286fd`, with tree `fc1e624f414ee7dec1965c3b4f0de87300a523a0`, first parent `ee6650d7f6304e73c31aee8a1ab709cd3be1fbf0` and second parent `cac81836ef2afa6159b28552c5d93c2f376fab22`. The automatic post-merge Backend CI push run `31827753025`, attempt 1, completed successfully with the active Mobile Booking verifier returning `ADMITTED`; it uploaded zero Mobile Booking capture artifacts, and the deliberate capture stop was intentionally inapplicable. Local `main` was subsequently synchronized to the merge commit using fast-forward-only operations. Exact evidence admission and merge do not authorize release or production; the dependency-release block remains active and production remains prohibited.
- **Dependency and warning debt:** `package.json` and `package-lock.json` remain unchanged. The admitted PRE-PRODUCTION audit population is 13 moderate and 16 high findings across all dependencies (29 total), and 12 moderate and 16 high findings in the production-classified graph (28 total), with no critical, low or informational findings. No application-runtime high finding was demonstrated, while one high group remains runtime-reachability uncertain; no zero-runtime-vulnerability claim is made. Production release remains blocked pending fresh online advisory and runtime/trusted-build reachability review, dependency remediation requires separate authorization, and automated audit fixing remains prohibited. The governed Jest debt is 65 warnings: 57 historical React `act()` warnings and eight historical SafeArea deprecation warnings; focused Booking provider warnings are zero. This is deferred test-hygiene/framework debt, not ignored evidence.
- **Deferred boundaries:** Executable confirmation/recovery, durable encrypted storage and process-death recovery, approved consent presentation and policy prose, native-language/legal/product approval, UI/navigation integration, provider/payment/notification/analytics/dispatch activation, dependency remediation, deployment and production activation remain separately authorized future work.

### AP-076 — Proposed server-owned Booking consent document delivery contract

- **Date:** 2026-08-15
- **Status:** PROPOSED / PRE-PRODUCTION for CTO review and later Founder/CEO decision. No legal, product, native-language, accessibility or Founder approval is recorded; no implementation, policy content, endpoint, publication, deployment or production activation is authorized.
- **Problem and benefit:** The server currently binds policy version, document identity and a document-level hash to Booking preview evidence, but it publishes no human-readable policy document or rendition identity. Those opaque values cannot truthfully inform a rider. The proposed contract would later let an authenticated rider retrieve and verify exactly one reviewed, localized, preview-bound rendition while preventing substitution, stale acknowledgment and client-authored policy. Success requires exact integrity and ownership evidence, fail-closed rotation/withdrawal and later human comprehension/accessibility validation; a simpler identifiers-only presentation does not solve informed consent.
- **Decision:** Propose a separate authenticated, rider-owned, immutable document read rather than embedding content in route-preview responses. Future V1 and V2 contracts are disjoint exact schemas with a mandatory `consent_contract_version`; optional extension, structural inference, partial parsing, local upgrade and client-driven downgrade are prohibited. An authenticated V2 preview selects one exact approved locale/rendition and binds a closed Ethiopian Immediate Standard Booking scope, policy family/version, document and rendition identities, format, effective interval, domain-separated manifest/rendition hashes and acknowledgment requirement. Existing V1 `content_hash` semantics remain unchanged, and V1 cannot become presentation or acknowledgment evidence. The initial proposed content format is bounded restricted canonical UTF-8 passive JSON/plain text; arbitrary HTML, Markdown, scripts, remote resources, compression, runtime translation and silent fallback are prohibited.
- **Authority and operation:** Server Booking owns scope, registry selection, deterministic uniqueness, current status, rotation and withdrawal. Authenticated identity and stored preview ownership are mandatory; preview identifiers are lookup references, never authority, and mobile supplies no rider, policy, document or hash authority. Initial caching is continuity-isolated memory only; cached bytes cannot prove activation, acknowledgment or confirmation eligibility. No-grace immediate rotation is a safety proposal awaiting product/legal approval. Policy approval, emergency withdrawal, content activation, software deployment and production authorization are separated; withdrawal can only disable and can never activate content. Exact content changes invalidate downstream approvals, and rollback requires a new attributable activation decision. The proposed lifecycle requires legal, product, rendition-specific native-language/accessibility and CTO review followed by attributable Founder approval from Ibrahim Hambentu Shibiru before scheduling or activation; none has occurred.
- **Alternatives and risks:** Embedded preview content was rejected because it couples routing with legal-content transfer and impairs bounded caching; bundled app prose, automatic English fallback, runtime translation, arbitrary markup, public authoritative retrieval, offline acknowledgment and silent reinterpretation of the existing hash were rejected as stale, ambiguous or unsafe. Remaining decisions include Ethiopian electronic-consent and disclosure requirements, approved wording and languages, accessibility, privacy/retention, withdrawal operations, app-store applicability, security operations and production thresholds.
- **Boundary and sequence:** This decision adds documentation only. Legal requirements, wording, languages, accessibility, retention, withdrawal obligations, app-store applicability and production thresholds remain assigned to qualified Ethiopian counsel/regulators, Product, native-language/accessibility reviewers, Security/CTO and ultimately Ibrahim Hambentu Shibiru, Founder & CEO; no approval is completed. It introduces no policy prose, active registry, endpoint, schema, migration, backend/mobile code, test, durable storage, acknowledgment UI, confirmation/recovery, provider composition, dependency, workflow, deployment or production authority. After approval, ordering remains passive delivery implementation, mobile consent presentation, dependency reachability/remediation before normal UI composition, durable encrypted confirmation-intent/recovery architecture, executable confirmation/recovery, UI/navigation composition, then separately authorized deployment and production activation. See `docs/AYO_BOOKING_CONSENT_DOCUMENT_DELIVERY_CONTRACT_ARCHITECTURE.md`.

### AP-077 — Proposed governed Booking consent approval pack

- **Date:** 2026-08-15
- **Status:** PROPOSED / PRE-PRODUCTION for CTO review and later Founder/CEO decision. No external authority was contacted, no answer was submitted or received, and no legal, regulator, privacy, product, language, accessibility, Security/CTO or Founder approval is recorded.
- **Problem and benefit:** AP-076 identifies independent human and external decisions that must precede truthful consent-document implementation and activation, but an informal checklist could allow silence, verbal guidance, stale sources, scope substitution or template completion to be mistaken for approval. A governed approval pack gives each question a stable authority, written evidence, exact scope, status, expiry and stage gate while preserving auditability and privacy.
- **Decision:** Propose a separate approval-pack architecture and unfilled template. Electronic assent, transport/operator classification, rider disclosures, consumer protection, privacy, retention, cross-border data, languages, rendition review, accessibility, app-store obligations, rotation/withdrawal, complaints, Product, Security/CTO, Founder, deployment and production remain distinct domains. Written, attributable, in-scope evidence is mandatory; silence, meetings, submissions, AI output and successful CI cannot imply approval. Lifecycle state is a closed eleven-state transition record beginning at `NOT_STARTED`, while `NOT_APPROVED` is a separate approval-result default and never a lifecycle state. Every decision binds a fingerprinted complete condition set: unconditional decisions use an explicit governed zero-condition set, and conditional decisions require an exactly reconciled ordered inventory whose every condition is current and satisfied. Exact versioned transitions, condition-satisfaction evidence, cryptographic evidence custody, role separation, rendition/UI binding and derived gate aggregation prevent reuse or widening. Unknown, expired, superseded, conflicting, incomplete or red-line-conflicting evidence fails closed.
- **Authority and red lines:** Legal, transport/regulatory, Privacy/Data Steward, Product, native-language, accessibility, Security/CTO, Founder/CEO, deployment and independent-audit roles remain separated. Founder approval is attributable only when actually performed by Ibrahim Hambentu Shibiru, Founder & CEO after prerequisites. Permanent RED boundaries prohibit transferring AYO consent-record ownership or policy IP, unilateral vendor policy control, a vendor-owned authoritative registry, surrender of signing keys/evidence/audit history, lock-in that blocks export or audit, unilateral third-party terms changes and bypass of Legal, CTO, independent-audit, Founder or production gates.
- **Boundary:** This decision and template are governance documentation only. Every approval defaults to `NOT_APPROVED`, unresolved answers to `UNRESOLVED`, and production to `PROHIBITED`. Implementation remains blocked pending written decisions for assent form, instrument separation, transport classification, privacy/data flow, required languages, accessibility criteria and rotation/withdrawal. Activation additionally requires approved prose and renditions, all human/external approvals, operational readiness, deployment authorization and separate production authorization. No policy content, endpoint, schema, migration, product code, test, UI, persistence, dependency, workflow, deployment or production change is authorized. See `docs/AYO_BOOKING_CONSENT_APPROVAL_PACK_ARCHITECTURE.md` and `docs/AYO_BOOKING_CONSENT_APPROVAL_PACK_TEMPLATE.md`.

### Governance bootstrap — Central AP decision-ID reservation and collision repair

- **Date:** 2026-08-26
- **Approval:** Founder approved; CTO architecture review approved. This bootstrap record is intentionally unnumbered because it establishes the serialization authority needed to make future permanent AP allocation reliable. It does not allocate AP-099 or any other new AP identity.
- **Problem:** Repository-wide inspection established 66 attributable decision-title allocations across 51 AP identifiers and 13 identifiers with substantively different titles. Independent histories allocated permanent AP identities without one serialization authority. Historical commits remain truthful evidence and must not be rewritten merely to make numbering appear clean.
- **Decision:** `docs/AYO_DECISION_ID_REGISTRY.json` is the central Git-native AP reservation authority when this registry tree is incorporated into authoritative `main`. Permanent AP reservations must reach `main` before unrelated feature work relies upon them. The standard-library validator rejects malformed, duplicated, mismatched, unregistered, silently reused or post-cutover collision states while preserving explicitly bootstrapped legacy collisions as historical composite identities: introducing commit SHA + original AP ID + exact title.
- **Historical bootstrap:** Uncontested main decisions, visible unmerged allocations, unexplained historical gaps and every mechanically established collision are recorded without claiming that they were centrally reserved before this cutover. Unexplained low-number gaps remain blocked from reuse. No collision winner or replacement identity is selected by this record.
- **Historical identity boundary:** Off-main AP allocations remain attributable through their introducing commits and exact titles. Recording them in the registry neither imports their substantive architecture into main nor makes any unresolved collision repository-wide authority. Permanent repair remains separately gated.
- **Cutover:** This tree is `READY_FOR_MAIN_ACTIVATION`; serialization authority becomes active only when the exact registry is incorporated into authoritative `main`. After activation, a new permanent AP decision must match a prior registry reservation on `main`; a feature branch may not manufacture both an unlanded reservation and an unrelated permanent allocation as if serialization had occurred. Historical collision-repair identities may not be expanded, rewritten or silently reused.
- **Boundary:** No Constitution, product behavior, production configuration, historical commit or decision substance changes. No AP identifier is allocated, renumbered, resolved, superseded or selected as a collision winner. No separate institutional architecture is imported by this main-based governance cutover.

### Operational security correction — deterministic pip audit-toolchain remediation

- **Date:** 2026-08-26
- **Approval:** Founder approved; CTO architecture and implementation approval granted. This operational security correction is intentionally unnumbered and allocates no AP identity.
- **Problem:** The locked development environment resolved `pip==26.1.2`, which `pip-audit==2.10.1` identified as affected by `PYSEC-2026-3721` / `CVE-2026-13346`. The finding concerns CI/development tooling and does not establish an AYO application-runtime vulnerability.
- **Decision:** Constrain the development-tooling environment to `pip>=26.2,<27`, regenerate only the necessary lock resolution, and admit the exact remediation through a mission-specific fail-closed CI evidence contract. The dependency audit remains active and no advisory is ignored or suppressed.
- **Boundary:** No application, backend, mobile, migration, production dependency, runtime behavior, AP identity, historical collision, Phase 5 material or production authority changes. The correction does not activate the pending AP registry or modify PR #90.

### Governance enablement — append-only AP identity and collision reconciliation lifecycle

- **Date:** 2026-08-27
- **Approval:** Founder approved; CTO architecture and implementation review approved. This governance-enablement record is intentionally unnumbered. It reserves and allocates no AP identity and creates no collision reconciliation.
- **Problem:** The active bootstrap registry preserves historical collisions, but its legacy allocation rows do not provide a safe append-only forward reservation/allocation lifecycle or an attributable reconciliation event. Mutating a frozen historical `reconciliation_status` would fail open by erasing the distinction between historical evidence and later repair authority.
- **Decision:** Preserve every bootstrap allocation as immutable human-readable evidence and derive a deterministic historical composite commitment from introducing commit, AP ID and exact original title separated by NUL bytes. Schema v2 adds empty append-only `forward_identity_events` and `collision_reconciliations` collections. Future event and reconciliation IDs are SHA-256 commitments over canonical payloads with their own IDs omitted, so provenance is non-recursive; Git history proves first introduction and eventual authoritative-main inclusion. A valid later reconciliation refers to one unchanged historical composite and one already-main-authoritative successor allocation. Effective status becomes `RESOLVED` only when exactly one valid reconciliation exists; otherwise the stored bootstrap state remains effective.
- **Forward lifecycle:** A future `RESERVED` event holds an exact identity on authoritative main but grants no allocation, decision-log heading or implementation authority. A later `ALLOCATED` event must reference an exact matching reservation already present on baseline authoritative main; reservation and allocation cannot be manufactured together. `SUPERSEDED` remains an attributable later event, never a rewrite. Historical introducing commits are validated as actual Git commit objects where repository context permits.
- **Exact future authority boundary:** A later separately authorized reservation lane may recognize only AP-099, titled “AYO Founder Institutional Discovery Corpus Phase 5 Preservation Foundation,” for the replacement forward identity historically colliding at AP-079, with no dual-corpus amendment, corpus receipt or ingestion authority; and AP-100, titled “AYO Founder Institutional Discovery Phase 5 Dual-Corpus and Source-Preservation Amendment,” for future raw-source custody, source-unit inventory, canonical numbered-corpus provenance, separate Discovery Intelligence preservation, extraction ledger, coverage semantics and open-count validation. Reservation alone grants no implementation or ingestion authority.
- **Boundary:** This record creates no `RESERVED`, `ALLOCATED`, `SUPERSEDED` or reconciliation instance; adds no AP-099 or AP-100 heading; allocates no identity; does not resolve AP-079 or any of the 13 historical collision groups; and grants no Phase 5 source receipt, hashing, ingestion, principle, shard, Discovery Intelligence or branch-mutation authority.

### Governance correction — authoritative historical AP provenance manifest

- **Date:** 2026-08-27
- **Approval:** Founder approved Architecture C and this bounded correction; CTO reviewed and approved the architecture and implementation mission. This record is intentionally unnumbered and reserves or allocates no AP identity.
- **Problem:** CI demonstrated that arbitrary historical Git-object availability is not portable: two frozen pre-cutover introducing commits remain in retained local object evidence but are not reachable from authoritative main or advertised GitHub refs. Fetch depth cannot restore an unadvertised object. Treating checkout availability as sole authority would reject truthful bootstrap history, while syntax-only SHA validation would accept fabrication.
- **Decision:** `docs/AYO_AP_HISTORICAL_PROVENANCE.json` is the primary and sole authority for frozen bootstrap provenance. It uniformly binds all 34 introducing commits to exact trees, ordered parents, subjects, lineages and historical AP/title composites with deterministic non-recursive entry IDs. Live Git objects and any separately approved durable archival refs are corroborating evidence only and cannot override the main-resident manifest. The two approved pre-cutover manifest-only exceptions are `20b81a0e4f4e06060525a33f3a5f1c767f4b88f7` and `32716a1c834ca24e3237966c53532886afa558fe`; their retained-object metadata was captured without publishing either historical branch. A missing live object is accepted only for those exact approved exceptions, while any available object must match the manifest exactly. Post-cutover lifecycle and governance events may never use manifest-only provenance.
- **Security evidence:** CI governance now binds the manifest and exact two-commit topology. Focused Bandit JSON evidence governs the registry validator's reviewed low-severity `B404`, `B607` and `B603` subprocess inventory, rejects medium/high or new findings and forbids suppression. Synthetic high-entropy test constants are constructed from deterministic fragments so runtime evidence is unchanged and the governed candidate-only secret set remains empty.
- **Boundary:** No archival ref is created. The Phase 5 branch remains unpublished and untouched, and no corpus content is inspected or imported. This correction creates no reservation, allocation, supersession or reconciliation, leaves AP-099 and AP-100 absent, leaves AP-079 and all 13 historical collision groups unresolved, and grants no Phase 5 receipt, ingestion or Discovery Intelligence authority.
