# Security and compliance for AI — control catalogue (A4)

> **Evidence, not design.** Researched 2026-10-31 from pages fetched that day (§7). Where the attachment and a page disagree, the page wins and I say so. `UNVERIFIED` = not confirmed on a page I fetched. Prices are EUR from the Azure Retail Prices API on 2026-10-31, indicative; `prices.md` (assignment P1) is authoritative. Nothing here is legal advice.

**Codes.** Status, disposition and component codes follow the brief. **Licence class:** `INC` included in the Azure/Foundry resource or tenant · `RES` per resource, plan or subscription-hour · `TOK` per token, text record, audit record or GB · `USR` per user · `IDN` per workload identity · `PAYG` Purview pay-as-you-go (tenant linked to an Azure subscription) · `OSS` MIT, run cost only. `[S#]` in prose and `S#` in the Src column = source in §7. Control codes: D Defender, P Purview, E Entra, G Azure Policy and benchmarks, **SG** Foundry, gateway and runtime safeguards, L logging and SIEM, K keys, C confidential computing, W edge, R red teaming.

**Working assumptions.** (1) A spoke in the operator's landing zone, private networking, EU Data Zone or regional model deployments. (2) Agents on Foundry Agent Service with Agent Framework, behind the Citadel gateway (APIM). (3) The operator's tenant may lack Agent 365, M365 E5 or Entra P2; the MIT core must work without them, so licence-bound controls are optional modules with a named fallback. (4) Under the AI Act the operator is both *provider* (builds and puts the system into service under his name) and *deployer*. Nothing is skipped: every control not adopted has a compensating control in its row.

## 1. Findings that change the design

- **F1 · Defender no longer covers Foundry agents.** Since 1 July 2026, agent discovery, posture and threat protection for Foundry agents need a Microsoft Agent 365 licence; Defender for AI Services keeps covering *models* only [S3]. Agent 365 is per user (list $15/user/month standalone, $99 in M365 E7); agents are unlicensed, owners and sponsors are licensed [S19]. → H8 cannot assume agent-level Defender. Runtime controls (AGT/FIDES, gateway, policy) must be ours; Agent 365 is an optional tenant module.
- **F2 · Defender for AI Services is token-metered and subscription-wide:** €0.000704 per 1K tokens (≈€0.70 per million), text only, Azure OpenAI and Model Inference models [S1,S5,S7]. For H7's cheap high-volume tiers the scan can cost more than the inference. → Scope untrusted-input agents (Diplomat, web-reading Scholar) in a separate subscription, or accept the uplift knowingly.
- **F3 · Purview's Foundry integration "doesn't yet support network isolation"**, needs PAYG or Agent 365 for policies, and enforces policies only for Entra *user-context* calls, not agent-identity calls [S8,S9]. → Conflicts with H3. The primary audit trail must be ours (append-only approvals + Foundry and APIM logs in the platform workspace); Purview is a WATCH.
- **F4 · PIM cannot make service principals or managed identities eligible** — "they can't perform the activation steps" [S23]. → H4's "activate a scoped, short-lived identity per Move" needs another mechanism: the approval service creates a time-bound role assignment, or a federated credential bound to an approved GitHub environment. Design and test it. Workload ID Premium ($3/identity/month) adds Conditional Access for those few identities [S22].
- **F5 · Foundry guardrails have sharp edges** [S32,S33]. Agent guardrails, tool-call/tool-response checks, Spotlighting, Groundedness, PII and Task Adherence are Preview; the agent guardrail *fully overrides* the model's; document-attack Prompt Shields are *off by default*; Prompt Shields are English-primary; Groundedness retires 30 Apr 2027; guardrails cover only agents built in Foundry Agent Service. → Configure model and agent guardrails explicitly, evaluate per working language, do not build on Groundedness.
- **F6 · Hosted-agent egress control is Preview, "not intended for production use"** [S41]. → WATCH for prod; compensate with VNet-injected outbound through gateway/firewall, tool allow-lists and AGT.
- **F7 · Azure Policy now governs models and agent tools.** GA: approved models and eligibility, also enforced for model router [S24,S29]. Preview: agents/toolboxes "only use approved tools" or "not use denied tools", and minimum content-filter levels [S24]. → H11 drift control becomes policy-as-code; Preview ones behind a switch.
- **F8 · Open-source runtime governance exists but is young.** AGT (MIT) is *public preview*, v4.1.0; its README claims 7 full and 3 partial of the 10 OWASP agentic risks while Microsoft's blog says all 10 — treat as partial [S37]. FIDES is experimental in agent-framework-core [S38]. ACS and ASSERT are new [S39]. → ADOPT-PREVIEW with a deterministic in-house fallback.
- **F9 · CMK is conditional.** Prompt agents get CMK only with bring-your-own Cosmos DB, Storage and AI Search, each keyed; hosted-agent `$HOME` is not CMK-encrypted and cannot be disabled; CMK regions are limited by AI Search capacity [S46]. Managed HSM ≈ €2,056/month [S7]. → Platform-managed keys by default; Key Vault only where a driver exists; no Managed HSM.
- **F10 · The AI Act moved, Article 50 did not.** The Omnibus entered into force 27 July 2026: Annex III high-risk now 2 Dec 2027, Annex I 2 Aug 2028 [S55]. Transparency (Art. 50) applies since 2 Aug 2026 to this system's Teams, e-mail, voice and avatar channels; emotion recognition at work is prohibited, so no mood inference from staff voices or faces (§4).
- **F11 · A spoke should feed the SIEM, not buy one.** Sentinel leaves the Azure portal after 31 March 2027 [S43,S45]; lake-tier ingestion is €0.057/GB against €4.92/GB for analytics-tier pay-as-you-go [S7]. → Policy-deployed diagnostic settings to the platform workspace.
- **F12 · The AI Red Teaming Agent cannot test everything we build.** Cloud runs (EU: Sweden Central, France Central) support Foundry prompt and container agents with Azure tools; workflow agents, non-Foundry agents, function tools and non-Azure tools are unsupported [S50]. → Add PyRIT and ASSERT in CI.

**Hypothesis check.**

| H | Verdict | Why |
|---|---|---|
| H3 private only | Partly conflicts | Purview–Foundry integration lacks network isolation [S9]; hosted-agent egress is Preview [S41]; NSP is GA for Foundry (AIServices kind) but Preview for the Azure OpenAI kind, Cosmos DB and SQL DB [S49] |
| H4 two planes | Holds; mechanism open | No eligible PIM assignment for service principals [S23]; hosted agents give VM-isolated sessions and a per-agent Entra Agent ID [S40] |
| H8 layers | Holds with gaps | Agent-level Defender moved to Agent 365; guardrails for agents are Preview; red-team coverage limits |
| H9 identity | Holds | Agent ID platform is GA and free; Conditional Access, ID Protection and governance for agents need Agent 365 [S14,S17] |
| H11 drift | Holds | Policy built-ins GA plus Preview; MCSB v2 AI controls as spine [S31] |

