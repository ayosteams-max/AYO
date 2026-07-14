# AYO Compute Strategy — Tiered Secure Computing

Status: tier strategy and modular-monolith topology approved; cloud provider selection remains provisional  
Research date: 2026-07-14  
Architectural clarification approved: 2026-07-15  
Deployment status: no infrastructure authorized or deployed  
Authority: `AYO_CONSTITUTION.md` and `AYO_ENGINEERING_WORKFLOW.md`

## 1. Approval status and remaining decision

The CTO and CEO approved the modular-monolith topology, provider-neutral/cloud-portable rules and risk-based use of confidential computing on 2026-07-15. This approval does not select or authorize a cloud provider.

AWS Cape Town remains a provisional recommendation. CTO review and CEO approval are still required after Ethiopian network measurements, actual provider pricing, exact regional-service verification and applicable legal/operational review. No infrastructure deployment, production data placement, regulated financial activity or provider contract is authorized.

## 2. Problem, beneficiaries and success

### Problem

AYO needs a compute foundation that can launch economically, protect mobility and financial data, operate across weak Ethiopian networks, and scale toward 10 million users. Applying maximum-cost confidential computing everywhere would increase expense and operational risk without proportionate customer benefit; applying only ordinary cloud controls everywhere would under-protect the most sensitive future workloads.

### Who benefits

- Riders benefit from a reliable, low-friction service and protected identity/location data.
- Drivers benefit from reliable dispatch, protected documents and auditable earnings.
- Safety, fraud, support and finance staff benefit from controlled, logged access.
- AYO leadership benefits from bounded cost, operational simplicity and a credible security/scaling path.

### Proposed success measures

Exact targets require CTO/CEO approval after launch-area measurement. The evaluation should include:

- Rider/driver API latency on Ethio Telecom and Safaricom Ethiopia under normal and degraded networks.
- Availability and recovery objectives demonstrated by failure and restore tests.
- Zero unaudited financial postings and zero unapproved Tier 2/3 data access.
- Successful secret/key rotation, backup restoration and provider-outage exercises.
- Cost per completed ride and provider-service cost variance within an approved budget.
- Ability to scale each module/workload independently without re-platforming the complete system.

## 3. Research limits and verification required

This comparison uses current official provider material. Service availability and pricing change frequently. No hyperscaler currently has a general public cloud region in Ethiopia; the African regions evaluated are in South Africa. Geography alone does not determine latency because Ethiopian carrier routing and peering matter.

Before selection, AYO must:

1. Measure latency, packet loss and route stability from approved Ethiopian mobile networks to each finalist region.
2. Confirm every required service/SKU is available in the exact region and account.
3. Obtain workload-based provider quotes, startup credits, support terms and data-egress estimates.
4. Complete Ethiopian data-location, cross-border transfer, payment, identity and regulated-workload legal review.
5. Validate provider contractual/compliance evidence; a provider certification does not itself make AYO compliant.

## 4. Principle: Tiered Secure Computing

AYO assigns each workload and dataset to the minimum tier that adequately protects its risk. Higher tiers add isolation, approvals, attestations and cost. Confidential computing is not the default for ordinary workloads.

Tiering supplements—not replaces—least privilege, encryption, secure development, auditing, backups and incident response.

### Tier 1 — Standard secure workloads

**Examples:** public API, notifications, ordinary ride orchestration, public map assets, non-sensitive workers and privacy-minimized operational metrics.

**Required controls:** managed compute, private service networking where appropriate, workload identity, TLS, provider-managed encryption at rest, least privilege, secret injection, multi-zone design, rate limits, logs/metrics, patched immutable artifacts and tested backups.

**Compute posture:** cost-efficient managed containers/serverless compute or autoscaled VMs. Scale to zero or low minimum capacity where safe. No TEE is required solely because a workload is production-facing.

**Promotion triggers:** the workload begins processing Tier 2/3 data directly, the threat model requires protection from privileged infrastructure access, or verified regulation/contract demands stronger isolation.

### Tier 2 — Highly sensitive workloads

**Examples:** identity documents, precise-location access, payment-provider secrets, fraud review, safety cases, support evidence and privileged ledger/reconciliation operations.

**Required controls:** dedicated service identity and data store/bucket boundary, private endpoints, customer-managed encryption keys where justified, field/application encryption for selected fields, time-bound privileged access, dual approval for high-risk actions, immutable audit events, restrictive egress, stronger monitoring, shorter retention and tested access revocation.

