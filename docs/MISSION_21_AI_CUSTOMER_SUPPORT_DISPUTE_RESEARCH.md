# Mission 21 — AI Customer Support, Dispute and Resolution Engine

Date: 2026-07-16  
Status: **Research direction approved by CTO and CEO on 2026-07-16 for future
architecture work. Architecture design and implementation remain unauthorized; no
migration, dependency, provider, push or activation is authorized.**

## 1. Mission boundary

Mission 21 researches an AI-first support experience that acknowledges immediately,
uses authenticated AYO evidence, resolves routine low-risk cases in seconds, and hands
off consequential or uncertain cases without making the user repeat their story.

It preserves the existing Mission 9 support foundation and deferred Customer Recovery
and AI Support boundaries. AI does not become authority for ride state, safety findings,
identity, fraud sanctions, pricing, ledger postings, refunds, payouts, account access or
legal disclosure. It may understand language, classify intent, summarize, retrieve an
authorized evidence view, explain an already-authorized rule and propose a typed action.
Only deterministic versioned policy and authorized tools may decide or execute an
outcome.

“Escalate only when AI confidence is insufficient” is therefore refined to comply with
Constitution Articles 2, 3, 6 and 8: uncertainty triggers escalation, but high-risk
categories also require escalation by policy regardless of AI confidence. Model
confidence never expands authority.

## 2. Problem, beneficiaries and success measures

### Problem

Generic chatbots can answer quickly but hallucinate policy, expose private evidence,
misclassify emergencies, unfairly resolve disputes, or trap users in automation. Purely
human support is safer for complex cases but slow and expensive for routine questions.
Riders and drivers need fast answers without sacrificing appeal, earnings, safety or
financial integrity.

### Beneficiaries

- Riders receive immediate, contextual explanations and simple recovery paths.
- Drivers receive equal access to evidence, report transparency and protection from
  false or platform-caused outcomes.
- Safety, fraud, identity, finance and support specialists receive structured cases,
  not raw chatbot transcripts requiring complete reinvestigation.
- AYO reduces repetitive work while retaining accountable human control.

### Proposed measures; targets require baseline and approval

- acknowledgement latency, time to verified resolution and time to human ownership;
- first-contact resolution for approved green workflows;
- correct escalation, false-resolution and reopen/repeat-contact rates;
- rider/driver appeal and overturn rates, split by issue, language and responsibility;
- safety under-escalation rate, with zero tolerance for known emergency routing defects;
- financial invariant violations and unauthorized-tool attempts, target zero;
- Amharic/English intent, explanation and handoff quality, including code-switching;
- privacy leakage, prohibited-data access and unsupported-claim rate, target zero;
- human workload displaced versus new review burden;
- model/provider latency, outage, token cost and deterministic fallback success.

Containment rate alone is not success: an AI that blocks access to a person or closes
cases incorrectly fails the mission.

## 3. Repository truth and preserved decisions

- Mission 9 already implements a PostgreSQL support-case foundation with append-only
  events/messages/AI evidence, explicit green/yellow/red action classes, authorization,
  optimistic concurrency and transactional audits.
- AI permissions are deliberately narrower than human support permissions. Current AI
  policy forbids arbitrary actions and provides no provider integration.
- The future Customer Recovery engine may recommend recovery but cannot execute money.
  The future AI Support engine may consume authorized projections and call only approved
  tools. Serious, ambiguous, financial, safety, legal, identity, fraud and vulnerable-
  person cases require human escalation.
- Mission 20 arrival/wait evidence and landmark evidence do not prove fault. Pricing
  remains fare/fee authority; immutable ledger postings remain financial authority.
- Authentication recovery, emergency operations, retention, provider/model choice and
  Amharic voice quality remain open approval or Ethiopian verification gates.

## 4. 2025–2026 platform research

Public platform material reveals product practices, not internal algorithms or proven
quality. AYO must validate every recommendation locally.

1. Uber's June 2025 generative-AI notice describes real-time support answers for earners,
   disclosure that a feature uses GenAI, monitored rollout and feedback collection. It
   does not publish adjudication accuracy or authorize copying its model approach.
   Accessed 2026-07-16:
   https://www.uber.com/legal/en/document/?country=united-states&lang=en%29&name=generative-ai-features-at-uber
