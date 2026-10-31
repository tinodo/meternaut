# Price snapshot: method, checks and caveats

> Research evidence (assignment P1 of the [research brief](00-research-brief.md)), not the design. As of **31 October 2026**. Snapshot: [`prices-snapshot.json`](../cost/prices-snapshot.json), generated 2026-10-31T20:44:12Z by [`tools/fetch-prices.py`](../../../tools/fetch-prices.py) from [`price-queries.json`](../cost/price-queries.json). Retail pay-as-you-go list prices: no VAT, no discounts.

## 1. Result

| Item | Value |
|---|---|
| Queries | 41 (86 API result pages, both currencies) |
| Meters | **2,468** in 35 services, each with EUR and USD: Sweden Central 1,194, West Europe 538, North Europe 468, global 254, no region 14. 2,396 pay-as-you-go rows, 72 reservation rows, 198 with savings-plan prices |
| Hand-recorded | **36** (27 prices, 8 allowances, 1 billing basis), each with URL and date |
| Pricing-page checks | 92 meters on 24 pages: **92 match, 0 differ** |
| Anomalies | **0** (none of: duplicate identity, retail and unit price differ, missing currency, manual mismatch, underfilled query, failed page check) |
| EUR basis | EUR = USD × **0.87997** on the 657 meters priced at 1 or more (5th and 95th percentile equal) |
| Flags | 24 `eur-precision-loss` (tiny prices, EUR rounded: use USD), 5 `placeholder-price` |
| Reproducibility | A second full run, written outside the repository, returned the same 2,468 meter keys (`meterKeysSha256` `3700350be150…`) and the same prices (`compare --prices`: SAME). `--self-test` passes. On 2026-10-31 a read-only run of `tools/cost-model.py` resolved every meter it selects. |

## 2. Method

1. [`price-queries.json`](../cost/price-queries.json) holds queries (an OData `$filter` of service name and region group, include and exclude regular expressions on product, SKU and meter, an `expectMin` floor that raises an `underfilled` anomaly), 36 manual entries and 92 page checks. Region groups: eu = westeurope, swedencentral, northeurope; global = `Global` and empty.
2. The script calls `https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview&currencyCode=EUR|USD`, follows `NextPageLink` (1,000 rows a page; the link carries `:443`, so host and path are checked), retries with back-off.
3. EUR and USD rows merge on identity (region, service, product, SKU, meter, price type, term, tier, meter id, SKU id). Key: `region|service|product|sku|meter|type[:term]|tN|meterId8:skuSuffix`. One meter per line, sorted by key, so a diff shows single meters.
4. Each record: key, source, service, family, product, SKU, ARM SKU, meter, region, unit, price type, reservation term, tier minimum units, `prices{EUR,USD}`, effective start, meter, SKU and product ids, retrieval time, queries, flags, `savingsPlan`.
5. Page check: the script reads each pricing page's HTML, which embeds the USD price per region slug in `data-amount` JSON (visible text shows `$-`). Page value × scale (per 1M against per 1K, per month against per hour) must equal the API USD within max(5e-7, 0.2%).
6. Manual entries are not machine-checked; I read each on the page named in it.

## 3. The 41 queries (meters kept; the filter returned more, for example 1,268 provisioned rows kept as 27)