**Compute posture:** separate isolated workloads/accounts/projects or strong cloud tenancy boundaries on ordinary hardened compute first. HSM-backed keys and managed secrets are used; a TEE may be added only after threat/cost analysis.

**Promotion triggers:** data must remain inaccessible to host/cloud administrators during processing, attestation-gated key release is required, a high-impact multi-party trust problem exists, or law/provider contract requires data-in-use protection.

### Tier 3 — Confidential computing workloads

**Examples:** attestation-gated cryptographic key release, selected sensitive AI inference, high-risk payment or identity processing, privacy-preserving multi-party analytics, and future regulated AYO Pay operations if legally approved.

**Required controls:** a hardware-backed TEE/enclave, measured and signed workload artifact, remote attestation, policy-bound secret/key release, minimal trusted code base, disabled debug paths, encrypted inputs/outputs, strict egress broker, reproducible builds, side-channel/threat analysis, attestation/audit evidence and deterministic secure failure when attestation fails.

**Compute posture:** isolated enclave/confidential VM/container or confidential GPU selected for the exact use case. Tier 3 must not contain an entire monolith merely for convenience.

**Entry rule:** CTO security/architecture review and CEO approval are required. The proposal must show the threat that Tier 2 cannot adequately address, customer/regulatory benefit, benchmarked performance/cost and an operational recovery plan.

**Exit/fallback rule:** failure of attestation or key release fails closed for cryptographic/high-risk processing. Customer-facing flows must have an approved safe fallback, such as delayed manual review—not silent downgrade to Tier 2.

## 5. Provider comparison

Ratings are qualitative research findings, not procurement scores. “Africa availability” means public cloud infrastructure in South Africa, not Ethiopia. Exact regional product availability must be rechecked during design.

| Criterion | AWS | Microsoft Azure | Google Cloud | Oracle Cloud Infrastructure |
|---|---|---|---|---|
| African region | Cape Town (`af-south-1`), three AZs | South Africa North (Johannesburg) with zones; South Africa West (Cape Town) is paired/restricted for some scenarios | Johannesburg (`africa-south1`), three zones | Johannesburg; broad OCI region footprint also includes other Middle East/Africa locations |
| Security baseline | Mature IAM, organizations, KMS, CloudHSM, Secrets Manager, S3 controls, CloudTrail and broad managed-service portfolio | Strong Entra/RBAC, Policy, Key Vault/Managed HSM, Defender and enterprise governance integration | Strong IAM, organization policy, Cloud KMS/HSM, regional Secret Manager, VPC Service Controls and security analytics | Strong compartments/IAM, Vault/HSM, security zones and comparatively simple network model |
| Confidential capability | Nitro Enclaves: constrained isolated VM with attestation/KMS integration; supported in Cape Town and all current AWS regions per current docs | Broad confidential VM/container/attestation portfolio; secure key release and confidential GPU options, but exact South Africa SKU availability must be proven | Confidential VMs/Space/GKE and H100 GPU capabilities; exact Johannesburg machine/GPU/attestation availability must be proven | AMD SEV/SEV-SNP confidential VM/bare-metal options; newer remote attestation uses customer-operated attestation, and shape/region availability varies |
| Managed PostgreSQL | RDS PostgreSQL, encryption/KMS, automated backups and Multi-AZ patterns | PostgreSQL Flexible Server, encryption including CMK/Managed HSM and backup options | Cloud SQL PostgreSQL, automated backup/failover/encryption and CMEK | OCI Database with PostgreSQL, automated and cross-region-copyable backups |
| Operational simplicity | High if AYO uses a small managed subset; service breadth can create complexity | Strong for Microsoft-skilled teams; identity/governance integration is coherent but product matrix is large | Strong managed/serverless developer experience and clear AI/data integration | Often straightforward and price-predictable; smaller local talent/ecosystem may increase support risk |
| Cost posture | Competitive with Graviton/serverless/reservations; NAT, logs and egress can surprise | Competitive with commitments; licensing/monitoring/networking and premium security services need careful modelling | Competitive serverless/data/AI options; network egress and managed data/AI usage need controls | Often attractive compute/egress claims and flexible shapes; validate support and managed-service fit, not price alone |
| Latency for Ethiopia | Unknown until carrier testing; Cape Town is far south | Unknown; Johannesburg may beat Cape Town geographically but routing dominates | Unknown; Johannesburg is a strong measurement candidate | Unknown; Johannesburg and selected Middle East regions should be measured |
| Scalability | Very high; broad global services and mature autoscaling | Very high; global platform and enterprise services | Very high; strong global network, data and AI platform | High; adequate for AYO scale if regional services and operations are validated |
| Vendor lock-in | High when using proprietary event, identity, database and AI services | High with Entra/Functions/Cosmos/proprietary platform use | High with managed data/AI/serverless-specific services | Moderate-to-high; Oracle database/platform features increase lock-in |
| Compliance support | Broad attestations/artifacts; AYO remains responsible for Ethiopian requirements | Broad compliance/governance tooling and enterprise documentation | Broad compliance/security documentation and data-boundary controls | Broad compliance/sovereignty documentation | 
| Managed-service breadth | Broadest/mature portfolio; regional gaps still possible | Broad enterprise portfolio; regional SKU differences matter | Strong compute, data and AI services; Johannesburg catalogue is still region-specific | Broad core IaaS/database services; ecosystem depth is smaller than hyperscaler leaders |

