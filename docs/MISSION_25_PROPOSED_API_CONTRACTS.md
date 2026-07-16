# Mission 25 — Proposed API Contracts

Documentation only; no route is authorized.

| Proposed command/query | Caller | Result/boundary |
|---|---|---|
| `POST /pricing/estimates` | authorized booking context | versioned expiring estimate |
| `POST /pricing/estimates/{id}/accept` | owning rider/business grant | accepted version or conflict |
| `POST /pricing/rides/{id}/finalize` | Active Ride service | final/review decision; no settlement |
| `POST /pricing/rides/{id}/recalculate` | authorized Recovery/Pricing role | linked correction proposal |
| `GET /pricing/rides/{id}` | role-scoped Rider/Driver/Support/Finance | redacted explanation projection |
| `POST /pricing/consequences/evaluate` | governed orchestration | eligible/suppressed/review only |
| `GET /pricing/policies/{id}/{version}` | authorized operations/audit | immutable policy metadata |
| `POST /pricing/policies/publish` | maker-checker admin | future effective version |
| `POST /incentives/eligibility/evaluate` | governed service | entitlement recommendation |
| `POST /settlement-instructions/prepare` | Pricing/Recovery workflow | instruction proposal only |

All commands use authenticated service/user context, RBAC, resource ownership, strict
schemas, bounded request size, rate limits, idempotency and expected versions. Responses
include decision/policy IDs, currency/minor units, reason codes, data quality and audit
reference. Client-supplied user, fare, commission, tax or entitlement is never authority.

Events use transactional outbox and include `pricing.estimate_produced`,
`pricing.estimate_accepted`, `pricing.final_calculated`, `pricing.review_required`,
`pricing.corrected`, `pricing.consequence_suppressed`, `incentive.entitlement_decided`
and `pricing.settlement_instruction_prepared`. Consumers deduplicate by event ID and
aggregate version.

