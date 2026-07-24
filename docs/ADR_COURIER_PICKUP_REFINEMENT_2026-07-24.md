# ADR: Refine the Existing Canonical Courier Pickup Capability

**Date:** 2026-07-24
**Status:** APPROVED
**Implementation:** INCREMENT 1 AUTHORIZED — PRE-PRODUCTION ONLY
**Production:** NOT APPROVED

## Context

AYO already has a canonical Courier Pickup owner and PRE-PRODUCTION foundation for
assignment admission, travel, arrival and merchant acknowledgement. Dispatch now has
append-only assignment attempts/reassignment, exposing a compatibility gap: Pickup is
currently one record per dispatch/order and lacks governed pre-custody closure and
correction evidence.

## Decision

Retain Courier Pickup as sole owner and retain its four-state core. In a future
authorized increment, add:

- one Pickup attempt per Dispatch assignment attempt;
- `pickup_attempt_ended_before_custody` as the single pre-custody terminal state;
- a closed, versioned reason taxonomy;
- append-only arrival, acknowledgement and attempt corrections;
- named, versioned, product-scoped Pickup policy;
- location-scoped merchant staff and support-assisted authority;
- provider-neutral optional location corroboration without tracking; and
- current, versioned `ready_for_custody_verification` handoff evidence.

## Rationale

This is the smallest truthful model under reassignment while assignment remains with
Dispatch and physical transfer remains with Custody. One terminal outcome plus evidence
avoids state explosion. Human acknowledgement and limited-device support avoid making
GPS a hidden authority.

## Consequences

- Existing historical Pickup records remain valid.
- A future additive migration needs assignment-attempt identity and must replace
  order/dispatch uniqueness without rewriting history.
- Consumers must process explicit corrections and source versions.
- Product policies may differ without product-specific Pickup domains.
- Attempt correlation and corrections add modest operational complexity.

## Rejected alternatives

- P2-specific Pickup: duplicate authority.
- Dispatch-owned travel/waiting: crosses the assignment boundary.
- Custody-owned arrival: combines presence with physical acceptance.
- GPS-only arrival: unreliable, inaccessible and surveillance-prone.
- Many exceptional lifecycle states: weaker than one terminal outcome plus taxonomy.

## Security, privacy and compatibility

Authorization is server-derived/action-scoped. Shared accounts and probabilistic actor
matching are prohibited. No continuous location, fingerprint, transcript, recording
or unrestricted note is admitted. Corrections never erase evidence.

This proposal refines
`AYO_COURIER_ARRIVAL_PICKUP_FOUNDATION_ARCHITECTURE.md`; it does not rewrite that
historical approval.

Approval was recorded on 2026-07-24 by OpenAI ChatGPT, Project CTO (Technical
Oversight), and Ibrahim Hambentu Shibiru, Founder & CEO. Increment 1 is bounded by the
dedicated authorization record. Production and successors remain unauthorized.
