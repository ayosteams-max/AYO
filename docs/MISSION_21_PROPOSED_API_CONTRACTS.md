# Mission 21 — Proposed API and Projection Contracts

Status: **Non-runtime proposal. Paths and schemas are not implemented.**

All commands require authenticated server identity when possible, RBAC, case ownership,
idempotency key, expected case version, size/rate bounds and privacy-minimised errors.
Emergency intake also supports a separately reviewed safe unauthenticated boundary.

| Method/path proposal | Purpose |
|---|---|
| `POST /support/cases` | Create case or emergency intake and receive durable fallback status |
| `GET /support/cases/{id}` | Role-safe case/status/deadline/handoff projection |
| `POST /support/cases/{id}/messages` | Append original-language user message |
| `POST /support/cases/{id}/evidence-requests/{request_id}/responses` | Supply bounded requested metadata/reference |
| `POST /support/cases/{id}/reopen` | Policy-validated appeal/reopen |
| `GET /support/history` | Rider/driver role-scoped case history |
| `POST /support/cases/{id}/handoff` | Request human handoff; AI cannot deny |
| `POST /support/emergency` | Immediate restricted safety path |
| `GET /support/cases/{id}/resolution` | Grounded bilingual explanation/prohibited-actions projection |
| `GET /support/cases/{id}/why` | Plain-language cited decision explanation and appeal status |
| `GET /support/cases/{id}/timeline` | Ordered role-redacted canonical ride/support timeline |
| `GET /support/cases/{id}/visual-replay` | Optional coarse privacy-safe replay, never raw GPS |
| `POST /support/cases/{id}/appeals` | Idempotent appeal with governed evidence-metadata references |

Internal typed contracts include `ClassifyIntent`, `RetrieveEvidenceReference`,
`ExplainPolicy`, `ProposeAllowListedAction`, `TranslateApprovedMessage`,
`PrepareHandoff`, `AcceptOwnership`, `RecordSpecialistDecision` and
`RecordResolution`. AI can invoke only the first six through the broker; each invocation
is case-scoped, read-only or non-consequential, bounded and audited.

The app projection always supplies `stage_code`, human explanation, `updated_at`,
expected next stage/deadline, fallback availability, evidence request status, handoff
queue/status, emergency affordance and reopen eligibility. Loading never hides durable
case creation or provider outage.

Future timeline, replay and explanation projections carry projection version, source
reference/version, redaction code, freshness and `as_of` timestamp. Rider, driver and
Support consume the same canonical ordering but role-safe fields. Visual replay fails
closed when purpose, consent, freshness or redaction policy is absent.

Future internal interfaces may include `SupportChannelAdapter`, `VoiceSessionReference`,
`VideoSessionReference`, `ScreenShareGrant`, `CoBrowseGrant`, `LiveLocationGrant`,
`CaseParticipantGrant`, `KnowledgeArticleProjection`, `QualityEvaluation` and
`SatisfactionObservation`. Grants are case-scoped, purpose-bound, time-limited,
revocable and audited. They expose no generic device control, credentials or raw
provider API to AI. No public path or provider contract is authorized.
