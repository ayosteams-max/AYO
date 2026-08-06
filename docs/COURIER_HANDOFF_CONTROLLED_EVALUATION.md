# Controlled Courier Handoff Evaluation Pack

Status: **PROPOSED — PRE-PRODUCTION evaluation protocol only**
Study status: **Not started; no participants, observations, or results exist.**

## Purpose and authority boundary

This pack defines one future supervised formative evaluation of AYO's read-only courier handoff status experience with approximately 8–12 consenting adult courier participants. It tests comprehension, recovery discoverability, and English/Amharic wording using synthetic evidence. It does not recruit participants, approve compensation, collect data, or claim findings.

The server remains authoritative for assignment, Pickup, Custody, freshness, and access. Refresh is read recovery only. Future AYO intelligence may explain verified evidence, clarify stale or conflicting information, recommend an approved recovery category, improve non-critical wording, or prepare human handoff. It must never create authority or lifecycle state, infer completion, fabricate freshness or findings, replace native-language review, or make safety, legal, identity, financial, or physical-world decisions.

## Evaluation objectives

The facilitator must test whether the participant understands that:

1. "Pickup work is current" means the current pickup is assigned to them.
2. "Travelling to the merchant" does not mean goods were received.
3. "At the merchant" does not mean handoff completed.
4. "Waiting for merchant" does not mean possession.
5. "Ready for handoff" does not mean custody transferred.
6. "Handoff in progress" does not mean completion.
7. "Pickup confirmed" requires authoritative confirmation.
8. "This pickup is no longer current" means the active pickup is not continuing.
9. "Information may be out of date" means the evidence may no longer be current.
10. Unavailable means current status could not be obtained.
11. Malformed or conflicting information must not be trusted.
12. Refresh checks status; it is not an operational command.
13. Return to operating areas leaves the current presentation.
14. Account and Sign out do not resolve handoff status.
15. Loss of assignment authority removes the courier status and locator.

## Synthetic scenario matrix

Use a PRE-PRODUCTION build with synthetic records only. Never show real people, businesses, orders, places, routes, payments, or identifiers. Use the exact approved user-facing copy in the build; do not expose internal terms to participants.

For every row ask: **"Tell me in your own words what is happening. What has definitely happened? What has not happened yet? What would you do next? Would you trust this information right now? Why?"** Ask **"Does this mean you have received the order?"** where possession could be misunderstood.

| Scenario | Synthetic setup and exact visible state | Expected understanding | Acceptable recovery | Dangerous misunderstanding | Facilitator stop condition |
|---|---|---|---|---|---|
| Pickup current | Authorized current pickup; **Pickup work is current** | Assigned work exists; travel, arrival, receipt, and handoff are not proven | Refresh or remain on status | Believes goods were received or pickup completed | Treats assignment as possession or completion |
| Travelling | Current assignment; **Travelling to the merchant** | Courier is travelling; no arrival or receipt is proven | Follow approved offline process; Refresh only to re-check | Claims arrival or possession | Would act as though goods were received |
| At merchant | Current assignment; **At the merchant** | Arrival is shown; handoff and possession are not proven | Wait for authoritative evidence; Refresh | Claims handoff completed | Treats arrival as transfer |
| Waiting for merchant | Current Pickup/Custody evidence; **Waiting for merchant** | Merchant-side preparation/evidence remains; courier has no possession | Wait or Refresh | Claims possession or merchant release | Would leave with goods based only on this screen |
| Ready for handoff | Sealed/ready evidence; **Ready for handoff** | Handoff may proceed through the approved in-person process; transfer is not complete | Follow approved in-person process or Refresh | Claims custody already transferred | Treats readiness as possession |
| Handoff in progress | Verified/released intermediate evidence; **Handoff in progress** | Confirmation is underway; completion is not yet proven | Wait or Refresh | Claims completion | Would proceed as if pickup were confirmed |
| Pickup confirmed | Authoritative accepted evidence; **Pickup confirmed** | Handoff confirmation exists; no unrelated delivery/payment fact is implied | Return to areas if appropriate | Infers payment, delivery completion, or other authority | Extends confirmation beyond the displayed handoff fact |
| Pickup ended | Authorized terminal projection; **This pickup is no longer current** | This pickup should not continue as active work | Return to operating areas | Continues the pickup or assumes a hidden reason | Attempts to continue operational work |
| Stale evidence | Prior status retained with **Information may be out of date** | Status is historical and not freshly confirmed | Refresh or return to areas | Treats it as definitely current | Persists in treating stale evidence as authority |
| Unavailable | Initial/read failure; **Unable to confirm current status** | Current status is unknown | Refresh or return to areas | Guesses a lifecycle state | Would take physical action based on a guess |
| Malformed evidence | Contract validation failure; **AYO could not safely read this status.** | Evidence is invalid and must not be trusted | Refresh or return to areas | Chooses a likely state from context | Attempts operational action from invalid evidence |
| Conflicting evidence | Valid sources disagree; **Current handoff information does not agree.** | No combined progression can be trusted | Refresh or return to areas | Selects the more convenient status | Persists in resolving the conflict personally |
| Refresh succeeds | Stale/unavailable state becomes fresh after Refresh | Refresh re-read evidence and the new full state replaces the old one | Use only the recovered fresh presentation | Believes Refresh changed domain state | Describes Refresh as completing or advancing handoff |
| Refresh fails | Prior state remains stale or first load stays unavailable | Refresh did not confirm current evidence | Retry later or return to areas | Treats the previous status as freshly confirmed | Would act on failed recovery |
| Assignment removed between reads | First synthetic read succeeds; second returns no-longer-current; courier status disappears | Authority disappeared; old evidence and locator must not be retained | Use another returned area or empty shell | Continues from remembered status | Attempts to recover or reuse the removed pickup |
| Another area available | Courier context disappears; shell selects another authorized area | Navigation changed because courier access ended; it did not complete the pickup | Use the independently authorized area | Treats navigation as lifecycle completion | Claims the other area preserves courier authority |
| No area available | Courier context disappears; **No available area** is shown | No operating area is currently authorized | Account or Sign out; facilitator-provided human handoff | Invents access or repeatedly searches for hidden work | Attempts bypass or believes a real assignment still exists |

