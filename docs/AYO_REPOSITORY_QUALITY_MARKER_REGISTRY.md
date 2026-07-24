# Repository Quality Marker Registry

**Authority:** AYO-RQC-1
**Owner:** Engineering Governance
**Status:** ACTIVE — PRE-PRODUCTION

## Governance

This is the canonical inventory for pytest markers. Developers may propose a marker,
but only Engineering Governance may approve its addition, semantic change,
deprecation or replacement. Every approved marker must also be registered in
`pyproject.toml`; `--strict-markers` remains mandatory. Aliases and duplicate
semantics are prohibited.

An addition proposal must identify the tests, infrastructure dependency, certification
purpose, owner, failure behavior and removal or deprecation path.

## Canonical markers

| Marker | Purpose | Certification treatment |
|---|---|---|
| `integration` | External PostgreSQL 17 integration behavior | Mandatory with disposable database; environment skips fail certification |
| `audit` | PostgreSQL audit behavior | Mandatory |
| `persistence_kernel` | Persistence-kernel storage | Mandatory |
| `identity_compatibility` | Canonical subject/account compatibility | Mandatory |
| `identity_access` | Identity and access storage | Mandatory |
| `customer_profile` | Customer Profile and Household storage | Mandatory |
| `passenger_mobility` | R1 Passenger Mobility storage | Mandatory |
| `service_area` | Service Area behavior and PostGIS storage | Mandatory |
| `request_access` | Request Access and Interaction Provenance | Mandatory |
| `migration` | Empty disposable migration database | Mandatory |
| `session_persistence` | Session and rate-limit storage | Mandatory |
| `authentication` | Identity and authentication storage | Mandatory |
| `authorization` | RBAC authorization storage | Mandatory |
| `support` | Support foundation storage | Mandatory |
| `known_defect` | Approved characterization of an unfixed defect | Must be enumerated in certification evidence; never silently treated as a pass |

The unfiltered full suite remains authoritative. Marker executions provide explicit
evidence and cannot replace the complete suite.

## Change control

Marker changes require:

1. an Engineering Governance decision reference;
2. synchronized registry and `pyproject.toml` updates;
3. CI impact assessment;
4. chronology-preserving deprecation when applicable; and
5. confirmation that no required test becomes silently unexecuted.