### Provider-specific findings

#### AWS

AWS Cape Town has three Availability Zones. Nitro Enclaves are available there, have no external networking or persistent storage, and support attestation-bound AWS KMS operations. This is a strong match for later narrow Tier 3 key-release or high-risk processing. The tradeoff is enclave-specific development and parent-instance operations; it is not a general serverless solution.

#### Microsoft Azure

Azure provides the broadest documented confidential-computing portfolio across confidential VMs, containers, attestation, secure key release, Managed HSM and confidential GPU options. Confidential VM limitations can affect backup, site recovery, networking and live migration, so AYO must verify the exact design and South African availability. Azure is especially credible if AYO later adopts Microsoft identity/enterprise operations heavily.

#### Google Cloud

Google Cloud operates three Johannesburg zones and offers strong Confidential VM/Space and confidential H100 GPU capabilities globally. Its AI/data platform and Johannesburg location make it the strongest alternative for future confidential AI. Exact confidential machine/GPU availability in `africa-south1` must be verified; managed AI APIs are not automatically equivalent to AYO-controlled attested confidential inference.

#### Oracle Cloud Infrastructure

OCI Johannesburg is credible and may offer attractive compute/egress economics. OCI confidential VM options use AMD SEV-family technologies, with SEV-SNP and customer-operated attestation on eligible newer shapes. This increases portability/control but also operational responsibility. OCI is a viable price/DR comparison, not the provisional first choice until Ethiopian latency, local engineering support and regional service depth are proven.

### Other options

- **Local Ethiopian hosting or colocation:** potentially valuable for verified data-location, carrier proximity or regulated requirements, but must prove physical security, power/network redundancy, HSM, managed database, backups, support and disaster recovery. It should not be assumed safer or cheaper than managed cloud.
- **Specialist confidential-computing/AI vendors:** may reduce enclave engineering effort but add a vendor and trust boundary. Consider only after workload-specific due diligence, attestation ownership, portability, financial stability and provider-region evaluation.
- **Multi-cloud from day one:** rejected for MVP. It duplicates skills, IAM, observability, networking and incident procedures before AYO has scale evidence. Portability and off-provider backups provide better early risk reduction.

## 6. Provisional recommendation for approval

### Recommended option: AWS-first, portable managed MVP

Subject to CTO review, CEO approval, Ethiopian legal verification, carrier benchmarks and commercial quotes, use AWS Africa (Cape Town) as the provisional primary MVP region.

**Why:**

- Three Availability Zones support an in-region high-availability design.
- Mature managed PostgreSQL, object storage, keys, secrets, audit and autoscaling services reduce the small team's operational burden.
- Nitro Enclaves are confirmed in Cape Town, preserving a narrow Tier 3 migration path without imposing confidential computing on Tier 1.
- Standard PostgreSQL, S3-compatible export formats, containers and OpenTelemetry can limit lock-in.

### Strong alternative: Google Cloud Johannesburg

Choose Google Cloud instead if measured Ethiopian latency/reliability is materially better, required services are regionally available, or the approved roadmap prioritizes confidential GPU/AI capabilities enough to outweigh AWS operational familiarity and enclave integration advantages.

