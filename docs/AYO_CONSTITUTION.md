# The AYO Constitution

Version: 1.16
Adopted: 2026-07-14
Amended: 2026-07-21 — Foundational Constitution milestone
Status: highest project authority; foundational framework complete pending final constitutional sign-off

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

### AYO AI Governance & Marketplace Health Platform

AYO maintains a permanent, constitutionally governed AI Governance & Marketplace Health Platform to
protect the long-term health of the ecosystem. It continuously evaluates evidence concerning customer and
partner outcomes, marketplace fairness, company sustainability, AI recommendation quality, safety, legal
compliance, privacy and alignment with this Constitution.

This platform evaluates and recommends only. It never performs an operational decision, changes domain
state, overrides a certified authority, grants permission, moves money, dispatches work, approves a person
or business, or silently blocks an authorized operation. Operational, safety, legal, financial and other
domain authorities remain responsible and accountable for their decisions.

Every significant AI recommendation must be designed for eventual evaluation against:

- Customer Value.
- Partner Value.
- Company Sustainability.
- Marketplace Health.
- Safety.
- Legal Compliance.

Privacy and constitutional alignment are mandatory governance constraints across every evaluation. When a
mandatory rule fails or evidence is missing, stale or conflicting, the platform records the reason and
recommends human or authoritative-domain review. It does not resolve the failure by expanding its authority.

The platform monitors long-term risks including off-platform behaviour, concentration risk, recommendation
bias, fair opportunity, trust degradation and fraud patterns. These signals are evidence, not guilt,
eligibility, ranking, pricing, punishment or enforcement decisions. Material recommendations remain
explainable, auditable, purpose-limited and subject to the authority and human-review rules of the
Multi-Layer Intelligence Architecture.

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

### AYO Community Impact Platform

AYO maintains a permanent Community Impact Platform foundation for future leadership-approved
assistance to elderly people, people with disabilities, orphans, people affected by disasters,
people requiring verified operational-recovery assistance and participants in other approved
community-support programmes.

Support eligibility is private, purpose-limited and never a public label, profile category,
marketing segment or participant-visible status. AYO discloses only the minimum information
required to deliver an approved benefit. Sensitive eligibility evidence is segregated,
access-controlled, retained only as lawfully necessary and never used to infer unrelated
identity, pricing, ranking, dispatch, employment or marketplace outcomes.

Potential benefits—including ride or delivery assistance, community ride credits,
accessibility support and merchant-, government- or charity-funded support—are configurable
programme policy. No value, entitlement, duration, funding share or eligibility threshold is
constitutional or hardcoded. The Community Impact Platform does not issue money, hold funds,
post ledger entries, settle providers or bypass the certified Financial Platform. Every future
movement of value remains server-authoritative, immutable and reconcilable under this Article.

Funding may eventually originate from an approved Community Fund, AYO company contribution,
government partnership, charity partnership or merchant contribution. Each source requires
separate legal authority, accounting treatment, restrictions, provenance, reconciliation and
leadership approval. Assistance must preserve company sustainability and marketplace fairness;
it must not silently shift costs, distort dispatch, discriminate, create misleading promises or
weaken service reliability.

Bounded Intelligence may review authorized evidence, identify missing documents and recommend
approval, return or review with evidence, confidence, reasoning and risks. AI never approves,
revokes, activates, prices or funds a benefit. Final approval and revocation remain with an
authenticated, authorized human operating under approved policy, review and appeal controls.

This constitutional foundation creates no benefit, eligibility, fund, financial instrument,
runtime, migration, provider integration or production authority. Ethiopian legal, disability,
child-safeguarding, charity, government-programme, privacy, tax, accounting and consumer-
protection review remains mandatory before implementation or activation.

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

### Constitutional Founder Office Platform

AYO maintains a protected Founder Office Platform, separate from every operational platform,
to preserve Founder-level constitutional authority, long-term vision, governance continuity,
delegation and complete constitutional audit evidence. It is not an operational AI, business
Intelligence domain, ordinary administrative console or universal super-user.

