# Mission 16 — Scheduled Ride Engine implementation

**Status:** Implemented locally; CTO/CEO-approved architecture preserved. No deployment,
external provider connection, payment handling, AI ranking or production data use.

## Delivered boundary

Mission 16 adds an isolated `BACKEND.scheduled` domain for reservations, deterministic
scheduled matching, controlled soft-candidate replacement, formal commitment locking,
smart pre-dispatch, airport context, third-party booking consent, lifecycle validation
and restart-safe checkpoint recovery. Immediate dispatch remains unchanged.

All thresholds live in immutable `ReservationPolicy` records. Candidate decisions carry
the policy version, conservative ETA, bounded fairness credit and safe reason codes.
Soft replacement requires both the configured stability margin and material reliability
and lateness gains. Once committed, replacement is denied unless an approved typed
safety/reliability trigger is supplied. Current trips are never diverted.

## Persistence and rollback

Migration `20260716_0011` adds the approved reservation aggregate, participant, consent,
history, planning, commitment, soft-plan, attempt, checkpoint, flight-context and
idempotency tables. The driver commitment table uses a PostgreSQL range exclusion
constraint backed by `btree_gist`, preventing overlapping active commitments under
concurrency. Repository writes use a caller-owned transaction so reservation state,
idempotency and privacy-minimised audit records commit atomically.

Rollback before activation: back up any test data, stop scheduled workers, then run
`alembic downgrade 20260716_0010`. The downgrade removes only Mission 16 tables. It
intentionally retains `btree_gist`, because PostgreSQL extensions may be shared. No
irreversible migration is included.

## Trust, privacy and extension

The domain accepts provider-neutral place IDs and minimal participant references, never
payment credentials. Booker and passenger are distinct roles. Third-party bookings
require pending, assisted or confirmed passenger consent and support verified-contact
or assisted channels. Flight data is optional and freshness-bounded. Future AI can
implement the strategy contract in shadow mode but cannot bypass hard rules.

Production activation still requires a reviewed authenticated API, notification
adapters, provider implementations, scheduler composition, dashboards and Ethiopian
legal/operations validation. Payments and pricing remain outside Mission 16.

## Verification snapshot

The full local suite passed with 117 tests, 50 PostgreSQL tests skipped because this
workstation has no configured `AYO_TEST_DATABASE_URL`, and one pre-existing documented
wallet xfail. Branch coverage was 73.75% against the repository's 70% gate. Ruff format,
Ruff lint, strict Mission 16 mypy, Bandit and pip-audit passed. A deterministic ranking
run over 10,000 eligible candidates completed in 124.50 ms on the development machine;
this is a characterization benchmark, not a production SLO.
