# AYO-RQC-1 Control Decisions

**Recorded:** 2026-07-24
**Status:** APPROVED — ALL CONTROL SELECTIONS RESOLVED
**Contract:** AYO-RQC-1
**Environment:** PRE-PRODUCTION ONLY
**Production:** NOT APPROVED

## Approval

- **CTO:** OpenAI ChatGPT
- **CTO role:** Project CTO (Technical Oversight)
- **Founder:** Ibrahim Hambentu Shibiru
- **Founder role:** Founder & CEO
- **Approval date:** 2026-07-24

These approvals apply specifically to the control selections in this record. Earlier
proposal, review and blocked states remain historical evidence.

## Approved controls

### Secret scanning

Gitleaks is the sole mandatory repository secret scanner.

- **Approved release:** `v8.30.1`
- **Resolved:** 2026-07-24
- **Authoritative source:** official Gitleaks GitHub Releases API,
  `https://api.github.com/repos/gitleaks/gitleaks/releases/latest`
- **Official release record:**
  `https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1`

The release must remain pinned; floating and `latest` versions are prohibited. A
scanner version change requires repository governance approval. No alternative
mandatory scanner may replace Gitleaks without a new approved ADR and repository
governance decision.

### Engineering certification evidence

- **Classification:** `ENGINEERING_CERTIFICATION_EVIDENCE`
- **Owner:** Engineering Governance
- **Review authority:** Project CTO
- **Supersession:** only an approved Repository Quality Contract revision or
  repository governance decision
- **Automatic deletion:** prohibited

Production retention periods may be refined only through separate approved legal and
governance review.

### Canonical test markers

Engineering Governance is the canonical owner of repository test-marker creation,
approval, documentation, lifecycle, deprecation and duplicate prevention.
Developers may propose markers, but only Engineering Governance may approve them as
canonical repository markers. Unmanaged marker creation is prohibited.

### Branch protection

Protected changes require at least two approvals. At least one approval must come
from the designated CODEOWNER or an approved repository owner.

Emergency bypass authority is limited to:

- Founder & CEO; and
- Project CTO.

Every bypass must create immutable audit evidence, record the reason, trigger
post-incident review and preserve repository chronology. Silent bypass is prohibited.

### PostgreSQL and PostGIS baseline

- **PostgreSQL:** major version 17
- **PostGIS:** major/minor line 3.6

Certification environments must use approved pinned versions and pinned image
digests. Floating tags and `latest` are prohibited. Digest updates require repository
governance approval.

### Resolved OCI image pin

- **Approved reference:**
  `postgis/postgis:17-3.6-alpine@sha256:88c78b602e7f2340ed46a090b78c96e9291d249517d50ea03a1cafb82d33ebe2`
- **OCI index digest:**
  `sha256:88c78b602e7f2340ed46a090b78c96e9291d249517d50ea03a1cafb82d33ebe2`
- **Resolved:** 2026-07-24
- **Authoritative source:** official Docker Hub tag API,
  `https://hub.docker.com/v2/repositories/postgis/postgis/tags/17-3.6-alpine`
- **Repository binding:** `.github/workflows/ci.yml` identifies
  `postgis/postgis:17-3.6-alpine` as the approved CI image line.

The recorded digest is the tag's OCI image-index digest returned by Docker Hub, not
an inferred platform manifest or shortened display digest.

## Resolution chronology

The first control closure recorded the approved scanner, baseline and pinning rules
but correctly left the exact release and digest unresolved. On 2026-07-24, the CTO
and Founder approved resolution from authoritative sources. The official source
queries above resolved both values without estimation, substitution or fabrication.
All AYO-RQC-1 control-selection blockers are closed.

## Authority boundary

This record performs no Q1 implementation. It changes no runtime code, CI,
PostgreSQL configuration, test, schema, migration or product capability. Q2-Q13 and
production remain unauthorized.
