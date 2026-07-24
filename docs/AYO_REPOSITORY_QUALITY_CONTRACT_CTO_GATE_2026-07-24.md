# CTO Gate — Repository Quality Contract Q0

**Date:** 2026-07-24
**Status:** APPROVED
**Q1 implementation:** IMPLEMENTATION AUTHORIZED (PRE-PRODUCTION ONLY)
**Production:** NOT APPROVED

## Approval closure

- **CTO:** OpenAI ChatGPT, Project CTO (Technical Oversight)
- **Founder:** Ibrahim Hambentu Shibiru, Founder & CEO
- **Approval date:** 2026-07-24
- **Contract:** AYO-RQC-1 APPROVED
- **Q1:** IMPLEMENTATION AUTHORIZED (PRE-PRODUCTION ONLY)
- **Q2–Q13:** NOT AUTHORIZED

The preceding review-ready, not-approved state remains historical evidence. This
closure does not claim that any quality gate currently passes.

## Approved contract scope

The approved contract `AYO-RQC-1` includes:

- tests-inclusive MyPy with zero errors;
- 70.00% branch coverage over all `BACKEND`;
- zero mandatory database skips;
- disposable PostgreSQL 17 and approved PostGIS 3.x certification;
- migration, concurrency, immutability, least-privilege, restart and restore gates;
- Ruff, Bandit, dependency, secret and sensitive-data gates;
- one evidence manifest tied to one commit;
- proposed protected-branch responsibilities; and
- separation of PRE-PRODUCTION certification from production release approval.

## Approved decision

The contract definitions are approved. Q1 must align or prepare the following
bounded controls without performing later remediation:

1. `mypy BACKEND tests` as the canonical zero-error scope;
2. the pinned secret scanner and policy;
3. required-marker inventory ownership;
4. evidence retention classification and duration;
5. branch reviewer/code-owner/bypass administration; and
6. the exact approved PostGIS image/digest policy.

## Current contradictions

MyPy has three scopes: repository config, CI subset and mission-expanded tests.
Secret scanning and branch protection are not reproducibly recorded. CI database
provisioning exists, but local missing-infrastructure skips are not certification.

## Control-decision closure

On 2026-07-24 the named CTO and Founder approved:

- Gitleaks as the sole mandatory scanner, with governance-controlled version pins;
- `ENGINEERING_CERTIFICATION_EVIDENCE`, owned by Engineering Governance, reviewed by
  the Project CTO and not subject to automatic deletion;
- Engineering Governance as canonical test-marker owner;
- two required approvals, including a designated CODEOWNER or approved repository
  owner, with emergency bypass limited to the Founder & CEO and Project CTO and
  requiring immutable evidence and post-incident review; and
- PostgreSQL 17 with PostGIS 3.6, using governance-approved immutable image digests.

The initial control closure did not supply the exact Gitleaks release or OCI digest.
The approved authoritative-source resolution on 2026-07-24 subsequently established:

- Gitleaks `v8.30.1`, from the official GitHub Releases API and release record; and
- `postgis/postgis:17-3.6-alpine@sha256:88c78b602e7f2340ed46a090b78c96e9291d249517d50ea03a1cafb82d33ebe2`,
  using the OCI image-index digest returned by the official Docker Hub tag API.

All Q1 governance control-selection blockers are closed. This does not claim Q1
implementation has begun or that any engineering gate currently passes.

## Authority boundary

This governance-closure mission does not:

- modify CI or configuration;
- begin the authorized Q1 implementation;
- execute PostgreSQL;
- remediate MyPy or coverage;
- implement a schema, migration, API or test; or
- authorize production, Custody, Delivery or another capability.

## Gate state

**APPROVED — Q1 IMPLEMENTATION AUTHORIZED (PRE-PRODUCTION ONLY)**

The authority contradiction is resolved at governance level. Existing configuration
and CI remain unchanged until Q1 implements the approved alignment. Production and
Q2–Q13 remain prohibited.
