# Mission 23 — Proposed Persistence Model

Status: **No migration authorized.**

Future additive records may include coordination decisions, candidate-stage summaries,
strategy selections, prediction references, fairness check results, recovery actions,
health metric definitions/snapshots, recommendations, simulation runs/policy comparisons
and policy snapshots. Store bounded reason counts/references—not full candidate locations
or duplicated raw trails.

Assignment, offer, reservation and Active Ride tables remain owned by existing modules.
Decision/outbox writes join the owning transaction where consequential; advisory health/
simulation data is isolated. Keys include city/zone/time bucket or ride/decision ID;
indexes and partitioning follow measured queries. Corrections append; policies are
immutable/effective-dated; retention/legal hold remains separately approved.
