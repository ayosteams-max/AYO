# Mission 24 — Identity and Verification Threat Model

| Threat | Mandatory control | Verification |
|---|---|---|
| Enumeration/OTP abuse | Uniform responses, distributed limits, bounded challenge/resend | Timing/delivery tests |
| SIM swap/interception | OTP assurance limits, step-up, recovery hold and operator seam | SIM scenarios |
| Credential stuffing/phishing | Argon2id, compromised-secret seam, passkeys/MFA, rate limits | Adversarial login |
| Token/session theft | Short access, rotating refresh, replay family revoke, device inventory | Theft/concurrency |
| Synthetic/stolen identity | Multi-source proofing, integrity, human review, no AI approval | Fraud corpus |
| Document forgery/replay | Hash/reference, issuer/provenance, duplicate/tamper checks | Forgery/replay |
| Selfie/biometric spoof | No provider selected; liveness/biometric separate gate and appeal | PAD/bias evaluation |
| Vehicle substitution | Driver-vehicle binding, periodic/incident reverification | Swap tests |
| Account sharing | Session/device anomaly escalation; no silent sanction | Multi-device simulations |
| Recovery social engineering | No security questions, safe responses, step-up/dual control | Support red team |
| Insider approval/policy abuse | Least privilege, separation, immutable decisions, dual publication | Privilege tests |
| Cross-account/case exposure | RBAC, resource scoping, opaque IDs, field projections | IDOR tests |
| AI/model manipulation | Untrusted extraction/advice, schema validation, human/deterministic authority | Prompt/poison tests |

Emergency access and account restrictions remain Safety/Authorization responsibilities;
identity evidence cannot be repurposed silently for dispatch, pricing or marketing.
