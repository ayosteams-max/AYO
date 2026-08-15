# AYO Booking Consent Ethiopia Written Decision Cycle Architecture

Status: **PROPOSED / PRE-PRODUCTION**
Research basis date: **16 August 2026**
Current jurisdiction profile: **Ethiopia only**

## 1. Purpose and authority boundary

This architecture governs how AYO may prepare for, receive, authenticate, verify, classify, retain and apply written Ethiopian legal or regulatory answers before any passive Booking consent-document delivery implementation. It creates no legal opinion, regulator response, approval, policy wording, evidence-store selection, implementation authority, deployment authority or production authority.

Global awareness; jurisdiction-specific authority. AI may research, organize and compare. Authorized humans decide. AYO independently verifies. Meeting attendance, silence, submission, verbal advice, an email, a completed template or successful CI cannot imply approval.

Missing, conflicting, expired, unverifiable, malformed, condition-unsatisfied or out-of-scope evidence is `BLOCKED`.

## 2. Existing architecture truth

AP-076 proposes server-owned consent-document delivery, and AP-077 proposes the governed approval pack. Neither provides approved policy prose, completed approval, an authoritative evidence store, a registry, an endpoint, rider presentation, acknowledgment, confirmation, recovery, deployment or production authority. This decision cycle prepares the minimum written external answers needed before passive delivery implementation can be considered.

## 3. Research basis and source records

The research basis is the read-only Ethiopia authority mission dated 16 August 2026. Absence of repeal evidence is not proof that an instrument remains current. Each source must be checked for amendments, repeal, supersession, authoritative language and applicability before it can support a decision.

Every governed source record binds:

- stable source ID;
- title, issuing authority and instrument type;
- instrument number or version;
- verified publication and effective dates, or `UNRESOLVED`;
- authoritative language, or `UNRESOLVED`;
- official URL reference and access date;
- digest algorithm and digest commitment for a later verified source copy, initially `UNRESOLVED`;
- amendment, repeal and supersession status, initially `UNRESOLVED` unless verified;
- exact proposition supported and applicability limitation;
- lifecycle state and separate research descriptors.

| Source ID | Instrument | Authority/type | Verified date | Language/official reference | Proposition and limitation | Gate state |
|---|---|---|---|---|---|---|
| ETH-SRC-CONST-001 | FDRE Constitution, Proclamation No. 1/1995 | Federal constitutional instrument | Publication/effect: `UNRESOLVED` in this pack | Authoritative language: `UNRESOLVED`; official copy/digest: `UNRESOLVED` | Federal language framework; private-app language consequence unresolved | `RESEARCHED_UNVERIFIED` |
| ETH-SRC-ETX-001 | Electronic Transaction Proclamation No. 1205/2020 | Federal proclamation | Published 30 June 2020; effect: `UNRESOLVED` | Authoritative language: `UNRESOLVED`; https://laws.moj.gov.et/registries/view/1414/am; digest `UNRESOLVED` | Electronic-transaction framework; does not make a tap sufficient by itself | `RESEARCHED_UNVERIFIED` |
| ETH-SRC-ESIG-001 | Electronic Signature Proclamation No. 1072/2018 | Federal proclamation | Published 16 February 2018; effect: `UNRESOLVED` | Authoritative language: `UNRESOLVED`; https://laws.moj.gov.et/registries/view/1273/am; digest `UNRESOLVED` | Signature/certification framework; applicability per instrument unresolved | `RESEARCHED_UNVERIFIED` |
| ETH-SRC-CCP-001 | Trade Competition and Consumer Protection Proclamation No. 813/2013 | Federal proclamation | Publication/effect: `UNRESOLVED` | Official consolidated text, authoritative language and digest: `UNRESOLVED` | Consumer duties and current institutional allocation unresolved | `RESEARCHED_UNVERIFIED` |
| ETH-SRC-PDP-001 | Personal Data Protection Proclamation No. 1321/2024 | Federal proclamation | Published 24 July 2024; effect: `UNRESOLVED` | Authoritative language: `UNRESOLVED`; https://pdp.eca.et/pdp-proclamation; digest `UNRESOLVED` | Personal-data framework and ECA role; AYO duties require written analysis | `RESEARCHED_UNVERIFIED` |
| ETH-SRC-ROAD-001 | Road Transport Proclamation No. 1274/2022 | Federal proclamation | Published 15 July 2022; effect: `UNRESOLVED` | Authoritative language: `UNRESOLVED`; https://laws.moj.gov.et/registries/view/1479/am; digest `UNRESOLVED` | Road-transport framework; Addis platform rules unresolved | `RESEARCHED_UNVERIFIED` |
| ETH-SRC-CRPD-001 | Convention on the Rights of Persons with Disabilities status | UN treaty record | Ethiopia ratified 7 July 2010; effect recorded 6 August 2010 | UN authentic texts; https://treaties.un.org/Pages/showDetails.aspx?clang=_en&objid=080000028017bf87; digest `UNRESOLVED` | Treaty status only; private-app implementing effect unresolved | `RESEARCHED_UNVERIFIED` |
| ETH-SRC-WCAG-001 | WCAG 2.2 | W3C Recommendation | 12 December 2024 Recommendation | English normative text; https://www.w3.org/TR/WCAG22/; digest `UNRESOLVED` | Proposed AYO engineering floor, not Ethiopian law | `RESEARCHED_UNVERIFIED` |
| ETH-SRC-MOBILE-001 | WCAG2Mobile | W3C Group Draft Note | 6 May 2025 draft note | English; https://www.w3.org/TR/wcag2mobile-22/; digest `UNRESOLVED` | Informative draft guidance; not a standard or Ethiopian law | `RESEARCHED_UNVERIFIED` |
| ETH-SRC-ADDIS-001 | Applicable Addis transport/taxi/platform directives | Authority/instrument unresolved | `UNRESOLVED` | Official text, language, URL and digest `UNRESOLVED` | Exact ride-hailing licence and disclosures unresolved | `BLOCKED` |

