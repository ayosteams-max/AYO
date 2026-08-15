# AYO Booking Consent Approval Pack Architecture

Status: **PROPOSED / PRE-PRODUCTION**

Research basis reviewed: **2026-08-15**

Approval state: **No external or human approval is recorded**

## 1. Purpose

This record defines how AYO will collect, verify, govern, expire and approve the human and external evidence required before Booking consent-document implementation or activation. It creates a fail-closed approval structure; it contains no policy prose and grants no implementation, deployment or production authority.

Each governed pack must answer what decision is required, who may answer it, what evidence supports the answer, whether the answer is written and attributable, which stage it unblocks, when it expires or requires review, which red line prevents bypass, and whether Founder approval actually occurred.

## 2. Existing architecture truth

The current backend owns V1 Booking consent metadata and binds its policy version, document identity, document-level hash, effective interval and acknowledgment requirement into preview evidence. Backend confirmation and rider-scoped recovery exist. Mobile is authenticated place-search and preview-only, strictly parses opaque V1 metadata and stops at `confirmation_locked`; it has no confirmation or recovery transport, parser, capability or state. No human-readable policy prose, active production registry, document-delivery endpoint, consent UI, durable mobile storage, normal provider composition, deployment or production activation exists.

`AYO_BOOKING_CONSENT_DOCUMENT_DELIVERY_CONTRACT_ARCHITECTURE.md` proposes a disjoint authenticated V2 rendition-delivery contract. It remains documentation, not executable authority.

## 3. Research basis and limitations

The provisional basis is the AYO assessment completed on 2026-08-15. Primary sources take priority: Ethiopian legislation and official registers; regulator and ministry publications; authoritative treaty records; W3C standards; official Apple and Google policies; and official Australian sources only for conditional Australian obligations.

- Electronic Transaction Proclamation No. 1205/2020 and Electronic Signature Proclamation No. 1072/2018 are binding Ethiopian legislation, but applicability and authoritative-language interpretation require Ethiopian counsel.
- Personal Data Protection Proclamation No. 1321/2024 is binding Ethiopian legislation; its application to each proposed evidence class requires privacy review.
- Exact current ride-hailing licensing and disclosure requirements remain unresolved.
- Ethiopia's CRPD ratification does not by itself establish every private-mobile-application obligation.
- WCAG 2.2 is a W3C Recommendation. WCAG2Mobile is informative draft guidance, not a standard, final W3C Recommendation or Ethiopian law.
- Apple and Google rules are platform policies, not Ethiopian law, and are time-sensitive.
- Unofficial translations never override authoritative Ethiopian-language texts.

An authenticated electronic acknowledgment may potentially satisfy applicable requirements, but its sufficiency depends on the governing instrument, attribution, affirmative action, disclosure, record integrity, accessibility, retention and any required signature form. No checkbox, button, tap or similar interaction is automatically legally sufficient. Only the accountable Ethiopian legal or regulatory authority may determine the applicable result; this record makes no validity or compliance claim.

This architecture is not legal advice and makes no compliance claim. A broken, unavailable, ambiguous or superseded source remains unresolved.

Provisional source register, accessed 2026-08-15:

| Source | Authority and classification | Limitation |
|---|---|---|
| [Electronic Transaction Proclamation No. 1205/2020](https://laws.moj.gov.et/registries/view/1414/am) | FDRE; binding proclamation | Applicability and authoritative-language interpretation require Ethiopian counsel. |
| [Electronic Signature Proclamation No. 1072/2018](https://laws.moj.gov.et/registries/view/1273/am) | FDRE; binding proclamation, published 2018-02-16 | It does not establish that every Booking acknowledgment requires a certified digital signature. |
| [Personal Data Protection Proclamation No. 1321/2024](https://pdp.eca.et/pdp-proclamation) | FDRE/Ethiopian Communications Authority; binding proclamation | Lawful basis and regulatory procedure remain decision-specific. |
| [FDRE Constitution Proclamation No. 1/1995](https://www.fsc.gov.et/am-et/Home/constitution-of-the-federal-democratic-republic-of-ethiopia-proclamation-no-11995-%E1%8B%A8%E1%8A%A2%E1%89%B5%E1%8B%AE%E1%8C%B5%E1%8B%AB-%E1%8D%8C%E1%8B%B4%E1%88%AB%E1%8B%8A-%E1%8B%B2%E1%88%9E%E1%8A%AD%E1%88%AB%E1%88%B2%E1%8B%AB%E1%8B%8A-%E1%88%AA%E1%8D%90%E1%89%A5%E1%88%8A%E1%8A%AD-%E1%88%95%E1%8C%88-%E1%88%98%E1%8A%95%E1%8C%8D%E1%88%A5%E1%89%B5-%E1%8A%A0%E1%8B%8B%E1%8C%85-%E1%89%81-11987) | FDRE; binding Constitution | Language status does not independently settle private consumer-contract language requirements. |
| [Ministry of Transport and Logistics transport-law register](https://www.motl.gov.et/resource_types/transport-law-1) | Official government register | Exact current ride-hailing obligations were not resolved by the accessible index. |
| [CRPD ratification record](https://treaties.un.org/Pages/showActionDetails.aspx?clang=_en&objid=080000028029564d) | UN Treaty Collection; authoritative treaty record | Ratification does not independently determine every private-app duty. |
| [WCAG 2.2](https://www.w3.org/TR/WCAG22/) | W3C Recommendation | Proposed engineering floor, not Ethiopian law. |
| [WCAG2Mobile](https://www.w3.org/TR/wcag2mobile-22/) | W3C informative draft guidance | Not normative law or a final W3C standard. |
| [Apple App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) | Official time-sensitive platform policy | Applies according to product capability and store submission; not Ethiopian law. |
| [Google Play User Data policy](https://support.google.com/googleplay/android-developer/answer/10144311?hl=en-GB) | Official time-sensitive platform policy | Applies according to data practice and distribution; not Ethiopian law. |
| [Australian Privacy Principles Guidelines](https://www.oaic.gov.au/privacy/australian-privacy-principles/australian-privacy-principles-guidelines) | OAIC regulatory guidance | Relevant only if an Australian legal nexus is established. |

## 4. Goals

- Keep every required decision attributable, scoped, reviewable and fail closed.
- Separate legal, regulatory, product, language, accessibility, privacy, security, deployment and production authority.
- Bind every approval to exact evidence and implementation/activation gates.
- Detect expiry, conflict, tampering, scope substitution and bypass.
- Minimize personal data while preserving independent auditability.

## 5. Non-goals

This increment does not create policy wording, an active document, registry, endpoint, schema, migration, product code, tests, UI, acknowledgment, confirmation, recovery, persistence, provider integration, dependency, workflow, deployment or production configuration. It sends no question, accepts no terms and records no completed approval.

## 6. Approval domains

Each domain has an independent decision record and may not be collapsed into blanket `legal approved` status:

1. electronic transaction and assent;
2. transport/operator classification;
3. required rider disclosures;
4. consumer protection;
5. privacy lawful bases;
6. controller/processor roles;
7. registration, DPO/contact and DPIA questions;
8. cross-border data;
9. evidence retention;
10. required languages;
11. native-language rendition review;
12. accessibility;
13. app-store obligations;
14. policy rotation;
15. emergency withdrawal;
16. complaints and disputes;
17. product acceptance;
18. Security/CTO acceptance;
19. Founder approval;
20. deployment authorization; and
21. production authorization.

## 7. Evidence types, authenticity and custody

Evidence types are source records, written counsel opinions, written regulator answers or licence conditions, legal-instrument classifications, disclosure inventories, privacy/data-flow decisions, native-language rendition reviews, accessibility evaluations, product decisions, technical/security reviews, operational readiness evidence, Founder decisions, deployment authorizations and production authorizations. Meeting notes and verbal guidance may provide context but cannot independently grant approval.

Every evidence object binds a stable evidence ID; digest and algorithm; MIME/type; byte length; creation and receipt timestamps; issuing authority; submission and receipt channel; authenticity-verification method and result; signer or official identity where lawfully retained; signature/certificate verification where applicable; redaction status; confidentiality classification; storage authority; storage-location and jurisdiction classification without exposing secrets; access-control class; legal-hold state; supersession identity; exportability; and independent-audit status.

Git contains only safe governance metadata and cryptographic commitments unless a separate authorization explicitly permits more. Confidential legal opinions, regulator correspondence, personal identity documents, signatures, certificates and sensitive evidence bytes must not be committed. The authoritative evidence store is `UNRESOLVED`; GitHub, email, local disks, vendors, AI systems and mobile clients are not implicitly authoritative evidence stores. A reference, URL or email provenance alone proves neither authenticity nor authority. No storage provider or retention duration is selected here.

## 8. Decision and status model

| Status | Exact meaning |
|---|---|
| `NOT_STARTED` | No governed work or evidence exists. |
| `RESEARCHED_UNVERIFIED` | Research exists but required authority has not verified it. |
| `QUESTION_PREPARED` | A governed question is ready but has not been submitted. |
| `SUBMITTED` | Submission is evidenced; no answer or approval is inferred. |
| `ANSWER_RECEIVED_UNVERIFIED` | A response exists but provenance, scope or interpretation is not verified. |
| `VERIFIED` | Evidence and scope were verified; this is not approval unless an authorized decision separately says so. |
| `APPROVED` | The named accountable authority issued a written, attributable, in-scope approval with prerequisites satisfied. |
| `REJECTED` | The authority rejected the decision; affected stages remain blocked. |
| `EXPIRED` | Its stated date or re-review trigger has elapsed; it grants no authority. |
| `SUPERSEDED` | A newer attributable record replaces it; the prior record remains historical only. |
| `BLOCKED` | A prerequisite, conflict, red line or unavailable authority prevents progress. |

Silence, attendance, payment, submission, a successful CI run or implementation does not imply approval. Verbal guidance requires the mandated written record. AI may prepare, compare and flag evidence but cannot set a human status to `APPROVED`. Material changes invalidate affected approvals. Unknown states fail closed.

Lifecycle state and approval result are separate fields. A lifecycle-state field accepts exactly `NOT_STARTED`, `RESEARCHED_UNVERIFIED`, `QUESTION_PREPARED`, `SUBMITTED`, `ANSWER_RECEIVED_UNVERIFIED`, `VERIFIED`, `APPROVED`, `REJECTED`, `EXPIRED`, `SUPERSEDED` or `BLOCKED`; blank, malformed or any other value fails closed. A new decision version begins at `NOT_STARTED`. `NOT_APPROVED` is only the safe default for an approval or authorization result and is never a lifecycle state. No approval-result field can cause or substitute for a lifecycle transition.

Every decision binds: stable decision ID; domain; exact question; jurisdiction, market and service scope; accountable authority; named reviewer and role where legally permitted; source/evidence IDs; version; received, effective and re-review dates; exact decision; conditions; reservations; implementation and activation stages unblocked; status; verification actor; and immutable audit timestamp. Credentials, private identity documents and unnecessary personal data are prohibited.

The universal decision identity is exact and includes jurisdiction and sub-jurisdiction; market; service; closed policy scope; instrument type and ID; instrument version; canonical locale; source and target rendition identities and hashes where applicable; format; exact lifecycle stage; evidence-bundle fingerprint; decision version; accountable actor identity; verification identity; stable condition-set ID; canonical nonnegative decimal condition count; complete ordered condition inventory; condition-set fingerprint; condition-satisfaction evidence identities where applicable; and effective and expiry times. The condition-set fingerprint participates in the decision/evidence-bundle commitment. A missing or inapplicably defaulted identity fails closed.

Cross-jurisdiction, cross-region, cross-market, cross-service, cross-policy-scope, cross-instrument, cross-language, cross-rendition, cross-version and cross-stage reuse is prohibited. Architecture approval cannot authorize implementation; implementation approval cannot authorize deployment; deployment authorization cannot authorize production. Approval scope cannot be widened retroactively.

### Normative transition contract

Every transition records the stable decision ID and version, attributable actor, accountable transition authority, evidence ID, reason, immutable timestamp, previous state and resulting state. Invalid, unknown, skipped or unauthorized transitions fail closed and append no authoritative state.

| Predecessor | Permitted successor | Accountable authority and minimum evidence |
|---|---|---|
| `NOT_STARTED` | `RESEARCHED_UNVERIFIED`, `QUESTION_PREPARED`, `BLOCKED` | Assigned domain owner; scoped research/question/blocker evidence. Direct approval is prohibited. |
| `RESEARCHED_UNVERIFIED` | `QUESTION_PREPARED`, `BLOCKED`, `SUPERSEDED` | Domain owner or verifier; reviewed research and scope evidence. |
| `QUESTION_PREPARED` | `SUBMITTED`, `BLOCKED`, `SUPERSEDED` | Authorized submitting owner; exact question, authority and submission evidence. |
| `SUBMITTED` | `ANSWER_RECEIVED_UNVERIFIED`, `BLOCKED`, `SUPERSEDED` | Custodian; receipt evidence. Silence or attendance cannot advance state. |
| `ANSWER_RECEIVED_UNVERIFIED` | `VERIFIED`, `REJECTED`, `BLOCKED`, `SUPERSEDED` | Independent verifier and domain authority; authenticity, scope, conflict and interpretation evidence. |
| `VERIFIED` | `APPROVED`, `REJECTED`, `BLOCKED`, `EXPIRED`, `SUPERSEDED` | Accountable approving authority; exact evidence bundle and prerequisite results. |
| `APPROVED` | `EXPIRED`, `SUPERSEDED`, `BLOCKED` | Expiry service or accountable authority; trigger, conflict, incident or replacement evidence. Approval cannot be edited in place. |
| `REJECTED` | `SUPERSEDED` | Accountable authority; a new attributable decision version is required to reopen work. |
| `EXPIRED` | `SUPERSEDED` | Accountable authority; a new attributable decision version is required after fresh verification. |
| `BLOCKED` | `RESEARCHED_UNVERIFIED`, `QUESTION_PREPARED`, `ANSWER_RECEIVED_UNVERIFIED`, `VERIFIED`, `REJECTED`, `SUPERSEDED` | Blocker owner plus independent verifier; evidence that the stated blocker was resolved. It cannot transition directly to `APPROVED`. |
| `SUPERSEDED` | none | Terminal historical state; successor exists under a new immutable version. |

`REJECTED`, `EXPIRED`, `SUPERSEDED`, `BLOCKED` and condition-unsatisfied records never satisfy a gate. Reopening rejected or expired work creates a new attributable version and preserves immutable history. A material scope or evidence change also creates a new decision version.

Conditional approval uses `APPROVED` plus an exact condition set, never a new ambiguous status. Every decision, including an unconditional decision, binds a stable condition-set ID, a canonical nonnegative decimal count, the complete ordered inventory and its SHA-256 fingerprint. Canonical decimal is `0` or a nonzero digit followed by digits; signs, whitespace, leading zeroes, fractions, exponents and empty values are invalid.

An unconditional decision is represented only by an explicit governed zero-condition set: its condition-set ID is present, its count is exactly `0`, and its ordered inventory is explicitly empty. The canonical empty-inventory bytes are UTF-8 without BOM, exactly `CONDITION_SET_V1` followed by LF, `condition_count=0` followed by LF, and no other bytes; their SHA-256 fingerprint is `e34d0c7c0c5ec8a6935d13fec9929b0905ee74b76ecbf49451a032ec3edd8a24`. Absence of the condition-set record is not equivalent to zero conditions, and no artificial satisfied condition may be invented.

For a nonzero set, the canonical count reconciles exactly with the complete ordered inventory. Each condition binds condition ID, exact scope, requirement, satisfaction evidence, verifier identity, verification time, expiry, residual restrictions and current result of `SATISFIED`, `UNSATISFIED` or `EXPIRED`. Every applicable condition must be current and `SATISFIED`. An omitted, duplicate, unknown, extra, expired or unsatisfied condition; a blank or incomplete inventory; a noncanonical count; or a count/inventory mismatch fails closed. Mutation of condition identity, count, order, content or result changes the condition-set fingerprint and invalidates the evidence-bundle fingerprint.

For final-gate evaluation, `condition-satisfied` means either a valid explicit zero-condition set for an unconditional decision or a complete nonzero condition set whose every governed condition is current and `SATISFIED`. No other representation satisfies the condition component, and satisfying that component alone grants no approval or downstream authority.

## 9. Authority and separation of duties

- Legal reviewer: legal interpretation; no technical, product or production authority.
- Transport/regulatory reviewer: licensing and regulator obligations within stated jurisdiction.
- Privacy/Data Steward: data inventory, lawful-basis, rights, transfer and retention governance.
- Product: rider experience and operating policy; no legal substitution.
- Native-language reviewer: rendition-specific linguistic and cultural accuracy.
- Accessibility reviewer: professional and representative-user accessibility evidence.
- Security/CTO: technical architecture, integrity and security; not legal approval.
- Founder/CEO: final attributable business decision after prerequisites; cannot silently replace them.
- Deployment operator: executes a separately authorized deployment; cannot approve content.
- Independent auditor: checks evidence and controls independently; does not operate them.

No self-approval is permitted where independence is required. The author or preparer is separate from the final approver. Translator, native-language reviewer and legal-equivalence reviewer are distinct roles. Legal cannot grant technical/security approval; Product cannot grant accessibility approval; native-language review alone cannot grant legal equivalence. Content approvers cannot bypass technical integrity. Deployment personnel cannot approve content. Founder approval cannot replace missing prerequisites. AI cannot grant approval. Independent auditors remain organizationally and operationally separate from evidence preparation and approval. Emergency-withdrawal actors cannot approve, schedule, activate, replace or roll back content.

| Negative case | Required result |
|---|---|
| Author or preparer acts as required independent final approver | `BLOCKED` |
| Translator also supplies required native-language or legal-equivalence approval | `BLOCKED` |
| Legal attempts Security/CTO approval | `BLOCKED` |
| Product attempts accessibility approval | `BLOCKED` |
| Founder record exists while a prerequisite is absent | `BLOCKED` |
| Auditor prepared or approved the governed evidence | `BLOCKED` |
| Emergency-withdrawal actor attempts activation, replacement or rollback | `BLOCKED` |

## 10. Source provenance

Every source record contains stable source ID; title; issuing authority; instrument number; adoption, publication and effective dates; source type; official URL; access date; language; translation status; relevant provisions; binding/guidance status; confidence; supersession check; reviewer; and limitations.

Primary sources are mandatory where available. Authoritative-language verification and newer/superseding-authority checks are required. Secondary sources may locate or explain primary material but cannot independently authorize implementation. Platform policies receive explicit re-review dates. Broken or unavailable sources remain unresolved.

## 11. Legal-instrument classification

The pack separately classifies transport-service terms, price/quote acceptance, privacy notice, genuinely consent-based privacy processing, safety disclosure, cancellation/refund terms, complaints/dispute information, optional marketing consent and later payment terms.

For each instrument it records legal purpose, lawful basis, required presentation, separate affirmative-action requirement, languages, versioning, retention driver, withdrawal/revocation effect, filing/approval requirement and implementation gate. Sharing one renderer or evidence mechanism never supplies legal permission to bundle instruments.

## 12. Counsel and regulator answer governance

The written-answer ledger binds the exact question, authority asked, submission channel and date, response and attachment/reference identity, formal/informal/binding/advisory/conditional character, jurisdiction and scope, conditions, contradictions, follow-up, counsel interpretation, internal verification and stage unblocked. Follow-up records bind the original question ID and every prior answer ID. No contact or submission is authorized by this record.

## 13. Language and rendition approvals

Amharic, Afaan Oromo and English are candidates, not approved launch languages. No runtime machine translation or silent fallback is permitted. Each approved rendition requires independent native-language and legal-equivalence review and binds market, instrument, version and rendition. Language change requires a newly bound exact rendition; a missing required rendition blocks that launch.

Every language or legal-equivalence decision binds source instrument, version, rendition identity and hash; target instrument, version, rendition identity and hash; canonical locale; format; translator identity; native-language reviewer identity; legal-equivalence reviewer identity; and evidence-bundle identity and version. Evidence also covers competence, terminology, glyph/font shaping, line breaking, truncation, text scaling, mixed scripts, applicable bidirectional behavior, representative-device testing, approval date and expiry/re-review. Every material byte change invalidates affected linguistic and legal-equivalence approvals. No language is approved here.

Source mutation, target mutation, locale substitution or required-role collision produces `BLOCKED` and requires a new rendition/evidence version and independent review.

## 14. Accessibility approval

The proposed AYO engineering floor is **WCAG 2.2 Level AA**. This is not a claim that Ethiopian law mandates WCAG 2.2. WCAG2Mobile is informative draft guidance, not normative law or a final W3C standard. Legal applicability remains for counsel, and conformance evidence requires native-mobile and representative-user testing.

Every accessibility decision binds exact rendition, document format, UI implementation/build identity, platform and version, supported device population, assistive-technology population, font/rendering configuration, test-evidence version and fingerprint, reviewer identity, approval scope and expiry. Evidence must cover accessible name/role/state; screen-reader reading order; resize/reflow; contrast and non-colour cues; target sizes; focus visibility/order; no forced reading timeout; motor accessibility; cognitive/plain-language review; weak-network unavailable states; Amharic and Afaan Oromo rendering; older Android devices; disabled-user testing; and professional accessibility review.

Architecture or template approval cannot approve a nonexistent future UI. Relevant UI, rendition, font, framework, platform, assistive-technology or supported-device changes require re-review. UI/build substitution, font change and use on an unsupported device population fail closed.

## 15. Privacy and retention decisions

Separate unresolved decisions cover lawful basis per evidence class; controller/processor roles; registration; DPO/contact; DPIA; cross-border transfers; hosting/support access; security controls; breach handling; subject access, correction and deletion; legal hold; retention; backup; mobile cache; and telemetry.

Retrieval is not acknowledgment; acknowledgment is not confirmation; privacy consent is not transport-contract assent; marketing consent is separate. No duration is invented. Raw policy content, credentials, full responses and rider location are prohibited in delivery telemetry.

## 16. Rotation and withdrawal decisions

Written decisions are required for scheduled activation, material-change classification, renewed acknowledgment, immediate rotation, grace/no-grace policy, emergency-withdrawal authority, outstanding previews, already confirmed rides, offline riders, incident response, later access, rollback, rider notification and audit retention.

Emergency withdrawal may disable but never approve or activate. No-grace rotation remains unapproved. Rollback requires a new attributable activation decision. Historical evidence cannot be silently rewritten.

## 17. Product and security approvals

Product approval binds the exact rider problem, journey, comprehension evidence, operational impact and authorized scope. Security/CTO approval binds exact architecture, evidence bundle, threat model, integrity, access, incident and verification results. Neither grants legal, language, accessibility, deployment or production approval.

## 18. Founder approval and red lines

Any future Founder decision is attributable only to **Ibrahim Hambentu Shibiru, Founder & CEO** and binds exact scope, evidence-bundle fingerprint, prerequisite status, timestamp, approval/rejection, conditions and re-review triggers. No Founder approval exists now.

Permanent **RED** boundaries prohibit transferring AYO consent-record ownership or policy IP; unilateral vendor policy control; making a vendor the authoritative registry; surrendering signing keys, rider evidence or audit history; lock-in over required records; blocking complete export/migration or independent audit; unilateral third-party terms changes; bypassing Legal, CTO, independent audit or Founder gates; and weakening production prohibition. No researched requirement authorizes these outcomes. A red-line conflict remains `BLOCKED` even if the Founder or another reviewer records approval; no approval can override a permanent red line.

## 19. Expiry and re-review

Every approval identifies an expiry date or objective re-review trigger. Triggers include superseding law or guidance, regulator direction, market/service expansion, instrument or rendition change, material product/architecture change, data-flow or provider change, accessibility defect, security incident, withdrawal, app-store change and evidence-bundle mutation. Expired evidence grants no authority.

## 20. Conflict and uncertainty handling

Binding, newer and authoritative-language sources take precedence. Conflicts are recorded rather than silently resolved. An unofficial translation remains supporting material only. Scope ambiguity, contradictory answers or unavailable authoritative text produces `BLOCKED` or `ANSWER_RECEIVED_UNVERIFIED` until the accountable authority resolves it in writing.

## 21. Implementation gates

Passive product implementation cannot begin until written decisions exist for electronic-assent form, legal-instrument separation, transport disclosure/licensing classification, privacy lawful bases/data flow, required languages, accessibility acceptance criteria and rotation/withdrawal behavior.

A separately authorized synthetic-content technical prototype may test parser/integrity mechanics only if it is unmistakably synthetic, cannot reach riders or production, has no policy prose or activation authority and is not described as product implementation or legal validation.

## 22. Activation gates

User-facing activation requires approved policy prose; approved immutable renditions for every required language; legal and required regulator approval; privacy approval; accessibility acceptance; Product and Security/CTO approval; operational withdrawal/incident readiness; attributable Founder approval; deployment authorization; and separate production authorization. One missing, expired or mismatched gate blocks activation.

## 23. Audit and privacy

Decision and evidence records are immutable, attributable and independently exportable. Access is least-privilege and purpose-bound. Audit records store commitments and necessary provenance, not secrets, raw legal-content copies, private identity documents or unrelated rider data. Custody, confidentiality, access and legal-hold decisions apply per evidence object. Retention and legal-hold rules remain unresolved pending written authority.

## 24. Failure model

Missing authority, verbal-only answer, unofficial/unverified translation, conflicting or stale source, expired approval, scope mismatch, missing language/accessibility/privacy decision, incomplete prerequisites, altered evidence bundle, red-line conflict, unknown status or attempted production authorization without all gates fails closed. Missing digest, changed bytes, unknown MIME/type, unverifiable signer, redaction mismatch, evidence-link rot, unavailable or compromised storage and unauthorized custody also fail closed. No failure state may be interpreted as approval.

## 25. Threat model

Controls must address forged or AI-invented approval, approval replay, scope substitution, outdated sources, unofficial translations treated as authoritative, reviewer impersonation, evidence tampering, evidence-link rot, confidential-document leakage, unavailable or compromised evidence storage, insider collusion, separation-of-duties bypass, vendor control and signing-key/evidence lock-in, emergency-withdrawal misuse, bundled consent, dark patterns, inaccessible-presentation approval, retention overreach, unapproved cross-border processing and production-gate bypass.

| Threat | Stable failure and prohibited authority | Accountable escalation and recovery |
|---|---|---|
| Evidence-link rot or unavailable store | `BLOCKED`; no verification, implementation, deployment or production authority | Evidence custodian and independent auditor; recover from an authorized export, re-verify digest and custody, then issue a new evidence version if needed. |
| Confidential-document leakage | `BLOCKED`; disclosed material cannot authorize a gate | Privacy/Data Steward and Security/CTO; contain, assess breach duties, rotate access and re-establish authorized evidence custody. |
| Compromised evidence store or changed bytes | `BLOCKED`; all dependent approvals are unusable | Security/CTO, evidence custodian and independent auditor; isolate the store, compare independently held digests/exports and re-verify or supersede affected evidence. |
| Insider collusion or separation-of-duties bypass | `BLOCKED`; affected approvals and downstream authority are invalid | Security/CTO and independent auditor; preserve immutable audit, investigate, reassign maker/checker roles and repeat independent approval. |
| Vendor/key/evidence lock-in | `BLOCKED`; no activation, migration acceptance or production authority | Founder/CEO, Legal and Security/CTO; require complete export, AYO-controlled authority and independent audit before re-review. |

Controls include independently verified digests, bounded Git metadata, least-privilege access, immutable audit records, complete export, independent audit, maker-checker separation, conflict escalation and tested recovery from unavailable or compromised storage.

## 26. Alternatives rejected

- One blanket legal approval: hides independent authorities and scope.
- Verbal or meeting-based approval: is not durable or attributable enough.
- Developer or AI self-approval: violates authority boundaries.
- Treating template completion as approval: confuses administration with decision authority.
- Vendor-owned registry/evidence: violates AYO control, portability and audit red lines.
- Beginning UI or policy drafting before classification: risks bundled, misleading or inaccessible consent.

## 27. CI consequences

Historical consent-document architecture evidence remains immutable. This documentation increment requires its own exact evidence route before publication unless an existing narrow documentation route is independently shown to support it safely. Historical admission must not be reused or broadened. Future implementation requires a separate source/test evidence mode. Workflow or documentation changes that affect secret inventories require fresh neutral capture. Executable validation cannot be relabelled as fresh.

## 28. Production prohibition

Production is inactive and prohibited. This record authorizes no policy content, implementation, deployment, release, external submission or production action.

## 29. Open decisions

All approval domains in Section 6 remain unresolved. The governed template defaults them to `NOT_APPROVED`, unresolved answers to `UNRESOLVED`, and production fields to `PROHIBITED` until separately attributable evidence and authorization exist. Ethiopia is the only currently scoped jurisdiction profile. The model may later support separately reviewed jurisdiction-specific profiles, but it does not claim worldwide legal coverage or knowledge. Global regulatory intelligence requires its own architecture, authority, provenance, freshness and local human-verification gates.
