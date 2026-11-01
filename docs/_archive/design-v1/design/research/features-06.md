# Features triage F6 — attachment lines 521–622

> Agent F6 · 2026-10-31 · slice = 102 rows (lines 521–622), 14 May 2026 back to 19 Mar 2026 · 33 clusters · row triage: A 11 · AP 4 · E 16 · W 38 · N 33. Pages were fetched for every A, AP and E row or, where the row is a blog echo, for the feature's primary source (Learn page, update entry or the same team's post); the rest were classified from the summaries (listed in section 4).
> Dispositions: A = ADOPT · AP = ADOPT-PREVIEW · E = EVALUATE · W = WATCH · N = N/A.

## 1. Clusters

33 clusters. Dispositions: A = ADOPT · AP = ADOPT-PREVIEW · E = EVALUATE · W = WATCH · N = N/A. Source keys (S01…) are listed under the table. **Status of every Azure Updates item was re-read today from the Release Communications API** (the `azure.microsoft.com/updates` pages render empty to fetch tools); where the attachment's summary and the live status differ, the live status wins and the row says so.

| id | feature | status (date) | what it does | fit for our design | disp | why | cost / security notes | sources |
|---|---|---|---|---|---|---|---|---|
| F6-01 | Bring your own model / AI gateway in Foundry Agent Service | GA (Apr 2026; preview Nov 2025) | Admin-connected models: Foundry agents call models behind APIM or another OpenAI-compatible gateway through a project connection (`ApiManagement` or `ModelGateway`), authenticated by APIM key or project managed identity. | GW, AGT, MOD — put declarative prompt agents behind the Citadel hub; one connection per access contract; model id is `<connection>/<model>`. | A | GA, and the only supported way to route prompt agents through our own gateway. | **Prompt agents only; chat-completions only (Responses API "isn't supported at present").** Private path needs the APIM+Foundry sample template; RAI mitigations are ours. | S01, S02 |
| F6-02 | Hosted agents in Foundry Agent Service | GA (Jun 2026, update 563596); preview Nov 2025; refresh preview 22 Apr 2026 | Your container (Python or C# per Learn; any framework) runs in a per-session VM-isolated sandbox with persistent `$HOME`, its own Entra agent identity, a versioned endpoint (Responses, Invocations, A2A, Activity) and scale-to-zero. | AGT, COMP, ID, NET, COST — runtime for Detective, Skeptic, Economist and any role with custom tools; outbound through our VNet; West Europe, Sweden Central, Germany West Central, France Central are listed. | A | GA; matches H1 and H6 (own code, own identity, pay only while a session is active). | Billed per active vCPU/GiB (rate not rendered). 2 vCPU/4 GiB max; no traffic splitting; idle timeout 2–240 min (15 default); deleted after 30 idle days. | S03, S04, S05 |
| F6-03 | Foundry Agent Service GA, Evaluations GA, SDK 2.0 (March 2026 digest) | GA (digest 9 Apr 2026) | Next-gen runtime on the Responses API with end-to-end private networking and MCP auth (key, agent identity, managed identity, OAuth passthrough); evaluations with continuous monitoring into Azure Monitor; azure-ai-projects 2.0.0 stable. | AGT, EVAL, DEV — baseline platform and the SDK to pin; continuous evaluation on production traces (H11) can rest on the GA parts. | A | GA baseline for H1; `azure-ai-agents` is gone, everything is `AIProjectClient`. | GPT-5.4 launched on Global and US Data Zone Standard only: check EU Data Zone before pinning models (A2). | S07 |
| F6-04 | Memory in Foundry Agent Service | Public preview (29 Apr 2026; refresh Jun 2026) | Managed long-term memory: LLMs extract and consolidate user-profile, chat-summary and procedural memories; item CRUD, store TTL, remember/forget commands; memory-search tool or Memory Store API. | KNW, AGT — Diplomat's per-person preferences (channel, language, quiet hours) only. Estate Model and Lesson Book stay in our own store. | E | Preview; memories are model-written, unlike evidence-backed Lesson Book entries. | DPA applies during preview; delete and TTL support erasure. Extraction model calls: gateway routing not stated. Poisoning risk from external text. | S09, S10 |
| F6-05 | Toolbox in Foundry | GA (Jun 2026, update 563481; preview 22 Apr 2026); tool search, connectors and triggers: Public preview (Jun 2026) | Named, versioned bundle of tools (MCP, A2A, OpenAPI, web search, code interpreter, file and AI search) behind one MCP endpoint, with central auth (OAuth passthrough, Entra, keys) and a guardrail setting. | TOOL, ID, GW — per-agent versioned tool bundles; user-delegated tools by OBO; hosted agents reach Foundry-managed tools only this way. | E | GA, but it overlaps Citadel publish contracts; test agent → toolbox → APIM MCP before committing. | Reached through the project private endpoint. Unsupported when network-isolated: Work IQ, browser automation; web search uses public endpoints. | S11, S12, S13 |
| F6-06 | Foundry observability and monitoring | Tracing GA (Mar 2026); Control Plane observability GA (Nov 2025); Agent Monitoring Dashboard, Agent Framework and hosted-agent tracing, custom continuous-evaluation evaluators: Public preview (Apr 2026) | OpenTelemetry traces to Application Insights; dashboard for tokens, latency, success and evaluator scores; agent inventory in Control Plane (Foundry agents, SRE Agent, custom agents). | OBS, EVAL — production-trace evaluation and per-agent token accounting (H11); GA tracing and evaluations now, preview dashboard behind a switch. | AP | Core parts GA; fallback for the dashboard is Application Insights workbooks. | Needs Application Insights and Log Analytics roles (Privileged Monitoring Data Reader for protected tables); ingestion is a cost meter. | S08, S53, S55 |
| F6-07 | Microsoft Agent Framework 1.0 | GA (3 Apr 2026), .NET and Python | Stable agents; graph workflows with checkpointing; five orchestration patterns with human approvals and pause/resume; middleware; memory providers; YAML declarative agents; A2A and MCP. Preview at 1.0: DevUI, Skills, Foundry hosting, AG-UI, Agent Harness. | FW — orchestrator for the Conductor and role workflows (H1); approvals as workflow requests. | A | GA with a long-term-support commitment; Microsoft's single orchestration path. | Open source. Middleware is where content safety and AGT plug in. | S15, S16 |
| F6-08 | A2A v1 in Agent Framework | Protocol v1.0 stable; MAF packages Public preview (28 Apr 2026); hosted agents: A2A v1.0 GA, v0.3 preview | Signed Agent Cards, multi-tenancy, HTTP+JSON (JSON-RPC fallback), SSE streaming; remote agents appear as ordinary `AIAgent`s. | TOOL, GW — cross-boundary agent calls through Citadel publish contracts; unnecessary inside one workflow. | AP | Protocol stable, SDK preview; fallback is MAF workflows or plain HTTP. | Signed cards help identity checks; APIM content safety for A2A APIs is GA (Jun 2026). | S17, S03, S25 |
| F6-09 | Agent Skills in Agent Framework | Public preview (MAF 1.0 notes, 3 Apr 2026) | Skills as `SKILL.md` folders, inline code or classes; loaded only when a request matches; scripts run through a pluggable runner with optional human approval. | FW, KNW, COST — Atlas Service Cost Profiles as skills loaded on demand to save tokens; Move scripts stay in the execution plane. | E | Preview; progressive disclosure suits token budgets, savings untested. | The sample subprocess runner is not production-safe: needs sandbox, limits, audit. | S18, S15 |
| F6-10 | CodeAct with Hyperlight | Public preview (Azure Updates, effective Jun 2026); alpha in the 23 Apr 2026 post | One model-written Python block runs in a fresh Hyperlight micro-VM, tools bridged back; claims ~50% less latency and >60% fewer tokens in "representative workloads". | FW, COMP, COST — Detective and Economist analysis loops (query, filter, compute) in fewer turns. | E | Large claimed token saving; measure on our loops and find where Hyperlight can run. | Sandbox isolates model code, not tools. Host virtualisation requirement UNVERIFIED; fallback: Container Apps dynamic sessions (A5). | S19, S20 |
| F6-11 | Handoff orchestration and AG-UI | Handoff stable in 1.0; AG-UI preview (Python; C# "in development", 8 Apr 2026) | Handoff: agents pick the next speaker on a declared graph. AG-UI: open protocol streaming agent events to a UI, with approval prompts. | FW, CHAN — routing among Diplomat and Detective roles; optional web approval console later. | W | Patterns; Teams cards and email come first. | Hosted agents serve AG-UI over the Invocations protocol. | S15, S03 |
| F6-12 | Agent Governance Toolkit (AGT) | Public preview, MIT (README today): "May have breaking changes before GA" | Open-source runtime governance: deterministic tool-call policy, agent identity, kill switch, SRE (SLOs, circuit breakers), compliance mapping (EU AI Act, NIST AI RMF), budgets, Merkle-chained audit; Agent Framework middleware for Python and .NET. | SEC, GOV, FW — in-process guard for the execution plane: approval gates (two approvers for purchases), cost budgets, intent-drift checks; complements the gateway. | E | Strong fit to H4, H8, H11, but preview and churning (policy engine moved upstream; `agent_os` deprecated). | Free. Sees what the gateway cannot (actions inside the process). Pin versions; red-team its policies. | S21, S22, S23 |
| F6-13 | Azure Resource Manager MCP Server | Public preview (7–11 May 2026) | Remote MCP server with six tools: generate, validate and execute Azure Resource Graph queries; create, monitor and cancel ARM template deployments. | TOOL, SEC — read-only query tools could serve Cartographer and Surveyor; deployment tools must never reach the reasoning plane (H4). | E | Preview and write-capable; own ARG tool is the GA fallback (Azure MCP Server 3.0 is GA since Oct 2026, A3). | Install flow needs VS Code and GitHub Copilot; natural-language-to-KQL sends estate questions to a Microsoft service. Use a tool allow-list. | S24, S25 |
| F6-14 | MCP servers on Azure Functions | GA: tool trigger (Nov 2025), resource triggers (Mar 2026), MCP Apps hosting (update title); prompt triggers on the binding page | Functions MCP extension (Python, TypeScript, .NET, Java) hosts tools, resources and prompts as a remote MCP server; Foundry connects by key, Entra (project identity), OAuth passthrough or none. | TOOL, COMP — host our own tools (Atlas lookup, Estate Model, cost-data query) as MCP servers; Atlas facts as MCP resources. | A | GA and serverless; the same server serves Foundry, VS Code and our workflows. | Foundry→Functions Entra supports the shared project identity only, not per-agent identity: enforce per-agent access at the gateway. | S26, S27, S28 |
| F6-15 | APIM and API Center as the MCP/agent front door | GA: MCP governance in APIM (Nov 2025); API Center agent registration/assessment and data-plane MCP server (Jun 2026); skills assessment: Not stated | APIM groups domain APIs and exposes them as MCP; API Center catalogues APIs, MCP servers, agents and skills and scores skills with an LLM judge (four dimensions, 1–5). | GW, GOV, TOOL — registry and discovery next to Citadel publish contracts; quality gate for skills. | E | Probably already part of the hub; decide in A1 whether to add API Center. | API Center Standard is free for linked APIM Standard/Premium (Nov 2025); judge calls cost tokens. | S30, S31, S32 |
| F6-16 | SQL MCP Server (Data API builder) | GA (Jun 2026; preview Mar 2026); open source, free | JSON-configured MCP server (MCP 2025-06-18) over SQL, PostgreSQL, Cosmos DB, MySQL: entity abstraction, role-based permissions, Entra, caching, OpenTelemetry; runs as a container. | TOOL, DATA — zero-code, role-scoped, read-only MCP over the operational DB (Estate Model); avoids agent-written SQL (the NL2SQL caution of L522). | E | Depends on the store chosen in A5; cheap to test. | Self-hosted (Container Apps or App Service); needs an auth mapping per agent group. | S33, S25 |
| F6-17 | PostgreSQL graph (Apache AGE) and AI functions | AGE GA (May 2025; PostgreSQL 16/17, extending to 18 per May 2026 post); `ai_extension` AI functions Public preview | openCypher graph queries inside PostgreSQL, joined with SQL, ACID, indexed; `extract()` builds graphs from text. | DATA, KNW — Estate Model as owner → team → service → resource graph next to relational and vector data. | E | Their example ("who should I talk to about the payment service") is our ownership question; compare in A5. | Flexible Server is not scale-to-zero (UNVERIFIED here); graph copies must be re-materialised as source tables change. | S34, S35 |
| F6-18 | Azure SQL embeddings (`AI_GENERATE_EMBEDDINGS`) | GA (8 May 2026) in Azure SQL Database and Managed Instance; `VECTOR_SEARCH` preview | `CREATE EXTERNAL MODEL` plus `AI_GENERATE_EMBEDDINGS` call an Azure OpenAI/OpenAI-format endpoint from T-SQL; key header, key query, managed identity or SAS. | DATA, KNW — only if Azure SQL is the operational store; point the external model at the gateway (inference). | W | One of three store options in A5; no phase-1 need. | Embeddings only at GA; a direct Foundry endpoint would bypass Citadel. | S36 |
| F6-19 | Cosmos DB for AI: quantization, Shell, cost tips | Spherical quantization and Shell: Public preview (6 May 2026) | Vector compression for faster indexing and better recall; open-source shell with MCP; vendor tips: free tier, serverless for bursty low volume, autoscale for spikes. | DATA, COST — input to the Cosmos serverless option for the operational store (A5). | W | Comparison material; preview features not needed. | The "$240 to under a dollar a month" case is a marketing anecdote, not evidence for us. | S37 |
| F6-20 | Gateway semantic cache and Azure Managed Redis | Azure Managed Redis GA (May 2025); Azure Cache for Redis retiring (30 Sep 2028); Enterprise tier retiring (30 Mar 2027), creation blocked from 1 Apr 2026 | APIM semantic caching needs an Azure Managed Redis instance with RediSearch (settable only at creation) plus an embeddings deployment. | GW, COST — a standing-cost option; model-side cached-input pricing may beat it for non-repeating investigations (inference). | W | Likely off by default; decide with a measured hit rate (A1). | Always-on Redis meter plus embedding tokens. Do not provision Azure Cache for Redis. | S38, S32 |
| F6-21 | Budget-triggered stop for Azure OpenAI | Pattern on GA parts (Budgets, Action Groups, Automation) | Budget alert → Action Group → runbook sets `-DisableLocalAuth $true` on the account; a manual runbook re-enables it. | COST, LAB, GOV — backstop for Lab subscriptions and spend alerts; never the primary cap. | E | Test real latency in the Lab; the real-time cap is gateway token limits. | Budgets evaluate every 24 h on data 8–24 h old and stop nothing; disabling local auth blocks keys only and takes minutes to hours. | S39, S40, S41 |
| F6-22 | Private networking and DNS for Foundry spokes | Practitioner posts (Apr–May 2026); platform behaviour checked on Learn (updated Sep–Oct 2026) | Checklists: custom DNS forwards to 168.63.129.16; central private DNS zones linked everywhere; Container Apps internal DNS zone with `*`, `@`, `*.internal`; Learn adds subnet and BYO-resource rules. | NET, GOV — DNS and egress checklist for H3. | E | Useful but unofficial; one claim (10.x needs allow-listing) is contradicted by Learn. | Standard private setup needs BYO Storage, AI Search, Cosmos DB with private endpoints you create; /24 delegated subnet advised; project-level capability host. | S42, S45, S46 |
| F6-23 | AI-assisted drift detection posts | Practitioner posts (Apr–May 2026) | AI explains drift, including portal edits outside the pipeline, and writes root-cause reports; one post says AI should assist, not approve or remediate. | OPS, GOV — pattern for H11: agents explain; Deployment Stacks, Policy and a deterministic plan decide. | W | Patterns only; consistent with human-in-the-loop. | One incident: an OpenAI endpoint publicly reachable despite private endpoints — watch public network access with Policy. | S61 |
| F6-24 | Retirements in the slice | Prompt Flow retiring (20 Apr 2027); Document Intelligence v3.0 retiring (30 Mar 2029); eight AI Language features retiring (31 Mar 2029); Azure ML external data import Retired (30 Sep 2026) | Prompt Flow is replaced by Agent Framework (migration guide); the others concern services we do not use. | FW — confirms Agent Framework as the one orchestration path. | N | Not used; the Prompt Flow date is the design-relevant one. | n/a | S47 |
| F6-25 | Azure SRE Agent | GA (Mar 2026); VNet integration and 30-day trial GA (Aug 2026); Live Reports Public preview (Aug 2026) | AI operations agent reading Azure Monitor and Log Analytics; proposes (review mode) or executes (autonomous mode) fixes; custom runbooks and subagents. | OPS, OBS — operate our own platform (H11): incident and drift triage in our spoke; billing per A3. | E | GA and VNet-capable; the 30 Mar post's preview-era region limits are stale. | Onboarding needs Owner or User Access Administrator, then least privilege; keep read-only by default. | S48, S49 |
| F6-26 | azd for agents | azd Extension Framework GA (Aug 2026); `azd ai agent` extension and Copilot-assisted `azd init` (Preview) shipped Mar 2026 | `azd ai agent run/invoke/show/monitor`, `azd deploy` for hosted agents, Container App Jobs via `host: containerapp`, local preflight validation. | OPS, DEV, COMP — hosted-agent deploy step and Container App Jobs for scale-to-zero analytics, run from GitHub Actions (H12). | AP | Fits delivery; fallback is SDK `agents.create_version` from CI. | Agent versions come from azd/SDK calls; no Bicep route on the pages read (UNVERIFIED). Unified extension needs azd 1.27.1+. | S50, S12, S35 |
| F6-27 | Foundry Local | GA (9 Apr 2026): Windows, macOS Apple silicon, Linux x64; 1.1 (12 May 2026) | On-device inference (chat, audio, embeddings, Responses API, live transcription) bundled into apps; no per-token cost. | DEV, MOD — offline dev/test loop and cheap smoke tests; not for production roles. | W | Possible CI cost lever; not needed in phase 1. | Small local models limit quality; needs hardware. | S08 |
| F6-28 | Realtime voice models | GPT Realtime 2.0 Public preview (May 2026); Translate and Whisper articles: Not stated (attachment summaries; pages not fetched) | Realtime translation, streaming transcription and a reasoning-capable realtime model. | CHAN, MOD — voice is an optional module, off by default (H10). | W | Not needed in phase 1. | Voice on hosted agents uses Invocations (WebSocket). | S03 |
| F6-29 | Foundry web search (Grounding with Bing) | Not stated (Learn page updated 21 Oct 2026) | Agent web search with citations through Grounding with Bing Search or Custom Search; domain-restricted option. | TOOL, SEC — Scholar's web reading: prefer our own egress-controlled fetch tool with a domain allow-list. | W | Data leaves the compliance boundary and the DPA does not apply; acceptable only for public, non-estate queries. | Per-1,000-transaction meter; public endpoints even in network-isolated projects. | S51, S13 |
| F6-30 | Azure DevOps MCP Server | Preview (19 Mar 2026 post; April update 21 Apr 2026) — attachment summaries only | MCP server for Azure DevOps work items, repos and pull requests; offered in the Foundry tool catalogue with per-tool filtering. | none — we use GitHub. | N | Not our source-control platform. | n/a | none fetched |
| F6-31 | Chat-history storage and compaction | Patterns; Agent Harness and compaction Public preview (22 Apr 2026) | Service-managed history (Foundry conversations, no say over compaction) versus client-managed (own location, truncation or summarisation); `CompactionProvider` with a sliding window. | FW, COST — history location is a token-cost and GDPR lever: client-managed plus compaction for long Detective runs, service-managed for short Diplomat chats. | E | A per-role decision we must take; test compaction savings. | Resent history inflates input tokens; stored conversations are personal data. | S52, S57 |
| F6-32 | Foundry Toolkit for VS Code | GA (Apr 2026); formerly AI Toolkit | VS Code extension: templates, local debug with traces, evaluate and deploy hosted agents, Agent Builder. | DEV — contributors' inner loop for the open-source repo. | A | GA, free, covers hosted agents and Agent Framework. | Microsoft-published extension; no cost noted. | S56, S08, S57 |
| F6-33 | Reference: governing agent sprawl (gateway + Control Plane + Agent 365) | Reference post (7 May 2026); says Agent 365 GA 1 May 2026 (not verified elsewhere) | Three control layers: AI gateway (token limits, content safety, metrics), Foundry Control Plane (inventory, continuous evaluation, guardrails; needs a gateway), Agent 365 (tenant registry, Entra agent ID, Conditional Access). | GW, GOV, ID — confirms the H2/H11 layering; Agent 365 is tenant-level oversight outside our spoke. | E | Independent confirmation of the layers; Agent 365 licensing and fit untested. | Multi-region APIM gateway needs Premium; Agent 365 licence unknown. | S43 |

**Source key** (all fetched 2026-10-31; Release Communications entries are the JSON behind the Azure Updates pages):
- S01 `https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/ai-gateway?tabs=api-management&pivots=foundry-portal`
- S02 `https://www.microsoft.com/releasecommunications/api/v2/azure/561002`
- S03 `https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents?view=foundry`
- S04 `https://devblogs.microsoft.com/foundry/introducing-the-new-hosted-agents-in-foundry-agent-service-secure-scalable-compute-built-for-agents/`
- S05 `https://www.microsoft.com/releasecommunications/api/v2/azure?$filter=contains(title,'osted agent')&$orderby=modified desc&$top=15&$select=id,title,status,generalAvailabilityDate,previewAvailabilityDate,modified`
- S06 `https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-state-store`
- S07 `https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-mar-2026/`
- S08 `https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-apr-2026/`
- S09 `https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-memory`
- S10 `https://www.microsoft.com/releasecommunications/api/v2/azure?$filter=contains(title,'emory') and contains(title,'Foundry')&$orderby=modified desc&$top=15&$select=id,title,status,generalAvailabilityDate,previewAvailabilityDate,modified`
- S11 `https://devblogs.microsoft.com/foundry/introducing-toolboxes-in-foundry/`
- S12 `https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox`
- S13 `https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox-network-isolation`
- S14 `https://www.microsoft.com/releasecommunications/api/v2/azure?$filter=contains(title,'oolbox')&$orderby=modified desc&$top=15&$select=id,title,status,generalAvailabilityDate,previewAvailabilityDate,modified`
- S15 `https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/`
- S16 `https://www.microsoft.com/releasecommunications/api/v2/azure?$filter=contains(title,'Agent Framework')&$orderby=modified desc&$top=15&$select=id,title,status,generalAvailabilityDate,previewAvailabilityDate,modified`
- S17 `https://devblogs.microsoft.com/agent-framework/a2a-v1-is-here-cross-platform-agent-communication-in-microsoft-agent-framework-for-net/`
- S18 `https://devblogs.microsoft.com/agent-framework/agent-skills-in-net-three-ways-to-author-one-provider-to-run-them/`
- S19 `https://devblogs.microsoft.com/agent-framework/codeact-with-hyperlight/`
- S20 `https://www.microsoft.com/releasecommunications/api/v2/azure/563566`
- S21 `https://devblogs.microsoft.com/agent-framework/governance-at-the-speed-of-agents-microsoft-agent-framework-and-agent-governance-toolkit-better-together/`
- S22 `https://github.com/microsoft/agent-governance-toolkit`
- S23 `https://techcommunity.microsoft.com/t5/linux-and-open-source-blog/agent-governance-toolkit-architecture-deep-dive-policy-engines/ba-p/4510105`
- S24 `https://techcommunity.microsoft.com/t5/azure-governance-and-management/introducing-the-azure-resource-manager-mcp-server/ba-p/4517521`
- S25 `https://www.microsoft.com/releasecommunications/api/v2/azure?$filter=contains(title,'MCP')&$orderby=modified desc&$top=40&$select=id,title,status,generalAvailabilityDate,previewAvailabilityDate`
- S26 `https://learn.microsoft.com/en-us/azure/azure-functions/functions-mcp-foundry-tools`
- S27 `https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-mcp`
- S28 `https://www.microsoft.com/releasecommunications/api/v2/azure/559981`
- S29 `https://devblogs.microsoft.com/azure-sdk/give-your-foundry-agent-custom-tools-with-mcp-servers-on-azure-functions/`
- S30 `https://techcommunity.microsoft.com/t5/azure-integration-services-blog/introducing-ai-skill-assessment-in-azure-api-center/ba-p/4515243`
- S31 `https://techcommunity.microsoft.com/t5/azure-architecture-blog/centralizing-enterprise-api-access-for-agent-based-architectures/ba-p/4511792`
- S32 `https://www.microsoft.com/releasecommunications/api/v2/azure?$filter=contains(title,'Cache for Redis') or contains(title,'API Center') or contains(title,'Prompt Flow')&$orderby=modified desc&$top=20&$select=id,title,status,generalAvailabilityDate,previewAvailabilityDate`
- S33 `https://devblogs.microsoft.com/azure-sql/introducing-sql-mcp-server/`
- S34 `https://techcommunity.microsoft.com/t5/microsoft-blog-for-postgresql/postgresql-as-your-graph-database-in-the-ai-era/ba-p/4516323`
- S35 `https://www.microsoft.com/releasecommunications/api/v2/azure?$filter=contains(title,'Foundry Local') or contains(title,'Managed Redis') or contains(title,'Apache AGE') or contains(title,'azd') or contains(title,'Developer CLI')&$orderby=modified desc&$top=20&$select=id,title,status,generalAvailabilityDate,previewAvailabilityDate`
- S36 `https://devblogs.microsoft.com/azure-sql/generate-embeddings-function-and-external-model-object-support-are-now-generally-available-in-azure-sql/`
- S37 `https://devblogs.microsoft.com/cosmosdb/7-tips-to-optimize-azure-cosmos-db-costs-for-ai-and-agentic-workloads/`
- S38 `https://learn.microsoft.com/en-us/azure/api-management/azure-openai-enable-semantic-caching`
- S39 `https://techcommunity.microsoft.com/t5/azure-infrastructure-blog/automating-azure-openai-cost-control-using-budgets-action-groups/ba-p/4505164`
- S40 `https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets`
- S41 `https://learn.microsoft.com/en-us/azure/ai-services/disable-local-auth`
- S42 `https://techcommunity.microsoft.com/t5/azure-infrastructure-blog/private-dns-and-hub-spoke-networking-for-enterprise-ai-workloads/ba-p/4508835`
- S43 `https://techcommunity.microsoft.com/t5/azure-architecture-blog/governing-agent-sprawl-a-multi-region-ai-agent-landing-zone-on/ba-p/4516036`
- S44 `https://techcommunity.microsoft.com/t5/azure-infrastructure-blog/operationalizing-responsible-ai-in-microsoft-foundry-within/ba-p/4516869`
- S45 `https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/virtual-networks`
- S46 `https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agents-networking-deep-dive`
- S47 `https://www.microsoft.com/releasecommunications/api/v2/azure/502936`
- S48 `https://www.microsoft.com/releasecommunications/api/v2/azure?$filter=contains(title,'SRE Agent')&$orderby=modified desc&$top=15&$select=id,title,status,generalAvailabilityDate,previewAvailabilityDate`
- S49 `https://techcommunity.microsoft.com/t5/azure-infrastructure-blog/from-toil-to-trust-how-azure-sre-agent-is-redefining-cloud/ba-p/4505875`
- S50 `https://devblogs.microsoft.com/azure-sdk/azure-developer-cli-azd-march-2026/`
- S51 `https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/web-search`
- S52 `https://devblogs.microsoft.com/agent-framework/chat-history-storage-patterns-in-microsoft-agent-framework/`
- S53 `https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/how-to-monitor-agents-dashboard`
- S54 `https://learn.microsoft.com/en-us/azure/foundry/whats-new-foundry?view=foundry`
- S55 `https://www.microsoft.com/releasecommunications/api/v2/azure?$filter=contains(title,'Control Plane') or contains(title,'racing') or contains(title,'Monitoring Dashboard') or contains(title,'Continuous evaluation')&$orderby=modified desc&$top=20&$select=id,title,status,generalAvailabilityDate,previewAvailabilityDate`
- S56 `https://www.microsoft.com/releasecommunications/api/v2/azure/560987`
- S57 `https://devblogs.microsoft.com/foundry/from-local-to-production-the-complete-developer-journey-for-building-composing-and-deploying-ai-agents/`
- S58 `https://www.microsoft.com/releasecommunications/api/v2/azure/560992`
- S59 `https://azure.microsoft.com/pricing/details/foundry-agent-service/` (rates not rendered)
- S60 `https://azure.microsoft.com/en-us/updates/?id=561002` (empty shell; banner mentions a Release Communications MCP server)
- S61 `https://techcommunity.microsoft.com/t5/azure-infrastructure-blog/ai-assisted-azure-infrastructure-validation-and-drift-detection/ba-p/4508346`

## 2. Row triage

`line · title · disposition · cluster`

- 521 · Agent Governance Toolkit with Agent Framework · E · F6-12
- 522 · SQL MCP Server and NL2SQL caution · W · F6-16
- 523 · SQL security across the MAESTRO stack · W · -
- 524 · What's new in Foundry, April 2026 · AP · F6-06
- 525 · Open in VS Code for Terraform · N · -
- 526 · Foundry Local 1.1: transcription, embeddings, Responses · W · F6-27
- 527 · Azure Cache for Redis to Managed Redis · W · F6-20
- 528 · Azure Resource Manager MCP Server preview · E · F6-13
- 529 · Terraform managed disks and stable keys · N · -
- 530 · Azure SQL embeddings function and external model GA · W · F6-18
- 531 · Cosmos DB AVASOFT Super Insight session · N · -
- 532 · Least-privilege agents with Curity azd template · N · -
- 533 · Governing agent sprawl: multi-region agent landing zone · E · F6-33
- 534 · Secure AI platforms in banking · W · F6-22
- 535 · Handoff orchestration pattern tour · W · F6-11
- 536 · Document Intelligence v3.0 retirement 2029 · N · F6-24
- 537 · Cosmos DB spherical quantization preview · W · F6-19
- 538 · Responsible AI in Foundry within network boundaries · W · F6-22
- 539 · Deploy Agent Framework agent to hosted agents · A · F6-02
- 540 · Distributing model weights on AKS and Slurm · N · -
- 541 · Resilient networks for AI supercomputers · N · -
- 542 · Cosmos DB Shell public preview · W · F6-19
- 543 · Multi-file refactoring with Copilot Workspace · N · -
- 544 · AI agent for infrastructure validation · W · F6-23
- 545 · SQL MCP Server on App Service · W · F6-16
- 546 · PostgreSQL graph queries with Apache AGE GA · E · F6-17
- 547 · From drift to self-healing infrastructure · W · F6-23
- 548 · Microsoft Discovery for scientists · W · -
- 549 · Shift-left governance with Agent Governance Toolkit · E · F6-12
- 550 · GPT Realtime Translate and Whisper articles · W · F6-28
- 551 · GPT Realtime 2.0 concept articles · W · F6-28
- 552 · AI-accelerated AVM refactoring · W · -
- 553 · AI root cause analysis for infrastructure drift · W · F6-23
- 554 · SharePoint permissions into AI Search RAG · W · -
- 555 · Video to SOPs with GraphRAG · N · -
- 556 · Memory in Foundry Agent Service preview · E · F6-04
- 557 · Observability for AI agents with Foundry · A · F6-06
- 558 · Microsoft Agent Framework 1.0 generally available · A · F6-07
- 559 · CI/CD as a platform, reusable workflows · W · -
- 560 · A2A v1 in Agent Framework .NET · AP · F6-08
- 561 · Prompt Flow retirement April 2027 · N · F6-24
- 562 · AI skill assessment in API Center · W · F6-15
- 563 · Bring your own AI gateway GA · A · F6-01
- 564 · LLM container cold-start dissected · N · -
- 565 · Foundry versus traditional ML pipelines · N · -
- 566 · Drone-based industrial inspection with AI · N · -
- 567 · When RAG isn't enough: relationships · W · F6-17
- 568 · Hosted agent support in Foundry Toolkit GA · A · F6-32
- 569 · Zero Trust networking for enterprise AI · W · F6-22
- 570 · Chat history storage patterns in Agent Framework · E · F6-31
- 571 · Azure MCP Server as .mcpb bundle · W · -
- 572 · AI downtime investigation for Azure VMs · N · -
- 573 · CTI-REALM: agents to validated detections · W · -
- 574 · Agentic data governance, hybrid cloud story · N · -
- 575 · CodeAct with Hyperlight in Agent Framework · E · F6-10
- 576 · Centralizing enterprise API access via MCP · E · F6-15
- 577 · Toolboxes in Foundry (now GA) · E · F6-05
- 578 · New hosted agents in Foundry Agent Service · A · F6-02
- 579 · SUSE Multi-Linux Manager MCP Server · N · -
- 580 · Complete developer journey: build, compose, deploy agents · A · F6-02
- 581 · Seven tips to optimize Cosmos DB costs · W · F6-19
- 582 · Azure DevOps MCP Server April update · N · F6-30
- 583 · GitHub Copilot with azd project setup · W · F6-26
- 584 · Observable MCP Server at Novo Nordisk · N · -
- 585 · Claude Opus 4.7 on Azure Databricks · N · -
- 586 · Foundry fine-tuning updates, April 2026 · W · -
- 587 · Oracle data next to Microsoft AI · N · -
- 588 · AI agents for Azure Database for MySQL · N · -
- 589 · Agent Skills in .NET Agent Framework · E · F6-09
- 590 · Azure SRE Agent redefining cloud operations · E · F6-25
- 591 · Agent Governance Toolkit architecture deep dive · E · F6-12
- 592 · What's new in Foundry, March 2026 · A · F6-03
- 593 · Foundry Local is generally available · W · F6-27
- 594 · Azure NetApp Files VS Code agentic · N · -
- 595 · Introducing SQL MCP Server · E · F6-16
- 596 · Foundry agent custom tools: MCP on Functions · A · F6-14
- 597 · SAP and Microsoft 3-IQ layers · N · -
- 598 · Real-time multi-agent UI with AG-UI · W · F6-11
- 599 · Build an agent with AI Toolkit · W · F6-32
- 600 · Cosmos DB Tredence document processing session · N · -
- 601 · Fluent API for MCP Apps on Functions · W · F6-14
- 602 · Functions MCP resource triggers GA · A · F6-14
- 603 · Private DNS and hub-spoke for enterprise AI · E · F6-22
- 604 · MCP Apps on Functions TypeScript quickstart · W · F6-14
- 605 · Microsoft Agent Framework version 1.0 · A · F6-07
- 606 · Azure SQL Managed Instance as AI platform · N · -
- 607 · AI-assisted infrastructure validation and drift detection · W · F6-23
- 608 · VS Code custom agents for Terraform scanning · W · -
- 609 · Komprise unstructured data on Azure · N · -
- 610 · Azure AI Language features retirement 2029 · N · F6-24
- 611 · Azure ML data import retirement September 2026 · N · F6-24
- 612 · AI-assisted Oracle to PostgreSQL migration · N · -
- 613 · azd March 2026: agents, Copilot, Jobs · AP · F6-26
- 614 · Guardrails for generative AI developer workflows · N · -
- 615 · Search-enabled agents: Bing grounding over A2A · W · F6-29
- 616 · GitHub Copilot CLI for infrastructure deployments · N · -
- 617 · Red teaming, Risk Cards, Azure guardrails · W · -
- 618 · AKS container networking troubleshooting agent · N · -
- 619 · Budgets and runbooks to cap OpenAI cost · E · F6-21
- 620 · GraphRAG with PostgreSQL, Cypher and MCP v2 · W · F6-17
- 621 · Deploy an agent to Foundry with azd · AP · F6-26
- 622 · Azure DevOps MCP Server in Foundry · N · F6-30

## 3. Findings that change the design

- **H2 does not hold uniformly for Foundry-managed agents.** Bring-your-own-model is GA (Apr 2026) but for *prompt agents only* and chat-completions only (Responses API "isn't supported at present"); full network isolation needs the APIM+Foundry sample template. Hosted agents call models from our code, and their agent identity can reach inference through the project endpoint by default — staying behind Citadel is our policy and RBAC job, not a platform guarantee (whether the default path can be closed: UNVERIFIED). [S01, S03]
- **Hosted agents are GA (Jun 2026).** L578's "public preview" is stale and L568's "aligned with GA" was early. The 22 Apr launch post promises weighted rollouts; Learn says traffic splitting isn't supported — Learn wins. The 2 vCPU / 4 GiB per-session cap sends heavy cost-data work to Container Apps jobs. EU regions listed: West Europe, Sweden Central, Germany West Central, France Central and others. [S03, S04, S05]
- **Private networking has a standing-cost floor and sizing rules.** The Standard private setup needs bring-your-own Storage, AI Search and Cosmos DB with private endpoints you create; one delegated subnet (`Microsoft.App/environments`) per Foundry account, /24 advised, sessions ≈ usable IPs; a *project-level* capability host is required; private ACR only for projects created after 25 Jun 2026. These meters sit against "scale to zero" (H6): price them in P1. [S45, S46, S13, S03]
- **Contradiction on IP ranges.** The L538 post says 10.x needs allow-listing; the Learn deep dive (7 Sep 2026) lists 10.0.0.0/8, 172.16.0.0/12 and 192.168.0.0/16 as supported (CGNAT 100.64.0.0/10 is not). Learn wins; the spoke can use the landing zone's normal RFC 1918 space. [S46, S44]
- **Foundry web search leaves the compliance boundary.** It uses Grounding with Bing; the DPA does not apply and transfers occur outside compliance and geographic boundaries. The Scholar should read the web through our own egress-controlled fetch tool. Network-isolated toolboxes also lose Work IQ and browser automation; web search stays on public endpoints. [S51, S13]
- **Budgets are not a spend cap.** They evaluate every 24 h on data 8–24 h old and "your consumption isn't stopped"; the L619 runbook only disables key authentication, which takes minutes to hours and (inference from S41's purpose, enforcing Entra instead of keys) leaves Entra-authenticated callers untouched. The real-time cap is the gateway's per-contract token limit plus Foundry quota; budgets are alerts and a Lab backstop. [S39, S40, S41]
- **Gateway semantic caching carries a standing cost.** It needs Azure Managed Redis with RediSearch (settable only at creation) plus an embeddings deployment; Azure Cache for Redis retires 30 Sep 2028 (Enterprise 30 Mar 2027, creation blocked since 1 Apr 2026). Default it off until a hit rate is measured; model-side cached input is the likelier saver for non-repeating investigations (inference). [S38, S32]
- **Toolbox (GA Jun 2026) is a second tool front door beside Citadel.** The agent→toolbox hop is Foundry-internal; APIM governs only downstream calls, and only if the toolbox points at APIM MCP URLs (inference). "Discover" and "Govern" were "coming soon" at launch. Hosted agents need it for Foundry-managed tools. Decide per agent group. [S11, S12, S14]
- **Per-agent identity breaks at Functions-hosted MCP.** Foundry→Functions Entra authentication supports the shared *project* managed identity, not the per-agent identity (H9). Enforce per-agent authorisation in the gateway contract or inside the server. [S26]
- **Memory (preview) is not a knowledge store.** Memories are LLM-extracted and consolidated, which conflicts with "testimony widened only with corroboration". Use it for Diplomat preferences only, with TTL and item delete for erasure. [S09, S10]
- **Orchestration is settled; its edges are not.** Agent Framework 1.0 is GA and Prompt Flow retires 20 Apr 2027, but Skills, Foundry hosting integration, AG-UI, the A2A packages and CodeAct (public preview) are not GA. The hosted-agent durable state store (preview; 1 MB items) can hold workflow checkpoints; the GA fallback is our operational DB. [S15, S47, S06, S17, S20]
- **AGT is the new safeguard worth a spike.** In-process, MIT, Public Preview: policy before every tool call, approval gates with minimum approvers, collective cost budgets, intent-drift blocking, Merkle audit, Agent Framework middleware for Python and .NET. Churn is real (policy engine moved upstream; `agent_os` deprecated). [S21, S22]
- **ARM MCP Server is write-capable.** Six tools include template deployment and cancel; install is VS Code- and Copilot-centric. Reasoning-plane use is limited to the read-only query tools (H4). [S24]
- **Estate Model as a graph is viable on GA parts.** Apache AGE is GA on PostgreSQL Flexible Server and the vendor's own example is "who owns this service"; AI functions are preview and scale-to-zero is UNVERIFIED (A5). SQL MCP Server (GA Jun 2026) can expose whichever store wins as a role-scoped, read-only MCP surface with no agent-written SQL. [S34, S35, S33]
- **In-database embeddings can bypass the gateway.** Azure SQL's `CREATE EXTERNAL MODEL` calls any URL; pointing it at the gateway (inference) keeps contracts and token metrics intact. [S36]
- **Production evaluation is feasible on GA parts.** Evaluations with continuous monitoring into Azure Monitor and tracing are GA; the Agent Monitoring Dashboard and custom continuous-evaluation evaluators are preview. [S07, S08, S53]
- **Agent versions look like data-plane objects.** Hosted-agent versions are immutable and created by azd or SDK calls; no Bicep route appeared on the pages read, so Deployment Stacks deny settings cannot guard them. Drift control for agents rests on pinned versions and evaluation gates (UNVERIFIED that no ARM type exists). [S03, S50]
- **Azure Updates can be read as data.** The updates site is JavaScript-only for fetchers, but `releasecommunications/api/v2/azure` returns unauthenticated OData JSON (title, status, GA/preview dates, description), and the page banner advertises a Release Communications MCP server (not evaluated): cheap, structured input for the Scholar's freshness checks. [S02, S60]
- **Renames and stale statuses to carry.** AI Toolkit → Foundry Toolkit for VS Code (GA Apr 2026); SRE Agent GA since Mar 2026 with VNet integration (Aug 2026), so the 30 Mar post's preview regions are stale; Foundry RBAC roles renamed (Azure AI User → Foundry User, and so on). [S08, S48, S01]

## 4. Could not verify

- **Azure Updates HTML pages** (`azure.microsoft.com/en-us/updates/?id=…`) return an empty shell (tested on 561002, S60); statuses came from the JSON API. Entries not re-read there: 561176, 561167, 557394, 557406, 557887, 560590 (all N rows).
- **Rates.** Hosted-agent vCPU-hour and GiB-hour prices and the other Foundry Agent Service meters show "$-" on the pricing page (S59, JavaScript-rendered): not found; see P1.
- **Truncated or unconverted pages.** Several Tech Community posts failed Markdown conversion; I read the description embedded in the page source (L528, L533, L538, L562, L576, L591, L603, L607, L619), which may stop before the end of the post.
- **Classified from summaries only** (no page fetched for the row itself): every N row and the W rows 522, 523, 526, 534, 535, 537, 542, 544, 545, 547, 548, 550–554, 559, 567, 569, 571, 573, 583, 586, 593 (digest only), 598, 599, 601, 604, 608, 615, 617, 620.
- **Not confirmed on any page read:** (a) whether a hosted agent's default model access through the project endpoint can be disabled (gateway bypass); (b) whether Foundry memory's extraction and consolidation model calls can be routed through a gateway; (c) Hyperlight's host-virtualisation requirement and where CodeAct can run; (d) whether the Functions MCP extension runs on Flex Consumption; (e) PostgreSQL Flexible Server stop/scale-to-zero behaviour; (f) Go support for hosted agents (a Go sample page appeared in Learn search results; the concept page says Python and C#); (g) Azure SRE Agent's current regions and billing; (h) the Agent 365 GA date (L533 post only); (i) terms for Azure-sold models fronted by APIM under BYOM (the page's note covers third-party models); (j) ARM MCP Server GA status and non-VS Code authentication; (k) GA status of API Center skills assessment (L562); (l) GPT-5.4 EU Data Zone availability today (the March digest names only Global and US Data Zone at launch); (m) the L543 "GitHub Copilot Workspace" name against current Copilot products; (n) status of the voice articles L550 and L551.
- **Source conflicts settled by judgement:** hosted-agent rollouts (launch blog vs Learn: Learn wins); IP ranges (L538 post vs Learn: Learn wins); CodeAct maturity (alpha post vs later public-preview update: later wins); AGT shape (April deep dive vs today's README: README wins); hosted-agent status (L578 vs L568 vs the June GA entry: GA entry wins).
