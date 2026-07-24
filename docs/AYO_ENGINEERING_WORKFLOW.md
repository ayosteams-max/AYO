# AYO Engineering Workflow

## Support-provider gate

AI, speech, telephony, messaging, email and external ticketing integrations require a separate evidence-based comparison and CEO/CTO approval. Measure queue outcomes, latency, escalation quality, language accuracy, privacy failures and cost before adding Redis, brokers, vector databases or provider-specific infrastructure.

Version: 1.0
Adopted: 2026-07-14
Status: mandatory for every mission
Authority: subordinate only to `AYO_CONSTITUTION.md` and approved CEO decisions following required CTO review

## 1. Purpose

This workflow turns AYO's Constitution into an approval-gated engineering process. Every mission follows every step in order. A later step cannot be used to bypass an incomplete earlier step.

Codex is responsible for research support, analysis, proposals, implementation, tests, verification and documentation within approved scope. The CTO reviews technical work and engineering readiness. The CEO gives final approval for major business, product and architecture decisions.

## 2. Permanent optimization priorities

Every recommendation and implementation must optimize across:

1. Customer experience.
2. Trust and safety.
3. Verified Ethiopian legal, regulatory and operational requirements.
4. Global engineering standards.
5. Long-term scalability toward 10 million users.
6. Simplicity over unnecessary complexity.
7. Low total operating cost without weakening reliability, safety, security or driver outcomes.
8. Production readiness.

Tradeoffs must be stated. A recommendation must not claim to maximize conflicting priorities without evidence.

## 3. Mandatory mission process

### Step 1 — Research first

Research the mission before proposing implementation. Cover, as applicable:

- The real customer, driver or operations problem and current user journey.
- Current repository behavior, constraints, dependencies and known defects.
- Relevant security, privacy, safety and fraud threats.
- Scalability, reliability, failure recovery and operating-cost implications.
- Ethiopian legal, regulatory, payment, transport, labour, tax, privacy, language, connectivity, device and field-operation requirements.
- Global engineering standards and primary technical guidance.
- AI need, data, evaluation, fairness, explainability, cost and deterministic fallback.

For every major product, architecture, infrastructure, pricing, safety, fraud, payments, maps, dispatch, wallet or AI decision, the research brief must also:

1. Define the exact problem.
2. Examine how leading ride-hailing and mobility companies address the same problem without assuming their approach is correct for AYO.
3. Examine Ethiopia-specific regulation, payments, connectivity, devices, maps, driver behaviour and operating reality.
4. Separate verified facts from assumptions, proposals and decisions requiring CEO or CTO approval.

Use authoritative primary sources for technical and regulatory claims where available. Record source, date accessed, jurisdiction/version and unresolved uncertainty. Do not treat general internet commentary as legal advice. Ethiopian requirements must be verified by qualified local counsel, regulators, licensed providers or accountable operations specialists before launch.

**Required output:** Research brief containing the problem, beneficiaries, evidence, success measures, constraints, sources, open questions and legal/operational verification items.

**Gate:** Research must be complete enough to compare credible options. If critical evidence is unavailable, stop and request direction.

### Step 2 — Present findings and recommendations

Summarize evidence without presenting proposals as approved facts. For every credible solution, compare:

| Criterion | Required analysis |
|---|---|
| Pros | Benefits and problems solved |
| Cons | Limitations and tradeoffs |
| Cost | Build, provider, infrastructure and ongoing operations |
| Scalability | Capacity path, bottlenecks and independent module scaling |
| Maintenance | Complexity, skills, upgrades, observability and support burden |
| Customer impact | Friction, reliability, accessibility, weak-network and trust effects |
| Security/safety | Threats, controls and residual risk |
| Ethiopian fit | Regulation, providers, cash, devices, language and operations |

The comparison must include at least two credible approaches when meaningful and must evaluate customer experience, driver impact, safety/fraud risk, legal/privacy risk, reliability, cost, operational complexity, scalability, vendor lock-in and maintenance burden.

State the recommended option, why it best fits the Constitution, what simpler solution was considered, what is deliberately deferred and how success will be measured.

Never copy a competitor feature blindly and never select a tool because it is popular or fashionable. Recommend the simplest reliable solution that solves the proven problem. Record the evidence or measurable threshold that would cause the recommendation to be revisited.

**Required output:** Findings and options report with a recommendation, alternatives matrix, risks, estimated cost class and explicit decisions requested.

**Gate:** No architecture design or implementation begins from an unreviewed recommendation.

### Step 3 — Wait for CEO and CTO approval

The CTO reviews technical correctness, architecture direction, security, scalability, quality, feasibility, cost and engineering risk. The CEO reviews vision, customer/business outcome, product policy, operating implications and final major decision.

