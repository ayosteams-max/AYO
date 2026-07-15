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