### CTO comparison gate

Before selecting either, run the same small proof-of-capability—not production deployment—against AWS Cape Town and Google Cloud Johannesburg:

- Mobile-network latency, packet loss and DNS/TLS connection timing.
- Managed PostgreSQL HA/backup/restore capabilities and quote.
- Managed compute cold/warm latency and autoscaling behavior.
- Secrets/KMS regional availability and audit export.
- Object-storage encryption, retention lock and cross-provider export.
- Required Tier 3 attestation/key-release feasibility.
- Monthly cost at idle, pilot, 10x pilot and stress-load assumptions.

Azure remains a Tier 3/enterprise finalist if its South African confidential SKUs and commercial terms are superior. OCI remains a cost/portability benchmark and possible secondary recovery destination.

## 7. Approved cost-efficient MVP topology

```text
Rider App        Driver App        Admin Dashboard
     \               |                    /
              AYO API Edge
     authentication, rate limits, API versioning
                       |
          FastAPI Modular Monolith
 -------------------------------------------------
 Identity | Drivers | Rides | Dispatch | Pricing
 Pickup   | Safety  | Ledger | Payments | Support
 Notifications | Audit | Analytics Events
 -------------------------------------------------
                       |
          PostgreSQL + PostGIS
                       |
        Worker Queue / Cache / Outbox
                       |
 Maps | SMS | Push | Payment Provider Adapters
```

These are clean internal modules, not separately deployed services initially. The approved topology is cloud-neutral: provider-specific networking, managed compute, PostgreSQL, queues, storage, keys and observability will be selected only in a later approved design after evidence is available.

### Architecture rules

- Extract a module only when traffic, security risk, team ownership or operational evidence justifies the customer and operating cost.
- Do not introduce microservices merely to claim scalability.
- Use provider-neutral interfaces and open standards where practical.
- Isolate cloud SDKs inside infrastructure/provider adapters and keep domain rules portable.
- AWS Cape Town is provisional pending Ethiopian latency/reliability tests and actual pricing.
- Apply Tier 3 confidential computing only when Tier 2 cannot adequately address an identified risk or verified requirement.
- This topology does not authorize infrastructure deployment.

### MVP cost controls

- Begin with one cloud and one primary region; use multiple AZs, not multiple clouds.
- Prefer managed/serverless or small autoscaled container compute with hard min/max limits.
- Use managed PostgreSQL rather than self-managed clusters; right-size from measured load.
- Avoid always-on Kubernetes until scheduling/scale evidence justifies its operating cost.
- Control NAT gateways, cross-zone/cross-region traffic, logs, metrics cardinality, backups, map routing and AI tokens with budgets/alerts.
- Use lifecycle policies for logs/documents/backups under approved retention rules.
- Reserve/commit capacity only after stable usage is observed.
- Track cost per completed ride and cost by module/provider call.

## 8. Migration path to stronger confidential computing

1. **MVP:** Tier 1 managed compute and Tier 2 isolation, KMS/secrets, restricted data access and encrypted managed services. No general TEE requirement.
2. **Trigger and threat model:** Identify a precise workload where privileged-host/cloud risk, multi-party mistrust or regulation makes Tier 2 insufficient.
3. **Portable confidential interface:** Define an internal attestation evidence and key-release interface; keep domain logic outside provider SDKs.
4. **Pilot:** Move only the minimal sensitive processor into Nitro Enclaves, Confidential VM/Space or another approved TEE. Use synthetic data first.
5. **Verify:** Independent security review, attestation-negative tests, performance/cost benchmarks, failure/recovery and side-channel assessment.
6. **Production gate:** CTO approves technical readiness; CEO approves cost/customer/regulatory outcome; local legal review resolves affected regulation.
7. **Future AYO Pay:** Re-evaluate provider, key custody, HSM, confidential compute and regulated operations from first principles. Do not inherit ride-ledger assumptions.

## 9. Mandatory data classification rules

