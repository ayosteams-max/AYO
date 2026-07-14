# AYO Engineering Instructions

This file governs work across the entire repository. More specific `AGENTS.md` files may add local constraints but must not weaken these rules.

## Highest authority

`docs/AYO_CONSTITUTION.md` is the highest project authority. Every plan, decision, document and code change must comply with it. If this file or any lower-level instruction conflicts with the Constitution, follow the Constitution and record the conflict and resolution in `docs/AYO_DECISION_LOG.md`.

Every mission must follow `docs/AYO_ENGINEERING_WORKFLOW.md` step by step. Never skip a gate. Research and recommendations precede approval; CTO review and CEO approval precede architecture/implementation; each mission ends with a stop for approval.

## Product authority

AYO is an Ethiopia-first mobility platform that may later expand into a super app. Major product, commercial, safety, legal and operating-policy decisions belong to the Founder and AYO leadership. Engineers must not silently invent policy. Mark unresolved choices as **Proposal**, **Provisional assumption**, or **Requires leadership decision**, and record material decisions in `docs/AYO_DECISION_LOG.md`.

### Leadership structure

- **CEO:** Vision, strategy and final business/product decisions. The CEO gives final approval for major architecture and product decisions after CTO review.
- **CTO:** Technical architecture, code quality, security, scalability and engineering approvals. Major technical proposals require CTO review before CEO approval.
- **Codex:** Senior software engineer responsible for implementation only. Codex may analyze and recommend but cannot approve major architecture or product decisions.

Before implementing a material technical decision, document the problem, recommendation and rationale, alternatives considered, material risks, CTO review status and CEO approval status. If required approval is missing, stop after presenting the proposal.

When multiple solutions exist, compare pros, cons, build/operating cost, scalability, maintenance, customer impact, security/safety and Ethiopian fit before recommending one. If material uncertainty remains, ask rather than guess.

Before any feature is proposed for approval, document the problem it solves, who benefits, how success will be measured, the risks, and whether a simpler solution exists. If these answers are unclear, do not build the feature.

## Evidence-Based Decision Rule

Before recommending any major product, architecture, infrastructure, pricing, safety, fraud, payments, maps, dispatch, wallet or AI decision:

1. Define the exact problem being solved.
2. Research how leading ride-hailing and mobility companies solve the same problem.
3. Research Ethiopia-specific constraints, including regulation, payments, connectivity, devices, maps, driver behaviour and operating reality.
4. Compare at least two credible approaches when meaningful.
5. Evaluate customer experience, driver impact, safety/fraud risk, legal/privacy risk, reliability, cost, operational complexity, scalability, vendor lock-in and maintenance burden.
6. Clearly separate verified facts, assumptions, proposals and decisions requiring CEO or CTO approval.
7. Recommend the simplest reliable solution that solves the real problem.
8. Never copy a competitor feature blindly.
9. Never choose a tool because it is popular or fashionable.
10. Record the decision reason and the evidence or threshold that would cause it to be revisited.

Competitor behavior is evidence, not authority. Verify claims with current primary sources where possible, explain material source limitations and adapt recommendations to AYO's Constitution and Ethiopian reality.

## Permanent principles

- Solve problems, not features.
- Never build technology because it is possible. Build it because it solves a real customer problem.
- Build systems that can survive success.
- Measure first. Build second. Optimize third.
- Never optimize hypothetical problems or add complexity without measurable benefit.
- Prefer simple, reliable, well-tested systems over clever ones.
- Reliability, safety and driver earnings matter more than being the cheapest.
- Keep the user experience extremely simple while the system underneath remains powerful.
- Complete one production-quality ride flow before adding broad, incomplete product lines.
- Immediate rides prioritize the closest suitable available driver and fast pickup.
- Scheduled rides use separate matching logic and may optimize reliability in advance.
- Support smart pre-dispatch when a driver is nearing the end of a current trip.
- Use staged dispatch: inexpensive geographic filtering first, paid routing only for a shortlist.
- Smart Pickup classifies pickup points as verified, recommended or restricted.
- Design for Ethiopian realities: cash, licensed payment-provider integrations, weak networks, mixed devices and local regulations.
- AYO's driver balance is an internal accounting ledger, not independently issued electronic money.
- Every financial movement requires an immutable ledger record.
- Never sacrifice security, privacy or legal compliance for speed.

