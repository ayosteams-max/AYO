# Mission 1 Implementation Roadmap

Mission: Build the AYO engineering foundation  
Status: active; milestones require separate approval  
Last reviewed against repository: 2026-07-15

This plan is subordinate to `AYO_CONSTITUTION.md`. Constitutional compliance is required at every milestone gate.

Mission execution also follows `AYO_ENGINEERING_WORKFLOW.md`. Existing milestone approval records remain historical evidence; all remaining work must satisfy the workflow's research, recommendation, CTO/CEO approval, design, risk, implementation, test, verification, documentation and stop gates.

## Mission objective

Make the existing FastAPI prototype reproducible, testable and safe to evolve without adding product features or silently changing current behavior.

## Governing constraints

- Preserve the current 12-route prototype unless a milestone explicitly explains and tests a necessary change.
- Do not repair the wallet, redesign dispatch, add persistence or begin authentication in Mission 1.
- Treat the confirmed wallet commission defect and anonymous/caller-authoritative financial API as known risks, not accepted production behavior.
- Use synthetic test data only. Do not add Ethiopian identity, payment or location data.
- Keep future PostGIS, weak-network, immutable-ledger, provider-adapter and AI boundaries visible, but do not implement them prematurely.
- Complete and report each milestone, then wait for Founder/leadership approval before starting the next.
- Before implementation, explain each technical choice, alternatives and risks. Major architecture/product choices require CTO review and CEO approval.

## Current repository comparison

| Foundation requirement | Current state | Mission 1 response |
|---|---|---|
| Repository hygiene | `.venv` and generated `__pycache__` files exist; no root `.gitignore` | Milestone 1 adds protective ignore rules without deleting files. |
| Reproducible environment | Local `.venv` contains only `pip`; no dependency manifest or supported Python declaration | Milestone 2 adds reviewed project metadata and a deterministic installation path. |
| Behavior protection | No automated tests; current flow was verified only through manual smoke checks | Milestone 3 characterizes the current API and critical service behavior before runtime refactoring. |
| Safe configuration | Generic `DEBUG` can collide with host variables; debug defaults true | Milestone 4 introduces namespaced, validated settings with compatibility analysis and tests. |
| Quality/security automation | No lint, type, test, dependency or secret gates; no CI | Milestone 5 adds local and CI gates pinned to the project toolchain. |
| Operating documentation | README does not explain setup, checks, constraints or known prototype risks | Milestone 6 documents the verified workflow and closes Mission 1. |

## Milestone 1 — Repository safety and change boundary

**Objective:** Prevent accidental commits of local environments, generated files, secrets and runtime artifacts, and establish the approval-gated execution plan.

**Scope:** Root `.gitignore`, this implementation roadmap, inventory/status validation and confirmation that runtime source is untouched.

**Exclusions:** No deletion of existing caches or environments, no dependency installation, no Python/code/configuration changes and no CI.

**Technical work:** Add categorized ignore rules for Python, environments, secrets, test/build output, local data and editor files. Keep `.env.example` eligible for future version control.

**Tests:** Validate representative ignored paths with `git check-ignore`; verify requested governance files remain visible; parse/import/smoke-check the unchanged backend using the already available environment.

**Security checks:** Ensure `.env`, private keys, virtual environments, logs and local databases are ignored; do not ignore source, migrations, public documentation or the future safe `.env.example`.

**Acceptance criteria:** Ignore rules behave as intended; no tracked or working runtime source is deleted/modified; the milestone plan is complete; verification passes or limitations are recorded.

**Dependencies:** Mission authorization already granted.

**Status:** Completed 2026-07-14. Validation confirmed representative secret, environment, cache, log and local-database paths are ignored; governance/source paths and `.env.example` remain visible; all 16 Python files parse; OpenAPI retains 12 paths; and the unchanged synthetic ride smoke flow reaches `TRIP_COMPLETED`.

## Milestone 2 — Reproducible Python project and dependency policy

**Objective:** Allow a clean machine and CI to install the same supported application and development toolchain.

**Scope:** `pyproject.toml`, supported Python range, direct runtime/dev dependencies, lock strategy, package/import layout decision and deterministic install commands.

**Exclusions:** No runtime behavior change, dependency upgrades without compatibility evidence or container/deployment build.

**Technical work:** Inventory actual imports, select compatible pinned ranges/lock mechanism, declare FastAPI/Pydantic/settings/ASGI runtime and test/quality tools, and document dependency-update policy.

**Tests:** Clean-environment installation, dependency consistency, backend import and OpenAPI generation.

**Security checks:** Dependency audit, hash/lock integrity where supported, trusted package sources and review of transitive vulnerabilities/licences.

**Acceptance criteria:** One documented command creates a working environment; dependency versions are reproducible; import/OpenAPI checks retain current behavior.

**Dependencies:** Milestone 1 and explicit approval.

**Status:** Completed 2026-07-15 under explicit CEO and CTO approval. Added
standard project metadata, Python 3.13 declaration, exact cross-platform lock,
documented install/update policy, and verified a locked environment can import
the backend and generate all 12 existing OpenAPI paths. The expanded approval
also authorized an initial regression suite and CI/security gates; those do not
replace the deeper scopes or approval gates of Milestones 3–5.

