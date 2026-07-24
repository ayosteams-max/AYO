# AYO-RQC-1 Validation Commands

**Authority:** AYO-RQC-1
**Status:** ACTIVE — PRE-PRODUCTION

Run from the repository root in a locked environment.

## Canonical commands

```text
uv lock --check
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy BACKEND tests
uv run --locked pytest --junitxml=certification-evidence/pytest-results.xml --cov-report=xml:certification-evidence/coverage.xml --cov-report=json:certification-evidence/coverage.json
uv run --locked bandit -f json -o certification-evidence/bandit.json -c pyproject.toml -r BACKEND ayo.py database/certify_restore.py
uv run --locked pip-audit --format=json --output=certification-evidence/pip-audit.json
git diff --check
```

Secret scanning uses Gitleaks `v8.30.1` after verifying the official Linux x64
release archive SHA-256:

```text
551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
```

The canonical scan is:

```text
gitleaks dir . --no-banner --redact=100 --report-format=json --report-path=certification-evidence/gitleaks.json
```

PostgreSQL certification uses:

```text
postgis/postgis:17-3.6-alpine@sha256:88c78b602e7f2340ed46a090b78c96e9291d249517d50ea03a1cafb82d33ebe2
```

and the repository integration, migration, backup/restore, restart, concurrency,
atomicity, immutability and least-privilege suites. A missing database or mandatory
skip is not a certification pass.

## Evidence rules

Commands, versions, exit codes and artifact hashes must be recorded against one
reviewed commit. Local feedback is not certification. Generated output is staged in
`certification-evidence/`, excluded from Git, redacted, and then transferred to the
approved immutable evidence store. A temporary CI artifact is transport evidence,
not the authoritative retained package.

The authoritative retained package follows `quality/evidence/manifest.schema.json`
and the `ENGINEERING_CERTIFICATION_EVIDENCE` classification.