| Query | Meters | Content |
|---|---|---|
| apim | 84 | every tier per unit-hour, v2, workspaces |
| container-apps | 48 | consumption, dedicated, sessions, environment; jobs use the same meters |
| functions | 43 | Flex, Consumption, Premium |
| cosmos-db | 114 | serverless, provisioned, autoscale, storage, backup, reservations |
| postgresql-flexible | 92 | burstable, general purpose, storage |
| sql-database | 70 | serverless, free-offer, DTU, storage |
| sql-database-provisioned | 12 | 2 and 4 vCore comparison |
| ai-search | 106 | Free to L2, semantic ranker, agentic, serverless |
| storage-blob | 234 | hot to archive, LRS, ZRS, operations, ADLS Gen2 |
| log-analytics | 27 | ingestion, retention, queries |
| azure-monitor-logs | 98 | commitment tiers, Basic, Auxiliary, search, Data Archive |
| application-insights | 20 | classic meters only |
| key-vault | 67 | standard, premium, managed HSM |
| private-link-network | 22 | endpoint hour, data processed, peering, public IP |
| private-dns | 10 | zones, queries, resolver endpoints |
| azure-firewall | 30 | reference only |
| event-hubs | 39 | Basic to Dedicated |
| stream-analytics | 29 | standard, V2, dedicated |
| service-bus | 51 | Basic, Standard, Premium |
| event-grid | 23 | operations, throughput |
| defender-for-cloud | 107 | AI services, APIs, containers, storage, Key Vault, CSPM |
| sentinel | 74 | analysis, tiers, data lake |
| acs-email-chat | 17 | email, chat |
| acs-sms-placeholder | 5 | placeholders only (price 1.0) |
| acs-voice | 35 | automation, calling; PSTN placeholders |
| acs-phone-numbers | 5 | leases NL, DE, FR, UK |
| speech | 122 | Voice Live, avatars, speech-to-text, text-to-speech |
| foundry-agent-service | 27 | hosted agents, memory, router, evaluations, content safety, SRE Agent |
| grounding-and-tools | 21 | Bing grounding, code interpreter, file search |
| models-openai-gpt6 | 134 | astra, sol, terra, luna |
| models-openai-gpt5 | 262 | 5.4, 5.5, 5.6 |
| models-openai-other | 103 | GPT-4.1, o4-mini, embeddings, realtime, gpt-oss |
| models-third-party | 183 | Mistral, DeepSeek, Grok, Llama, Phi, Kimi, Cohere, MAI |
| models-provisioned | 27 | PTU hours and reservations |
| agent-pre-purchase | 3 | Agent Commit Units |
| data-explorer | 5 | engine markup |
| data-explorer-dev-vms | 6 | VM meters under the dev SKUs |
| durable-task-scheduler | 6 | consumption, dedicated |
| container-registry | 60 | Basic, Standard, Premium |
| managed-redis | 36 | Balanced B0 to B5 |
| managed-grafana | 12 | Essential, Standard |

The per-query counts add up to 2,469: one meter (MAI Web Grounding) is selected by two queries.

## 4. Page checks: 92 of 92 match

Pages are `https://azure.microsoft.com/en-us/pricing/details/<slug>/`; 79 checks use the West Europe slug, 13 Sweden Central.

`api-management` 10 (seven tiers, v2 scale-out, extra requests, Consumption calls) · `container-apps` 5 · `functions` 6 (Flex, Premium, Durable Task Scheduler) · `cosmos-db/serverless` 1 · `cosmos-db/autoscale-provisioned` 5 · `postgresql/flexible-server` 4 · `search` 6 · `key-vault` 2 · `private-link` 2 · `container-registry` 2 · `monitor` 6 (three ingestion tiers, retention, Data Archive, search) · `event-hubs` 2 · `service-bus` 2 · `azure-firewall` 2 · `defender-for-cloud` 6 (CSPM, containers, AI services, APIs, Key Vault, storage) · `sre-agent` 2 · `data-explorer` 1 · `foundry-agent-service` 4 (hosted vCPU and memory, code interpreter, web search) · `ai-foundry-models/model-router` 1 · `content-safety` 2 · `communication-services` 3 · `cognitive-services/speech-services` 5 · `azure-openai` 9 (GPT-6 luna, GPT-5.4 mini, embedding, Global and Data Zone PTU, monthly reservation) · `storage/blobs` 4.

## 5. Hand-recorded entries (36)

| Group | n | Source and content |
|---|---|---|
| Claude in Foundry | 11 | [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing), USD per 1M tokens: Haiku 5.5 0.10 in, 0.50 out, 0.01 cache read; Sonnet 5.5 2, 10, 0.10; Opus 5.5 4, 20, 0.20; Haiku 4.5 1, 5. EUR derived at 0.87997 |
| SMS | 8 | Learn sms-pricing: NL, DE, FR, UK alphanumeric send (UK $0.04, NL $0.092); mobile number send and receive |
| Voice PSTN | 8 | Learn pstn-pricing: "starting at" make and receive per minute (NL make $0.35, DE $0.015) |
| Allowances | 8 | pricing pages: see §7 |
| Billing basis | 1 | SRE Agent page: always-on, 4 Azure Agent Units an hour per agent until deletion |

## 6. Quirks met