## 2. Control catalogue

**2.0 Licence map — what is included, what is bought, and by which meter.**

| Billing model | Controls |
|---|---|
| **Included / free** | Foundational CSPM; Azure Policy and MCSB; Entra Agent ID platform; managed identities and workload identity federation; Agent 365 foundational set (agent identity, registry, basic insights, audit logs and eDiscovery for agent activity) [S19]; NSP (no meter seen, `UNVERIFIED`); Foundry diagnostic settings (storage/ingestion cost only); Purview Audit of Foundry interactions (but see F3); Compliance Manager baseline |
| **RES** per resource, plan or subscription-hour | Defender CSPM; Defender for APIs P1–P5; Resource Manager; Key Vault; Storage; Cosmos DB/PostgreSQL; Key Vault HSM keys; Managed HSM; Front Door; Application Gateway WAF |
| **TOK** per token, record or GB | Defender for AI Services (1K tokens); Azure AI Content Safety behind the gateway (1K text records); Purview PAYG (audit records, messages, GB-day); Sentinel (GB ingested, analysed, queried; compute-hours) |
| **USR** per user | Agent 365 ($15 list; E7 $99) for Conditional Access, ID Protection, governance, threat detection for agents; Entra P1/P2/Governance |
| **Per template** | Compliance Manager premium templates, annual licence |
| **IDN** per identity | Workload ID Premium, $3/identity/month |
| **OSS** | PyRIT, AGT, FIDES, ASSERT, ACS (MIT) |

Billing of Foundry-native guardrails is `UNVERIFIED`: a classic page says content filtering "might be billed separately", the current pages state no charge.

**2.1 Microsoft Defender for Cloud**

| # | Control | Status | Licence · meter | Fit · compensating control | Disp. | Src |
|---|---|---|---|---|---|---|
| D1 | Foundational CSPM: inventory, MCSB recommendations, secure score | GA | INC | SEC/GOV baseline on every subscription | ADOPT | S4,S30 |
| D2 | Defender CSPM incl. AI posture: AI BOM, attack paths, exposed AI endpoints, IaC checks (private endpoints, managed identity) | Not stated for gen-AI apps; "AI agents" labelled Preview (page 2026-06-17) | RES €0.00616 per billable resource-hour ≈ €4.50/month (storage accounts, databases, serverless containers 2:1, functions 8:1) | SEC. Cost grows with resource count, so Lab subscriptions matter. Use if the landing zone already enrols the subscription | EVALUATE | S2,S4,S7 |
| D3 | Defender for AI Services: jailbreak, data-leak, credential-theft alerts via Prompt Shields; Defender XDR | GA (2026-07-27); 30-day trial ≤75 B tokens | TOK €0.000704/1K tokens; text only; subscription-level toggle; prompt evidence optional | SEC, see F2. Compensate: gateway shield-prompt and guardrails | EVALUATE | S1,S5,S7 |
| D4 | Agent posture and threat protection for Foundry agents | Licence moved 2026-07-01 | USR Agent 365 (≥1 licensed user; owners, sponsors) | SEC/ID optional tenant module; alerts in Agent 365 logs, table `AgentsInfo` | WATCH | S3,S19 |
| D5 | Defender for APIs: inventory, unauthenticated and unused APIs, classification, OWASP-API anomaly detection for APIs in APIM | Not stated (priced plan) | RES per subscription P1 €176/month … P5 ≈ €44k/month, plus per-call overage | GW/SEC. MCP/A2A coverage `UNVERIFIED`. Compensate: `validate-jwt`, APIM logs, KQL alerts | EVALUATE | S4,S6,S7 |
| D6 | Defender for Resource Manager: suspicious ARM operations | Not stated (priced plan) | RES €0.006072/h per subscription ≈ €4.43/month | SEC/OPS watches Engineer and Lab identities | ADOPT | S4,S7 |
| D7 | Defender for Key Vault | Not stated (priced plan) | RES €0.000299/h per vault ≈ €0.22/month | SEC cheap | ADOPT | S4,S7 |
| D8 | Defender for Storage + malware scanning | Not stated (priced plan) | RES €0.0118/h per account ≈ €8.6/month; scan €0.132/GB (blobs) | Only accounts taking untrusted uploads (inbound attachments, Commons submissions) | EVALUATE | S4,S7 |
| D9 | Defender for Containers (AKS, registry scans) | Not stated (priced plan) | RES €0.00828/vCore-h; registry-only €0.255/image digest | No AKS planned; scan images in CI | N/A | S4,S7 |
| D10 | Defender for Cosmos DB / PostgreSQL | Not stated (priced plan) | RES €0.001056 per 100 RU/s-h (serverless converted ×0.00003125); PostgreSQL €13.2/node-month | DATA: decide after A5 picks the store | EVALUATE | S4,S7 |

**2.2 Microsoft Purview**

| # | Control | Status | Licence · meter | Fit · compensating control | Disp. | Src |
|---|---|---|---|---|---|---|
| P1 | Purview Audit of Foundry interactions | Not stated (page 2026-05-01) | INC: Audit is "included as part of the Microsoft Purview license for Foundry services"; non-Microsoft AI apps PAYG ≈ $15 per 1M records, 180 days | GOV. Not supported with network isolation (F3), so our append-only log is primary | WATCH | S8,S9,S11 |
| P2 | DSPM for AI, SIT classification, data-security (DLP) policies, insider risk, communication compliance | Not stated | PAYG (audit records, text records, DSPU) or Agent 365; per-user M365 licences cover M365 sources | SEC/GOV. Enforced only for Entra user-context calls; little value for agent-identity flows. Compensate: PII guardrail (Preview), pseudonymised owners in prompts | WATCH | S8,S10,S11 |
| P3 | Retention and eDiscovery of AI interactions | Not stated | PAYG: ≈ $6 per 1M messages/month; eDiscovery per GB-day | GOV. Ours: append-only store with our retention policy. Teams-delivered cards and replies are also M365 content in the humans' retention scope (`UNVERIFIED`) | N/A | S10,S11 |
| P4 | Sensitivity labels in AI Search (query-time enforcement, admin-access auditing) | Public preview (2026-09-17) | Purview label licence `UNVERIFIED` | KNW. Only if M365 content is indexed; the Atlas is public | N/A | S13 |
| P5 | Compliance Manager: baseline plus premium templates (EU AI Act, ISO/IEC 42001, ISO/IEC 23894, NIST AI RMF) | Not stated (2026-06-25) | INC baseline; premium = annual licence per template (some agreements include three) | GOV. Use MCSB and Azure Policy compliance free; buy a template only for an audit | EVALUATE | S12 |
| P6 | "Data security for AI interactions" toggle in Defender | Not stated | Paid Purview feature, "not included" in the Defender plan | Same limits as P2 | WATCH | S5 |

