# Round 2 · E — Consistency, tone and readability (model: gemini-3.8-flash)

> Raw report, saved exactly as the reviewer returned it (everything below the rule). Reviewed on 2026-11-01: all 14 files of the written design (`docs/design/`, commit `3543f3b`). Lens: facts that must agree across documents, terms, contradictions, tone, duplication, diagrams, density. Line references like `09:15` mean line 15 of `09-delivery-and-operations.md`. The orchestrator's spot-checks of what this reviewer cited are in the [disposition](disposition.md).

---

# Round 2 Review: Consistency, Tone, and Readability

### 1. Verdict
The design is disciplined, rigorous, and remarkably coherent across 14 documents, establishing genuine architectural depth without hand-waving.
However, minor inter-document contradictions (Function app count/paths, tool calling actors, and Cosmos container naming) compromise implementation precision.
Cleaning up terminology overloading ("role", "credential"), unexpanded acronyms, and internal draft residue ("exam-bank", "north star") will make the specification production-ready.

### 2. Top 5 Fixes
1. **Reconcile Function app count and `bot` hosting across `02`, `09`, and `11`:** `02:38` and `05:133` define `bot` as an independent C#/TS app, but `09:15` and `11:111` omit `apps/bot` and locate it in `apps/approvals`.
2. **Align PR creation and tool invocation semantics:** `05:22` and `12:23` state the Study workflow opens Atlas PRs, but `03:18` assigns `pr-draft` to `engineer`, while `05:124` lists `Study workflow` as calling an agent tool through the Hub.
3. **Disambiguate overloaded terms:** Restrict "role" to agent personas (using "RBAC role" and "directory group" elsewhere) and "credential" to autopilot policy records (using "secret/key" or "federated credential" elsewhere).
4. **Fix the "79 mechanisms" error in `08:52`:** The Cost Grammar defines 14 mechanisms; the 79 gold items are verified traps/rows, not separate mechanisms.
5. **Deduplicate cross-document boilerplate:** Replace multi-file repetitions (profile migration, ACS email retirement, Bot Service networking, and budget latency) with canonical links.

---

### Agreement Table

