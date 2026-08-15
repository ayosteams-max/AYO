# Server-Owned Booking Consent Document Delivery Contract Architecture

Status: **PROPOSED / PRE-PRODUCTION.** This record is an architecture proposal for CTO review and later Founder/CEO decision. It creates no implementation, approval, policy content, endpoint, registry entry, deployment or production authority.

## Problem statement

AYO can bind server-owned Booking consent metadata to route-preview evidence, but it cannot yet deliver the reviewed human-readable document represented by that metadata. The current contract exposes only a required version, document identifier, content hash and acknowledgment requirement. Those values protect integrity but are not meaningful consent content for a rider. Displaying identifiers, hashes, invented placeholder prose or an unreviewed translation would create false assurance rather than informed acknowledgment.

The next safe design problem is therefore narrower than confirmation: define how a future authenticated rider client can retrieve exactly the reviewed localized rendition that the server bound to one preview, verify it without substitution, and fail closed under rotation, withdrawal, expiry and weak connectivity. This proposal does not make that capability executable.

## Existing architecture truth

- `ImmutableBookingConsentRegistry` owns immutable `BookingConsentMetadata` records and requires exactly one active policy at a given server time.
- Current metadata contains `required_version`, `document_id`, `content_hash`, effective interval, mandatory acknowledgment and `immediate_mandatory` rotation.
- Route preview includes the complete current metadata in its evidence hash and persists that binding with the preview.
- Confirmation requires the exact preview-bound version and hash, explicit acknowledgment, and equality with the created, registered and current mandatory policy before any side effect.
- The repository contains no legal policy prose, policy-document endpoint or production consent registry. Runtime defaults fail closed when consent authority is unavailable.
- Mobile strictly parses the current bounded metadata but has no document-content parser, delivery transport, acknowledgment action, confirmation/recovery capability, durable Booking storage, screen or navigation composition.
- Mobile Booking uses authenticated transport for its intended route-preview use and stops at `confirmation_locked`; its provider remains outside normal application composition. The current backend preview route accepts an optional subject, which does not authorize anonymous consent-bearing V2 previews.
- The current `content_hash` does not identify a locale or localized rendition. Its meaning must not be silently changed or treated as proof that a particular translation was shown.
- The admitted `mobile-booking-intent-foundation` CI mode governs the completed historical foundation and its exact evidence. It is not authority for this proposed contract.

## Goals and success measures

The proposed later contract should:

1. let an authenticated rider retrieve the exact approved rendition already selected and bound by the server to one current preview;
2. make any version, document, rendition, locale, format, byte or effective-state substitution fail closed;
3. keep preview responses bounded and document delivery independently cacheable and rate-limited;
4. support deterministic unavailable, stale, withdrawn and offline states without false acknowledgment;
5. minimize retained content and personal data; and
6. provide an understandable, testable path to additional approved Ethiopian languages without runtime translation.

Later implementation success must be measured by exact contract/integrity tests, rotation and weak-network recovery tests, zero cross-rider preview access, bounded payload and cache behavior, accessibility validation, native-language review, and rider comprehension evidence. No production target is approved by this proposal.

## Non-goals

This increment does not introduce policy or legal prose, an active document, a production registry, a database table or migration, an endpoint, backend or mobile code, acknowledgment UI, a component, screen or navigation route, confirmation or recovery transport, confirmation-capable mobile state, durable mobile storage, provider composition, payment, dispatch, notification, analytics, dependencies, lockfile changes, CI workflow changes, deployment, production activation or a legal-compliance claim.

## Trust and authority boundaries

- The server is the sole authority for policy family, policy version, approved document, approved localized rendition, effective state, rotation, withdrawal and acknowledgment requirement.
- Mobile may request a supported locale before preview creation, retrieve the server-selected preview-bound rendition and verify it. Mobile may never author, edit, translate, merge, substitute or activate content.
- The future presentation client must not accept developer placeholder content, bundled fallback policy prose, machine translation, remote content fragments or an unbound cached rendition.
- Policy approval authority is separate from software deployment authority. A deployment cannot approve content, and content approval cannot deploy software.
- Policy-management writes are not part of the rider API and must never be exposed through mobile capability.
- The authenticated server context supplies rider identity. No request field may select rider ownership or override preview ownership.
- Backend Booking remains authoritative for preview, pricing, consent binding, confirmation, recovery and dispatch. Mobile remains presentation-only until later separately authorized increments.

