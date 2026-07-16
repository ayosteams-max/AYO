# Mission 23 — Offer Strategy Comparison

| Strategy | Permitted use | Key controls and recovery |
|---|---|---|
| Sequential exclusive | Immediate default | One driver/ride lock, short timeout, decline suppression, radius expansion |
| Bounded batch | Only approved hot-zone/tail-wait experiment | Tiny capped set, no uncontrolled race, first atomic valid acceptance, losers notified, shadow first |
| Reservation offer | Scheduled planning/commitment | Explicit window, commitment version, replacement rules, fallback |
| Pre-dispatch offer | Healthy near-complete current ride | No distraction/overlap, buffer, transparent rider copy, auto release |
| Airport queue | Verified staging/queue/product | Queue lease, terminal/access checks, separate Standard/Premium |
| Emergency redispatch | Assignment failure/safety-directed recovery | Owning authority trigger, priority reason, bounded scope, full audit |

All offers use server deadlines, idempotent response, optimistic/row lock, one semantic
winner and explicit expired/duplicate/race outcomes. Uncontrolled broadcast is rejected:
it creates distraction, contention and rider uncertainty.