| Class | Examples | Minimum tier and rules |
|---|---|---|
| Public | Published service information, public app assets | Tier 1; integrity controls and safe caching |
| Internal | Non-sensitive operational configuration, privacy-minimized aggregate metrics | Tier 1; authenticated staff/workload access and retention |
| Confidential | User profiles, ride records, coarse/recent operational location, ledger views | Tier 1 hardened storage with Tier 2 access paths for sensitive operations; encryption and audit |
| Restricted | Identity documents, precise location history, provider/payment secrets, safety/fraud cases, key material | Tier 2 minimum; separate boundaries, time-bound access, stronger encryption/audit; Tier 3 only when trigger is proven |
| Regulated/critical | Future legally classified payment/identity data and key-release workloads | Legal classification plus CTO/CEO-approved Tier 2 or Tier 3 design; fail closed |

- Data owners classify data before collection and document purpose, location, retention, access and deletion.
- Derived, cached, exported, logged and AI-embedded data inherit the highest applicable source classification unless formally declassified.
- Unknown data defaults to Restricted until classified.
- Production sensitive data is prohibited in development/test.

## 10. Encryption and key ownership

### In transit

- TLS 1.2 minimum with TLS 1.3 preferred where supported; validated certificates and modern cipher policy.
- Private endpoints/service networking for database, storage, secrets and internal provider paths where available.
- Mutual TLS or workload-identity-authenticated channels for high-risk internal boundaries as threat-modelled.
- Mobile certificate pinning is not automatic; adopt only with a safe rotation/recovery design.

### At rest

- Provider encryption is mandatory for all storage, database, queue, log and backup data.
- Use customer-managed envelope-encryption keys for Restricted data when the control benefit outweighs key-availability/rotation risk.
- Apply application/field encryption to selected Tier 2 fields where database/storage administrators must not see plaintext.
- Keep encryption metadata/version so data can be rotated and restored.

### Key ownership

- AYO owns key policy, authorization, rotation, disable/recovery decisions and audit evidence.
- Provider-managed keys are acceptable for Tier 1 where the threat model and legal review allow.
- Customer-managed keys are the default proposal for Tier 2 storage; the CTO can approve exceptions with reasons.
- Tier 3 key release is bound to attestation measurements and approved workload identity.
- Keys must not be exported merely to claim ownership. External key custody/HYOK adds outage and operational risk and requires a proven legal/threat need.

## 11. HSM and secrets management

- Use managed secret storage and workload identity; never long-lived credentials in code, images, CI variables without controls, mobile apps or logs.
- Rotate provider/payment credentials and database credentials automatically where supported.
- Use KMS HSM-backed key protection where service guarantees meet the tier. Use dedicated/single-tenant managed HSM only for keys whose risk or regulation justifies its fixed cost and quorum operations.
- Separate key administrators, service deployers and data users. High-risk key deletion/disable/rotation uses dual approval and break-glass controls.
- Back up/export keys only through supported protected mechanisms and test recovery without exposing plaintext key material.
- Alert on secret reads, policy changes, failed decrypt/attestation, disabled keys and unusual geographic/workload access.

## 12. Access approval and AI agent restrictions

### Human/workload access

- No standing human access to production databases, Restricted buckets or Tier 3 workloads.
- Use just-in-time, time-limited access with ticket/case, purpose, approver and session audit.
- Tier 2 sensitive access requires the data owner or designated operations/security approval; high-risk export/correction requires separation of duties.
- Tier 3 production access is through controlled APIs and attested workloads, not shell access. Break-glass use is exceptional, alerted and reviewed.
- Revoke access automatically on role change/offboarding and review permissions regularly.

### AI agents

- AI agents receive no general cloud-console, database, secrets, HSM or production-shell access.
- Grant narrow task-specific tools with least privilege, explicit schemas, bounded time/rate/value, environment isolation and human approval for consequential actions.
- Never put raw payment secrets, private keys, full identity documents or unrestricted precise-location histories into prompts or long-term agent memory.
- Treat model/tool output as untrusted. Validate authorization and business rules outside the model.
- Log tool requests/outcomes safely, not hidden chain-of-thought or unnecessary sensitive payloads.
- Require human approval for financial movement, account suspension, safety escalation, key policy, production deployment and destructive actions.
- Tier 3 AI inference requires data minimization, attestation, encrypted input/output, model/version evidence, egress controls and a non-AI safe fallback.

## 13. Audit logging