## Proposed immutable document and rendition model

The future model should distinguish:

- `policy_family_id`: stable family for the Booking consent obligation;
- `policy_version`: immutable approved semantic version within that family;
- `document_id`: immutable logical document identity for that policy version;
- `document_manifest_hash`: SHA-256 commitment to the approved rendition manifest and its immutable identities;
- `rendition_id`: immutable identity for one reviewed language rendition;
- `locale`: canonical approved locale tag for that rendition;
- `format`: the exact versioned passive media type;
- `rendition_content_hash`: SHA-256 over the exact canonical rendition bytes;
- `effective_from` and optional `effective_until`: UTC server-owned interval with equality expired;
- `status`: scheduled, active, withdrawn or retired runtime state after promotion;
- `acknowledgment_required`: strict true for this Booking contract;
- bounded accessibility metadata such as document language, title identifier, reading order and heading relationships; and
- an externalized, non-sensitive approval reference proving required approvals exist without exposing review notes, identities beyond approved attribution, signatures or internal records to mobile.

The model also requires one immutable closed `policy_scope`. The proposed initial scope is limited to the reviewed Ethiopian Immediate Standard Booking context and must encode exact country/jurisdiction, market, service type, booking class, product, tenant and policy-family identifiers. Wildcards, omitted dimensions, default inheritance and cross-scope substitution are prohibited. This does not authorize another tenant, market, jurisdiction, service or product. A wrong-scope record fails closed.

For one closed scope and authoritative server time, exactly one policy version may be active. For one policy version, canonical locale, format, closed scope and server time, exactly one rendition may be active. Overlapping active intervals, ambiguous scheduled activations and duplicate active renditions fail closed. Active bytes, scope, identities, hashes, locale, format and effective interval are immutable. Approval metadata cannot mutate them under an existing identity. A material revision creates new immutable draft bytes and identity.

Rollback never mutates or silently resurrects retired or withdrawn content. Reusing an earlier approved immutable rendition requires a new attributable scheduling/activation decision after current scope, locale, security, legal, product, language, accessibility and effective-interval eligibility checks. Outstanding preview handling remains explicit and fail closed.

## Distinct V1/V2 schemas and downgrade resistance

The future consent-bearing preview and document contracts require an exact wire discriminator, provisionally `consent_contract_version`. V1 and V2 are wholly distinct exact schemas. V2 fields are never optional extensions to V1, and contract identity is never inferred from field presence or structural typing.

Missing, duplicated, unknown, partially populated or malformed discriminators fail closed. Partial V2 cannot be parsed as V1. Client-driven version or content downgrade negotiation is prohibited. A client cannot reconstruct, enrich or locally upgrade a V1 preview into V2 presentation or acknowledgment evidence. V2 activation for the consent-presentation flow invalidates outstanding unconfirmed V1 previews; a new authenticated V2 preview is required.

Future confirmation rejects V1 acknowledgment evidence, partial V2 evidence, legacy-unbound evidence, unknown contract versions and downgraded evidence. The separately versioned V2 preview contract must be selected by an exact server route/schema contract, not a permissive union or default.

Future validation must cover exact V1, exact V2, partial V2, missing/duplicate/unknown discriminator, downgrade attempts, local V1-to-V2 reconstruction and legacy-unbound confirmation.

The existing V1 `content_hash` remains a legacy document-level commitment with its existing semantics. It must not be renamed or reinterpreted in place. A later versioned metadata contract must add the manifest, rendition, locale, format and rendition hash explicitly. Mobile presentation must reject V1 metadata as insufficient rather than guessing a rendition. A preview created under the future contract binds the complete new metadata tuple into its canonical evidence hash.

Acknowledgment must eventually bind to the exact `rendition_id`, locale, format and `rendition_content_hash` displayed, as well as policy version and document identity. A general policy-version acknowledgment is insufficient.

## Delivery-contract comparison and recommendation

### Embed content in route-preview responses

Advantages are one network round trip and atomic receipt of preview plus content. Disadvantages are materially larger preview responses, repeated policy transfer, coupled routing/document failures, poorer conditional caching, harder independent size controls, and greater risk that clients treat changed embedded content as interchangeable metadata. It also makes a routing retry carry legal content unnecessarily.

### Separate authenticated immutable read