Stop the individual scenario whenever its row's stop condition occurs. Apply the session-wide stop rules below as well.

## Comprehension scoring

Score teach-back manually; taps and screen views are not comprehension evidence.

- **Correct:** accurately states what is proven, what is not proven, freshness, and a safe next step.
- **Partially correct:** core state is understood but one non-safety detail is missing; no authority, possession, or completion is overstated.
- **Incorrect:** material meaning or recovery is wrong without immediate physical-world risk.
- **Unsafe misunderstanding:** overstates authority, freshness, possession, completion, or recommends unsafe operational action.
- **Facilitator intervention required:** yes/no; mark yes whenever the facilitator must stop, correct, or protect the participant.

The facilitator must record the category, not a verbatim answer or personal narrative.

## Recovery evaluation

For Refresh, Return to operating areas, Account, and Sign out, record only one result:

- found without help;
- found after a neutral prompt;
- selected wrong control;
- did not find; or
- unsafe interpretation.

A neutral prompt may be: **"Show me where you would go next."** Do not record navigation trails, touch coordinates, timings, or detailed behavior. Account and Sign out are navigation/session controls, not status-resolution commands.

## Language review boundary

Keep six evidence types separate:

1. **Key equivalence:** automated comparison may verify matching resource keys.
2. **Deterministic semantic equivalence:** reviewers verify that status and safety boundaries match.
3. **Rendering correctness:** device review checks clipping, ordering, scaling, and glyph display.
4. **Natural wording:** requires a qualified native reviewer.
5. **Cultural appropriateness:** requires native and operational review.
6. **Participant comprehension:** comes only from supervised teach-back.

English wording requires editorial and operational review. Amharic naturalness, respectful tone, ambiguity, cultural suitability, and comprehension interpretation require at least one qualified native Amharic reviewer. Disputed Amharic wording must receive that review before any production localization change. This protocol neither changes nor invents translations; an exact localization defect requires a separate CTO-reviewed correction.

## Participant, consent, and compensation boundaries

Future participants must be consenting adults able to understand the test language. Before the session, state that:

- the app and scenarios are PRE-PRODUCTION and synthetic;
- no real delivery, work allocation, payment, earnings, eligibility, or preferential access is involved;
- participation is voluntary and may stop at any time without consequence;
- performance is not an employment or platform-eligibility assessment;
- no recording is permitted.

Do not recruit through pressure, dependency, or misleading work promises. Recruitment and compensation require separate approval. Compensation must not depend on correct answers.

## Privacy and manual evidence

