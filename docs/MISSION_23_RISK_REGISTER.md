# Mission 23 — Risk Register

| Risk | L/I | Mitigation | Owner/gate |
|---|---|---|---|
| Optimization delays immediate rider | M/High | Materiality cap and sequential fallback | CTO/Product |
| Scheduled commitment churn | M/Critical | Formal-lock invariant | Scheduled/Ops |
| Pre-dispatch harms current trip | M/Critical | Current-trip priority and auto release | Safety/Ops |
| Fairness metric becomes punishment | M/High | Aggregate advisory use only | CEO/Support |
| Batch driver race/distraction | M/High | Bounded shadow and atomic winner | Safety/CTO |
| Airport queue gaming | H/High | Staging lease and operations audit | Airport Ops |
| Prediction bias/drift | M/High | Segmented calibration and fallback | AI Governance |
| Hot-zone lock/provider overload | M/High | Bounded funnel/backpressure | CTO |
| Raw location over-retention | M/Critical | Derived evidence and approved TTL | Privacy/Legal |
| Weak-network false availability | H/High | Fresh lease/uncertainty fail closed | CTO |

No critical risk is accepted for implementation by this proposal.
