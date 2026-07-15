# AYO Audit Event Architecture

## Support taxonomy

Mission 9 audits case creation/view/update, information request, assignment, escalation, takeover, AI guidance, recommendations, resolution/closure, access denial and redaction. Audit metadata excludes messages, notes, recordings, transcripts, credentials, payment data, precise histories and hidden model reasoning. Domain case events complement but do not replace Mission 5 audit records.

## Purpose and boundaries

The audit foundation answers who or what attempted an important action, on which
resource, when, with what outcome and safe reason. It benefits customers, drivers,
operations and investigators by preserving trustworthy accountability. Success is
measured by atomic coverage of required actions, zero prohibited metadata accepted,
bounded query/insert behavior, and recoverable investigation evidence.

Audit records are not ordinary application logs. Operational logs may contain an
audit event UUID, duration and safe outcome category, but must not copy audit
metadata. This mission does not activate auditing in existing in-memory ride or
wallet traffic, add authentication/authorization, or export data externally.

## Architecture comparison

| Approach | Benefits | Costs and risks | Decision |
|---|---|---|---|
| Application event in business Unit of Work | Full actor/business meaning; success event and state are atomic | Required actions must explicitly append | Selected primary path |
| Separate audit transaction | Persists even without a business transaction | Can falsely record success after rollback | Only bounded denied/failed pre-transaction events |
| Transactional outbox/CDC | Reliable later SIEM/analytics export | Adds consumer, lifecycle and operating cost | Shape-compatible; deferred until a consumer is approved |
| Event sourcing | Complete domain history and rebuild | Makes events business truth; large modeling/operational burden | Rejected without evidence |
| Trigger/database-native audit | Captures direct SQL changes | Weak request/actor context; privileged DB code; sensitive row snapshots | Defense-in-depth candidate, not primary |

The selected design remains a module inside the FastAPI modular monolith. It uses
SQLAlchemy Core, the existing Unit of Work, PostgreSQL 17 and Alembic. No external
network call occurs inside a transaction.

## Contract and taxonomy

Each immutable `AuditEvent` has UUID `event_id`; UTC `occurred_at` and
`recorded_at`; actor type/optional opaque actor identifier and session UUID; bounded
action; resource type/optional identifier; outcome and safe reason category;
correlation, optional causation and request UUIDs; source module; schema version;
allowlisted metadata; and an optional command idempotency key.

Actors: `anonymous`, `rider`, `driver`, `staff`, `administrator`, `system`, and
`service`. Outcomes: `success`, `denied`, `failed`, and `cancelled`.

Actions use stable lowercase names such as `ride.state.changed`. Reasons are safe
machine categories, never exception messages. Resources and actor identifiers must
be opaque internal identifiers where possible. Correlation links one operation;
causation links a later event to the event that caused it.

## Metadata allowlist and prohibited data

Allowed keys are deliberately narrow: `category`, `channel`, `error_category`,
`operation`, `policy_version`, `risk_level`, `state_from`, and `state_to`. Values
are bounded strings containing category-safe characters, integers or booleans.
Unknown/nested/float/unbounded fields fail validation. Adding a key requires privacy,
security, operational-purpose and retention review plus contract tests.

Never store passwords, OTPs, access/refresh tokens, secrets, keys, payment
credentials, database URLs, authorization headers, unrestricted bodies, unnecessary
personal data or precise-location histories. Generic metadata also prohibits phone,
email, government and device identifier fields. Validation errors hide supplied
input so rejected secrets are not echoed into logs.

Pseudonymization means using stable opaque internal identifiers when investigation
requires linkage. Masking is allowed only under an approved field-specific policy;
it is not permission to copy personal data into generic metadata. Encryption at
rest/TLS and backup encryption remain infrastructure controls.

## Transactions, failure and idempotency

- Important successful state changes append through `unit_of_work.audit_events`
  before commit. Any repository/audit failure fails the transaction and is surfaced.
