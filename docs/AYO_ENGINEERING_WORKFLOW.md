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
