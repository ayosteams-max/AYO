# Mission 22 — UX Risk Register and Test Strategy

Status: **Documentation proposal only. No critical risk is accepted for launch.**

| Risk | Impact | Control | Verification |
|---|---|---|---|
| UI advances server state | Critical | Projection-only state and confirmed receipts | Offline/retry/state contract tests |
| False arrival/wait/fee impression | Critical | Mission 20 gate, evidence wording, no financial copy | Disabled/stale/paused scenarios |
| Rider/driver factual mismatch | High | Canonical references and role-redacted parity | Two-device timeline tests |
| Unsafe exact stop/walking route | Critical | Provenance/freshness/accessibility and fallback | Field simulation and ambiguity tests |
| Airport Standard/Premium leakage | High | Separate product/policy identity | Cross-product snapshot tests |
| Weak network duplicate ride/action | Critical | Idempotency and visible pending state | Packet loss/restart tests |
| Map-only exclusion | High | Textual equivalent and logical focus | Screen-reader/no-map tests |
| Driver distraction | Critical | Glanceable moving mode, parked complex tasks | Road-safety usability review |
| Amharic mistranslation/truncation | High | Native review and expansion layouts | Bilingual task tests |
| Store assets promise unshipped behavior | High | Release-manifest evidence gate | Metadata-to-build audit |
| Sensitive location leakage | Critical | Coarse role projections and minimal cache | Privacy/forensic tests |

Test synthetic Rider and Driver journeys across first use, immediate/scheduled ride,
reassignment, every Mission 20 presentation state, landmark ambiguity, walking expiry,
exact stop, accessibility, airport Standard/Premium, hospital/hotel/market/university/
stadium, app restart, offline, event gaps, GPS loss, device sleep and provider outage.

Measure task completion/error/time, duplicate command rate, stale-state comprehension,
unsafe tap rate, pickup-point identification, rider/driver fact parity, screen-reader task
completion, bilingual comprehension, data/battery use and Support contacts. Thresholds
require prototype baselines and CTO/CEO approval; production claims require field data.