Never collect: name, phone, email, government ID, courier account ID, pickup/order/merchant/assignment/session identifiers, tokens, device fingerprints, IP addresses, exact location, route, exact timestamps, screen/audio/video recordings, support conversations, raw payloads, free-form personal histories, or verbatim quotations without separately approved consent.

Permitted worksheet fields are limited to:

- temporary session label `P01`–`P12`;
- scenario category;
- language category (`English` or `Amharic`);
- comprehension result;
- recovery-discovery result;
- bounded unsafe-misunderstanding category;
- facilitator intervention required (`yes` or `no`);
- bounded wording-issue category;
- paraphrased, de-identified issue summary; and
- aggregate count.

The manual worksheet must remain local and access-limited. Do not commit completed worksheets, participant-level results, raw notes, or quotations to Git. Temporary labels are session-local, must not link across sessions or systems, and must be destroyed with participant-level notes immediately after aggregate results are quality-checked.

Paraphrases must remove personal and operational detail. Do not combine evaluation data with identity, operational, support, audit, device, or location data.

## Small-cohort protection

- Suppress or combine any reported category with fewer than three observations.
- Do not publish language-by-rare-status combinations with counts below three.
- Do not compare, rank, profile, or longitudinally link participants.
- Report English and Amharic separately only when the resulting groups remain meaningful and suppression-safe.
- Make no statistical-significance or population-wide comprehension claim from 8–12 participants.

## Formative success criteria

The pack may advance to a leadership review only when all are true:

- zero unsafe misunderstanding of authoritative confirmation or completion;
- zero interpretation that readiness means possession;
- zero interpretation that stale evidence is definitely current;
- participants distinguish Refresh from an operational command;
- participants identify when unavailable, malformed, or conflicting evidence cannot be trusted;
- recovery controls are discoverable without misleading participants;
- Amharic wording passes native review; and
- zero privacy or consent violation occurs.

These conservative criteria are formative gates, not scientific proof of population-wide comprehension. Any unsafe misunderstanding blocks progression and requires wording/recovery review followed by limited re-evaluation.

## Stop conditions

Stop the scenario or session immediately if:

- the participant believes a real order, delivery, work offer, or payment is involved;
- personal or operational information is disclosed;
- the participant becomes distressed or withdraws consent;
- unsafe misunderstanding persists;
- an identifier, real location, real operational data, or production configuration appears;
- behavior differs from the approved deterministic scenario;
- recording occurs unexpectedly; or
- the facilitator cannot provide the approved human escalation contact.

Do not retain information disclosed after a stop; remove it from the worksheet before continuing any aggregate review.

## Required gates before evaluation begins

None of these approvals is recorded by this document. Evaluation may begin only after:

1. Founder/CEO approval is explicitly recorded by Ibrahim Hambentu Shibiru, Founder & CEO.
2. The tested build is verified as PRE-PRODUCTION.
3. Every synthetic scenario is verified against deterministic behavior.
4. No production or participant operational data is present.
5. Facilitator instructions are reviewed.
6. English wording is reviewed.
7. Amharic wording receives qualified native review.
8. Privacy and consent boundaries are accepted by the accountable reviewer.
9. Recruitment and compensation are separately approved.
10. A trained human facilitator and escalation contact are available.
11. A practical destruction process exists for participant-level notes and temporary labels.
12. An accountable owner is assigned for the suppression-safe aggregate report.

## Aggregate result classification

After participant notes are destroyed, the suppression-safe aggregate report must select one or more applicable categories:

- **READY FOR WORDING REFINEMENT**
- **READY FOR RECOVERY REFINEMENT**
- **READY FOR LIMITED RE-EVALUATION**
- **BLOCKED BY UNSAFE STATUS MISUNDERSTANDING**
- **BLOCKED BY AMHARIC LANGUAGE QUALITY**
- **BLOCKED BY PRIVACY OR PROCESS FAILURE**
- **READY TO CONSIDER NARROW AGGREGATE COUNTERS**

The last category authorizes only a separate architecture/privacy review. It does not authorize telemetry, persistence, analytics, or production activation.

## Explicit exclusions

This evaluation does not validate or authorize production readiness, driver onboarding, real deliveries, support staffing, payments, scanner behavior, routing, tracking, safety response, legal compliance, telemetry, analytics, AI explanations, model integration, operational commands, or production activation. It creates no application behavior, participant evidence, product finding, support case, or authority.
