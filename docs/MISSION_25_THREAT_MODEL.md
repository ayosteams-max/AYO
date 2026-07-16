# Mission 25 — Threat Model

| Threat | Primary controls | Safe failure |
|---|---|---|
| Fare/route/GPS spoofing | integrity-checked observations, provenance, plausibility, review | suppress/review |
| Fake wait/cancellation farming | Mission 20 multi-signal evidence, continuity, notification gate | no consequence |
| Referral/promotion/device farms | bounded eligibility, one-benefit identity, graph anomaly reference | hold entitlement |
| Collusion/airport/bonus gaming | cross-event anomaly evidence, separation of duties | specialist review |
| Cash fraud | multi-party/provider evidence, reconciliation, immutable claims | unsettled/disputed |
| Insider policy change | least privilege, maker-checker, signed publication, immutable versions | reject/unpublish successor |
| Replayed/tampered quote | opaque ID, integrity tag, expiry, idempotency, accepted-version binding | conflict/requote |
| Currency/rounding manipulation | allow-listed ISO currency, integer minor units, deterministic rounding | calculation failure |
| Promotion stacking | explicit composition graph and caps | reject ambiguity |
| Tax evasion/misconfiguration | approved legal basis, Finance reconciliation, audit | block publication |
| Support social engineering | case-scoped RBAC, redaction, dual approval for remedies | no financial action |
| AI/model manipulation | no price tools/publication authority, allow-listed retrieval | deterministic fallback |

Policy publication is separately authorized from drafting. Audit captures actor, reason,
before/after hashes, approvals and effective window without logging protected fraud
signals or unnecessary location. Anomaly evidence never silently punishes a party.