**2.3 Microsoft Entra**

| # | Control | Status | Licence · meter | Fit · compensating control | Disp. | Src |
|---|---|---|---|---|---|---|
| E1 | Entra Agent ID: blueprints, agent identities, agent users, OBO, sponsors and owners, sign-in and audit logs | GA (what's-new page dated 2026-05-01); creation wizard Preview | INC — "available for all Microsoft Entra customers" | ID: own identity plus named human sponsor per agent (H9); hosted agents get one automatically [S40] | ADOPT | S15,S16 |
| E2 | Managed identities; workload identity federation (GitHub OIDC) | Not stated (free feature) | INC | ID/OPS, no secrets | ADOPT | S22 |
| E3 | Conditional Access for agents: OBO, app-only, agent-user; agent risk | Documented (page 2026-10-07); Agent ID is GA | USR Agent 365 + Entra P1 or M365 E3, or M365 E7 | ID optional. Fallback: least-privilege RBAC, short-lived identities, network limits | EVALUATE | S14,S17,S20 |
| E4 | ID Protection for agents | Not stated; "starting soon" needs Agent 365 | USR | ID | WATCH | S14 |
| E5 | Agent governance: access packages, sponsor lifecycle workflows, access reviews | Not stated | USR Agent 365 or E7 (+ ID Governance for members); access reviews P2/Governance | ID/GOV. Sponsor re-assignment is also in our records | EVALUATE | S14,S15,S20 |
| E6 | PIM for humans: eligible or time-bound Azure RBAC, approval, MFA | Not stated | USR Entra P2 or ID Governance | ID for admins and Move approvers; **not** for service principals (F4) | ADOPT | S23,S30 |
| E7 | Workload ID Premium: Conditional Access, ID Protection, CAE for service principals | GA | IDN $3/identity/month | ID only for the few execution identities | EVALUATE | S22 |
| E8 | Agent 365 foundational set; registry (the Entra agent registry converges into the Agent 365 registry) | GA (Commercial, 2026-05-01) | INC with a Microsoft cloud subscription | ID/GOV inventory of our agents | ADOPT | S18,S19,S21 |

**2.4 Azure Policy and benchmark**

| # | Control | Status | Licence | Fit | Disp. | Src |
|---|---|---|---|---|---|---|
| G1 | MCSB v2 AI Security domain: AI-1 approved models, AI-2 multi-layer filtering, AI-3 safety meta-prompts, AI-4 least privilege for agent functions, AI-5 human-in-the-loop, AI-6 monitoring, AI-7 continuous red teaming | Guidance, last reviewed 2025-12-01 | INC | GOV control spine; maps to ATLAS and OWASP | ADOPT | S31 |
| G2 | Foundry/AI Services built-ins: key access disabled, restrict network access, Private Link, public access off (Modify), managed identity, customer-owned storage, CMK, diagnostics (DINE); model eligibility and approved models incl. model router | Not marked Preview | INC | GOV. Deny in prod, Audit in Lab | ADOPT | S24,S29 |
| G3 | Foundry agents/toolboxes approved or denied tools; minimum content-filter levels for agents and deployments | Public preview (1.0.0-preview) | INC | GOV/TOOL tool allow-list as policy. Guardrail ones are Audit only | ADOPT-PREVIEW | S24 |
| G4 | APIM built-ins: VNet, no direct management endpoint, authenticated backends, certificate validation, secrets in Key Vault, subscriptions not scoped to all APIs, `<base />` inheritance; TLS ≥1.2 and zone-redundant (Preview) | Not marked Preview, except the two noted | INC | GW stops hub drift | ADOPT | S25 |
| G5 | Container Apps built-ins: network injection, public access off, internal-only, HTTPS only, managed identity, authentication | Not marked Preview | INC | COMP | ADOPT | S26 |
| G6 | AI Search and Key Vault built-ins: local auth off, public access off, CMK, private endpoints; Key Vault RBAC model, purge protection, private link, firewall, soft delete, rotation, HSM-backed keys | Not marked Preview | INC | DATA/SEC | ADOPT | S27,S28 |

**2.5 Foundry, gateway and runtime safeguards**

| # | Control | Status | Licence · meter | Fit · compensating control | Disp. | Src |
|---|---|---|---|---|---|---|
| SG1 | Guardrails for models: hate, sexual, self-harm, violence, user-prompt-attack shield (on by default), protected material; default `Microsoft.DefaultV2` | Models: no Preview label | INC (billing `UNVERIFIED`) | SEC. Set explicit thresholds per agent group | ADOPT | S32,S33 |
| SG2 | Prompt Shields document attacks: user input; tool responses for agents | Models: no Preview label; agent tool-response scanning Preview | as SG1 | SEC. Off by default: enable on every untrusted-text route (billing text, tags, e-mail, web) | ADOPT | S33 |
| SG3 | Agent guardrails: tool-call and tool-response intervention, Task Adherence, PII | Public preview | as SG1 | AGT/SEC. Fallback: AGT/FIDES plus gateway shields | ADOPT-PREVIEW | S32 |
| SG4 | Spotlighting; Groundedness | Preview, models only; Groundedness retires 2027-04-30 | as SG1 | SEC. Spotlighting EVALUATE; replace Groundedness with evaluators | EVALUATE | S32 |
| SG5 | APIM `llm-content-safety` on LLM, MCP and A2A routes: categories, blocklists, `shield-prompt`, 403 | Documented (page 2026-08-18); GA per attachment line 473 (page silent) | TOK Content Safety Standard €0.33/1K text records (record = 1,000 characters; request window 10,000 ≈ €0.0033/request); free 5,000 records/month; policy absent on Consumption tier | GW. Apply to untrusted-text routes only, not internal tool results | ADOPT | S34,S36,S7 |
| SG6 | APIM token limits and quotas, semantic cache, managed identity to backends, OAuth credential manager | Documented (2026-05-29) | INC in APIM tier; semantic cache needs Azure Managed Redis (RES) | GW/COST (A1) | ADOPT | S35 |
| SG7 | Agent Governance Toolkit: policy-as-code before each tool call, agent identity, execution rings, Agent SRE; ACS standard | Public preview, MIT, v4.1.0 | OSS | AGT/FW. Fallback: in-house deterministic checks | ADOPT-PREVIEW | S37,S39 |
| SG8 | FIDES: integrity and confidentiality labels, policy before sensitive tools | Experimental | OSS | FW enforces "external text is data" deterministically | EVALUATE | S38 |
| SG9 | ASSERT: policy-driven agent evaluation | New (Build 2026) | OSS | EVAL in CI | EVALUATE | S39 |
| SG10 | Hosted-agent isolation: VM-isolated session, per-agent Agent ID, BYO-VNet outbound | GA per attachment line 462 (blog 2026-04-22 said Preview); A2 to confirm | Consumption, scale to zero | AGT/SEC ASI05, ASI10 | ADOPT | S40 |
| SG11 | Hosted-agent egress policy: FQDN allow/deny, Audit or Enforced | Preview, "not intended for production use" | INC | NET. Compensate: see F6 | WATCH | S41,S32 |
| SG12 | Network security perimeter | GA: Foundry (AIServices), Service Bus. Preview: Azure OpenAI kind, Cosmos DB, SQL DB, Event Grid domains | No meter seen (`UNVERIFIED`) | NET exfiltration control, access logs; for Foundry, Storage, Key Vault, AI Search | ADOPT | S49 |

**2.6 Logging and SIEM**

| # | Control | Status | Licence · meter | Fit | Disp. | Src |
|---|---|---|---|---|---|---|
| L1 | Foundry and APIM diagnostic settings: Audit, Request/Response, Usage, metrics → Log Analytics or Storage | Documented (page 2026-06-25) | TOK Log Analytics ingestion (`prices.md`) | OBS/SEC. Policy-deployed (DINE); up to 2 h latency; logs may hold prompt text, so restrict access and retention | ADOPT | S42,S24 |
| L2 | Sentinel analytics tier; Defender XDR correlation of AI alerts | Azure portal support ends 2027-03-31 | TOK €4.919/GB analysis | SEC. Platform service: feed it | EVALUATE | S43,S45 |
| L3 | Sentinel data lake: open Parquet, ≤12 years, KQL jobs, notebooks, MCP server | GA (Sept 2025) | TOK ingestion €0.0572/GB, storage €0.0211/GB-month, query €0.00572/GB; notebook/graph compute-hours; MCP free plus underlying meters | OBS/GOV cheap retention of the audit trail if the landing zone has Sentinel | ADOPT if available | S43,S44,S45,S7 |

**2.7 Keys, confidential computing, edge, red teaming**

| # | Control | Status | Licence · meter | Fit · compensating control | Disp. | Src |
|---|---|---|---|---|---|---|
| K1 | Platform-managed encryption, FIPS 140-2 256-bit AES | Default (page 2026-10-19) | INC | SEC default | ADOPT | S46 |
| K2 | Foundry CMK with Key Vault or Managed HSM | Not stated; limits in F9 | RES Key Vault €0.0264/10K operations; HSM-protected key €0.88/month | SEC only with a compliance driver; BYO resources each keyed; policy audit | EVALUATE | S46,S7 |
| K3 | Managed HSM | Not stated (priced) | RES ≈ €2,056/month (pool B1 €2.82/h) | None needed | N/A | S7 |
| C1 | Confidential VMs, confidential containers on ACI, confidential GPU VMs (NCCadsH100v5) for self-hosted inference | Offered (2026-02, 2026-10); managed confidential inferencing in Foundry: Not stated | RES VM prices; no resizing | SEC. No self-hosting, no special-category data, so N/A; WATCH the managed offering | N/A | S47 |
| W1 | Front Door Premium + WAF: managed rules, bot protection, Private Link origin | Not stated; classic retires 2027-03-31 | RES base €290.39/month (Standard €30.80, custom rules only) + requests | NET. Only if a public ingress exists (Teams bot endpoint, ACS webhooks); otherwise none | EVALUATE | S48,S7 |
| W2 | Application Gateway WAF v2 | Not stated (priced) | RES €0.4118/h ≈ €301/month + €0.0127/capacity-unit-h | NET regional alternative | EVALUATE | S7 |
| R1 | AI Red Teaming Agent: scheduled cloud runs, agentic risks, XPIA | Local: Preview; cloud API `2025-11-15-preview`; GA not stated | Target, attacker and evaluator model consumption (`UNVERIFIED`) | EVAL. Weekly in a purple environment | ADOPT-PREVIEW | S50 |
| R2 | PyRIT | MIT, v1.1.0 (2026-09-04), active | OSS | EVAL in CI for function, MCP and non-Azure paths and non-English prompts | ADOPT | S51 |

**2.8 Indicative monthly cost by tier** (arithmetic on the meters above; volumes are my illustrations, not forecasts).

| Tier | Contents | Cost |
|---|---|---|
| 0 — included | D1, E1, E2, E8, G1–G6, SG1–SG4, SG6–SG9, SG12, K1, R2 | €0 licence, except that billing of SG1–SG4 and SG12 is `UNVERIFIED`; log ingestion and model-side consumption excluded |
| 1 — adopt by default | D6 on 4 subscriptions €17.7; D7 on 4 vaults €0.9; gateway shielding of untrusted text at €0.00033 per 1,000 characters (10,000 inputs of 3,000 characters ≈ €10); E6 needs Entra P2 already in the tenant | ≈ €30 plus P2 |
| 2 — optional, by decision | D2 for 20 billable resources €90; D3 at 50 M tokens €35, at 500 M tokens €352; Agent 365 for 3 sponsors $45 list; E7 for 3 identities $9; D5 P1 €176; W1 Premium €290 plus requests; L3 ingestion of 10 GB €0.57; Compliance Manager premium template `UNVERIFIED` | Each priced on its own meter |
| 3 — not recommended | K3 Managed HSM ≈ €2,056; D5 P5 ≈ €44k | Driver required |

## 3. Threat frameworks and this system's threat model

- **OWASP Top 10 for LLM Applications 2025:** LLM01 Prompt Injection · 02 Sensitive Information Disclosure · 03 Supply Chain · 04 Data and Model Poisoning · 05 Improper Output Handling · 06 Excessive Agency · 07 System Prompt Leakage · 08 Vector and Embedding Weaknesses · 09 Misinformation · 10 Unbounded Consumption [S52].
- **OWASP Top 10 for Agentic Applications 2026:** ASI01 Agent Goal Hijack · 02 Tool Misuse and Exploitation · 03 Identity and Privilege Abuse · 04 Agentic Supply Chain Vulnerabilities · 05 Unexpected Code Execution · 06 Memory and Context Poisoning · 07 Insecure Inter-Agent Communication · 08 Cascading Failures · 09 Human-Agent Trust Exploitation · 10 Rogue Agents. The OWASP page confirms the title and scope; the item names come from Microsoft's AGT post [S53,S37].
- **MITRE ATLAS:** content release 2026.10 (28 Oct 2026): 16 tactics, 221 techniques and sub-techniques (129 + 92), 44 mitigations. These are my counts from the published YAML, because atlas.mitre.org is script-rendered and returned no text. 148 entries carry the *Agentic AI* tag; 71 have no predictive-AI tag. Agent mitigations specific to agents: M0026–M0033, M0037, M0038, M0043; also relevant: M0020, M0024, M0035, M0036 [S54].

Cost data is full of attacker-controllable text: tags, names, descriptions, invoice lines, owner replies, public pages.

| # | Threat | Where it enters | OWASP LLM · ASI | ATLAS |
|---|---|---|---|---|
| T1 | Indirect prompt injection | Tags, names, billing lines, e-mail and Teams replies, pages Scholar reads, MCP results | LLM01 · ASI01 | T0051.001, T0066, T0093 |
| T2 | Knowledge and memory poisoning | Atlas claims, Commons contributions, Lesson Book testimony, search index | LLM04, LLM08 · ASI06 | T0070, T0080.000 |
| T3 | Excessive agency | Engineer's write rights, purchases, Lab experiments | LLM06 · ASI02, ASI03, ASI10 | T0053, T0101 |
| T4 | Denial of wallet | Runaway loops, noisy Lab, abusive gateway callers | LLM10 · ASI08 | T0034.002, T0029 |
| T5 | Estate-data disclosure | Prompts, logs, Commons publication, non-EU processing | LLM02, LLM07 | T0086, T0085, T0069 |
| T6 | Supply chain | Models, MCP servers, Move recipes, packages, Commons code | LLM03 · ASI04 | T0010.005, T0110 |
| T7 | Inter-agent spoofing, propagation | A2A calls, shared memory | ASI07, ASI08 | T0118, T0143 |
| T8 | Approval-path abuse | Impersonated approver by voice, avatar or e-mail; persuasive agent text | ASI09 | — |
| T9 | Output injection | Agent output rendered in cards, Markdown, KQL, Bicep, CLI | LLM05 | T0077 |
| T10 | Confident wrong numbers | Hallucinated savings drive a Move | LLM09 · ASI09 | — |

## 4. Compliance

**4.1 EU AI Act, as of 2026-10-31** [S55]

| Date | What applies |
|---|---|
| 2 Feb 2025 | Prohibitions (Art. 5) and AI literacy (Art. 4) |
| 2 Aug 2025 | General-purpose AI model obligations |
| 27 Jul 2026 | AI Omnibus in force (Regulation (EU) 2026/1744 per the OJ link; Articles 102–110 apply) |
| 2 Aug 2026 | Remainder of the Act, incl. Art. 50 transparency. Art. 50(2) marking: grace to 2 Dec 2026 only for systems already on the market |
| 2 Dec 2026 | Ban on non-consensual intimate-image and CSAM generators |
| 2 Dec 2027 | Annex III high-risk (postponed; secondary sources: previously 2 Aug 2026) |
| 2 Aug 2028 | Annex I high-risk (postponed; secondary sources: previously 2 Aug 2027) |

I treat the operator as provider and deployer. An MIT release does not exempt an Art. 50 system: Art. 2(12) leaves free and open-source AI systems out of scope "unless" high-risk, Art. 5 or Art. 50 (last limb from the Regulation; the fetched page cut the sentence).

| Obligation | Applies? | Action |
|---|---|---|
| Art. 5 prohibitions | Yes, since Feb 2025 | No emotion recognition of staff in meetings or calls; no social scoring or ranking of individuals; no manipulative techniques. Red-team "prohibited actions" [S50] |
| Art. 4 AI literacy | Yes; simplified by the Omnibus (Commission and Member States take a stronger role) | Light training record for operators and approvers. Amended wording `UNVERIFIED`: the Art. 4 page still shows the old text |
| Art. 50(1) tell people it is AI | Yes since 2 Aug 2026; provider duty | Disclose at first interaction in every channel: card footer, e-mail banner, voice greeting, avatar label, first SMS |
| Art. 50(2) machine-readable marking of synthetic text, audio, video | Yes; a new system gets no grace period | Header and metadata on e-mail and cards; marks on audio and video where the service offers them (`UNVERIFIED`); consider the voluntary Code of Practice on Transparency of AI-generated Content |
| Art. 50(4) deepfakes (deployer) | If an avatar or voice resembles a real person | Default to a clearly synthetic avatar; consent and disclosure for any personal voice or custom photo avatar |
| High-risk, Annex III employment | Out of scope by purpose | Keep it out of work management: no evaluation of individuals' performance or behaviour; attribute to resources and teams |
| General-purpose model duties | On the model providers | No fine-tuning or distillation into a new general-purpose model without legal check (threshold `UNVERIFIED`) |

**4.2 GDPR.** Owner names, addresses, Teams content, tags, voice and avatars are personal data [S58,S59].

| Topic | Position | Action |
|---|---|---|
| Terms | Microsoft processes under the Products and Services DPA; prompts, completions and embeddings are not shared or used for training | Keep DPA acceptance in the evidence pack |
| Residency | Processing stays in the chosen geography unless the deployment is Global or Data Zone; EU Data Zone means EU member states; data at rest, incl. the abuse-monitoring store, stays in the chosen geography | No Global deployments for prompts with personal data; check Speech, Voice Live and avatar regions (A2) |
| Abuse monitoring | Foundry and Microsoft personnel may review prompts; managed customers may apply to modify | Decide, record, put in the DPIA |
| Minimisation | Not a platform feature | Replace owner names with stable IDs in prompts; keep the mapping in our store |
| DPIA, lawful basis, works-council or labour-law consent for staff-facing voice or meeting agents | Not verified | Legal review before enabling voice or avatar (H10: off by default) |
| Automated decisions | Moves need human approval | Meets the intent of Art. 22 if approvals are authenticated and recorded |

**4.3 NIS2** [S56]. Directive 2022/2555, transposition due 17 Oct 2024; medium and large entities in listed sectors; management accountability. The Commission proposed targeted simplification on 20 Jan 2026 (status `UNVERIFIED`). Whether the operator is in scope, and national transposition, are `UNVERIFIED`; EUR-Lex returned no text, so Article 21 is not quoted. Controls that would carry it: G1–G6, D6–D7, L1–L3, E6, an incident runbook.

**4.4 Frameworks and artefacts**

| Item | Status | Use |
|---|---|---|
| ISO/IEC 42001 | Microsoft Foundry is in scope of Microsoft's certification (page 2026-09-11); certificates sit on the Service Trust Portal (not loadable here) | Cite it; your own controls still need your own assessor [S57] |
| NIST AI RMF | Microsoft red teaming maps to Map, Measure, Manage [S50]; premium Compliance Manager template [S12] | Use the MCSB mapping as a free baseline |
| Responsible AI Standard, Transparency Notes | Notes are "part of the Responsible AI Standard"; the Agent Service note urges human oversight and caution for irreversible or highly consequential actions [S58] | Moves and purchases are such actions: approvals, two named approvers for purchases |
| Compliance Manager | See P5 | EVALUATE |
| Service Trust Portal | Hosts Microsoft's ISO/IEC 42001 certificates and audit reports (per the ISO page); I could not load it [S57] | Pull the certificate and scope statement into the evidence pack |
| Trust Center, EU Data Boundary | Commitment to process and store EU/EFTA customer data in region; per-service scope not checked for Foundry [S59] | Verify scope for Voice Live and Foundry features before relying on it |

## 5. Attachment cross-check

A two-pass keyword search of the attachment (Defender, Purview, Entra, Agent ID, Sentinel, prompt injection, red team, policy, confidential, key, compliance, OWASP, sovereign, egress, and more) matched 177 and then 68 further rows; I checked those that decide design [S60]. Azure Updates pages (`azure.microsoft.com/updates/?id=…`) returned no text when fetched, so their rows were checked against Learn.

| Line | Attachment says | Page says |
|---|---|---|
| 362 | Foundry agent security in Defender moves to an Agent 365 licence on 1 Jul 2026 | Confirmed [S2,S3] |
| 770 | Entra Agent ID public preview (18 Nov 2025) | Superseded: "now generally available" (what's-new page dated 2026-05-01) [S15] |
| 787 | Agent guardrails public preview | Still Preview, page 2026-10-28 [S32] |
| 432 | Azure Policy for model router, Preview (2 Jun 2026) | How-to (2026-10-19) shows deploy-time enforcement on portal, REST, CLI, ARM; status not stated [S29] |
| 473 | APIM content safety for MCP and A2A, GA | Policy page confirms MCP/A2A scope; carries no GA label [S34] |
| 799 | NSP for Foundry and Azure OpenAI, GA (18 Nov 2025) | Page wins: Foundry GA; Azure OpenAI kind Preview [S49] |
| 706 | Confidential inferencing deep dive, "16 Dec 2025" | Post dates from 24 Sep 2024 and announces an *upcoming* preview; Dec 2025 is a modification time [S47] |
| 739 | AI Red Teaming Agent public-preview enhancements (25 Nov 2025) | Cloud and agentic risks documented; GA not stated [S50] |
| 135, 143 | Hosted-agent egress controls not GA, no SLA | Confirmed [S41] |
| 411, 412, 416 | Purview labels and auditing in AI Search, Preview | Confirmed [S13] |
| 507, 514, 549, 591 | AGT covers "every" OWASP agentic risk; FIDES | AGT is public preview; README says 7 full, 3 partial [S37,S38] |
| 79, 87, 109 | Agent 365 with APIM; Foundry governance layers; multitenant governance | Not fetched; summaries only |
| 147 | Agent 365 can enable or disable Foundry agents tenant-wide, GA (18 Sep 2026) | Not fetched; `UNVERIFIED`; a candidate kill switch for row 29 of §8 |

## 6. Could not verify

- Azure Updates pages render no text; lines 362, 432, 473, 770, 787, 799 rest on Learn pages (§5).
- Whether Foundry-native guardrails or the Foundry Control Plane carry a separate charge: a classic page says content filtering "might be billed separately", current pages are silent, and the Foundry pricing page points Control Plane pricing at the Content Safety page [S36].
- AI Red Teaming Agent: GA or Preview for cloud runs; its billing.
- Defender for APIs: MCP and A2A coverage; plan entitlement numbers.
- Purview: what "doesn't yet support network isolation" excludes (Audit too?), and when it changes.
- PIM: whether time-bound *active* assignments for service principals are supported and licensed.
- NSP: price; the Foundry/Azure OpenAI split comes from the onboarded-resources table (seen as a Learn search excerpt of the page I fetched).
- Foundry CMK: supported EU regions (AI Search capacity limits).
- Whether the operator's tenant holds Agent 365, E5 or Entra P2 (assumed not); the licence and cost of agent user accounts (mailbox, Teams presence) for the Diplomat; the Entra release-notes "April 2026" GA entry, seen only as a search excerpt (the Agent ID what's-new page was fetched).
- EU: amended Art. 4 wording; Regulation number (OJ link `L_202601744` and secondary sources); open-source limb of Art. 2(12); modification threshold for general-purpose model providers; NIS2 Article 21 and national transposition.
- Microsoft: ISO 42001 scope per feature (Voice Live, hosted agents, Agent Service); EU Data Boundary scope for Foundry features; the Service Trust Portal did not load.
- Defender for AI Services for partner models outside Azure OpenAI and Model Inference (the page lists only those).
- Sentinel MCP server status after Sept 2025 (then Preview).
- My ATLAS counts come from the YAML; OWASP agentic item names come via Microsoft's AGT post; prices are a 2026-10-31 snapshot.

## 7. Sources (all fetched 2026-10-31)

| Tag | URL |
|---|---|
| S1 | https://learn.microsoft.com/en-us/azure/defender-for-cloud/ai-threat-protection |
| S2 | https://learn.microsoft.com/en-us/azure/defender-for-cloud/ai-security-posture |
| S3 | https://learn.microsoft.com/en-us/defender-xdr/security-for-ai/transition-agent-security-to-agent-365 |
| S4 | https://azure.microsoft.com/en-us/pricing/details/defender-for-cloud/ |
| S5 | https://learn.microsoft.com/en-us/azure/defender-for-cloud/ai-onboarding |
| S6 | https://learn.microsoft.com/en-us/azure/defender-for-cloud/defender-for-apis-introduction |
| S7 | https://prices.azure.com/api/retail/prices (EUR; service and product filters; 2026-10-31) |
| S8 | https://learn.microsoft.com/en-us/purview/ai-azure-foundry |
| S9 | https://learn.microsoft.com/en-us/azure/foundry/control-plane/how-to-manage-compliance-security |
| S10 | https://learn.microsoft.com/en-us/purview/purview-billing-models |
| S11 | https://azure.microsoft.com/en-us/pricing/details/purview/ |
| S12 | https://learn.microsoft.com/en-us/purview/compliance-manager-regulations and …/compliance-manager-regulations-list |
| S13 | https://learn.microsoft.com/en-us/azure/search/search-query-sensitivity-labels |
| S14 | https://learn.microsoft.com/entra/fundamentals/licensing |
| S15 | https://learn.microsoft.com/en-us/entra/agent-id/whats-new-agent-id |
| S16 | https://learn.microsoft.com/en-us/entra/agent-id/what-is-microsoft-entra-agent-id and …/security-for-ai-overview |
| S17 | https://learn.microsoft.com/en-us/entra/identity/conditional-access/agent-id |
| S18 | https://learn.microsoft.com/entra/agent-id/agent-registry-convergence |
| S19 | https://www.microsoft.com/licensing/faqs/122 |
| S20 | https://learn.microsoft.com/en-us/office365/servicedescriptions/microsoft-agent-365/microsoft-agent-365 |
| S21 | https://learn.microsoft.com/en-us/microsoft-agent-365/overview |
| S22 | https://learn.microsoft.com/en-us/entra/workload-id/workload-identities-faqs |
| S23 | https://learn.microsoft.com/en-us/azure/role-based-access-control/pim-integration |
| S24 | https://learn.microsoft.com/azure/ai-services/policy-reference |
| S25 | https://learn.microsoft.com/azure/api-management/policy-reference |
| S26 | https://learn.microsoft.com/azure/container-apps/policy-reference |
| S27 | https://learn.microsoft.com/azure/search/policy-reference |
| S28 | https://learn.microsoft.com/azure/key-vault/policy-reference |
| S29 | https://learn.microsoft.com/en-us/azure/foundry/how-to/model-router-policy |
| S30 | https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai/platform/governance |
| S31 | https://learn.microsoft.com/en-us/security/benchmark/azure/mcsb-v2-artificial-intelligence-security |
| S32 | https://learn.microsoft.com/en-us/azure/foundry/guardrails/guardrails-overview |
| S33 | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/content-filter-prompt-shields |
| S34 | https://learn.microsoft.com/en-us/azure/api-management/llm-content-safety-policy |
| S35 | https://learn.microsoft.com/en-us/azure/api-management/genai-gateway-capabilities |
| S36 | https://azure.microsoft.com/en-us/pricing/details/content-safety/ and https://azure.microsoft.com/en-us/pricing/details/microsoft-foundry/ |
| S37 | https://github.com/microsoft/agent-governance-toolkit and https://techcommunity.microsoft.com/blog/linuxandopensourceblog/governing-ai-agents-against-every-owasp-agentic-risk-a-deep-dive-with-the-agent-/4523749 |
| S38 | https://devblogs.microsoft.com/agent-framework/fides/ |
| S39 | https://devblogs.microsoft.com/foundry/build-2026-open-trust-stack-ai-agents/ |
| S40 | https://devblogs.microsoft.com/foundry/introducing-the-new-hosted-agents-in-foundry-agent-service-secure-scalable-compute-built-for-agents/ |
| S41 | https://devblogs.microsoft.com/foundry/egress-controls-hosted-agent/ |
| S42 | https://learn.microsoft.com/en-us/azure/foundry/how-to/diagnostic-logging |
| S43 | https://learn.microsoft.com/en-us/azure/sentinel/billing |
| S44 | https://learn.microsoft.com/en-us/azure/sentinel/datalake/sentinel-lake-overview |
| S45 | https://learn.microsoft.com/en-us/azure/sentinel/whats-new |
| S46 | https://learn.microsoft.com/en-us/azure/foundry/concepts/customer-managed-keys |
| S47 | https://learn.microsoft.com/en-us/azure/confidential-computing/confidential-ai, …/gpu-options, https://techcommunity.microsoft.com/blog/azureconfidentialcomputingblog/azure-ai-confidential-inferencing-technical-deep-dive/4253150 |
| S48 | https://learn.microsoft.com/en-us/azure/frontdoor/front-door-cdn-comparison |
| S49 | https://learn.microsoft.com/en-us/azure/private-link/network-security-perimeter-concepts |
| S50 | https://learn.microsoft.com/en-us/azure/foundry/concepts/ai-red-teaming-agent and …/how-to/develop/run-ai-red-teaming-cloud |
| S51 | https://github.com/microsoft/PyRIT (and api.github.com/repos/microsoft/PyRIT) |
| S52 | https://genai.owasp.org/llm-top-10/, https://genai.owasp.org/llmrisk/llm01-prompt-injection/, https://genai.owasp.org/llmrisk/llm102025-unbounded-consumption/, https://github.com/OWASP/www-project-top-10-for-large-language-model-applications/tree/main/2_0_vulns |
| S53 | https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ |
| S54 | https://github.com/mitre-atlas/atlas-data (dist/manifest.yaml, dist/v6/ATLAS-2026.10.yaml) |
| S55 | https://digital-strategy.ec.europa.eu/en/news/ai-omnibus-enters-force, https://artificialintelligenceact.eu/implementation-timeline/, …/article/4/, …/article/50/, …/article/2/, https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai, https://digital-strategy.ec.europa.eu/en/policies/guidelines-ai-transparency-obligations |
| S56 | https://digital-strategy.ec.europa.eu/en/policies/nis2-directive |
| S57 | https://learn.microsoft.com/en-us/compliance/regulatory/offering-iso-42001 |
| S58 | https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy, …/responsible-ai/agents/transparency-note, https://www.microsoft.com/en-us/ai/principles-and-approach |
| S59 | https://www.microsoft.com/en-us/trust-center/privacy/european-data-boundary-eudb |
| S60 | `Azure-AI-updates_2025-10-31_to_2026-10-31.md` (attachment) |

## 8. Control-to-threat table

Mitigation IDs are MITRE ATLAS (2026.10); technique IDs are `AML.T…`, mitigation IDs `AML.M…`. "Licence" is the class from §2.0. Rows marked *design* are ours, not Microsoft products.

| # | Control (catalogue ref) | OWASP LLM | OWASP ASI | ATLAS technique → mitigation | Licence | Status · disposition |
|---|---|---|---|---|---|---|
| 1 | Agent identities, sponsors, managed identities, least-privilege RBAC (E1, E2, G2) | 06 | 03, 10 | T0053, T0098 → M0026, M0028 | INC | GA · ADOPT |
| 2 | Two planes: read-only reasoning identities, just-in-time execution identity per Move (*design*, E6) | 06 | 02, 03, 10 | T0053, T0101 → M0037, M0029 | INC; PIM is USR for humans | Mechanism open (F4) · ADOPT |
| 3 | Authenticated human approval in an append-only record; two named approvers for purchases (*design*) | 06, 09 | 09 | T0053 → M0029 | INC | ADOPT |
| 4 | Conditional Access, ID Protection, governance for agents (E3–E5) | 06 | 03 | T0098 → M0026, M0027 | USR Agent 365 + P1/E3 | Documented · EVALUATE |
| 5 | Workload ID Premium for execution identities (E7) | 06 | 03 | T0098 → M0026 | IDN $3 | GA · EVALUATE |
| 6 | Gateway token limits, quotas, budgets, circuit breaker (SG6) | 10 | 08 | T0034.002, T0029 → M0004, M0036 | INC (APIM tier) | Documented · ADOPT |
| 7 | Gateway content safety and `shield-prompt` on untrusted routes (SG5) | 01, 05 | 01 | T0051.000, T0051.001, T0054 → M0020, M0033 | TOK €0.33/1K records | ADOPT |
| 8 | Foundry guardrails and Prompt Shields incl. document attacks (SG1, SG2) | 01, 02, 05 | 01 | T0051, T0054 → M0020, M0033 | INC (billing `UNVERIFIED`) | No Preview label (models) · ADOPT |
| 9 | Agent guardrails: tool-call and tool-response checks, Task Adherence, PII (SG3) | 01, 02, 06 | 01, 02 | T0053, T0086 → M0030, M0033 | as 8 | Preview · ADOPT-PREVIEW |
| 10 | FIDES labels and AGT policy engine (SG7, SG8) | 01, 06 | 01–10 claimed (README: 7 full, 3 partial) | T0051.001, T0053, T0086, T0101, T0118 → M0028, M0030, M0032, M0033, M0037, M0038 | OSS | Preview, experimental · ADOPT-PREVIEW, EVALUATE |
| 11 | Hosted-agent VM isolation; sandboxes for any generated code (SG10) | 06 | 05, 10 | T0053 → M0032 | consumption | GA per attachment · ADOPT |
| 12 | Exfiltration control: NSP, private endpoints, gateway or firewall egress; hosted egress policy (SG11, SG12) | 02 | 02 | T0086 → M0032 | NSP INC | NSP GA · ADOPT; egress Preview · WATCH |
| 13 | Azure Policy: approved models and tools, content-filter minima, no local auth, private link (G2–G6) | 03 | 04 | T0010.005, T0110 → M0014, M0019 | INC | Built-ins not marked Preview, some Preview · ADOPT, ADOPT-PREVIEW |
| 14 | MCSB AI-1…7 and Defender CSPM AI posture (G1, D2) | 03 | 04 | T0010 → M0016, M0023 | INC; RES €4.50/resource-month | EVALUATE (D2) |
| 15 | Defender for AI Services (D3) | 01, 02 | 01 | T0051, T0054 → M0024 | TOK €0.70/M tokens | GA · EVALUATE |
| 16 | Defender for Resource Manager, Key Vault, Storage (D6–D8) | — | 02, 10 | T0101 → M0024 | RES €0.2–9/month | Not stated (priced plans) · ADOPT, EVALUATE |
| 17 | Defender for APIs (D5) | 10 | 08 | T0029 → M0004 | RES ≥ €176/month | EVALUATE |
| 18 | Diagnostic logs to SIEM; Sentinel analytics and lake (L1–L3) | all (detection) | 08, 10 | all → M0024 | TOK | Logs documented, lake GA · ADOPT |
| 19 | Purview Audit, DSPM, DLP (P1–P3, P6) | 02 | — | T0086, T0085 → M0024 | INC, PAYG | WATCH |
| 20 | Encryption: platform keys; Key Vault CMK (K1, K2) | 02 | — | T0085 → M0005, M0012 | INC; RES | Default · ADOPT; CMK EVALUATE |
| 21 | Confidential computing (C1) | 02 | — | T0085 → M0041 | RES | N/A |
| 22 | WAF with Front Door or Application Gateway (W1, W2), only with public ingress | 10 | 08 | T0029, T0006.003 → M0004 | RES ≥ €290/month | Not stated · EVALUATE |
| 23 | Red teaming: AI Red Teaming Agent, PyRIT, ASSERT (R1, R2, SG9) | 01, 02, 06 | 01, 02, 10 | broad → M0035 | consumption; OSS | Preview, GA · ADOPT-PREVIEW, ADOPT |
| 24 | Memory and knowledge hardening: provenance on every claim, replicate before rely, human review of "known" claims (*design*) | 04, 08, 09 | 06 | T0070, T0080 → M0025, M0031 | INC | ADOPT |
| 25 | Supply chain: pinned model, prompt and Move versions; signed Moves; AI-BOM; dependency scanning in CI (*design*) | 03 | 04 | T0010.001, T0010.005, T0110 → M0013, M0014, M0023 | INC, OSS | ADOPT |
| 26 | Output handling: schema-validated output, escaping for cards, KQL and Bicep, dry-run Moves (*design*) | 05 | 02, 05 | T0077 → M0033 | INC | ADOPT |
| 27 | Prompt hygiene: no secrets or estate data in system prompts; prompts treated as public (*design*) | 07 | — | T0069, T0084 → M0020, M0021 | INC | ADOPT |
| 28 | Disclosure and numeric checks: Art. 50 notices, evaluators for savings figures, confidence shown (*design*) | 09 | 09 | — | INC | ADOPT |
| 29 | Kill switch, SLOs and scope-drift detection for agents (AGT Agent SRE; gateway) | 10 | 08, 10 | T0034.002 → M0036, M0038 | OSS | Preview · ADOPT-PREVIEW |
| 30 | Lab expiry and clean-up of anything an agent creates (*design*) | 06 | 10 | — → M0043 | INC | ADOPT |
| 31 | Data minimisation: stable owner IDs in prompts, redaction before logs and Commons publication, human review of anything that leaves the estate (*design*) | 02, 07 | 06 | T0086, T0085 → M0029, M0033 | INC | ADOPT |