Founder Intelligence observes minimized, authorized evidence across company, marketplace,
financial, community-impact, AI-governance, operational and strategic health. It prepares
recommendations with evidence, confidence, reasoning and risks. It never approves, dispatches,
prices, moves money, changes access, mutates operations or performs any other operational action.

The Founder Policy Engine identifies potentially affected platforms, policies, approved knowledge,
AI rules, workflows and documentation and prepares a complete review package. It never applies a
change. Founder-level decisions enter a protected Founder Approval Queue and require the Founder or
a lawfully authorized Founder-level decision-maker. No policy changes silently because AI, a queue,
a dependency analysis or an approval package exists.

The Founder Vault isolates constitutional rules, Founder principles, strategic policies,
delegation rules, succession policies and audit history. Operational users, representatives,
merchants, drivers, Support, operational AI and business Intelligence domains have no direct
access. Purpose-scoped, minimum, approved projections may be released without exposing Vault data
or expanding recipient authority.

Founder delegation is explicit, purpose- and action-scoped, attributable, revocable and time-
limited where required. It never transfers Founder ownership or silently creates subdelegation.
Succession is never automated: it requires lawful governing instruments, verified identity,
required independent approvals, waiting and objection periods where applicable, conflict handling
and complete evidence. Emergency lock, approval freeze, delegation suspension and recovery controls
are protective state changes only; they cannot create a successor, rewrite policy, evade lawful
governance, conceal audit history or permanently concentrate authority through recovery.

Every constitutional amendment and Founder-level decision records immutable proposal, evidence,
approvals, effective time, impact, dissent/conflict where legally appropriate, delegation or
succession lineage and rollback/compensation implications. Operational availability cannot weaken
this evidence requirement.

This Constitution does not replace applicable law, AYO's legal ownership records, articles,
shareholder rights, board duties, binding agreements, regulatory authority or court orders.
Where they conflict or remain undefined, the action stops for qualified Ethiopian corporate counsel
and authorized governance review. Company ownership and constitutional authority are protected
independently from operational systems, but are exercised only through lawful governance.

Operational architecture and public enterprise workflows refer to this protected constitutional
boundary as the **Governance Office**. The Governance Office abstraction may internally resolve to
Founder Intelligence, the Founder Policy Engine, Founder Vault, delegation, succession, emergency
controls, board governance, executive governance or later lawfully approved structures. Operational
participants neither need nor receive knowledge of that internal resolution.

### Constitutional Authority Routing Engine

AYO maintains one Authority Routing Engine to determine the minimum lawful approval authority for
every governed decision. It evaluates the approved decision category, financial impact, operational
impact, constitutional impact, legal requirements, risk level, applicable delegation and effective
governance policy and routes the request to the correct approval queue.

The engine never approves, rejects, executes, changes policy, grants permission or decides the
substance of a request. Routing is not approval, and Authorization remains responsible for verifying
that the eventual human decision-maker may access and decide the specific request. Founder
Intelligence and Approval Intelligence remain recommendation-only.

“Minimum” means the least senior authority that is lawful and sufficient under current approved
governance—not the cheapest, fastest or easiest reviewer. Ambiguous, conflicting, missing, stale or
legally uncertain routing evidence fails closed to authorized governance review. The engine cannot
downgrade authority through request splitting, misleading categorization, delegation chains,
financial fragmentation, omitted impacts or AI confidence.

Routing policy is human-approved, versioned, effective-dated and auditable. Every result records the
request classification, applicable policy and delegation versions, required authority class, reasons,
material impact inputs, unresolved constraints and routing time. A policy update does not silently
reroute a decision already under review unless approved transition rules require re-evaluation.

Operational users receive minimum-disclosure status such as `Pending Review`, `Pending Senior Review`
or `Pending Governance Approval`. They do not receive Governance Office internals, protected delegation
structures, reviewer identities, security controls or strategic evidence unless separately authorized.

The Authority Routing Engine cannot supersede applicable law, governing instruments, regulators,
courts, board/shareholder duties or a certified domain authority. Required approvals may be additive;
where law or policy requires multiple independent decisions, the engine routes each without collapsing
them into a hierarchy or treating one approval as another.

