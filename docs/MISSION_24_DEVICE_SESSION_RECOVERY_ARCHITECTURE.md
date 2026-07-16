# Mission 24 — Device Trust, Multi-Device and Recovery Architecture

Trust states remain `UNKNOWN`, `RECOGNIZED`, `TRUSTED`, `RESTRICTED`, derived from approved
method strength, session history and privacy-safe risk references. A device name or model
never proves trust. Each device has separate sessions/token families and one-device revoke;
logout-all, replay, high-risk recovery, suspension and security reset revoke the applicable
set transactionally.

Recovery types: lost/stolen device, lost/changed SIM or phone, forgotten password, lost
passkey, compromised account, driver reverification and workforce recovery. Recovery is
alternate authentication and cannot be weaker. High-risk recovery enters
`RECOVERY_PENDING`, revokes sessions, uses safe anti-enumeration responses, step-up/dual
human approval where configured and never auto-logs in after reset. Security questions are
prohibited.

Lost-device UX exposes trusted session inventory, one/all revoke, last safe activity band
and Support escalation without precise location or invasive fingerprinting.
