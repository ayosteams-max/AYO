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
- Mobile Booking is authenticated for its intended route-preview use and stops at `confirmation_locked`; its provider remains outside normal application composition.
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

The existing V1 `content_hash` remains a legacy document-level commitment with its existing semantics. It must not be renamed or reinterpreted in place. A later versioned metadata contract must add the manifest, rendition, locale, format and rendition hash explicitly. Mobile presentation must reject V1 metadata as insufficient rather than guessing a rendition. A preview created under the future contract binds the complete new metadata tuple into its canonical evidence hash.

Acknowledgment must eventually bind to the exact `rendition_id`, locale, format and `rendition_content_hash` displayed, as well as policy version and document identity. A general policy-version acknowledgment is insufficient.

## Delivery-contract comparison and recommendation

### Embed content in route-preview responses

Advantages are one network round trip and atomic receipt of preview plus content. Disadvantages are materially larger preview responses, repeated policy transfer, coupled routing/document failures, poorer conditional caching, harder independent size controls, and greater risk that clients treat changed embedded content as interchangeable metadata. It also makes a routing retry carry legal content unnecessarily.

### Separate authenticated immutable read

Advantages are bounded preview responses, strict document-specific limits, conditional retrieval, independent rate limiting, cache reuse, clearer failure classes and direct verification against the exact preview-bound tuple. It keeps the document service replaceable without moving Booking authority to mobile. The cost is one additional read and explicit weak-network handling.

### Decision

Recommend a separate authenticated, read-only consent-document delivery contract. A future V2 preview request includes one canonical requested consent locale. The server selects exactly one approved rendition and binds its full tuple to the preview. The later document read is keyed by the preview evidence identity; it does not let mobile select a policy version, document, hash or substitute rendition. The server resolves the authenticated rider, proves preview ownership and current validity, then returns only that bound rendition. Conditional retrieval may use the bound rendition hash as a strong validator.

Changing language requires a new preview with an explicitly requested approved locale. This avoids changing the legal content underneath an existing quote or acknowledgment flow. If no exact approved rendition exists, preview/document presentation fails closed.

## Authentication and authorization

- The recommended initial contract is authenticated and rider-role restricted. This preserves preview ownership and prevents cross-account evidence association.
- The read accepts no rider identifier. The server derives identity from the trusted authentication context and requires the preview to belong to that identity.
- Anonymous/public delivery could improve CDN caching, but it would sever the ownership check and expand enumeration and scraping surface. It is rejected for the initial contract. A later public-copy decision would require separate threat, legal and operational review and could not authorize acknowledgment.
- The contract is read-only. No mobile policy creation, approval, publication, withdrawal or translation capability exists.
- Apply bounded per-identity and per-network rate limits, request-size limits and abuse monitoring without logging content, tokens, preview identifiers or rider-sensitive data unnecessarily.
- Authentication failures remain generic. Unknown, foreign and unavailable preview/document combinations must not reveal registry membership or another rider's activity.

## Localization and fallback

- Use canonical BCP 47 language tags constrained by an explicit approved registry. Initial candidates are English `en`, Amharic `am` and Afaan Oromo `om`; listing them does not approve content or require launch support.
- A future preview request may specify exactly one supported consent locale. The server normalizes only an explicitly documented equivalent spelling/case representation, never semantic language substitution.
- The selected locale and rendition are server-bound to the preview and returned exactly.
- No silent fallback is permitted. Missing English, Amharic, Afaan Oromo or other requested content returns a stable rendition-unavailable result.
- A rider may explicitly choose another available, approved language only through a new preview, and only if product/legal review confirms that choice is sufficient. English is not automatically legally equivalent to a missing Ethiopian-language rendition.
- Runtime machine translation, AI-authored legal content and client-side translation are prohibited. Human native-language approval is mandatory per rendition.
- Mixed-language and accessibility variants require distinct reviewed rendition identities when their canonical bytes differ.

