# Mission 26 — Risk Register

| ID | Risk | L/I | Mitigation/verification | Owner/residual |
|---|---|---|---|---|
| M26-R01 | AYO wallet classified as regulated stored value | M/C | legal/NBE classification; careful wording | Legal; open blocker |
| M26-R02 | Prototype balances imported as money | M/C | quarantine and evidenced opening reconciliation | Finance; open blocker |
| M26-R03 | Ethiopian safeguarding/settlement rules unknown | M/C | provider/legal/Finance review | Legal; open blocker |
| M26-R04 | Ledger imbalance/duplicate posting | L/C | DB invariants, idempotency/property/concurrency tests | Engineering; low |
| M26-R05 | Cash claims inaccurate | H/H | corroboration and exceptions | Operations; medium/high |
| M26-R06 | Provider unknown outcome causes duplicate | M/C | query/reconcile, never blind retry | Payments; medium |
| M26-R07 | Payout takeover/redirection | M/C | step-up, destination controls, dual review | Security; medium |
| M26-R08 | Refund plus chargeback duplicates recovery | M/H | linked case/provider/ledger controls | Finance; medium |
| M26-R09 | Card data expands PCI scope | M/C | hosted/tokenized flow and assessor review | Security; open |
| M26-R10 | Multi-currency accounting error | M/C | defer FX; currency-separated books | Finance; low until enabled |
| M26-R11 | Insider adjustment/report abuse | M/C | maker-checker, audit, anomaly alert | Finance/Security; medium |
| M26-R12 | Provider lock-in/outage | H/H | adapters, canonical states, reconciliation | Payments; medium |
| M26-R13 | Regulatory/reporting retention conflict | M/H | legal-hold and approved schedules | Legal/Privacy; open |
| M26-R14 | AI triggers transaction | L/C | no tool permission or execution path | Security; low |

No critical risk is accepted. R01–R03 block wallet/payment implementation decisions.
