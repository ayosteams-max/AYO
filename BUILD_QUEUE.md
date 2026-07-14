# AYO Build Queue

Status: awaiting CTO and CEO approval before production implementation  
Last updated: 2026-07-15  
Authority: `docs/AYO_CONSTITUTION.md`, `docs/AYO_ENGINEERING_WORKFLOW.md`, and `docs/AYO_ROADMAP.md`

## Queue rules

- This file orders approved candidate missions; it does not authorize implementation.
- Every mission must complete all ten Engineering Workflow steps in order.
- Research and recommendations are presented first. CTO review and CEO approval are recorded before architecture design or production code.
- Only one mission may be in implementation at a time unless the CTO and CEO explicitly approve parallel work and its risks.
- A mission cannot advance while required Ethiopian legal/operational verification or a critical security/safety risk is unresolved.
- After each mission, stop and request approval before beginning the next.
- Measure first, build second and optimize third. Do not add architecture or infrastructure for hypothetical scale.

## Approval states

- **Queued:** dependency order recorded; research not authorized.
- **Research authorized:** Workflow Steps 1–2 may proceed; no architecture or code.
- **Awaiting approval:** findings presented; waiting for CTO review and CEO approval.
- **Design authorized:** approved scope may complete Steps 4–5; no production implementation until the design gate is approved.
- **Implementation authorized:** Steps 6–9 may proceed within approved scope.
- **Complete:** evidence accepted; work stopped before the next mission.

## First 10 engineering missions

| # | Mission | Customer/engineering outcome | Principal dependency | Current gate |
|---|---|---|---|---|
| 1 | Reproducible engineering foundation | Engineers can install, run, test and change the prototype safely and consistently. | None | Active at milestone level: Milestone 1 complete; Milestone 2 not approved. No production code authorized. |
| 2 | Domain contracts and persistence seam | Working behavior can move from unsafe memory storage without a platform rewrite or leaked internal data. | Mission 1 | Completed 2026-07-15 |
| 3 | PostgreSQL/PostGIS, migrations and audit foundation | Ride and operational state survives restarts, workers and failures with transactional history. | Mission 2 | PostgreSQL foundation implemented 2026-07-15; migrations and audit remain queued; real PostgreSQL integration run pending CI/server availability |
| 4 | Identity, sessions and permissions | Riders, drivers and staff can act only as authenticated, authorized identities. | Mission 3 plus verified OTP/identity assumptions | Queued |
| 5 | Driver onboarding and operational verification | Only eligible, verified drivers and vehicles can serve riders. | Mission 4 plus Ethiopian document/transport verification | Queued |
| 6 | Canonical ride lifecycle and idempotent commands | One reliable ride flow survives retries, races, stale clients and weak connectivity. | Missions 3–5 and approved exception policies | Queued |
| 7 | Smart Pickup and map-provider abstraction | Riders and drivers receive safer, serviceable pickups and reliable routes without provider lock-in. | Missions 3 and 6 plus launch-area field verification | Queued |
| 8 | Reliable immediate dispatch | The closest suitable available driver receives a time-bounded offer without double assignment. | Missions 5–7 plus approved dispatch/fairness policy | Queued |
| 9 | Pricing, immutable ledger and cash reconciliation | Fares and driver earnings are server-authoritative, auditable, balanced and cash-aware. | Mission 6 plus approved pricing/commission and Ethiopian tax/accounting review | Queued |
| 10 | Licensed payment integration and driver payouts | Digital collections, refunds and payouts reconcile safely through licensed providers. | Mission 9 plus provider contracts and Ethiopian legal verification | Queued |

## Mission 1 remaining gate

The next candidate work is Mission 1, Milestone 2: reproducible Python project metadata and dependency policy. It remains unapproved.

Before any implementation, its Workflow Steps 1–3 must provide and approve:

- Current dependency/import evidence and supported Python requirements.
- Options comparison for dependency declaration and locking, including cost, maintenance, portability, security and developer experience.
- Recommended option with rationale, alternatives and risks.
- Ten-question “survive success” assessment.
- Recorded CTO review and CEO approval with scope and exclusions.

## Stop condition

No production code, dependency metadata, infrastructure, cloud proof-of-capability, detailed next-mission design or optimization is authorized by this queue. Codex must wait for explicit CTO and CEO approval.