- **Precision.** Without `api-version` EUR is rounded to 4 decimals (per-second meters read 0.0) while USD keeps 6. `2023-01-01-preview` gives 6-decimal EUR and `savingsPlan`; plain `2023-01-01` returns HTTP 400.
- **EUR is converted.** Learn: "The currency that Microsoft uses to price all Azure services is USD." Anchor on USD; the factor will move.
- **OData.** `eq` and `contains` are case-sensitive (use `contains(tolower(x),'…')`); `not (…)`, numeric and date comparisons return 400.
- **Names.** Models sit under `Foundry Models` (OpenAI, Mistral, DeepSeek, Grok, Llama, Phi, Kimi, Cohere, MAI); speech, content safety, agents, router, evaluations and SRE Agent under `Foundry Tools`. AI Search is still `Azure Cognitive Search`, Managed Redis is `Redis Cache`. Web search is `MS Bing Services`; Defender for AI Services is under Defender for Cloud; "Long-term retention" is the meter `Data Archive` under `Azure Monitor`; Data Explorer dev compute is `Virtual Machines`.
- **Model meters** abbreviate: `Inp`/`Opt` input/output, `Cd` cached, `Gl` Global, `DZ` Data Zone, `PP` Priority, `ShortCo`/`LongCo` context.
- **Free grants** appear as a tier-0 row at price 0 plus a paid row at `tierMinimumUnits`. Reservation rows hold the **full-term** price under unit `1/Hour`.
- **Units** vary: `1/Hour` or `1 Hour`; Functions executions per 10; commitment tiers and Container Registry per day; DNS resolver endpoints a bare `1` (per month).
- **Placeholders and duplicates.** SMS and PSTN meters are price 1.0 "consumption units". One meter id can sit under two SKUs or names, so identity includes both.
- **Savings plans** (preview API, 198 meters): about −15% (1 year) and −17% (3 years) on Container Apps, −12% Cosmos, −20% PostgreSQL, −17% Functions. One Cosmos meter shows 27.5 times its list price: ignore ratios above 1.
- **Pages** render prices client-side; a bare `Mozilla/5.0` agent gets 403.

## 7. What is free, and what could not be found

