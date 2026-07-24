# AYO-RQC-1 Certification Evidence

This directory defines the evidence package structure. Generated certification
artifacts belong in `certification-evidence/` during CI and must not be committed.

Each package is classified `ENGINEERING_CERTIFICATION_EVIDENCE`, owned by Engineering
Governance and reviewed by the Project CTO. Automatic deletion is prohibited.
Production retention changes require separate legal and governance approval.

Required package contents include:

- completed `manifest.json` conforming to `manifest.schema.json`;
- JUnit and branch-coverage XML/JSON;
- Ruff format and lint results;
- MyPy result for `BACKEND` and `tests`;
- Bandit and dependency-audit reports;
- Gitleaks version and result;
- migration, concurrency, atomicity, immutability and least-privilege results;
- restart and backup/restore evidence;
- skip/xfail and canonical-marker inventory;
- artifact hashes and redaction review; and
- approval and unresolved-risk status.

Q1 establishes this structure only. It does not create certification evidence or
claim that any gate passes.
