# Mission 10 — Rider Destination Search

Status: implemented and verified on 2026-07-15; awaiting final mission approval.

## Problem, beneficiary and success measure

Riders need to move from the home screen to a destination confidently, with minimal typing and useful saved, recent and airport shortcuts. Success means the home destination field opens a focused search screen; all approved categories are reachable; a selection returns to the home flow; the UI remains accessible, responsive and provider-neutral. No booking, fare, map-provider selection, persistence or location policy is added.

## Evidence, options and approved recommendation

Expo SDK 54 documents file-based stack routes and `router.push`, `back` and `dismissTo`. The existing app already uses Expo Router 6 and React Native 0.81. The simplest reliable approach is a typed `DestinationSearchGateway` injected into a dedicated screen, with a bounded offline adapter for the current non-network prototype.

Alternatives considered: embedding provider calls in the screen was rejected because it couples UI, credentials and provider schemas; adding a state/search library was rejected because current state is local and bounded; implementing a backend or choosing Google/OSM now was rejected as outside approved scope. A future remote adapter can provide pagination, caching, provider attribution and authenticated saved/recent data without changing screen contracts.

## Architecture and survivability review

The route is outside the tab navigator and returns the selected display name as navigation state. Search requests are debounced, abortable and capped at 20. Domain types, gateway, hook and presentation are separate. The gateway boundary is horizontally scalable, testable, observable by a future adapter, provider-replaceable and understandable without new infrastructure. The local catalog is an explicit prototype/offline adapter, not a production source of truth.

## Risks and edge cases

- Provider outage: the gateway exposes failure and cancellation; the UI has honest empty/error states.
- Stale responses: abort on query/category change and unmount.
- Weak devices/networks: no map surface, image payload or new dependency; lists are virtualized.
- Privacy: no precise coordinates, raw queries, saved places or location are logged or persisted.
- Accessibility/localization: labeled controls, selected state, readable contrast and touch targets are provided; Amharic strings and RTL validation remain future launch-app work.
- Production gap: remote search, authenticated saved/recent storage, real current location, provider attribution, analytics and selection IDs are deliberately excluded.

## Verification record

- Mobile lint: passed (`expo lint`).
- Strict types: passed (`tsc --noEmit`).
- Destination adapter tests: 3 passed (matching, category/limit, cancellation).
- Expo SDK compatibility: dependencies current; Expo Doctor 18/18 passed.
- Production web export: passed; eight static routes generated including `/destination-search`.
- Repository regression: Ruff passed; Pytest 54 passed, 38 PostgreSQL tests skipped because no test database was configured, and one pre-existing known-defect test xfailed; coverage 70.01% met the gate.
- Security: Bandit found zero issues. `npm audit --audit-level=high` found no high/critical advisories; 14 moderate transitive Expo toolchain advisories remain. The registry offers only a forced Expo 57 upgrade, which violates the required SDK 54 baseline and is not an approved safe fix. Recheck on the next compatible Expo 54 patch or an approved SDK upgrade.
- Privacy/performance: no query, precise location or personal-place persistence/logging was added; result work is bounded to 20, requests are debounced and abortable, and the virtualized list exported successfully.

Rollback is removal of the new route/gateway/hook and restoration of the home field navigation; there is no database, provider or API migration.

## Runtime repair

Android verification after commit `0755fb6` exposed that the committed home screen was a stale version: the root Stack and search route existed, but the complete Destination row and quick-place controls had no navigation action. The repair uses Expo Router `Link` with `asChild` so each complete `Pressable` is the navigation target, renders the returned destination parameter, marks decorative children as non-interactive, and adds source-level navigation contract tests for entry, Stack registration and return selection. There was no overlay, disabled state or pointer-events blocker.
