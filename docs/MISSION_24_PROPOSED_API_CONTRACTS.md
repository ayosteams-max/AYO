# Mission 24 — Proposed API Contracts

Status: **Non-runtime proposal; no routes authorized.**

Potential contracts: create/read proofing case; request/verify phone challenge; request/
confirm email; list/revoke device sessions; start/retrieve recovery; submit onboarding
metadata; request document/vehicle review; retrieve assurance/eligibility projection;
create/retrieve appeal; manage business/participant grants.

All commands use trusted identity, RBAC/resource ownership, idempotency, expected version,
step-up where required, bounded payload/rate, safe anti-enumeration failures and audit.
Uploads use separately approved pre-signed/quarantine boundaries—not API bodies. No client
supplies authoritative identity, approval, trust, eligibility, role or reviewer result.