2. Airbnb's October 2025 release expands authenticated AI support across languages and
   gives contextual answers and interactive cards for common reservation actions. This
   supports authenticated context and constrained actions, not autonomous dispute or
   safety decisions. Accessed 2026-07-16:
   https://news.airbnb.com/product-releases/airbnb-2025-winter-release/
3. Uber's 2025 driver update emphasizes report transparency, allowing drivers to provide
   their side, limiting restrictions where possible, and excluding some externally
   caused delivery cancellations from ratings. This supports bilateral evidence and
   proportional action. Accessed 2026-07-16:
   https://www.uber.com/us/en/newsroom/onlyonuber25/
4. Uber's August 2025 Toronto incident statement records that rigid serious-incident
   routing delayed contact for over an hour and that exceptional cases may need trained
   frontline intervention. This supports immediate specialist escalation, rehearsed
   emergency exceptions and measured handoff latency. Accessed 2026-07-16:
   https://www.uber.com/ca/en/newsroom/statement-child-vehicle-march-2025/
5. Uber's current lost-item flows use trip-scoped authenticated reporting, identity
   verification for lost-phone/account-inaccessible cases, anonymized contact and human
   follow-up when direct contact fails. Accessed 2026-07-16:
   https://help.uber.com/en/riders/article/i-left-my-phone-in-a-vehicle?nodeId=91b7b0e2-e1b9-43a1-b10d3411c74bd
6. Uber's current identity help states that identity data is secured, purpose-limited,
   withheld from drivers, retained for a defined period and supported by a mistake/
   appeal path. Accessed 2026-07-16:
   https://help.uber.com/en/riders/article/verifying-my-identity?nodeId=7de4956c-22f5-4555-856d-887d9e180a94
7. Uber's current India support page separates on-trip safety/SOS, trip-scoped
   self-service, 24/7 first-line support and a grievance escalation tier; it also uses
   call anonymization. Published response windows are jurisdiction-specific evidence,
   not proposed AYO promises. Accessed 2026-07-16:
   https://help.uber.com/riders/article/india-customer-support?nodeId=9de54d31-c25e-4020-8873-62a3165b2bfd

The searches did not find sufficiently detailed 2025–2026 primary disclosures from
DoorDash, Lyft or Instacart describing internal AI dispute thresholds. Absence of public
detail is a source limitation, not evidence that those platforms lack automation.

## 5. Ethiopian operating research

The Ethiopian Ministry of Justice publishes Personal Data Protection Proclamation No.
1321/2024, establishing the need for a national personal-data protection framework and
effective remedies. Exact lawful bases, automated-decision rights, sensitive-data
treatment, cross-border processing, retention and regulator procedures require
qualified Ethiopian counsel before design approval or launch. Source accessed
2026-07-16: https://justice.gov.et/am/law/personal-data-protection-proclamation/

World Bank reporting published in June 2025 estimates internet access at 19% of the
population by the end of 2024 despite strong recent growth. This supports low-bandwidth,
interrupted-session, call/SMS and human-assisted fallbacks; it does not establish AYO's
launch-area network profile. Source accessed 2026-07-16:
https://www.worldbank.org/en/results/2025/06/30/empowering-ethiopians-by-laying-the-digital-foundations-for-afe-economic-growth

Required local verification:

- Amharic and English are first-release support languages; Afaan Oromo and other launch-
  area languages require leadership scope plus measured native-speaker evaluation.
- Amharic script, transliteration, code-switching, speech recognition, text-to-speech,
  regional vocabulary and respectful tone require local evaluators. Translation
  confidence cannot substitute for case confidence.
- Cash trips require evidence that distinguishes quote/fare, amount tendered, change,
  driver report and immutable ledger state. AI cannot infer payment from chat text.
- Support must survive low data availability, shared/changed phones, lost SIMs, power
  interruptions and delayed notifications without weakening account recovery.
- Ethiopian police, ambulance, airport, transport, privacy, consumer, labour and legal
  escalation contacts, hours and handoff obligations must be verified and rehearsed.

## 6. Recommended operating model

### Deterministic authority with AI-first interaction

Use the existing Support module in the modular monolith. A provider-neutral language
adapter converts untrusted user content into a typed proposed intent and draft response.
A deterministic case orchestrator independently validates identity, authorization,
case state, evidence freshness, policy version, action class and required approvals.
Approved read tools return minimum, role-safe projections from owning domains. Approved
write tools are narrow, idempotent and policy-bound. The model never receives database,
network or generic tool access.