Advantages are bounded preview responses, strict document-specific limits, conditional retrieval, independent rate limiting, cache reuse, clearer failure classes and direct verification against the exact preview-bound tuple. It keeps the document service replaceable without moving Booking authority to mobile. The cost is one additional read and explicit weak-network handling.

### Decision

Recommend a separate authenticated, read-only consent-document delivery contract. Future V2 consent-bearing preview creation is rider-authenticated and includes one canonical requested consent locale. The server selects exactly one approved rendition and binds its full tuple to the preview. The later document read is keyed by the preview evidence identity; it does not let mobile select a policy version, document, hash or substitute rendition. The server resolves the authenticated rider, proves preview ownership and current eligibility at retrieval time, then returns only that bound rendition. Conditional retrieval may use the bound rendition hash as a strong validator.

Changing language requires a new preview with an explicitly requested approved locale. This avoids changing the legal content underneath an existing quote or acknowledgment flow. If no exact approved rendition exists, preview/document presentation fails closed.

## Authentication and authorization

- The recommended initial contract is authenticated and rider-role restricted. This preserves preview ownership and prevents cross-account evidence association.
- V2 preview creation and retrieval both require authenticated rider context. The current route's optional-subject behavior is not inherited by V2.
- The read accepts no rider identifier. A preview ID is an untrusted lookup reference, never authorization. The server derives identity from the current trusted authentication context and requires exact equality with the rider identity stored on the preview.
- Captured mobile identity continuity remains exact through preview creation, retrieval, display and any future acknowledgment. Credential refresh may refresh credentials only; it preserves the same account continuity and immutable request identity. Logout, relogin as another account, account replacement or continuity drift invalidates the operation and erases local evidence.
- Anonymous/public delivery could improve CDN caching, but it would sever the ownership check and expand enumeration and scraping surface. It is rejected for the initial contract. A later public-copy decision would require separate threat, legal and operational review and could not authorize acknowledgment.
- Bearer-style retrieval capability is rejected initially. Any later separately authorized capability must expire, bind to one preview, be non-transferable, be replay-bounded, remain authenticated-continuity-bound and never replace server-side ownership authorization.
- The contract is read-only. No mobile policy creation, approval, publication, withdrawal or translation capability exists.
- Apply bounded per-identity and per-network rate limits, request-size limits and abuse monitoring without logging content, tokens, preview identifiers or rider-sensitive data unnecessarily.
- Authentication failures remain generic. Unknown, foreign and unavailable preview/document combinations must not reveal registry membership or another rider's activity.

Future validation includes anonymous preview, cross-rider access, refresh continuity, logout/relogin, account replacement, transferred identifiers, enumeration and replay.

## Localization and fallback

- Use one future normative canonical BCP 47 profile constrained by a closed approved-locale registry. It must define exact tag canonicalization and accepted canonical equivalents. Initial candidates are English `en`, Amharic `am` and Afaan Oromo `om`; listing them does not approve content, make them mandatory or establish launch support.
- A future preview request may specify exactly one supported consent locale. The server performs only the normative tag canonicalization; implicit language-range matching and parent-language fallback are prohibited.
- The selected locale and rendition are server-bound to the preview and returned exactly.
- No silent fallback is permitted. Missing English, Amharic, Afaan Oromo or other requested content returns a stable rendition-unavailable result.
- A rider may explicitly choose another available, approved language only through a new preview, and only if product/legal review confirms that choice is sufficient. English is not automatically legally equivalent to a missing Ethiopian-language rendition.
- Runtime machine translation, AI-authored legal content and client-side translation are prohibited. Human native-language approval is mandatory per rendition.
- Mixed-language and accessibility variants require distinct reviewed rendition identities when their canonical bytes differ.
- Representative-device and human review must cover Amharic and Afaan Oromo font/glyph coverage, line breaking, text scaling, screen-reader reading order, truncation, older Android rendering and mixed-script safety. Bidirectional isolation is required for future applicable languages. Unicode confusables and bidi controls require explicit validation rather than silent normalization.
- Future vectors cover case variants, canonical equivalents, unsupported subtags, unavailable locale, mixed scripts, bidirectional controls, Unicode confusables, explicit language change and different rendition hashes.

## Format and strict parsing

The proposed initial format is `application/vnd.ayo.booking-consent+json;version=1`, using a restricted typed canonical document grammar rather than general JSON. It contains only:

- one exact schema discriminator;
- the immutable identity and locale fields;
- one bounded title string;
- an ordered array of at most 32 sections;
- each section has one immutable section identifier, one bounded heading and one bounded plain-text body; and
- one bounded accessibility block containing language, reading order and heading relationships only.

Proposed engineering bounds for later approval are 64 KiB canonical bytes, a maximum nesting depth of three, at most 32 sections, at most 160 Unicode scalar values per title/heading and at most 4,096 per section body. These provisional limits are intended to accommodate ordinary disclosures while bounding transfer, parsing and memory cost on weak networks and older Android devices. Representative approved-content and device measurements are required before implementation approval; any changed bound requires review.

The future normative grammar must specify UTF-8 without BOM, NFC strings, exact field/key order, exact string escaping, LF-only behavior, whitespace policy, ordered arrays, duplicate-key rejection, missing-field rejection, prohibition on undeclared optional fields, one terminal LF, control-character rules and deterministic backend/mobile behavior. Numbers and null are prohibited unless a field is specifically justified and normatively encoded. Strict Boolean encoding is permitted only for declared fields such as acknowledgment requirement.

The normative specification must define the exact hashed byte envelope and exact metadata inclusion/exclusion. Manifest and rendition hashes are domain-separated with different fixed schema/domain prefixes; a manifest digest can never validate as a rendition digest or vice versa. Implementations use a shared cross-language conformance corpus and never hash a platform-dependent parser dump.

Transfer compression is initially prohibited. Any later separately authorized compression must enforce both compressed and decompressed byte limits before canonical parsing and hashing, and must reject truncation, expansion beyond bounds and unknown encodings.

Future canonical vectors cover BOM, NFC/non-NFC, escaping, key order, duplicate keys, whitespace, line endings, terminal newline, truncation, oversize, excessive depth/sections, null, numbers, hash-domain confusion and compressed payloads.

Arbitrary HTML, Markdown, XML, rich-text objects, scripts, styles, remote fonts, images, tracking pixels, arbitrary URLs, dynamic embeds and executable markup are prohibited. Future links or media require a separately reviewed closed typed element and a new format version. Plain text keeps rendering passive and screen-reader compatible while accessibility presentation remains the UI layer's responsibility.

## Integrity and preview binding

Before any future display is acknowledgment-eligible, mobile must verify exact equality with the preview-bound:

- policy family and version;
- document and rendition identifiers;
- locale and format;
- document manifest hash and rendition content hash;
- effective interval;
- acknowledgment requirement; and
- preview evidence identity and hash.

Mobile then hashes the canonical bytes and performs constant-time comparison with `rendition_content_hash`. It rejects malformed content before projection. The server independently revalidates current registry state at any later acknowledgment or confirmation. Client verification is defense in depth, not policy authority.

An acknowledgment record in a future increment must carry the exact verified tuple. Neither display nor acknowledgment may upgrade legacy V1 preview evidence by assumption.

## Rotation, withdrawal and expiry

- Initial rotation remains the proposed `immediate_mandatory` safety policy with no grace period. Product and legal approval are required; it is not an approved business rule.
- Activating a replacement version or withdrawing a document/rendition invalidates affected unconfirmed previews and any acknowledgment eligibility immediately.
- Effective interval checks use authoritative UTC time; `now == effective_until` is expired.
- Content bytes are immutable. Any byte change requires a new rendition identity and hash; a semantic policy change also requires a new policy version and document manifest.
- Withdrawal is distinct from retirement. Withdrawal blocks presentation and confirmation immediately; retirement is historical lifecycle state after it is no longer eligible.
- Conditional cache validators do not override registry status. A cache hit cannot prove that content remains active.
- If content changes after preview and before display, acknowledgment or confirmation, the operation fails closed and the rider must obtain a new preview. No server or client substitutes the replacement silently.
- A grace-period model is deferred to explicit legal/product approval and a new architecture decision.
- Emergency withdrawal immediately makes affected policy/document/rendition evidence ineligible for new previews and future confirmation. Rollback uses the separately governed new activation decision described above; it never mutates historical state.

## Weak-network and cache behavior

