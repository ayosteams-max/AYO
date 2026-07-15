# Deferred Future Architecture — Recovery, Trust and AI Customer Support

Date: 2026-07-16
Status: **Architecture direction recorded by CTO/CEO amendment; deferred and not authorized for implementation.**

This document records two future engines without changing Mission 17, its validated
PostgreSQL schema or any runtime behavior. Detailed policies, financial limits, data
retention, model/provider choices and implementation sequencing require later evidence,
CTO review and CEO approval. Ethiopian legal and operational review remains mandatory.

## Customer Recovery and Trust Engine

### Purpose and boundary

The future engine investigates confirmed operational failures and recommends a fair,
explainable recovery response. It does not automatically approve every complaint and
does not own payments, wallets, dispatch, safety adjudication or account enforcement.
It consumes purpose-limited evidence through provider-neutral read contracts and emits
an idempotent recommendation or a typed human-review requirement.

Candidate incidents include non-arrival, repeated driver cancellation, breakdown,
failed airport pickup, material AYO-caused delay, incorrect fare or charge, verified app
or dispatch failure, lost-item cases, verified poor service and safety incidents that
must be escalated.

### Evidence and responsibility model

Evidence may reference approved trip/reservation state, timestamps, dispatch attempts,
payment status—not credentials—communication delivery status and immutable audit
events. Source records stay with their owning domains. The engine stores minimum
decision evidence and opaque references, not copied location trails, conversations or
payment data.

Every investigation produces one responsibility classification:

- rider responsibility;
- driver responsibility;
- AYO/platform responsibility;
- verified external disruption;
- shared responsibility; or
- insufficient evidence.

Traffic, accidents, road closures, emergencies, platform failures and other verified
external causes must protect drivers from blame or hidden penalties. Neither riders nor
drivers receive an undisclosed punishment score.

### Recommendation contract

Versioned, configurable policies may recommend priority rebooking, refund eligibility,
ride credit, next-trip discount, apology/status notification, fault-free driver
compensation, human support, fraud/abuse review or operational incident review. A
recommendation records policy version, safe reason codes, evidence sufficiency,
responsibility class, financial-limit band, idempotency identity and expiry.

Financial execution is explicitly outside this engine. Future payment and wallet
actions must use provider-neutral approved interfaces, immutable financial records and
their own authorization. No automated refund, credit, payout or compensation is
authorized by this architecture entry.

Human approval is mandatory for safety/legal matters, high-value or ambiguous claims,
account takeover, suspected fraud/collusion, payouts, irreversible actions and any case
without sufficient evidence. Duplicate-claim fingerprints, bounded claim frequency,
prior-decision linking and human appeal protect against abuse without silently punishing
legitimate repeat reporters.

### Audit, privacy and failure behavior

Decisions are deterministic for the same policy and evidence snapshot, idempotent,
versioned and auditable. Access is purpose-scoped and least-privileged; retention is
class-specific and requires legal approval. Missing/stale/conflicting evidence produces
`insufficient_evidence` or human review, never an invented conclusion. Engine outage
leaves support available and cannot block rides, reservations or safety escalation.

Mission 18's future Active Ride Confidence decisions and confirmed Dynamic Pickup
outcomes are eligible evidence references only when their rule/source version,
freshness and later operational outcome are preserved. A health level is not fault, and
a pickup recommendation is not proof that a person followed it. Recovery must obtain
corroborating domain evidence and retain the existing responsibility/human-review rules.

## AI Customer Support Engine

### Purpose and operating model

The future AI-first support system acknowledges a rider, driver, booker, passenger or
trusted contact immediately, then distinguishes acknowledgement from verified final
resolution. It uses the existing support-case authority, approved tools and structured
evidence to resolve routine low-risk issues within seconds when policy and evidence
permit. It never guesses to meet a speed target.

Context resolution may inspect only the minimum approved view of the current ride,
scheduled reservation, dispatch state, account state, notification delivery and known
system health. Users should not repeat information AYO already possesses. Tool results,
policy versions, actions, customer-visible explanations and handoffs remain auditable;
hidden model reasoning is neither required nor stored.

### Routine and prohibited authority

Potential pre-authorized workflows include booking/reservation status, driver-delay and
cancellation explanations, no-driver recovery, pickup-verification help, fare or
payment-status explanations, lost-item case creation, notification troubleshooting,
account-access triage, priority rebooking and an approved low-risk recovery or credit
recommendation. Any actual financial action remains outside this architecture and needs
the Customer Recovery and Trust Engine plus approved financial authority.

Mandatory human escalation applies to safety incidents, harassment/assault, legal
requests, identity disputes, account takeover, fraud/collusion, payment disputes,
payouts, high-value compensation, ambiguous evidence, repeated unresolved complaints,
vulnerable passengers and emergencies. Handoff includes a concise case summary,
purpose-minimised evidence references, actions attempted and unresolved questions.

### Safety, privacy and availability

The engine uses dedicated least-privileged service identity and existing support-case
authorization. Prompt/input content is untrusted. Policy and tool authorization—not
model confidence—control actions. Unavailable, uncertain or contradictory AI falls back
to deterministic support policy and human service. It cannot weaken emergency, fraud,
identity, financial or privacy controls.

Future AI may explain a public Active Ride Confidence reason or Dynamic Pickup guidance
from an authorized projection, but cannot infer blame, expose raw signals, execute a
recommendation or silently relocate pickup. Any shadow comparison with deterministic
confidence production authority remains non-executing until separately approved.

Provider-neutral channel contracts must support app chat, SMS, voice and call-centre
workflows under weak connectivity, with Amharic and English as first-class evaluation
languages. No channel or model provider is selected here. Future human-supervised
learning may use only confirmed case outcomes under approved consent, minimisation,
retention, bias and evaluation controls.

### Performance principles

- acknowledge immediately;
- diagnose routine cases within seconds;
- resolve within seconds only when evidence and authority are sufficient;
- provide calm progress updates when investigation continues;
- measure accuracy, containment quality, escalation quality, language quality, privacy
  failures, latency, cost and repeat-contact rate; and
- never trade accuracy, safety, fairness or privacy for response speed.

## Future approval gates

Before implementation, each engine requires its own mission covering evidence research,
alternatives, threat model, user journeys, responsibility and recovery policy, financial
authority, abuse controls, retention, Ethiopian legal/operational verification,
multilingual evaluation, deterministic fallback, human staffing and rollback. Provider,
model, payment, wallet and public activation decisions remain separate approval gates.
