# The AYO Constitution

Version: 1.0  
Adopted: 2026-07-14  
Status: highest project authority

## Preamble

AYO exists to solve real mobility problems and earn lasting trust, beginning in Ethiopia and growing responsibly. This Constitution governs product design, engineering, data, AI, financial systems, operations and technical delivery.

No roadmap, architecture, policy, deadline, experiment or implementation may override this Constitution. No code may violate it.

## Article 1 — Customer obsession before feature obsession

AYO starts with a clearly understood customer, driver or operations problem—not a desire to add features.

> Never build technology because it is possible. Build technology because it solves a real customer problem.

- Every proposed capability must identify the problem, affected people and measurable outcome.
- A simpler solution is preferred when it solves the problem safely and reliably.
- Feature count is not a measure of progress.
- Driver experience and sustainable earnings are part of customer obsession because reliable mobility depends on trusted driver partners.

### Mandatory feature-approval questions

Before any feature may be approved, its proposal must answer clearly:

1. What problem does it solve?
2. Who benefits?
3. How will success be measured?
4. What are the risks?
5. Is there a simpler solution?

If these questions cannot be answered clearly, the feature must not be built.

## Article 2 — Trust and safety over speed

Delivery speed never justifies avoidable harm, deception or unreliable operation.

- Safety-critical behavior must be explicit, tested, observable and supported operationally.
- Product wording must describe what AYO can actually deliver.
- High-impact automated decisions require appropriate safeguards, explanations and human review or appeal.
- Unresolved critical safety risks block release.

## Article 3 — Security by design

Security is a design constraint from the first decision, not a final checklist.

- Deny by default, grant least privilege and authorize every protected action and resource.
- Minimize sensitive data and protect it throughout collection, use, storage, sharing and deletion.
- Treat clients, devices, networks, provider events and AI outputs as untrusted inputs.
- Threat modelling, secure defaults, auditability, incident readiness and security testing are part of delivery.
- Unresolved critical security or privacy risks block release.

### Tiered Secure Computing

AYO applies computing isolation according to workload risk:

- Tier 1 uses standard hardened managed cloud controls for ordinary secure workloads.
- Tier 2 adds stronger isolation, access approval, key control and audit for highly sensitive workloads.
- Tier 3 uses attested confidential computing only for workloads whose threat, customer benefit or verified regulatory requirement justifies the additional cost and complexity.

Confidential computing is not mandatory for every workload and never replaces secure design, least privilege, encryption, auditability, backups or incident response. Tier definitions and promotion gates are governed by `AYO_COMPUTE_STRATEGY.md`; provider and deployment choices require CTO review and CEO approval.

## Article 4 — Ethiopian-first architecture with global standards

AYO is designed for Ethiopian users, drivers, infrastructure, markets and law while meeting rigorous global engineering standards.

- Cash, licensed local payment-provider integrations, weak networks, mixed devices, local languages and field operations are first-class realities.
- Ethiopian legal, regulatory and operational questions must be verified by qualified local authorities or specialists; engineers must not guess.
- Global standards for security, reliability, accessibility, privacy, financial integrity and software quality remain the baseline.
- Local adaptation must improve suitability without weakening safety, rights or engineering discipline.

## Article 5 — Build for 10 million users, not 1,000

Architecture and data models must have a credible path to serve 10 million users without requiring reckless premature complexity.

> Build systems that can survive success.

- Avoid process-local sources of truth, unbounded operations, collision-prone identifiers and designs that prevent horizontal growth.
- Use bounded queries, pagination, backpressure, idempotency, durable state and observable capacity limits.
- Define service-level objectives and test realistic load, failure and recovery behavior before scale demands it.
- Scale readiness does not require premature microservices. The simplest architecture that preserves clear boundaries and a safe scaling path is preferred.

### Mandatory architecture evaluation

Before an architectural decision may be implemented, answer:

1. Can it safely serve 10 million users?
2. Can it survive provider outages?
3. Can it be understood by a new engineer in six months?
4. Can it be tested automatically?
5. Can it be secured by default?
6. Can it be monitored in production?
7. Can it be upgraded without downtime where practical?
8. Can it be replaced without rewriting the entire platform?
9. Does it improve the customer experience?
10. Is it the simplest solution that correctly solves the problem?

If several answers are **No**, redesign before implementation. Any accepted limitation must identify evidence, mitigation, owner and review trigger and must remain consistent with this Constitution.

### Permanent engineering philosophy

> Measure first. Build second. Optimize third.

- Never optimize for hypothetical problems.
- Never add complexity without measurable benefit.
- Prefer simple, reliable, well-tested systems over clever ones.
- Establish a baseline and success threshold before optimization.
- Optimize only after measurement identifies a material customer, reliability, security, capacity or cost problem.

## Article 6 — AI is a first-class system, not an add-on

AI capabilities are designed as governed production systems with explicit purpose, inputs, evaluation, safety and fallback behavior.

