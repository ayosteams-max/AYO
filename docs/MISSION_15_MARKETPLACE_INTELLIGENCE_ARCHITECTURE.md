# Mission 15 — Deterministic Marketplace Intelligence Architecture

Status: **Architecture approved by CTO and CEO; deterministic implementation complete and awaiting final review.**

Date: 2026-07-16

## 1. Problem, beneficiaries and measurable success

AYO needs to observe whether its immediate-ride marketplace is healthy and recommend bounded operational responses without turning one opaque score into pricing, dispatch or livelihood authority. Riders benefit from shorter, more reliable pickup; drivers benefit from less unpaid idle/deadhead time and visible, fair opportunity; operations benefit from early warnings; AYO benefits only when those outcomes remain sustainable together.

The simpler safe solution is a deterministic advisory engine inside the modular monolith. It consumes privacy-minimized aggregates and immutable domain events, produces versioned snapshots, forecasts and recommendations, and never directly changes fares, driver eligibility or ride assignment. Mission 12 dispatch continues to prioritize fastest pickup among suitable drivers.

Proposed success measures, whose launch thresholds require field baselines and leadership approval:

- rider request-to-assignment and request-to-pickup p50/p90/p95 by service zone and time;
- driver utilization, idle minutes, pickup deadhead minutes and net earning opportunity per online hour;
- opportunity distribution and worst-decile gaps among comparable eligible drivers;
- rider/driver cancellation, no-driver and offer-expiry rates with reason attribution;
- ETA calibration error and external-delay attribution confidence;
- recommendation precision, stability, operator acceptance and measured outcome after intervention;
- zero use of prohibited characteristics, zero automatic fare changes and complete decision replayability.

## 2. Evidence and competitor comparison

Public evidence is directional, not proof of internal algorithms or Ethiopian performance.

| Operator | Publicly supported approach | Weakness/limitation AYO should avoid |
|---|---|---|
| Uber | Describes marketplace health as balancing rider reliability and driver earnings, demand signals, dynamic pricing and minimizing collective wait rather than blindly choosing physical proximity. Its public principles emphasize clarity about matching and pricing. | Public explanations remain high-level; variable rider/driver economics and experimentation can be hard for participants to understand. AYO should expose stable reason codes, policy versions and measured guardrails internally and approved explanations externally. |
| Grab | Describes allocation across a bounded nearby pool, suitability, traffic/road conditions, idle reduction, dynamic supply-demand balance and demand guidance using historical/live context such as weather and events. | Mature optimization can reward behavioral settings or area history in ways that are difficult to contest. AYO must not turn acceptance settings, geography familiarity or ratings into hidden livelihood penalties. |
| Bolt | Shows upfront earning information, demand-area guidance, dynamic pricing and bonuses; some markets support a driver minimum expected fare. | Market-specific flexible commissions and incentives can obscure long-run distribution. AYO separates recommendation from pricing authority and measures opportunity/earnings distribution before intervention. |
| Lyft | Public material supports ETA-led matching and marketplace balancing; detailed current allocation internals are not publicly verifiable. | Sparse public transparency means AYO must not copy inferred mechanisms. Use measurable contracts and disclose only verified comparisons. |
| DiDi | Public material establishes very large ride-hailing marketplace operations, inclusion and sustainability goals, but accessible first-party detail on current matching/fairness rules is limited. | Scale is not evidence that an opaque optimizer fits Ethiopia. AYO starts deterministic and advances only from local measurements. |
| Yango | Official material describes proprietary routing, demand-dependent driver earnings, stacked rides and airport queues in some markets. | Priority statuses and bonus systems can create opaque hierarchy. AYO keeps airport logic separate and forbids purchased or unexplained priority in immediate dispatch. |
| RIDE | Public listings support app and dispatch-centre booking, airport service and phone-number masking. | No verified public marketplace algorithm or fairness metrics were found. Assisted booking is useful evidence; undisclosed ranking is not. |
| Feres | Official material supports nearest-car claims, upfront price display, tracking, call-centre access and multiple payment modes. | No verified technical allocation/fairness disclosure was found. AYO should measure real pickup outcomes and retain assisted-channel parity rather than copy marketing claims. |

Primary/authoritative sources consulted:

- Uber marketplace pricing, open marketplace and principles: <https://www.uber.com/us/en/marketplace/pricing/>, <https://www.uber.com/us/en/marketplace/open-marketplace/>, <https://www.uber.com/us/en/marketplace/principles/>
- Grab marketplace allocation and overview: <https://www.grab.com/inside-grab/stories/matching-driver-partners-and-riders-allocation/>, <https://www.grab.com/inside-grab/stories/an-overview-of-grabs-marketplace/>
- Grab 2024 ESG report (demand guidance context): <https://assets.grab.com/wp-content/uploads/media/si/reports/2024/Grab-ESG-Report-2024.pdf>
- Bolt driver earnings and offers: <https://bolt.eu/en/driver/earn/>, <https://bolt.eu/en-ua/driver/guide/offers/>
- DiDi corporate/investor information: <https://didiglobal.com/>, <https://ir.didiglobal.com/>
- Yango company, driver and partner material: <https://yango.com/company/>, <https://yango.com/en/driver/>, <https://yango.com/en_cm/driver/partner/>
- RIDE official App Store listing: <https://apps.apple.com/us/app/ride-driver-et/id1375519435>
- Feres official site: <https://feres.et/Home>
- World Bank Ethiopia digital-connectivity evidence: <https://www.worldbank.org/en/results/2025/06/30/empowering-ethiopians-by-laying-the-digital-foundations-for-afe-economic-growth>

Source limitation: Lyft first-party pages available to search did not disclose enough current deterministic marketplace detail for a reliable mechanism comparison. RIDE and Feres publish service capabilities but not their allocation internals. These are recorded gaps, not invitations to infer behavior.

## 3. Recommended architecture

Add a `Marketplace Intelligence` module to the existing modular monolith. It has four boundaries:

```text
Immutable ride/dispatch/driver/ETA context events
                 |
                 v
        Aggregation and quality gate
                 |
                 v
    Deterministic snapshot + rule evaluator
          |             |             |
          v             v             v
   explanations    recommendations   simulation
          |
          v
 Internal operations API / approved metrics export
```

The engine is **advisory except for telemetry quality gates**. It may mark a recommendation `INSUFFICIENT_DATA`, but it cannot assign a driver, alter a quote, activate surge, suspend an account or invent an incentive. Pricing, dispatch, safety, fraud and operations remain separate authorities.

### 3.1 Contracts

- `MarketplaceObservationSource`: bounded reads of aggregated, delayed or pseudonymized facts; no unrestricted personal-history access.
- `MarketplaceRuleSetRepository`: immutable versioned rule sets with effective time, jurisdiction/service zone, author, approval reference and checksum.
- `MarketplaceEvaluator`: pure deterministic evaluation of one canonical snapshot and rule set.
- `DemandSignalProvider`: provider-neutral airport/event/weather/traffic facts with provenance, observed time, expiry and confidence.
- `MarketplaceRecommendationRepository`: immutable recommendation, evidence window, component results, reason codes and lifecycle.
- `MarketplaceSimulationRunner`: replays de-identified event streams against candidate rules without writing operational state.
- `FutureMarketplaceStrategy`: later AI may produce a shadow recommendation through the same output contract; deterministic policy remains fallback and authority until separately approved.

Every input has `observed_at`, `available_at`, freshness, provenance and quality. Every output has decision UUID, generated time, market/zone, rule-set version, input-window reference, component values, reason codes, confidence class and expiry.

## 4. Deterministic modules

All scores use integer basis points `[0, 10_000]`, fixed-point/Decimal intermediate arithmetic, explicit clamping and missing-data states. There are no binary floats in durable results. Numeric thresholds and weights below are structural proposals, not launch values.

### 4.1 Marketplace health

A dashboard index only, never a dispatch objective:

```text
health = weighted_geometric_mean(
  rider_reliability,
  driver_opportunity,
  marketplace_efficiency,
  sustainability_guardrail
)
```

Geometric aggregation prevents one excellent component from hiding a collapsed component. Each component and breach remains visible. A configured hard guardrail forces `UNHEALTHY` regardless of aggregate score.

### 4.2 Driver opportunity and idle-time balancing

Compare only drivers who were verified, online, service-compatible and materially available in the same zone/time cohort. Opportunity includes offered earning-minutes and expected net earnings, not merely trip count. Exclude offline time, self-selected incompatible services and periods with stale location.

The dispatch-facing result is a bounded tie-break adjustment only among candidates whose pickup ETA lies inside the approved material-equivalence band. It can never make a substantially slower pickup outrank the fastest suitable driver. New verified drivers begin at cohort-neutral standing until the configured minimum exposure/completed-trip sample is reached.

### 4.3 Rider satisfaction

Use operational outcomes available before subjective rating: assignment success, pickup wait against communicated range, avoidable cancellation, support contact and ETA calibration. Ratings may be reported separately with sample/confidence warnings; they are not a driver-ranking input because ratings can encode bias.

### 4.4 Driver fairness

