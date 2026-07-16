# Mission 23 — Threat Model

| Threat | Control | Verification |
|---|---|---|
| GPS spoof/replay | Fresh sequence, plausibility, integrity reference, uncertainty gate | Replay/drift/routes |
| Fake availability/account sharing | Server lease, session/device assurance, active-work invariant | Hijack/concurrency |
| Offer manipulation/bots | Signed context, deadline, idempotency, rate/device anomaly escalation | Bot/race tests |
| Collusion/repeated cancellation | Evidence linkage and specialist review; no hidden score | Synthetic rings/appeal |
| Dispatch DoS/enumeration | Auth, quotas, bounded search, opaque IDs, generic projections | Load/IDOR |
| Cross-zone/airport gaming | Authoritative zone/staging lease and policy version | Boundary/queue tests |
| Insider/policy abuse | Least privilege, dual approval, effective-dated immutable policy/audit | Privilege/change tests |
| Model poisoning/evasion | Provenance, shadow, dataset governance, drift/fallback | Adversarial evaluation |
| Privacy leakage | Role/phase minimisation, coarse candidate summaries, retention | Schema/log review |

AI and maps are untrusted providers. Candidate lists, precise unrelated locations,
restricted safety/fraud reasons and future-rider identity never leave authorized boundaries.
