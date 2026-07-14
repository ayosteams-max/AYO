# AYO Session and Rate-Limit Persistence Architecture

## Scope

This foundation provides durable storage contracts for future Authentication. It
does not authenticate a person, issue or accept tokens, set cookies, define login
policy, authorize resources, expose routes, or activate PostgreSQL application
traffic. Future Authentication must separately approve session durations, renewal,
device controls, credential format and customer-facing failure behavior.

## Research comparison

| Option | Reliability and failure | Scale/cost/complexity | Decision |
|---|---|---|---|
| PostgreSQL sessions | Durable revocation, backups and existing operations | Adequate initial indexed lookups; one existing platform | Selected source of truth |
| Redis-only sessions | Fast, but eviction/outage/persistence gaps can lose revocation | Adds service; lowest latency | Rejected as authority |
| PostgreSQL + Redis sessions | Durable authority plus fast cache | Invalidation, outage and consistency paths | Deferred until measured need |
| Database fixed-window limiter | Atomic and simple | Boundary bursts; one write per request | Not selected |
| Database sliding-window log | Accurate rolling limits | High row/index/cleanup cost | Rejected initially |
| PostgreSQL token bucket | Smooth refill, bounded storage, atomic row lock | Hot-key serialization and DB write load | Selected durable baseline |
| Redis atomic/Lua limiter | Sub-millisecond distributed counters | New provider/service and failover semantics | Future accelerator |

PostgreSQL documents that `ON CONFLICT DO UPDATE` has an atomic insert-or-update
outcome under concurrency. Redis supports atomic counters and Lua rate limiters at
very high throughput, but Redis persistence/replication configurations can retain a
data-loss window. OWASP requires server-side session expiry and invalidation and
recommends meaningless, high-entropy session identifiers.

## Session contract and privacy

`SessionRecord` contains an opaque UUID, opaque subject identifier, a 32-byte token
fingerprint, UTC creation/expiry/last-seen/revocation times, safe revocation reason
and optimistic version. No raw session token, password, OTP, authorization header,
IP address, device identifier or personal profile is stored.

The supplied token material must be generated later by an approved cryptographically
secure mechanism with at least 128 bits of entropy. This mission only provides a
SHA-256 lookup fingerprint helper and rejects short input. Hashing is not encryption;
low-entropy identifiers would remain guessable and are prohibited.

Expiry and revocation are server-side. Active lookup requires an unrevoked record
whose expiry is later than the supplied aware time. Revocation is persistent,
idempotent for the same safe reason and conflicting for a different reason. Sessions
have no ordinary delete repository method; retention cleanup requires separate
approval and audit.

## Rate-limit contract and algorithm

The provider-neutral `RateLimiter.consume` accepts only a 32-byte fingerprint, a
bounded named policy and integer cost. It returns allowed, decimal remaining tokens
and bounded retry delay. It never receives a raw IP, phone, email, device ID or
credential. Callers must construct privacy-reviewed high-entropy or keyed
fingerprints in the future; this mission does not establish identity policy.

PostgreSQL inserts the bucket if absent, locks the exact `(key_hash, policy_name)`
row, refills using database UTC time and decimal arithmetic, then consumes atomically.
Workers therefore share one decision. Different keys proceed independently; no
global lock exists. Policy capacity is bounded to one million and refill period to
one day. Policy values are future security/product decisions, not set here.

## Failure behavior

- PostgreSQL session lookup/revocation failure is surfaced. No cache result may
  override durable revocation after a Redis accelerator is added.
- A required rate-limit storage error raises and cannot silently become `allowed`.
  Future callers must map this to an approved fail-closed or degraded response based
  on endpoint risk; Authentication owns that policy.
- Database outage therefore prevents protected state change rather than creating an
  unrevoked session or bypassing a required limit.
- No external call occurs in the Unit of Work. Redis is not deployed.
- Retries are safe: session IDs/token fingerprints are unique, revocation is
  one-way, and token consumption is atomic. A caller must not retry an uncertain
  consumed request without a separately approved command idempotency strategy.

## Database and privileges

Migration `20260715_0003` creates `ayo.sessions` and
`ayo.rate_limit_buckets`. Session indexes support token uniqueness, subject lookup,
expiry and active-subject lookup. Rate buckets use a composite primary key and one
cleanup index. This avoids unnecessary write-amplifying indexes.

Public privileges are revoked. An existing `ayo_runtime` receives only schema
`USAGE` and table `SELECT`, `INSERT`, and `UPDATE`; it receives no `DELETE`,
`TRUNCATE`, `REFERENCES`, or `TRIGGER`. The migration role remains owner. Expiry
cleanup must run under a separate, narrowly approved maintenance role in bounded
batches and must never erase evidence that retention policy requires.

## Capacity and Redis migration gate

The PostgreSQL token bucket performs one row lock and update per decision. Hot keys
serialize by design so capacity cannot be overspent. Measure p50/p95/p99 decision
latency, lock wait, pool saturation, rate-limit writes/second, hot-key frequency,
table/index growth and denied ratio.

Redis becomes justified only when measured PostgreSQL load or latency breaches an
approved SLO after query/pool tuning. A future hybrid must provide:

1. Provider-neutral Redis adapter with atomic script/versioning.
2. PostgreSQL-authoritative session revocation and cache invalidation.
3. Defined Redis outage behavior with no revocation bypass.
4. Clock, replication, eviction and failover tests.
5. Bounded TTLs, key pseudonymization and no raw identifiers.
6. Reconciliation/metrics proving cache decisions remain safe.

## Operations and security monitoring

Monitor session create/revoke conflicts, active/expired counts, lookup latency,
bucket decision latency, row-lock waits, error rate, denial rate, pool use, storage
growth and cleanup lag. Logs must never include token/key hashes, subject IDs, raw
identifiers or policy keys. Audit event IDs may link future session lifecycle events
after Authentication adopts the Mission 5 foundation.

Backups/PITR include sessions; restore readiness must prove revocation survives.
Rate buckets are reconstructable protective state, but must not be silently cleared
during an incident because that could remove active abuse limits.

## Unresolved decisions

- CEO/CTO-approved authentication risk tiers, session idle/absolute/renewal times,
  limiter policies and user-facing failure messages.
- Ethiopian privacy/legal treatment and retention for session, abuse and network
  identifiers, including lawful pseudonymization and staff access.
- Managed Redis provider/region/cost only after the migration gate is met.
- Cleanup schedule, maintenance role and incident override process.