| Item | Expected | Occurrences & Details | Disagreements & Citations |
|---|---|---|---|
| **Hosted Agents** | 5 (`study`, `investigate`, `skeptic`, `diplomat`, `engineer`) | `02:20`, `02:31`, `03:7-18`, `05:47`, `06:106`, `09:12`, `10:50`, `11:15`, `12:21` | In `02:69`, `evaluation` is listed under "contract per hosted agent" (`study`..`evaluation`), though `03:19` and `06:108` clarify it is an evaluation-harness contract, not a hosted agent. |
| **Roles** | 10 (Scholar, Librarian, Surveyor, Detective, Economist, Auditor, Conductor, Skeptic, Diplomat, Engineer) | `README:15,31`, `02:20`, `03:7-18`, `04:190-204`, `05:12-22`, `07:30`, `08:24-32`, `12:21` | Agree across all files. (Note: "Judge" in `08:69` is an evaluator role under the `evaluation` contract, not a runtime role). |
| **Workflows** | 7 (Watch, Case, Study, Estate refresh, Respond, Strategy, Evaluate and grow) | `02:21`, `03:70-81`, `04:162,254`, `05:45,95`, `07:30`, `08:12`, `11:82`, `12:15`, `13:11-14` | Agree across all files. |
| **Function Apps** | 5 (`workflows`, `tools`, `approvals`, `runner`, `bot`) | `02:31-38`, `05:41-47,133`, `06:107`, `09:14-15`, `10:52`, `11:83,111`, `12:16` | **Disagreement:** `02:38`, `05:133`, `12:16` define 5 apps including `bot`. `09:15` omits `apps/bot` (listing only `workflows`, `tools`, `approvals`, `runner`) and places the Teams bot endpoint in `apps/approvals`. `11:111` states "The Teams bot in `approvals`". |
| **Private Endpoints** | 8 in Operate (Foundry, AI Search, Cosmos DB, Audit Blob, Platform Blob, Queue, Table, Key Vault) | `02:77,81`, `05:173`, `06:207`, `07:16`, `09:22`, `10:55`, `11:87,131`, `12:83`, `13:44` | Agree across all files. (Cost in `10:55` exactly reflects 8 endpoints: $8 \times 730\text{ h} \times €0.0088 = €51.39$). |
| **Approval Classes** | 3 (R1: 1-tap, non-prod; R2: web page MFA context; R3: 2-person, phishing-resistant) | `03:55,155`, `04:243`, `05:135-144,162`, `06:143-149`, `07:69`, `08:65,128`, `09:88,147`, `11:8`, `12:68`, `13:12-14` | Agree across all files. |
| **Proof Points** | 10 (P1 to P10) | `README:88`, `01:41`, `03:25,32`, `04:155,310`, `05:101,133`, `06:48,157`, `07:148-151`, `08:130,167`, `09:28,84`, `11:19-79`, `12:35-74`, `13:18-30` | Defined in `13:18-30`. Note: `01:41`, `05:101`, `11:79`, `12:57` cite P9 for Azure MCP Server 3.0 / Container Apps hosting, whereas `13:28` defines P9 as Hub tool-pinning drift rejection. |
| **Decisions (ADRs)** | 20 in `12-decisions.md` | `README:27-43` (lists top 10), `02:158`, `06:255`, `11:11`, `12:1-120` | `12-decisions.md` contains 20 ADRs; `README:27` highlights 10 ("Ten decisions that shape it"), clarifying the full list is in `12-decisions.md`. |
| **Cost-Trap Bank & Cost Grammar** | Bank: 145 rows (79 verified, 33 partial, 33 unverified); Grammar: 14 mechanisms | `04:60-83,295,310`, `08:37,52` | **Disagreement:** `04:60` correctly identifies 14 grammar mechanisms. `08:37` states 79 verified rows become gold labels, but `08:52` incorrectly writes: *"The limit: the gold covers 79 mechanisms."* |
| **Technology Register Rows** | 63 technologies in 7 tables + 4 non-Microsoft components = 67 rows | `11:1-124` | Count is consistent across `11-technology-register.md`. |
| **Model Aliases** | 5 (`triage`, `reason`, `judge`, `embed`, `batch`) | `02:46`, `03:11-20,131`, `06:176,192`, `08:69,122`, `10:148`, `11:21-36`, `12:39` | Agree across all files. (`fast` is not an alias; "fast clock" refers to metrics/activity cadence in `02:157` and `04:307`). |
| **Hub Contracts** | 6 contracts (`study`, `investigate`, `skeptic`, `diplomat`, `engineer`, `evaluation`) $\times$ 2 profiles = 12 | `02:69`, `03:11-20`, `06:46,106`, `07:12`, `08:12,171`, `09:13`, `12:32` | Agree across all files. |
| **Foundry Profiles** | 2 (Evaluate / dev; Operate / prod) | `02:71-85`, `06:203-211`, `07:111`, `08:12`, `09:22-26`, `10:16-67`, `12:81-86`, `13:10-12` | Agree across all files. |
| **Tool Table** | 11 published tools | `02:69`, `03:11-18`, `05:108-125`, `06:86`, `09:13`, `12:55` | Exactly 11 tools (`docs`, `atlas`, `estate-read`, `cost-query`, `price-sim`, `directory`, `ledger`, `ledger-propose`, `plan`, `channels-draft`, `pr-draft`). |
| **Data Stores** | 8 categories / 7 Cosmos DB containers | `02:22`, `04:11-15`, `05:12-35`, `06:23`, `07:61`, `09:128-130`, `12:47` | **Disagreement:** `05:33` names the container `switches`, while `07:61` names it the `kill switches` container. |

---

### Findings Table