- Start with the decision or user problem, then determine whether AI is justified.
- AI inputs, model/rule versions, outcomes and material decision reasons must be traceable.
- Evaluate accuracy, latency, cost, bias, fairness, drift, abuse and Ethiopian operating conditions.
- Provide deterministic rules and human/operational fallbacks for safety-critical or unavailable AI paths.
- AI must not silently make unapproved pricing, livelihood, safety, identity or legal-policy decisions.
- Data collection for AI follows privacy, consent, minimization and retention requirements.

## Article 7 — Every feature must reduce friction

Every feature must make an important task safer, clearer, faster or more reliable for its intended user.

- Measure total journey friction, including retries, uncertainty, support burden, weak connectivity and failure recovery.
- Do not transfer system complexity to riders, drivers or operations.
- Remove or redesign capabilities that create more confusion or work than the problem they solve.
- Accessibility, localization and low-connectivity behavior are part of friction reduction.

### Extremely easy access

The normal rider journey must use the fewest reasonable steps:

```text
Open AYO
  -> Confirm pickup
  -> Choose destination
  -> See price and ETA
  -> Request ride
```

The driver's core journey must remain simple and safe:

```text
Go online
  -> Receive clear offer
  -> Accept or decline
  -> Navigate
  -> Arrive
  -> Start
  -> Complete
```

Permanent usability rules:

- Use one primary action per screen whenever practical.
- Do not request information during onboarding unless it is necessary for safety, security, legal compliance or the immediate user outcome.
- Use progressive disclosure; show advanced options only when they are needed.
- Clearly distinguish pending, confirmed, failed and offline states.
- Design for weak connectivity, retries and interrupted sessions.
- Provide accessibility for disabled users, older users and people travelling with children or luggage.
- Measure booking completion time, abandoned bookings, user errors and support contacts.
- Simplify any flow that repeatedly confuses users.

Before any rider or driver interface implementation is approved, present user journeys, wireframes, a design-system proposal, accessibility checks, low-connectivity behavior and measurable usability targets for CTO review and CEO approval.

### Beautiful and premium product design

AYO must feel modern, calm, trustworthy and premium.

- Use clean screens with generous spacing.
- Use consistent typography, icons and reusable components.
- Minimize clutter and unnecessary text.
- Maintain clear visual hierarchy.
- Keep loading fast and interactions smooth.
- Provide accessible contrast, readable type and large touch targets.
- Support Amharic and English without breaking layouts.
- Perform well on affordable and older Android devices.
- Beauty must never reduce speed, clarity, accessibility or reliability.
- Establish a reusable AYO design system before building many screens.

Visual polish is valid only when it reduces friction or strengthens clarity and trust. Decorative complexity that harms performance or accessibility violates this Constitution.

## Article 8 — Every financial transaction must be auditable

Every movement of value must be server-authoritative, immutable, attributable and reconcilable.

- Use a durable double-entry ledger or an equivalently rigorous approved accounting model.
- Every posting links to a business event, actor/system source, currency, time, reason and idempotency key.
- Posted history is never edited or deleted; corrections use linked compensating entries.
- Provider events are authenticated, replay-protected and reconciled.
- Client-supplied fares, bonuses, commission, refunds or payout outcomes are never authoritative.
- AYO's driver balance remains an internal accounting ledger unless leadership and qualified Ethiopian legal review approve a different regulated model.

### Smart, fair and transparent pricing

AYO must use a server-controlled, versioned pricing algorithm. Rider and driver applications may display pricing results but may never authoritatively calculate or decide the fare.

The pricing engine may consider only approved, documented factors such as:

- Base fare.
- Route distance.
- Estimated trip time.
- Pickup difficulty.
- Traffic conditions.
- Waiting time.
- Service level.
- Airport or venue fees.
- Driver supply and rider demand.
- Approved bonuses, discounts and taxes.

Permanent pricing rules:

- AYO does not compete by being the cheapest.
- Pricing must support reliable service, safety and sustainable driver earnings.
- Riders see the estimated total and important conditions before confirming.
- Drivers see policy-approved expected earnings information.
- Nationality, ethnicity, language and other protected personal characteristics must never influence pricing.
- Every quote and final fare records its pricing-rule version and explanation components.
- Dynamic pricing requires leadership-approved limits and must never exploit emergencies.
- Actual prices require research into the Ethiopian market and real operating costs.
- No final fare values may be implemented without CTO review and CEO approval.

Pricing must be tested for correctness, transparency, prohibited inputs, fairness, manipulation resistance, rounding, retries and emergency-limit enforcement before release.

## Article 9 — Never sacrifice code quality for speed

Urgency changes prioritization, not the standard of correctness.

- Production changes require clear scope, review, tests, secure configuration, observability and rollback or recovery planning proportional to risk.
- Dependencies and environments must be reproducible.
- Known debt and exceptions must be explicit, owned, time-bounded and prevented from becoming hidden policy.
- Working code is preserved through characterization and compatible migration rather than unexplained rewrites.

