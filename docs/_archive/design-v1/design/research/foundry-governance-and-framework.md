# Foundry governance, identity, networking, observability, evaluation and the Agent Framework — research A3

> **Evidence, not design.** Written 2026-10-31 by research agent A3 for [the design](../README.md), under the [research brief](00-research-brief.md). Every status is as of today and comes from the page cited; a date is the date that page (or a release tag or blog post) gives. **(att.)** marks a claim taken only from the attached update list because the page would not render or was not fetched: treat it as `UNVERIFIED`. Where the attachment and a page disagree, the page wins and the text says so. Source IDs such as `[C1]` are listed in §19. Codes and dispositions are those of the brief.

## 1. Ten findings that matter most

1. **Foundry's UI workflows retire on 1 Dec 2026**; the page says to build new workflows with Agent Framework. Orchestration therefore means MAF graph workflows [F24].
2. **Agent guardrails are preview**, an agent policy *replaces* its model's policy, and tool-call/response screening covers a fixed tool list that excludes MCP and A2A. Document (indirect-injection) attack detection is **off by default** [G1, G2, G5].
3. **Network choices are one-way.** BYO-VNet is set when the account is created and cannot be added or changed later; moving between BYO and managed VNet means a redeploy. Managed-VNet FQDN rules create a managed Azure Firewall, about €254–803 a month at list price [N1, N2, N6, R6].
4. **Gateway routing is optional per tool.** Only *new* portal-made MCP tools route through Foundry's AI gateway, and a request header can override a deployment's guardrail. *Only the gateway is reachable* has to be enforced by the network [C6, G7].
5. **Each Foundry agent gets its own Entra agent identity with no permissions.** Conditional Access for agents and agent-level Defender protection need Agent 365 (or Microsoft 365 E7) licences [I1, I3, I7].
6. **Region is decisive.** Sweden Central is the only EU region present in every list checked. West Europe lacks managed VNet, SRE Agent, cloud red teaming, Groundedness Pro and agent-playground evaluations; North Europe lacks Agent Service [N8, N6, R3, E2, E1].
7. **Agent Framework 1.0 is GA (2 Apr 2026, MIT)**, but the Foundry hosting, durable, A2A and .NET AG-UI packages are pre-release; Foundry hosted agents themselves are GA [F3, F11, F17].
8. **Human-in-the-loop and checkpointing are native.** Pending requests survive a restart; the checkpoint store is a trust boundary [F6, F7].
9. **Azure SRE Agent bills 4 AAU an hour per agent even when idle** (about €283 a month in Sweden Central). Stopping it does not stop billing [R1, R6].
10. **Budgets only alert and Azure OpenAI has no hard cap**, so token limits must live in the gateway [C11, C5].

**Counts.** 63 capabilities rated (62 table rows plus Copilot Studio): 27 ADOPT · 11 ADOPT-PREVIEW · 16 EVALUATE · 7 WATCH · 2 N/A. Where a row carries two dispositions, the first is counted.

## 2. Foundry Control Plane and fleet governance (GOV · GW · OBS)

| Capability | Status | What matters | Disp. |
|---|---|---|---|
| **Control Plane** (Operate: Overview, Assets, Compliance; Manage: Quota, AI Gateway) | Public preview 18 Nov 2025 (att.); observability core GA 22 Apr 2026 [C12]; overview labels only some panes preview [C1] | Portal only. Discovers Foundry prompt, workflow and hosted agents, Azure SRE Agent, Logic Apps agent loops and registered custom agents; classic agents and Assistants excluded. Reader views, **Contributor can start, stop or block**, Owner manages. Shows each agent's Entra identity. No separate price stated [C1, C2] | ADOPT (inventory, kill switch, fleet monitoring) |
| **Custom-agent registration** | Preview [C10] | Foundry puts APIM in front and issues a new URL that clients must use. Needs an AI gateway, a reachable endpoint (HTTP or A2A) and OTel GenAI telemetry sent to the project's App Insights [C3] | EVALUATE (non-Foundry runners such as the Move runner) |
| **Foundry AI Gateway** (project-level APIM) | Not stated; APIM "AI Gateway tier" preview (att.) | Existing APIM must be a v2 tier in the **same tenant and subscription**; "create new" makes Basic v2. Per-project TPM limit (429) and token quota from hourly to yearly (403). A gateway made in the UI is public, so a private Foundry needs private APIM. Page says "free to set up"; the APIM instance still bills [C3, C4, C5, N2] | EVALUATE (Citadel supersedes it) |
| **MCP governance via gateway** | Public preview [C6] | Only *new* portal-created MCP tools without managed OAuth are routed. SharePoint, OpenAPI, code-first and managed-OAuth tools are excluded; no tool traces; policies editable only in the Azure portal | WATCH (use Citadel publish contracts) |
| **Bring your own model or gateway** | GA 27 Apr 2026 (att.); page unlabelled [C7] | Prompt agents only; Responses API "isn't supported at present"; you supply content filters; private pattern is Bicep template 16 [C7, N1] | EVALUATE (prompt agents only) |
| **Policy** (guardrail policy and built-ins) | Approved-models and eligibility policies GA; model-router policies preview [C9] | The Compliance pane creates Azure Policy over model deployments (subscription or resource-group scope, exceptions; deleting in the portal deletes the assignment). Assign as code; effect in about 15 minutes, compliance within 24 hours [C8, C9] | ADOPT |
| **Cost and quota** | Project-level attribution preview, Azure-sold models only [C11] | Budgets alert only; hard caps belong in gateway token limits [C5, C11] | ADOPT (gateway caps) |
| **Agent 365 integration** | Agent 365 GA 1 May 2026 [I6]; enable/disable of Foundry agents GA 18 Sep 2026 (att.) | Registry sync for prompt and hosted agents; telemetry needs a licence; data follows the Entra tenant's region, so opt out per Foundry resource [I5] | EVALUATE |