- Centralize immutable or tamper-evident audit events in a security-controlled account/project.
- Record identity, action, target, result, time, reason, source workload/session and correlation ID.
- Audit all IAM, KMS/HSM, secret, database-admin, object access, backup, restore, Tier 2/3 case, attestation and infrastructure-policy events.
- Do not log OTPs, secrets, key material, full documents, payment credentials or unnecessary precise location.
- Protect log integrity, restrict deletion/export and define retention through Ethiopian legal/privacy review.
- Regularly test alerts for privilege escalation, public exposure, logging disablement, unusual decrypt/secret reads and failed Tier 3 attestations.

## 14. Backups, disaster recovery and provider outage

- Define leadership-approved RPO/RTO by domain; money/ride/safety data need stricter objectives than rebuildable assets.
- Use encrypted automated PostgreSQL backups, point-in-time recovery and deletion protection.
- Store versioned/locked object backups with least privilege and a separate backup administration boundary.
- Maintain periodic portable logical PostgreSQL exports and critical configuration/IaC copies outside the primary failure boundary; encrypt with separately governed keys.
- Restore test at least quarterly before launch cadence is finalized; measure integrity and RPO/RTO, not only job success.
- Multi-AZ handles a data-centre failure. Cross-region/cross-provider recovery is a separate business decision with latency, sovereignty, cost and consistency tradeoffs.
- For provider outage, degrade noncritical features, preserve retry/idempotency, queue safe commands and communicate honestly. Never downgrade security or fabricate financial/ride state.
- Maintain tested provider status/escalation contacts, manual safety/support procedures and a CTO-approved regional recovery runbook.

## 15. Cloud exit and portability

- Keep core domain code provider-neutral; isolate cloud SDKs behind adapters.
- Use PostgreSQL, OCI-compatible container images, OpenTelemetry and portable file/data formats.
- Keep infrastructure definitions and configuration in version control without secrets.
- Export and restore database, objects, ledger/audit evidence and keys through documented procedures; test into a clean isolated environment.
- Avoid proprietary databases/workflow/AI services in the critical path unless their measured benefit and exit cost are approved.
- Document egress volume/time/cost and contract termination/data-deletion evidence.
- Portability means a tested exit path, not expensive active-active multi-cloud equivalence.

## 16. Risks and edge cases requiring design-stage treatment

| Risk | Impact | Required response before implementation |
|---|---|---|
| Ethiopia-to-South-Africa latency/routing instability | Poor booking/driver experience | Multi-carrier benchmark; polling/retry/offline design; edge use without moving authority to cache |
| Regional service/SKU gaps | Architecture cannot deploy as assumed | Exact region/account proof and alternative service mapping |
| Confidential computing creates false confidence | Sensitive data exposed outside TEE boundary | End-to-end threat model, minimal TCB, attestation and egress review |
| TEE/enclave operational failure | Key release or sensitive flow unavailable | Fail-closed design, safe manual fallback, capacity and recovery test |
| Customer-managed key loss/misconfiguration | Irrecoverable or inaccessible data | Dual control, deletion protection, monitoring and tested key/backup recovery |
| Managed service lock-in | Expensive/slow cloud exit | Adapters, open data formats, portable backups and exit drills |
| Multi-cloud complexity too early | Higher cost and weaker operations | Single-cloud MVP; portability rather than active multi-cloud |
| AI agent over-privilege/prompt injection | Data disclosure or harmful action | Tool allowlists, external authorization, human approval and isolation |
| Cross-border data restrictions | Illegal processing/transfer | Qualified Ethiopian legal verification before data placement |
| Provider cost spikes | Unsustainable unit economics | Budgets, quotas, autoscaling caps, cost per ride and provider-call controls |

## 17. Alternatives considered

### A. Confidential computing for every workload

**Pros:** uniform maximum data-in-use isolation story.  
**Cons:** higher compute/skills/observability complexity; some backup/network/autoscaling limitations; larger failure surface.  
**Cost/scaling:** potentially expensive and capacity/SKU constrained.  
**Customer impact:** little added benefit for public/ordinary workloads; outages or latency may harm experience.  
**Decision:** not recommended.

### B. Standard managed cloud only

**Pros:** simplest and lowest initial cost.  
**Cons:** no attestation-bound data-in-use protection for future high-risk workloads.  
**Cost/scaling:** efficient for MVP.  
**Customer impact:** good performance, but insufficient for specific future threats/regulation.  
**Decision:** use for Tier 1 and hardened Tier 2, with a Tier 3 migration path.

### C. Multi-cloud active-active MVP