- Safe retries repeat the same read for the same preview identity. Reads are side-effect-free and return the same immutable bytes while the binding remains active.
- A strong conditional validator may be the quoted rendition content hash. A not-modified response is usable only when the locally cached bytes independently hash to that exact value and the server has just reconfirmed eligibility.
- Initial implementation caching is memory-only unless durable caching receives separate authorization. It is isolated to current authenticated continuity and erased on logout, account replacement, provider/controller replacement, clear, retirement and app lifecycle termination where applicable.
- Cache keys include schema/contract version, closed scope, policy family/version, document and rendition IDs, locale, format, manifest hash, rendition hash and effective interval: every immutable identity affecting bytes or eligibility. Rider identity appears in no server-shared cache key, URL, telemetry or log.
- Cached bytes are integrity-verified before use and never prove activation or confirmation eligibility.
- Any future durable cache requires separate authorization, opaque local-account namespacing, app-private protection, integrity verification, mandatory testable purge, crash-safe account replacement, process-restart isolation, backup/restore policy, corruption handling and proof of no cross-account exposure.
- Cached text may be shown as explicitly offline informational content only if product/legal review allows. Offline display is never acknowledgment-eligible because the client cannot prove immediate withdrawal or rotation status.
- No offline acknowledgment or confirmation is authorized. Retrieval uncertainty produces a deterministic unavailable state and no false success.
- Timeouts, cancellation and identity replacement retain the existing stale-completion suppression model. A response for an obsolete preview, locale or identity is discarded.
- Future cache validation covers logout, account replacement, failed/crashed purge, process restart, backup/restore, corruption, wrong-account cache and evidence-semantics confusion.

## Privacy and retention

The future client may minimally retain, subject to separate storage approval:

- rendition identity and hash;
- policy/document version identities;
- locale and format;
- effective interval; and
- retrieval timestamp for cache management, not as proof of acknowledgment.

It should avoid retaining duplicate policy bodies, raw envelopes, tokens, rider identity, precise location, route geometry or unrelated personal data. Document content is not assumed harmless merely because it is common across riders. Logs and analytics must not contain content, identifiers that expose rider activity, authentication material or raw failures.

Retrieval, network delivery, device receipt, display, acknowledgment, comprehension, legal consent and confirmation are distinct events. Retrieval proves none of display, comprehension, acknowledgment, legal consent or confirmation. Delivery telemetry is not acknowledgment evidence; acknowledgment evidence is not confirmation evidence; confirmation evidence is separate from legal audit records. Legal sufficiency remains a qualified human/legal determination.

Delivery logs, acknowledgment evidence, confirmation evidence, operational telemetry and legal audit records are separate stores/contracts with separate minimum-data access and retention decisions. This proposal creates none of them.

The server may retain immutable approval and publication evidence outside the rider delivery response. Legal retention periods, acknowledgment evidence retention, deletion exceptions and cross-account device behavior require qualified legal/privacy decisions; this proposal does not choose a duration.

## Approval and promotion governance

Proposed future content lifecycle:

`DRAFT -> LEGAL_REVIEW -> PRODUCT_REVIEW -> NATIVE_LANGUAGE_REVIEW -> ACCESSIBILITY_REVIEW -> CTO_VERIFIED -> FOUNDER_APPROVED -> SCHEDULED -> ACTIVE -> WITHDRAWN/RETIRED`

Proposed accountable transition ownership is explicit and cannot be inferred from software roles:

| Transition | Accountable future authority | Minimum evidence gate |
|---|---|---|
| Create/revise `DRAFT` | Authorized policy-content owner under Product governance | New immutable canonical bytes, identity, closed scope and revision reason |
| Enter/complete `LEGAL_REVIEW` | Qualified Ethiopian counsel/regulatory owner | Applicable law/disclosure review tied to exact document version |
| Enter/complete `PRODUCT_REVIEW` | AYO Product authority | Rider problem, presentation intent, comprehension and operational behavior |
| Enter/complete `NATIVE_LANGUAGE_REVIEW` | Named qualified reviewer for each rendition language | Exact rendition-byte linguistic review |
| Enter/complete `ACCESSIBILITY_REVIEW` | Qualified accessibility reviewer | Exact rendition/format and representative presentation evidence |
| Enter/complete `CTO_VERIFIED` | AYO CTO/Security authority | Integrity, authorization, threat, operations and evidence verification |
| Enter/complete `FOUNDER_APPROVED` | Ibrahim Hambentu Shibiru, Founder & CEO | Complete prerequisite chain and exact immutable proposal |
| `SCHEDULED -> ACTIVE` | Separately authorized content-promotion operator under maker-checker control | Founder-approved identity, deterministic interval and separately authorized environment/content-promotion decision; this is never itself production authorization |
| `ACTIVE -> WITHDRAWN` | Separately governed incident/content authority | Bounded withdrawal reason and immutable incident evidence; no activation power |
| Eligible state -> `RETIRED` | Authorized records/content lifecycle owner | Supersession/expiry evidence and retention decision; no reactivation |