**Behind Citadel:** Control Plane sees Foundry-native agents whatever the gateway. Foundry's token limits (project × deployment) duplicate Citadel's per-contract limits, so choose one source of truth (Citadel). Registering a custom agent adds a second APIM proxy in front of it.
**Price:** no Control Plane charge is stated [C1]; costs arise in APIM, Application Insights and Agent 365 licences. **Limit that matters:** with BYO VNet about 250 projects per Foundry resource at low traffic [N3].

## 3. Guardrails and controls (SEC · AGT)

| Capability | Status | What matters | Disp. |
|---|---|---|---|
| **Model guardrails** | Not stated; unmarked while the preview controls are marked [G1] | `Microsoft.DefaultV2`: four harm classes at Medium, jailbreak, protected material. Core-harm and jailbreak on, **document attack off**. Turning output harms off needs approval. About 50–100 ms per intervention point [G1, G2, G5] | ADOPT |
| **Agent guardrails** (input, tool call, tool response, output) | Public preview [G1] | The agent's policy fully overrides the model's. Applies only to Foundry Agent Service agents, not other registered agents. "Annotate" is unavailable; Spotlighting and Groundedness are unsupported for agents [G1] | ADOPT-PREVIEW (fallback: model guardrail, gateway, MAF middleware) |
| **Tool-call and tool-response screening** | Public preview | Works only for AI Search, Functions, OpenAPI, SharePoint, Fabric data agent, Bing and Browser Automation. **Not** MCP, A2A, Code Interpreter or File Search [G2] | ADOPT-PREVIEW |
| **Hosted-agent specifics** | Public preview | No `rai_config` means no guardrail. A nonexistent policy **fails open**. Sync (buffered) or async output; the Invocations protocol needs moderation paths; WebSocket has none; a block is HTTP 400 `content_filter`, or a terminal error event when output was streamed [G3, G4] | ADOPT-PREVIEW |
| **Prompt Shields** | Not stated; unmarked for models [G1] | Wrap external text in the `<documents>` delimiter or indirect-attack detection does not see it. Configure separately from harm levels [G7] | ADOPT |
| **Task Adherence** | Public preview | API `2024-12-15-preview`; ≤100,000 characters; English-tested. Data "may be routed to and processed in other US and EU regions outside the specified Geo" [G6] | EVALUATE (residency) |
| **PII filter** | Public preview | Scans model completions only [G8] | EVALUATE |
| **Groundedness detection** | Preview; Azure OpenAI retirement 30 Apr 2027 [G1] | Models only | N/A (use evaluators) |
| **Network egress controls** | Public preview (`2026-05-15-preview`) | Hosted agents only. Ordered host rules (allow, deny, transform, rewrite), default deny, Audit then Enforce, 480 rules, fail-closed. Not enforced through Azure Policy; "not intended to be used in production" [G4] | ADOPT-PREVIEW (fallback: hub firewall) |

**Where configured:** portal Build › Guardrails; ARM `raiPolicies` plus `raiPolicyName` on a deployment; hosted-agent definition (`rai_config`, `rai_policy_name`; azd ≥1.0.0-beta.12, SDK ≥2.2.0); request header `x-policy-id`, which **overrides the deployment's guardrail for that call**; fleet policy in Operate › Compliance [G4, G7, C8].
**Behind Citadel:** deployment-level guardrails still apply to calls made through the gateway, but the gateway must strip or force `x-policy-id` (inference). Agent-boundary guardrails sit outside the gateway. For a BYOM connection the page makes content filtering your responsibility [C7].
**Price:** no guardrail meter is stated on these pages (Content Safety billing and regions are linked, not fetched: `UNVERIFIED`).

## 4. Agent identity (ID · SEC)

| Capability | Status | What matters | Disp. |
|---|---|---|---|
| **Foundry agent identity** | Not stated; sub-features preview | A blueprint and an agent identity are created with each agent. They start with **no permissions**; a federated credential trusts a Microsoft first-party app, so no secret exists. Hosted code gets tokens only from the token service, never the project identity. Moving from the legacy shared project identity changes the principal and role assignments do not transfer [I1] | ADOPT |
| **Entra Agent ID platform** | "available for all Microsoft Entra customers" (no date) [I2] | Blueprints, identities, agent users, **owners and sponsors with expiry** (the H9 sponsor), sign-in and audit logs; third-party agents via sidecar or workload identity federation [I1, I2] | ADOPT |
| **Conditional Access, Identity Protection, governance for agents** | Licence-gated | Needs M365 E7, or Agent 365 plus Entra P1 or M365 E3 [I3]. OBO calls are judged against the *user*; API-key access bypasses CA; the blueprint's own Graph-provisioning tokens are exempt [I3] | EVALUATE (cost) |
| **Agent registry** | Agent 365 GA 1 May 2026; Entra registry converged into Agent 365 [I4, I6] | Viewing the inventory needs the AI Reader role, no licence; applying controls needs one [I4] | ADOPT (view) |
| **OBO and user-delegated tools** | Agent-identity-as-actor preview [I8] | Foundry-as-actor works only for Microsoft-owned tools. The `AgentBlueprint` endpoint scheme is preview and serves direct runtime clients; Foundry dev clients and **Azure Bot integrations stay on the Foundry audience**, so no agent-identity OBO there (inference) [I8] | WATCH |
| **Foundry RBAC** | Not stated; unmarked [I9] | Foundry Agent Consumer (call endpoints only), User, Project Manager, Account Owner, Owner. Role assignments at **agent scope** apply to endpoint access only; the portal assigns Agent Consumer only at account scope, so use CLI or IaC for project or agent scope. Keys bypass RBAC. Roles were renamed from "Azure AI …"; IDs unchanged [I9] | ADOPT |
| **Hosted-agent isolation** | Platform GA; MAF hosting packages pre-release [F17] | Each session is a VM-isolated sandbox with no blueprint credential. User isolation and session isolation are separate controls [I1, F17] | ADOPT |

