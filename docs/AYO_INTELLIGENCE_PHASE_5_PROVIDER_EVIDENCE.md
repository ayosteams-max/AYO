# AYO Intelligence Phase 5 provider evidence

**Status:** PRE-PRODUCTION offline governance evidence only

**Reviewed:** 2026-08-10

**Re-review by:** 2026-09-09

**Native Amharic status:** `NEEDS_NATIVE_AMHARIC_REVIEW`

## Problem and success threshold

AYO needs to compare changing external text-provider policies and measured behavior without selecting a vendor by brand, changing Phases 1–4, or turning evaluation into activation. Merchant operations, security reviewers, and leadership benefit when an eventual provider decision has auditable evidence.

Phase 5 succeeds when the repository can reject missing, unknown, stale, account-inapplicable, unsafe, unreliable, non-exact, or unreviewed evidence across the fixed 20-scenario corpus. It does not succeed by recommending or activating a provider. A documentation-only matrix was too weak to enforce these rules; live adapters and a generic router were broader than the current problem. The approved solution is a typed offline evaluator plus this version-controlled evidence record.

## Current official-policy observations

These are general policy observations, not proof of AYO account eligibility. They remain `UNKNOWN` for admission until the exact product, model/version, account tier, configuration, region, contractual terms, and current official evidence are verified. Privacy/training use, retention/abuse-monitoring storage, zero-retention eligibility, and processing location are separate gates.

| Provider | Category | Applicable product/tier | Official source | Conclusion for AYO | Uncertainty |
|---|---|---|---|---|---|
| OpenAI | Training/data use and retention controls | API platform; endpoint and organization/project controls vary | [API data controls](https://developers.openai.com/api/docs/guides/your-data#default-usage-policies-by-endpoint) | UNKNOWN | General API policy does not prove AYO account configuration, endpoint eligibility, retention control, or region. |
| Anthropic | Retention | Commercial API; applicable agreement/account | [Commercial data retention](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data) | UNKNOWN | Published defaults do not establish AYO terms or configuration. |
| Anthropic | Zero-data-retention eligibility | Eligible API products and approved arrangements only | [Zero data retention scope](https://privacy.claude.com/en/articles/8956058-i-have-a-zero-data-retention-agreement-with-anthropic-what-products-does-it-apply-to) | CONDITIONALLY AVAILABLE | Availability to some customers is not evidence that AYO has an approved arrangement. |
| Google | Retention | Gemini Enterprise agent platform; feature/account scope varies | [Zero data retention](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/zero-data-retention) | UNKNOWN | Product-specific statements do not establish the future AYO API product, account, region, or configuration. |
| Google | Cost | Gemini API model-specific public pricing | [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) | COMPARATIVE ONLY | No exact model/version, billing tier, traffic profile, or Founder-approved AYO budget exists. |

No candidate is recommended, admitted, activated, or production-approved. No live call or credential check was performed. Current evidence is intentionally incomplete and cannot pass the account-verified hard gates.

## Evaluation and admission rules

- The fixed `merchant_ack_corpus_v1` contains the ten currently provider-callable merchant ACK reasons in English and Amharic: exactly 20 synthetic scenarios derived from the locked server language contract.
- The corpus contains no real merchant, customer, order, Pickup, identifier, address, location, payment, credential, or operational private data. Arbitrary user prose is not an evaluator input.
- Mandatory policy gates are privacy, training/data use, retention, regional/data location, and security/compliance. Evidence must identify provider, exact model, product, plan/tier, official source, review date, validity date, conclusion, applicability, and uncertainty.
- General availability is not AYO eligibility. Only explicitly verified AYO-account evidence can pass a policy gate.
- Technical hard gates include server-only use, no mobile secret, no client prose, structured output, an exact pinned model version, two-second p95 latency, reliability, exact preservation, locale adherence, tools disabled, stateless operation, provider-neutral edge integration, no automatic retry/failover, and production disabled.
- Native Amharic approval requires dated, named human review for every Amharic scenario. Machine results cannot create that evidence.
- Median/p95/p99 latency, success/failure rates, exactness, locale adherence, documented rate limits, lifecycle risk, and token-cost projections are comparative metrics only. They never override a hard-gate failure. No AYO cost ceiling has been invented.
- `EVALUATED`, `ADMISSION_RECOMMENDED`, `FOUNDER_APPROVED`, and `ELIGIBLE_FOR_PREPRODUCTION_ACTIVATION` remain separate manual records. Eligibility is not activation, and activation is not production approval.

## Risk and edge-case register

| Risk | Deterministic control / verification |
|---|---|
| Stale policy, pricing, or model facts | Every evidence item has review and validity dates; stale mandatory evidence fails. Re-review is manual, never background monitoring. |
| Incomplete or malformed evidence | Strict immutable schemas reject extra/missing fields; missing/unknown mandatory evidence cannot qualify. |
| Candidate collision or overwrite | Provider and exact model identity must match across profile, policy, observations, and human review; duplicates reject. |
| Availability mistaken for AYO eligibility | General policy evidence yields `UNKNOWN`; AYO-account verification is a distinct applicability state. |
| False Amharic certification | All ten Amharic scenarios require a named, dated, fully approved human review; none is generated automatically. |
| A magic score masks a failure | Every mandatory requirement is an explicit gate; comparative metrics cannot override it. |
| Evaluation becomes activation | Evaluation returns only an evaluated report. Later lifecycle states require separate manual governance records and explicit Founder evidence; Phase 5 forbids production approval. |
| Alias drift, deprecation, unsupported tier/region | Exact model IDs are part of every evidence identity; version pinning and current lifecycle/region/account evidence are hard gates. |
| PII or arbitrary prose enters the corpus | Corpus is code-built from locked semantic keys and canonical text; strict models reject arbitrary prompt fields and unknown scenarios. |
| Accidental network, credential, tool, command, or retry | The evaluator accepts recorded observations, not a provider callback; it has no transport, credential, command, tool, retry, failover, memory, or RAG interface. Source and tests verify the boundary. |

## Revisit threshold

Controlled live synthetic evaluation requires separate Founder/CEO authorization after CTO review. Provider recommendation can be considered only after exact account/product/model evidence is current, all offline and later authorized live measurements pass hard gates, native Amharic review is complete, and leadership has approved any cost threshold. Activation and production remain separately gated.
