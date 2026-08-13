# Immediate Standard Rider/Driver Public Contract and Weak-Network Architecture

Status: **CTO approved and Founder/CEO implementation-authorized on 2026-08-11. PRE-PRODUCTION only.**

## Problem and outcome

AYO's authoritative Immediate Standard cash-ride application-service chain is certified,
but a lost Booking-confirmation response could not be recovered through an authoritative
read keyed by the rider's durable client intent. A later mobile client must not infer that
a ride exists, create a replacement intent, or access internal repositories after a
timeout or process restart.

The bounded outcome is a stable authenticated public contract over the existing Booking,
Dispatch, Active Ride and Post Trip authorities. Success means an identical retry returns
the original result, a rider can recover Booking confirmation by the original
`client_request_id`, stale or conflicting commands fail closed, and role-specific reads
remain minimized. This does not implement Rider or Driver screens.

## Decision and alternatives

Use the existing public routes and add only a rider-owned Booking confirmation recovery
read. The recovery query joins the persisted Booking confirmation to its canonical Ride
Request and requires both records to belong to the authenticated rider. Its response
includes the immutable FareEstimate, EstimateAcceptance and pricing-lineage identifiers.

Alternatives rejected:

- A new Ride Journey aggregate or projection framework would duplicate existing domain
  authority and add cross-domain consistency risk without solving a proven need.
- Replaying POST forever is idempotent but does not provide the required authoritative
  read after response loss or process restart.
- Client-side reconstruction from cached quote or ride data would move authority into an
  untrusted device.
- WebSockets, push and background synchronization add provider and operating complexity;
  polling and existing idempotent commands are sufficient for this contract increment.

Build and operating cost are low: one bounded indexed relational read and no new worker,
provider, dependency, schema, cache or service. The join follows existing unique Rider
Request client-identity constraints and has a credible horizontal database scaling path.

## Authority and public contracts

- **Booking:** owns preview and confirmation orchestration. `POST /api/mobile/booking/confirm`
  remains the idempotent mutation. `GET
  /api/mobile/booking/confirmations/by-client-request/{client_request_id}` is the
  authoritative response-loss/process-restart recovery read.
- **Pricing:** remains sole authority for FareEstimate, EstimateAcceptance and pricing
  lineage. The public response displays identifiers only and never calculates money.
- **Dispatch:** existing driver-mode, current-offer, offer-response and rider-status routes
  retain assignment authority and hide candidate ranking and decision internals.
- **Active Ride:** existing role-safe snapshot, bounded event polling and optimistic,
  idempotent lifecycle commands remain authoritative.
- **Post Trip:** existing owned summary, cash-confirmation and receipt projection remain
  authoritative. A cash confirmation is operational evidence, not digital settlement or
  proof that AYO owns physical cash.
- **Support:** the purpose/case/permission-bound Support ride-evidence application remains
  staff-only. This increment creates no rider/driver Support authority or public Support
  projection.

## Weak-network and retry contract

1. A mobile client creates and durably retains one random `client_request_id`, one
   idempotency key and the immutable command payload before dispatching a Booking command.
2. An identical retry uses the same key and payload. A changed payload with the same key
   fails as `idempotency_conflict`.
3. If a response is lost, the client reads confirmation using the original
   `client_request_id`. `404 booking_confirmation_not_found` means no authoritative
   confirmation is currently visible; it is not permission to fabricate state.
4. After recovery, the rider polls canonical Dispatch status using the returned
   `ride_request_id`. Active Ride recovery uses the returned `active_ride_id`, snapshot
   version and bounded event sequence.
5. Active Ride commands retain their original command ID and expected aggregate version.
   Stale versions fail closed; identical replays return the already-confirmed result.
6. Authentication refresh never changes command, rider, ride or idempotency identity. An
   identity/session change retires the local intent until authoritative reconciliation.
7. Polling responses are authoritative. Cached client state is explicitly pending or
   stale and cannot advance Ride, Pricing, Dispatch, cash or accounting state.

## Security, privacy and financial controls

- Identity is resolved from the trusted server authentication context.
- Recovery does not accept a rider identity and returns no cross-rider confirmation.
- Public Booking confirmation contains only confirmation, Ride Request and immutable
  pricing-lineage references plus public state/recovery guidance.
- Internal candidate lists, scores, other drivers, accounting instructions, journal lines,
  Support evidence and sensitive audit data remain absent.
- Missing, partial or contradictory canonical pricing lineage fails closed.
- No production accounting model, fare, commission, tax, remittance rule or payment rail
  is selected or exposed.

## Risk and edge-case register

| Risk | Control and verification | Residual risk / owner |
|---|---|---|
| Lost Booking response creates a duplicate ride | Durable client intent, server idempotency and owned recovery read | Mobile MVP must persist the intent before network dispatch; Mobile mission |
| Cross-rider client-request probing | Query binds Ride Request and confirmation to authenticated rider; unknown and foreign values return bounded not-found | Rate limiting and enumeration monitoring remain activation concerns; Security/Operations |
| Partial pre-0059 confirmation appears authoritative | Public response requires complete pricing lineage and otherwise fails `pricing_unavailable` | Historical PRE-PRODUCTION records are not auto-upgraded; CTO review before data admission |
| Dispatch did not start after confirmation | Recovery response directs the client to canonical Dispatch status; retry uses the original confirm intent | Public composition/worker activation remains separately gated; Operations |
| Stale or duplicated lifecycle command | Existing expected-version and command-ID rules | Mobile presentation must distinguish stale, pending and outcome unknown; Mobile mission |
| Excess polling under weak networks | Existing bounded reads and rate limits; clients honor server polling guidance | Load/SLO thresholds require controlled environment evidence; CTO/Operations |
| Cash wording implies settlement | Existing Post Trip fields and receipts remain server-authoritative; documentation explicitly separates evidence from settlement | Native Amharic and Ethiopian legal/accounting review remain required |

No accepted risk authorizes production activation.

## PRE-PRODUCTION and deferred work

All relevant feature flags remain disabled by default and prohibited from unsupported
production composition. AP-073's Immediate Standard public-contract implementation required
no booking schema migration. The certified current Alembic head is `20260812_0060`;
separate forward-only migration `20260812_0060` repairs the `cash.reconciliation.execute`
permission seed and is included in the same certified candidate. No provider, credential,
live map, SMS, push, payment, identity proofing,
AI or realtime connection is added.

Deferred to separately authorized missions: Rider/Driver screens and navigation, durable
device-side command storage, production offline synchronization, device/network matrix
testing, native Amharic review, Support operations UI, legacy-route retirement, controlled
environment activation and every production policy/provider decision.

# Consent binding clarification

Booking recovery does not authorize the client to invent consent metadata. A new route preview binds the server-required consent version and document hash into canonical route evidence. First confirmation must acknowledge that exact binding while it remains the current mandatory policy, before any mutable continuation. Immediate policy rotation requires a new preview and deliberate acknowledgment; a recovery `404`, expiry, or rotation never authorizes a replacement booking. Legacy unbound previews cannot be upgraded by assumption. Canonical confirmed recovery remains rider-scoped and read-only.
