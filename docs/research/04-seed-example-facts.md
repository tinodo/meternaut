# Research 04 — Seed-Example Facts: Log Analytics ingestion usefulness & Virtual WAN P2S gateways

> **Status:** research report v1 · **Retrieved:** 2026-10-30 · **Produced by:** research agent (desk research), spot-checked by the orchestrator (see *Orchestrator addendum*)
> Status tags: **Verified** = primary source read; **Partially verified** = source has caveats or is secondary; **Unverified** = not independently confirmed. Paths below are `learn.microsoft.com/...` unless stated.
> Used by: [03 — deep dives](../ideation/03-deep-dives-seed-examples.md), [02 — catalog](../ideation/02-opportunity-catalog.md) (TELE-*, SIZE-12/13/14).

---

## PART A — Log Analytics / Azure Monitor ingestion usefulness

### A.1 Cost-model structure

| Dimension | Analytics Logs | Basic Logs | Auxiliary Logs (incl. Sentinel data lake) |
|---|---|---|---|
| Ingestion | Per-GB standard rate; includes 30 days analytics retention (90 for Sentinel/App Insights) | Per-GB, reduced flat rate | Per-GB, lowest flat rate; billed size = **uncompressed** column size |
| Query | Interactive queries not charged by data scanned (within analytics retention) | Billed per GB scanned in the query time range | Billed per GB scanned |
| Commitment tiers | Yes, from 100 GB/day, up to ~30% discount vs pay-as-you-go, 31-day commitment lock, overage billed at tier rate | **No** | **No** |
| Retention | 30/90 days hot, extendable to 2 years, then long-term retention (rate identical across plans) | No analytics retention; total up to 12 years | No analytics retention; total up to 12 years |
| Feature support | Full: alerts, search jobs, restore, workspace replication, summary rules | Search jobs, summary rules (single-table KQL), restore, replication; **simple log search alerts are supported** (orchestrator-verified) | Search jobs, summary rules (single-table); **no restore, no replication; alerts stop working** if a table is moved here |
| Plan switching | 1 switch per table per week | same | same |

