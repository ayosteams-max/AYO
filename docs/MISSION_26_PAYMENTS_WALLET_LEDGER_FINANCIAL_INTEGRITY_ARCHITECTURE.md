# Mission 26 — Payments, Wallet, Ledger and Financial Integrity Architecture

Date: 2026-07-16
Status: **Architecture approved by CTO/CEO on 2026-07-16 for documentation
preservation. No implementation, provider, transaction or activation authorized.**

## Problem, beneficiaries and success

AYO must account for cash and future digital rides without duplicated earnings,
invented balances, provider-dependent truth or unauditable corrections. Riders, drivers,
businesses, Finance, Support and auditors benefit. Success means every movement balances,
retries are harmless, provider and cash positions reconcile, payout/refund status is
truthful, explanations are role-safe and no prototype balance becomes trusted money.

## Current-state finding

`BACKEND/services/wallet_service.py` is an early mutable aggregate with hard-coded
commission, direct balance updates, short transaction identifiers and no durable atomic
double entry. Its route accepts caller-supplied driver identity. It is preserved only as
legacy prototype behavior; it is neither production wallet nor migration source of
financial truth. No runtime change is authorized here.

## Evidence and constraints

- The National Bank of Ethiopia publishes the current payment-system regulatory
  framework and a register distinguishing payment-instrument issuers and payment-system
  operators. Provider licensing/status must be verified at contracting and launch, not
  inferred from a brand name.
- NBE reports EATS operating on ISO 20022, supporting provider-neutral structured
  references as a future compatibility goal, not requiring AYO to operate settlement
  infrastructure.
- PCI DSS applies when cardholder data is stored, processed or transmitted. AYO should
  minimize scope through hosted/tokenized provider boundaries; exact applicability
  requires provider and qualified assessor review.

Sources accessed 2026-07-16: NBE payment-system directives, licensed-provider register,
2026 Financial Stability Report and EATS announcement; PCI SSC DSS v4.0.1 resources.
These are architecture evidence, not legal advice or provider approval.

## Options and recommendation

| Approach | Benefits | Risks/cost | Position |
|---|---|---|---|
| Mutable wallet balances | Simple prototype | Unbalanced, race-prone, unauditable | Rejected |
| Immutable double-entry ledger with derived wallets | Reconciliation, audit, replay safety | More accounting and operational discipline | Recommended |
| Provider ledger as AYO truth | Faster integration | Lock-in, incomplete cash/business semantics | Rejected as authority |
| Blockchain/distributed ledger | Tamper narrative | Unnecessary cost, privacy and correction complexity | Rejected |

Use a PostgreSQL double-entry subledger inside the modular monolith. Wallets are
role-specific projections over ledger accounts, not mutable pots. Payments orchestrates
licensed-provider attempts and evidence. Ledger alone posts balanced journals. Provider
adapters, cash claims and Pricing instructions are untrusted until validated by their
own deterministic workflows.

## Authority and financial invariant

Pricing calculates amounts and prepares versioned instructions; Payments owns external
authorization, capture, refund and payout attempt state; Reconciliation compares AYO,
provider, bank and cash evidence; Ledger alone records money movement. Customer Recovery
authorizes approved remedies. Finance approves controlled manual adjustments. AI may
summarize or flag anomalies but cannot authorize, post, release, reverse, refund or pay.

For each posted journal and currency: total debits equal total credits; entries are
append-only; a business event/idempotency key posts at most once; corrections are linked
compensating journals; balances are derived; currency never converts implicitly.

## Wallet products and regulatory boundary

Driver, rider and business wallets are distinct projections with available, pending,
reserved, restricted and obligation views appropriate to role. A rider refund balance or
business credit is not approved stored value. Diaspora payer, traveller/rider and ride
beneficiary are separate participants with consent, refund destination and disclosure.
AYO Pay is a future regulated product boundary: it cannot emerge from naming an internal
ledger view a wallet. Licensing, safeguarding, redemption and customer-funds treatment
require separate leadership and qualified Ethiopian legal/NBE review.

ETB is the primary launch ledger currency. Multi-currency readiness uses separate
currency ledgers, explicit minor-unit metadata and separately authorized FX quotes;
cross-currency journals must use approved clearing/FX accounts and never balance unlike
currencies against each other.

## Reliability, privacy and scale

Commands are authenticated, authorized, idempotent, version-checked and transactional.
Provider webhooks enter an append-only inbox after signature, timestamp and replay
validation; processing and outbox publication are recoverable. Unknown outcomes remain
pending and are queried/reconciled—not retried blindly. Partitioning by ledger book/time
is evidence-driven; bounded account queries and snapshots prevent full-history scans.

Do not store raw PAN, CVV, mobile-money credentials, bank secrets or unnecessary payer
identity. Token references remain provider-scoped. Financial telemetry excludes payment
credentials and personal data. Audit access is least-privilege and separation-of-duties
controlled.

## Gates and exclusions

No code, migration, dependency, provider integration, wallet/ledger, numeric limit,
transaction, production route, AYO Pay, commit, push or activation is authorized.
Mission 20 remains disabled with `ARRIVAL_WAITING_ENABLED = False`; all required
PostgreSQL certification gates remain mandatory.