Every transition records required evidence, immutable timestamp, attributable actor, reason, previous state, resulting state and audit identity.

- Every transition is explicit, attributable, immutable and auditable; rejection returns to a new draft version rather than editing approved history.
- Every transition requires its named accountable authority, required evidence, immutable timestamp, attributable actor, reason, previous state, resulting state and audit record.
- Required review is per exact canonical rendition bytes. Changing content invalidates downstream approvals.
- Rejection cannot activate content. Material revision after review invalidates affected approvals and creates new immutable draft bytes and identity.
- Legal, product, native-language and accessibility reviewers approve only their bounded responsibility. Native-language approval is rendition-specific; accessibility approval is rendition/format-specific.
- CTO verification confirms technical integrity and activation prerequisites; it is not legal approval.
- Founder approval must be attributable to **Ibrahim Hambentu Shibiru, Founder & CEO**.
- Founder approval cannot bypass legal, product, security, native-language or accessibility gates.
- Software deployment and content promotion remain distinct separated duties with maker-checker controls.
- AI may prepare comparisons, validate schema/hash/consistency and flag risks. It may not invent legal wording, translate an approved legal document for activation, impersonate a reviewer, or create Founder approval.

No approval or lifecycle transition is recorded as completed by this proposal.

A separately governed incident authority may immediately withdraw an active policy/document/rendition. Withdrawal is fail closed, prevents new eligible previews and future confirmations using affected evidence, creates immutable incident/audit evidence and requires mandatory later review. The withdrawal path cannot activate, replace, approve or silently roll back content; emergency activation is prohibited. Deployment authorization, content activation and production authorization remain separate decisions.

## Stable failure model

The later implementation requires a reviewed failure matrix. “Erase” below means erase local evidence for the affected operation, not alter server audit history.

| Internal condition | Stable public class | Retry | State/evidence effect | Disclosure and operational meaning |
|---|---|---|---|---|
| Missing/invalid authentication | `authentication_required` | Only after explicit reauthentication | Retire operation; erase local evidence | Reveal no preview or registry state; sign-in required |
| Unknown or foreign preview | `consent_preview_unavailable` | Non-retryable for that reference | Retire; erase | Same response for absent/foreign where appropriate; booking information unavailable |
| Withdrawn policy/document/rendition | `consent_document_unavailable` | Non-retryable; new preview only after approved replacement | Invalidate preview/acknowledgment eligibility; erase | Do not reveal withdrawal reason or registry identity |
| Expired preview/document evidence | `consent_document_expired` | Non-retryable; new preview required | Mark stale; erase acknowledgment eligibility | Information is no longer current |
| Unsupported/unavailable locale | `consent_locale_unavailable` | Non-retryable until explicit approved-language choice/new preview | No acknowledgment eligibility | Do not claim fallback or equivalent language |
| Malformed/partial content | `consent_document_malformed` | Non-retryable for those bytes | Reject and erase bytes | No parser detail or raw content |
| Version/discriminator/downgrade failure | `consent_contract_mismatch` | Non-retryable | Reject and erase | No supported-version inventory |
| Hash/domain integrity mismatch | `consent_integrity_mismatch` | Non-retryable; incident signal | Reject and erase | No expected/observed digest disclosure |
| Preview/document/rendition mismatch | `consent_preview_mismatch` | Non-retryable; new preview required | Reject and erase | No bound tuple disclosure beyond rider-safe state |
| Registry unavailable | `temporarily_unavailable` | Retryable with bounded backoff | Preserve only non-authoritative operation state | Temporary unavailability; no registry details |
| Temporary transport failure | `temporarily_unavailable` | Retryable with bounded backoff | No consent-state mutation | Retrieval not completed |
| Rate limit | `temporarily_unavailable` | Retry only after bounded server guidance | No consent-state mutation | Must not reveal registry state |

