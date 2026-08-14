# Mobile Booking Intent Foundation Architecture

Status: **PRE-PRODUCTION, preview-only, confirmation locked.** It is not wired into normal application composition. Deployment and production activation are prohibited.

## Bounded purpose

This foundation prepares one authoritative Booking route preview for weak-network mobile use without duplicating backend authority. It implements strict place-result, preview-request, and preview-response validation; authenticated place/preview transport; one immutable in-memory preview intent; deterministic duplicate and cancellation handling; and a non-visual presentation context.

Production mobile source can search places and request `/mobile/booking/route-previews`. It contains no executable confirmation submission, confirmation recovery, outcome-unknown reconciliation, dispatch, provider, payment, notification, analytics, screen, route, or navigation authority. Confirmation response parsing is deferred with confirmation/recovery implementation to a separately authorized increment.

## Identity and lifecycle

Context consumers provide only strictly validated pickup and destination input. The provider obtains the opaque current identity-continuity handle from established authenticated session composition and constructs its preview engine around that same handle; no controller, continuity reader, state producer or store is accepted through provider props or exposed through context. A bounded construction seam accepts only raw preview transport plus value-only identifier-generator and clock dependencies for deterministic tests. The importable engine is a pure preview mechanism, not authenticated authority by itself; the provider composition is the enforceable continuity boundary, and no JavaScript module-secrecy claim is made.

The engine internally generates the local intent ID, backend `client_preview_id`, client-created opaque `booking_session`, pickup ID, and destination ID. The UUID values are produced by `crypto.randomUUID`; booking session uses the backend's 32-to-128-character opaque-safe syntax. All five outputs are validated and an immediate duplicate is rejected before state or dispatch. Cleared historical identifiers are not retained merely to prove global uniqueness; cryptographic generation is the bounded collision control. Place search returns a `place_reference`, while the current backend pickup/destination request models contain no place-reference field and independently define client/default UUID identities, so generated entity IDs do not replace a wire lineage field.

One normalized deeply frozen request is captured. Exact plain-record validation rejects custom prototypes, inherited/accessor/non-enumerable fields and symbol extras without invoking getters. JavaScript Proxy traps cannot be made side-effect-free and are not represented as a security guarantee. Identical concurrent preview calls join one promise; conflicting calls fail locally; authentication refresh cannot replace the request or its identifiers.

The executable lifecycle is `draft -> previewing -> confirmation_locked`, with bounded `failed_safe` and `stale` outcomes. Retirement and clearing erase the evidence-bearing store. There is no `preview_ready`, confirmation-pending, outcome-unknown, recovery, or confirmed state. A successful response becomes `confirmation_locked` atomically. Expiry is checked while parsing, before locking, and whenever cached state is read; equality is expired.

Identity replacement, logout, unmount, dependency replacement, cancellation, retirement, or explicit clearing invalidates the active generation, aborts its request where possible, erases request and preview evidence, and suppresses late success or failure. Flight ownership is installed before transport executes, and finalization is scope-owned so synchronous or asynchronous failures cannot strand an old flight or clear a newer one. Operation results distinguish locked, failed, stale, cancelled, retired, cleared, superseded, conflicting, and invalid input without fabricating success.

## Data, privacy, and authority

The bounded memory store holds at most one active intent. Pickup/destination input is retained only while needed for the active preview operation and is removed after locking or any terminal invalidation. It stores no rider-selected identity, access or refresh token, policy prose, raw backend payload, route geometry, unnecessary location history, provider credential, confirmation identifier, confirmation idempotency key, or dispatch authority. It uses no durable device storage and makes no process-death recovery claim.

Every serialized request field is validated against the existing FastAPI/Pydantic contract before dispatch. Every response field is validated before projection, including exact field inventory, enums, strict Booleans, geographic/numeric bounds, toll consistency, ETB currency, identifiers, timestamps, expiry, quote lineage, and opaque consent metadata. Mobile never calculates fare, selects policy, invents consent, or treats legacy-unbound evidence as current.

Backend Booking remains authoritative for identity authorization, routing, fare, consent metadata, preview validity, confirmation, recovery, and dispatch. Real consent presentation, confirmation, and recovery require separate Founder/CTO, legal, product, and native-language authorization, approved policy prose, a reviewed mobile authority boundary, and production consent configuration. Amharic operational wording remains `NEEDS_NATIVE_AMHARIC_REVIEW`.

No backend, schema, migration, dependency, lockfile, workflow, production configuration, provider, payment, notification, analytics, deployment, or activation change is included.
