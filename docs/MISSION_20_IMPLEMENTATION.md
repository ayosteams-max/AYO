# Mission 20 — Implementation and Verification Record

Date: 2026-07-16
Status: **Implementation approved for local preservation only; PostgreSQL 17 certification pending.**

## Scope and authority

Implement the approved evidence-only Smart Arrival, Rider Readiness and Waiting module
inside the modular monolith. Active Ride retains lifecycle authority, Dynamic Pickup
retains pickup authority, Pricing retains fee authority, and Support/Recovery retain
review authority. Mission 20 performs no cancellation, fee, paid wait, refund,
compensation, wallet/ledger mutation, blame, provider integration or activation.

## Pre-implementation risk and edge-case register

| Risk / edge case | Likelihood / impact | Mitigation | Residual risk / owner | Verification |
|---|---|---|---|---|
| GPS drift or proximity-only false arrival | High / High | Require zone, freshness, accuracy, stationarity and approach corroboration | Field calibration / CTO+Operations | Drift, stale and false-arrival tests |
| Spoofed, replayed or out-of-order location | Medium / High | Authenticated driver, bounded timestamps/sequences, idempotency and stale-version rejection | Device attestation deferred / Security | Replay, ownership and stale tests |
| Driver triggers wait then leaves | Medium / High | Continuous zone evidence; policy-driven pause/invalidation | Real map accuracy / Operations | Leave-zone and continuity tests |
| Rider readiness reveals sensitive context | Medium / High | Derived classifications only; no private-building claim; no protected inputs or raw trail in projection/log | Retention/legal approval / Privacy | Privacy and prohibited-input tests |
| Notification spam or delivery treated as receipt | Medium / Medium | Cooldown, cap, material-change gate; distinct intent/delivery evidence | Provider delivery semantics deferred / Product | Anti-spam and failure tests |
| Missing/ambiguous policy | Medium / High | Versioned deterministic resolution and fail closed | Launch configuration / Operations | Precedence, ambiguity and effective-date tests |
| Mid-session policy change | Medium / High | Immutable snapshot per session | Emergency override policy / CEO+Operations | Snapshot/versioning tests |
| Accessibility context disadvantaged | Medium / High | Explicit accommodation selector; cannot shorten base protection | Values require local review / Legal+Operations | Accessibility policy tests |
| Airport zone/staging ambiguity | High / High | Separate Standard/Premium context; authoritative zone/version required; suppress on confusion | Airport authority data / Operations | Airport separation/confusion tests |
| Landmark ambiguity or poisoned correction | High / Medium | Provider-neutral verified contract; ambiguous fallback; never promote submission | Landmark implementation deferred / Operations | Ambiguity/provenance tests |
| Weak network, stale map/ETA or notification outage | High / High | Server time, freshness bounds, pause/suppress, deterministic degraded projection | Field measurements / CTO | Outage and uncertainty tests |
| External disruption unfairly attributed | Medium / High | Explicit external evidence and suppression; insufficient responsibility by default | Verification sources / Operations | Closure/weather/emergency tests |
| Concurrent start/pause/no-show commands | Medium / High | Row lock, optimistic version and command idempotency | Database availability / CTO | Concurrency and retry tests |
| Partial database/outbox write | Low / High | One transaction for state, evidence and outbox | Restore/recovery readiness / CTO | Rollback and integration tests |
| Unbounded evidence/location growth | Medium / High | Store bounded decisions and references, not trails; indexed per-ride records | Retention job separately gated / Privacy | Schema/query review and benchmark |
| Fee/blame authority leakage | Low / Critical | No financial fields/actions; evidence recommendation only; prohibited public schemas | Future integration / CTO+CEO | Contract and forbidden-field tests |

No unaccepted critical risk is introduced by the bounded local implementation. Real
providers, production activation, retention enforcement, airport authority data,
Ethiopian policy values and field-calibrated thresholds remain launch blockers.

## Requirements-to-test mapping

Arrival maps to deterministic signal, drift, freshness, heading and false-arrival tests.
Readiness maps to deterministic, privacy, freshness and cooldown tests. Waiting policy
maps to precedence, ambiguity, effective date, accessibility, severe-weather and airport
separation tests. Waiting maps to verified-start, countdown, pause, invalidation and
restart tests. Evidence readiness maps to every prerequisite and suppression reason.
Persistence/API maps to migration parity/downgrade, transaction/outbox, idempotency,
authorization, ownership, request bounds, rate limiting and concurrency tests.

## Implementation and verification

The bounded modular-monolith implementation is approved for local preservation and
disabled by default. It adds deterministic arrival and rider-readiness evaluation, immutable
waiting-policy snapshots, waiting continuity and evidence-only no-show evaluation,
provider-neutral landmark and airport inputs, authenticated projections/commands,
PostgreSQL repositories, transactional outbox intents and reversible migration 0014.

Verified on 2026-07-16: Ruff format and lint passed; strict mypy passed for the new
deterministic domain core; 167 non-integration tests passed with one known pre-existing
prototype xfail and 70.26% branch coverage; the 5,000-evaluation benchmark completed in
0.03 seconds; Bandit passed; and the local dependency audit reported no known
vulnerabilities. PostgreSQL 17 integration, concurrency, restart/recovery and migration
upgrade/downgrade certification remain blocked because no PostgreSQL service is present
and the official Windows 17.10 installer download returned HTTP 403. This is a failed
quality gate, not an accepted skip. Production activation, public routes, deployment and
push are prohibited until a separately recorded certification and activation approval.

Rollback is: keep `ARRIVAL_WAITING_ENABLED=false`, stop the bounded waiting worker,
drain or discard only unpublished Mission 20 outbox intents under an approved operating
procedure, downgrade migration `20260716_0014` to `20260716_0013`, and revert the
uncommitted application changes. No fee, ledger or ride-lifecycle compensation is
required because Mission 20 has no such authority.

## CTO final capability review amendment

The provider-neutral landmark contract now supports multiple bilingual named pickup
points typed as main gate, emergency entrance, terminal, taxi bay, side entrance or
venue-defined pickup point. Each point carries a confidence-bearing exact driver stop
coordinate/heading/curb side and static bilingual approach text. A separate injected
walking-route contract accepts a fresh rider observation and returns expiring,
confidence-bearing distance, duration and bilingual turn guidance to that approved
point; no external map provider is selected or connected.

The server-time countdown projection is identical in state/deadline semantics for rider,
driver and authorized Support, with an explicit audience label. Waiting remains durable
and server-authoritative across client restart, sleep and battery-saving behavior.
Temporary GPS/network uncertainty pauses according to the immutable policy and a valid
later observation resumes the session while extending the deadline by the measured pause
duration. University, stadium and market contexts join the existing airport, hospital,
hotel, shopping-centre and residential configuration dimensions.

An optional `PickupReferencePhotoReference` is metadata-only future extension data:
opaque reference/version, verification/provenance, bilingual accessible description and
validity window. It contains no image bytes, URL, storage design or provider authority;
using or publishing photos remains separately approval-gated.