**Behind Citadel:** the hosted-agent token service supplies the agent-identity token, so a Citadel contract can validate a per-agent principal (inference). Tool connections choose agent identity, project managed identity or keys; only the first carries a per-agent identity [I1].
**Price:** the Agent ID platform needs no licence; Conditional Access, identity governance and Defender protection for agents need per-user Agent 365 (trial: 25 seats for 30 days) [I2, I3, I7].

## 5. Networking (NET)

| Capability | Status | What matters | Disp. |
|---|---|---|---|
| **Private endpoint (inbound)** | Not stated; unmarked [N2] | `publicNetworkAccess`: disabled, or selected IPs. Endpoint in the VNet's region and subscription; avoid 172.17.0.0/16 [N2] | ADOPT |
| **BYO-VNet agent injection** | Agent Service GA (page; 16 Mar 2026 att.) [N8] | Subnet delegated to `Microsoft.App/environments`, /27 minimum, /24 advised, RFC 1918. Same region as the account. Account-level, set at creation, **cannot be changed**. One session uses about one IP: ~20 sessions in a /27, ~250 in a /24 (1:10 on request). About 250 projects, as few as 25 under load. No IP-use metric: watch HTTP 429 `subnet_exhausted` [N1, N3] | ADOPT |
| **Standard setup and capability hosts** | Not stated; unmarked (Agent Service itself is GA [N8]) | Cosmos DB (threads), AI Search (vectors), Storage (files) in your tenant; CMK only in standard setup. Account **and project** capability hosts are needed, or tool calls fail with "name or host unknown". REST/ARM only; no update, delete and recreate. Private endpoints to the BYO resources are **not** auto-created. BYO VNet can use platform-managed data instead [N1, N2, N4, N5]. [N4] is "retained for reference" and points to a newer "capability settings" page that did not load, and [N6] says projects inherit account values: host semantics are `UNVERIFIED` | ADOPT (as IaC, spike first) |
| **Managed VNet** | GA May 2026 (att.); CLI group preview [N6] | No IP planning. Outbound mode *Allow only approved outbound* plus FQDN rules creates a managed **Azure Firewall** (Standard default, Basic selectable). Ports 80 and 443 only; no outbound logging; no BYO firewall; cannot be disabled afterwards. Regions listed exclude West Europe and North Europe [N6] | WATCH (cost, regions) |
| **Network security perimeter** | Not stated on the Foundry page (att. GA 18 Nov 2025; the OpenAI page is titled preview) | Transition, Enforced and Audit modes; Enforced overrides `publicNetworkAccess` [N7] | EVALUATE |
| **Hub-spoke and firewall** | Not stated; unmarked [N2] | Allow `*.identity.azure.net`, Entra login hosts, App Insights endpoints and the AzureMachineLearning tag; the Agent 365 endpoint is optional (`a365LoggingEnabled`) [N2] | ADOPT |

**Tools behind isolation [N2]:** *via your subnet*: private MCP, OpenAPI, Functions, A2A; *private endpoint*: AI Search, File Search; *backbone*: Code Interpreter, function calling. *Public endpoint*: Bing, web search, SharePoint grounding (block by Azure Policy if unwanted). *Unsupported*: Fabric data agent, Logic Apps, Browser Automation, Computer Use, Image Generation. Workflow agents get no outbound injection.
**Behind Citadel:** every tool call leaves through the single-tenant data proxy in the delegated subnet [N3], so a route table to the hub firewall can see it (inference). A Foundry-plus-APIM private reference exists (template 16) [N1].
**Price:** private endpoints bill as Private Link (A5, P1); the managed VNet itself is free [N6]; standard setup adds Cosmos DB, AI Search and Storage.

## 6. Observability (OBS)

| Capability | Status | What matters | Disp. |
|---|---|---|---|
| **Tracing** | GA for prompt and hosted agents; preview for workflow and external agents [O1] | Available wherever Foundry is. OTel GenAI conventions are "Development" status. Spans: `invoke_agent`, `plan`, `invoke_workflow`, `execute_tool`, memory. Stored in App Insights (Log Analytics Reader to view). Traces appear in 2–5 minutes. Record content only in development [O1, O3] | ADOPT |
| **Sensitive-content table** | Public preview [O2] | `AppGenAIContent` as a protected table; read with Privileged Monitoring Data Reader. Since **30 Sep 2026** new prompt and tool values land only there. Opt-out flag ends 30 Sep 2027 [O2] | ADOPT-PREVIEW |
| **Agent monitoring dashboard and alerts** | Recurring evaluations, red-team scans and alerts preview [O4] | Tokens, latency, success rate. The pricing page says "no charge for monitoring"; Application Insights ingestion bills [O4, O6] | ADOPT-PREVIEW |
| **Microsoft OpenTelemetry distro** | Not stated | `microsoft-opentelemetry` adds agent attributes for MAF agents outside Foundry [O3] | EVALUATE |
| **Insights, trace replay** | Insights public preview 24 Sep 2026 [O7] | Mines traces for recurring behaviour | WATCH |

**Behind Citadel:** gateway logs and Foundry traces are separate stores; correlate them with a shared request ID (inference). Foundry also offers diagnostic logging of platform logs and metrics to Azure Monitor [C10]. Plan table tiers and retention in A5.
**Price:** Foundry charges nothing for monitoring or tracing; Application Insights and Log Analytics ingestion and retention bill [O1, O6].