- Rollback removes both business state and its success audit event.
- Denied or failed work that occurs before business state exists may use
  `StandaloneAuditWriter`, which rejects success/cancelled outcomes.
- Never silently discard required events and never make an external call in the
  database transaction. Track append failures and latency through safe operational
  metrics/log events that contain no audit payload.
- Idempotency uniqueness is scoped to source module, action and command key. A
  semantically identical retry returns the stored event. Reuse with different
  content raises a conflict rather than creating misleading evidence.
- Read queries are bounded to 500 records. Bulk investigation/export needs a later
  approved paginated interface, not unbounded application queries.

## Append-only privilege model

The application repository exposes append, lookup and bounded correlation reads;
it has no update/delete operation. The migration revokes public access and grants
an existing `ayo_runtime` role only schema `USAGE` and table `SELECT`/`INSERT`.
It explicitly revokes `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES`, and `TRIGGER`.
The migration role owns the table and remains capable of controlled schema work.

This prevents ordinary runtime mutation, not owner/superuser tampering. Production
must alert on audit-table DDL, privilege changes, unexpected mutation attempts,
append failure rate, insert latency, volume growth, storage/backup pressure and
schema-version mismatch. Audit read access must itself be audited once staff
authorization exists.

## Tamper evidence

No hash chain is used now. Deterministic hashes stored beside the same mutable data
do not protect against a database owner recomputing them. A global chain would add
a fragile serialization point; per-resource chains make ordering and missing-event
detection more complex. Therefore AYO claims append-only controls, not tamper-proof
storage. Future signed checkpoints or immutable external copies require an approved
managed key lifecycle, independent control plane, export design and verification
tool. No signing/KMS interface is added before that system has a real consumer.

## Retention framework

Final periods require Ethiopian legal and operational professional approval. Until
then, categories must be separable and no team may invent durations:

- Security/authentication evidence may require longer incident and fraud windows.
- Financial/payment/wallet evidence may require accounting, tax and regulatory
  retention aligned with the future immutable ledger.
- Safety incident evidence may need legal hold and tightly approved access.
- Staff/administrator activity may require employment/privacy proportionality.
- Ordinary ride operations should use the shortest period that meets a verified
  purpose; precise location must not be reconstructed through metadata.

Retention must cover primary storage, replicas, exports and backups; legal holds
must be explicit. Expiry deletion cannot be performed by the runtime role and needs
a separately approved, audited retention mechanism.

## Incident investigation procedure

1. Assign a case/correlation identifier and obtain approved investigator access.
2. Preserve relevant evidence and backup/PITR references; do not edit records.
3. Query narrowly by event, correlation, actor or resource and bounded time range.
4. Compare audit evidence with operational logs by event UUID without copying
   sensitive payloads.
5. Record every access, export, interpretation and chain-of-custody handoff.
6. Escalate suspected owner-level tampering; database contents alone cannot disprove
   it. Preserve infrastructure/database access and backup evidence.
7. Apply legal hold/notification only under approved incident and legal policy.

## Capacity, recovery and future export

Six lookup indexes plus one partial idempotency index balance investigation needs
against insert cost. Concurrent inserts do not use a global audit lock. Measure
rows/second, index size, query latency and retention growth before considering time
partitioning. At scale, CDC can export inserts using event UUID, schema version and
correlation fields; consumers must be idempotent. An outbox or SIEM is not deployed.

Backup/PITR and restore tests must include audit history and migration readiness.
Provider outage does not apply because no provider is called; a database outage
fails required audit/business transactions rather than creating unaudited success.

## Questions requiring Ethiopian verification

- Lawful bases, notices and access rights for rider, driver and staff audit data.
- Category-specific retention, deletion restrictions and legal-hold duties.
- Cross-border storage/export and regulator/law-enforcement disclosure requirements.
- Financial, transport, employment and safety evidence requirements.
- Whether pseudonymized identifiers remain personal data under applicable rules.

These are unresolved professional questions, not engineering assumptions.
