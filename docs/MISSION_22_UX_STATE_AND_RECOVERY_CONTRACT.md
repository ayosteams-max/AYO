# Mission 22 — UX State and Recovery Contract

Status: **Documentation proposal only.**

## Projection contract

Every screen consumes `projection_version`, `aggregate_version`, `last_sequence`,
`server_time`, `generated_at`, freshness by subprojection, `presentation_state`, allowed
actions and stable public reason codes. The client records `local_display_time` only for
animation/countdown interpolation; it cannot establish domain time.

Commands include command/idempotency ID, expected aggregate version and bounded typed
payload. UI states are `READY_TO_SEND`, `SENDING`, `CONFIRMED`, `REJECTED`,
`INDETERMINATE` and `RESYNC_REQUIRED`. Only a server receipt produces `CONFIRMED`.

## Recovery matrix

| Failure | Display | Recovery |
|---|---|---|
| Slow request | Name operation and elapsed stage | Continue, cancel request where safe, or create Support case |
| Network loss | Last confirmed state + timestamp | Adaptive retry then snapshot reconciliation |
| App restart | Encrypted minimum cached projection | Authenticate and fetch after last sequence |
| Device sleep/battery saver | Mark visual freshness | Recompute from server time/deadline, then refresh |
| GPS temporarily unavailable | Explain reduced pickup confidence | Follow server pause/suppression projection; never fake continuity |
| Event gap/out of order | Stop applying incremental state | Bounded buffer then authoritative snapshot |
| Duplicate tap/retry | Preserve one pending command | Reuse idempotency key and show original receipt |
| Provider/map outage | Textual confirmed pickup and fallback | Provider-neutral fallback; no invented ETA/route |
| Mission 20 disabled | Hide smart-wait claims | Use Active Ride status and ordinary pickup help |

Offline-safe items are cached vehicle/driver match, confirmed pickup/destination labels,
emergency affordance and last known status. Raw location trails, PINs, identity documents,
payment credentials and internal evidence are not persisted for presentation recovery.