## 7. Evaluation and red teaming (EVAL)

| Capability | Status | What matters | Disp. |
|---|---|---|---|
| **Built-in evaluators** | Mixed GA and preview [E4] | General, similarity, RAG, risk and safety, agent, rubric, OpenAI graders, custom (preview). Most agent evaluators are preview. Composite "Output Quality" and "Tool Use Quality" (preview) batch several judges into one call. Limits: 2 MB a row, 100,000 rows a batch, run creation rate-limited per tenant, subscription and project [E4, E1] | ADOPT / ADOPT-PREVIEW |
| **Billing** | — | Quality and continuous evaluations are billed as tokens on **your** judge deployment, no surcharge. Safety, red-team and playground evaluations use a separate meter (price not rendered). **Playground evaluations are on by default** [O5, O6] | — |
| **Continuous and scheduled evaluation** | Preview in the dashboard [O4] | Samples live traffic; default `max_hourly_runs` is 100; needs Foundry User on the project identity; custom evaluators allowed [O4] | ADOPT-PREVIEW |
| **AI Red Teaming Agent** | No label on pages (preview in att., 25 Nov 2025) | PyRIT; local = content-risk classes; cloud adds prohibited actions, sensitive-data leakage, task adherence (single-turn, English-only, synthetic). Targets Foundry prompt and hosted-container agents using Azure tools; **not** workflow agents, function tools, non-Azure tools or non-Foundry agents [E2, E3] | EVALUATE (fallback: local PyRIT) |
| **Datasets and analysis** | Not stated | Synthetic Q&A and multi-turn simulation seeds; trace-to-dataset (available in West Europe); human evaluation and cluster analysis of failures [E1, E6, C10, C1] | EVALUATE |
| **CI integration** | GitHub Action preview (`microsoft/ai-agent-evals`); azd evaluation preview [E5] | Evaluates named agent versions against a baseline with confidence intervals; Azure Login with OIDC [E5] | ADOPT-PREVIEW |
| **Agent optimizer** | Preview | Tunes hosted-agent instructions and skills from evaluation results [C10] | WATCH |

**Behind Citadel:** the judge deployment is a normal model call, so route it through the gateway and give it its own contract and token budget. Regions: see §13.

## 8. Microsoft Agent Framework (FW · AGT · TOOL)

| Capability | Status | What matters | Disp. |
|---|---|---|---|
| **Core** | GA 1.0, 2 Apr 2026 (.NET and Python); MIT. Python 1.24.0 and .NET 1.27.0 on 30 Oct 2026. Go v0.2.1 public preview [F2, F3, F1] | Agents, middleware, memory providers, graph workflows, orchestrations, declarative YAML, MCP and A2A are "stable"; successor to Semantic Kernel and AutoGen (archived) [F3, F23] | ADOPT |
| **Pre-release or experimental pieces** | Not GA | DevUI beta; `hosting-a2a` alpha; Foundry hosting packages; Durable extension (v1.16 preview); Cosmos checkpoint and memory; AG-UI .NET; FIDES; functional workflows (Python) [F2, F4, F9, F14, F16] | — |
| **Graph workflows** | GA | Supersteps, typed executors, fan-out and fan-in, sub-workflows, workflow-as-agent. Declarative workflows 1.0 in both SDKs (23 Jul 2026) [F4, F5, F20] | ADOPT |
| **Checkpoints** | GA; breaking change in Python 1.13.0 [F6] | Saved at superstep ends with pending requests. Stores: in-memory, file, Cosmos DB, `FoundryCheckpointStore`; the protocol allows a custom store. Python uses a restricted pickle; "Never load checkpoints from untrusted or potentially tampered sources" [F6] | ADOPT |
| **Human-in-the-loop** | GA | `RequestPort` or `request_info` plus tool approval; restoring a checkpoint re-emits pending requests [F7] | ADOPT |
| **Orchestrations** | GA | Sequential, concurrent, handoff, group chat, Magentic [F8, F3] | ADOPT |
| **Hosting** | Foundry hosted agents GA; MAF hosting packages and Python self-hosting pre-release [F9, F11, F17] | Responses, Invocations, Activity (Microsoft 365), A2A, MCP-tool and AG-UI endpoints. Python can host a native workflow; Python resilient background responses tie checkpoints to hosted sessions. .NET 10 or Python 3.10+ [F9, F11, F16] | ADOPT-PREVIEW |
| **Durable Extension** | Pre-release | Functions (Flex Consumption, scale to zero) or your own compute; Durable Task Scheduler; waits "without consuming compute or model tokens"; reliable streaming needs Redis [F10] | ADOPT-PREVIEW (fallback: checkpoint and queue resume) |
| **A2A** | Protocol v1.0 stable (28 Apr 2026); MAF packages preview [F18] | JSON-RPC and HTTP+JSON bindings, agent cards, long-running tasks with continuation tokens [F19]. Foundry's A2A tool and endpoints use v1.0, older `a2a_preview` and 0.3 stay preview, cards require Entra authentication [X1] | ADOPT-PREVIEW |
| **AG-UI and DevUI** | Preview; AG-UI Python stable, .NET preview; DevUI beta tag [F12, F16, F2] | AG-UI needs app-level authentication [F16]. DevUI is a local debugger: never deploy it | WATCH (AG-UI); ADOPT (DevUI, dev only) |
| **Middleware and safety** | Middleware GA | Purview middleware needs M365 E5 plus pay-as-you-go, fails closed, buffers streams [F13]. **FIDES** (experimental, Python) labels content trusted or private and blocks privileged tools before they run [F14]. **AGT** (MIT, v4.1.0, 9 Jun 2026) adds policy, capability and audit middleware [F15] | EVALUATE / ADOPT-PREVIEW (FIDES) |
| **Memory** | Foundry memory preview; Cosmos memory Python preview | `FoundryMemoryProvider`, Azure AI Search provider, history stores [F16, F12] | EVALUATE (A2, A5) |
| **Harness, skills, CodeAct** | Harness stable 22 Jul 2026 [F21]; skills stable (att.); CodeAct preview | Harness: tool loop with iteration cap, compaction, todos, file memory, approvals. Hyperlight isolates model-written code only; registered tools run in your runtime [F21, F16] | EVALUATE |
| **OpenTelemetry** | Not stated (Foundry integration was preview at 1.0 [F3]) | Traces, metrics, logs per GenAI conventions ("Development" status [O1]); default source name `Experimental.Microsoft.Agents.AI` [F22] | ADOPT |
| **Foundry UI workflows** | **Retiring 1 Dec 2026** [F24] | Use MAF instead | N/A |