No failure can be represented as display, acknowledgment, consent, confirmation or ride success. Retryable failures never mutate consent state; permanent failures never trigger endless automatic retry. Malformed, ambiguous or unclassified output is fatal. Internal provenance, unpublished versions, withdrawal reasons, stack traces, hashes beyond the rider's own bound tuple and operational details remain private.

## Future confirmation dependency

A later executable confirmation design must use one immutable durable command bound to:

- authenticated rider continuity;
- exact preview identity and evidence hash;
- exact quote and pricing evidence;
- exact policy family/version;
- exact document and rendition identifiers;
- exact content and manifest hashes;
- exact locale and format;
- explicit acknowledgment evidence;
- durable client request identity;
- idempotency key; and
- authoritative confirmation recovery identity.

The command must be durably stored before dispatch, survive process death, reuse the same identities across retries, distinguish pending/unknown/confirmed outcomes and reconcile through the authenticated server read. None of these capabilities is implemented or authorized here.

## Security and threat analysis

| Threat | Required control | Residual decision |
|---|---|---|
| Client substitutes friendlier or stale prose | Server-selected preview binding plus exact rendition hash | Approved content quality remains human-owned |
| IDOR, cross-rider access, preview enumeration or transferred references | Authenticated rider identity, exact stored preview ownership, non-enumerating failures and bounded rate limits | Rate-limit thresholds require operational evidence |
| Runtime machine translation changes meaning | No runtime translation; exact approved rendition only | Required launch languages need legal/product decision |
| Cache survives rotation or account change | Online eligibility check; bounded eviction; no offline acknowledgment | Durable cache design requires separate threat review |
| Active markup executes or tracks rider | Passive strict JSON/plain text; no URLs, embeds or scripts | Future media requires a new format decision |
| Deployment activates unapproved content | Separate approval/promotion authority and maker-checker controls | Operational roles need leadership approval |
| Registry outage blocks Booking | Fail closed with stable unavailable state; independent read scaling/caching | Availability SLO requires measured evidence |
| Hash canonicalization differs by platform | Versioned canonical bytes and shared conformance corpus | Implementation libraries chosen later |
| Withdrawal races acknowledgment | Server revalidates current state at acknowledgment/confirmation | No grace policy is approved |
| Logs expose content or rider activity | Bounded error taxonomy and content/identifier log prohibition | Monitoring design remains later scope |
| V1/V2 downgrade or partial-schema parsing | Disjoint discriminator-bound schemas; no optional extension or client downgrade | V2 implementation evidence required |
| Manifest/rendition hash or locale substitution | Domain-separated hashes and exact preview-bound locale/rendition | Canonical conformance review required |
| Approval forgery or unauthorized activation | Attributable evidence, maker-checker separation and complete approval chain | Administrative threat model required |
| Registry compromise or rollback/replay | Immutable history, current eligibility revalidation and new attributable activation | Incident recovery design required |
| Oversize, truncation or decompression bomb | Pre-parse byte limits, compression prohibited initially, exact terminal framing | Representative payload measurement required |
| Parser differential or malicious document | Restricted grammar, exact parser corpus, passive text only | Backend/mobile differential testing required |
| Unicode spoofing or bidi manipulation | NFC, confusable/bidi validation and human rendition review | Approved locale profile required |
| CDN/cache poisoning | No CDN initially; any future CDN validates origin, complete keys, immutable hashes and withdrawal | Separate CDN authorization required |
| Compromised build or mobile client | Client checks are defense in depth; server revalidates complete tuple and continuity | Supply-chain/mobile hardening remains required |
| Retrieval denial of service or repeated abuse | Bounded rate/request limits and non-enumerating backoff | Thresholds require operational evidence |

The design has a credible scale path: immutable renditions can be content-addressed and horizontally cached behind an authenticated bounded read, while registry state remains server-owned. It does not require a new microservice; the modular Booking boundary can later be extracted if measured load justifies it.

Mobile/client integrity is defense in depth. A compromised client cannot create authoritative acknowledgment or confirmation because the server revalidates the complete immutable tuple and authenticated continuity. If CDN use is ever separately authorized, it requires authenticated origin validation, complete cache keys, immutable integrity-checked bytes, withdrawal revalidation, poisoning defenses and no delegation of authorization to the CDN.

## Alternatives rejected