Record:

- CTO review status, conditions and date.
- CEO approval status, conditions and date.
- Approved option and scope.
- Explicit exclusions and deferred items.
- Any approval expiry or evidence still required before launch.

**Required output:** Decision-log entry or linked approval record.

**Gate:** Without required approval, stop. Silence, ambiguity or permission to explore is not approval to implement.

### Step 4 — Design the architecture

Design only the approved scope. The design must include:

- Current state and safe migration path without unexplained rewrites.
- Module responsibilities, contracts and data ownership.
- Data model, state transitions, idempotency and consistency boundaries.
- APIs/events, error handling and compatibility strategy.
- Security/privacy controls and threat boundaries.
- Capacity assumptions, bottlenecks and path to 10 million users.
- Failure modes, retries, backpressure, degraded operation and disaster recovery.
- Observability, rollout, rollback and provider/AI fallbacks.
- Ethiopian connectivity/device/operating constraints.
- Cost drivers and means to bound them.

**Required output:** Reviewed technical design linked from the decision log.

**Gate:** CTO architecture approval is required before implementation. Material architecture changes return to Steps 2–3 and require CEO approval where major product/business scope changes.

### Step 5 — Identify risks and edge cases

Create a risk and edge-case register before coding. Cover:

- Authorization, abuse, fraud, replay and insider threats.
- Duplicate, delayed, stale and out-of-order commands.
- Concurrency, partial failure, timeout and retry behavior.
- Weak/no connectivity, low-end devices, clock drift and battery constraints.
- Money rounding, idempotency, reversal, reconciliation and provider mismatch.
- Location staleness/spoofing, map/provider outage and unsafe pickup.
- Data privacy, retention, deletion and audit access.
- Accessibility, localization and confusing failure states.
- Capacity limits, hot partitions, unbounded growth and third-party cost spikes.
- AI error, bias, drift, prompt/input abuse, unavailable model and human fallback.

For each risk, record likelihood, impact, mitigation, residual risk, owner and verification method. Escalate unresolved critical/high risks.

**Required output:** Risk/edge-case register and test mapping.

**Gate:** No production implementation while an unaccepted critical risk remains.

### Step 6 — Build only production-quality code

Implementation must be small, reviewable, compatible and limited to the approved design.

- Preserve working behavior through tests and migration adapters.
- Use explicit types, bounded operations, secure defaults and clear module contracts.
- Avoid process-local authoritative state, unaudited money, hidden policy and premature complexity.
- Include observability and operational failure behavior with the implementation.
- Explain any working-code replacement before editing: why it is necessary, alternatives, migration, compatibility and rollback.
- Do not start later roadmap missions early.
- Do not add unnecessary dependencies; document the need, alternatives, security/supply-chain risk, maintenance burden and removal path for every new dependency.
- Do not create microservices without measured justification and required approval.
- Do not expose production secrets, personal data, precise sensitive location, identity documents or payment credentials to AI tools.
- Do not modify approved production architecture, pricing policy, safety policy or legal assumptions without renewed CTO review and CEO approval.
- If a better tool or faster reliable workflow is available, surface it with benefits, risks and constraints before continuing manually.

**Required output:** Reviewable implementation with traceability to design and risks.

**Gate:** Scope expansion stops work and returns to approval. Codex does not invent policy to unblock implementation.

### Step 7 — Write automated tests

Tests are part of the implementation, not optional follow-up work. Include as applicable:

- Unit tests for domain rules and state transitions.
- Integration tests for persistence, providers and transactions.
- Contract/API tests and backward compatibility.
- Authorization and security regression tests.
- Idempotency, concurrency and financial invariant tests.
- Failure, timeout, retry and degraded-network tests.
- Property-based tests for high-risk state/financial logic.
- End-to-end tests for the approved customer journey.

Use synthetic data. Tests must be deterministic, isolated and meaningful; coverage percentage alone is not acceptance.

**Required output:** Automated suite and requirements-to-test evidence.

**Gate:** Required tests must pass before readiness verification.

### Step 8 — Verify security and performance

Perform risk-proportionate verification:

- Threat-model/control review and authorization testing.
- Secret/dependency/static analysis and sensitive-data/log review.
- Load, stress, soak or targeted benchmark against documented capacity assumptions.
- Query/index, memory, latency, queue and provider-cost analysis.
- Failure injection, recovery, backup/restore or rollback checks where applicable.
- AI quality, safety, latency, cost, drift and fallback evaluation where applicable.

Record environment, dataset/workload, thresholds, results and limitations. Never claim production scale from an unrealistic local test.

**Required output:** Security and performance verification report with residual risks.