**Behind Citadel:** MAF's model, MCP and A2A clients are plain HTTP clients, so base URLs can point at the gateway (inference). Agents that use Foundry's own service-side tool connections bypass any code-level gateway setting.
**Price:** the framework is free (MIT); you pay for hosting (hosted-agent compute in A2, Functions or Container Apps in A5), Durable Task Scheduler and Redis if used, and model tokens. **Languages:** .NET and Python GA; Go public preview, without declarative agents, CodeAct or functional workflows [F1].

## 9. Microsoft 365 Agents SDK and Teams delivery (CHAN)

| Capability | Status | What matters | Disp. |
|---|---|---|---|
| **Agents SDK** | Not stated; stable 1.x releases, MIT: .NET v1.9.205 (19 Oct 2026), JS v1.9, Python v1.9.0 [M2] | C# (.NET 8), JavaScript (Node 18+), Python 3.9–3.11 per page; AI-agnostic channel layer with turn state [M1] | ADOPT (Teams front end) |
| **Adaptive Cards** | — | `Action.Execute` and `Submit` handlers exist in .NET and JavaScript; **not in the Python SDK** [M3] | ADOPT (.NET or JS) |
| **Azure Bot resource** | Not stated | User-assigned managed identity, Teams channel. Free tier: unlimited standard-channel messages; premium per 1,000 [M4, M6]. Local data residency for West Europe; host the bot in the same locality [M4, M5] | ADOPT |

**Behind Citadel:** Teams traffic is outside the gateway; model calls made by the bot's agent code go through it. A Foundry agent can be published to Teams or Microsoft 365 while its public access is disabled, with extra setup [N2]; that route is A2's. The Teams SDK is `UNVERIFIED` here.
**Price:** SDK free; the Azure Bot resource has a free tier (standard channels); whether Teams counts as a standard channel is `UNVERIFIED` [M6].

## 10. Azure MCP Server (TOOL · OPS)

| Capability | Status | What matters | Disp. |
|---|---|---|---|
| **Azure MCP Server 3.0** | GA 12 Oct 2026; MIT; `microsoft/mcp`; 4.0 beta already shipping (29 Oct) [T1] | Toolsets include Advisor, **Optimization** (ranks cost recommendations by impact and estimated annual savings), Monitor, Cosmos, Backup, SRE Agent (55 commands). A read-only mode exists; anti-SSRF validation; `advisor recommendation apply` only returns IaC rules [T1] | ADOPT (read tools) |
| **Remote hosting** | Self-hosted on Container Apps [T2] | Two templates: managed identity (the project identity needs the app role `Mcp.Tools.ReadWrite.All`) or on-behalf-of the user [T2] | ADOPT |

**Behind Citadel:** expose it through a publish contract so tool calls are logged and rate-limited (inference). Give the server a dedicated read-only managed identity; the threat-model post warns against reusing an engineer's session [T3].
**Price:** the server is free open source; you pay for the Container Apps host and the Azure calls it makes (A5).

## 11. Azure SRE Agent as operator of our platform (OPS · COST)

| Capability | Status | What matters | Disp. |
|---|---|---|---|
| **Azure SRE Agent** | GA 11 Mar 2026 (att.); VNet integration GA 26 Aug 2026 (att.); evaluation for new customers waives always-on (30 days, att.) [R1] | Billing in AAUs: **always-on 4 AAU per agent-hour** until deleted, plus token-based active flow. Monthly AAU limit (500–1,000,000) caps active flow only. Review mode is the agent default but **response plans and scheduled tasks default to Autonomous**; approval prompts cover Azure infrastructure operations only. Its own governance: tool access allow, ask or deny, hooks, Bicep deployment, managed identity with RBAC [R1, R2, R4] | EVALUATE (default off) |
| **Regions** | — | EU: France Central, Italy North, Spain Central, Sweden Central, UK South. Region fixed at creation; subscription registration may be needed [R3] | — |
| **Azure Copilot Observability Agent** | GA 23 Jun 2026; autonomous operations preview [R7] | Billed per use in Azure Agent Credits from 1 Jul 2026, 500 AAC cap per operation [R8] | EVALUATE |

Indicative cost (retail API, 31 Oct 2026): €0.0968 per AAU in Sweden Central, so always-on 2,920 AAU a month ≈ **€283**; a quick question on Claude Opus 4.6 ≈ 3.8 AAU ≈ €0.37, an incident investigation ≈ 35 AAU ≈ €3.4 [R1, R6]. **Behind Citadel:** its model calls are service-managed and so presumably bypass our contracts and token budgets (inference).

## 12. Copilot Studio (comparison only)

Billed in Copilot Credits since 1 Sep 2025 through pay-as-you-go, prepaid packs or a prepurchase plan [P1]. It suits user-facing Microsoft 365 agents, not the reasoning plane: it offers no gateway contract model, no hosted code and no per-agent token budget (inference). Disposition: **WATCH**.

