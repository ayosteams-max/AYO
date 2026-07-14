# AYO Authorization Architecture

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