### Constitutional Governance Communications Gateway

AYO maintains one Governance Communications Gateway as the public enterprise intake boundary for
legitimate communications intended for governance. Operational users, merchants, partners,
investors, media, government bodies, regulators, courts, lawful authorities and external
organizations communicate with the Governance Office abstraction, not directly with protected
Founder communications or internal governance components.

Every communication is treated as untrusted until classified and supported by appropriate sender,
channel and document evidence. Classification may identify government, regulator, court/lawful
authority, strategic partnership, investor, major commercial proposal, media, security incident,
operational escalation or general enquiry. Classification prepares routing only. It never decides
validity, merits, legal effect, urgency policy, company response or governance outcome.

The Authority Routing Engine determines the minimum lawful approval destination under effective
governance. External and operational participants receive only minimum workflow status. They never
learn whether Founder authority was involved, the internal route, delegation, reviewer identity,
protected hierarchy or Governance Office implementation.

Governance AI may assist with sender-evidence checks, document summarization, missing-information
detection, urgency indicators, routing recommendations and executive-summary drafts. These outputs
are untrusted recommendations with evidence, confidence, reasoning and risks. AI never impersonates
the Founder or another human, commits AYO, accepts legal obligations, waives rights, promises a
response or outcome, approves a constitutional decision or sends a binding communication.

Founder personal email, phone, messaging accounts and location remain protected and are never public
routing data. Only authenticated, authorized and audited governance processes may deliver a minimum
approved communication into a Founder-level boundary.

Government, court and regulator communications receive clear evidence status and qualified human/
legal review. The Gateway may prepare sender-verification evidence, purpose summary, required-response
indicators, recommendation and supporting references, but cannot determine lawful service, authenticity,
jurisdiction, deadline or response obligation by itself. Intake or acknowledgement never waives rights,
accepts service, creates jurisdiction or changes a legal deadline. Approved legal channels and qualified
counsel remain authoritative.

The Gateway provides no guarantee that a submission is accepted, confidential, privileged, reviewed by
the Founder or approved. Binding commitments require separately authenticated and authorized human
approval and execution through the owning legal, financial, commercial or governance authority.

#### Governance Case Communication

Every public or operational Governance Office interaction is attached to one official governance case.
Participants may submit additional information, reply to an authorized request, upload documents or ask
for clarification through that case. They never receive a direct communication channel to the Founder,
governance or executive reviewers, approval representatives or any Intelligence domain.

Governance Office replies use an organization identity and remain part of the immutable case history.
Ordinary operational communication requires no personal executive or reviewer identity. Internal actors
may remain attributable inside protected audit evidence without becoming visible to the participant.

Operational decision presentation exposes only the minimum applicable state: `Pending Review`, `Pending
Senior Review`, `Pending Governance Approval`, `Approved`, `Returned for Correction` or `Rejected`.
After decision, the outcome heading is only `Approved`, `Returned for Correction` or `Rejected`.
Approved policy or law may require a minimum reason, correction list, effective date, deadline, review or
appeal path; that explanation must remain useful without revealing internal routing, reviewer identities,
Founder participation, governance hierarchy, AI involvement or Authority Routing determinations.

Case-based communication is not social messaging. It does not create a relationship with an individual
reviewer, permit searching or contacting governance personnel, reveal presence/availability or allow an
internal participant to move the conversation to personal channels. Every message, request, document,
acknowledgement and outcome retains case, sender-role, time, purpose and immutable audit lineage.

#### Governance Decision Finality

A completed governance outcome is final for its associated case unless an authorized governance process
explicitly reopens it. `Approved`, `Returned for Correction` and `Rejected` are immutable decision
outcomes. Where applicable, the case then transitions to `Closed`; closure prevents new participant-
initiated debate, negotiation, evidence or messaging on that completed decision.

Finality does not remove an appeal, correction, resubmission, new application, regulatory, court or other
right established by applicable law or approved policy. Such action proceeds only through its authorized
governance process. An appeal, resubmission, new application or Governance-initiated request for additional
information creates a distinct governance action with its own identity, authority determination, evidence,
decision and audit history linked to—not substituted for—the original case.

