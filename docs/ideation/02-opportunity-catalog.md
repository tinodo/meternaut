# The Opportunity Catalog — 17 families, 300+ ideas

> **Status:** Ideation v1 · **Date:** 2026-10-30 · Part of the [north-star vision](01-north-star-vision.md)
> **Rule of the catalog:** *every entry is a **hypothesis to validate** unless it is mapped to a verified source in [Appendix A](#appendix-a--evidence-map).* The catalog is for breadth; the research reports ([05 cost traps](../research/05-cost-traps-and-dark-spend.md), [04 seed facts](../research/04-seed-example-facts.md)) carry the verification.
> **Scope guard:** ideation. Technical feasibility is ignored here on purpose; the spikes in the [plan](../plan/03-capability-radar.md) test it.

---

## How to read this catalog

| Column | Meaning |
|---|---|
| **ID** | Stable identifier (`FAMILY-NN`) used by playbooks, cases and the plan |
| **Opportunity** | What is wrong or improvable |
| **Usage-truth signal** | What would *prove* it — the evidence the Analyst must gather (usage, not just billing) |
| **Action** | The verb from the [action vocabulary](06-closed-loop-actions-and-autonomy.md#2-the-action-vocabulary-the-verbs) |
| **Rev** | Reversibility class **R0–R3** ([06](06-closed-loop-actions-and-autonomy.md)); `—` = advice only |
| **Ceil** | *Suggested first-generation autonomy ceiling* (L1–L4), **to be ratified** in the guardrails phase; many items should start at L1/L2 |

Items marked **★** are the two seed examples from the brief. Items marked **⚑** need **security co-sign** (they touch security posture or compliance). Items marked **§** are *protected-class candidates* — likely "advise only" until a recorded exception.

---

## The cross-cutting plays (sequencing matters)

Many savings interact. The Conductor sequences cases into **plays**:

| Play | Sequence | Why |
|---|---|---|
| **Right-size, then commit** | SIZE → RATE-01/02 | Don't commit to capacity you are about to remove |
| **Hybrid Benefit before reservations** | RATE-07/08 → RATE-01 | Licensing changes the effective baseline |
| **Fix at source, then filter, then price** | TELE-26 → TELE-02 → TELE-09/RATE-17 | Eliminate noise at the root before buying a discount tier |
| **Schedule, then reserve the remainder** | TIME → RATE | Reserve only the always-on baseline |
| **Consolidate, then right-size** | PLAT/SIZE-06 → SIZE | Resize the merged thing once |
| **Owner first** | GOV-01 → everything | No action without a confirmed owner |
| **Forced migrations as windows** | PLAT-10 | Retirement-driven moves double as right-sizing windows |
| **Delete orphans, then revisit subscription-level plans** | IDLE → SEC-03, IDLE-29 | A subscription may be empty after cleanup |

---

## 1. IDLE — Idle and zero-use

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| IDLE-01 | Unattached managed disks | Disk state *unattached* for N days; no snapshot lineage; no recent restore | Snapshot, countdown, delete | R2 | L4 dev, L2 prod |
| IDLE-02 | Orphan snapshots (source disk gone, old) | Snapshot age; source missing; no restore history | Archive or delete after owner check | R2 | L3 |
| IDLE-03 | Unattached public IPs | Not associated with NIC/LB/gateway; absent from DNS and known allow-lists | Release (**address loss is R3**) | R3 | L2 |
| IDLE-04 | Idle NAT gateways | Outbound bytes near zero; no subnet attached | Remove | R2 | L2 |
| IDLE-05 | Load balancers with empty backend pools | Backend count zero; no data-path bytes | Remove after dependency check | R2 | L2 |
| IDLE-06 | Application Gateways with no backend traffic | Requests/throughput near zero; no healthy backends | Stop or remove where supported | R2 | L2 |
| IDLE-07 | Private endpoints disconnected, rejected or pending | Connection state | Remove | R1 | L3 |
| IDLE-08 | ExpressRoute circuits never provisioned | Provider provisioning state *not provisioned* (verify billing behaviour) | Delete | R2 | L2 |
| IDLE-09 | VPN/ER gateways with no connections | Zero connections; zero tunnel bytes | Remove or downsize | R2 | L2 |
| IDLE-10 | Azure Firewall with no traffic | Data processed near zero; rule hits zero | Deallocate or delete | R2 | L2 |
| IDLE-11 | Azure Bastion unused | Session count zero | Delete or swap SKU | R1 | L3 |
| IDLE-12 | DDoS protection plan covering nothing | No protected IPs | Remove plan | R2 | L2 ⚑ |
| IDLE-13 | Empty App Service plans | Plan with zero apps | Delete | R2 | L3 |
| IDLE-14 | App Service plans with idle apps | CPU, memory and requests near zero | Downsize | R1 | L2 |
| IDLE-15 | Functions Premium plans without traffic | Executions near zero while always-ready instances run | Move to a consumption-style plan | R1 | L2 |
| IDLE-16 | Container Apps with minimum replicas but no traffic | Requests zero | Scale to zero | R1 | L3 |
| IDLE-17 | AKS clusters or pools with no real workloads | Only system pods; low requests | Stop cluster or scale pool to zero | R1 | L2 |
| IDLE-18 | Idle VMs | CPU, network, disk and logins all low for N days | Scream-test ladder, then stop | R1 | L2 |
| IDLE-19 | **Stopped-but-not-deallocated VMs** | Power state *stopped* (still billed) | Deallocate | R0/R1 | L4 |
| IDLE-20 | Long-deallocated VMs holding premium disks | Deallocated for months | Snapshot and downgrade disk tier, or delete | R2 | L2 |
| IDLE-21 | Idle SQL databases or managed instances | Connections and CPU near zero | Pause (serverless), export, or delete | R2 | L2 |
| IDLE-22 | Idle Cosmos DB accounts or containers | Request units consumed near zero | Delete or move to serverless | R2 | L2 |
| IDLE-23 | Idle Redis caches | Connected clients and ops near zero | Downsize or delete | R2 | L2 |
| IDLE-24 | Idle API Management instances | Request count near zero | Downsize tier or delete | R2 | L2 |
| IDLE-25 | Idle Service Bus or Event Hubs namespaces on premium/dedicated tiers | Message count zero | Downsize or delete | R2 | L2 |
| IDLE-26 | Idle Data Explorer clusters | Queries and ingestion near zero | Stop or enable auto-stop | R1 | L3 |
| IDLE-27 | Idle Databricks, Synapse or Fabric capacity | No jobs; low capacity usage | Pause, terminate, auto-terminate | R1 | L3 |
| IDLE-28 | Idle Virtual Desktop hosts and developer workstations | No sessions for N days | Deallocate or delete | R1 | L3 |
| IDLE-29 | **Zombie subscriptions** with no workloads but recurring plans (security plans, support, backup) | Zero resources or near-zero activity | Cancel plans; close subscription | R2 | L3 |
| IDLE-30 | Backup items for resources that no longer exist | Protected item with missing source; retention still costing | Delete data after policy (data loss) | R3 | L1 ⚑ |
| IDLE-31 | Unused VM capacity reservations | Reserved capacity not consumed (billed whether used or not) | Release or associate | R2 | L2 |
| IDLE-32 | Idle SignalR/Web PubSub/Static Web Apps premium tiers | Connections zero | Downgrade | R1 | L3 |
| IDLE-33 | Container registries with no pulls | Pull counts near zero on premium/geo-replicated registries | Downgrade or remove replicas | R2 | L2 |
| IDLE-34 | Idle managed online endpoints and compute instances (ML) | Requests zero; compute idle | Delete or scale to zero | R2 | L2 |
| IDLE-35 | Idle Logic Apps (standard plans) and integration accounts | Runs zero | Delete | R2 | L3 |
| IDLE-36 | **Idle-shutdown that silently does not work** (e.g. compute-instance auto-shutdown blocked by a missing permission or by a still-"active" kernel/process) | Instance running with no real activity beyond the configured idle time | Fix permission/config; then enable shutdown | R1 | L2 |
| IDLE-37 | Virtual WAN hubs with little attached traffic (a fixed hourly hub fee applies regardless of traffic) | Hub connection count and processed bytes near zero | Consolidate or delete hub | R3 | L1 |
| IDLE-38 | Soft-deleted backup items and vaults retained past usefulness (soft-delete is billed after the free window; a vault with soft-deleted items cannot be deleted) | Soft-deleted items older than policy | Purge after confirmation | R3 | L1 ⚑ |
| IDLE-39 | Deprecated multi-step availability tests still running and billing | Test type and last review | Remove or migrate | R1 | L3 |
| IDLE-40 | Orphaned persistent-volume disks in a Kubernetes node resource group (reclaim policy *retain*) | Disk tagged for a claim whose namespace no longer exists | **Fix at source** (the cluster owner removes the claim); managed groups resist direct deletes | R2 | L2 |
| IDLE-41 | Managed private endpoints and integration compute left running in analytics workspaces | Zero activity | Remove | R2 | L3 |

---

## 2. SIZE — Over-provisioned, including hidden capacity units

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| SIZE-01 | VM right-sizing | CPU, memory, network, disk p95 over 30–90 days, incl. peak weeks | Resize | R1 | L2 |
| SIZE-02 | Older VM generations | SKU generation vs price-performance of newer ones | Resize to newer generation | R1 | L2 |
| SIZE-03 | Premium disks where standard suffices | Provisioned IOPS/throughput vs actual | Change disk SKU (may need downtime) | R1 | L2 |
| SIZE-04 | Provisioned IOPS on advanced disks | Metrics vs provisioned | Reduce provisioned performance | R1 | L2 |
| SIZE-05 | SQL database/managed-instance SKU | CPU, IO, worker p95 | Scale down | R1 | L2 |
| SIZE-06 | SQL databases that fit an elastic pool | Many underused single databases with complementary peaks | Pool | R1 | L2 |
| SIZE-07 | SQL service-tier overkill (Hyperscale/Business Critical vs General Purpose) | Read scale-out use; IO; HA need | Re-tier | R2 | L1 |
| SIZE-08 | Cosmos DB throughput | Normalised RU consumed vs provisioned; throttling | Autoscale, manual, or serverless | R1 | L2 |
| SIZE-09 | Cosmos DB indexing bloat | Index metrics; RU per write | Tune indexing policy | R2 | L1 |
| SIZE-10 | App Service plan SKU and density | CPU/memory p95; apps per plan | Resize or consolidate | R1 | L2 |
| SIZE-11 | Application Gateway minimum capacity | Capacity units used vs minimum instance count | Lower minimum | R1 | L3 |
| SIZE-12 ★ | **Virtual WAN point-to-site gateway scale units** | Concurrent connections and bandwidth vs scale units over 90+ days | Scale down | R1 | L2 |
| SIZE-13 | Virtual WAN site-to-site and ExpressRoute gateway scale units | Tunnel/circuit bandwidth vs scale units | Scale | R1 | L2 |
| SIZE-14 | Virtual WAN hub capacity | Hub throughput and workload count vs hub capacity | Scale | R1 | L2 |
| SIZE-15 | VPN/ExpressRoute gateway SKU oversize | Throughput and tunnel counts | Downsize SKU (may need recreate) | R2 | L1 |
| SIZE-16 | Event Hubs throughput/processing units and auto-inflate creep | Throughput vs units (auto-inflate scales up, not down) | Lower | R1 | L3 |
| SIZE-17 | Service Bus premium messaging units | Namespace CPU/memory vs units | Lower | R1 | L2 |
| SIZE-18 | API Management units and tier | Capacity metric | Lower | R1 | L2 |
| SIZE-19 | AI Search replicas, partitions, units | QPS, latency, storage used | Lower | R1 | L2 |
| SIZE-20 | Redis SKU, size, shards | Memory, CPU, connections | Resize | R1 | L2 |
| SIZE-21 | Premium file shares provisioned vs used | Used capacity and IOPS vs provisioned | Reduce | R1 | L2 |
| SIZE-22 | NetApp Files capacity pools and QoS | Used vs provisioned | Resize | R1 | L2 |
| SIZE-23 | AKS node size, packing and autoscaler | Requests vs usage; node CPU/memory | Right-size nodes; tune autoscaler | R1 | L2 |
| SIZE-24 | Kubernetes pod requests and limits | Requests vs p95 usage | Pull request to manifests | R1 | L1 |
| SIZE-25 | VM scale set minimums and autoscale ranges | Utilisation vs min/max | Lower minimum | R1 | L3 |
| SIZE-26 | Flex/Premium function plans and Container Apps concurrency | Utilisation | Tune | R1 | L3 |
| SIZE-27 | Fabric/Power BI capacity SKU and smoothing | Capacity-unit utilisation | Resize or pause | R1 | L2 |
| SIZE-28 | Synapse dedicated pool DWU; Data Explorer SKU and node count | Utilisation | Resize | R1 | L2 |
| SIZE-29 | Databricks cluster sizing and auto-termination | Cluster utilisation | Tune | R1 | L2 |
| SIZE-30 | Backup policy over-retention | Policy retention vs need | Lower retention (**data loss**) | R3 | L1 ⚑ |
| SIZE-31 | Over-sized Bastion, NAT and load-balancer tiers | Throughput vs tier | Re-tier | R1 | L3 |
| SIZE-32 | Search/vector index storage and dimensions | Index statistics | Tune | R2 | L1 |
| SIZE-33 | Cosmos DB autoscale maximum set far above real peaks (billed at the hourly peak reached) | Normalised RU consumption vs configured maximum | Lower the ceiling | R1 | L2 |
| SIZE-34 | Databricks pools with idle minimum instances kept warm | Pool idle-instance hours | Lower minimum idle | R1 | L3 |
| SIZE-35 | Container Apps workload profiles (dedicated profiles bill per reserved instance; some profiles cannot scale to zero) | Profile utilisation | Re-profile | R1 | L2 |

---

## 3. TIME — Scheduling and elasticity

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| TIME-01 | Dev/test sleep schedules | No sessions or traffic outside business hours | Deallocate and start on schedule | R1 | L4 |
| TIME-02 | Weekend and holiday shutdown (regional calendars) | Calendar + usage | Schedule | R1 | L3 |
| TIME-03 | Non-prod AKS stop schedules | Usage by hour | Stop cluster or scale pools to zero | R1 | L3 |
| TIME-04 | Fabric/Power BI capacity pause windows | Usage by hour | Pause schedule | R1 | L3 |
| TIME-05 | Virtual Desktop scaling plans and workstation auto-stop | Session patterns | Configure | R1 | L3 |
| TIME-06 | Scale-by-calendar for known events (e.g. gateway capacity for the all-hands) | Event calendar vs capacity | Schedule scaling | R1 | L2 |
| TIME-07 | Serverless auto-pause and scheduled scale for databases | Idle windows | Configure | R1 | L3 |
| TIME-08 | Auto-stop for Data Explorer, Synapse, Databricks | Idle periods | Configure | R1 | L3 |
| TIME-09 | Follow-the-sun capacity | Regional demand shape | Shift | R1 | L1 |
| TIME-10 | Test-environment time-to-live | Test-run history | Auto-delete | R2 | L3 |
| TIME-11 | Ephemeral-environment expiry (expiry tags) | Expiry date passed | Tear down | R2 | L3 |
| TIME-12 | Batch workloads on spot/cheaper windows | Job tolerance to interruption | Move | R1 | L2 |

---

## 4. RATE — Pricing models, commitments, licensing

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| RATE-01 | Reservation recommendations for steady-state resources | Stable baseline over 30–90 days **after** planned right-sizing | Staged purchase | R3 | L2 two-key |
| RATE-02 | Savings plan for compute | Baseline compute spend | Staged purchase | R3 | L2 two-key |
| RATE-03 | Commitment scope optimisation | Utilisation by scope (where scope can be changed) | Change scope | R1 | L3 |
| RATE-04 | Under-used reservations | Utilisation under target | Re-target, exchange or return within policy | R3 | L1 |
| RATE-05 | Orphaned reservations after SKU migrations | Reserved SKU no longer running | Exchange within policy | R3 | L1 |
| RATE-06 | Reservation expiry planning | Expiry vs forecast baseline | Renew, resize or lapse | R2 | L2 |
| RATE-07 | Hybrid Benefit not applied (Windows Server, SQL Server) | Eligible entitlements vs resources; licensing confirmation | Apply benefit | R1 | L2 |
| RATE-08 | Linux subscription benefits | Eligible images | Apply | R1 | L2 |
| RATE-09 | Dev/Test pricing for non-production subscriptions | Subscription offer vs environment | Move or re-create subscription | R1 | L1 |
| RATE-10 | Spot VMs for tolerant workloads | Stateless, interruption-tolerant | Move to spot | R1 | L1 |
| RATE-11 | Region price differences | Same workload, cheaper region; residency and latency constraints | Move (big change) | R3 | L1 |
| RATE-12 | Commitment burn-down steering (enterprise commitment) | Commitment vs consumption forecast | Advise | — | L1 |
| RATE-13 | Marketplace subscriptions unused or auto-renewing | Usage vs charge | Cancel/renew decision | R2 | L1 |
| RATE-14 | Negotiated-price drift | Effective unit price vs price sheet | Inform/dispute | — | L1 |
| RATE-15 | Support plan fit | Ticket usage vs plan cost | Advise | R2 | L1 |
| RATE-16 | Prepayment/credit expiry | Balance and expiry | Use before expiry | — | L1 |
| RATE-17 | Commitment tier choice for monitoring and SIEM ingestion | Daily GB vs tier | Pick tier | R1 | L2 |
| RATE-18 | Capacity reservations vs reservations alignment | Both exist; mismatch | Align | R2 | L2 |
| RATE-19 | Security-plan pricing-model fit | Resource counts and transaction volumes | Switch plan model | R1 | L1 ⚑ |
| RATE-20 | Portfolio mix: reservation vs savings plan | Back-tested simulation | Rebalance | R3 | L1 |
| RATE-21 | **Break-even utilisation check** before any commitment (commitments are priced as if used 100% of the term) | Projected utilisation vs break-even | Gate every purchase | — | L1 |
| RATE-22 | Single-subscription commitment scope stranding unused hours | Utilisation by subscription | Widen scope | R1 | L3 |
| RATE-23 | Size-flexibility limits when moving between VM families | Reserved size-group vs running size-group | Plan before migrating | — | L1 |
| RATE-24 | Prepaid security-plan units use-it-or-lose-it | Consumption vs prepaid pool | Adjust plan scope | R2 | L1 ⚑ |
| RATE-25 | Commitment-tier ratchet (can be raised any time, lowered only after a lock period; dedicated clusters carry a minimum) | Daily volume vs tier | Choose conservatively; stage | R3 | L1 |

---

## 5. TELE — Telemetry and observability ★ (seed example 1)

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| TELE-01 ★ | **Tables ingested but never queried, alerted on, exported or rule-matched** | Ingestion volume vs query audit, alert rules, workbooks, security rules, export rules | Stop collecting; Basic/Auxiliary plan; export | R3 | L2 ⚑ |
| TELE-02 ★ | **Noisy log patterns inside heavily-used tables** (health probes, debug, success chatter) | Message-template mining vs what queries and alerts reference | Ingestion filter, **shadow first** | R3 | L2 ⚑ |
| TELE-03 ★ | Columns never referenced (huge raw-message fields) | Column reference analysis across queries | Drop columns at ingestion | R3 | L2 |
| TELE-04 | Verbose diagnostic settings (everything enabled) | Category usage | Narrow categories | R1 | L2 |
| TELE-05 | Duplicate ingestion (two paths, two workspaces) | Duplicate records per resource/time | Remove the duplicate path | R1 | L2 |
| TELE-06 | Table plan fit (analytics vs cheaper plans) | Query frequency and features used | Change plan | R1 | L2 |
| TELE-07 | Interactive retention longer than needed | Query age distribution; compliance requirements | Shorten interactive; archive | R3 | L1 ⚑ § |
| TELE-08 | Archive/long-term retention never restored | Restore/search-job history | Reduce | R3 | L1 ⚑ § |
| TELE-09 | Commitment tier or dedicated cluster fit | Daily GB distribution | Switch tier | R1 | L2 |
| TELE-10 | Workspace sprawl | Many small workspaces each with minimums | Consolidate (access-model impact) | R2 | L1 |
| TELE-11 | Container logs: probes, debug, namespaces | Template mining; namespace volume | Config change; exclude namespaces | R1 | L2 |
| TELE-12 | Metrics cardinality and scrape intervals | Series count; unused metrics | Relabel, drop, lengthen interval | R1 | L2 |
| TELE-13 | Application telemetry sampling and dependency noise | Per-type volume | Sampling configuration | R1 | L2 |
| TELE-14 | Availability tests too frequent or from too many locations (non-prod) | Test config vs environment | Reduce | R1 | L3 |
| TELE-15 | Log-alert rules: high frequency × dimensions × heavy queries | Rule count, frequency, time series | Tune | R1 | L3 |
| TELE-16 | Metric alerts with many time series in dev | Rule count | Prune | R1 | L3 |
| TELE-17 | Windows security events at "all" level | Event IDs actually used | Lower collection level | R3 | L1 ⚑ § |
| TELE-18 | Syslog facility/severity too wide | Severities actually queried | Narrow | R1 | L2 |
| TELE-19 | Performance counters at high frequency | Counters actually queried | Reduce | R1 | L3 |
| TELE-20 | VM dependency-map data unused | Map/connection tables never queried | Disable | R1 | L3 |
| TELE-21 | Flow logs and traffic analytics processing | Usage of the analytics output | Adjust | R1 | L2 |
| TELE-22 | Firewall logs in the legacy shared table | Table choice | Switch to resource-specific tables | R1 | L2 |
| TELE-23 | SIEM connectors ingesting high-volume low-value sources | Analytic-rule coverage per source | Re-tier or exclude | R1 | L1 ⚑ |
| TELE-24 | Activity-log duplicates across subscriptions | Duplicates | Remove | R1 | L3 |
| TELE-25 | Metrics copied into logs | Queries on copied metrics | Remove | R1 | L3 |
| TELE-26 | **Log statements in application code** (level misconfiguration, chatty loops) | Template→source mapping; level distribution | **Code pull request** | R1 | L1 |
| TELE-27 | Pipeline-stage filtering before ingestion | Patterns | Edge transform | R1 | L1 |
| TELE-28 | Log budgets and SLOs per team | Ingestion per team vs agreed budget | Governance | — | L1 |
| TELE-29 | **Incident-informed usefulness** | Which logs were used in past incidents and post-mortems | Prioritise keep/drop | — | L1 |
| TELE-30 | Data exports never consumed | Export rules vs downstream consumers | Remove export | R1 | L3 |
| TELE-31 | **Silent throttling** of metrics ingestion at default limits (loss of data, not only cost) | Throttle indicators vs active series | Reduce cardinality; raise limits deliberately | R1 | L2 |
| TELE-32 | Flow logs on storage with no retention/lifecycle policy | Container growth | Lifecycle | R1 | L3 |

---

## 6. DATA — Storage lifecycle and data platforms

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| DATA-01 | Blob tiering (hot → cool → cold → archive) | Last-access time and frequency | Lifecycle policy | R1 | L3 |
| DATA-02 | Versioning, soft-delete and snapshots growing without lifecycle rules | Version count and size | Lifecycle deletion (**data loss**) | R3 | L2 |
| DATA-03 | Old orphan snapshots and versions | Age; no restore history | Clean up | R3 | L2 |
| DATA-04 | Geo-redundancy where local or zone redundancy suffices | Criticality tag; recovery objectives | Downgrade redundancy (the lost copy is gone) | R3 | L1 |
| DATA-05 | **SFTP-enabled storage accounts with no SFTP use** | Zero SFTP sign-ins (hourly fee while enabled; verify) | Disable SFTP | R1 | L3 |
| DATA-06 | Unused storage accounts | Transactions near zero (beware infrastructure-state accounts) | Delete or archive | R2 | L2 § |
| DATA-07 | Storage diagnostic logs growth | Log container size | Lifecycle | R1 | L3 |
| DATA-08 | Small-file explosion (transaction costs) | Average object size; operations | Compaction | R2 | L1 |
| DATA-09 | Duplicate datasets across accounts and lakes | Inventory and content hashes | Consolidate | R2 | L1 |
| DATA-10 | Archive early-deletion and rehydration surprises | Tier transitions | Tune policies | R1 | L2 |
| DATA-11 | Time-to-live for ephemeral data in databases | Data age vs query horizon | Set TTL (**data loss**) | R3 | L1 |
| DATA-12 | SQL backup storage redundancy for non-prod | Redundancy vs environment | Lower | R3 | L2 |
| DATA-13 | Zone redundancy in non-prod databases | Environment | Disable | R1 | L2 |
| DATA-14 | Unused SQL indexes | Index usage statistics | Drop via pull request | R2 | L1 |
| DATA-15 | SQL long-term backup retention | Policy vs need | Tune (**data loss**) | R3 | L1 ⚑ |
| DATA-16 | Pipeline frequency and polling too high | Trigger-run history showing mostly empty runs | Reduce frequency | R1 | L3 |
| DATA-17 | Data-flow cluster time-to-live and integration-runtime sizing | Run duration and idle | Tune | R1 | L3 |
| DATA-18 | **Hot-cache window larger than query horizon** (Data Explorer) | Query time ranges | Reduce cache policy | R1 | L2 |
| DATA-19 | Ingestion capture copies nobody reads | Consumers | Remove | R1 | L3 |
| DATA-20 | Databricks pools, job vs all-purpose clusters, spot workers | Cluster utilisation | Tune | R1 | L2 |
| DATA-21 | Unused Fabric items, workspaces and refresh schedules | Usage; refresh history | Retire or reduce | R1 | L3 |
| DATA-22 | Dataset refresh frequency vs report usage | Report views | Reduce refresh | R1 | L3 |
| DATA-23 | Serverless SQL query scan volume | Bytes scanned | Partitioning pull request | R1 | L1 |
| DATA-24 | Backup vault redundancy defaults | Environment | Lower | R3 | L2 |
| DATA-25 | File-share snapshot accumulation | Snapshot count | Policy | R2 | L3 |
| DATA-26 | **Capacity pause with hidden settlement** (pausing a capacity may settle accumulated overage immediately; storage keeps billing) | Overage balance at pause; storage size | Plan pause windows; include settlement in the saving | R1 | L2 |
| DATA-27 | Soft-deleted containers billed at full data rate | Soft-deleted container size/age | Shorten retention window | R3 | L2 |
| DATA-28 | Change feed or inventory left on, writing to containers nobody reads | Consumers of the output | Disable | R1 | L3 |
| DATA-29 | Leftover unmanaged VHD page blobs after VM deletion | Blob lease state/age | Delete after owner check | R2 | L2 |

---

## 7. NET — Network

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| NET-01 | Cross-region data-transfer hotspots | Flow data by region pair | Co-locate | R3 | L1 |
| NET-02 | Internet egress that could be cached or private | Egress bytes by destination | Re-route or cache | R2 | L1 |
| NET-03 | Double processing (NAT plus firewall; unneeded hops) | Bytes processed per hop | Simplify | R2 | L1 |
| NET-04 | Private-link processing charges on high-volume paths | Endpoint bytes | Reconsider endpoint vs alternative | R2 | L1 |
| NET-05 | ExpressRoute metered vs unlimited | Monthly bytes | Switch plan | R1 | L2 |
| NET-06 | ExpressRoute Premium add-on unused | Features used | Remove | R1 | L2 |
| NET-07 | Under-used ExpressRoute Direct ports/circuits | Utilisation | Decommission | R3 | L1 |
| NET-08 | Front Door/CDN tier fit | Feature use | Downgrade | R2 | L1 |
| NET-09 | Application Gateway sprawl | Many gateways with low traffic | Consolidate multi-site | R2 | L1 |
| NET-10 | Global peering traffic | Bytes | Re-architect | R3 | L1 |
| NET-11 | Idle DNS resolver endpoints | Queries zero | Remove | R2 | L3 |
| NET-12 | Excess network-monitoring tests | Test count | Prune | R1 | L3 |
| NET-13 | VPN gateway sprawl across virtual networks | Gateway count vs traffic | Consolidate (vWAN or peering) | R3 | L1 |
| NET-14 | Retiring network SKUs (forced migrations) | SKU inventory | Plan migration | R2 | L2 |
| NET-15 | Private traffic going via public path (or vice versa) | Flow data | Re-route | R2 | L1 |
| NET-16 | **Flow-log migration duplicates** (legacy and new flow logs running in parallel double records and storage; legacy flow logs retire 30 Sep 2027) | Both log types enabled on the same network | Finish migration; disable legacy | R1 | L2 |

---

## 8. PLAT — Platform and architecture

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| PLAT-01 | Consolidate underused app-service plans | Density and utilisation | Consolidate | R2 | L2 |
| PLAT-02 | Fewer, shared Kubernetes clusters | Cluster count and utilisation | Consolidate (isolation review) | R3 | L1 |
| PLAT-03 | IaaS databases to PaaS | VM utilisation; operations burden | Migrate | R3 | L1 |
| PLAT-04 | Windows to Linux for web workloads | Runtime compatibility | Move | R3 | L1 |
| PLAT-05 | ARM-based SKU migration | Multi-architecture image readiness | Move | R2 | L1 |
| PLAT-06 | Function hosting-plan fit | Invocation pattern | Move plan | R1 | L2 |
| PLAT-07 | **Polling triggers billed per poll** (workflow engines) | Trigger runs mostly skipped | Lengthen interval or switch to event | R1 | L3 |
| PLAT-08 | Always-on dev VMs → managed dev workstations | Usage | Move | R3 | L1 |
| PLAT-09 | Redundancy over-engineering for low-criticality workloads | Criticality tag; recovery objectives | Reduce | R3 | L1 |
| PLAT-10 | **Retiring services/SKUs** | Inventory vs announcements | Plan migration (window for right-sizing) | R2 | L2 |
| PLAT-11 | Monolithic VM fleets → containers | Utilisation | Modernise | R3 | L1 |
| PLAT-12 | Overlapping services (several queues, several caches) | Inventory | Rationalise | R3 | L1 |
| PLAT-13 | Premium tiers where standard suffices | Feature use | Downgrade | R2 | L1 |
| PLAT-14 | Replicas never read (geo-replication, multi-region writes) | Read use per replica | Remove replicas | R2 | L2 |
| PLAT-15 | Preview SKUs approaching price changes | SKU status | Plan | — | L1 |

---

## 9. SEC — Security-tool economics (never trade away required security) ⚑

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| SEC-01 | Server protection plans on ephemeral or dev machines | Environment and lifecycle | Re-scope plan | R1 | L1 ⚑ |
| SEC-02 | Per-transaction storage protection on very high-transaction accounts | Transaction volume | Switch/cap | R1 | L1 ⚑ |
| SEC-03 | Plans enabled on subscriptions with no matching resources | Resource counts | Disable | R1 | L1 ⚑ |
| SEC-04 | SIEM ingestion tiering and commitment | GB/day vs coverage | Tier | R1 | L1 ⚑ |
| SEC-05 | DDoS network vs IP protection fit | Number of protected IPs | Switch | R1 | L1 ⚑ |
| SEC-06 | Firewall premium vs standard | Premium-feature logs show unused | Downgrade (redeploy) | R2 | L1 ⚑ |
| SEC-07 | Managed-HSM or premium keys unused | Key operations | Downgrade | R2 | L1 ⚑ |
| SEC-08 | Always-on connectivity where just-in-time access fits | Usage | Right-fit | R1 | L2 ⚑ |
| SEC-09 | Over-broad data-scanning scopes | Scan cost vs findings | Narrow | R1 | L1 ⚑ |
| SEC-10 | **The protected-sources registry** | Which log/retention/plan settings are compliance-critical | Protect (a guard for every other family) | — | L1 ⚑ |
| SEC-11 | SIEM enabled on a whole workspace bills *all* data analysed there | Share of non-security data in the workspace | Separate security data into a dedicated workspace | R2 | L1 ⚑ |
| SEC-12 | Malware-scanning caps and legacy per-transaction storage plans | Scan volume vs cap; plan generation | Adjust cap; migrate off the legacy plan | R1 | L1 ⚑ |
| SEC-13 | Redundant agentless scanning enabled by more than one plan | Duplicate scan snapshots per resource | De-duplicate | R1 | L1 ⚑ |

---

## 10. DEV — Developer platform

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| DEV-01 | **Preview environments outliving their pull request** | PR closed; environment alive | Tear down (owner = PR author) | R2 | L3 |
| DEV-02 | Build-agent pools with idle minimums | Queue time vs idle time | Lower minimum | R1 | L3 |
| DEV-03 | Always-on self-hosted runners | Job history | Scale to zero | R1 | L3 |
| DEV-04 | Wasted CI minutes (flaky retries, long tests) | Job statistics | Pull request to pipelines | R1 | L1 |
| DEV-05 | Container registry bloat (untagged and old images) | Pull statistics | Retention policy | R2 | L3 |
| DEV-06 | Long-lived sandboxes and test subscriptions | Creation date; activity | Add expiry | R2 | L3 |
| DEV-07 | Load-test leftovers | Test runs | Delete | R2 | L3 |
| DEV-08 | Idle cloud workstations/codespaces | Usage | Auto-stop | R1 | L4 |
| DEV-09 | **Infrastructure-state storage mistaken for "unused"** (false-positive guard) | Repository references to the account | Protect | — | L1 § |
| DEV-10 | Feature-branch databases | Branch merged | Tear down | R2 | L3 |
| DEV-11 | Package/artifact feed retention | Usage | Retention | R2 | L3 |
| DEV-12 | Prod-size SKUs in dev | Environment tag vs SKU | Dev-SKU policy | R1 | L2 |

---

## 11. AI — AI workloads

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| AI-01 | **Near-idle fine-tuned model deployments** — hosting is billed hourly regardless of calls; a deployment with *zero* calls for 15 days is deleted automatically, so the waste sits in the first 15 days and in near-idle deployments kept alive by health checks or trickle traffic | Requests per hosting hour; keep-alive call patterns | Undeploy (the customised model is kept and can be redeployed) | R1 | L2 |
| AI-02 | Provisioned throughput under-utilised | Utilisation percentage | Resize or switch to pay-as-you-go | R1 | L2 |
| AI-03 | Provisioned-throughput commitments vs deployments | Mismatch | Align | R3 | L1 |
| AI-04 | **Model downshift** (smaller model for simple tasks; routing) | Task complexity metrics; quality evaluations | Route | R1 | L1 |
| AI-05 | Batch processing for non-urgent work | Latency tolerance | Move to batch | R1 | L2 |
| AI-06 | Prompt caching and prefix reuse | Repeated prefixes | Enable/design | R1 | L1 |
| AI-07 | Verbose prompts, outputs, retry storms | Token statistics | Prompt/code pull request | R1 | L1 |
| AI-08 | Duplicate embeddings and recomputation | Duplicates | Cache | R1 | L1 |
| AI-09 | **Runaway agent loops** | Tokens per session; repeated tool calls | Circuit breaker (cost brake) | R1 | L4 |
| AI-10 | Idle GPU virtual machines | GPU utilisation near zero | Deallocate | R1 | L2 |
| AI-11 | ML compute clusters with non-zero minimum nodes | Node utilisation | Set minimum to zero | R1 | L3 |
| AI-12 | Sprawl of model deployments across projects | Requests per deployment | Retire | R2 | L2 |
| AI-13 | Data-zone vs global deployment pricing | Residency need | Re-deploy | R2 | L1 |
| AI-14 | Commitment tiers for speech, vision, document services | Volume | Commitment tier | R1 | L2 |
| AI-15 | Evaluation and benchmark jobs left running | Job history | Time-to-live | R1 | L3 |
| AI-16 | Token showback per agent, app and user | Tokens by caller | Allocate | — | L1 |
| AI-17 | Copilot-style message-pack capacity vs use | Consumption | Adjust | R1 | L1 |
| AI-18 | Redundant tool calls in agent traces | Trace analysis | Prompt/tool pull request | R1 | L1 |
| AI-19 | Vector-store quantisation and dimension choices | Index stats; quality evaluation | Tune | R2 | L1 |
| AI-20 | **The crew's own cost** (FinOps for the agents) | € per case; ROI | Route models, cache, cut off | R1 | L2 |
| AI-21 | **Anti-pattern guard:** scheduling provisioned throughput up and down hourly (Microsoft advises against; it cannot be paused) | Deployment churn vs billing | Prefer pay-as-you-go for spiky load; right-size steady load | — | L1 |
| AI-22 | One-way tier choices in AI services (a serverless developer tier cannot be changed back) | Tier chosen at creation | Coach at creation time | — | L1 |
| AI-23 | Legacy commitment models no longer sold to new customers | Commitment type | Plan migration | R2 | L1 |

---

## 12. ANOM — Anomaly and incident

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| ANOM-01 | Cost-spike root cause ("what changed?") | Cost delta × deployment/scale/traffic history | Explain and act | — | L1 |
| ANOM-02 | Runaway scale-out | Instance counts; autoscale events | Cap or brake | R1 | L4 |
| ANOM-03 | Egress spikes as exfiltration signal | Bytes out by destination | Alert SOC; restrict | R1 | L1 ⚑ |
| ANOM-04 | Compute in unusual regions/subscriptions (mining pattern) | New SKUs/regions | Alert; quarantine | R1 | L1 ⚑ |
| ANOM-05 | Forgotten load or stress tests | CPU/traffic spike pattern | Stop | R1 | L2 |
| ANOM-06 | Log-volume spike from a new deployment | Ingestion delta by source | Fix at source | R1 | L2 |
| ANOM-07 | Anomaly dialogue ("expected?") | Owner reply | Label to train baselines | — | L1 |
| ANOM-08 | Retry storms inflating PaaS call costs | Error and retry rates | Fix | R1 | L1 |

---

## 13. FORE — Forecast and budget

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| FORE-01 | Mid-month burn-rate conversations | Forecast vs budget | Dialogue | — | L1 |
| FORE-02 | Owner-level budgets (not only subscription budgets) | Ownership coverage | Create budgets with owners | R0 | L3 |
| FORE-03 | Commitment burn-down forecast | Consumption vs commitment | Advise | — | L1 |
| FORE-04 | What-if scenarios for policies and purchases | Simulation | Advise | — | L1 |
| FORE-05 | Year-end true-up and prepayment planning | Forecast | Advise | — | L1 |
| FORE-06 | Unit-cost trend alerts (cost per unit) | Unit definition | Alert | — | L1 |
| FORE-07 | Seasonality-aware forecasts and pre-buys | History | Advise | — | L1 |
| FORE-08 | Forecast-accuracy scorecards per team | Forecast vs actual | Coach | — | L1 |

---

## 14. COMM — Contracts and commercial

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| COMM-01 | Renewal evidence packs | Consumption history and forecast | Prepare | — | L1 |
| COMM-02 | Effective price vs price-sheet drift | Billing vs price sheet | Inform | — | L1 |
| COMM-03 | Marketplace private offers and commitments usage | Usage | Advise | — | L1 |
| COMM-04 | Support-contract fit | Ticket history | Advise | — | L1 |
| COMM-05 | Partner/reseller margin review | Invoices | Advise | — | L1 |
| COMM-06 | Billing-structure hygiene (invoice sections ↔ organisation) | Mapping gaps | Fix | R2 | L1 |
| COMM-07 | Credit and sponsorship expiry | Balance and expiry | Use before expiry | — | L1 |
| COMM-08 | Licence true-up readiness (benefit entitlements) | Entitlement vs deployment | Advise | — | L1 |

---

## 15. GOV — Governance hygiene

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| GOV-01 | Missing or invalid owner tags | Owner Graph vs tags | Propose, confirm, write tag | R0 | L2→L4 |
| GOV-02 | Tag drift (tag disagrees with evidence) | Evidence vs tag | Open case | R0 | L2 |
| GOV-03 | Tag-inheritance and allocation-rule gaps | Untagged cost share | Fix rules | R0 | L2 |
| GOV-04 | Subscription sprawl | Subscriptions with no owner or activity | Consolidate/close | R2 | L2 |
| GOV-05 | Exceptions without expiry | Exception registry | Add expiry; re-ask | R0 | L3 |
| GOV-06 | Locks protecting unused waste | Lock plus zero usage | Ask owner to lift | R1 | L1 |
| GOV-07 | Preventive policy for allowed SKUs and regions | Recurring waste pattern | Propose policy | R1 | L1 |
| GOV-08 | Budget/anomaly alerts without reachable owners | Alert recipients vs directory | Fix recipients | R0 | L3 |
| GOV-09 | Role assignments held by leavers; ghost owners | Directory lifecycle | Ownership review | R1 | L2 |
| GOV-10 | Management-group structure misaligned to cost ownership | Allocation gaps | Advise | — | L1 |
| GOV-11 | Dev/test guardrail policies (deny premium SKUs in dev) | SKU usage in dev | Propose policy | R1 | L1 |
| GOV-12 | Expiry tags for temporary resources | Temporary by name/purpose | Add expiry | R0 | L3 |
| GOV-13 | **One-way-door settings** (choices that cannot be changed after creation: some backup redundancies, zone redundancy on certain environments, some tiers) | Setting chosen at creation vs workload criticality | **Coach at creation time**; policy to warn | — | L1 |
| GOV-14 | Tags apply only going forward in cost data (retro-tagging does not restate history) | Untagged historical cost share | Allocation rules for history; tag at creation | R0 | L2 |
| GOV-15 | "Archived" resource groups of finished projects that were never deleted | Resource group with project closed but resources running | Ownership review, then retire | R2 | L2 |

---

## 16. SUST — Sustainability crossover

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| SUST-01 | Right-sizing with an emissions delta in every case | Estimated emissions | Report | — | L1 |
| SUST-02 | Carbon-aware placement of flexible batch work | Region carbon intensity | Re-place | R1 | L1 |
| SUST-03 | Idle-resource emissions reporting | Idle inventory | Report | — | L1 |
| SUST-04 | Efficiency-first SKU selection (newer, ARM) | Price-performance | Advise | — | L1 |
| SUST-05 | Carbon-aware scheduling for deferrable jobs | Job flexibility | Schedule | R1 | L2 |

---

## 17. ADJ — Adjacent spend (horizon 3+; decision D8)

| ID | Opportunity | Usage-truth signal | Action | Rev | Ceil |
|---|---|---|---|---|---|
| ADJ-01 | Inactive AI-assistant seats for developers | Seat activity | Reclaim | R1 | L2 |
| ADJ-02 | CI minutes and runner configuration | Usage | Optimise | R1 | L1 |
| ADJ-03 | Inactive productivity-suite and assistant licences | Activity | Reclaim | R1 | L2 |
| ADJ-04 | Low-code platform capacity add-ons and premium licences | Utilisation | Adjust | R1 | L1 |
| ADJ-05 | Dataverse storage and audit-log growth | Growth | Tune | R2 | L1 |
| ADJ-06 | Premium collaboration licences unused | Activity | Reclaim | R1 | L2 |
| ADJ-07 | BI licence mix (per-user vs capacity) | Usage | Re-mix | R1 | L1 |
| ADJ-08 | Developer-service users and parallel-job entitlements unused | Activity | Reclaim | R1 | L2 |

---

## Appendix A — Evidence map

*Built from [research/01](../research/01-azure-native-landscape.md), [04](../research/04-seed-example-facts.md) and [05](../research/05-cost-traps-and-dark-spend.md) (retrieved 2026-10-30). **Any ID not listed here is still a pure hypothesis.** "Status" is the research agents' own tag (Verified = primary source read; Partial = secondary or inferred; Unverified = mechanism well known but not re-checked).*

| Catalog IDs | Research evidence | Status | Nuance the playbook must respect |
|---|---|---|---|
| IDLE-01, 02, 03, 20 | TRAP-ORPH-001/002/003, TRAP-STOP-002/003 | Partial / Unverified | Snapshot lineage; **releasing a static public IP loses the address** (R3) |
| IDLE-04 | TRAP-ORPH-004, TRAP-NET-001 | Verified | NAT gateway has **no stopped state** — only deletion stops billing |
| IDLE-05, 06, SIZE-11 | TRAP-ORPH-005/006, TRAP-NET-007 | Partial / Verified | Application Gateway v2 bills a fixed rate plus capacity units even at zero traffic |
| IDLE-07 | TRAP-ORPH-007 | Verified | Private endpoints outlive the target resource |
| IDLE-08, 09, 10 | TRAP-ORPH-008/011, TRAP-NET-003/010 | Verified / Partial | An ExpressRoute gateway **keeps billing after the circuit is deleted**; firewalls carry a fixed hourly charge |
| IDLE-12, SEC-05 | TRAP-NET-008 | Verified | DDoS plan is a flat recurring fee |
| IDLE-13 | TRAP-APP-009 | Partial | Empty dedicated plan bills as if populated |
| IDLE-15, 16, SIZE-26, 35 | TRAP-APP-001/004/005/006/007, research/04 Part C | Verified | Premium plans always bill ≥1 instance; "always ready" has no free grants; replicas bill an **idle rate**, not zero; some profiles never scale to zero |
| IDLE-17, 40 | TRAP-STOP-004, TRAP-PLAT-001/002/003 | Verified / Partial | The node resource group is **protected by a system deny assignment** → **fix at source** (cluster owner), not a direct delete |
| IDLE-18, 19 | TRAP-STOP-001 | Partial | "Stopped" is not "deallocated" |
| IDLE-21, SIZE-06/07/28 | TRAP-STOP-007, TRAP-DB-006/007/009 | Partial / Unverified | Provisioned tiers bill 24/7 |
| IDLE-27, SIZE-34, TIME-08 | TRAP-STOP-005, TRAP-PLAT-004/005, TRAP-DATA-004/005 | Verified / Partial | Terminated clusters still bill residual storage; "min idle" pool instances bill |
| IDLE-30, 38 | TRAP-ORPH-010, TRAP-BAK-001/002/003/004 | Verified | *Stop and retain* keeps billing indefinitely; soft-delete is free only for the first window; a vault with soft-deleted items cannot be deleted |
| IDLE-31 | TRAP-ORPH-009 | Unverified | Capacity reservations bill whether or not used |
| IDLE-34, 36, AI-11 | TRAP-AI-006/007/008 | Verified | Minimum nodes bill; **idle shutdown can silently fail** (missing permission, "active" process) |
| IDLE-37, SIZE-14 | TRAP-PLAT-008, TRAP-NET-006; research/04 | Verified | Fixed hub router fee regardless of traffic (West Europe list ≈ €0.22/hour per hub unit, Retail Prices API) |
| IDLE-39 | TRAP-OBS-003 | Verified | Deprecated test type keeps billing |
| SIZE-01 | research/01 §2 | Verified | Advisor's VM algorithm uses **retail rates and ignores commitment coverage**; cross-series resize can raise effective cost |
| SIZE-08, 09, 33 | TRAP-DB-001/002/003 | Verified / Partial | Throughput billed at the **hourly peak**; default indexing indexes everything |
| **SIZE-12, 13, 14** ★ | research/04 Part B/C | **Verified** | P2S: 1–200 scale units (~500 users and 500 Mbps each); scaling may reconnect users; meter "VPN P2S Scale Unit" |
| SIZE-16–21 | research/04 Part C; TRAP-DATA-012/014, TRAP-APP-010, TRAP-AI-003/004, TRAP-STOR-005 | Verified / Partial / Unverified | Event Hubs auto-inflate scales **up only**; search cost is **replicas × partitions** (multiplicative) and scale-in is disruptive; messaging units bill at the **peak in the hour** |
| TIME-01 | research/01 §5 | Verified | Start/Stop VMs v2 (Functions-based) replaced v1; native auto-shutdown has no start schedule |
| TIME-04, DATA-26 | TRAP-DATA-007/008/009/010 | Verified | **Pausing a capacity stops compute but not storage and can settle accumulated overage immediately** |
| TIME-07 | TRAP-DB-008 | Partial | Auto-pause delay often set too long |
| RATE-01–06, 21–23 | research/01 §5; TRAP-COMMIT-001/002/003/004 | Verified | Priced as if used 100% of the term; scope matters; size flexibility only within a family; **exchange policy is time-limited ("until further notice")**, refunds capped (USD 50,000 per rolling 12 months), owner-only |
| RATE-07, 08, 09 | research/01 §5; TRAP-COMMIT-005/006 | Verified (mechanics) | Hybrid Benefit needs eligible licences; Dev/Test needs Visual Studio subscriptions |
| RATE-12, 13 | TRAP-COMMIT-009/010 | Unverified | Marketplace auto-renew; MACC tracked at billing-account level |
| RATE-17, 25, SEC-04, 11 | research/04 A.1; TRAP-SEC-005/006/007 | Verified | Commitment tiers start at 100 GB/day, 31-day lock; SIEM bills **all** data analysed on the workspace |
| RATE-19, SEC-01–03, 12, 13 | TRAP-SEC-001/002/003/008, TRAP-STOR-009, TRAP-PLAT-009 | Verified / Partial | Legacy per-transaction storage plan is retired for new enablement; malware scanning has a default monthly per-account cap |
| **TELE-01, 02, 03** ★ | research/04 A.2–A.4 | **Verified** | Query audit **off by default**, excludes scheduled/hunting; **no native "never queried" signal**; row filters and column drops supported |
| TELE-06, 09 | research/04 A.1 | Verified | Plan switch once per table per week; **simple log-search alerts work on Basic; alerts stop on Auxiliary** |
| TELE-11, 12, 13, 17, 18, 20, 22, 31 | research/04 A.3/A.5; TRAP-OBS-001/004/005 | Verified / Partial | Cost presets for container monitoring; sampling; Windows event tiers; **Prometheus ingestion limits throttle silently** |
| TELE-14, 15 | TRAP-OBS-002/003 | Verified | Log alerts at scale bill per **time series** |
| TELE-05, 24, 25 | research/04 A.5 | Partial | Duplicates via multiple diagnostic settings |
| TELE-21, 32, NET-16 | research/04 A.5; TRAP-OBS-007 | Verified / Unverified | Legacy flow logs **retire 30 Sep 2027**; parallel running doubles records and storage |
| DATA-01–05, 07, 08, 10, 27–29 | TRAP-STOR-001…011 | Verified / Partial / Unverified | **Enabling SFTP adds a flat hourly charge for as long as it is enabled**; versioning, soft-delete and snapshots each retain full-priced copies; defaults to geo-redundancy |
| DATA-12, 13, 24 | TRAP-DB-004/005, TRAP-BAK-005, TRAP-REGION-004 | Verified | Default geo-redundant backups cost roughly **double** local; some redundancy choices are **fixed at creation** |
| DATA-16–20 | TRAP-DATA-001/002/003/004/011/013 | Verified / Unverified | Data-flow debug sessions and runtime TTL bill while idle |
| NET-01–07, 14 | TRAP-NET-003/004/009/011/012/014, TRAP-REGION-003 | Verified / Partial | Private Link bills endpoint-hours, data processing and cross-region; Premium downgrade is blocked above a linked-network limit |
| PLAT-06, 07, 10 | TRAP-APP-001/004/011/012, TRAP-NET-012, TRAP-COMMIT-008 | Verified / Unverified | Polling triggers billed per poll (unverified); retiring Basic SKUs; legacy commitment model |
| AI-02, 03, 21, 23 | research/04 Part C; TRAP-STOP-006, TRAP-AI-001/002, TRAP-COMMIT-007/008 | Verified | Provisioned throughput **cannot be paused**; Microsoft advises against hourly scaling |
| AI-09 | TRAP-AI-010 | Unverified | Runaway loops |
| AI-12 | TRAP-AI-009 | Partial | Deployment sprawl |
| AI-22 | TRAP-AI-005 | Verified | One-way developer-tier choice |
| GOV-01, 04, 15 | TRAP-FINOPS-001/002/003 | Unverified | Untagged, sprawl, archived-in-name |
| GOV-07, 11 | research/01 §5 | Verified | Policy effects (deny/modify/audit/…) for preventive guardrails |
| GOV-08 | research/01 §1 | Verified | Budget action groups work **only at subscription and resource-group scope** |
| GOV-14 | TRAP-FINOPS-006; research/01 §1 | Verified | Tag inheritance applies to **usage records going forward** |
| ANOM-01, 07, FORE-* | research/01 §1 | Verified | Cost anomaly alerts use a 60-day baseline and are **email-only** |
| AI-01 | Learn: Azure OpenAI *manage costs* (full billing model), *fine-tuning how-to* and *FAQ* (retrieved 2026-10-30) | Verified | Hourly hosting regardless of usage; **auto-deleted after 15 days with no calls**; deleting a deployment does not delete the model |
| COMM-*, ADJ-*, SUST-*, most of DEV-* and TIME-02…12 | — | **Hypothesis** | Not yet sourced; verify in Phase 3 when selected for a playbook |

## Appendix B — How the catalog becomes playbooks (Phase 3)

Score each entry on **value × signal availability × reversibility × owner clarity × safety**, select 8–12 for the first release, and write each as a playbook spec (signals, evidence, counter-evidence, options, risks, verification, test data). The two seed examples (**SIZE-12**, **TELE-01/02/03**) are first; **IDLE-01**, **TIME-01** and **GOV-01** are natural companions because they are safe, reversible and prove the ownership loop.
