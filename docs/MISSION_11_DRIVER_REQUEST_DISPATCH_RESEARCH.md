# Mission 11 — Rider Request and Dispatch Foundation Research

Status: **Research and architecture approved by CTO and CEO on 2026-07-15; bounded Mission 12 immediate-dispatch implementation authorized.**
Date: 2026-07-15
Workflow coverage: Steps 1–2 only.

## 1. Exact problem

After choosing a destination and ride type, a rider needs one reliable action that creates exactly one authoritative ride request and clearly communicates that AYO is searching. The current button only opens an alert. The current mobile values are presentation-only strings, and the current backend request/dispatch path is an unauthenticated synchronous prototype; connecting them directly would make identity, fare, ETA and retry behavior unsafe.

Beneficiaries are riders who need confidence and recovery under weak connectivity, drivers who need fair and non-duplicated offers, and operations who need traceable request/dispatch outcomes.

Proposed measurable outcomes, subject to approval and launch-area baselining:

- Duplicate taps or network retries create exactly one ride.
- Every accepted request has a server-generated UUID, UTC acceptance timestamp, version and idempotency record.
- The UI never displays a locally invented fare, assignment, safety guarantee or search estimate as authoritative.
- A killed/restarted or temporarily offline client can recover the authoritative ride state.
- Search-request API latency, time-to-first-offer, time-to-assignment, no-driver rate, cancellation rate and pickup ETA error are measured before optimization.
- Accessibility labels, reduced-motion behavior, Amharic/English layouts and the approved low-end Android/network matrix pass before launch.

The simpler solution is a deterministic, server-authoritative request and dispatch contract with a premium state-driven screen. AI is not needed to solve the first version of this problem.

## 2. Current repository facts

- `AYO-Mobile/app/(tabs)/index.tsx` displays hard-coded fare and driver-arrival strings and passes only a destination display name through navigation state. Pickup is the literal text `Your current location`; neither location is a verified server reference.
- The Request button calls an alert and creates no request.
- The backend `POST /api/rides/` accepts caller-supplied `rider_name`, pickup/destination strings and pickup coordinates, uses an eight-character UUID fragment, and has no idempotency key or authenticated actor context.
- The backend immediately reads a process-local driver list, ranks by straight-line distance with a rating tie-break, writes private queue/offer data on the ride aggregate, and normally returns `WAITING_FOR_DRIVER`. This is prototype behavior, not the approved Mission 6/8 lifecycle.
- In-memory repositories are the application default. PostgreSQL seams exist, but the production ride lifecycle, authenticated request endpoint, durable idempotency, quote authority, provider routing, verified-driver operations and reliable dispatch workers are not implemented.
- The existing database ride fields use floats for fare/distance and expose legacy compatibility shapes. They do not satisfy the approved money or public-contract rules.
- The roadmap assigns canonical request/idempotency to Mission 6, maps/ETA to Mission 7, immediate dispatch to Mission 8, authoritative quote/fare to Mission 9, and launch apps to Mission 11. Roadmap Mission 11 depends on Missions 4–10.
- The two untracked files under `AYO-Mobile/.claude/` and `AYO-Mobile/CLAUDE.md` are pre-existing local files and are outside this proposal.

## 3. External evidence