- **Allowances** (pages): Container Apps per subscription and month 180,000 vCPU-s, 360,000 GiB-s, 2M requests (not in the API; [Learn billing](https://learn.microsoft.com/en-us/azure/container-apps/billing) agrees); Functions Flex 100,000 GB-s and 250,000 executions, Consumption 400,000 GB-s and 1M; Cosmos free tier 1,000 RU/s and 25 GB; Content Safety free 5,000 text records and 5,000 images; AI Search semantic ranker 1,000 requests, agentic retrieval 50M tokens; Foundry file search 1 GB. In the API: Log Analytics first 5 GB, Event Grid first 1M operations, Service Bus 13M operations.
- **Dash.** Every pricing-page price reads `$-` in `web_fetch`; only the HTML `data-amount` JSON carries it. The Sentinel page returned 200 but no parsable table, so Sentinel prices are API-only (UNVERIFIED on the page). The Marketplace page returned 403.
- **Not found:** the Claude "Opus 5.5 Fast" price; a price for the APIM "AI Gateway tier" (page: "Pricing details are coming soon!"); PSTN per-destination prices (four countries "starting at" only); the Azure SQL free-offer quantity (zero-priced meters exist; UNVERIFIED); Data Explorer free-cluster limits (no meter).
- **Not queried:** Front Door, Entra, Purview, Microsoft 365, Agent 365, GitHub.

## 8. Caveats for the design

- **Hosted agents.** `Hosted vCPU Usage` $0.10934 and `Hosted Memory Usage` $0.01298 per hour exist for **Sweden Central only**: no West Europe or North Europe meter. Memory-store meters too. Whether billing is always-on or per active session is not on the page (UNVERIFIED).
- **Router surcharge.** Model router adds $0.14 per 1M tokens (Data Zone $0.154) on top of the model; listed in Sweden Central; which tokens count is UNVERIFIED.
- **Claude** is not in the API: billed through Azure Marketplace in CCU at $0.01 per CCU ([Anthropic page](https://platform.claude.com/docs/en/about-claude/pricing), [Learn CCU billing](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models-billing), updated 2026-10-27). Azure-hosted offers Global Standard and a **US** Data Zone (×1.1) only: no EU Data Zone ([Learn hosting comparison](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models-hosting-comparison), 2026-09-22).
- **Data Zone premium.** +10% on GPT-5.x, +20% on GPT-6.x over Global; Flex is Global only at 50% of Standard; Batch 50% (GPT-5.4); Priority 2×; cached input 10%. Token meters are held for Sweden Central; in an exploratory probe 95 of 1,936 differed in the other EU regions, mostly regional and PTU meters (Global and Data Zone token prices matched).
- **Token prices**, USD per 1M, Sweden Central, short context, Standard, Global input/output (Data Zone EU): GPT-6 luna 0.10/0.50 (0.12/0.60; cached 0.01); GPT-6.1 terra 1/5 (1.2/6); GPT-6.1 sol 2/10 (2.4/12); GPT-5.4 mini 0.75/4.50 (0.825/4.95); Mistral Large 3 0.50/1.50 (0.55/1.65); DeepSeek V4 Flash 0.19/0.51 (0.21/0.56); text-embedding-3-small 0.02 (0.022).
- **SRE Agent** always-on: 4 units an hour × $0.136 (West Europe) = €349 a month; Sweden Central $0.11 = €283.
- **Container Apps private endpoint.** Learn says private endpoints are "subject to a Dedicated Plan Management charge" even on Consumption. The API has `Environment Private Endpoint` at $0.143 an hour (€91.86 a month) and `Dedicated Plan Management` at $0.10 (€64.24); which one bills is UNVERIFIED: budget the higher.
- **Regions** differ by meter (USD, Sweden Central against West Europe): APIM v2 +30%; Container Apps −29%; PostgreSQL B2s −50%; SRE unit −19%; regional PTU −13%.
- **Defender for AI Services** costs $0.80 per 1M tokens (per 1K $0.0008), above both the input ($0.10) and the output ($0.50) price of GPT-6 luna, the cheapest GPT-6 tier; which tokens it counts is UNVERIFIED.
- **Durable Task Scheduler:** dedicated unit €629 a month; consumption $0.00429 per action; break-even about 166,670 actions a month; what an "action" counts is UNVERIFIED.
- **Commitments:** PTU Global $730 a month on demand, $260 on a monthly reservation, $2,652 on a one-year reservation (about $221 a month); Cosmos 100 RU/s $56 for a year against $70.08 on demand; Redis B0 $108 against $166.44. Agent Pre-Purchase Plan: $19,000 buys 20,000 Agent Commit Units (−5%); which meters draw them down is UNVERIFIED here.

## 9. Ten meters that dominate a small deployment

West Europe, 730 hours, one private-network spoke, quantities mine (illustrative, not the cost model).

| # | Meter | USD | € a month |
|---|---|---|---|
| 1 | API Management Standard v2 unit-hour (own gateway only; Basic v2 €132, no VNet) | 0.9589 | 615.98 |
| 2 | Log Analytics analytics-tier GB (60 GB, first 5 free; Basic logs €34, Auxiliary €4) | 2.99 | 144.71 |
| 3 | Container Apps environment private endpoint hour | 0.143 | 91.86 |
| 4 | AI Search Basic unit-hour | 0.101 | 64.88 |
| 5 | Private endpoint hour, ten endpoints | 0.01 | 64.24 |
| 6 | Container Apps vCPU- and GiB-seconds (3 replicas, 0.5 vCPU, 1 GiB, 10% active) | 0.000034 | 55.39 |
| 7 | Foundry tokens, output first (GPT-6 luna, terra, sol Global) | see §8 | 50.16 |
| 8 | Container Registry Premium day | 1.6666 | 44.61 |
| 9 | Defender for AI Services, 60M tokens | 0.0008 per 1K | 42.24 |
| 10 | Azure Managed Redis B0 hour | 0.019 | 12.20 |

Together ≈ €1,186 of ≈ €1,199. Optional and large: SRE Agent €283 to €349.

## 10. Refresh

```
python tools/fetch-prices.py                      # about 30 s of API calls plus page checks
python tools/fetch-prices.py compare OLD.json NEW.json --prices
```

Copy the old snapshot first; review price changes, `anomalies` and flags; change the specification, never the snapshot. `--only ids --out file` runs a subset (never over the snapshot), `--dry-run` prints the calls, `--no-pages` skips checks, `--strict` exits 3 on anomalies. Then regenerate the cost model's block with `tools/cost-model.py` (`--update-doc`, `--check`).

## 11. Sources fetched

[Retail Prices API overview](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) (updated 2026-01-06) · [Container Apps billing](https://learn.microsoft.com/en-us/azure/container-apps/billing) · [Claude CCU billing](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models-billing) · [Claude hosting comparison](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models-hosting-comparison) · [ACS SMS](https://learn.microsoft.com/en-us/azure/communication-services/concepts/sms-pricing) and [PSTN](https://learn.microsoft.com/en-us/azure/communication-services/concepts/pstn-pricing) pricing · [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) (via `aka.ms/ccu-pricing`) · the 24 pricing pages of §4 · the API at `https://prices.azure.com/api/retail/prices`.