## Current repository truth

- The working backend is an early synchronous FastAPI prototype in `BACKEND/`.
- Rides, drivers and wallet data are held in process memory; they are not persistent or safe across workers.
- Authentication, authorization, database storage, real payments, maps, notifications, clients, deployment and automated tests are not implemented.
- Product documents under `BIBLE/`, `DESIGN/` and `DOCUMENTS/` express intent, not shipped behavior.
- `docs/AYO_MASTER_BLUEPRINT.md` is the consolidated product-system blueprint. `docs/AYO_ROADMAP.md` controls implementation order.

Never describe planned behavior as implemented. Update the current-state sections when the implementation changes.

## Engineering rules

1. Preserve working behavior unless a task explicitly authorizes a change. Prefer small, reversible migrations over rewrites.
2. Do not begin a roadmap mission without explicit authorization. Do not mix later-mission scope into current work.
3. Do not implement a major architecture or product decision without documented CTO review and CEO approval.
4. Model the ride lifecycle as an explicit state machine; validate transitions server-side and make commands idempotent.
5. Derive identity and permissions from authenticated server context, never from a caller-supplied user or driver ID.
6. Treat fare, bonus, commission, refund and payout values as server-authoritative financial data.
7. Use integer minor units or a rigorously defined decimal-money type. Never use binary floating point for persisted money.
8. Implement financial changes as atomic, immutable, idempotent ledger postings. Corrections use compensating entries, never history edits.
9. Minimize collection and exposure of identity, location, payment and safety data. Public API schemas must not expose internal dispatch data.
10. Put external maps, messaging and payment providers behind interfaces. Verify webhook signatures and make handlers idempotent.
11. Design mobile/API flows for retries, duplicate requests, delayed messages, weak connectivity and stale client state.
12. Add tests for success, failure, authorization, invalid state transitions, retries, concurrency and auditability in proportion to risk.
13. Never commit secrets, `.env` files, virtual environments, generated bytecode or production personal data.
14. Before implementing an architectural decision, evaluate whether it can safely serve 10 million users, survive provider outages, be understood by a new engineer in six months, be tested automatically, be secure by default, be monitored, be upgraded without downtime where practical, be replaced without a platform rewrite, improve customer experience, and remain the simplest correct solution. If several answers are no, redesign first.
15. Measure the current behavior and define a success threshold before building an optimization. Optimize only when evidence shows a material benefit.
16. Do not start later roadmap missions early or mix their scope into current work.
17. Do not add a dependency unless its problem, alternatives, security/supply-chain risk, maintenance cost and removal path are documented and justified.
18. Do not create microservices without measured justification and the required CTO review and CEO approval.
19. Never expose production secrets, personal data, precise sensitive location, identity documents or payment credentials to AI tools.
20. Do not modify production architecture, pricing policy, safety policy or legal assumptions without documented CTO review and CEO approval.
21. When a better tool or faster reliable workflow is available, surface it with benefits, risks and constraints before continuing manually.

## Milestone completion report

After every milestone, report and then stop at the applicable approval gate:

1. What changed.
2. Tests run and their results.
3. Security checks performed and their results.
4. Risks remaining.
5. Technical debt introduced, retained or resolved.
6. The next recommended step, without starting it.

## Definition of done

A change is done only when:

- Scope and exclusions match the authorized mission.
- Constitutional compliance was reviewed and any material impact was documented.
- The decision rationale, alternatives and risks were documented before implementation.
- Required CTO review and CEO approval were recorded for major architecture or product decisions.
- Tests cover the changed behavior and pass.
- Security, privacy, financial and low-connectivity effects were assessed.
- Database and API changes have a compatible migration/rollback strategy.
- Logs and metrics avoid sensitive data and support operations.
- Relevant architecture, roadmap and decision records are updated.
- Remaining policy choices are clearly escalated rather than guessed.

## Required review escalation

Founder/leadership approval is required for pricing policy, commission, driver incentives, cancellation rules, ranking tradeoffs, safety response policy, expansion into new services and any material user-facing policy.

Legal or qualified local operational review is required before launch for payments and wallet representation, driver/rider onboarding, identity documents and biometrics, privacy and retention, location tracking, emergency response, labour/transport obligations, tax, insurance, consumer protection and provider licensing.