*Verified:* `azure-monitor/logs/cost-logs` (#table-plans, #commitment-tiers, #log-data-retention), `.../logs/data-platform-logs#table-plans`, `.../logs/logs-table-plans#change-the-table-plan`.

- **Dedicated clusters:** ADX-cluster-backed, minimum commitment 100 GB/day, **no pay-as-you-go option**, two billing modes (cluster vs workspaces-proportional). *Verified* — `cost-logs#dedicated-clusters`.
- **Microsoft Sentinel data-lake tier:** separate meters for ingestion, data processing (supports redaction/splitting/filtering/normalisation), storage (6:1 compression assumption), query (per-GB uncompressed scanned), and advanced data insights (compute-hour notebook pools). *Verified* — `azure/sentinel/billing#data-lake-tier`, `sentinel/manage-data-overview`.
- **Search jobs:** on the Analytics plan only data in *long-term retention* is billed to scan; on Basic/Auxiliary all data in the queried range is billed. *Verified* — `cost-logs#search-jobs`.

### A.2 Measuring ingestion, and learning what is actually *used*

| Signal | Mechanism | What it tells you | Observable by default? |
|---|---|---|---|
| **Usage** table | KQL table; `DataType`, `IsBillable`, `Quantity` (MB), `MeterId`, `Plan`, `Solution` | Per-table billed volume, hourly granularity | Yes |
| `_BilledSize` / `_IsBillable` columns | On every ingested record | Per-record billed bytes | Yes |
| `_ResourceId` / `_SubscriptionId` columns | On Azure-resource records | Attribute ingestion to resource/subscription/resource group — but cross-table attribution needs expensive `find`/`union` queries | Yes |
| **LAQueryLogs** (query audit) | A **diagnostic setting on the workspace**, category "Audit" | Who (identity), which tool, when, exact KQL, CPU time | **No — off by default** |
| Workspace Insights → Query Audit tab | Built on LAQueryLogs | Duration/rows percentiles; slow/inefficient queries | Only if LAQueryLogs is enabled |
| Scheduled query rules / Sentinel analytics & hunting rules | Rule definitions embed KQL | Confirms a table feeds alerting/hunting | **No built-in cross-reference report found** — must be reconstructed from rule definitions |
| Data-export rules | Up to 10 active rules per workspace; Analytics and Basic tables only, **not Auxiliary** | Confirms external consumption | Yes (rule exists or not) |
| Logs Ingestion / Query API consumers | Programmatic callers | Visible in LAQueryLogs (`AADClientId`, `RequestClientApp`) only if audit is enabled | No, unless audit enabled |
| Workbooks / Grafana / Power BI | Basic and Auxiliary support Workbooks and Grafana; Azure Monitor Dashboards are not supported on those plans; **Power BI cannot query Basic/Auxiliary tables** | — | Power BI access impossible on Basic/Auxiliary by design |

*Verified:* `logs/analyze-usage`, `logs/log-standard-columns`, `logs/query-audit`, `sentinel/audit-sentinel-data#auditing-with-laquerylogs`, `logs/log-analytics-workspace-insights-overview`, `logs/logs-data-export#considerations`, `logs/data-platform-logs#table-plans`, `logs/basic-logs-query`.

**Explicitly *not* observable:**
- Ad-hoc portal Logs-blade browsing **before** query auditing is enabled — nothing is recorded. *Verified.*
- LAQueryLogs does **not** log service-to-service executions — in particular **scheduled alert/analytic rule runs** are not recorded — so "query auditing shows zero hits" never means "nothing uses this data". *Verified* — `azure-monitor/logs/query-audit` ("the system logs queries only when you execute them in a user context … it doesn't log alert queries triggered on a schedule"). **Coverage of interactive Sentinel/Defender experiences is documented inconsistently** (corrected after review): the Azure Monitor audit page lists `ASI_Portal`, `Sentinel-Investigation-Queries`, `Sentinel-analyticsManagement-customerQuery` and `M365D_AdvancedHunting` as request client apps, while the Sentinel audit page says LAQueryLogs "does not include the queries run by scheduled analytics rules, using the Investigation Graph, in the Microsoft Sentinel Hunting page, or in the Defender portal's Advanced hunting page" (`sentinel/audit-sentinel-data#auditing-with-laquerylogs`). **Treat the blind-spot list as something to measure per workspace** (run a canary query through each surface and look for it), never as a fixed list.
- **Does anything flag a table/pattern as never used?** *Corrected after review.* **Advisor's four documented Log Analytics cost recommendations and Azure Copilot for Cost Management do not.** But **Microsoft Sentinel SOC optimization does, for Sentinel workspaces**: "data value optimizations only look at billable tables that ingested data in the past **30 days**"; observations include *the table wasn't used at all in the last 30 days* and *the table wasn't used by analytics rules but was used by workbooks/log queries/hunting queries*, with suggested actions (analytics rule templates, Basic plan, stop ingestion, long-term retention); plus **unused columns (Preview)**. It is **security-scoped, Sentinel-only and 30-day**; nothing equivalent was found for Azure Monitor-only workspaces. *Verified* — `azure/sentinel/soc-optimization/soc-optimization-reference` (retrieved 2026-10-30).

### A.3 DCR transformations and volume-reduction levers

| Capability | Detail | Status |
|---|---|---|
| Filter rows | `source \| where condition` in transform KQL | Verified (`data-collection-transformations-samples`) |
| Drop columns | `project-away` / explicit `project` | Verified |
| Supported tables | Tables flagged "DCR transformations" in the table-features reference; any custom AMA table; custom Auxiliary-plan tables | Verified (`data-collection-transformations`) |
| Workspace transformation DCR | **Exactly one per workspace**, covers any number of standard tables; ~60 minutes to activate a new query | Verified (`data-collection-transformations-create`) |
| Sentinel filter/split (no DCR) | Filter: any DCR-supported table. Split: only Analytics-tier tables onboarded to the Sentinel data lake | Verified (`sentinel/transformation-filter-split`) |
| Container Insights cost presets | **Logs and Events** (default, 1 min) · **Syslog** (1 min) · **Standard** (1 min, all tables) · **Cost-optimized** (5 min, excludes `kube-system`, `gatekeeper-system`, `azure-arc` namespaces) | Verified (`containers/kubernetes-monitoring-enable`, `container-insights-cost`) |
| Application Insights sampling | Adaptive sampling default for ASP.NET/ASP.NET Core/Functions server-side; Java agent supports sampling overrides to suppress health-check telemetry and disable `traces`/`dependencies` auto-instrumentation | Verified (`app/sampling`, `troubleshoot-high-data-ingestion`, `app/java-standalone-sampling-overrides`) |
| Windows Event collection tiers | **All** / **Common** (full audit trail incl. 4634 sign-out) / **Minimal** (breach-indicator events only; excludes 4634 as high-volume, low-value for breach detection) / **Custom** (XPath) | Verified (`sentinel/windows-security-event-id-reference`) |
| Syslog | DCR `facilityNames` + `logLevels` filters at the agent | Verified (`data-collection-rule-samples`) |
| Diagnostic-setting category groups | `audit` vs `allLogs` groupings exist for selecting categories wholesale | Partially verified (seen on one product's doc) |

### A.4 Microsoft's own guidance and tools

| Tool | Function | Flags unused tables? |
|---|---|---|
| **Cost optimization in Azure Monitor** (`fundamentals/best-practices-cost`) | Checklist: Basic Logs for debug/audit tables, limit collection at source, retention/archive, daily cap as a *backstop only*, Advisor alerts | No |
| **Analyze usage in a Log Analytics workspace** | KQL recipes on `Usage`/`_BilledSize`; Power BI with incremental refresh for trends | No (volume trend only) |
| **Log Analytics Workspace Insights** | Ingestion by table/solution/computer, anomaly and upward-trend detection, Query Audit tab | No |
| **Azure Advisor — four documented LA cost recommendations** | (1) Consider the Basic plan (>1 GB/month to Basic-eligible tables); (2) Consider changing pricing tier; (3) Consider removing unused *restored* tables; (4) Data-ingestion anomaly detected | **No** |
| **Microsoft Sentinel SOC optimization** (added after review) | *Data value* recommendations for **Sentinel workspaces**: billable tables ingested in the past 30 days that were unused by analytics rules and/or unused altogether → analytics templates, Basic plan, stop ingestion, long-term retention; unused columns (Preview) | **Yes — but security-scoped, Sentinel-only, 30-day window** |
| **Azure Copilot (Cost Management)** | Natural-language cost Q&A, recommendations, breakdowns, forecasting, token what-if | General; not table-specific |
| **Export job (preview)** | One-time bulk Parquet export to Blob | N/A |

*Verified:* `fundamentals/best-practices-cost#azure-monitor-logs-cost-optimization`, `logs/analyze-usage`, `logs/log-analytics-workspace-insights-overview`, `logs/best-practices-logs#cost-optimization`, `copilot/analyze-cost-management`.

### A.5 Notoriously high-volume, low-value sources

| Source / pattern | Why | Status |
|---|---|---|
| **AzureDiagnostics** (shared table for Firewall, App Gateway, Storage, Key Vault …) | Schema-less multi-resource table; per-resource analysis requires parsing `ResourceProvider`/`ResourceId` | Verified (`reference/queries/azurediagnostics`) |
| **ContainerLogV2** | Captures all stdout/stderr, incl. health-probe/debug prints, unless namespace- or annotation-filtered | Verified (`container-insights-cost`) |
| **AppTraces / dependencies** (App Insights) | Default log level + full dependency auto-instrumentation; Microsoft maintains a dedicated "troubleshoot high data ingestion" doc | Verified |
| **Perf** | Per-counter/instance/interval rows; VM Insights adds extra default counters | Verified (`analyze-usage`, `vm/best-practices-vm#cost-optimization`) |
| **Syslog** | Facility × severity cross-product incl. debug/info noise | Verified |
| **Windows Security events (All/Common)** | "Common" ships high-volume sign-out (4634) events to preserve a full audit trail even though "Minimal" shows it is not needed for breach detection | Verified |
| **VM Insights Map** (process/dependency data) | Microsoft's VM best-practices says disable process/dependency collection if the Map feature is unused | Verified |
| **NSG flow logs + Traffic Analytics / VNet flow logs** | **NSG flow logs retire 30-Sep-2027** (no new creation after 30-Jun-2025); running NSG and VNet flow logs in parallel causes duplicate records and doubled storage cost | Verified (`plan-for-traffic-inspection`, `network-watcher/nsg-flow-logs-migrate`) |
| **AzureMetrics** (platform metrics replicated into Logs) | Metrics are already native in Azure Monitor Metrics; routing them into Logs is a billed duplicate | Partially verified |
| **Activity-log fan-out to several workspaces** | Multiple diagnostic settings can each target a different workspace, duplicating records | Partially verified / inferred |

### A.6 Prior art — AI/ML-based log-noise detection (Grafana Adaptive Logs)

Grafana Cloud **Adaptive Logs**: (1) cluster incoming logs into structural patterns, (2) check which patterns were actually **queried in the trailing 15 days**, (3) recommend a per-pattern **drop percentage** for rarely/never-queried patterns, (4) let the user **review, adjust or exempt** patterns before anything is dropped, (5) continuously re-evaluate. The mitigation for "accidentally dropped something rare-but-critical" is **step 4 — human review and permanent exemptions** rather than autonomous deletion. *Verified* — Grafana docs/blog (retrieved via web search, 2026-10-30).

---

## PART B — Virtual WAN point-to-site (User VPN) gateway

| Attribute | Finding | Status |
|---|---|---|
| Resource type | `microsoft.network/p2svpngateways` — a **distinct ARM resource**, separate from S2S/ExpressRoute vWAN gateways and classic VPN gateways | Verified (`monitor-virtual-wan-reference`) |
| Where it lives | Deployed **inside the Virtual WAN virtual hub** (a Microsoft-managed virtual network); not a standalone customer-visible object like a classic VPN gateway | Verified (`point-to-site-concepts`, `hub-settings`) |
| Scale-unit definition | **1–200 scale units**; throughput is linear at **0.5 Gbps per unit**, but **concurrent-connection capacity is banded, not linear** (corrected after review): units **1–3 → 500** connections, **4–6 → 1,000**, **7–10 → 5,000**, **11–20 → 10,000**; above 20, one more pair of gateway instances per extra 20 units adds 10,000 (40 → 20,000; 100 → 50,000; 200 → 100,000). Gateway instances: **2 up to 20 units**, then +2 per additional 20 (100 units → 10 instances). Instances may be serviced, so plan to the table value, **not** to twice it. | **Verified** (`virtual-wan-faq#for-user-vpn-point-to-site--how-many-clients-are-supported` — table read in full by the orchestrator; `point-to-site-concepts`: "1–200 scale units, supporting 500 to 100,000 users per gateway") |
| Pricing structure | Billed **per scale-unit hour** plus a per-connection-unit hour meter. Meter names **confirmed by the orchestrator** via the public Azure Retail Prices API (see addendum): **"VPN P2S Scale Unit"** and **"VPN P2S Connection Unit"** | **Verified** (addendum) |
| Metrics | **Gateway P2S Bandwidth** (`P2SBandwidth`, BytesPerSecond, Average, dim `Instance`); **P2S Connection Count** (`P2SConnectionCount`, Count, Total, dims `Protocol` + `Instance`); **User Vpn Route Count** (`UserVpnRouteCount`, Count, dims `RouteType` + `Instance`) | Verified (`monitor-virtual-wan-reference#metrics`) |
| Diagnostic logs | `GatewayDiagnosticLog`, `IKEDiagnosticLog`, `P2SDiagnosticLog` land in the shared **AzureDiagnostics** table; reference marks **Basic plan: No** and **ingestion-time transformation: No** for all three | Verified |
| How scaling is changed | Portal (hub → "Point to site"), PowerShell/CLI, REST | Verified (`gateway-settings`) |
| Does scaling disrupt users? | **Yes, explicitly.** FAQ: *"be sure to plan for downtime in case you decide to scale up or down on the scale unit"*; *"you may experience TCP reconnects during the scale unit change"* | Verified (`virtual-wan-faq`) |
| Right-sizing guidance | Microsoft's monitoring best practice: alert on **Gateway P2S Bandwidth** nearing aggregate throughput (e.g. 2 su = 1 Gbps → alert at 950 Mbps) and on **P2S connection count** nearing the scale-unit limit | Verified (`monitor-virtual-wan#monitoring-azure-virtual-wan---best-practices`) |

### Other Virtual WAN cost components that scale "invisibly"

| Component | Scale concept | Key facts | Status |
|---|---|---|---|
| S2S VPN gateway | Scale units; **1 su = 500 Mbps**; 2 instances per unit (active-active) | Hub supports up to 1,000 connections / 2,000 IPsec tunnels | Verified |
| ExpressRoute gateway (in-hub) | Scale units; **1 su = 2 Gbps** | Separate from the standalone ER VNet gateway | Verified |
| Hub routing infrastructure units (RIUs) | Default **2 RIU = 3 Gbps / 2,000 VMs**; each extra RIU = +1 Gbps / +1,000 VMs | Hard cap 10,000 routes; single-TCP-flow degradation above ~1.5 Gbps | Verified |
| Hub autoscale | Scales RIUs between configured minimum and traffic need | Won't go below configured minimum; scale-out up to ~25 minutes | Verified |
| Secured-hub Azure Firewall | **Capacity Units**, autoscale 2–50 (prescaling) | "Capacity Unit Hour" meter on top of base firewall charge; billable count excludes the 2 default instances | Verified (`firewall/prescaling`) |

---

## PART C — The general pattern: provisioned capacity vs actual use

*25 of 27 rows independently sourced; 2 flagged Unverified / weak fit.*

| # | Resource | Capacity unit | "Used" metric(s) | Cost exposure | Scaling: online or disruptive | Status |
|---|---|---|---|---|---|---|
| 1 | Application Gateway v2 / WAF v2 | Capacity Unit (2,500 persistent connections + 1 GB/hr throughput + 1 compute unit); min/max instance count | `CurrentCapacityUnits`, `CapacityUnits`, `ComputeUnits`, Estimated Billed CU | Fixed hourly + CU consumption; min instance reserves 10 CU/instance even if idle | Online scale-out (3–5 min); max-decrease only after a scale-in event | Verified |
| 2 | ExpressRoute gateway (standalone, scalable) | Scale units 1–40, 1 Gbps/unit | `ExpressRouteGatewayCpuUtilization`, `ScalableExpressRouteGatewayScaleUnit`, … | Per scale-unit hour | Scale change up to 30 min; possible TCP reconnects | Verified |
| 3 | VPN Gateway, standalone (SKU-based) | SKU tier (Basic…VpnGw5) | Not re-verified | SKU-hour | Resize needs SKU-family match or recreate | **Unverified** |
| 4 | **vWAN P2S gateway** | Scale units 1–200 | `P2SBandwidth`, `P2SConnectionCount`, `UserVpnRouteCount` | Scale-unit hour | Explicit downtime risk | Verified |
| 5 | vWAN S2S gateway | Scale units, 500 Mbps/unit | Gateway bandwidth/tunnel metrics | Scale-unit hour | Scale change can disrupt | Verified |
| 6 | vWAN ExpressRoute gateway | Scale units, 2 Gbps/unit | — | Scale-unit hour | TCP reconnects possible | Verified |
| 7 | vWAN hub routing infrastructure units | RIUs | Hub router traffic-processed metrics | Hub-hour by RIU | Autoscale; ≤25 min; never below configured minimum | Verified |
| 8 | Secured-hub Azure Firewall | Capacity Units 2–50 | `Observed Capacity` | Capacity-Unit-Hour meter on top of base fee | Autoscale 5–7 min out; scale-in below 20% utilisation | Verified |
| 9 | Event Hubs Standard | Throughput Units 1–40/namespace | `IncomingMessages`, `ThrottledRequests`, `IncomingBytes` | Hourly at **peak TU reached in the hour** | Online; **auto-inflate is scale-up only** | Verified |
| 10 | Event Hubs Premium | Processing Units 1,2,4,6,8,10,12,16 | same family | PU-hour | Online (manual) | Verified |
| 11 | Service Bus Premium | Messaging Units 1,2,4,8,16 | `NamespaceCpuUsage`, `NamespaceMemoryUsage`, `ThrottledRequests` | Hourly at **peak MU in the hour** | Online (minutes) | Verified |
| 12 | Cosmos DB | RU/s (manual or autoscale) | `Normalized RU Consumption`, `Provisioned Throughput`, `Autoscaled RU` | Hourly at peak RU/s (autoscale) or flat (manual) | Online, near-instant | Verified |
| 13 | Azure AI Search | Search Units = replicas × partitions | QPS/latency/throttled queries | Fixed (dedicated) or consumption (serverless) | Scale-out non-disruptive; **scale-in explicitly disruptive** — stop indexers first | Verified (S-tier SU cap partially verified) |
| 14 | API Management (classic tiers) | Scale units | `Capacity` | Per unit | Config changes ≥15 min; gateway stays up except Developer tier | Verified |
| 15 | Azure OpenAI | Provisioned Throughput Units (PTU) | `AzureOpenAIProvisionedManagedUtilizationV2` | Reserved PTU-hour regardless of call volume | Effectively a redeploy | Verified |
| 16 | Azure Functions Premium | Always-ready instances | Plan minimum instance count / `AlwaysReadyUnits` | Billed whether idle or active; every Premium plan has ≥1 billed instance | Online | Verified |
| 17 | Azure Functions Flex Consumption | Always-ready instances per function group | `AlwaysReadyFunctionExecutionCount`, `AlwaysReadyUnits` | "Always Ready Baseline" meter | Online | Verified |
| 18 | Azure Container Apps | Min replicas (default 0) | vCPU-seconds / GiB-seconds; idle vs active rate | Idle-rate billing applies at min-replica > 0 when traffic is very low | Online | Verified |
| 19 | AKS node pools | Cluster-autoscaler min/max nodes | `cluster_autoscaler_unschedulable_pods_count`, `…unneeded_nodes_count` | Pay for every provisioned node regardless of packing | Scale-in can disrupt workloads | Verified |
| 20 | VMSS | Autoscale min/max/default instances | `Percentage CPU` (+ network/disk) | Per running instance | Scale-in: tasks on the instance stop abruptly | Verified |
| 21 | Microsoft Fabric capacity (F-SKU) | Capacity Units | CU utilisation; interactive/background % | Per-capacity hourly regardless of idle workspaces | Autoscale-add automatic; SKU resize manual | Verified |
| 22 | Azure Data Explorer cluster | Instance count (manual/optimised/custom autoscale) | CPU, cache-utilisation factor, ingestion utilisation | Per-instance hour by SKU | Online; **cache-bound clusters can't scale in** despite low CPU | Verified |
| 23 | Synapse dedicated SQL pool | Data Warehouse Units | — (lever is pause/resume) | Compute billed only while Online | Pause/resume is the primary lever | Verified |
| 24 | Azure SignalR Service | Units (Premium autoscale) | `ConnectionQuotaUtilization`, `ServerLoad` | Per unit-hour | Autoscale 3–5 min | Verified |
| 25 | Azure Cache for Redis | Tier/shard size (no native autoscale) | `serverLoad`, `percentProcessorTime` per shard | Per tier/shard hourly | Disruption profile varies by tier | Verified (metrics); partial (disruption) |
| 26 | Azure Front Door (Std/Premium) | Mostly consumption | `RequestCount`, `OriginRequestCount`, `OriginHealthPercentage` | Pay-as-you-go — weak fit | N/A | Partial / weak fit |
| 27 | PostgreSQL / MySQL Flexible Server | vCores + storage | Not researched | — | — | **Unverified** |

---

## PART D — Implications for our idea (from the research agent)

1. Both seed examples have the same shape — a **provisioned-capacity signal** vs a **consumption signal**. Build one generic "provisioned vs used" comparator, not two bespoke detectors.
2. **"Never queried" is not a first-class Azure signal today.** The agent must synthesise it from Usage + LAQueryLogs + a rule/workbook inventory, and must first **check whether query auditing is enabled** before trusting a zero-query verdict.
3. LAQueryLogs **does not log scheduled alert/analytic rule executions** — zero interactive queries must never alone mean "safe to downgrade"; cross-check active rule table references. Coverage of Sentinel/Defender interactive surfaces is documented inconsistently: **measure it per workspace with a canary query** and treat unknown coverage as a blocking condition for destructive recommendations.
4. Table-plan changes are **rate-limited (once a week)** and **break alerting when moved to Auxiliary** — remediation must be staged (filter columns → Basic → Auxiliary) with dependency checks and a rollback window.
5. The P2S scale-unit → connections/throughput table is **public and static** (but **banded**, see Part B), so right-sizing is a deterministic **lookup** that must satisfy *both* the connection band and the bandwidth requirement plus headroom. Because scaling **may disconnect users**, treat it as a **human-approved, disruption-bearing change** — not a "low-risk automatable fix".
6. Scaling the P2S gateway **explicitly risks user-facing disruption** per Microsoft — a textbook human-in-the-loop case: show connected users, propose a window, approve in Teams, execute, re-verify with the same metric.
7. P2S diagnostic logs **cannot** use the Basic plan or DCR transformations — don't assume every log-cost lever applies to every resource; the recommendation engine needs per-table capability flags.
8. Billing-meter names for vWAN scale units must be reconciled via Cost Management / price-sheet data rather than baked into message text (now confirmed for P2S, see addendum).
9. Grafana Adaptive Logs' pattern — cluster, correlate with real trailing-window usage, recommend a drop rate, **require human review/exemption** — maps directly onto our Part-A flow.
10. Remaining gaps (Front Door fit, Redis disruption specifics, standalone VPN gateway, PostgreSQL/MySQL rows, AI Search SU cap) should become named follow-up research before any card copy asserts numbers.

---

## Orchestrator addendum (spot-checks, 2026-10-30)

| Claim checked | Result | Source |
|---|---|---|
| Are alerts supported on Basic Logs? (agent said yes; Auxiliary no) | **Confirmed.** *Simple log search alerts* are supported on Basic Logs tables; log-search alerts support Analytics and Basic; moving a table to Auxiliary/Lake means **alerts stop working for that table**. | Learn: `azure-monitor/containers/cost-effective-alerting`, `azure-monitor/alerts/alerts-types`, *Azure Monitor Logs overview — table plans* |
| P2S scale-unit capacity | **Confirmed:** "Gateway scale units can range from 1–200, supporting 500 to 100,000 users per gateway"; "1 scale unit of VPN = 500 Mbps"; scale-unit change may cause TCP reconnects; plan for downtime | Learn: `virtual-wan/point-to-site-concepts`, `virtual-wan/virtual-wan-faq`, `virtual-wan/gateway-settings` |
| P2S billing meter (agent could not confirm) | **Confirmed via the public Azure Retail Prices API** (West Europe, EUR, retail list price, retrieved 2026-10-30): meter **"VPN P2S Scale Unit"** = **€0.3177 per unit-hour** (≈ €232 per unit-month); **"VPN P2S Connection Unit"** = €0.011 per hour. Example arithmetic: **100 scale units ≈ €23.2k/month at list price**; scaling to 12 units ≈ saves ≈ €20.4k/month. Negotiated rates differ — the Economist must use the customer's price sheet, never list prices. | `https://prices.azure.com/api/retail/prices` (serviceName *Virtual WAN*, armRegionName *westeurope*) |

**Caveat for the deep dives:** prices drift and differ by agreement; every € figure in a card must come from the customer's own price data at execution time.

### Corrections made after Rubber-Duck Round 1 (2026-10-30)

| Correction | Why | Source |
|---|---|---|
| **P2S connection capacity is banded, not "≈500 per unit"** | Reviewer A (R1) challenged the linear assumption; the orchestrator read the FAQ table: 1–3 su → 500, 4–6 → 1,000, 7–10 → 5,000, 11–20 → 10,000, then +10,000 per extra 20 su; throughput 0.5 Gbps/su; 2 gateway instances up to 20 su | `virtual-wan-faq` |
| **LAQueryLogs coverage of Sentinel/Defender surfaces is inconsistent between two Learn pages** | Reviewer A (R12); both pages read; scheduled executions are *not* logged in either | `azure-monitor/logs/query-audit`; `sentinel/audit-sentinel-data` |
| **"Nothing flags a never-used table" is false for Sentinel workspaces** | Reviewer C (F1); SOC optimization page read in full | `sentinel/soc-optimization/soc-optimization-reference` |
