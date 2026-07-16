# Mission 21 — Support Case State Machine

Status: **Architecture proposal only.**

## States and transitions

| State | Purpose | Allowed next states |
|---|---|---|
| `CASE_CREATED` | Durable authenticated or safe anonymous intake | `TRIAGE_PENDING`, `SPECIALIST_REVIEW_REQUIRED` |
| `TRIAGE_PENDING` | Deterministic category/risk routing | `AI_ASSISTED_REVIEW`, `HUMAN_REVIEW_REQUIRED`, `SPECIALIST_REVIEW_REQUIRED` |
| `AI_ASSISTED_REVIEW` | Constrained evidence retrieval and proposal | `WAITING_FOR_USER`, `WAITING_FOR_DRIVER`, `WAITING_FOR_EVIDENCE`, `HUMAN_REVIEW_REQUIRED`, `SPECIALIST_REVIEW_REQUIRED`, `RESOLUTION_PROPOSED` |
| `WAITING_FOR_USER` | Minimum necessary user input requested | `TRIAGE_PENDING`, `HUMAN_REVIEW_REQUIRED`, `CLOSED` |
| `WAITING_FOR_DRIVER` | Driver response requested without exposing reporter | `TRIAGE_PENDING`, `HUMAN_REVIEW_REQUIRED`, `CLOSED` |
| `WAITING_FOR_EVIDENCE` | Owning-domain/provider evidence pending | `TRIAGE_PENDING`, `HUMAN_REVIEW_REQUIRED`, `SPECIALIST_REVIEW_REQUIRED` |
| `HUMAN_REVIEW_REQUIRED` | General Support owns judgment | waiting states, `SPECIALIST_REVIEW_REQUIRED`, `RESOLUTION_PROPOSED` |
| `SPECIALIST_REVIEW_REQUIRED` | Safety/Identity/Fraud/Finance/Legal/etc. owns judgment | waiting states, `RESOLUTION_PROPOSED` |
| `RESOLUTION_PROPOSED` | Versioned explanation/action awaits authorized acceptance | review states, `RESOLVED` |
| `RESOLVED` | Outcome recorded; appeal/reopen window active | `REOPENED`, `CLOSED` |
| `REOPENED` | New evidence, appeal or recurring failure | `TRIAGE_PENDING`, `SPECIALIST_REVIEW_REQUIRED` |
| `CLOSED` | Administratively complete, retained by policy | `REOPENED` only under policy/authority |

## Invariants

- Commands are authenticated where possible, idempotent and expected-version guarded.
- Only the orchestrator transitions state; AI emits proposals, never transitions.
- Exactly one accountable queue/owner exists after triage; transfer is atomic and audited.
- Safety/emergency goes directly to specialist review and cannot be AI-closed.
- Deadlines come from immutable policy snapshots. Breach raises priority and requeues;
  it never silently closes a case.
- Waiting requests state the missing item, responsible party, expiry and fallback.
- Resolution records decision/policy/evidence versions and appeal/reopen eligibility.
- Reopen is allowed for approved windows, material new evidence, recurring platform
  failure, appeal rights or authorized Support override; duplicates link, not overwrite.
- Closure is administrative and cannot delete audit/evidence under retention or legal hold.