Every final decision is reproducible from a versioned policy and evidence snapshot.
Generative wording may vary, so it is not the decision: customer-visible claims must be
grounded in structured reason/explanation components, and the exact delivered response
is retained under an approved privacy schedule.

### Confidence and authority bands

Numeric thresholds below are research proposals for shadow evaluation, not approved
launch values:

- **Green:** calibrated case confidence at least 9,500 basis points, complete fresh
  evidence, one unambiguous low-risk intent and an approved deterministic action. AI may
  explain or execute only the allow-listed routine tool.
- **Yellow:** 7,000–9,499 basis points, conflicting/missing evidence, repeated complaint,
  contested responsibility or action requiring judgment. AI acknowledges, gathers only
  necessary facts, preserves state and hands off.
- **Red:** safety, emergency, vulnerable person, identity/account recovery, suspected
  fraud/collusion, legal request, irreversible restriction, payout or material financial
  dispute. Immediate specialist routing regardless of confidence.
- **Unavailable:** model/provider outage or unsupported language. Deterministic menus,
  case creation and human routing remain available.

Confidence is calibrated per intent and language. A self-reported model probability is
not sufficient. Thresholds may only be approved from representative shadow data with
false-resolution, under-escalation, bias, privacy, latency and cost results.

### Human handoff contract

Handoff carries case/participant roles, authenticated context, urgency, language,
structured issue, policy/evidence versions, actions attempted, exact claims made,
unresolved questions and minimum evidence references. It never exposes hidden reasoning
or unnecessary raw identity, location, payment or safety material. Users can request a
person; abuse may be rate-limited but not used to suppress emergency or appeal access.

## 7. Category responsibility matrix

Response times are proposed service objectives measured from receipt. “AI resolve”
means a deterministic approved workflow, never free-form model authority.