**Gate:** Failed acceptance thresholds or unresolved critical/high findings block completion unless formally accepted by the appropriate CTO/CEO authority consistent with the Constitution and law.

### Step 9 — Document every important decision

Update the decision log, architecture, API/runbooks, migrations, threat model, operational procedures and roadmap to match reality. Record:

- Problem, beneficiary and success measure.
- Decision and reasons.
- Alternatives, including the simpler option.
- Risks, mitigations and residual risk.
- CTO review and CEO approval.
- Implementation and verification evidence.
- Superseded decisions and follow-up obligations.

**Required output:** Complete traceability from problem through approval, code, tests and operations.

**Gate:** Undocumented material decisions mean the mission is incomplete.

### Step 10 — Stop and request approval before the next mission

Provide a mission completion report containing:

- Customer/problem outcome delivered.
- Approved scope completed and exclusions preserved.
- Files/systems changed.
- Test, security and performance results.
- Known limitations, residual risks and Ethiopian verification still required.
- Operational/rollback readiness.
- Recommended next mission with its problem statement only.

Then stop. Do not research or implement the next mission until explicitly authorized. If research for the next mission is separately authorized, stop again after Steps 1–2 for CTO review and CEO approval.

## 4. Mandatory milestone completion report

After every milestone—not only at mission completion—report:

1. What changed.
2. Tests run and their results.
3. Security checks performed and their results.
4. Risks remaining.
5. Technical debt introduced, retained or resolved.
6. The next recommended step without starting it.

Stop at the applicable approval gate after delivering the report.

## 5. Uncertainty rule

Never guess when uncertainty could change product policy, architecture, security, safety, privacy, financial treatment, regulatory compliance, customer experience or material cost.

State:

1. What is known and its evidence.
2. What is uncertain.
3. Why the uncertainty matters.
4. Available options and consequences.
5. The specific CEO, CTO, legal or operations decision needed.

Continue only with reversible, approved work that does not depend on the unresolved answer. Otherwise stop and ask.

## 6. Mission evidence checklist

| Step | Required evidence | Complete |
|---|---|---|
| 1 | Research brief and sources | No |
| 2 | Findings, options matrix and recommendation | No |
| 3 | CTO review and CEO approval record | No |
| 4 | Approved architecture/design | No |
| 5 | Risk and edge-case register | No |
| 6 | Production-quality implementation | No |
| 7 | Automated test evidence | No |
| 8 | Security/performance verification | No |
| 9 | Decision and operational documentation | No |
| 10 | Completion report and next-mission approval request | No |

## Authentication change gate

Every authentication-related mission or change must explicitly review device trust,
multi-device sessions, refresh rotation/replay, hijacking, suspicious login,
one-device/all-device/admin revocation, remember-me, bounded clock skew, high-risk
step-up, anti-enumeration failures, audit taxonomy, privacy-safe IP/device signals
and future versioned risk-scoring compatibility. Tests must cover applicable
lifecycles, concurrency, rollback, outage and prohibited-data behavior. A missing
answer is an unresolved design decision, not permission to choose a shortcut.

Copy this checklist into each mission plan and link every artifact. A mission cannot be marked complete with a required row missing.

## Governance reconciliation checkpoint — 2026-07-23

The documentation-only Ride Request readiness review originally reached Step 3 and stopped
because exact approvals were absent. Separate milestone approvals and Canonical Mobility
Ownership approval were subsequently recorded on 2026-07-23. Governance readiness is now
closed and ready for a separately authorized Ride Request implementation mission. This
checkpoint records workflow application only; it does not alter the permanent process,
authorize implementation, or approve production activation. See
`GOVERNANCE_RECONCILIATION_RIDE_REQUEST_READINESS_2026-07-23.md`.

## Ride Request and Service Area checkpoint — 2026-07-23

Ride Request Increment 1 completed Steps 1–10 and received milestone-specific CTO and
Founder approval on 2026-07-23 for PRE-PRODUCTION ONLY. Its former awaiting-review state
is historical and the gate is closed.

The Service Area & Ride Product Availability mission is currently documentation and
architecture only:

| Step | State |
|---|---|
| 1 — Research | Complete; repository and primary PostgreSQL/PostGIS evidence recorded |
| 2 — Findings/recommendation | Complete; R1 supporting domain and PostGIS recommended |
| 3 — CTO/Founder architecture approval | Pending |
| 4 — Architecture | Proposed; not approved |
| 5 — Risks/edge cases | Complete at architecture level |
| 6–9 — Implementation through operations | Not authorized/not started |
| 10 — Stop | Satisfied; awaiting CTO and Founder review |

Architecture approval will not itself grant implementation authority.