- **Embed every document in route preview:** rejected because it couples routing and legal-content availability, repeats large content and weakens independent caching and controls.
- **Treat current `content_hash` as a localized rendition hash:** rejected because the admitted V1 contract has no locale/rendition identity; reinterpretation would create ambiguous evidence.
- **Bundle policy prose in the mobile app:** rejected because content can become stale, bypass server rotation and conflate deployment with approval.
- **Public unauthenticated document endpoint initially:** rejected because it cannot prove preview ownership and expands enumeration; it may be reconsidered only for non-authoritative informational copies.
- **Automatic English fallback or runtime translation:** rejected because it can present unapproved or legally nonequivalent content.
- **Arbitrary HTML/Markdown:** rejected because active content, remote resources and parser differences expand security and integrity risk.
- **Offline acknowledgment from cache:** rejected because immediate withdrawal/rotation cannot be authoritatively checked offline.
- **Database-backed registry now:** rejected because this architecture increment authorizes no schema and the approved operating/promotion model is unresolved.

## Open human, legal and product decisions

Before implementation or user-facing activation, AYO requires:

1. qualified Ethiopian advice on electronic consent, consumer and transport disclosures, evidence and withdrawal;
2. approved policy wording and the legally required language set;
3. named native-language review for every activated Amharic, Afaan Oromo or other rendition;
4. product decisions on explicit language choice, comprehension support and unavailable states;
5. accessibility review of reading order, screen-reader semantics, text scaling and comprehension;
6. privacy/legal decisions on content cache and future acknowledgment retention;
7. an approved withdrawal, emergency correction, no-grace/grace and rotation operating procedure;
8. app-store policy review where applicable;
9. security review of registry administration, promotion separation, rate limits and monitoring;
10. CTO review of this architecture and any later implementation design; and
11. Founder/CEO approval by Ibrahim Hambentu Shibiru before content promotion or activation.

Legal sufficiency, required languages, retention duration, approval roles, service levels and production thresholds remain unresolved. Engineering must not guess them.

## Proposed later implementation scope

Only after the required architecture and human approvals, a separately authorized passive implementation may add:

- versioned backend consent document/rendition models and a read-only authority interface;
- explicit activation composition using synthetic/non-production fixtures only until content approval;
- a versioned preview metadata contract with exact locale/rendition binding;
- one authenticated rider-owned immutable document read;
- strict backend and mobile canonical-format parsers and hash verification;
- bounded in-memory retrieval/cache behavior only, unless durable storage receives separate approval;
- focused contract, authorization, rotation, malformed-content, weak-network and cross-rider tests; and
- corresponding architecture, roadmap and decision updates.

That implementation must still contain no real policy prose, active production document, acknowledgment UI, confirmation/recovery capability, normal provider composition, schema/migration, dependency change or production activation unless each receives separate authorization.

## CI evidence consequences

- This architecture-only increment changes documentation and must not modify `.github/workflows/ci.yml`.
- The admitted `mobile-booking-intent-foundation` and `booking-consent-policy-authority` evidence modes remain immutable historical contracts.
- A later implementation requires a new exact evidence mode rather than widening either historical selector.
- Expected evidence must bind the exact changed-file manifest, backend/mobile/test trees, versioned schema, canonical hash vectors, exact locale selection, cross-rider denial, immediate rotation/withdrawal, no silent fallback, malformed-content rejection, bounded size/cache behavior and continued absence of mobile acknowledgment, confirmation, recovery, durable storage, UI/navigation and production authority.
- It must also cover V1/V2 downgrade resistance, closed-scope uniqueness, authentication continuity, account-isolated memory caching, failure-matrix behavior, approval-transition invariants, emergency withdrawal, rollback, Unicode/bidi handling, replay, denial of service and complete threat negative controls.
- Linux dependency, warning and complete line-sensitive secret inventories must be recaptured. Package/lockfile drift remains fatal unless separately authorized.
- Backend broad, PostgreSQL where applicable, MyPy, migration, security, cleanup and candidate-tree evidence remain required. No historical evidence substitutes for the new execution.

## Production prohibition

This proposal is PRE-PRODUCTION only. It creates no policy content, legal approval, endpoint, registry activation, acknowledgment, confirmation, recovery, deployment or release authority. Existing dependency-release blocks remain active. Production activation is prohibited and requires separately reviewed legal, product, native-language, accessibility, security, CTO and Founder/CEO decisions plus implementation and controlled evidence.
