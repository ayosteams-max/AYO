# Mission 21 — Threat Model

Status: **Architecture proposal; security review required before implementation.**

## Assets and trust boundaries

Assets include identities, case isolation, safety reports, precise location, evidence
integrity, support communications, policy, tool authority and financial/account status.
Untrusted boundaries are user/model text, translations, uploaded files, provider output
and external incident signals. Trusted enforcement remains authenticated server context,
RBAC, case orchestrator, owning-domain projections, policy registry and audit/outbox.

| Threat | Mandatory control | Verification |
|---|---|---|
| Prompt injection/tool coercion | Treat content as data; schema-constrained output; no generic tools; deterministic broker allow-list | Adversarial corpus and forbidden-tool tests |
| Unauthorized/cross-case access | Case-scoped capability token, ownership/RBAC, purpose/sensitivity checks, no caller-selected identity | IDOR, confused-deputy and tenant-isolation tests |
| Account takeover/impersonation | Server identity, step-up for sensitive actions, anti-enumeration, recovery outside AI | Hijack/session/replay scenarios |
| Evidence tampering | Immutable references, source/version/integrity status, append-only audit, uploaded-file quarantine | Mutation/replay/provenance tests |
| Malicious uploads | Metadata-only intake first; size/type limits, quarantine and future approved scanning; model cannot execute content | Polyglot/archive/macro test corpus |
| Repeated/coordinated abuse | Idempotency, duplicate linkage, bounded rates, specialist fraud routing, symmetric appeal | Rider/driver collusion and velocity simulations |
| Social engineering | No secret disclosure or policy override from chat; verified staff identity and step-up | Staff-targeted red-team scripts |
| Model leakage/training reuse | Minimized masked prompts, contractual processing controls, no training use without approval, output leakage filters | Canary and data-exfiltration tests |
| Unsafe recovery/restriction | AI tools cannot recover/restrict; mandatory specialist | Negative authorization tests |
| Emergency abuse/under-escalation | Visible deterministic fast path; ordinary throttles cannot block; abuse reviewed after safety routing | Recall-focused multilingual safety tests |
| Provider outage/lock-in | Provider-neutral adapter, deadlines/circuit breaker, deterministic fallback and exportable evaluation corpus | Failure injection/provider swap test |
| Timeline/replay inference | Purpose-bound coarse projections, role redaction, no raw trails or restricted signals, access audit | Differencing, enumeration and re-identification tests |
| Appeal attachment abuse | Metadata validation, quarantine boundary, size/type/rate controls, no direct model execution | Malware, duplicate and evidence-spam tests |
| Voice/video impersonation | Server identity, visible participants, no voice-biometric authority, specialist verification | Spoofed-media and takeover exercises |
| Screen-share/co-browse overreach | Expiring grant, field/action allow-list, credential redaction, immediate revoke | Isolation and remote-action tests |
| Live-location leakage | Purpose/recipient/precision/expiry, revoke and restricted safety boundary | Recipient, expiry and inference tests |
| Family/diaspora confused deputy | Typed roles, separate consent/scopes, no relationship-based account authority | Cross-role IDOR tests |
| Quality/CSAT gaming | Aggregate minimisation, rubric audit and no consequential authority | Bias and purpose-creep review |
| Poisoned/stale knowledge | Approved sources, effective window, conflict fail-closed and withdrawal | Stale/conflicting article tests |
| Learning-data poisoning/privacy | Eligibility, provenance, de-identification, approval and deletion lineage | Poisoning and inference tests |

Residual critical gates: Ethiopian emergency operations, safety staffing, identity and
privacy legal review, upload processing design, provider data-processing terms and
representative Amharic safety evaluation.