### Service Area approval closure

The architecture and Increment 1 implementation authority were subsequently approved on
2026-07-23 by CTO Architecture Review, Chief Technology Officer, and Ibrahim Hambentu
Shibiru, Founder & CEO.

| Step | Current state |
|---|---|
| 1 — Research | Complete |
| 2 — Findings/recommendation | Complete |
| 3 — CTO/Founder architecture approval | APPROVED |
| 4 — Architecture | APPROVED |
| 5 — Risks/edge cases | Complete for implementation entry |
| 6–9 — Implementation through operations | Authorized for Increment 1 PRE-PRODUCTION only; not yet completed |
| 10 — Stop | Required after Increment 1 technical gate |

Production activation, later increments and real territory activation remain separate
future gates. PostGIS dependency/environment certification must pass before dependent
domain implementation.

### Service Area Increment 1 completion checkpoint

| Step | Current state |
|---|---|
| 1–5 — evidence, recommendation, approval, architecture and risks | Complete |
| 6 — dependency certification | Complete for PostgreSQL 17/PostGIS PRE-PRODUCTION |
| 7 — implementation | Complete for authorized Increment 1 |
| 8 — verification | Focused, migration and quality evidence recorded in the CTO gate report |
| 9 — documentation/operations | Complete for PRE-PRODUCTION review |
| 10 — stop | Satisfied; awaiting CTO and Founder & CEO review |

This checkpoint grants no production activation and no later-increment authority.

### Request Access & Interaction Provenance architecture checkpoint

| Step | Current state |
|---|---|
| 1 — Research/repository authority review | Complete |
| 2 — Findings/recommendation | Complete; shared supporting capability plus immutable provenance recommended |
| 3 — CTO/Founder architecture approval | PENDING |
| 4 — Architecture | PROPOSED; not approved |
| 5 — Risks/edge cases | Complete for architecture review |
| 6–9 — Implementation through operations | NOT AUTHORIZED / not started |
| 10 — Stop | Satisfied; awaiting CTO and Founder & CEO architecture review |

This checkpoint creates no successor implementation authority.

### Request Access & Interaction Provenance architecture approval closure

Architecture governance was approved on 2026-07-23 by OpenAI ChatGPT, Project CTO
(Technical Oversight), and Ibrahim Hambentu Shibiru, Founder & CEO.

| Step | Current state |
|---|---|
| 1 — Research/repository authority review | Complete |
| 2 — Findings/recommendation | Complete |
| 3 — CTO/Founder architecture approval | APPROVED FOR PRE-PRODUCTION GOVERNANCE ONLY |
| 4 — Architecture and ADR | APPROVED |
| 5 — Risks, privacy, metadata and threat model | APPROVED for governance |
| 6–9 — Implementation through operations | NOT AUTHORIZED / not started |
| 10 — Stop | Satisfied after governance closure |

The next implementation increment may be proposed as **Request Access & Interaction
Provenance Increment 1**, but work cannot begin until a separate implementation
authorization is recorded. Production activation remains separately prohibited.

### Request Access & Interaction Provenance Increment 1 authorization closure

Milestone-specific implementation authority was recorded on 2026-07-23 by OpenAI
ChatGPT, Project CTO (Technical Oversight), and Ibrahim Hambentu Shibiru, Founder & CEO.

| Step | Current state |
|---|---|
| 1-5 - evidence, recommendation, approval, architecture and risks | Complete; approved ADR remains authoritative |
| 6-9 - implementation through operations | IMPLEMENTATION AUTHORIZED for Increment 1 PRE-PRODUCTION ONLY; not started by this closure |
| 10 - stop | Required after the Increment 1 technical gate |

Production activation, real channel runtimes, user interfaces and later increments
remain unauthorized. This closure changes governance state only and preserves the
earlier not-authorized checkpoint as historical chronology.

### Request Access & Interaction Provenance Increment 1 completion checkpoint

| Step | Current state |
|---|---|
| 1-5 - evidence, recommendation, approval, architecture and risks | Complete |
| 6 - dependency and migration preparation | Complete for the PRE-PRODUCTION foundation |
| 7 - implementation | Complete for authorized Increment 1 |
| 8 - verification | INCOMPLETE; PostgreSQL integration, migration and backup/restore require configured test database |
| 9 - documentation | Complete for technical review |
| 10 - stop | Satisfied at the blocked certification gate |

No production activation, real adapter runtime, business-domain integration or later
increment is authorized by this checkpoint.

### Enterprise Experience & Release Governance architecture checkpoint

