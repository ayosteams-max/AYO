# Mission 20 — Smart Arrival, Waiting and Fair Cancellation Architecture

Date: 2026-07-16  
Status: **CTO and CEO approved 2026-07-16 for bounded implementation. Fixed policy
values, providers, financial actions, commit, push and production activation remain
unauthorized.**

## Approved architecture amendment

The CTO/CEO amendment approves inclusion of Smart Pickup Readiness and a
configuration-driven Dynamic Waiting Policy in the Mission 20 proposal. It does not
approve fixed durations, fees, refunds, compensation, automatic cancellation, provider
selection or implementation.

## Boundaries and ownership

Mission 20 remains a deterministic, evidence-producing module inside the approved
modular monolith.

- Dispatch continues to own Immediate matching and assignment.
- Scheduled Dispatch continues to own reservation, commitment and pre-dispatch logic.
- Active Ride owns the post-assignment lifecycle and pickup-start transition.
- Dynamic Pickup owns approved pickup recommendations and material-change confirmation.
- Mission 20 owns arrival observations, readiness decisions, selected waiting-policy
  snapshots, timer evidence and consequence-suppression evidence only.
- Notification delivery owns channel attempts and delivery status; Mission 20 may issue
  an advisory intent but cannot treat delivery as acknowledgement.
- Pricing owns any later approved fee calculation; the ledger owns value movement;
  Support/Recovery owns separately approved review and refund recommendations.

The engine cannot assign/reassign a driver, relocate pickup, start a trip, cancel a
ride, establish blame, charge, refund, compensate or create a hidden reputation score.

## Smart Pickup Readiness

### Inputs

Use only policy-approved, fresh, purpose-limited signals:

- server-authoritative driver ETA range and freshness;
- rider location freshness/accuracy when lawfully available;
- bounded recent rider movement toward the approved pickup point;
- rider walking-time range to the same approved pickup point;
- approved venue/landmark boundary confidence, without asserting precise indoor
  position;
- pickup recommendation version and accessibility context;
- notification history, current connectivity and known provider/platform disruption.

Raw location trails remain with their owning domain. The readiness decision stores
derived facts and opaque evidence references, not a copied trail.

### Decision contract

Each evaluation produces one classification:

- `moving_toward_pickup`;
- `likely_on_time`;
- `possibly_inside_building_or_venue`;
- `unlikely_on_time`; or
- `insufficient_data`.

It also records a basis-point confidence score, policy/rule version, reason codes,
signal freshness, generated/expiry times, audit evidence references and a
human-readable explanation. “Possibly inside” is explicitly an inference and is not
shown as surveillance-style certainty to either party.

### Notification decision

A notification intent is allowed only when the readiness decision is fresh, the pickup
point is unchanged, driver ETA and rider walking ETA create an actionable window, and
confidence meets the selected policy. The policy defines:

- eligible readiness classifications and minimum confidence;
- minimum time since the prior readiness prompt;
- maximum prompts per ride;
- material ETA/readiness change required before another prompt;
- quiet/suppression behavior for stale data, acknowledged movement, accessibility,
  notification failure and operational disruption;
- localized template identifier and explanation reason code.

The example message is a localized template parameterized by an ETA range; it is not
assembled from untrusted text. A prompt never starts arrival or waiting. Delivery,
display and acknowledgement are distinct audit outcomes.

## Dynamic Waiting Policy

### Configuration model

Waiting policy is immutable and versioned once published. Selection inputs support:

- pickup context: airport, hotel, hospital, shopping centre or residential;
- ride origin: Immediate or Scheduled;
- service context, including Airport Standard and Airport Premium without inheritance
  that silently changes Standard;
- approved accessibility requirements;
- severe-weather classification and source freshness;
- city/service-area and approved operational policy or temporary override.

A policy snapshot may define free-wait duration, ending-warning offsets, driver
departure tolerance, pause/invalidation behavior, notification requirements, confidence
thresholds and manual-review requirements. Actual values remain leadership/legal/
operations decisions and are absent from this architecture.

Selection uses explicit precedence and records every matched dimension, selected policy
ID/version and override reason. Operational overrides must be authorized, time-bounded,
audited and unable to introduce an unapproved financial rule. Missing, expired,
ambiguous or conflicting configuration yields `policy_unavailable` and suppresses all
consequence eligibility.

### Timer semantics

The server is authoritative for elapsed time. Waiting can start only after verified
arrival under the selected policy snapshot. The snapshot remains fixed for that waiting
episode so a configuration publication cannot alter an active countdown retroactively.
Driver departure, pickup change, stale/conflicting evidence, provider/platform failure,
unsafe access or external disruption produces a policy-defined pause or invalidation.
Resume creates an auditable continuation; it does not erase elapsed history.

Immediate and Scheduled rides share timer mechanics but never share an implicit policy:
the ride origin is a required selector input. Airport and venue contexts require an
approved zone/pickup version. Airport Premium selects its own approved policy without
modifying Airport Standard or ordinary Standard rides.

## Evidence, explanations and audit

Every material readiness, arrival, policy-selection, timer, notification and
suppression decision records:

- ride, assignment and approved pickup references;
- rule and configuration versions;
- confidence score and stable reason codes;
- source freshness and data-quality status;
- server timestamps and idempotency identity;
- privacy-minimized evidence references;
- responsibility as `insufficient_evidence` unless a separately authorized process
  establishes otherwise;
- role-appropriate human-readable explanation.

Candidate reason families add `readiness.movement.*`, `readiness.timing.*`,
`readiness.venue_context.*`, `readiness.data_quality.*`, `notification.cooldown.*`,
`notification.suppressed.*`, `waiting_policy.context.*`,
`waiting_policy.override.*` and `waiting_policy.unavailable.*`.

## Failure, privacy and scale behavior

- Stale, missing, spoof-suspected or conflicting rider evidence cannot be used against
  the rider and suppresses readiness inference or consequence eligibility.
- Readiness must not expose one party's precise location or inferred building presence
  to the other party.
- Notification outage cannot become proof of rider fault. Map/ETA outage degrades to
  safe static guidance and prevents consequential evidence where timing is material.
- Evaluations are bounded per ride, idempotent and horizontally partitionable by ride
  ID. Published configuration is cacheable by version, while the durable snapshot
  preserves reproducibility and provider outage resilience.
- Policy/configuration changes require validation, authorization, audit, staged rollout
  and rollback to a previously published version. They cannot rewrite historical
  evidence.

## Approved architecture and implementation gate

CTO and CEO approved these module boundaries, readiness constraints, notification
controls, policy configuration, server-time semantics, failure suppression and audit
separation on 2026-07-16. Before coding, Workflow Step 5 must record the full risk and
edge-case register with test mapping. Implementation must remain within the approved
evidence-only boundary and stop for final review before any implementation commit or
activation.
