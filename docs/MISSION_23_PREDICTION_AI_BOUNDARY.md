# Mission 23 — Prediction and AI Boundary

Permitted estimates: ETA, completion, acceptance/cancellation probability, supply/demand,
lateness, reservation failure, airport congestion and imbalance. Each output carries
prediction ID, model/policy version, confidence/calibration band, freshness/expiry, input
provenance, reason/features where safe, applicability and deterministic fallback.

Models cannot assign/remove drivers, change eligibility, punish, price, bonus, override
safety, bypass commitment or create financial consequences. Deterministic policy validates
schema, scope, freshness and confidence, then may ignore the prediction. Drift is monitored
by zone/service/language/device/network where lawful. Rollback selects the prior policy or
simple ETA/freshness rules. Shadow output is isolated from execution.
