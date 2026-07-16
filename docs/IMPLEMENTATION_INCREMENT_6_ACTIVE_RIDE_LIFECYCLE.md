# Implementation Increment 6 — Active Ride Lifecycle Foundation

**Status:** Implemented locally under CTO/CEO authorization; awaiting review. No public
route, deployment, automatic commit or push is authorized.

## Outcome and authority

Active Ride is the sole post-assignment lifecycle authority. It starts only from a
PostgreSQL-authoritative Immediate Dispatch assignment and preserves source assignment,
handoff, request, rider, driver, vehicle and policy lineage. Ride Request continues to
own pre-dispatch request state; Dispatch owns candidates, offers and assignment. Active
Ride cannot assign a driver, calculate a fare, move money or activate Mission 20.

The canonical lifecycle is:

```text
DRIVER_ASSIGNED
  -> DRIVER_EN_ROUTE
  -> DRIVER_ARRIVED
  -> PICKUP_CONFIRMED
  -> RIDE_IN_PROGRESS
  -> DESTINATION_ARRIVED
  -> COMPLETED
```

Explicit terminal alternatives are `DRIVER_CANCELLED`, `RIDER_CANCELLED`,
`SUPPORT_INTERRUPTED` and `SYSTEM_INTERRUPTED`. They record lifecycle fact only. They
assign no blame and create no fee, refund, penalty or compensation.

The earlier Mission 19 states remain readable for compatibility. New authoritative
handoffs enter only `DRIVER_ASSIGNED` and follow the canonical transition map. Removing
the older representation before consumers migrate would be an unsafe rewrite and is
therefore deferred.

## Commands, ownership and localization

Driver commands are limited to assigned-driver progress and driver cancellation. Rider
cancellation is limited to the owning Rider. Pickup confirmation and system interruption
require a server service identity. Support interruption requires Staff or Administrator
identity. Callers cannot supply owner, assigned driver or authoritative state.

Every command requires an expected aggregate version and stable command ID. PostgreSQL
locks the aggregate; the idempotency hash binds command, payload and ride ID. Duplicate
identical retries return the canonical result, changed replay fails, and concurrent stale
commands produce one winner. Privacy-safe not-found behavior prevents ownership leaks.

Domain state stores stable reason codes and translation keys only. New lifecycle results
return localization references such as `active_ride.driver_en_route`; no user-facing
language is embedded in lifecycle policy.

## Event source, recovery and audit

Each transition appends an immutable, monotonically sequenced event containing previous
state, next state, policy version, reason code, bounded evidence references and a
translation key. The current aggregate is a locked projection of that stream. Replay
verifies contiguous sequence and exact agreement between event-derived and stored state.

The transition, projection checkpoint, idempotency result and transactional outbox
message commit atomically. Bounded `events_after` recovery supports reconnect, offline
clients, response loss and worker restart without mobile connectivity. A sequence ahead
of the server fails with an explicit resync requirement. Duplicate event identities and
ride/sequence pairs are rejected by PostgreSQL.

## Inactive future integration points

Consumers must use versioned outbox events and must never update Active Ride tables.
The following seams are documented but no consumer is implemented or activated:

| Event / projection | Future consumer | Permitted future purpose | Authority retained |
|---|---|---|---|
| `active_ride.driver_assigned` | AYO Family, AYO Status | Privacy-approved assignment/status notification | Active Ride owns state; consent service owns sharing |
| `active_ride.driver_en_route` | AYO Status, AYO Family | Coarse progress/status projection | No live location disclosure without purpose/consent |
| `active_ride.driver_arrived` | Mission 20 | Arrival-evidence input only | Mission 20 separately verifies arrival and remains disabled |
| `active_ride.pickup_confirmed` | Trust Engine, AYO Status | Verified pickup reference and status | Trust remains advisory unless separately authorized |
| `active_ride.ride_started` | AYO Family, Trust Engine | Consent-scoped trip status and anomaly evidence | No safety or restriction authority transfers |
| `active_ride.destination_arrived` | AYO Status | Arrival projection | Active Ride alone completes the ride |
| `active_ride.ride_completed` | Pricing, AYO Wallet/Ledger, AYO Status, Growth Engine, Driver Support Bonus | Future fare-input readiness, immutable posting instruction, progression, referral/promotion/loyalty and bonus eligibility | Pricing calculates; Ledger moves money; each programme owns approved eligibility |
| cancellation/interruption events | Support, Recovery, Trust | Case creation and evidence references | No automatic blame, penalty, refund or restriction |

AYO Wallet, AYO Status, AYO Family, Growth Engine, Driver Support Bonus and Trust Engine
must each use an idempotent inbox keyed by event ID, minimum necessary fields, explicit
schema compatibility and independent feature flags. A consumer outage cannot roll back
or block an otherwise valid lifecycle transition. Family sharing requires separate
consent, participant authorization, expiry and location-minimization approval. Growth,
promotion, loyalty and bonus consumers cannot infer financial eligibility from completion
alone and cannot encourage unsafe work.

The event envelope preserves inactive extension metadata for future Airport Standard,
Airport Premium, Scheduled, multi-stop, parcels, food and marketplace logistics. These
products require separately approved state/policy modules; their presence as schema seams
does not activate them.

## Persistence and rollback

Revision `20260716_0018` adds source-link and policy fields plus partial unique indexes to
the existing Active Ride aggregate. It supports an empty database, an existing revision
17 database and downgrade to revision 17. Rollback first disables any future lifecycle
consumer, drains or quarantines revision-18 outbox work, verifies no canonical active
ride depends on the new source fields, then downgrades. Completed history must be retained
or exported under approved retention policy before a production rollback.

## Risks and open decisions

- Ethiopian operations must approve driver/rider cancellation and interruption reason
  taxonomies; this increment deliberately creates no consequences.
- Pickup confirmation evidence policy needs separate safety and operations approval.
- Support-interruption permissions, staffing and recovery/resumption policy remain open.
- Precise event/location retention and Family consent rules need Ethiopian legal/privacy
  review.
- Consumer ordering, dead-letter operations and capacity thresholds require load evidence
  before public activation.
- Mission 20 remains disabled and `ARRIVAL_WAITING_ENABLED` remains false.