Descriptors such as `PRIMARY_SOURCE_AVAILABLE`, `OFFICIAL_SOURCE_UNAVAILABLE`, `BINDING_INSTRUMENT`, `ADVISORY_GUIDANCE` and `INFORMATIVE_STANDARD` describe research only. They never authorize a gate.

## 4. Closed lifecycle and approval result

Every material issue has exactly one lifecycle state:

`NOT_STARTED`, `RESEARCHED_UNVERIFIED`, `QUESTION_PREPARED`, `SUBMITTED`, `ANSWER_RECEIVED_UNVERIFIED`, `VERIFIED`, `APPROVED`, `REJECTED`, `EXPIRED`, `SUPERSEDED`, or `BLOCKED`.

New records begin at `NOT_STARTED`. `NOT_APPROVED` is an approval-result default, not a lifecycle state. Unknown, blank, conflicting or malformed lifecycle values resolve to `BLOCKED`. No direct `NOT_STARTED` to `APPROVED` transition is valid. Every transition binds prior and resulting state, actor, authority, evidence ID, reason and immutable timestamp. Rejected or expired work reopens only as a new version preserving history. Material scope change requires a new decision version and cannot widen an earlier answer.

Non-authoritative descriptors may include `PRIMARY_SOURCE_AVAILABLE`, `OFFICIAL_SOURCE_UNAVAILABLE`, `CONFIRMED_AUTHORITY`, `PROBABLE_AUTHORITY`, `RESEARCH_LEAD`, `BINDING_INSTRUMENT`, `ADVISORY_GUIDANCE`, `INFORMATIVE_STANDARD`, `SECURITY_REQUIREMENT` and `FOUNDER_RED_LINE`.

## 5. Counsel engagement structure

The governed roles are lead Ethiopian counsel; electronic-transactions/evidence specialist; transport and Addis licensing specialist; consumer-protection specialist; privacy/data-protection specialist; authoritative-language/legal-equivalence specialist; and, where needed, accessibility-law specialist.

One person may hold multiple roles only where professional competence, independence, conflicts and the reason for consolidation are written and verified. No person may self-certify a domain requiring independent review. Lead counsel coordinates but cannot replace regulator, Privacy, translator, native-language, legal-equivalence, accessibility, Product, Security/CTO, independent-audit or Founder authority.

Before reliance, an engagement record must bind professional identity and licensing verification; jurisdiction and practice scope; conflict check; engagement scope; confidentiality and privilege classification; exclusions; accountable author and reviewer; issue date; expiry/re-review trigger; cited authoritative sources; exact written conclusion; conditions; and residual uncertainty. No private lawyer is named or selected here.

## 6. Question and answer identity