No later action overwrites, edits, deletes, re-labels or obscures the original outcome. A lawful reopening
is an explicit, authorized and audited lifecycle event; it does not pretend the original case was never
final. Clerical correction uses linked correction evidence and cannot silently change substantive meaning.

Governance Office communication remains respectful, professional, policy-based and clear about finality
and any available next process. It never encourages repeated negotiation, personal escalation or off-case
contact after completion. Attempts to continue a closed discussion receive the minimum applicable finality
notice and approved next-process information without creating a new review.

#### Governance Policy Versioning

Every governance decision is permanently bound to the exact approved policy version effective when the
decision was made, together with its effective date/time and the constitutional version where relevant.
The immutable case evidence records stable policy and version identifiers, owning authority, jurisdiction
and scope, effective window, decision time and an integrity reference sufficient to recover the approved
policy text and rules used.

Later amendment, correction, expiry, retirement or replacement of a policy never alters the historical
basis, evidence, explanation or outcome of an existing decision. Policies evolve through new immutable
versions; historical cases do not silently resolve through the latest policy.

An appeal, review, audit or regulatory investigation evaluates the original decision against the policy
and constitutional versions effective at the original decision time unless applicable law or an approved
legally authorized retrospective rule requires otherwise. The review separately records its own governing
policy version, current legal evidence and any retrospective authority. It never disguises current-law
analysis as the original historical basis.

If a historical policy is later found invalid, unlawful, incorrectly applied or affected by a material
error, the original record remains immutable. Any remedy, reconsideration, correction, redress or new
decision is a linked governance action with its own authority, policy versions, reasons and audit lineage.

Policy references are required governance evidence, not optional metadata. A decision cannot be treated
as complete when its applicable version cannot be resolved or when multiple effective versions conflict;
the matter fails closed for authorized governance and legal review.

#### Constitutional Supremacy

Every AYO platform, Intelligence domain, workflow, procedure, automation and future capability operates
under one permanent governance hierarchy:

1. Applicable law.
2. The AYO Constitution.
3. Approved governance policies.
4. Approved operational procedures.
5. AI recommendations and operational automation.

No platform, workflow, AI model, automation, operational procedure, technical configuration, commercial
pressure or delivery deadline may override this Constitution. The Constitution cannot authorize conduct
prohibited by applicable law. An apparent conflict with law stops the affected action for qualified legal
and authorized governance review.

Governance policies must conform to applicable law and the Constitution. Operational procedures must
conform to applicable law, the Constitution and approved effective governance policies. AI and automation
may operate only within all higher authorities and their explicit delegated scope.

AI may recommend, analyze, summarize, classify or prepare decisions within its approved authority. It
never overrides the Constitution, approved policy or lawful governance decisions; creates unauthorized
governance authority; treats confidence as permission; resolves a legal conflict; or silently chooses a
lower authority because it is faster, cheaper or operationally convenient.

When guidance conflicts, the higher authority prevails. A lower-level instruction is rejected or suspended
only to the extent of conflict and does not mutate the higher authority or historical evidence. Conflicting
instructions at the same level fail closed until the accountable authority resolves them under effective
versioning, scope, jurisdiction and approval rules.

Every detected material conflict and resolution records the conflicting artifacts and versions, applicable
hierarchy levels, scope, evidence, deciding authority, reasoning, effective time, affected systems,
remediation and immutable audit lineage. Resolution never silently edits or deletes the original guidance.

#### Constitutional Exceptions

A departure from ordinary governance is permitted only when required by applicable law, a valid court
order, a binding regulatory direction, a declared emergency under competent lawful or constitutional
authority, or another lawful authority expressly recognized by this Constitution. An exception is not a
general power to suspend the Constitution, invent authority or avoid an inconvenient rule.

Every exception must be necessary, lawful, purpose-limited and no broader than its authoritative basis.
Where the basis is temporary, the exception has an explicit expiry or review condition and ends when that
basis no longer applies. Continuation requires fresh lawful authority and new linked evidence; elapsed
time, operational dependence or repeated use does not renew an exception.

