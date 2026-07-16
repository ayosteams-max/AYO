# Mission 23 — Proposed API Contracts

Status: **Non-runtime proposal; no routes authorized.**

Internal contracts: `ClassifyDispatch`, `GenerateCandidates`, `EvaluateCandidateETA`,
`RankImmediate`, `EvaluateReservationHealth`, `ProposePreDispatch`, `EvaluateAirportQueue`,
`RecordDecisionExplanation`, `BuildHealthSnapshot` and `RecommendOperationalAction`.

Potential authenticated Operations reads: dispatch decision explanation, privacy-thresholded
health snapshot and simulation report. Commands remain with existing owning dispatch
applications. All contracts are versioned, bounded, RBAC/ownership checked, rate limited,
idempotent where mutating and privacy-redacted. No public candidate list, model feature,
raw location or policy mutation endpoint is proposed.
