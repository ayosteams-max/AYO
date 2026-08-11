# AYO Intelligence Phase 9 deterministic-first Merchant ACK architecture

**Status:** CTO approved and Founder/CEO approved; documentation-only governance candidate awaiting review and merge authorization

**Decision date:** 2026-08-11

**Scope:** Merchant ACK intelligence only; architecture and governance documentation, with no source or runtime implementation

## Problem and evidence basis

Merchant ACK needs reliable, localized guidance derived from trusted capability and
state evidence. Phases 6–8 tested whether live generative inference could reproduce the
already bounded Phase 2 wording inside the locked two-second screen:

| Candidate | Responses | Reliability, exactness and locale | p95 latency |
|---|---:|---:|---:|
| Phase 6 OpenAI mini | 18/20 | 90% | 2,054 ms |
| Phase 7 OpenAI nano | 18/20 | 90% | 2,073 ms |
| Phase 8 Anthropic Haiku | 13/20 | 65% | 2,057 ms |

All returned responses preserved the canonical content and locale. Across the three
screens, timeout and latency—not malformed output, semantic rewriting, locale corruption
or provider HTTP errors—were the dominant observed failure. Phase 9 research also found
that the historical transports created a fresh HTTPS connection for every scenario and
combined payload construction, DNS/TCP/TLS, request/response transfer and provider work
into one client-observed duration. First-request schema or cold effects may contribute but
cannot explain all failures.

The evidence does not establish universal provider or model performance. It establishes
that none of the three exact candidates met AYO's locked screen and that no demonstrated
Merchant ACK benefit justifies a live model dependency.

## Approved synchronous path

The permanent required Merchant ACK intelligence path is:

```text
Trusted Merchant ACK capability/state
    -> validate current authority evidence
    -> Phase 1 deterministic recommendation
    -> Phase 2 deterministic localized language
    -> immediate merchant presentation
```

No live provider call, external model, provider network, provider queue, provider retry,
provider failover or model availability belongs in this chain.

### Phase 1 — deterministic decision layer

Phase 1 remains unchanged. It may interpret trusted capability/state evidence and derive
the bounded recommendation and user actionability. It cannot create authority, mutate
state, dispatch commands, acknowledge automatically, retry automatically, reconcile
automatically or fabricate availability.

### Phase 2 — deterministic explanation layer

Phase 2 remains unchanged. It owns the centralized English/Amharic headline, body and
approved action-label semantics and maps the Phase 1 result deterministically. It cannot
change the Phase 1 decision, become command authority, depend on an external model or
fabricate state.

## Generative decision — remove from this use case's product path

Generative inference will not be activated for Merchant ACK, synchronously or
asynchronously. Merchant ACK has a closed, bounded state/reason set, and Phase 2 already
supplies the complete localized wording. The evaluated models reproduced that wording
while adding latency, availability, privacy, cost and operational dependencies. No
measurable incremental user value has been demonstrated.

This decision does not delete or invalidate Phase 3–8 research code, controlled runners,
artifacts or governance records. Those remain historical engineering evidence and may
inform separately justified future domains.

## Authority and fail-closed boundary

> Intelligence may interpret authority.
> Intelligence may explain authority.
> Intelligence may never create authority.

Merchant ACK command authority remains exclusively in the trusted capability,
controller and backend domains. Contradictory, stale, missing, malformed, unsupported or
incoherent evidence continues to fail closed. No optimistic inference, automatic command,
acknowledgement, retry or reconciliation is permitted.

## Historical evaluation tooling boundary

Phase 6/7/8 controlled-evaluation runners remain engineering-only, inactive,
synthetic-corpus-governed research tooling disconnected from product runtime. They must
not become a generic provider router, provider marketplace, automatic model selector,
retry engine, failover engine or runtime provider infrastructure.

Historical Phase 6/7/8 results remain fresh-connection experiments and must not be
reinterpreted as persistent-connection measurements. Any separately authorized future
diagnostic must explicitly distinguish fresh connections from persistent or pooled
connections.

## Localization

English and Amharic remain centralized in Phase 2. Human Amharic status remains
`UNKNOWN`; `NEEDS_NATIVE_AMHARIC_REVIEW` is still required. This architecture makes no
native-language certification claim.

