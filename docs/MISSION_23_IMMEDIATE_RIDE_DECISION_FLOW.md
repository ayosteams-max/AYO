# Mission 23 — Immediate Ride Decision Flow

1. Validate authenticated request, references, idempotency and active-ride invariant.
2. Classify Immediate and validate city/service/pickup zone.
3. Query fresh availability leases in the smallest configured radius.
4. Apply service, accessibility, safety, compliance and active-work hard gates.
5. Reject stale, replayed, implausible or low-confidence availability.
6. Straight-line shortlist, then bounded routed ETA/heading/direction enrichment.
7. Rank primarily by confident pickup ETA, then bounded uncertainty, rider aging and
   equivalent-candidate opportunity correction.
8. Atomically reserve and create one exclusive server-timed offer.
9. Idempotent acceptance locks; decline/expiry releases and suppresses immediate repeat.
10. Expand radius only after bounded failure; never wait for marginal score improvement.
11. Exhaustion produces typed no-supply/recovery status and audit.

Acceptance/cancellation predictions remain advisory and cannot create hidden punishment.
