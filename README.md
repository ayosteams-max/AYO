# AYO

Mission:
Build Ethiopia's most trusted super app.

Core Values:
- Quality over quantity
- Security first
- Fast and smooth
- AI-powered
- Customer trust
- Fair to drivers
- Continuous improvement

Version:
0.0.1

Current MVP:
- AYO Ride
- AYO AI
- Security

Created by:
AYO Team

Founder:
Ibrahim Shibiru

## Backend development

AYO currently supports Python 3.13. Install the exact locked application and
development dependencies with [uv](https://docs.astral.sh/uv/):

```powershell
uv sync --locked --all-groups
```

Run the API locally:

```powershell
$env:DEBUG = "true"
uv run --locked uvicorn BACKEND.main:app --reload
```

The explicit `DEBUG` value isolates a known prototype configuration issue that is
scheduled for a later approved milestone. It is not production guidance.

Run the same quality and security checks used by CI:

```powershell
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked pytest
uv run --locked bandit -c pyproject.toml -r BACKEND ayo.py
uv run --locked pip-audit
```

Update dependencies only in a dedicated reviewed change: edit constraints in
`pyproject.toml`, run `uv lock --upgrade`, inspect the lock diff, then execute the
complete check suite. Never hand-edit `uv.lock`.

### Persistence boundary

Domain services depend on protocols in `BACKEND/repositories/contracts.py`.
FastAPI dependencies select adapters from `BACKEND/repositories/registry.py`; the
current adapters are process-local development implementations only. A future
PostgreSQL adapter must pass the same repository contract and API parity tests
before it can become authoritative. Do not persist or migrate prototype wallet
balances as trusted value.

### PostgreSQL integration tests

The application still uses in-memory adapters by default. To run the PostgreSQL
foundation tests, provide a disposable PostgreSQL 17 database:

```powershell
$env:AYO_TEST_DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/ayo_test"
uv run --locked pytest -m integration
```

Integration fixtures create and remove test-only tables. Application startup never
creates schema. Do not point the test suite at a shared or production database.
GitHub Actions supplies an isolated PostgreSQL 17.10 service automatically.