## Performance and UX budget

The required path has no external generative-network dependency. The historical product
requirement remains at most 2,000 ms for the complete merchant-visible outcome, including
app/network, backend authorization and validation, deterministic intelligence and
rendering. This decision does not invent internal deterministic thresholds; those require
representative measurement.

The Phase 9 provider p95 signal around 1,000 ms remains a non-binding research target
only. It is not a gate, SLO, admission criterion or production target. Any future use
requires CTO approval, representative server geography and African/Ethiopian evidence.

## Future diagnostic boundary

A separately authorized diagnostic transport may decompose sanitized timing into:

```text
payload
  -> DNS
  -> connect
  -> TLS
  -> request write
  -> provider wait / TTFT where observable
  -> provider completion
  -> body download
  -> parse and validate
  -> total client-observed time
```

It must distinguish the unchanged product threshold from diagnostic observation:

```text
product_success = required-path latency <= 2,000 ms
diagnostic_observation = actual bounded measurement
```

A future diagnostic observation ceiling may exceed 2,000 ms solely to measure how late a
failure was. A request above 2,000 ms remains a product failure. No numeric diagnostic
ceiling is approved here. No hidden warm-up, automatic retry, automatic failover,
slow-request exclusion or historical-gate change is permitted.

## Geographic qualification

Australian/Melbourne-path evidence must not be extrapolated to Addis Ababa. Future
provider qualification requires representative AYO server geography, privacy-safe coarse
network labels, African-region testing, eventual Ethio Telecom and Safaricom Ethiopia
field evidence, cold/warm comparison and time-of-day analysis. No cloud or inference
region is selected by this decision.

## Security and privacy

Future diagnostics may retain only allowlisted synthetic evidence such as coarse test
geography, phase durations, outcome, token counts and governed configuration identity.
They must exclude credentials, authorization headers, personal IP addresses, raw provider
responses, real product/user data, precise location and request IDs unless request-ID use
is separately justified and governed.

## Future provider governance

Any future provider work requires all of the following before execution or activation:

1. a demonstrated customer problem not already solved deterministically;
2. measurable incremental user value;
3. research and credible alternatives;
4. a sanitized diagnostic architecture;
5. CTO review and Founder/CEO approval;
6. synthetic-only execution authorization;
7. account, privacy, retention, region and security evidence;
8. native-language review where applicable;
9. explicit performance and geography criteria; and
10. separate evaluation, recommendation, admission, activation and production gates.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Deterministic wording drifts when capability semantics evolve | Exhaustive, versioned mappings and review with every semantic change |
| English and Amharic copies diverge | Exact-equivalence and exhaustive mapping tests |
| Native Amharic quality remains unverified | Preserve `NEEDS_NATIVE_AMHARIC_REVIEW`; require qualified review before launch |
| Research runners are repurposed as runtime infrastructure | Explicit inactive composition and governance boundary |
| Generative text is revived and creates UI churn | Require a new user-value case, architecture review and approval |
| Weak instrumentation hides mobile/network latency | Measure complete merchant-visible end-to-end UX in representative conditions |

## Alternatives rejected

1. **Synchronous generation:** rejected because it failed reliability and duplicates
   deterministic content.
2. **Deterministic guidance plus asynchronous Merchant ACK generation:** rejected for now
   because no incremental user value is demonstrated.
3. **Pre-generated provider cache:** rejected because it adds provenance and staleness
   complexity while duplicating Phase 2.
4. **Generic AI router or automatic failover:** rejected as unnecessary, unsafe and
   outside the bounded authority model.
5. **Local or regional inference now:** rejected as unjustified infrastructure for a
   problem already solved deterministically.
6. **Delete Phase 3–8 history:** rejected because it would erase valid research and
   governance evidence.

## Implementation and activation status

Current evidence indicates no Merchant ACK source or runtime implementation is required
after this architecture decision. Phase 1 and Phase 2 remain unchanged, and generative
provider code remains inactive and outside product runtime.

After this architecture governance record is reviewed, merged and post-merge locked,
leadership may reassess whether any implementation mission exists. No implementation
mission may be manufactured merely to continue the phase. This decision authorizes no
source, test, runtime, provider, diagnostic, activation or Phase 10 work.
