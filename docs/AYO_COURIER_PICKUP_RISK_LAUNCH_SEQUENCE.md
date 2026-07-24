# Courier Pickup Risk, Launch Admission and Sequencing

**Architecture:** APPROVED — 2026-07-24
**Increment 1:** IMPLEMENTATION AUTHORIZED — PRE-PRODUCTION ONLY
**Production:** NOT APPROVED

## Risk register

| Risk | Control | Production evidence |
|---|---|---|
| Duplicate Pickup authority | Refine existing owner only | Ownership scan/ADR |
| Pickup implies custody | Explicit pre-custody semantics | Contract tests |
| Reassignment overwrites history | Attempt per assignment | Concurrency tests |
| False arrival | Separate human evidence/corrections | Abuse/dispute trials |
| GPS over-trust | Optional corroboration | Weak-network/basic-phone trials |
| Worker surveillance | No tracking history/fingerprints | Privacy/labour review |
| Merchant shared accounts | Individual/location authority | Staff trials/audit |
| Support impersonation | Dual attribution/no fabrication | Threat tests |
| Stale source evidence | Versioning/fail closed | Race/replay tests |
| Waiting becomes blame | Evidence only | Fairness/policy review |
| State explosion | Four-state core plus one terminal | Lifecycle review |
| Product leakage | Product-scoped policy | Cross-domain review |
| Event duplication/reordering | Idempotency/outbox/versions | PostgreSQL/restart tests |
| Premature production | Separate launch approval | Completed admission record |

## Recommended implementation sequence

1. Confirm the approved authorization and stop condition before implementation.
2. Certify Dispatch assignment-attempt, Preparation readiness, Merchant staff/location
   and Custody admission contracts.
3. Add assignment-attempt-compatible Pickup persistence without rewriting history.
4. Add policy, terminal outcome, taxonomy and corrections.
5. Add actor/action idempotency, optimistic concurrency, audit and outbox.
6. Certify races, restart, rollback and backup/restore.
7. Run courier, merchant and limited-device trials.
8. Return for technical, legal, operational and Founder production gates.

Increment 1 authority is recorded separately. This sequence grants no production or
successor authority.

## Production admission

- [ ] Architecture and implementation reviews formally approved.
- [ ] Production product policy/values approved.
- [ ] Courier/merchant/source contracts certified.
- [ ] Dispatch/Preparation/Pickup/Custody compatibility certified.
- [ ] Courier and merchant usability trials completed.
- [ ] Limited-device trials completed where launch claims require them.
- [ ] Arrival/acknowledgement reliability threshold approved and met.
- [ ] False-arrival/replay/impersonation/support-abuse tests passed.
- [ ] Waiting-evidence fairness review completed.
- [ ] Qualified Ethiopian labour, transport, privacy, commercial and records review.
- [ ] PostgreSQL 17 concurrency/migration certification.
- [ ] Restart, rollback and backup/restore certification.
- [ ] Security/privacy, incident and correction runbooks approved.
- [ ] Named territory/product and production activation separately approved.

Production remains prohibited until every applicable item is evidenced.