| # | Severity | File:line | Quote (at most 25 words) | What is wrong | Proposed fix |
|---|---|---|---|---|---|
| 1 | **blocker** | `09:15` | `apps/approvals, apps/runner \| Approval service and credential evaluator, Teams bot endpoint, web page; action runner, verifier` | Lumps Teams bot into `apps/approvals`, omitting `apps/bot`. Contradicts 5 Function apps in `02:31`, `05:133`, `12:16`. | Add `apps/bot` row with description: "Teams bot endpoint (C#/TS Agents SDK); token validation". |
| 2 | **blocker** | `11:111` | `Microsoft 365 Agents SDK \| The Teams bot in approvals \| GA (1.x)` | States bot runs in `approvals`. Contradicts dedicated `bot` Function app in `02:38` and `05:133`. | Change to: "The Teams bot in the `bot` Function app". |
| 3 | **major** | `08:52` | `The limit: the gold covers 79 mechanisms. More instances widen the sets, not the mechanisms` | Conflates 14 Cost Grammar mechanisms (`04:60`) with 79 verified test bank rows (`08:37`). | Change to: "The limit: the gold covers 79 verified cost traps across the 14 mechanisms." |
| 4 | **major** | `05:124` | `pr-draft \| ... \| engineer; the Study workflow (Atlas change sets)` | Workflows run in `workflows` Function app and do not call Hub agent tools directly (`02:47`). | Clarify that `pr-draft` tool is called by `engineer`; the Study workflow creates PRs via GitHub App API directly. |
| 5 | **major** | `05:140` | `the bot installs itself through Graph (TeamsAppInstallation.ReadWriteSelfForUser.All)` | Contradicts `02:38`, `05:43`, and `06:214` stating `bot` identity can only call Approval service and has no Graph rights. | Assign `TeamsAppInstallation` to `workflows` app or document Graph permission on `bot`. |
| 6 | **major** | `07:61` | `They are items in the kill switches container of Cosmos DB.` | Container is defined as `switches` in `05:33`. Cosmos container IDs cannot contain spaces. | Change `kill switches` to `switches`. |
| 7 | **minor** | `01:41` | `Azure MCP Server and cost MCP toolsets ... evaluated in P9` | P9 in `13:28` is Hub tool pinning. P9 is overloaded with Azure MCP Container Apps evaluation (`05:101`, `11:79`, `12:57`). | Clarify P9 question in `13:28` to include Azure MCP Server remote hosting evaluation, or separate them. |
| 8 | **minor** | `04:295` | `gold labels from [the cost-trap bank](../research/exam-bank-cost-traps.md) are described there.` | Exposes internal development term "exam-bank". (Also in `08:37`). | Rename reference/path to `cost-trap-bank.md`. |
| 9 | **minor** | `04:164` | `The north star imagined a place where the system deploys a new service and watches its meters.` | Self-referential document artifact; unneeded in public architecture specification. | Replace with: "Earlier architectural concepts considered an active experimentation lab; this design replaces it with bill observation." |
| 10 | **minor** | `10:143` | `Citadel research digest section 7 ... security research digest D3` | Unexplained citations of private session research digests. | Replace with direct factual note: "(Empirical estimate based on Azure AI Language PII list pricing)". |

---

### Sectional Analyses

#### (b) Terms & Acronyms
- **Unexpanded Acronyms:** `FOCUS` (`01:40`), `EA`/`MCA` (`05:52`), `DPIA` (`06:195`), `RPO`/`RTO` (`09:128`), and `ABAC` (`13:27`) are never expanded. Expand on first appearance.
- **Glossary Overloading:**
  - *"Role"*: Overloaded across 4 meanings: Agent persona (`03:3`), human stakeholder (`01:16`), Azure RBAC role (`02:78`), and Entra directory group (`05:162`).
  - *"Credential"*: Overloaded across Autopilot policy record (`03:159`), secret/key (`07:33`), and OIDC federated credential (`09:34`).

#### (c) Contradictions
- **PR Authoring:** `09:5` asserts *"Agents open pull requests; humans merge them"*, whereas `05:22` and `12:23` state the Librarian only outputs a change set and deterministic workflow code opens the PR.
- **Message Dispatch:** `02:50` says `workflows` and `bot` send messages to Teams/Graph, but `02:38` and `06:214` explicitly restrict `bot` to forwarding opaque IDs to `approvals`.

#### (d) Tone & Style
- `04:298-303`: Monday digest mock uses conversational first-person ("This week I learned", "Two Lessons from your team", "I said 79 %"). Rewrite in neutral system report format.
- `04:188`: The fictional narrative ("Azure Prism") is engaging but should be explicitly branded as an illustrative scenario to prevent confusion with actual Azure products.

#### (e) Duplication & Links
1. **Foundry Profile Immutability** (`02:80`, `06:210`, `09:23`, `12:83`): Keep in `02:80`; link from `06` and `09`.
2. **ACS Email Retirement** (`01:74`, `05:143`, `06:117`, `11:113`, `12:79`): Keep in `11:113` and `05:143`; link from `01`, `06`, `12`.
3. **Bot Service Inbound Allow-List** (`02:38`, `05:137`, `06:215`, `11:112`, `12:78`): Keep in `06:215`; link from `02`, `05`, `12`.
4. **Budget Evaluation Latency** (`01:40`, `07:104`, `09:183`, `10:182`, `12:107`): Keep in `07:104`; link from `09`, `10`, `12`.

#### (f) Mermaid Diagrams
All 16 diagrams across the 14 documents correctly depict non-trivial topologies: loops, hubs, state transitions with rollbacks, or parallel forks. Labels are clean and readable.

---

### (g) Density & Rewrites