| Category | AI responsibility | Human responsibility and escalation | Confidence / proposed response | Audit and privacy | Abuse prevention |
|---|---|---|---|---|---|
| AI chat support | Authenticate context, classify, answer grounded FAQs, open/update case, summarize | Review yellow/red, unsupported language, repeated failure or user-requested handoff | Green ≥9,500 bps: acknowledge <2s, routine verified answer <10s; otherwise ownership target <5m | Model/prompt-policy version, retrieved views, citations, response and tool result; no unrestricted retrieval | Input bounds, prompt-injection isolation, tool allow-list, per-identity/device rate limits |
| Driver support | Explain offer/trip/earnings status from authorized records; collect driver evidence | Decide deactivation, livelihood impact, payout, safety, repeated report or contested fault | Routine status green; any restriction/earnings dispute yellow/red; acknowledge <2s, urgent earning blockage ownership <15m | Equal evidence access, policy version and report provenance; protect rider identity/location | Duplicate linkage, collusion signals to fraud specialists, evidence integrity and appeal |
| Rider support | Explain ride state, receipt components and verified service events | Decide contested fault, safety, identity, money or policy exceptions | Routine green <10s; dispute human ownership <30m proposed | Trip-scoped views; do not expose driver private contact, internal risk or exact post-trip location | Ownership checks, bounded claims, duplicate-case linking without hidden reputation |
| Safety incidents | Recognize safety language, acknowledge, preserve case, display verified emergency options | Trained safety team owns triage, contact, safeguarding and platform restrictions | Always red; emergency routing intent <2s, specialist acknowledgement target <60s subject to staffed capability | Restricted safety evidence, legal hold and access logs; never expose report to alleged party automatically | Cannot rate-limit emergency access; detect spam separately; malicious-report action requires review |
| Lost property | Identify trip/item class, initiate anonymized contact and status workflow | Handle unreachable party, dangerous/illegal items, identity uncertainty and disputes | Ordinary authenticated case green; phone/ID/medicine or no contact yellow/red; <10s initiation, human update target <24h | Consent and masked contact, trip reference, contact attempts; no direct number by default | Trip ownership, contact caps, harassment block, no guarantee item exists |
| Cancellation disputes | Explain recorded initiator, timing and approved policy; assemble evidence | Resolve conflicting evidence, appeal or any financial correction | Green only with complete authoritative evidence; otherwise yellow; <10s explanation, ownership <30m | Ride/policy versions, external-failure and responsibility evidence; no raw location trail | Idempotent claim, repeat linkage, symmetric rider/driver statements, no hidden score |
| Waiting-fee disputes | Explain Mission 20 arrival/wait policy snapshot and suppression evidence | Review low confidence, GPS/pickup/notification/platform/airport/accessibility conflict; authorize recovery recommendation only if approved | Green explanation only when evidence complete; all contested charge outcomes yellow; <10s explanation, ownership <30m | Arrival confidence, timer, pickup, notification and policy references; minimum derived location facts | Fake-wait and false-presence evidence remain advisory; no AI fault inference |
| Fare disputes | Explain quote/final-fare components and payment status | Pricing/finance reviews wrong fare, cash conflict, refund, chargeback or ledger correction | Explanation green; any value change red; <10s explanation, finance ownership <4h proposed | Quote/pricing/ledger versions and immutable posting references; no credentials | Duplicate/refund/collusion checks, idempotent recovery, compensating entries only |
| Airport pickup disputes | Explain approved zone, reservation/ride status, arrival and notification evidence | Resolve airport rules, access failure, Premium promise, external disruption or money | Routine directions green; operational/financial contest yellow/red; live-trip ownership <5m | Airport-context freshness and authority source; minimize flight/passenger data | Require authoritative zone/version, detect repeated claims, protect external disruption |
| Identity verification | Explain required step/status and collect no document in ordinary chat | Identity specialists handle document/selfie review, mismatch, bias appeal and account restriction | Always yellow/red for outcome; immediate acknowledgement, specialist ownership <15m | Dedicated identity boundary, encrypted references, strict access/retention; model sees no raw document unless separately approved | Liveness/vendor/replay controls outside support; anti-enumeration and attempt bounds |
| Account recovery | Provide safe generic guidance and create recovery session | Trusted recovery service/human verifies ownership and revokes/restores sessions | Always red; acknowledge <2s, specialist ownership <15m | No disclosure whether account exists; recovery/audit events separated from chat | Step-up, refresh/session revocation, replay resistance, device/IP signals privacy-minimized |
| Fraud detection | Detect typed anomaly indicators and route evidence; never accuse | Fraud specialists investigate collusion, sanctions, appeals and legal implications | Always red for adverse action; urgent route <10s | Restricted features/reasons, model/rule version and evidence lineage; no protected traits | Adversarial testing, graph/velocity checks only if separately approved, insider controls |
| Emergency escalation | Identify emergency intent, show verified local emergency instructions and preserve context | Human safety operations and verified emergency services own response | Always red; route/display target <2s, live specialist target <60s only if operationally staffed | Minimal live trip/contact/location sharing with explicit lawful authority and access log | Emergency path bypasses normal throttles; false-report review occurs after safety response |
| Human handoff | Produce grounded summary and continue calm status updates | Human accepts ownership, verifies summary and records decision/reason | Yellow/red or user request; warm handoff <5m routine, safety as above | Exact handoff, queue, ownership, edits and decision audit; no hidden chain-of-thought | Queue rate controls cannot block safety, identity appeal or legal rights |
| Multi-language support | Detect requested language, translate approved content and flag uncertainty | Native-language reviewer handles low confidence, safety, legal and material dispute | Language confidence assessed separately; unsupported/low confidence yellow; acknowledgement <2s | Source and delivered text, locale/model/glossary versions; approved retention | Prompt-injection and abusive content controls must not erase underlying complaint |

## 8. Options comparison

### Option A — FAQ bot plus human ticketing

- **Pros/cost:** simplest, lowest build and provider cost; easy deterministic fallback.
- **Cons/customer impact:** little contextual resolution, repetitive questions, high
  handoff load and weak “seconds” objective.
- **Scale/maintenance/security:** scales easily and minimizes data, but does not solve
  disputes or fragmented evidence. Suitable only as fallback.

### Option B — constrained AI orchestration over deterministic support policy
(recommended)

- **Pros:** immediate natural-language access, authenticated context, explainable
  outcomes, narrow tools, strong human gates, provider portability and compatibility
  with the current support foundation.
- **Cons:** requires evaluation data, policy ownership, staffed specialist queues,
  multilingual quality work and disciplined tool/evidence contracts.
- **Cost:** medium build and operations; model costs bounded through intent routing,
  structured views, caching and deterministic FAQ fallback.
- **Scale/maintenance:** partition cases by case ID, bounded event histories, async human
  queues and stateless model adapters; remain a modular-monolith module until measured
  scale/isolation evidence supports extraction.
- **Ethiopian fit:** supports weak-network recovery, cash evidence and language-specific
  evaluation without making voice or a single provider mandatory.

