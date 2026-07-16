# AYO Implementation Phase 1 Master Plan

Date: 2026-07-16
Status: **Approved by CTO/CEO on 2026-07-16. Implementation requires one explicitly
authorized increment at a time; Increment 1 is authorized.**
Authority: AYO Constitution, approved decisions and Missions 1–26. This plan defines no
new mission and authorizes no code, migration, dependency, provider or activation.

## 1. Outcome and implementation strategy

Phase 1 delivers one trustworthy Ethiopia-first ride flow before broad activation:

`authenticate -> confirm pickup/destination -> quote -> request Immediate Standard ->
deterministic dispatch -> pickup -> trip -> cash obligation -> immutable accounting ->
receipt/support evidence`.

Build as a well-bounded modular monolith plus independently deployable mobile clients.
Integrate vertically in small reversible slices, preserve server authority, keep providers
behind contracts, and require PostgreSQL evidence before enabling dependent features.
Architecture documents are not shipped behavior. Every slice ends at its own CTO/CEO
gate; this plan does not authorize implementation by itself.

### MVP definition

MVP includes authenticated Rider and Driver roles; approved driver/vehicle eligibility;
Immediate Standard booking; safe pickup/landmark fallback; closest-suitable deterministic
dispatch; Active Ride lifecycle; versioned ETB quote/final fare; cash collection claim;
balanced ledger accounting; receipts; basic deterministic support case creation;
English/Amharic critical content; accessibility baseline; weak-network retry/recovery;
audit, observability, backup/restore and operator runbooks.

MVP excludes public Mission 20, Scheduled/Airport Premium activation, autonomous AI,
demand adjustment, incentives, digital payments, payouts, stored-value wallets, AYO Pay,
external support AI, later super-app products and any unverified numeric or legal policy.

## 2. Recommended repository structure

Preserve the repository and evolve it without a rewrite:

```text
BACKEND/
  api/                 # versioned HTTP schemas/routers and composition only
  domain/              # shared value objects and domain primitives
  identity/            # accounts, authentication, sessions, recovery
  drivers/             # onboarding, documents, vehicles, eligibility projections
  pickup/              # pickup and provider-neutral map/landmark contracts
  dispatch/ scheduled/ marketplace/
  active_ride/ arrival_waiting/
  pricing/ incentives/
  ledger/ wallets/ payments/ reconciliation/
  support/ safety/ audit/
  persistence/ workers/ config/ observability/
database/              # Alembic revisions and operational DB scripts
tests/                  # unit, contract, integration, security, recovery, performance
AYO-Mobile/
  app/                  # route shells only
  domain/               # typed role presentation state and commands
  features/rider/ features/driver/ features/shared/
  services/             # authenticated API, sync, cache, provider-neutral adapters
  components/ design-system/ localization/ tests/
docs/ runbooks/
```

Directory moves occur only when the implementing slice needs them and characterization
tests protect imports. Do not create microservices or split Rider/Driver packages until
measured release, team or scaling evidence justifies it.

## 3. Ordered implementation programme

| Order | Increment | Deliverable | Entry dependency | Exit gate |
|---:|---|---|---|---|
| 0 | Baseline and policy freeze | inventory, traceability, test baseline, approved ETB/cash/identity/pilot policies | Phase 1 approval | no unresolved launch-critical authority |
| 1 | Engineering certification | reproducible environments, CI, secrets/config, PostgreSQL 17 service | existing Missions 1–3 | lint/type/unit/integration and restore pass |
| 2 | Persistence/audit platform | UoW, idempotency, outbox/inbox, migration rules, audit | 1 | upgrade/downgrade, concurrency, restart/recovery pass |
| 3 | Authentication/authorization | identity, sessions, RBAC, ownership, staff step-up | 2, Mission 24 policy | security and recovery gates pass |
| 4 | Driver identity/eligibility | onboarding, documents/vehicles, deterministic eligibility | 3, local verification policy | no provider/AI authority; appeal path |
| 5 | Canonical ride/pickup | ride state, pickup contracts, maps fallback, weak-network commands | 2–4 | state/idempotency/provider-outage tests |
| 6 | Immediate dispatch | closest-suitable offers, locks, recovery and audit | 5, certified existing dispatch | concurrency/worker recovery/load gates |
| 7 | Active Ride | accepted-to-complete lifecycle and realtime projections | 6 | ownership/retry/restart tests |
| 8 | Pricing | approved versioned ETB estimate/final calculation | 5, approved numeric policy | financial property/fairness tests |
| 9 | Ledger and cash | double entry, cash claim, wallet projections, reconciliation | 7–8, accounting approval | balance/concurrency/restore/parallel-book proof |
| 10 | Mobile MVP | Rider/Driver vertical journey, offline sync, accessibility/localization | stable APIs 3–9 | device/usability/network certification |
| 11 | Support/operations | deterministic cases, evidence timeline, dashboards/runbooks | 3–10 | role/privacy/incident exercises |
| 12 | Pilot readiness | security review, DR, finance close, field rehearsal | all MVP increments | CTO/CEO go/no-go |
| 13 | Post-MVP gated capabilities | Mission 20, Scheduled, Airport, digital payment, AI assist | independent gates | separate activation approvals |