Before activation, or as soon as lawfully possible during a genuine emergency, the immutable exception
record identifies:

- the exact legal or constitutional basis and authoritative instrument;
- purpose, scope, affected rules, people, systems and jurisdictions;
- effective time and expiry, termination or review conditions;
- approving authority and proof of authorization; and
- supporting evidence, safeguards, required notifications and restoration actions.

The responsible authority records activation, every review, modification, use, expiry, revocation and
closure. Emergency urgency may change when evidence is recorded but never removes the evidence duty.
Sensitive evidence may be access-controlled, but its existence, integrity and authorized audit lineage
cannot be concealed or erased.

An exception never automatically amends the Constitution, becomes precedent, or creates a permanent
governance policy or operational procedure. Permanent change follows the ordinary constitutional
governance, approval, versioning and change-management process. AI may identify a possible need, assemble
evidence and monitor conditions, but it cannot declare, approve, broaden, renew or convert an exception.

#### Constitutional Stability

This Constitution governs AYO's enduring principles, permanent authority boundaries and long-term
enterprise integrity. It is not the normal home for business rules, operating practices, technical
standards, thresholds, provider choices, workflows or implementation details.

Constitutional amendment is reserved for a necessary change concerning fundamental governance,
constitutional authority, legal structure or long-term enterprise integrity. Preference, convenience,
temporary conditions, product iteration, technical fashion, implementation difficulty or a desire to
avoid ordinary governance are insufficient reasons to amend it.

Business rules, operational practices, technical standards and implementation details evolve through
approved, versioned governance policies and operational procedures under Constitutional Supremacy. Those
lower layers may adapt within delegated authority but cannot contradict, dilute or silently reinterpret a
constitutional principle.

Where constitutional wording permits more than one lawful interpretation, the authorized interpreter
favors the reading that preserves constitutional continuity while leaving the greatest lawful operational
flexibility to lower governance layers. Interpretation cannot create an unstated constitutional power,
override applicable law, or substitute for an amendment where the constitutional meaning must change.

Every proposed constitutional amendment includes a compatibility analysis against all previously approved
constitutional principles. Existing principles remain effective unless the amendment explicitly identifies
what it replaces, the lawful approving authority, reasons, effective version and date, consequences,
transition and immutable supersession lineage. Silence, inconsistency or later operational practice never
repeals a constitutional principle.

#### Constitutional Interpretation

This Constitution is interpreted as one coherent framework. Its Preamble, Articles and approved
constitutional principles are read together according to their purpose, authority boundaries and recorded
constitutional intent. No sentence, example or principle may be isolated to produce a result that conflicts
with the Constitution as a whole.

Every interpretation must remain consistent with applicable law, Constitutional Supremacy,
Constitutional Stability and all previously approved constitutional principles still effective for the
version being interpreted. Where provisions can operate together, interpretation preserves each rather
than treating one as silently repealed. A genuine unresolved conflict follows the constitutional conflict
and amendment processes; an interpreter does not choose a preferred provision for convenience.

Where genuine ambiguity remains, Governance acting through the minimum lawful constitutional authority
may issue an official interpretation. The interpretation explains how existing constitutional text applies
to a defined question, facts, scope and constitutional version. It does not amend, replace, expand, narrow
or repeal the Constitution; create new authority; or substitute for an amendment required to change its
meaning.

Every official interpretation is immutable governance evidence recording its stable identifier, question,
relevant facts and scope, interpreted constitutional version and provisions, applicable law, approving
authority, reasoning, outcome and effective date. It remains linked to later review, clarification,
supersession or amendment without rewriting its historical record.

Future constitutional amendments consider all relevant official interpretations and state their
compatibility, continued applicability or explicit displacement. An interpretation follows the
constitutional version it explains and cannot be silently applied to materially different future text.

#### Constitutional Equality

The Constitution provides equal constitutional protection and constraint to every person, organization,
partner, customer, merchant, driver, courier, representative, employee, executive, shareholder and
governance participant. Position inside or outside AYO does not increase or reduce constitutional
protection, accountability or obligation.