Every counsel question binds question ID; Ethiopia jurisdiction and sub-jurisdiction; Addis market; Immediate Standard Booking service; exact policy/instrument/domain scope; blocking reason; suspected authority; required answer type; acceptable written evidence; accountable reviewer; downstream gate; lifecycle state; approval result; condition-set ID and fingerprint; expiry/re-review trigger; and safe result `BLOCKED`.

Every written answer binds answer ID; original question ID; prior-answer and follow-up IDs; exact-byte digest and algorithm; issuing person/institution; verified professional or official authority; receipt channel/time; signature or certificate verification where applicable; confidentiality and redaction state; authorized storage record; exact scope; cited sources; conclusion; conditions; limitations; effective and expiry times; verifier; conflicts; and downstream effect.

Verbal guidance creates only a linked follow-up question. A URL, email provenance, sender display name or meeting record alone does not establish authenticity or authority.

## 7. Minimum counsel domains

The unfilled template contains stable records for:

- electronic assent: governing instruments, affirmative action, attribution, authentication, disclosure, integrity, signature form, rider copy and evidentiary record;
- instrument separation: transport, price/quote, cancellation/refund, safety, privacy notice, privacy consent, marketing, payment and insurance/operator disclosures;
- language: Amharic, Afaan Oromo and English requirements, explicit selection, unavailable rendition and legal equivalence;
- accessibility: domestic obligations, CRPD implementation, national standards, WCAG 2.2 AA proposal, informative WCAG2Mobile use and representative-user testing;
- privacy and custody: roles, lawful bases, registration, notification, DPO, DPIA, rights, minimization, retention, legal hold, breach, transfer, localization, Australian access and evidence storage;
- rotation and withdrawal: material change, grace, renewed acknowledgment, notice, offline riders, emergency withdrawal, rollback and historical evidence;
- transport and consumer disclosures: identity, licence, fare, route, cancellation, complaints, insurance, safety, contacts, stage, format, language and retention;
- admissibility: attribution, timestamps, hashes, signatures, certificates, original bytes, language, export, custody and inspection forum.

No answer is prefilled.

## 8. Regulator-question governance

Possible recipients are Addis Ababa Transport Bureau; Ministry of Transport and Logistics; Ethiopian Communications Authority; Ministry of Trade and Regional Integration or a verified successor consumer authority; INSA only if counsel finds the signature/certificate regime applicable; and a counsel-identified accessibility authority.

No regulator question may be submitted until counsel verifies the recipient, mandate, statutory basis, exact wording, sender authority and formal route. Each record binds question ID; proposed authority; counsel-confirmed mandate state; statutory basis; submission route; sender; expected binding/advisory/operational character; response identity and attribution; conditions; appeal/escalation; expiry; and non-response result `BLOCKED`.

## 9. Interim confidential-evidence handling rule

The authoritative evidence store is **`UNRESOLVED`**. No provider is selected.

Until separately authorized storage exists:

- do not accept or solicit sensitive legal opinions, identity documents, signatures, certificates, regulator correspondence or confidential evidence into GitHub, AI chat, issue trackers, mobile clients, ordinary email attachments or unmanaged local folders;
- public, non-confidential research and blank templates may be prepared;
- Privacy and Security/CTO must approve any proposed sensitive exchange channel first;
- unexpectedly received sensitive material must not be copied, summarized into Git or redistributed; it requires a separately approved quarantine/incident procedure;
- no object satisfies a gate without stable ID, digest, custody, authenticity, scope and authorized storage record.

A future store must provide encryption in transit and at rest; AYO-controlled or separately approved governed key control; phishing-resistant administration; least privilege; maker/checker administration; immutable audit; cryptographic commitments; versioning and supersession; legal hold; duration-neutral retention enforcement; controlled redaction; secure export; independent audit; disaster recovery; offboarding; vendor exit; and complete migration.

Vendor ownership/control of AYO IP, policy, evidence or registry, key surrender, non-exportability or audit obstruction is permanently `BLOCKED`.

## 10. Written-answer verification sequence

The mandatory order is receipt; quarantine pending custody verification; authenticity verification; authority verification; source verification; scope verification; conflict review; condition extraction; independent reviewer verification; decision; expiry/re-review; and supersession.

No stage may infer completion of a later stage. `APPROVED` requires an attributable authorized decision after `VERIFIED`; it is never generated by counsel submission, receipt, implementation, CI or AI output.

## 11. Conflict and uncertainty