Report cohort opportunity distribution, bottom-decile gap, Gini/Theil-style diagnostics, offer-quality parity and reason-code parity. No single fairness statistic is sufficient. Cohorts may include service zone, vehicle/service capability and online window but never protected traits or proxies selected to disadvantage a group. Voluntary self-identification, if ever used for legal fairness auditing, requires a separate privacy/legal design and may not enter dispatch.

### 4.5 Cancellation reduction

Classify cancellation causes before recommending action: rider-caused, driver-caused, platform/communications, pickup ambiguity, ETA miss, external disruption or unknown. Recommendations address the causal category (pickup guidance, ETA buffer, offer window, communications) and never automatically punish a driver from an uncertain cause.

### 4.6 Driver retention signals

Only cohort-level operational warnings: sustained fall in online return rate, rising unpaid idle/deadhead, falling net opportunity/hour, repeated low-quality offers or unresolved support burden. No individual “churn score,” covert targeting or manipulation is authorized. Driver outreach/incentives remain a leadership-approved product/operations decision.

### 4.7 Traffic-impact compensation

Protect driver metrics by comparing actual progress against the route/ETA baseline and signed external signals. Accidents, closures, severe congestion, weather, pickup restrictions and platform routing failures produce an `EXTERNAL_DELAY_PROTECTED` attribution when evidence and confidence thresholds pass. Protected minutes are excluded from reliability/cancellation penalties and surfaced for separately approved compensation review. The engine does not post money.

Disagreement or low confidence resolves in the driver's favor for punitive metrics while flagging manual/aggregate review; it does not create an automatic financial entitlement.

### 4.8 Rule-based demand prediction

Forecast a range per zone and fixed time bucket using transparent seasonal baselines:

```text
baseline = robust median of comparable weekday/time buckets
adjusted range = baseline
  × approved event factor
  × approved weather factor
  × airport schedule/queue factor
```

Each factor is capped, expiring and independently explainable. Sparse or stale inputs widen the range or return `INSUFFICIENT_DATA`; they never fabricate precision. Forecast evaluation uses rolling-origin backtests and reports WAPE/MAE, interval coverage and bias by zone.

### 4.9 Airport demand

Airport is a separate policy context, not a universal priority boost. Inputs may include approved flight-arrival aggregates, queue length, verified airport eligibility, pickup-zone capacity and access constraints. It recommends staffing/queue status. Airport fees, queue priority, premium eligibility and rematch rules require leadership/local operational approval. Flight passenger identity is neither required nor allowed.

### 4.10 Event and weather demand

Events are allowlisted operational records with venue polygon, expected attendance band, ingress/egress windows, confidence and source. Weather uses provider-neutral categorical observations/forecasts with expiry. Emergency or disaster classifications force surge recommendation suppression until leadership-approved emergency policy says otherwise.

### 4.11 Surge recommendation

Output only: `NO_CHANGE`, `SUPPLY_GUIDANCE`, `INCENTIVE_REVIEW`, `PRICE_REVIEW`, `SUPPRESS` or `INSUFFICIENT_DATA`, plus bounded suggested pressure band and reasons. There is no multiplier or automatic price mutation in Mission 15. Any future price action requires the pricing engine, approved caps/floors, emergency restrictions, rider disclosure, driver-earnings treatment and CEO/CTO approval.

## 5. Rule model and explainability

Rules are declarative data, not executable user code. Supported primitives are bounded comparisons, ratios, windows, capped linear transforms, lookup tables and AND/OR composition. No expression evaluation, dynamic imports or SQL fragments.

Rule lifecycle:

```text
DRAFT -> VALIDATED -> SIMULATED -> REVIEWED -> APPROVED -> ACTIVE
                                                |          |
                                                v          v
                                             REJECTED   RETIRED
```

Only an approved signed/checksummed version can be active. Activation uses maker-checker authorization, effective timestamps and an audit/outbox event. Exactly one active rule set exists per market/service/context at an instant. Rollback reactivates a prior immutable version; history is never edited.

Example explanation:

```text
MARKET_HEALTH_DEGRADED
  rider_pickup_p90: breached
  eligible_supply_ratio: below band
  driver_idle_p50: within band
  external_disruption: heavy_rain (fresh, medium confidence)
recommendation: SUPPLY_GUIDANCE
expires_at: ...
```

Public/driver explanations require separate approved copy. Internal raw thresholds, fraud signals and other drivers' information are not exposed.

## 6. Persistence proposal

Additive PostgreSQL tables, subject to later migration approval:

- `marketplace_rule_sets`: immutable version/config/checksum/status/effective range/approval reference;
- `marketplace_snapshot_windows`: zone/time/service aggregates, quality and source watermark;
- `marketplace_decisions`: decision identity, rule version, component results, reasons, confidence and expiry;
- `marketplace_recommendations`: recommendation type, lifecycle, operator outcome and linked decision;
- `marketplace_signal_facts`: bounded airport/event/weather/traffic facts with provenance and expiry;
- `marketplace_simulation_runs`: candidate rule version, dataset manifest/checksum, result summary and status;
- `marketplace_simulation_metrics`: scenario/cohort metric values;
- existing immutable audit/outbox for activation, override and recommendation events.

Partition high-volume snapshots/decisions by observed month only after volume evidence; use bounded zone/time indexes first. Raw GPS traces do not belong in these tables. Retention and aggregation windows require Ethiopian privacy/legal review.

## 7. Processing, consistency and scale

- Produce fixed-window snapshots from durable outbox/domain events with idempotent event IDs and source watermarks.
- Use event time, not arrival time; bounded lateness may revise an unfinalized window. Finalized decisions are immutable and superseded by a linked correction.
- Claim work with existing PostgreSQL transactional patterns. One decision key `(market, zone, service, window, rule_version)` is unique.
- Bound every run by zones/windows/events and expose lag/readiness. Backpressure delays advisory output rather than dispatch.
- Start in PostgreSQL and the modular monolith. Consider a stream/batch platform only when measured event volume, lag or analytical isolation breaches approved SLOs.
- At 10 million users, deterministic pure evaluators remain horizontally parallel by market/zone/window; aggregated facts and append-only decisions permit later extraction without changing contracts.

## 8. Simulation framework

Simulation is offline and read-only against an immutable, de-identified dataset manifest. It supports historical replay, synthetic stress scenarios and counterfactual comparison between a baseline and one candidate rule set.

Required scenarios include normal demand, supply shortage, rain, road closure, airport arrival bank, venue egress, provider outage, stale signals, delayed events, driver cohort entry, concentrated cancellations and adversarial signal spikes.

Outputs compare rider wait percentiles, assignment/no-driver rates, driver idle/deadhead/opportunity distribution, cancellation attribution, sustainability proxy, recommendation churn and computation time. A candidate fails if it improves an aggregate while breaching any safety, fairness, rider-wait or driver-earnings guardrail. Simulation does not prove causality; controlled operational pilots require separate approval.

Proposed pre-implementation performance targets for CTO review:

- pure evaluation p99 below 50 ms for one canonical zone snapshot on CI reference hardware;
- 10,000 snapshot evaluations below 10 seconds with deterministic identical output across repeated runs;
- memory bounded below 256 MiB for the benchmark dataset;
- no unbounded database query and no per-driver loop in marketplace-wide evaluation;
- 100% decision replay equality from snapshot + rule version.

## 9. Security, privacy, fairness and abuse model

- Dedicated `marketplace.read`, `marketplace.simulate`, `marketplace.rules.review`, `marketplace.rules.activate` and `marketplace.recommendations.manage` permissions; deny by default and separate maker/checker roles.
- Authenticate signal ingestion; constrain source, schema, time skew, geography, rate and size. Quarantine conflicting or implausible signals.
- Prevent configuration injection with typed schemas and bounded primitives. Checksum every immutable rule and dataset manifest.
- Never ingest nationality, ethnicity, religion, language, gender, disability, income proxy, neighbourhood wealth or other protected/sensitive traits into operational ranking.
- Precise driver/rider locations remain in their owning domains. Intelligence receives zone/time aggregates or short-lived references needed for traffic attribution.
- Apply minimum cohort sizes and suppress sparse results to reduce re-identification.
- Do not expose individual earnings, opportunity or another participant's reasons through public APIs.
- Audit rule creation/review/activation, simulation, recommendation disposition and authorized override. Logs contain opaque IDs and safe reasons, not coordinates or identities.
- Detect gaming through data-quality anomalies, but do not turn anomaly detection into punishment; fraud/safety modules own reviewed action.

## 10. Configuration governance and operational controls

Every rule parameter declares unit, allowed range, default absence behavior, owner, rationale, metric affected, guardrails, approval reference and revisit trigger. Configuration changes require schema validation, static prohibited-field checks, replay regression, simulation, peer technical review and product/policy approval.

Kill switches exist independently for demand signals, recommendation classes and the entire engine. Stale/unhealthy intelligence degrades to no recommendation; immediate dispatch continues with its approved deterministic policy. There is no dependency from ride creation or offer acceptance to marketplace intelligence availability.

## 11. Alternatives