No later row starts merely because an earlier row exists; its policy, evidence and
approval gates must also be satisfied.

## 4. Backend, database and API sequence

Backend work starts by characterizing legacy routes and composing approved modules behind
disabled flags. Replace process-local authority one aggregate at a time through repository
contracts. Canonical commands perform authorization, validation, version/idempotency
checks, domain transition, persistence, audit and outbox atomically. Workers are bounded,
lease/lock safely, resume after restart and never start on import.

Database order is identity/audit/idempotency/outbox foundations; driver eligibility;
ride/pickup; dispatch/offers; Active Ride; pricing; ledger/cash/reconciliation; support.
Every change needs reversible Alembic upgrade/downgrade, expand-contract compatibility,
backup/restore evidence, indexes and retention classification. Prototype wallet balances
are quarantined and never migrated as trusted opening value.

API order follows stable domain authority rather than screens: authentication/session;
driver onboarding; pickup/quote; ride command/query; dispatch internal commands; Active
Ride projections; pricing/receipt; ledger projection; support. `/api/v1` schemas are
explicit, privacy-minimized and backward compatible. All mutations require authenticated
context, RBAC/ownership, idempotency, expected version, rate/request limits and stable
error codes. Internal worker/provider endpoints use separate service authentication.

## 5. Authentication and identity sequence

1. Durable accounts, roles, permissions and audit.
2. Password/OTP boundary and provider-neutral contact verification after approval.
3. Short access tokens, rotating refresh families, replay revocation and multi-device
   sessions.
4. Ownership authorization and staff/admin phishing-resistant step-up.
5. Recovery, lost-device revocation, anti-enumeration and appeal.
6. Driver document/vehicle workflows with deterministic human-authorized results.
7. Trusted/Airport eligibility only after separate local policy approval.

Authentication proves control; proofing binds evidence; eligibility grants a product
capability. AI/OCR never approves, recovers, suspends or grants eligibility.

## 6. Dispatch and ride sequence

Certify existing Immediate Dispatch persistence and secure activation boundaries first.
Keep eligibility/availability filters separate from ranking. Immediate prioritizes the
fastest suitable pickup using staged candidate filtering, exclusive offers and assignment
locks. Active Ride alone owns post-assignment lifecycle. Marketplace Health and models
remain shadow/advisory. Scheduled and pre-dispatch retain separate commitment logic and
stay disabled during MVP unless separately pilot-approved.

Mission 20 remains `ARRIVAL_WAITING_ENABLED = False`. Before any later activation it must
pass PostgreSQL integration, migration upgrade/downgrade, concurrency, restart and
recovery tests with no accepted skips, then obtain a distinct activation decision.

## 7. Pricing, ledger and payment sequence

Approve Ethiopian numeric pricing, rounding, commission, tax and cash policy before
implementing Pricing. Pricing emits immutable instructions; it never posts money. Build
the balanced ledger and derived wallet views next, validate with synthetic parallel books,
then implement cash claims and reconciliation. Only after ledger/Finance readiness may a
separate provider mission add one licensed payment adapter in sandbox. Payment attempts,
provider settlement and ledger posting remain distinct. Digital refunds/payouts follow
only after reconciliation and incident operations pass. AYO Pay is excluded.

## 8. Mobile sequence

1. Shared design system, bilingual tokens, accessibility and authenticated API client.
2. Session/recovery and explicit offline/pending/failed states.
3. Rider pickup, destination, quote and Immediate booking.
4. Driver availability, offer, accept/decline and navigation handoff.
5. Shared Active Ride timeline and server-reconciled commands.
6. Cash claim, receipt, ledger projection and support entry.
7. Weak-network queue, restart/device-sleep recovery and telemetry redaction.
8. Field-tested polish and truthful store assets based only on enabled behavior.

Clients cache projections and interpolate display-only timers; they never author ride,
dispatch, fare, payment, ledger, identity or safety decisions.

## 9. Feature-flag and rollout strategy

Flags are server-owned, deny-by-default, environment-validated, versioned and audited.
Separate code availability, internal shadow, staff cohort, geographic pilot, product and
public flags. Financial/safety flags require maker-checker approval and kill switches.
Dependencies are explicit: a child flag cannot enable if prerequisite certification or
parent flag is false. Mobile remote configuration may hide presentation only and cannot
grant authority. Rollback disables new commands while preserving durable in-flight state.