- Conflicting counsel opinions: `BLOCKED`, escalated to lead counsel and an independent qualified reviewer.
- Counsel/regulator conflict: `BLOCKED`, escalated to the accountable legal and regulatory authorities.
- Unavailable authoritative text: `BLOCKED` pending authoritative-language/source verification.
- Unofficial translation: cannot satisfy authoritative-language verification.
- Incomplete, out-of-scope or fact-dependent answer with unknown facts: `BLOCKED`.
- Expired or superseded answer: cannot satisfy the current gate.
- Conditional answer with any unmet, unknown, duplicated, omitted or expired condition: `BLOCKED`.
- Silence or non-response: `BLOCKED`.
- Foreign-jurisdiction answer: cannot authorize Ethiopia.

Escalation identifies the responsible role and next written question but never chooses the legal outcome.

## 12. Separation of duties

Distinct roles are preparer; lead counsel; specialist counsel; regulator; Privacy/Data Steward; translator; native-language reviewer; legal-equivalence reviewer; accessibility professional; Product; Security/CTO; independent auditor; Founder/CEO; deployment operator; and production authorizer.

Authors cannot self-approve. Translators cannot self-certify native review or legal equivalence. Legal cannot grant Security approval. Product cannot grant Accessibility approval. Deployment cannot approve content. Independent audit is organizationally and operationally separate from preparation, custody administration and approval. Emergency-withdrawal authority cannot approve, schedule, activate, replace or roll back content.

Founder identity is label-only: **Ibrahim Hambentu Shibiru, Founder & CEO**. No Founder signature or approval is recorded. Founder approval cannot replace missing Legal, Privacy, language, accessibility, Product, Security or audit requirements.

## 13. Permanent Founder RED conditions

The result is `BLOCKED` if a proposal would transfer ownership, equity, voting or control; transfer policy or IP ownership; grant uncontrolled broad or perpetual IP rights; surrender signing keys, repositories or control planes; transfer control of rider evidence or the registry; prevent export, migration or independent audit; allow unilateral third-party policy change; bypass an approval gate; let withdrawal authority activate replacement content; weaken production prohibition; or authorize production before prerequisites.

No recorded approval, including a Founder record, can override a permanent RED condition.

## 14. Founder meeting brief contract

The meeting brief binds purpose; attendee/authority verification; scope; unresolved questions; verified sources; documents safe to bring; confidential-material restrictions; questions; conditions; RED items; decisions excluded from the meeting; written follow-up; and final result.

- `GREEN`: exact written, attributable, verified, current, scoped and condition-satisfied evidence.
- `AMBER`: useful but insufficient research or conditional/informal material; no gate unblocked.
- `RED`: conflict, ownership/control danger, authority failure, custody failure or prohibited term.
- `HUMAN/EXTERNAL SIGN-OFF REQUIRED`: an accountable qualified person must decide.

If any RED remains unresolved, AYO does not proceed. A meeting cannot itself authorize implementation, deployment or production.

## 15. Australia and global boundary

This cycle is Ethiopia-only. Australia requires separate Commonwealth, state/territory, local and sector profiles. Australian citizenship, development activity or an Australian entity does not authorize Ethiopian operation; Ethiopian approval does not authorize Australia. Cross-border IP, employment, tax, privacy and data access remain separate. Future global intelligence must preserve jurisdiction-specific sources, freshness, applicability and accountable local human verification. This increment creates no global law corpus.

## 16. Implementation and production gates

Passive consent-document delivery remains blocked until exact written decisions resolve assent form, instrument separation, transport classification and disclosures, privacy/data flow/custody, required languages, accessibility criteria, and rotation/withdrawal. Later activation additionally requires approved prose and immutable renditions, every human/external approval, operational readiness, deployment authorization and separate production authorization.

Production is inactive and **PROHIBITED**. This architecture cannot authorize product implementation, deployment, release or production.

## 17. Failure and threat model

Missing authority, forged or impersonated answers, replay across scope, unofficial translations, stale sources, altered bytes, custody compromise, confidential leakage, role collision, collusion, link rot, unavailable storage, vendor control, condition omission, scope widening and production-gate bypass all produce `BLOCKED`. Recovery requires a new attributable version, verified evidence, restored authorized custody, independent review and preserved immutable history.

## 18. Open decisions

Counsel selection, engagement channel, evidence-store authority, regulator recipients, authoritative-language sources, every substantive legal answer, privacy decisions, required languages, accessibility law, policy prose, implementation, deployment and production remain unresolved and require separate authorization.