Constitutional meaning, interpretation, access to lawful governance process and application of authority
must not vary because of status, influence, personal or commercial relationship, commercial value,
investment, political interest, public profile or proximity to a decision-maker. No person or organization
acquires constitutional privilege, immunity or preferential interpretation through position, authority,
ownership, investment or relationship.

Equality does not require identical operational treatment where relevant circumstances lawfully differ.
Differentiation is permitted only when applicable law requires it, this Constitution expressly permits it,
or an approved effective governance policy establishes objective criteria consistent with higher
authority. The differentiation must remain purpose-based, no broader than justified and subject to the
same authorization, evidence, review and audit standards. Protected Identity, accessibility, safeguarding,
legal duties and risk controls may provide different protections without creating constitutional rank.

Where equality or differentiation materially affects a governance decision, immutable evidence records
the applicable constitutional and policy basis, objective criteria, relevant facts, authorized authority,
reasoning, scope and outcome. Sensitive identity or risk evidence remains minimum-disclosure and
access-controlled, but preferential treatment cannot be hidden behind confidentiality.

AI, automation and operational discretion cannot infer constitutional privilege or disadvantage from
status, influence, value, relationships, political interest or public profile. They remain subordinate to
the same constitutional equality, authorization and audit requirements as human decisions.

#### Constitutional Intent

The Constitution is applied to preserve its enduring purpose, mission, governance philosophy and
foundational protections. Its text remains authoritative and is read as part of the whole constitutional
framework; isolated literal wording cannot be used to produce an outcome that defeats the documented
purpose of the applicable principle.

Purpose does not authorize an interpreter to disregard clear constitutional text, invent authority or
override applicable law. Where text and documented purpose cannot be reconciled, the matter follows the
official interpretation, conflict or amendment process rather than an informal purpose-based exception.

Approved governance policies, operational procedures, technical standards, AI systems and future
platforms may adapt to changes in law, technology, markets and operating conditions, but must preserve the
constitutional outcome and authority boundaries. A new implementation method does not permit a result the
Constitution forbids, and obsolete implementation wording does not prevent a conforming modern method
within delegated authority.

No person, organization, platform, AI system or governance participant may exploit drafting ambiguity,
technical form, data structure, interface design, organizational separation, contractual label or process
fragmentation to defeat constitutional protections or obtain authority that the Constitution does not
grant. Substance and real-world effect are evaluated alongside form.

Official constitutional interpretations consider both the enacted text and documented purpose of the
exact constitutional version being interpreted. Relevant evidence may include the Preamble, structure,
approved decision record, amendment rationale and related principles. Unapproved commentary, later
preference or AI-generated explanation does not become constitutional intent.

Future amendments assess compatibility with AYO's enduring mission, governance philosophy and
foundational values. A lawful amendment may change them only by explicitly identifying the intended
change, authority, reasons, consequences, effective version and immutable supersession lineage; silence or
indirect drafting cannot do so.

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

### AYO Foundational Constitution milestone

Following comprehensive constitutional review, the CTO recommends that AYO's foundational constitutional
architecture be recognized as enterprise-complete. This Constitution now establishes the enduring
governance, authority, accountability, interpretation, equality, stability, intent and supremacy principles
upon which AYO operates.

This is a completion and stability milestone, not a freeze, repeal, exception or transfer of authority.
Future constitutional amendments remain available through this Article when extraordinary circumstances
justify constitutional change. Consistent with Constitutional Stability, amendments are expected to be
exceptional rather than routine.

Ordinary evolution proceeds through the appropriate approved layer:

- Governance Policies;
- Operational Procedures;
- Technical Standards;
- Platform Architectures;
- Product Design; and
- Software Implementation.

Every lower layer remains subject to Constitutional Supremacy, Interpretation, Equality, Stability and
Intent. This milestone does not itself approve any policy, architecture, product, implementation, runtime,
migration, deployment or production activation.

**Milestone status:** recorded on CTO recommendation and awaiting CTO and Founder & CEO final constitutional
sign-off.

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