**Pros:** theoretical provider-outage resilience and bargaining power.  
**Cons:** duplicated security, data consistency, skills, testing and incident burden.  
**Cost/scaling:** highest early cost; slows a small team.  
**Customer impact:** complexity may reduce reliability more than it improves it.  
**Decision:** not recommended; use portability and off-boundary backups.

### D. Self-hosted/private cloud MVP

**Pros:** possible physical/data-location control.  
**Cons:** AYO owns patching, hardware, database, backup, DDoS, HSM, power/network and staffing risk.  
**Cost/scaling:** high fixed and operational cost; slow scale.  
**Customer impact:** local latency could improve, but availability may degrade without proven facilities.  
**Decision:** not recommended absent a verified legal requirement or superior audited local partner.

## 18. Required approvals and next step

### CTO review completed for architectural clarification

- Approved the three-tier principle and modular-monolith topology on 2026-07-15.
- Approved clean module boundaries, evidence-based extraction and provider-neutral/cloud-portable design.
- No cloud provider or infrastructure deployment approved.

### CEO approval completed for architectural clarification

- Approved the same architectural clarification on 2026-07-15.
- AWS remains provisional; proof-of-capability funding/scope and final provider selection remain undecided.

### Remaining approval request before provider-specific design

- Approve the AWS-versus-GCP proof-of-capability scope and Ethiopian carrier testing.
- Review actual provider quotes and exact regional-service availability.
- Approve the selected cloud and any justified Tier 3 MVP workload; the default remains none.

### Stop condition

No provider-specific detailed architecture, cloud account setup, proof-of-capability execution, provider contract or infrastructure deployment may start until the remaining CTO review and CEO approval are recorded.

## 19. Primary research sources

Provider features and availability must be rechecked at design time.

### AWS

- [AWS regions: Cape Town has three Availability Zones](https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-regions.html)
- [Nitro Enclaves overview, isolation, availability and pricing](https://docs.aws.amazon.com/enclaves/latest/user/)
- [Nitro Enclaves concepts and constraints](https://docs.aws.amazon.com/enclaves/latest/user/nitro-enclave-concepts.html)
- [Nitro Enclaves attestation and KMS integration](https://docs.aws.amazon.com/enclaves/latest/user/set-up-attestation.html)
- [RDS encryption with AWS KMS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.Encryption.html)

### Microsoft Azure

- [Azure regions list](https://learn.microsoft.com/en-us/azure/reliability/regions-list)
- [Azure confidential VM overview and limitations](https://learn.microsoft.com/en-us/azure/confidential-computing/confidential-vm-overview)
- [Azure confidential computing overview](https://learn.microsoft.com/en-us/azure/azure-sovereign-clouds/public/confidential-computing)
- [Azure confidential GPU options](https://learn.microsoft.com/en-us/azure/confidential-computing/gpu-options)
- [Azure Database for PostgreSQL encryption and Managed HSM](https://learn.microsoft.com/en-us/azure/postgresql/security/security-data-encryption)

### Google Cloud

- [Google Cloud regions/zones: Johannesburg `africa-south1`](https://cloud.google.com/compute/docs/regions-zones)
- [Google Cloud Johannesburg region announcement](https://cloud.google.com/blog/products/infrastructure/heita-south-africa-new-cloud-region)
- [Confidential VM overview](https://cloud.google.com/compute/docs/about-confidential-vm)
- [Confidential Space security overview](https://cloud.google.com/docs/security/confidential-space)
- [Google Cloud confidential computing and confidential H100](https://cloud.google.com/security/products/confidential-computing)
- [Cloud SQL for PostgreSQL managed features](https://cloud.google.com/sql/postgresql)
- [Cloud SQL backups](https://cloud.google.com/sql/docs/postgres/backup-recovery/backups)
- [Regional Secret Manager locations](https://cloud.google.com/secret-manager/docs/locations)

### Oracle Cloud Infrastructure

- [OCI Johannesburg cloud region](https://www.oracle.com/za/cloud/cloud-regions/johannesburg/)
- [OCI confidential computing](https://docs.oracle.com/en-us/iaas/Content/Compute/References/confidential_compute.htm)
- [OCI Database with PostgreSQL backups](https://docs.oracle.com/en-us/iaas/Content/postgresql/backups.htm)
- [OCI HSM vault/key backup and restore](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Tasks/backingupvaultsandkeys.htm)