## 13. EU region matrix (what each list actually says)

| Capability | West Europe | Sweden Central | France Central | Germany W. Central |
|---|---|---|---|---|
| Agent Service with private VNet [N8] | ✔ | ✔ | ✔ | ✔ |
| Managed VNet [N6] | ✘ | ✔ | ✔ | ✔ |
| SRE Agent [R3] | ✘ | ✔ | ✔ | ✘ |
| Cloud red teaming [E2] | ✘ | ✔ | ✔ | ✘ |
| Groundedness Pro [E1] | ✘ | ✔ | ✘ | ✘ |
| Risk and safety evaluators; batch evaluations [E1] | ✔ | ✔ | ✔ | ✔ |
| Agent-playground evaluations [E1] | ✘ | ✔ | ✔ | ✔ |
| Copilot harness (preview) [N8] | ✔ | ✔ | ✘ | ✔ |

North Europe appears only in the batch-evaluation list. The two red-teaming region lists disagree: [E2] names East US 2, France Central, Sweden Central, Switzerland West and North Central US; [E1] names only East US 2 and North Central US.

## 14. Cost levers

| Lever | Driver | Evidence |
|---|---|---|
| Managed-VNet firewall | Azure Firewall hours | Standard €1.10 an hour ≈ €803 a month; Basic €0.3476 ≈ €254 (West Europe, retail, data processing extra) [R6] |
| SRE Agent | 4 AAU an hour plus tokens | See §11 |
| BYO data resources | Cosmos DB, AI Search, Storage | Platform-managed data is allowed with BYO VNet [N1]; prices in A5 and P1 |
| AI gateway | APIM tier | Basic v2 by default [C4]; sizing in A1 |
| Evaluation | Judge tokens; safety meter; playground default | Composite evaluators cut input tokens 61–71% (att.) [O5, O6] |
| Telemetry | App Insights ingestion | No Foundry surcharge [O6]; plans in A5 |
| Licences | Agent 365 per user; Purview middleware needs E5 | Trial: 25 seats for 30 days [I6, I7, F13] |
| Durability | Durable Task Scheduler; Redis for streaming | [F10]; A5 |

## 15. Defence-in-depth map

| Layer | Controls (status) | As code? |
|---|---|---|
| Fleet | Control Plane inventory and Contributor "block" (preview); Azure Policy approved-models (GA) | Policy yes; Operate panes no |
| Network | Private endpoints, BYO-VNet injection, hub firewall (no preview label); host egress rules (preview); NSP (not stated) | Yes |
| Identity | Per-agent identity, scoped RBAC, Agent Consumer role at agent scope (no preview label); Conditional Access (licence) | Yes |
| Gateway | Token limits, content safety, JWT validation (A1) | Yes |
| Model | DefaultV2 plus document-attack control; request-header override must be closed | Yes (`raiPolicies`) |
| Agent boundary | Agent guardrails at four points (preview) | Yes (agent definition) |
| Tool | Approval-gated tools (MAF HITL, GA); FIDES labels (experimental); AGT capability guard; read-only Azure MCP | Code |
| Data | Protected telemetry table (preview); CMK (standard setup); trusted checkpoint store | Yes |
| Assurance | Tracing (GA); continuous evaluation and scheduled red teaming (preview); CI gates (preview) | Mostly |

## 16. Design implications

1. **H1.** Run MAF graph workflows inside Foundry hosted agents; use prompt agents for simple roles. Do not use Foundry UI workflows (retiring, no VNet outbound, not red-teamable). Pin MAF and hosting versions (weekly releases, pre-release hosting) and run the Exam on every bump [F24, N2, E2, F2].
2. **H1 and H4.** An approval is a `RequestPort` or `request_info` plus a persisted checkpoint. Use the Cosmos or Foundry checkpoint store, or implement `CheckpointStorage` for the chosen operational database, and treat it as trusted infrastructure. For multi-day waits use the Durable Extension, falling back to checkpoint plus queue-triggered resume in Container Apps jobs [F6, F7, F10].
3. **H2.** Make the gateway the only reachable endpoint: configure model, tool and A2A clients in code with the Citadel base URL; allow only that FQDN in the hub firewall; add Foundry egress rules in Audit then Enforce (preview; `Rewrite` can redirect to the gateway). Do not rely on portal MCP routing. Strip or force `x-policy-id`. Use BYOM connections only for prompt agents [C6, G4, G7, C7].
4. **H3.** One Foundry account per environment, BYO VNet in the spoke, /24 delegated subnet, project-level capability host, no mixing of basic and standard setups. Projects are the isolation unit (data is not shared between them), so one project per agent group and environment mirrors Citadel access contracts (inference). Choose platform-managed or BYO data by cost and CMK need. The network cannot be changed later [N1, N3, N4, N5].
5. **Region.** Prefer Sweden Central unless model or Data Zone constraints (A2) force West Europe, which gives up managed VNet, SRE Agent, cloud red teaming, Groundedness Pro and playground evaluations (§13).
6. **H4 and H9.** Give each agent its own identity and grant read-only roles to reasoning-plane agents only. Use Foundry Agent Consumer at agent scope for caller-to-agent access. Decide licence versus compensating controls for Conditional Access on agents (A4). Never use the project identity in hosted code [I1, I3, I9].
7. **H8.** Enable DefaultV2 and document-attack detection; wrap untrusted text in `<documents>`; use agent guardrails (preview) on input and output. Tool-response screening skips MCP and A2A, so add gateway content safety, FIDES or AGT middleware and approval-gated write tools. Check Task Adherence residency first [G1, G2, G7, F14, F15].
8. **H9 and H10.** Approvals are authenticated by the human's Teams and Entra identity in our own approval service built on the Agents SDK in .NET or JavaScript (Python lacks card routing), not by agent OBO, which Azure Bot integrations apparently cannot use (inference). Use an Azure Bot resource with a user-assigned identity in West Europe for local residency [M3, M4, M5, I8].
9. **H11.** Drift controls: Azure Policy approved-models plus model-router policies; Control Plane Compliance on top; pinned agent versions; continuous and scheduled evaluation (100 runs an hour by default) and scheduled red teaming (preview, local PyRIT fallback); NSP and egress rules in Audit then Enforce; the Contributor "block" action as kill switch [C9, O4, E2].
10. **H12.** Gate releases with `ai-agent-evals` (preview) or SDK scripts, OIDC, named agent versions and a baseline; use composite evaluators and route the judge through the gateway [E5, E4].
11. **H6 and H7.** Skip the managed-VNet firewall; keep SRE Agent off by default; disable playground evaluations; sample continuous evaluation; enforce hard caps at the gateway [N6, R1, O5, C11].
12. **Operator tooling.** Publish Azure MCP Server (read-only, dedicated managed identity) as a Citadel tool for Surveyor and Detective; trial SRE Agent in a non-production spoke (new customers get a 30-day evaluation without the always-on charge, att.) [T1, T2, R1].

