# Implementation Increment 5 — Immediate Dispatch Handoff and Global Localization

**Status:** Implemented locally under CTO/CEO authorization; awaiting review. No public
route, deployment, production activation, commit or push is authorized.

## Scope and authority

This increment connects an authenticated `READY_FOR_DISPATCH` Immediate Standard
request to the existing Immediate Dispatch authority through a durable one-way handoff.
Ride Request continues to own request validation and pre-assignment cancellation.
Dispatch alone owns candidate filtering, sequential offers and assignment. Driver Trust
owns eligibility evidence. Active Ride, Pricing, Payments, Mission 20 and AI remain
inactive or advisory as previously approved.

`READY_FOR_DISPATCH` means eligible for consideration; it is not an assignment. The
handoff contains identifiers, approved versions, timestamps and lineage only. Private
rider notes and presentation strings are excluded.

## Dispatch contract and lifecycle

The handoff records its stable ID, ride/request/rider references, service type,
pickup/destination references, zone identity and version, validation decision, request
version, policy versions, expiry, correlation/causation identities, idempotency identity
and audit reference. Receipt revalidates the authoritative request and latest successful
validation decision and fails closed on stale or unsupported state.

Candidate filtering requires current eligible Driver Trust evidence, an approved vehicle,
current driver-to-vehicle authorization, Immediate Standard capability, fresh availability,
pickup accessibility and no conflicting commitment. Ranking is deterministic by pickup
cost first, then valid heading consistency and a stable identifier tie-break. It contains
no opaque AI score and cannot delay pickup for a marginal theoretical improvement.

Offers follow `CREATED -> ACCEPTED | REJECTED | EXPIRED | CANCELLED | SUPERSEDED`.
Responses are versioned, expiry checked and idempotent. PostgreSQL row locks and partial
unique constraints ensure one active assignment per request and no conflicting active
driver assignment. Assignment, events and outbox writes are atomic. Cancellation locks
the handoff before offers, preventing a deadlock and deterministically resolving an
acceptance/cancellation race without financial consequences.

Internal events are versioned, privacy-minimised, correlation-linked and persisted with a
transactional outbox. Restart and response-loss recovery reads authoritative PostgreSQL
state; duplicate delivery returns the canonical result.

## Global localization contract

Localization is presentation-only. The foundation validates BCP 47 tags and stores an
authenticated identity's preferred language, optional device language, ordered acyclic
fallback chain and optimistic version. Language-pack manifests contain metadata only:
pack version, text direction, format profiles, offline-manifest reference and approval
time. Downloadable pack contents do not belong in PostgreSQL.

Authoritative domains persist reason codes and versioned translation keys. Switching a
language cannot mutate ride, dispatch, eligibility, financial, policy or audit state.
Missing packs/keys produce privacy-safe telemetry and a bounded fallback; they do not
block valid dispatch work. Direction metadata supports right-to-left presentation, and
format profiles preserve future plural, date, number and currency handling.

Legal, safety, emergency, identity, pricing and financial wording is accepted only from
human-reviewed approved packs. AI translation can later be an identified temporary
advisory fallback for non-consequential general content only and has no official wording
or decision authority.

## Persistence and rollback

Migration `20260716_0017` adds handoffs, candidate-set metadata, offers, assignments,
dispatch idempotency/events/outbox, language preferences and language-pack manifests.
It adds scoped internal permissions and downgrades to `20260716_0016`; the tables contain
no fare, payment, wallet, Mission 20 or translated-prose authority.

Rollback disables any future consumer, drains or quarantines unpublished outbox work,
verifies there are no relied-upon assignments, and downgrades one revision. Existing
Ride Request and Driver Trust records remain intact.

## Remaining decisions

Leadership and Ethiopian operations must still approve service zones, availability and
offer timeouts, pickup-cost/ETA providers, destination disclosure rules, fatigue and
commitment policy, driver location retention, initial language packs and fallback order,
human translation review workflow, terminology for Ethiopian addresses and landmarks,
and public/mobile activation. Scheduled, Airport, Active Ride, Pricing and notification
integration require separate increments.

Mission 20 remains disabled and `ARRIVAL_WAITING_ENABLED` remains false.