## Article 10 — Every module must be independently scalable

Each domain module must have a clear responsibility, ownership boundary and credible independent scaling path.

- Modules expose explicit contracts and do not reach into another module's private state.
- Data ownership, workload, failure behavior and performance limits are identifiable per module.
- Hot workloads can be scaled, queued, cached, partitioned or extracted without rewriting unrelated domains.
- Independent scalability does not require immediate independent deployment. A modular monolith is valid when boundaries are enforced and extraction remains safe.
- Shared infrastructure must not erase domain ownership or allow failures to spread without controls.

## Article 11 — Every decision must be documented with reasons

Material decisions must be discoverable and explainable.

- Record the problem, decision, alternatives, reasons, consequences, risks, owner, date and approval status.
- Clearly separate approved decisions, proposals, provisional assumptions and matters requiring legal or operational verification.
- Code and documentation must not present a proposal as approved policy.
- When evidence changes, supersede a decision explicitly rather than silently rewriting history.

Every proposed technical decision must document, before implementation:

- The problem and why a decision is needed.
- The recommended option and why it is recommended.
- Reasonable alternatives considered and why they were not selected.
- Security, safety, privacy, scalability, reliability, financial, AI, regulatory and delivery risks as applicable.
- Required CTO review and CEO approval status.

## Article 12 — Enforcement

Every change must demonstrate constitutional compliance during planning, review and release.

Every mission must follow `AYO_ENGINEERING_WORKFLOW.md` in order: research; findings and recommendation; CTO review and CEO approval; architecture; risks and edge cases; production-quality implementation; automated tests; security and performance verification; decision documentation; then a stop for approval before the next mission. No step may be skipped.

A change is blocked when it:

- Violates an Article.
- Hides or misrepresents a material risk or decision.
- Introduces unauditable financial movement.
- Weakens security, privacy, safety or legal compliance without authorized resolution.
- Creates an architecture with no credible path to the required scale.
- Adds user friction without a documented, approved justification.
- Skips or reorders a required Engineering Workflow gate without a constitutional amendment.

Reviewers must cite the relevant Article when blocking or requiring changes. Automated checks should enforce constitutional requirements where practical, but passing automation never replaces engineering judgment or leadership authority.

## Article 13 — Authority and conflict resolution

### Leadership and engineering authority

- **CEO:** Owns AYO's vision and strategy and makes final business and product decisions. The CEO gives final approval for major architecture or product decisions after CTO review.
- **CTO:** Owns technical architecture, code quality, security, scalability and engineering approvals. The CTO reviews all major architecture and technical proposals before they are presented for CEO approval.
- **Codex:** Acts as a senior software engineer responsible for implementation only. Codex may inspect, analyze, test, document options and implement approved work, but may not independently approve or establish major architecture or product policy.

No major architecture or product decision may be implemented until it has been presented for CTO review and received CEO approval. If approval is absent or ambiguous, implementation must stop at analysis and proposal.

The order of authority is:

1. `docs/AYO_CONSTITUTION.md`
2. CEO-approved decisions following required CTO review, recorded in `docs/AYO_DECISION_LOG.md`
3. `AGENTS.md` engineering instructions
4. Security, architecture, blueprint and roadmap documents
5. Mission plans, implementation notes and code-level conventions

If two instructions conflict, follow the higher authority and record the conflict and resolution. Applicable law and binding regulatory requirements must always be followed; any apparent conflict with this Constitution must be escalated immediately to leadership and qualified counsel rather than resolved by engineering guesswork.

## Article 14 — Amendments

Only the Founder and authorized AYO leadership may approve amendments.

Every amendment must:

- State the problem and reason for change.
- Identify affected Articles, systems and decisions.
- Include security, safety, privacy, financial, scalability, AI and Ethiopian legal/operational impact as applicable.
- Be recorded in the decision log with approval and effective date.
- Preserve prior versions in version control.

Convenience, deadlines and implementation difficulty are not sufficient reasons to weaken the Constitution.

## Constitutional review checklist

Before approving a material change, answer:

1. What real customer, driver or operations problem does this solve?
2. Who benefits?
3. How will success be measured?
4. What are the risks?
5. Is there a simpler solution?
6. Does it improve or preserve trust and safety?
7. Is security designed into the change?
8. Does it fit Ethiopian realities and require local verification?
9. Does it retain a credible path to 10 million users?
10. Is any AI component governed, evaluated, explainable and recoverable?
11. Does it reduce total user and operational friction?
12. Are all financial movements immutable and auditable?
13. Does the implementation meet production code-quality standards?
14. Can affected modules scale independently with clear boundaries?
15. Is the decision documented with its reasons and authority?

Any unresolved **no** blocks approval or requires an explicitly documented leadership decision consistent with this Constitution.