## Format and strict parsing

The proposed initial format is `application/vnd.ayo.booking-consent+json;version=1`, UTF-8 only, containing passive plain text in a shallow exact schema:

- one schema marker;
- the immutable identity and locale fields;
- one bounded title string;
- an ordered array of at most 32 sections;
- each section has one immutable section identifier, one bounded heading and one bounded plain-text body; and
- one bounded accessibility block containing language, reading order and heading relationships only.

Proposed engineering bounds for later approval are 64 KiB canonical bytes, a maximum JSON nesting depth of three, at most 32 sections, at most 160 Unicode scalar values per title/heading and at most 4,096 per section body. The parser must reject duplicate keys, unknown fields, custom/non-plain structures, invalid Unicode, non-NFC text, CR/CRLF, missing terminal LF, forbidden control characters, invalid ordering, excess depth/count/size and arithmetic inconsistencies.

The canonical hash input is the exact normalized UTF-8 byte serialization defined by the versioned schema: fixed field order, fixed JSON separators, NFC strings and LF-only terminal newline. Implementations must use one shared conformance corpus; they must not hash a platform-dependent parser dump.

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

- Initial rotation remains `immediate_mandatory`; no grace period is proposed.
- Activating a replacement version or withdrawing a document/rendition invalidates affected unconfirmed previews and any acknowledgment eligibility immediately.
- Effective interval checks use authoritative UTC time; `now == effective_until` is expired.
- Content bytes are immutable. Any byte change requires a new rendition identity and hash; a semantic policy change also requires a new policy version and document manifest.
- Withdrawal is distinct from retirement. Withdrawal blocks presentation and confirmation immediately; retirement is historical lifecycle state after it is no longer eligible.
- Conditional cache validators do not override registry status. A cache hit cannot prove that content remains active.
- If content changes after preview and before display, acknowledgment or confirmation, the operation fails closed and the rider must obtain a new preview. No server or client substitutes the replacement silently.
- A grace-period model is deferred to explicit legal/product approval and a new architecture decision.

## Weak-network and cache behavior

- Safe retries repeat the same read for the same preview identity. Reads are side-effect-free and return the same immutable bytes while the binding remains active.
- A strong conditional validator may be the quoted rendition content hash. A not-modified response is usable only when the locally cached bytes independently hash to that exact value and the server has just reconfirmed eligibility.
- Cache keys include schema version, policy family/version, document ID, rendition ID, locale, format and rendition hash. They include no token, rider identity, location or mutable display state.
- Cache storage, if later authorized, must be app-private, bounded, integrity-checked and evicted on logout/account replacement. Whether it must be encrypted requires the later mobile storage threat model; this proposal creates no durable storage claim.
- Cached text may be shown as explicitly offline informational content only if product/legal review allows. Offline display is never acknowledgment-eligible because the client cannot prove immediate withdrawal or rotation status.
- No offline acknowledgment or confirmation is authorized. Retrieval uncertainty produces a deterministic unavailable state and no false success.
- Timeouts, cancellation and identity replacement retain the existing stale-completion suppression model. A response for an obsolete preview, locale or identity is discarded.

## Privacy and retention

The future client may minimally retain, subject to separate storage approval:

- rendition identity and hash;
- policy/document version identities;
- locale and format;
- effective interval; and
- retrieval timestamp for cache management, not as proof of acknowledgment.

It should avoid retaining duplicate policy bodies, raw envelopes, tokens, rider identity, precise location, route geometry or unrelated personal data. Document content is not assumed harmless merely because it is common across riders. Logs and analytics must not contain content, identifiers that expose rider activity, authentication material or raw failures.

The server may retain immutable approval and publication evidence outside the rider delivery response. Legal retention periods, acknowledgment evidence retention, deletion exceptions and cross-account device behavior require qualified legal/privacy decisions; this proposal does not choose a duration.

## Approval and promotion governance

Proposed future content lifecycle:

