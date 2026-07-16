# Mission 24 — Driver Onboarding, Document and Vehicle Verification

The onboarding aggregate tracks requirements and progress, not truth of documents or
eligibility. Each requirement references an owning verification result with document type,
issuer/jurisdiction, subject/vehicle binding, issue/expiry, provenance, integrity, review
state and retention class. Raw images remain in separately approved encrypted evidence
storage, never ordinary case payloads or AI prompts.

Document flow: declared metadata -> secure capture/upload boundary -> integrity/malware/
quality checks -> provider-neutral extraction proposal -> deterministic validation ->
authorized human review where policy requires -> immutable result -> expiry/recheck.
AI/OCR may extract or flag mismatch but cannot approve/deny.

Vehicle verification binds opaque vehicle ID, registration, ownership/authorization,
inspection, insurance, photos/check evidence and service capabilities. Vehicle approval
does not approve its driver; driver approval does not approve every vehicle. Changes,
expiry and suspected tampering trigger typed reverification and appeal.