- Uber describes matching as a real-time marketplace concern and says real-world ETA—not simple proximity—must account for traffic and geographic barriers. It also documents batched matching as a later optimization across riders and drivers, not a reason to skip a reliable baseline: <https://www.uber.com/jm/en/marketplace/matching/>.
- Uber's marketplace principles emphasize reliability, aligning rider and driver needs, and transparency about pricing and matching: <https://www.uber.com/us/en/marketplace/principles/>.
- Uber's published rider-session work models request and dispatch events as explicit trip state, supporting AYO's existing state-machine rule: <https://www.uber.com/en-GB/blog/sessionizing-data/>.
- Grab describes allocation as serving riders quickly while protecting driver livelihood, reinforcing two-sided success measures rather than rider wait time alone: <https://engineering.grab.com/understanding-supply-demand-ride-hailing-data>.
- GSMA's 2025 LMIC research reports daily mobile-internet use among surveyed Ethiopian mobile-internet users as low as 55%, while its overview identifies rural connectivity experience as a leading Ethiopian adoption barrier. The Ethiopia sample excluded conflict-affected areas representing 27% of the population, so the figures are directional rather than fully national: <https://www.gsma.com/somic/wp-content/uploads/2025/09/The-State-of-Mobile-Internet-Connectivity-2025-Understanding-Mobile-Internet-Use-in-LMICs.pdf> and <https://www.gsma.com/somic/wp-content/uploads/2025/09/The-State-of-Mobile-Internet-Connectivity-2025-Trends-in-Mobile-Internet-Connectivity.pdf>.

Competitor behavior is evidence, not AYO policy. No source verifies AYO's launch-area supply, acceptable search time, cancellation behavior or Ethiopian dispatch rules; those require measurement and leadership/local operational review.

## 4. Options

| Option | Customer experience | Reliability and scale | Safety/security | Cost and maintenance | Ethiopian fit | Recommendation |
|---|---|---|---|---|---|---|
| A. Create the full ride object locally and navigate immediately | Fast demo; appears responsive | Duplicate/lost rides after retries or process death; no multi-worker authority | Client invents ID, time, fare and ETA; deceptive searching state | Lowest build cost, highest later rewrite | Superficially works offline but cannot honestly request a ride | Reject |
| B. Call the existing `/api/rides/` prototype behind a mobile gateway | Demonstrates a round trip | Process-local drivers/state, truncated IDs, no idempotency, synchronous dispatch and legacy schema | Caller controls identity/location; private dispatch fields and float money remain unsafe | Moderate now; entrenches prototype debt | Weak-network retries can duplicate requests | Reject |
| C. Add an authenticated, idempotent server request command and a provider-neutral dispatch strategy boundary; mobile renders authoritative state | Honest pending/search/recovery states; slightly more prerequisite work | Durable state, bounded work, horizontal path and recoverable clients | Server owns identity, UUID, timestamp, quote/fare, state and authorization | Higher initial work but smallest safe long-term path; no new service required | Supports retries, polling fallback and low-data UI | **Recommend** |
| D. Implement ML/AI scoring now | No proven rider benefit over baseline | Needs training/evaluation/feature infrastructure and safe fallback | Bias, explainability, drift and livelihood risks are unmeasured | Highest cost and lock-in risk | No representative AYO dispatch data exists | Reject now; retain future plug-in boundary |

## 5. Recommendation

Approve Option C as the direction for later architecture design, with **AI-ready, deterministic-first** semantics:

1. The client submits a command containing stable pickup/destination references, requested ride type, server quote ID and a cryptographically strong idempotency key. It does not create the authoritative ride object.
2. The authenticated server returns the ride UUID, server acceptance time, authoritative location snapshots/references, ride type, quote/fare in integer minor units with currency and quote version, ETA/search fields with provenance/freshness, lifecycle status and resource version.
3. A dispatch strategy port receives a bounded eligible candidate set. The approved initial strategy remains deterministic and explainable. A future AI implementation may plug into the port only after offline evaluation, shadow mode, fairness/safety review, versioned reason evidence, monitored rollout and deterministic fallback.
4. The mobile application uses a `RideRequestGateway` and explicit request state (`idle`, `submitting`, `searching`, `assigned`, `no_driver`, `failed`, `offline_pending` where policy permits). The searching screen renders only server-authoritative ride state and survives restart/retry.
5. Keep the modular monolith. Do not add Redis, a broker, ML platform or microservice until measured load/reliability evidence and the applicable approval gate justify it.

The requested object fields are retained, but authority must be corrected:

| Requested field | Proposed authority |
|---|---|
| pickup | Server-validated location reference and immutable request snapshot |
| destination | Server-validated destination reference and immutable request snapshot |
| ride type | Client choice validated against server catalog/policy |
| estimated fare | Server quote in minor units; client display only |
| ETA | Server/provider result with kind, freshness and confidence/range; meaning requires approval |
| timestamp | Server UTC acceptance time |
| unique ride ID | Server-generated UUID; never an eight-character fragment |

## 6. Proposed user journey and conceptual wireframe for review

```text
Home
  -> validated destination + selected ride + current server quote
  -> tap Request once
  -> button shows submitting and rejects duplicate taps
  -> server accepts idempotently
  -> Searching for Driver
       [reduced-motion-safe searching indicator]
       Finding your best driver…  (copy requires approval)
       [honest server search estimate or non-numeric fallback]
       [approved, supportable safety message]
       [explicit offline/delayed/no-driver recovery state]
  -> authoritative assignment replaces searching state
```

The design should reuse the current navy/cyan/green theme, large touch targets and one-primary-action rule. Animation must respect reduced-motion settings and avoid continuous high-cost rendering on low-end devices. Exact wireframes, motion specification and screen architecture belong to Workflow Step 4 after approval.

## 7. Risks and unresolved decisions

- **Roadmap sequencing:** The requested name combines Roadmap Mission 11 UI with Mission 6 request lifecycle, Mission 8 dispatch and Mission 9 quote authority. Building it now would start dependent work early unless leadership explicitly re-scopes the roadmap and accepts a vertical-slice order.
- **Identity:** The current mobile app has no authenticated rider context. Caller-supplied identity is prohibited.
- **Locations:** The current display-name-only destination and placeholder pickup are insufficient for a serviceable ride.
- **Fare:** `ETB 180` and other current values are unapproved presentation placeholders and cannot enter a ride request as authoritative values.
- **ETA ambiguity:** Leadership must define whether the requested ETA means driver pickup ETA, trip ETA or search-to-match estimate. A search-time number needs measured launch-area calibration and honest degradation behavior.
- **Safety copy:** Wording cannot promise verified drivers, monitoring, response or protection that operations and technology do not yet deliver. CEO/CTO and qualified local operational review must approve supportable wording.
- **Cancellation/no-driver policy:** Searching-screen cancellation, timeout and no-supply behavior affect riders and drivers and require leadership approval.
- **AI governance:** Driver ranking affects livelihood and safety. Inputs, prohibited characteristics, fairness metrics, reason codes, human review/appeal, fallback and rollout thresholds require explicit approval before AI use.
- **Weak connectivity:** Retry, process death, stale state and delayed assignment must not create duplicate rides or show false status.
- **Privacy:** Precise pickup/destination and driver locations require purpose limitation, minimized responses, retention rules and Ethiopian legal review before launch.

## 8. Approval record

The CTO approved the recommendation, dependency/sequence assessment, server-authoritative field ownership, deterministic-first dispatch boundary, idempotency/recovery requirements and rejection of direct prototype integration on 2026-07-15.

The CEO approved the architecture and roadmap resequencing on 2026-07-15. AP-025 bounds Mission 12 to immediate dispatch and excludes scheduled rides and pre-dispatch.

The separate implementation authorization is recorded in AP-025. Production persistence and authenticated API activation remain later gates.

## 9. Mission evidence checklist

| Step | Evidence | Status |
|---|---|---|
| 1 | Repository, competitor and Ethiopia research above | Complete |
| 2 | Options, recommendation, journey, success measures and risks above | Complete |
| 3 | CTO architecture approval and subsequent CEO confirmation | Complete 2026-07-15 |
| 4 | Architecture/API/wireframes/state/security/database design | Approved in `docs/AYO_DISPATCH_ARCHITECTURE_PROPOSAL.md` |
| 5 | Risks and edge cases | Approved for bounded Mission 12 scope |
| 6–10 | Implementation through completion report | Mission 12 authorized; in progress |