Rollout stages: local synthetic -> CI PostgreSQL -> internal staff -> controlled driver/
rider field rehearsal -> small Addis Ababa zone/time cohort -> measured expansion.
Every stage has entry/exit criteria, support staffing, reconciliation, incident owner and
rollback rehearsal. No percentage claim is set before capacity and operations evidence.

## 10. Testing and security milestones

Testing layers: unit/state/property; repository/PostgreSQL; migration up/down; contract;
authorization; idempotency/concurrency; worker restart/recovery; offline/mobile; provider
sandbox; end-to-end; accessibility/localization; load/soak; backup/restore; reconciliation.
Synthetic data only. Coverage threshold remains the repository-approved threshold, but
requirements-to-test traceability and financial/safety invariants are release authority.

Security milestones are threat-model sign-off; secrets/key strategy; authentication and
RBAC tests; sensitive-data/log review; SAST/dependency/secret scans; webhook/replay
verification; mobile storage and transport review; privilege/insider tests; penetration
test; incident, account-takeover, payment and disaster-recovery tabletops. Critical or
unaccepted high findings block rollout.

## 11. DevOps and CI/CD milestones

- Reproducible Python/Node/PostgreSQL toolchains and locked dependencies.
- PR gates for formatting, lint, strict typing, unit/integration, migration, security and
  documentation validation.
- Ephemeral PostgreSQL 17 integration environment with no mission-specific skips.
- Build provenance, artifact signing/SBOM, protected branches and approval environments.
- Separate dev/test/staging/production configuration and managed secrets/keys.
- Zero-downtime-compatible migration discipline, backups, PITR and restore drills.
- Health/readiness, structured privacy-safe telemetry, SLOs, alerts and runbooks.
- Staged deployment, canary/cohort controls, automated halt signals and manual rollback.

CI proves build quality; it never grants production activation without the human gate.

## 12. Module dependency map

| Module | Requires | Enables |
|---|---|---|
| Identity/session/RBAC | PostgreSQL, audit, keys | every protected domain |
| Driver eligibility | identity, local policy | dispatch candidates |
| Pickup/maps | ride, provider contracts | quote, dispatch, arrival |
| Ride/Active Ride | identity, pickup, persistence | pricing final, ledger event, support |
| Dispatch | eligibility, availability, pickup/ETA | assignment |
| Pricing | ride facts, approved policies | financial instruction |
| Ledger/wallet | Pricing instruction, Finance mappings | cash accounting, payment settlement |
| Payments | identity, ledger, licensed provider contract | digital collection/refund/payout |
| Mission 20 | ride/pickup/location/notification plus PG certification | evidence only |
| Support | identity and authorized domain evidence | investigation/handoff |
| Mobile | stable versioned APIs/projections | user journey only |

## 13. Production readiness checklist

- [ ] All MVP policies and Ethiopian legal/operational decisions approved.
- [ ] No process-local production authority or trusted prototype wallet balance.
- [ ] PostgreSQL migration, concurrency, restart, recovery and restore gates pass.
- [ ] Authentication, RBAC, ownership, session replay and step-up pass.
- [ ] Immediate Dispatch and Active Ride invariants pass under failure/load.
- [ ] Pricing versions/explanations and ledger balance/idempotency pass.
- [ ] Cash reconciliation and Finance close rehearsal pass.
- [ ] Mobile weak-network, device matrix, accessibility and Amharic validation pass.
- [ ] Privacy retention, consent, audit access and deletion/legal-hold rules approved.
- [ ] Security scans, penetration test and incident tabletops have no open critical risk.
- [ ] SLOs, dashboards, alerts, support coverage, backups and rollback are owned.
- [ ] Feature flags and prohibited features verified false.
- [ ] Store/marketing claims match the enabled build.
- [ ] CTO technical readiness and CEO pilot approval recorded.

## 14. Principal risks and decisions required

Largest risks are integration of partially completed missions without recertification;
unverified Ethiopian identity, transport, tax, cash and payment rules; PostgreSQL gaps;
legacy route bypass; provider/map/network outage; weak-device UX; dispatch/ledger races;
insufficient field/support capacity; and premature activation of advanced features.

Leadership must approve the MVP zone/cohort, numeric pricing/commission/cash rules,
driver verification evidence, map/notification/provider strategy, pilot support/safety
operations, SLO/rollback thresholds and budget. Qualified Ethiopian review remains
mandatory for identity, privacy/location, transport/labour, tax/accounting, payments,
consumer protection and emergency response.

## 15. Review gate

CTO/CEO approval of this plan should authorize only a named first implementation
increment with explicit files, exclusions and quality gates. Do not infer approval for
the whole programme, Mission 20 activation, providers, numeric policy or production.
