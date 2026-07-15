# AYO Authorization Architecture

## Support resource policy

Mission 9 adds resource policy around RBAC: customer ownership, assigned AI service identity plus permission, or permitted staff queue. Six `support.queue.<queue>.access` permissions separate human queues and are never included in the AI support permission set. Assignment is server-authoritative and deny-by-default; details are in `AYO_SUPPORT_ARCHITECTURE.md`.

Status: Mission 8 approved architecture. This defines implementation boundaries,
not the final operational role matrix.

## Decision and evidence

NIST core RBAC separates identity-role and role-permission assignments. NIST ABAC
can evaluate subject, resource, action and environmental attributes but requires
reliable attribute governance. OWASP requires least privilege, denial by default
and authorization checks on every request. OPA and Cedar provide policy languages;
OpenID AuthZEN defines a portable PDP/PEP interface; Zanzibar addresses global
relationship graphs.

AYO uses core RBAC behind a policy-shaped decision interface. It is the smallest
reliable fit for the modular monolith and can later move behind an internal
AuthZEN-style API without changing permission identifiers or enforcement meaning.

## Model

- `permissions`: immutable bounded action codes controlled by reviewed changes.
- `roles`: named permission bundles with no inheritance in Mission 8.
- `role_permissions`: idempotent many-to-many grants.
- `identity_role_assignments`: attributable, optionally expiring and explicitly
  revocable assignments; one active assignment exists per identity and role.
- Identity status remains authoritative; only active identities can be allowed.

The initial registry contains authorization-infrastructure permissions only. Rider,
driver, support, safety, finance and administrator matrices require leadership
approval and are not silently invented or seeded.

## Enforcement and failure behavior

Authentication supplies a trusted subject. Headers, public parameters and token
role claims never directly grant privilege. Middleware attaches trusted context;
route decorators and dependencies declare required permissions; service operations
use the same decision service so HTTP cannot be the only enforcement boundary.

No active grant means deny. Missing Authentication means authentication required.
PostgreSQL or required audit failure aborts the protected operation. Customer-facing
responses remain deliberately non-diagnostic.

## Transactions, audit and revocation

Role creation, permission grant, assignment and revocation share a Unit of Work
with their audit record. Decisions record allow/deny, actor, permission, bounded
resource reference and correlation identifiers without request bodies or sensitive
resource data. Revocation takes effect on the next authoritative decision because
Mission 8 adds no authorization cache.

## Performance and extraction

The indexed decision query joins active assignments, role permissions and permission
code while checking authoritative identity status. Measure latency, pool use, deny
rate and hot roles before caching. Future caching must fail closed and bound
revocation staleness. Stable subject/action/resource contracts can later sit behind
an internal AuthZEN-compatible endpoint if extraction is approved by evidence.

## Open approvals and verification

- Final operational roles, separation of duties and emergency access require CEO
  and CTO approval.
- Workforce monitoring, audit retention and staff privacy require Ethiopian legal
  and operational verification.
- Future AYO Pay needs separate regulated authorization and dual-control design.

## Future AI-first customer support boundary

Future chat and voice support must authenticate as a dedicated `service` identity,
never as a customer, staff member or administrator. The reviewed permission set is
limited to assigned-case creation/read/update/escalation, limited trip/account
views, payment-status reads and approved guidance. Permission presence does not
itself bypass resource scoping: `read_assigned` and every limited view still require
authoritative support-domain ownership and field filtering when that module exists.

The service cannot mutate identity, payment or payout state; suspend/delete an
account; override safety, fraud, Authentication or Authorization; read unrestricted
audit evidence; or access another customer's data. Safety, fraud, finance, identity,
legal and takeover concerns must escalate to trained humans. High-risk workflows
require separately approved step-up and human authorization.

Every future AI support operation must carry a correlation ID and safe audit event.
Credentials, OTPs, tokens, payment details and unnecessary personal data are
prohibited from prompts, metadata and logs. Voice recordings and transcripts have
no approved retention period and must not be retained by default. Mission 8 creates
permission identifiers only: no service identity, role assignment, support case,
model, voice, provider or workflow implementation.