### Option C — autonomous generative agent with broad tools

- **Pros:** potentially high apparent containment and flexible dialogue.
- **Cons:** nondeterministic authority, prompt injection, hallucinated policy, privacy
  overreach, unsafe emergency/identity/financial actions and difficult appeals.
- **Cost/lock-in:** highest evaluation, incident and governance cost; broad tool schemas
  increase provider and security coupling.
- **Decision:** reject. It conflicts with the Constitution and stated deterministic,
  explainable and auditable requirement.

## 9. Recommendation, simpler alternative and deferrals

Approve Option B for architecture design, initially in shadow/agent-assist mode against
synthetic and reviewed historical-like cases. Activate one or two genuinely low-risk
green workflows only after per-language thresholds pass; expand workflow by workflow.
The simplest FAQ bot remains the outage and unsupported-language fallback.

Deliberately defer model/channel/provider selection, voice, telephony, vector databases,
brokers, autonomous refunds/credits, account recovery authority, fraud sanctions,
emergency promises and final SLOs. Each requires evidence, policy ownership and the
support-provider gate. Do not add infrastructure merely to imitate competitors.

## 10. Risks and mitigations for architecture review

- **Hallucination/incorrect closure:** deterministic evidence and action gate; grounded
  public explanation; reopen and human appeal.
- **Safety under-escalation:** red-category rules independent of model confidence;
  keyword/rule fallback; staffed drills and failure injection.
- **Prompt injection/tool abuse:** treat all content as untrusted; schema validation,
  least-privilege service identity and no generic tools.
- **Bias and language disparity:** per-language/category evaluation, native reviewers,
  minimum sample gates and rollback when disparity exceeds approved bounds.
- **Privacy overcollection:** purpose-scoped projections, field allow-lists, retention
  classes, restricted safety/identity/fraud stores and no training reuse without
  separate lawful approval.
- **False fraud/identity action:** AI routes only; specialists and owning domains decide;
  provide notice and appeal where legally/operationally appropriate.
- **Automation abuse:** bounded attempts, duplicate linkage and anomaly routing without
  silently penalizing legitimate repeat reporters.
- **Provider outage/cost spike:** provider-neutral adapter, deterministic self-service,
  budget/latency circuit breakers and human queue fallback.
- **Human queue overload:** capacity planning and graceful status updates; automation
  cannot fabricate resolution to meet latency targets.

## 11. Architecture questions requiring CTO/CEO/legal/operations decisions

1. CTO: approve deterministic orchestrator versus autonomous agent, exact trust
   boundaries, evidence projections, tool classes and shadow evaluation design.
2. CEO/Support: approve which initial green workflows may resolve automatically and
   which user-requested handoffs AYO promises.
3. CEO/Operations: approve staffed hours and truthful response objectives for routine,
   urgent, safety and emergency cases.
4. Legal/Privacy: approve lawful basis, notices, automated-decision safeguards,
   retention, transcript/model-feedback reuse, cross-border/model processing, legal
   holds and data-subject access/deletion boundaries.
5. Safety/Legal: verify Ethiopian emergency organizations, escalation contacts, evidence
   sharing, response limitations and mandatory reporting.
6. Identity/Security: approve recovery proof, step-up, session revocation and human
   override; AI receives no recovery authority.
7. Finance/Leadership: approve refund/credit/cash-dispute authority and limits in a
   separate financial decision; Mission 21 cannot move value.
8. Product/Language: approve launch languages, native evaluator panels, accessibility,
   low-connectivity journeys and minimum quality thresholds.
9. CTO/CEO: approve a separate provider comparison only after workflows, evaluation set,
   volume, latency, privacy and cost requirements are known.

## 12. Survivability and workflow stop gate

The recommendation has a credible 10-million-user path through bounded case streams,
partitionable work queues, stateless provider adapters and independently scalable human
queues. Provider outage cannot remove deterministic help or case creation. Explicit
contracts, policies and evidence snapshots are testable, monitorable, replaceable and
understandable without premature microservices. Its customer benefit depends on
verified accuracy and staffed escalation, not claimed AI capability.

| Workflow step | Evidence | Status |
|---|---|---|
| 1 | Repository, platform and Ethiopian research in this document | Complete |
| 2 | Options, recommendation, category matrix, risks and decisions requested | Complete |
| 3 | CTO/CEO research-direction approval | Complete 2026-07-16 |
| 4–10 | Architecture through completion | Not authorized; stop here |
