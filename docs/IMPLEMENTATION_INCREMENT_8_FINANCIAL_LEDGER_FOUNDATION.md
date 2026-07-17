# Implementation Increment 8 — Financial Ledger Foundation

**Status:** Architecture and implementation authorized for local development under CTO/CEO instruction. No payment provider integration, wallet product, settlement, payout, refund, promotion, referral, loyalty or production activation is authorized by this increment.

## 1. Problem and beneficiaries

AYO has immutable pricing lineage but does not yet have an immutable financial ledger authority. Without a ledger foundation, AYO cannot guarantee balanced postings, deterministic replay, or auditable correction handling once cash and digital financial systems are introduced.

Beneficiaries:
- Riders and drivers who need trustworthy financial history.
- Finance and operations teams that need reconciliation-ready records.
- Security and audit stakeholders that need immutable append-only evidence.
- Future payment, wallet and settlement modules that need one financial source of truth.

Success criteria for this increment:
- Ledger postings are append-only and immutable.
- Every posting is balanced per currency (double-entry invariant).
- Idempotent posting prevents duplicate journals.
- Posting is traceable to Pricing and ride lifecycle lineage.
- Corrections are compensating journals linked to predecessor journals.
- Ledger can reconstruct account balances from immutable entries.
- Ledger performs no payment execution.

## 2. Scope and explicit exclusions

In scope:
- Enterprise ledger domain contracts and invariants.
- PostgreSQL ledger persistence model.
- Ledger posting repository with fail-closed validations.
- Traceability linkage from pricing financial lineage to ledger lineage.
- Migration, permissions and automated tests.

Out of scope (explicitly excluded):
- Payment provider adapters and webhook handlers.
- Wallet product views or mutable balances.
- Settlement instruction logic.
- Driver payout workflows.
- Refund orchestration.
- Promotions, referrals and loyalty economics.
- Tax policy engine.

## 3. Architecture decision and alternatives

### Recommended design (selected)

Use an immutable PostgreSQL double-entry subledger with:
- Ledger books and immutable journals.
- Journals containing two or more entries.
- Per-journal currency consistency.
- Atomic journal posting with strict balance checks.
- Append-only events and outbox for future consumers.
- Idempotency reservation keyed by actor, operation and key.
- Immutable traceability chain from ride and pricing artifacts.

Why selected:
- Enforces financial integrity at write time.
- Supports deterministic replay and reconstruction.
- Preserves modular-monolith simplicity and existing patterns.
- Avoids provider lock-in and premature distributed architecture.

### Alternative A (rejected): mutable account balances

Pros:
- Fast initial implementation.

Cons:
- Race-prone updates and difficult correction lineage.
- Weak auditability and replay guarantees.
- Violates constitutional immutable-finance principles.

### Alternative B (rejected): provider-ledger authority

Pros:
- Reduced local accounting implementation effort.

Cons:
- Incomplete cash/offline semantics.
- Vendor lock-in and weak internal audit lineage.
- Cannot represent AYO business obligations independently.

### Alternative C (rejected): distributed ledger/blockchain

Pros:
- External tamper narrative.

Cons:
- Unnecessary cost/complexity for current mission.
- Privacy and correction workflow burden.
- No measured need in current operating phase.

## 4. Data model and invariants

Core entities:
- `ledger_books`: logical accounting scope and currency policy metadata.
- `ledger_accounts`: chart of accounts entries with class and normal side.
- `ledger_journals`: immutable posted journals with business-event lineage and predecessor link.
- `ledger_entries`: immutable debit/credit entries for each journal.
- `ledger_idempotency`: canonical replay guard for posting operations.
- `ledger_events` and `ledger_outbox`: append-only event evidence and future integration seam.

Mandatory invariants:
- Entry amounts are positive integer minor units.
- Journal contains at least two entries.
- Journal is balanced by currency: total debits == total credits.
- Journal entries cannot mix currencies.
- Posted journals are immutable.
- Compensations create a new journal linked by predecessor.
- Duplicate idempotency with changed payload fails closed.

## 5. Immutable traceability lineage

Every posted journal stores immutable lineage references to:
- Ride Request
- Dispatch Handoff
- Assignment
- Active Ride
- Fare Estimate
- Fare Calculation
- Financial Traceability snapshot hash
- Previous Ledger Journal (when compensating)

Future reserved nullable linkage fields are included for:
- Wallet
- Settlement
- Driver Payout
- Rider Payment
- Refund
- Promotion
- Referral
- Loyalty
- Tax
- Audit package

The ledger does not populate future-owner IDs in this increment; it only preserves forward-compatible seams.

## 6. Concurrency, idempotency and fail-closed behavior

- Posting is transactionally atomic: journal, entries, events and outbox persist together.
- Idempotency record is inserted first with canonical request hash.
- Existing idempotency with same hash returns canonical posted journal ID.
- Existing idempotency with different hash is rejected (`idempotency_conflict`).
- Balance or lineage mismatch rejects the entire transaction.
- Unknown account, unknown predecessor, or cross-ride lineage mismatch rejects posting.

## 7. Security and AI boundary

- Ledger mutation authority is limited to authorized server/service identities.
- Runtime role receives append/read privileges; no update/delete on ledger rows.
- Sensitive payloads are minimized in events/outbox.
- AI may read summarized ledger state through approved projections only.
- AI has no permission or code path to post, reverse, compensate or otherwise mutate ledger state.

## 8. Future integration points

Future modules consume this foundation through bounded contracts:
- Pricing -> Ledger: settlement-ready posting instructions.
- Payments -> Ledger: provider-attempt outcome postings.
- Wallet projections -> Ledger: derived balances and statements.
- Reconciliation -> Ledger: external mismatch cases and correction journals.
- Customer Recovery/Finance -> Ledger: maker-checker compensating adjustments.
- Tax/Reporting -> Ledger: jurisdictional reporting projections.

All future integrations must append, never mutate prior history.

## 9. Risk register (Increment 8)

1. Chart-of-accounts governance risk.
Mitigation: immutable account creation and explicit class/side constraints; finance approval required for production mappings.

2. Idempotency misuse risk.
Mitigation: canonical payload hashing and strict conflict failure; integration tests for concurrent posting races.

3. Traceability drift risk between pricing and ledger.
Mitigation: persist full lineage snapshot and enforce cross-check against source calculation lineage.

4. Multi-currency extension risk.
Mitigation: enforce single-currency journals now; reserve FX fields and clearing-account seams for separately approved increment.

5. Over-privileged runtime mutation risk.
Mitigation: migration grants only append/read permissions and test assertions that update/delete remain denied.

6. Operational replay/reconciliation performance risk.
Mitigation: indexed account/journal lookup paths and deterministic event ordering; defer partitioning until measured thresholds.

## 10. Why each key design decision is chosen

- Double-entry journals: chosen to mathematically enforce value conservation.
- Append-only immutable rows: chosen for auditability and legal defensibility.
- Compensating corrections: chosen to preserve historical truth while allowing fixes.
- Integer minor units: chosen to avoid floating-point rounding defects.
- Idempotent posting with canonical hash: chosen to make retries safe under weak networks and worker restarts.
- Transactional outbox: chosen to preserve future integration seams without adding a broker now.
- Strict lineage requirements: chosen to make financial reconstruction deterministic and eliminate inference.
- Payment-execution exclusion: chosen to preserve authority boundaries and reduce safety/compliance risk in this increment.

## 11. Approval gate note

This document is the pre-code architecture/risk/integration rationale required for Increment 8 implementation. Code, migration and tests that follow must remain within this boundary and stop at the next CTO/CEO review gate.