| Step | Current state |
|---|---|
| 1 - Research/repository authority review | Complete |
| 2 - Findings/recommendation | Complete; existing-owner profile recommended |
| 3 - CTO/Founder architecture approval | PENDING |
| 4 - Architecture and ADR | PROPOSED |
| 5 - Risks/edge cases | Complete for architecture review |
| 6-9 - Implementation through operations | NOT AUTHORIZED / not started |
| 10 - stop | Satisfied; awaiting CTO and Founder & CEO architecture review |

The package rejects a new monolithic capability and creates no runtime, schema,
migration, API, scheduler, feature flag, publication, targeting, channel or production
authority.
### Enterprise Authority Routing architecture refinement checkpoint

| Step | Current state |
|---|---|
| 1 — Repository/evidence review | Complete |
| 2 — Findings and recommendation | Complete; refine existing canonical owner |
| 3 — CTO/Founder architecture approval | PENDING |
| 4 — Architecture and ADR | PROPOSED |
| 5 — Risks and boundaries | Complete for architecture review |
| 6–9 — Implementation through operations | NOT AUTHORIZED / not started |
| 10 — Stop | Satisfied; awaiting CTO and Founder & CEO review |

This checkpoint creates no workflow, permissions, schema, migration, runtime or
production authority.
### Enterprise Initiative Orchestration Profile architecture checkpoint

| Step | Current state |
|---|---|
| 1 — Repository and external evidence review | Complete |
| 2 — Findings and recommendation | Complete; federated profile, no new owner |
| 3 — CTO/Founder architecture approval | PENDING |
| 4 — Architecture and ADR | PROPOSED |
| 5 — Risks and boundaries | Complete for architecture review |
| 6–9 — Implementation through operations | NOT AUTHORIZED / not started |
| 10 — Stop | Satisfied; awaiting CTO and Founder & CEO review |

No runtime, agent, workflow, schema, migration, product launch or production authority
is created by this checkpoint.
### Synthetic AYO Eat Addis initiative exercise checkpoint

| Step | Current state |
|---|---|
| architecture inventory | Complete |
| paper lifecycle simulation | Complete |
| ownership/approval/evidence validation | PASS |
| genuine gap analysis | Complete |
| implementation or production | NOT AUTHORIZED / not started |
| stop | Satisfied |

The exercise proves coordination structure, not launch readiness. P2 architecture,
domain evidence and all implementation/production gates remain open.
### P2 AYO Eat architecture and launch-admission checkpoint

| Step | Current state |
|---|---|
| 1 — Repository/external evidence review | Complete |
| 2 — Recommendation | Complete; federated P2, one Commerce Order |
| 3 — CTO/Founder architecture approval | PENDING |
| 4 — Architecture and ADR | PROPOSED |
| 5 — Launch risks/checklist | Complete for architecture review |
| 6–9 — Implementation through operations | NOT AUTHORIZED / not started |
| 10 — Stop | Satisfied; awaiting CTO and Founder & CEO review |

No participant activation, Addis operating area, implementation or production authority
is created.
### P2 AYO Eat architecture approval and Increment 1 authorization closure

Approval recorded on 2026-07-23 by OpenAI ChatGPT, Project CTO (Technical Oversight),
and Ibrahim Hambentu Shibiru, Founder & CEO.

| Step | Current state |
|---|---|
| 1–5 — evidence, architecture, risks and approvals | Complete; APPROVED |
| 6–9 — Increment 1 implementation through verification | IMPLEMENTATION AUTHORIZED (PRE-PRODUCTION ONLY); not started by this closure |
| 10 — stop | Required after Increment 1 technical gate |

Authority is limited to Product Availability and Canonical Commerce Order Composition
Foundation. Production and future increments remain unauthorized.

### P2 AYO Eat Increment 1 technical checkpoint

| Step | Current state |
|---|---|
| 1–5 — authority and frozen architecture | Complete |
| 6 — implementation | Complete in authorized PRE-PRODUCTION scope |
| 7 — focused verification | Complete; PostgreSQL certification pending configured PostgreSQL 17 URL |
| 8 — security and operational review | Complete for technical gate |
| 9 — CTO/Founder milestone review | PENDING |
| 10 — stop | Satisfied; Increment 2 and production not started |

The implementation record and CTO gate report preserve the exact exclusions. Technical
completion does not activate an area, participant, API, release or production system.

### P2 AYO Eat Increment 2 merchant decision architecture checkpoint

| Step | Current state |
|---|---|
| 1 — repository and primary-source review | Complete |
| 2 — findings and recommendation | Complete; evolve Merchant Order Management |
| 3 — CTO and Founder architecture approval | PENDING |
| 4 — architecture and ADR | PROPOSED |
| 5 — risks and edge cases | Documented |
| 6–9 — implementation through operations | NOT AUTHORIZED / not started |
| 10 — stop | Satisfied; awaiting architecture review |