`DRAFT -> LEGAL_REVIEW -> PRODUCT_REVIEW -> NATIVE_LANGUAGE_REVIEW -> ACCESSIBILITY_REVIEW -> CTO_VERIFIED -> FOUNDER_APPROVED -> SCHEDULED -> ACTIVE -> WITHDRAWN/RETIRED`

- Every transition is explicit, attributable, immutable and auditable; rejection returns to a new draft version rather than editing approved history.
- Required review is per exact canonical rendition bytes. Changing content invalidates downstream approvals.
- Legal, product, native-language and accessibility reviewers approve only their bounded responsibility.
- CTO verification confirms technical integrity and activation prerequisites; it is not legal approval.
- Founder approval must be attributable to **Ibrahim Hambentu Shibiru, Founder & CEO**.
- Software deployment and content promotion remain distinct separated duties with maker-checker controls.
- AI may prepare comparisons, validate schema/hash/consistency and flag risks. It may not invent legal wording, translate an approved legal document for activation, impersonate a reviewer, or create Founder approval.

No approval or lifecycle transition is recorded as completed by this proposal.

## Stable failure model

Future public responses should map internal detail into bounded classes:

- `consent_document_unavailable`;
- `consent_rendition_unavailable`;
- `consent_locale_unsupported`;
- `consent_version_mismatch`;
- `consent_integrity_mismatch`;
- `consent_document_expired`;
- `consent_document_withdrawn`;
- `consent_preview_mismatch`;
- `consent_document_malformed`;
- `authentication_required`; and
- `temporarily_unavailable`.

Unknown and foreign resources must not disclose registry or rider existence. Internal approval provenance, unpublished versions, withdrawal reasons, stack traces, hashes beyond the rider's own bound tuple and operational details remain private. Malformed, ambiguous or unclassified output is fatal, never converted to success.

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
| Cross-rider preview probing | Authenticated rider identity and preview ownership check | Rate-limit thresholds require operational evidence |
| Runtime machine translation changes meaning | No runtime translation; exact approved rendition only | Required launch languages need legal/product decision |
| Cache survives rotation or account change | Online eligibility check; bounded eviction; no offline acknowledgment | Durable cache design requires separate threat review |
| Active markup executes or tracks rider | Passive strict JSON/plain text; no URLs, embeds or scripts | Future media requires a new format decision |
| Deployment activates unapproved content | Separate approval/promotion authority and maker-checker controls | Operational roles need leadership approval |
| Registry outage blocks Booking | Fail closed with stable unavailable state; independent read scaling/caching | Availability SLO requires measured evidence |
| Hash canonicalization differs by platform | Versioned canonical bytes and shared conformance corpus | Implementation libraries chosen later |
| Withdrawal races acknowledgment | Server revalidates current state at acknowledgment/confirmation | No grace policy is approved |
| Logs expose content or rider activity | Bounded error taxonomy and content/identifier log prohibition | Monitoring design remains later scope |

The design has a credible scale path: immutable renditions can be content-addressed and horizontally cached behind an authenticated bounded read, while registry state remains server-owned. It does not require a new microservice; the modular Booking boundary can later be extracted if measured load justifies it.

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
7. an approved withdrawal, emergency correction and rotation operating procedure;
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
- Linux dependency, warning and complete line-sensitive secret inventories must be recaptured. Package/lockfile drift remains fatal unless separately authorized.
- Backend broad, PostgreSQL where applicable, MyPy, migration, security, cleanup and candidate-tree evidence remain required. No historical evidence substitutes for the new execution.

## Production prohibition

This proposal is PRE-PRODUCTION only. It creates no policy content, legal approval, endpoint, registry activation, acknowledgment, confirmation, recovery, deployment or release authority. Existing dependency-release blocks remain active. Production activation is prohibited and requires separately reviewed legal, product, native-language, accessibility, security, CTO and Founder/CEO decisions plus implementation and controlled evidence.