| Option | Benefits | Costs/risks | Decision |
|---|---|---|---|
| One weighted marketplace score directly controls dispatch and pricing | Simple headline optimization | Hides trade-offs, couples authorities, hard to appeal, unsafe for livelihoods | Reject |
| Deterministic advisory module with explicit guardrails and separate authorities | Explainable, reversible, locally measurable, AI-ready | More visible policy work; requires disciplined configuration | **Recommend** |
| Rules SaaS/remote optimization platform | Faster tooling | Sensitive data/provider lock-in, outage dependency, unclear Ethiopian fit | Reject until measured need and provider review |
| ML/RL marketplace optimizer now | Potential future efficiency | No representative AYO data, opaque trade-offs, drift/bias and operational complexity | Explicitly excluded |
| Manual dashboards only | Lowest build cost | Slow detection, inconsistent reasoning, no replay/simulation contract | Useful fallback, insufficient as the core |

## 12. Required implementation milestones after approval

1. Pure domain contracts, fixed-point score primitives, rule schema and explanation tests.
2. Snapshot aggregation and deterministic modules, initially without production activation.
3. PostgreSQL migration/repositories and immutable rule governance, stopping before migration application outside disposable tests.
4. Simulation/replay framework and performance/fairness test corpus.
5. Internal authenticated read/simulation APIs, observability and controlled local activation.
6. Shadow-only staging evaluation against synthetic/de-identified data.

Each milestone runs formatting, lint, strict type checks, unit/integration/concurrency/security tests, coverage and benchmarks, then stops at the applicable gate. No marketplace rule should affect live dispatch or pricing during Mission 15 without a new explicit approval.

## 13. Leadership decisions required

- Approve the advisory-only boundary and separation from dispatch/pricing authority.
- Approve which driver opportunity/earnings metrics may be used and the material-equivalence principle.
- Approve airport queue/service policy ownership; actual queue priority remains unresolved.
- Approve event/weather/emergency suppression policy owners.
- Approve whether any future recommendation may trigger a human-approved incentive or pricing review; no values are proposed.
- Assign Ethiopian legal/operational review for location aggregation, earnings analytics, retention, worker fairness and airport/event operations.
- Approve proposed benchmark/SLO targets or request revision.

## 14. Architecture evaluation

The design has a credible 10-million-user partitioning path, survives signal/provider outage by returning no recommendation, is deterministic and replayable, is deny-by-default, supports metrics/lag/kill switches, uses additive versioned records, can be extracted behind stable contracts, improves rider/driver decisions without blocking rides, and remains simpler than AI, microservices or a streaming platform. Accepted limitation: PostgreSQL analytics may eventually need extraction; revisit only when measured lag, load isolation or retention cost breaches approved thresholds.

## 15. Approval gate

CTO review is requested for boundaries, deterministic arithmetic, persistence, scale, security, simulation and benchmark targets. After CTO review, CEO approval is requested for marketplace trade-offs, fairness/earnings principles, recommendation authority, airport/event/weather policy ownership and roadmap sequencing.

The CTO and CEO approved this architecture and authorized implementation. No AI ranking, automatic pricing, payment, deployment, production provider or real customer data was authorized.

## 16. Implementation result

Mission 15 implements the approved deterministic advisory boundary in `BACKEND/marketplace`:

- immutable validated rule sets with configurable score, demand, fairness, delay and recommendation parameters;
- rider reliability, driver fairness, marketplace efficiency, business sustainability and weighted-geometric marketplace health components;
- materially equivalent-pickup opportunity and idle-time credits with neutral new-driver standing;
- causal cancellation attribution and external traffic/weather/event/platform delay protection;
- freshness/confidence-aware airport, event, weather and traffic demand factors with capped ranges;
- recommendation-only supply, incentive/price review and emergency suppression states; no fare or dispatch mutation exists;
- deterministic replay simulation with baseline/candidate comparison and benchmark evidence;
- a stable `MarketplaceStrategy` protocol for a future shadow strategy while deterministic dispatch remains authoritative;
- failure-isolated application orchestration: any intelligence exception returns no recommendation and cannot block ride creation or dispatch;
- structured privacy-safe logs plus recommendation, failure, health, component and forecast metrics;
- PostgreSQL immutable rule, decision/explanation and simulation records with unique retry keys and least-privilege runtime grants.

Migration `20260716_0010` is additive and reversible. It creates `marketplace_rule_sets`, `marketplace_decisions` and `marketplace_simulation_runs`; downgrade removes them in dependency order. No production migration was run.

The runtime contains no router, scheduler or dispatch call to this module. Controlled activation and operational rule values require a future approval. The current configuration defaults are testable structural defaults, not approved Ethiopian commercial policy.