### Courier Dispatch architecture and launch-admission checkpoint

| Step | Current state |
|---|---|
| 1 — repository and primary-source review | Complete |
| 2 — findings and recommendation | Complete; refine existing canonical owner |
| 3 — CTO and Founder architecture approval | PENDING |
| 4 — architecture and ADR | PROPOSED |
| 5 — risks, edge cases and launch admission | Documented |
| 6–9 — implementation through production operations | NOT AUTHORIZED / not started |
| 10 — stop | Satisfied; awaiting architecture review |

No runtime, schema, migration, API, test or production authority is created.

### Courier Dispatch architecture approval and Increment 1 authorization closure

Approval recorded on 2026-07-23 by OpenAI ChatGPT, Project CTO (Technical Oversight),
and Ibrahim Hambentu Shibiru, Founder & CEO.

| Step | Current state |
|---|---|
| 1–5 — research, architecture, risks and approvals | Complete; APPROVED |
| 6–9 — Increment 1 implementation through verification | IMPLEMENTATION AUTHORIZED — PRE-PRODUCTION ONLY; not started by this closure |
| 10 — stop | Satisfied for governance mission |

Production and successor increments remain unauthorized. Implementation must remain
inside the dedicated Increment 1 authorization record.

### Courier Dispatch Increment 1 technical checkpoint

| Step | Current state |
|---|---|
| 1–5 — approved architecture and risks | Complete |
| 6 — bounded PRE-PRODUCTION implementation | Complete |
| 7 — focused verification | Complete; full suite retains one unrelated fixture failure |
| 8 — security/dependency review | Complete locally; PostgreSQL certification pending |
| 9 — CTO/Founder implementation review | PENDING |
| 10 — stop | Satisfied; Increment 2 and production not started |

No new Merchant Acceptance capability is admitted. The package preserves existing
Increment 20 authority and proposes the smallest additive successor only.

### P2 AYO Eat Increment 2 architecture approval closure

Approval was recorded on 2026-07-23 by OpenAI ChatGPT, Project CTO (Technical
Oversight), and Ibrahim Hambentu Shibiru, Founder & CEO.

| Step | Current state |
|---|---|
| 1–5 — evidence, architecture, risks and approvals | Complete; APPROVED |
| 6–9 — Increment 2 implementation through verification | IMPLEMENTATION AUTHORIZED (PRE-PRODUCTION ONLY); not started by this closure |
| 10 — stop | Satisfied for governance mission |

Production and future increments remain unauthorized. Implementation must stop at the
Increment 2 technical gate.

### P2 AYO Eat Increment 2 technical checkpoint

| Step | Current state |
|---|---|
| 1–5 — approved architecture and risks | Complete |
| 6 — bounded PRE-PRODUCTION implementation | Complete |
| 7 — focused verification | Complete; live PostgreSQL certification pending configured URL |
| 8 — security and dependency review | Complete for local technical gate |
| 9 — CTO/Founder implementation review | PENDING |
| 10 — stop | Satisfied; Increment 3 and production not started |

### P2 AYO Eat Increment 3 Preparation architecture checkpoint

| Step | Current state |
|---|---|
| 1 — repository and primary-source review | Complete |
| 2 — findings and recommendation | Complete; refine existing Preparation owner |
| 3 — CTO and Founder architecture approval | PENDING |
| 4 — architecture and ADR | PROPOSED |
| 5 — risks, privacy and edge cases | Documented |
| 6–9 — implementation through operations | NOT AUTHORIZED / not started |
| 10 — stop | Satisfied; awaiting architecture review |

No new Preparation domain, runtime, schema, migration, API, test claim or production
authority is created by this checkpoint.

### P2 AYO Eat Increment 3 architecture approval closure

Approval recorded on 2026-07-23 by OpenAI ChatGPT, Project CTO (Technical Oversight),
and Ibrahim Hambentu Shibiru, Founder & CEO.

| Step | Current state |
|---|---|
| 1–5 — evidence, architecture, risks and approvals | Complete; APPROVED |
| 6–9 — Increment 3 implementation through verification | IMPLEMENTATION AUTHORIZED (PRE-PRODUCTION ONLY); not started by this closure |
| 10 — stop | Satisfied for governance mission |

Production and future increments remain unauthorized. Implementation must stop at the
Increment 3 technical gate.

### P2 AYO Eat Increment 3 technical checkpoint