## 17. Gotchas

- Guardrail fail-open: a missing policy deploys an active agent with no filtering [G3].
- Subnet exhaustion is silent and the project cap can fall to about 25 [N3].
- Without a project-level capability host, tool traffic fails and nothing is inherited from the account [N2, N4]; see the contradiction below.
- Indexers default to multitenant execution: private AI Search then indexes nothing silently unless `executionEnvironment` is `Private` [N2].
- Public-endpoint tools (Bing, web search, SharePoint grounding) leave the network [N2].
- Pages contradict each other on CGNAT ranges [N1, N3], red-teaming regions [E1, E2], Agent 365 prerequisites (Frontier programme versus GA) [I5, I6], managed-VNet regions [N6], capability host versus capability settings semantics [N4, N6] and hosted-agent status ("preview" in [N2], GA in [F11]). Take the more restrictive reading until a spike proves otherwise.
- The Contributor "block" action is a fleet kill switch, so scope that role carefully [C2].
- Since 30 Sep 2026 prompt and tool values are only in `AppGenAIContent`; old queries and alerts break [O2].
- Evaluators are LLM judges, so results vary; agentic red-team classes are single-turn, English-only and synthetic [E2].
- Python 1.13.0 changed checkpoint ordering; telemetry source name is `Experimental.…` [F6, F22].
- Azure MCP 4.0 betas ship weekly; its SRE Agent toolset needs the `Microsoft.App/SREAgentPreview` provider [T1].
- Foundry RBAC names changed; older IaC and policy text may still say "Azure AI User" [I9].
- Defender agent-level discovery and threat protection need Agent 365 since 1 Jul 2026; CSPM still discovers accounts and projects [I7].

## 18. Could not verify (`UNVERIFIED`)

- All `azure.microsoft.com/updates` pages are script-rendered, so these dates are (att.) only: SRE Agent GA, VNet-integration GA, managed-VNet GA, Control Plane and Agent ID preview, MAF tracing preview, APIM content safety for MCP and A2A, enable/disable of Foundry agents in Agent 365.
- SRE Agent and Foundry observability price tables show "$-" [R5, O6]; the AAU price comes only from the Retail Prices API [R6].
- Agent 365 list price; overall Control Plane GA label; Entra Agent ID GA date; AI Red Teaming Agent status label; NSP preview versus GA and price; whether Control Plane has an API; Task Adherence data scope.
- The "capability settings" page that [N4] points to; Content Safety region availability and any guardrail billing (linked, not fetched).
- Whether Teams counts as a free standard Bot channel; the Teams SDK versus Agents SDK split.
- Whether SRE Agent model calls can be routed through a customer gateway.
- Composite-evaluator token savings (att.); hosted-agent pricing (A2).

## 19. Sources (all fetched 2026-10-31)