## Milestone 3 — Characterization and regression test suite

**Objective:** Protect current working behavior before changing runtime configuration or architecture.

**Scope:** Test structure/fixtures, current route inventory, ride happy path, invalid transitions, dispatch eligibility/ordering, wallet calculations and explicit known-defect tests or quarantine markers.

**Exclusions:** No defect fixes, new endpoints, database or authentication.

**Technical work:** Use isolated in-memory state fixtures, deterministic synthetic drivers/times where necessary, API-level tests and service-level financial invariants. Distinguish intended behavior from captured defects.

**Tests:** Root/health/OpenAPI, validation, no-driver path, offer ownership/status, ride lifecycle, duplicate/race-risk characterization, cash/digital wallet and withdrawal boundaries.

**Security checks:** Verify current unauthorized exposure as a documented launch blocker without normalizing it as acceptable; ensure test output contains no secrets or real personal data.

**Acceptance criteria:** Tests are deterministic and isolated; current intended behavior passes; known defects are visible and cannot disappear unnoticed; no runtime code is changed merely to make tests pass without explanation.

**Dependencies:** Milestone 2 and explicit approval.

**Status:** Not started.

## Milestone 4 — Production-safe configuration foundation

**Objective:** Remove ambiguous host-environment behavior and establish validated environment-specific defaults.

**Scope:** `AYO_`-namespaced settings, debug-off default, environment selection, documentation-safe `.env.example`, startup validation and compatibility plan.

**Exclusions:** No secret manager integration, authentication, CORS/product policy or deployment infrastructure.

**Technical work:** Update settings using current Pydantic Settings conventions; explicitly define development/test/production behavior; avoid reading unrelated `DEBUG`; keep necessary compatibility only when safe and time-bounded.

**Tests:** Defaults, environment overrides, invalid values, production safeguards, no generic-variable collision, backend import and full characterization suite.

**Security checks:** No secrets in defaults/examples; production debug/docs posture documented; failure messages do not expose sensitive values.

**Acceptance criteria:** `DEBUG=release` cannot break AYO startup; production defaults are safe; configuration is documented and fully tested; all behavior changes are explained.

**Dependencies:** Milestone 3 and explicit approval.

**Status:** Not started.

## Milestone 5 — Automated quality and security gates

**Objective:** Make every future change pass consistent engineering checks before merge.

**Scope:** Formatter/linter, type checks at an achievable strictness baseline, tests/coverage reporting, secret scanning, dependency audit and CI workflow.

**Exclusions:** No production deployment, cloud resources or arbitrary coverage target that encourages low-value tests.

**Technical work:** Configure pinned tools in `pyproject.toml`, define one local verification command, add CI with least permissions/caching discipline and document triage/exception rules.

**Tests:** Run all gates locally where possible and in CI; intentionally verify representative gate failures in configuration review.

**Security checks:** Pin third-party CI actions, minimize workflow permissions, prevent secret exfiltration, audit dependencies and retain evidence of justified exceptions.

**Acceptance criteria:** A clean checkout runs the same gates locally and in CI; failures are actionable; all current code either passes or has narrow documented debt with ownership.

**Dependencies:** Milestones 2–4 and explicit approval.

**Status:** Not started.

## Milestone 6 — Developer workflow and Mission 1 closure

**Objective:** Make the foundation understandable, repeatable and ready for Mission 2 review.

**Scope:** README development workflow, commands, architecture boundary, known risks, test strategy, troubleshooting, decision/roadmap status and final clean-environment verification.

**Exclusions:** No product features or Mission 2 domain/persistence interfaces.

**Technical work:** Document setup/run/check steps, supported environment, prototype limitations, contribution/change process and approval gates; reconcile governance documents with actual state.

**Tests:** Execute documented setup and verification from a clean environment; compare route inventory and smoke behavior; review links and commands.

**Security checks:** Documentation contains no credentials or unsafe production shortcuts; risks remain explicit; Ethiopian legal questions remain unresolved rather than guessed.

**Acceptance criteria:** A new engineer can reproduce and verify the backend; Mission 1 roadmap items are evidenced; no product feature was added; leadership receives a closure report and proposed next mission.

**Dependencies:** Milestones 1–5 and explicit approval.

**Status:** Not started.

## Approval record

| Milestone | Approval | Completion evidence |
|---|---|---|
| 1 | Approved by the user's instruction to start Milestone 1 | `.gitignore` validation, 16-file Python parse, 12-path OpenAPI check and synthetic ride completion passed on 2026-07-14. |
| 2 | CEO and CTO approval granted in the 2026-07-15 instruction | `pyproject.toml`, `uv.lock`, Python 3.13 environment, 12-path import/OpenAPI check, Ruff, 6 passing tests plus 1 known-defect xfail at 78% coverage, Bandit and pip-audit clean, and GitHub Actions CI. |
| 3 | Not approved | — |
| 4 | Not approved | — |
| 5 | Not approved | — |
| 6 | Not approved | — |
