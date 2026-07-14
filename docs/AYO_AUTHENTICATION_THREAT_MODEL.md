# AYO Authentication Threat Model

| Threat | Current controls | Residual requirement |
|---|---|---|
| SIM swap/intercepted OTP | OTP is not phishing-resistant; rate/risk/step-up/recovery audit | Provider/operator signals and Ethiopian procedure |
| Credential stuffing | Argon2id, generic failures, distributed limits, compromised-password seam | Thresholds/provider deferred |
| Token theft/replay | Short access life, fingerprint-only refresh, rotation/history/family revocation | Production key/device storage design |
| Session fixation/hijack | Server UUIDs, durable revocation, expiry, rotation, device risk | Cookie/mobile secure storage deferred |
| Concurrent refresh | Family row lock; consumed history; replay revocation | Client serialization on weak networks |
| Enumeration | Constant-shape message and no contact/method disclosure | Provider timing/delivery tests |
| Client privilege claim | PostgreSQL identity/status authority; no client elevation | Full Authorization mission |
| Lost/stolen device | One/all-device revocation, expiry, step-up | Recovery UX and device storage |
| Recovery/support fraud | Recovery state, revocation, audit, future dual approval | Authorization and operations procedure |
| Workforce phishing | Phishing-resistant method and high-risk step-up required | WebAuthn provider/RP approval |
| Insider/database abuse | Least privilege, audit, migration ownership | Owner monitoring and independent evidence |
| Clock manipulation | UTC authority and bounded 0–120 second skew | Multi-region time monitoring |
| Risk-signal privacy abuse | Opaque references; no raw IP/device/location in audit | Legal basis, retention, scoring governance |
| Provider outage | No provider selected; fail closed on persistence | Method-specific customer fallback |

Production blockers remain signing/key lifecycle, workforce phishing-resistant
implementation, provider approval, full Authorization, recovery operations, load and
failure testing, and Ethiopian professional privacy/regulatory review.
