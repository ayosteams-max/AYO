# Mission 26 — Financial Threat Model

| Threat | Controls | Safe outcome |
|---|---|---|
| Duplicate/replayed command or webhook | idempotency, signature, timestamp/nonce, unique keys | original result/no repost |
| Provider impersonation/key compromise | allow-listed endpoint, managed rotating keys, incident revocation | quarantine evidence |
| Client-forged success/fare/identity | authenticated server context and provider verification | reject |
| Ledger imbalance/tampering | DB balance constraints, append-only journals, audit/hash checkpoints | transaction rollback/alert |
| Payout/refund redirection | verified destination, step-up, cooldown, maker-checker | hold/review |
| Account takeover/social engineering | Mission 24 assurance, case isolation, no support override | block financial action |
| Cash/ride/collusion fraud | corroboration and anomaly evidence | dispute/review, no hidden punishment |
| Insider adjustment | least privilege, separation of duties, dual approval, alerts | reject/compensate |
| Card/mobile credential leakage | hosted/tokenized flow, no CVV/PIN, vault references | scope containment/incident |
| Race/negative available balance | atomic posting/reservation, row/version locks | one winner/conflict |
| Rounding/currency confusion | integer minor units, single-currency accounts | validation failure |
| Provider outage/unknown result | status query, reconciliation, no blind retry | honest pending |
| AI prompt/manipulation | no financial tools or authority, redacted evidence | advisory discarded |
| Report/export leakage | scoped RBAC, masking, expiring exports, audit | deny/revoke |

Fraud detection produces versioned risk evidence and recommendations. Freezes,
restrictions, reversals and reports to authorities require approved deterministic policy
and authorized humans; AI confidence never bypasses these boundaries.
