# Mission 23 — Failure and Recovery Matrix

| Failure | Deterministic recovery |
|---|---|
| Driver offline/cancels/rejects/timeout | Release exact lease/offer once; suppress immediate repeat; continue bounded cycle |
| Rider cancels | Atomically stop offers/locks; Active Ride owns later lifecycle branch |
| Duplicate acceptance | Same response for same command; one atomic winner; stable loser result |
| Stale GPS/weak network/drift | Exclude or uncertainty downgrade; never infer online state |
| Map outage | Bounded geometric fallback/ETA band or fail closed by policy |
| Database interruption | No local assignment; retry idempotently after authority returns |
| Worker restart/out-of-order event | Lease expiry, checkpoint, sequence/version validation and replay |
| Commitment conflict | Scheduled conflict policy and specialist/operations evidence |
| Airport closure | Stop zone offers, preserve/recover commitments, approved fallback |
| Current-trip delay | Release/replan pre-dispatch and notify role-safe status |
| Insufficient supply | Bounded expansion, honest rider projection, Operations recommendation |

Every path records causation, prior/new state, policy version, actor, time and outbox/audit.