**Control Plane and governance** — C1 `learn.microsoft.com/en-us/azure/foundry/control-plane/overview` · C2 `…/control-plane/how-to-manage-agents` · C3 `…/control-plane/register-custom-agent` · C4 `learn.microsoft.com/azure/foundry/configuration/enable-ai-api-management-gateway-portal` · C5 `…/control-plane/how-to-enforce-limits-models` · C6 `…/agents/how-to/tools/governance` · C7 `…/agents/how-to/ai-gateway` · C8 `…/control-plane/quickstart-create-guardrail-policy` · C9 `…/how-to/model-deployment-policy` · C10 `…/concepts/capability-reference` · C11 `…/concepts/manage-costs` · C12 `devblogs.microsoft.com/foundry/from-local-to-production-the-complete-developer-journey-for-building-composing-and-deploying-ai-agents/` (all `learn.microsoft.com/azure/foundry/…` unless shown).
**Guardrails** — G1 `…/guardrails/guardrails-overview` · G2 `…/guardrails/intervention-points` · G3 `…/agents/concepts/hosted-agent-guardrails` · G4 `…/agents/how-to/add-hosted-agent-guardrails` · G5 `…/guardrails/default-safety-policies` · G6 `…/guardrails/task-adherence` · G7 `…/guardrails/how-to-create-guardrails` · G8 `…/openai/concepts/content-filter-personal-information`.
**Identity** — I1 `…/agents/concepts/agent-identity` · I2 `learn.microsoft.com/entra/agent-id/what-is-microsoft-entra-agent-id` · I3 `learn.microsoft.com/entra/identity/conditional-access/agent-id` · I4 `learn.microsoft.com/entra/agent-id/agent-registry-convergence` · I5 `…/agents/concepts/agent-365-integration` · I6 `learn.microsoft.com/en-us/microsoft-agent-365/overview` · I7 `learn.microsoft.com/defender-xdr/security-for-ai/transition-agent-security-to-agent-365` · I8 `…/agents/concepts/user-delegation` · I9 `…/concepts/rbac-foundry`.
**Networking** — N1 `…/agents/concepts/networking-options` · N2 `…/how-to/configure-private-link` · N3 `…/agents/concepts/agents-networking-deep-dive` · N4 `…/agents/concepts/capability-hosts` · N5 `…/how-to/configure-capability-settings` · N6 `…/how-to/managed-virtual-network` · N7 `…/how-to/add-foundry-to-network-security-perimeter` · N8 `…/agents/concepts/limits-quotas-regions`.
**Observability and evaluation** — O1 `…/observability/concepts/trace-agent-concept` · O2 `…/observability/how-to/traces-sensitive-content` · O3 `…/observability/how-to/trace-agent-framework` · O4 `…/observability/how-to/how-to-monitor-agents-dashboard` · O5 `…/concepts/observability` · O6 `azure.microsoft.com/en-us/pricing/details/foundryobservability/` · O7 `techcommunity.microsoft.com/t5/microsoft-foundry-blog/insights-in-foundry-turns-agent-traces-into-action/ba-p/4559634` · E1 `…/concepts/evaluation-regions-limits-virtual-network` · E2 `…/concepts/ai-red-teaming-agent` · E3 `…/how-to/develop/run-ai-red-teaming-cloud` · E4 `…/concepts/built-in-evaluators` · E5 `…/how-to/evaluation-github-action` · E6 `…/observability/how-to/evaluation-dataset-synthetic`.
**Agent Framework** — F1 `learn.microsoft.com/agent-framework/overview/` · F2 `github.com/microsoft/agent-framework` plus `gh api` releases of it, of `agent-framework-go`, `agent-framework-durable-extension` and `agent-governance-toolkit` · F3 `devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/` · F4 `learn.microsoft.com/agent-framework/concepts/workflows/` · F5 `…/workflows/` · F6 `…/workflows/checkpoints` · F7 `…/workflows/human-in-the-loop` · F8 `…/workflows/orchestrations/` · F9 `…/hosting/` · F10 `…/hosting/durable-extension` · F11 `learn.microsoft.com/en-us/agent-framework/hosting/foundry-hosted-agent` · F12 `…/integrations/` · F13 `…/integrations/by-component/middleware/purview` · F14 `devblogs.microsoft.com/agent-framework/fides/` · F15 `…/governance-at-the-speed-of-agents-microsoft-agent-framework-and-agent-governance-toolkit-better-together/` · F16 `…/interactive-experiences-memory-and-resilient-execution/` · F17 `…/foundry-hosted-agent-isolation-with-microsoft-agent-framework/` · F18 `…/a2a-v1-is-here-cross-platform-agent-communication-in-microsoft-agent-framework-for-net/` · F19 `learn.microsoft.com/agent-framework/integrations/by-component/agent-services/a2a` · F20 `…/move-agent-orchestration-workflows-out-of-code-with-agent-framework-declarative-workflows-1-0/` · F21 `…/the-microsoft-agent-framework-harness-is-now-released/` · F22 `learn.microsoft.com/en-us/agent-framework/agents/observability` · F23 `github.com/microsoft/autogen` · F24 `learn.microsoft.com/en-us/azure/foundry/agents/concepts/workflow` · X1 `techcommunity.microsoft.com/t5/microsoft-foundry-blog/a2a-endpoints-and-a2a-tool-in-microsoft-foundry-agents/ba-p/4557115`.
**Agents SDK, MCP, SRE, Copilot Studio** — M1 `learn.microsoft.com/microsoft-365/agents-sdk/agents-sdk-overview` · M2 `github.com/microsoft/Agents` plus `gh api` releases of `Agents-for-net`, `-js`, `-python` · M3 `learn.microsoft.com/en-us/microsoft-365/agents-sdk/adaptive-cards` · M4 `learn.microsoft.com/microsoft-365/agents-sdk/azure-bot-create-managed-identity` · M5 `learn.microsoft.com/azure/bot-service/bot-builder-concept-regionalization` · M6 `azure.microsoft.com/en-us/pricing/details/bot-services/` · T1 `devblogs.microsoft.com/azure-sdk/azure-mcp-server-3-0-stable-release/` plus `gh api repos/microsoft/mcp` · T2 `learn.microsoft.com/azure/developer/azure-mcp-server/how-to/deploy-remote-mcp-server-microsoft-foundry` · T3 `techcommunity.microsoft.com/t5/azure-infrastructure-blog/threat-modeling-azure-mcp-securing-ai-assisted-infrastructure/ba-p/4564892` · R1 `learn.microsoft.com/azure/sre-agent/pricing-billing` (redirect from `…/billing`) · R2 `…/sre-agent/overview` · R3 `…/sre-agent/supported-regions` · R4 `…/sre-agent/run-modes` · R5 `azure.microsoft.com/en-us/pricing/details/sre-agent/` · R6 `prices.azure.com/api/retail/prices` (filters `productName eq 'Azure Agent Unit'`, `serviceName eq 'Azure Firewall'`, EUR) · R7 `techcommunity.microsoft.com/t5/azure-observability-blog/azure-copilot-observability-agent-is-generally-available-with/ba-p/4528213` · R8 `…/understanding-billing-for-the-azure-copilot-observability-agent/ba-p/4537780` · P1 `learn.microsoft.com/microsoft-copilot-studio/billing-licensing`.