| Step | Current state |
|---|---|
| 1–5 — approved architecture and risks | Complete |
| 6 — bounded PRE-PRODUCTION implementation | Complete |
| 7 — focused verification | Complete; full suite has one unrelated expired-quote failure |
| 8 — security/dependency review | Complete; live PostgreSQL certification pending |
| 9 — CTO/Founder implementation review | PENDING |
| 10 — stop | Satisfied; Increment 4 and production not started |

### Courier Pickup architecture and launch-admission checkpoint

| Step | Current state |
|---|---|
| 1 — repository authority and implementation-history review | Complete |
| 2 — external evidence and alternatives | Complete |
| 3 — CTO and Founder architecture approval | PENDING |
| 4 — architecture and ADR | PROPOSED |
| 5 — risks, privacy, authority and edge cases | Documented |
| 6–9 — implementation through operations | NOT AUTHORIZED / not started |
| 10 — stop | Satisfied; awaiting architecture review |

No new Pickup owner, runtime, schema, migration, API, test claim or production
authority is created by this checkpoint.

### Courier Pickup architecture approval closure

Approval was recorded on 2026-07-24 by OpenAI ChatGPT, Project CTO (Technical
Oversight), and Ibrahim Hambentu Shibiru, Founder & CEO.

| Step | Current state |
|---|---|
| 1–5 — evidence, architecture, risks and approvals | Complete; APPROVED |
| 6–9 — Increment 1 implementation through verification | IMPLEMENTATION AUTHORIZED — PRE-PRODUCTION ONLY; not started by this closure |
| 10 — stop | Satisfied for governance mission |

Production and successor increments remain unauthorized. Implementation must stop at
the Increment 1 technical gate.

### Courier Pickup Increment 1 technical checkpoint

| Step | Current state |
|---|---|
| 1–5 — approved architecture and risks | Complete |
| 6 — bounded PRE-PRODUCTION implementation | Complete |
| 7 — focused verification | Complete; PostgreSQL certification pending |
| 8 — security/dependency review | Complete; Bandit and dependency audit passed |
| 9 — CTO/Founder implementation review | PENDING |
| 10 — stop | Satisfied; Increment 2 and production not started |

### Repository Quality Initiative planning checkpoint

| Step | Current state |
|---|---|
| 1 — gate/configuration evidence | Complete |
| 2 — remediation recommendation and matrices | Complete |
| 3 — CTO and Founder approval | PENDING |
| 4 — authoritative gate contract | PROPOSED; no tooling change |
| 5 — risks and clean-worktree strategy | Documented |
| 6–9 — remediation, PostgreSQL execution and certification | NOT AUTHORIZED / not started |
| 10 — stop | Satisfied; awaiting Q0 governance review |

The proposal preserves the 70% whole-backend branch gate and treats tests-inclusive
MyPy as the stricter pending governance choice. It creates no runtime, schema,
migration, CI publication, PostgreSQL execution, product or production authority.

### Repository Quality Initiative Q0 contract checkpoint

| Step | Current state |
|---|---|
| 1 — authority/configuration review | Complete |
| 2 — canonical contract recommendation | Complete; `AYO-RQC-1` proposed |
| 3 — CTO and Founder approval | PENDING |
| 4 — CI/configuration alignment | NOT AUTHORIZED / not started |
| 5 — gate evidence and responsibility maps | Complete |
| 6–9 — Q1, remediation and certification | NOT AUTHORIZED / not started |
| 10 — stop | Satisfied; awaiting contract decision |

Q0 documents but does not resolve the MyPy/CI/certification contradiction. Existing
tooling remains unchanged until a later approval closure. PostgreSQL execution,
coverage/MyPy remediation, product work and production remain prohibited.

### AYO-RQC-1 approval and Q1 authorization checkpoint

| Step | Current state |
|---|---|
| 1–2 — contract evidence and recommendation | Complete |
| 3 — CTO and Founder approval | APPROVED on 2026-07-24 |
| 4 — AYO-RQC-1 | APPROVED |
| 5 — Q1 implementation | AUTHORIZED — PRE-PRODUCTION ONLY; not started by this closure |
| 6–9 — PostgreSQL, coverage/MyPy remediation and certification | NOT AUTHORIZED / not started |
| 10 — stop | Satisfied; governance closure complete |

Q1 may align the approved gate infrastructure and documentation only. Production and
Q2–Q13 remain unauthorized.

### AYO-RQC-1 control-decisions closure checkpoint

| Step | Current state |
|---|---|
| 1–2 — control gap review and recommendation | Complete |
| 3 — CTO and Founder approval | APPROVED on 2026-07-24 |
| 4 — scanner family, evidence class, marker owner, branch policy and database baseline | APPROVED |
| 5 — exact Gitleaks release and exact PostgreSQL/PostGIS OCI digest | RESOLVED from official sources on 2026-07-24 |
| 6–9 — Q1 implementation and later remediation/certification | Q1 not started by this control-closure mission; subsequently implemented |
| 10 — stop | Satisfied; partial control closure recorded |