**Top 10 Densest Passages:**
1. `03:22`: *"A prompt agent is a Foundry definition of instructions and tools, with no code; a hosted agent is our code in a managed sandbox..."*
2. `03:65`: *"Work starts on triage and moves to reason when a result fails its schema, a tool errors, the Skeptic objects..."*
3. `04:188`: *"Tuesday 09:00: Microsoft announces Azure Prism, a managed retrieval service. The price snapshot shows six new meters. By 10:30..."*
4. `05:101`: *"Our default estate-read is a typed tool of our own on Resource Graph, Monitor and the Advisor tables, because it must return..."*
5. `05:126`: *"The untrusted_excerpt holds its source (tool, field, resource id), length, content hash, the Prompt Shields result and the text inside..."*
6. `06:47`: *"Tool rug pull \| A tool or server changes after approval \| Own tools: the contract's operation allow-list... Other servers: pinned version..."*
7. `06:154`: *"Purchases use their own identity with no standing role. 1. After the second approval, the Approval service gives that identity..."*
8. `07:27`: *"what-if of each template (stacks have none yet); stack deny settings; Policy state plus an on-demand scan after a change..."*
9. `08:113`: *"It builds on PyRIT and Foundry's safety evaluators (concept). Cloud runs support Foundry prompt agents and hosted container agents with Azure..."*
10. `09:23`: *"That setting is fixed when the Foundry account is created (Learn), so moving from evaluate to operate means a new account..."*

**Rewrites:**

- **Passage 4 (`05:101`):**
  > *Original:* Our default `estate-read` is a typed tool of our own on Resource Graph, Monitor and the Advisor tables, because it must return structured fields and respect the read budget. Azure MCP Server 3.0 (generally available since October 2026) is an optional extra for generic Advisor and Monitor reads, evaluated in P9: it has a documented `Read only` start option, but Learn documents remote hosting only as a container app, which this design does not otherwise use. If it is adopted it runs under an identity that holds Reader roles only (the identity is the hard control, the option is defence in depth), its image is pinned by digest, and the Hub rejects `tools/list` drift. Its raw JSON can carry free text that the Hub cannot screen (MCP responses stream), so every answer counts as untrusted and only `investigate` and `skeptic` may call it.
  >
  > *Rewrite:* Our default `estate-read` queries Resource Graph, Monitor, and Advisor directly, returning structured fields within our ARM read budget. Azure MCP Server 3.0 is an optional fallback evaluated in P9, but currently requires Container Apps for remote hosting. If adopted, it runs under a Reader identity with pinned image digests. Because streaming MCP payloads bypass Hub content screening, its outputs are treated as untrusted excerpts restricted to `investigate` and `skeptic`.

- **Passage 7 (`06:154`):**
  > *Original:* Purchases use their own identity with no standing role. 1. After the second approval, the Approval service gives that identity the built-in Reservation Purchaser role on one subscription and removes it after the run or at expiry. A custom role that mimics it cannot buy (Learn). 2. The Approval service can create only that assignment: Role Based Access Control Administrator with a condition naming role and principal, free of charge (Learn). 3. The runner buys exactly the stored quote from the reservation calculate step. 4. Every purchase alerts. A daily count or amount above its limit disables the purchase identity.
  >
  > *Rewrite:* Purchases execute under a dedicated identity with no standing permissions. Upon two-person approval, the Approval service temporarily grants this identity the built-in Reservation Purchaser role on the target subscription via conditioned RBAC delegation. The runner executes strictly against the pre-calculated quote ID, raises an immediate alert, and relinquishes the role upon completion or timeout. Any rate or spend breach automatically disables the purchase identity.

---

### 4. What I Verified Myself
- `https://learn.microsoft.com/azure/bot-service/security-faq`: Confirmed Azure Bot Service does not publish fixed inbound IP addresses and does not support inbound IP allow-lists.
- `https://learn.microsoft.com/azure/cost-management-billing/reservations/prepare-buy-reservation`: Confirmed custom RBAC roles cannot purchase reservations; built-in `Reservation Purchaser` is required.
- `https://learn.microsoft.com/azure/communication-services/acs-retirement-and-breaking-changes-guide`: Confirmed Azure Communication Services Email retirement date of September 30, 2028.
- `https://learn.microsoft.com/azure/foundry/agents/concepts/networking-options`: Confirmed virtual network configuration must be specified at Foundry hub/account creation and cannot be toggled later.

### 5. What I Could Not Verify
- Live API response behaviors and token metering for unreleased models (e.g., GPT-6.1 Sol Responses API requirement, GPT-6 Luna Decisions API availability).
- Whether Azure MCP Server 3.0 remote hosting can run natively on Functions Flex Consumption without Container Apps.
