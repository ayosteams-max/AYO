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
uv run --locked uvicorn BACKEND.main:app --reload
```

Application settings use the `AYO_` namespace and debug mode defaults off. Copy the
safe values from `.env.example` when local overrides are needed. Production
configuration fails closed unless PostgreSQL persistence is explicitly enabled.

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

Legacy prototype services still use process-local adapters, but canonical Identity,
Booking, Ride Request and Dispatch foundations use explicit PostgreSQL repositories and
unit-of-work transactions. Increment 19 Milestone 5 connects canonical booking to an
exclusive Immediate Dispatch handoff and accepted assignment behind disabled-by-default
activation. It requires PostgreSQL 17 plus approved Route Intelligence, driver-supply,
authentication, authorization, worker-session, rate-limit and operations dependencies.
The legacy ride/wallet adapters are not authoritative and their balances must never be
migrated as trusted value.

### PostgreSQL integration tests

In-memory adapters remain available for isolated tests, but Increment 19 Milestone 1
removed their legacy public ride and wallet routes from the default application. To run
the PostgreSQL foundation tests, provide a disposable PostgreSQL 17 database:

```powershell
$env:AYO_TEST_DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/ayo_test"
uv run --locked pytest -m integration
```

Integration fixtures create and remove test-only tables. Application startup never
creates schema. Do not point the test suite at a shared or production database.
GitHub Actions supplies an isolated PostgreSQL 17.10 service automatically.

Run reviewed migrations as a controlled job; application startup never creates or
migrates schema:

```powershell
$env:AYO_DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/ayo_local"
$env:AYO_DATABASE_SSL_MODE = "disable" # local test database only
uv run --locked python -m database.migrate
```

`/health` remains the shallow compatibility probe. `/livez` reports process lifecycle
and `/readyz` reports database plus exact migration-head readiness. Probe responses use
stable categories and never include database credentials or exception details.

Increment 19 Milestone 2 adds canonical authentication routes behind
`AUTHENTICATION_ENABLED`. Enabling them requires explicit PostgreSQL composition,
asymmetric signing/verification keys and an identifier-pepper secret; the repository
contains no fallback production credential. The default application remains fail closed.