The controlling record is `AYO_RQC_1_CONTROL_DECISIONS_2026-07-24.md`. Gitleaks
`v8.30.1` and the immutable OCI image-index digest for the repository-configured
PostgreSQL 17/PostGIS 3.6 image were resolved from official sources. All Q1
governance blockers are closed. No CI, configuration, runtime, database, test,
schema, migration or product work occurred.

### Q1 implementation checkpoint

Q1 implemented the approved alignment on 2026-07-24. `pyproject.toml`, CI
governance, validation commands, marker ownership, branch-administration policy and
certification-evidence structure now represent AYO-RQC-1. It did not execute
PostgreSQL or remediate MyPy or coverage. See
`AYO_REPOSITORY_QUALITY_Q1_IMPLEMENTATION_2026-07-24.md`.

Q2, product work and production remain unauthorized.

### Q2 repository-wide MyPy remediation checkpoint

Q2 was subsequently authorized and implemented on 2026-07-24. The authoritative
`BACKEND tests` scope now reports zero MyPy errors across 436 files, reduced from
291 errors across 34 files. Changes were limited to test typing and did not alter
runtime behaviour, APIs, schemas, migrations, CI configuration or gate strictness.

Q2 is awaiting CTO and Founder review. Coverage remediation, PostgreSQL
certification, Q3, product work and production remain outside this checkpoint.
See `AYO_REPOSITORY_QUALITY_Q2_MYPY_REMEDIATION_2026-07-24.md`.

### Q3 repository-wide coverage checkpoint

Q3 began on 2026-07-24 and added risk-focused tests without changing production
behaviour or coverage governance. Whole-BACKEND combined branch coverage increased
from 55.71% to 57.12%, below the mandatory 70.00% contract. The gate therefore
remains open and Q3 is not complete.

The checkpoint also records a production audit-allowlist incompatibility and 201
PostgreSQL-dependent skips. Neither was silently bypassed. See
`AYO_REPOSITORY_QUALITY_Q3_COVERAGE_REMEDIATION_2026-07-24.md`.

### Q3 risk-focused continuation checkpoint

The authorized continuation resolved the Eat Availability audit incompatibility
through the existing Audit contract and added 21 risk-focused tests. Coverage rose
from 57.12% to 58.12%; the 70.00% gate remains open.

The audit allowlist was not expanded, the scheduled 500 ms characterization was
not altered, and PostgreSQL/Engineering Certification did not begin. See
`AYO_REPOSITORY_QUALITY_Q3_CONTINUATION_2026-07-24.md`.

### Q3 continuation 2 checkpoint — 2026-07-24

Fourteen risk-focused application tests increased whole-`BACKEND` combined
line-and-branch coverage from 58.12% to 59.49%. The 70.00% gate remains open.
MyPy, Ruff, Bandit and `git diff --check` passed. PostgreSQL-dependent tests
remain skipped because `AYO_TEST_DATABASE_URL` is unavailable; no PostgreSQL
certification was attempted or claimed. Q3 must stop for CTO and Founder review.

### Q3 continuation 3 checkpoint — 2026-07-24

Twelve risk-focused tests increased whole-`BACKEND` combined coverage from
59.49% to 60.70% (+228 covered lines and +90 covered branches). MyPy, Ruff,
Bandit and `git diff --check` passed. The 70.00% and PostgreSQL certification
gates remain open; no PostgreSQL certification or product work began.

### Q3 coverage feasibility checkpoint — 2026-07-24

Assessment found that 2,440 further covered elements are required. Meaningful
non-PostgreSQL work is likely to plateau at 66.42%, with an optimistic defensible
ceiling of 68.89%. AYO-RQC-1 defines coverage and PostgreSQL as independent gates;
the original Quality Initiative sequences the PostgreSQL baseline before broad
coverage authoring. PostgreSQL remains unauthorized in this checkpoint. The next
recommended gate is explicit authority for a disposable PostgreSQL baseline while
Q3 remains open.

### P2 AYO Eat Increment 4 readiness-to-handoff architecture checkpoint

| Step | Current state |
|---|---|
| 1 — repository authority review | Complete |
| 2 — recommendation | Complete; no new capability/runtime |
| 3 — CTO and Founder architecture approval | PENDING |
| 4 — profile and ADR | PROPOSED |
| 5 — risks and boundary cases | Documented |
| 6–9 — implementation through operations | NOT AUTHORIZED / not started |
| 10 — stop | Satisfied; awaiting architecture review |
