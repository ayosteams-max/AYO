# Mission 25 — Proposed Persistence Model

Documentation only; no migration is authorized.

| Aggregate/table concept | Purpose and important constraints |
|---|---|
| `pricing_policies` / `pricing_policy_versions` | immutable draft/published versions, effective window, approval/hash |
| `pricing_component_rules` | ordered applicability, rounding, cap and explanation key |
| `fare_estimates` | input snapshot, components, totals, expiry, integrity and data quality |
| `fare_acceptances` | estimate/version/actor/time and idempotency |
| `fare_calculations` | append-only estimate/final/correction lineage |
| `fare_evidence_refs` | typed purpose-scoped opaque evidence references |
| `consequence_decisions` | eligible/suppressed/review, Mission 20 references and reasons |
| `commission_snapshots` | prospective policy applied to the ride |
| `incentive_programmes` / `incentive_entitlements` | immutable rules and separate eligibility result |
| `tax_policy_versions` / `tax_components` | approved jurisdiction/legal-basis metadata and calculation |
| `settlement_instruction_proposals` | prepared, not posted; correlation/idempotency |
| `cash_collection_claims` / `reconciliation_cases` | conflicting claims and review state |
| `pricing_audit_records` | privacy-minimized decision/actor/version hashes |
| `pricing_outbox` | atomic events, attempts and delivery state |

Amounts are integer minor units with explicit currency and checked arithmetic. Unique
keys enforce idempotency and one accepted policy snapshot; optimistic aggregate versions
reject stale writes. Append-only calculations and approvals are never updated in place.
Raw GPS, identity documents, protected fraud signals and provider credentials remain in
their owning domains.

Partition first by bounded time/ride or programme only after measurement. Index ride,
decision, policy/version, state/created time and outbox availability. Use pagination,
retention/legal-hold policy, encryption, backup/restore and point-in-time recovery.
Transactional boundaries cover calculation plus audit/outbox, not external payment.

