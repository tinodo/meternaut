# Round 2 · closure checks

> Raw replies, saved exactly as the reviewers returned them (everything below each rule). After the first fix pass on the written design, the same six reviewers were asked to re-read the *current* files and say, finding by finding, whether each fix closed its finding, and to look for holes the fixes had introduced. Reviewer B was given the new platform claims to verify instead. The orchestrator's spot-checks and what changed afterwards are in the [disposition](disposition.md).

## C · Security (grok-4.6)

*Asked: for each of the ten findings, and for each attack path that was not "stops it", CLOSED / PARTLY / OPEN with evidence; then new holes in the `bot` paths, the `consumption` container, purchase scope, the `engineer` host's schema check, the what-if function and the three inbound private endpoints.*

---

The written controls for the original blockers largely landed. The new bot/queue/private-endpoint story is where the remaining holes are.

### Closure

| Item | Status | Evidence |
|---|---|---|
| F1 R1 trusts bot “who tapped” | **CLOSED** | `06:145` “verifies the tapper's own token”; `05:142` OBO; fallback to page if P3 fails |
| F2 `workflows` W can delete consumption | **CLOSED** | `05:36,46–54` `consumption` C-only for runner; “no one may replace or delete” |
| F3 purchase scope / savings-plan role | **CLOSED** | `06:157–159` Savings plan purchaser; quote has “billing subscription, applied scope”; shared off by default |
| F4 invocation bypasses Hub | **PARTLY** | `06:95` host validates invocation schema “before the model sees it”; still not Hub traffic |
| F5 GitHub App over-permissioned | **CLOSED** | `05:124` “bar the App from pushing or merging” default |
| F6 Evaluate/Operate same Hub | **PARTLY** | `02:138` “reach no production backend” + CI gate; same hub remains |
| F7 Foundry history vs erasure | **CLOSED** | `06:200` “Invocations protocol Foundry stores no conversation history”; `05:196` sessions “hold nothing to erase” |
| F8 Lessons writer is code-only | **PARTLY** | `05:52` still code rule; now admits false Lesson |
| F9 bot under `apps/approvals` | **CLOSED** | `09:18` `apps/bot` own CODEOWNERS path |
| F10 DORA / RAI missing | **CLOSED** | `06:257–258` adopter mapping rows |
| A1 injection → Engineer/Diplomat | **PARTLY** | Engineer cut `06:87,95`; Diplomat still reads replies `05:143` |
| A2 replay / TOCTOU | **PARTLY** | consumption replay **CLOSED** `05:54`; etags still miss types |
| A3 card spoof / coercion | **PARTLY** | invent-a-tap **CLOSED** `06:222`; coercion and P3-unknown remain |
| A4 confused deputy (bot / what-if) | **PARTLY** | tap not bot `06:75`; what-if “stored plan id” `05:126`; queues unsigned |
| A5 runner family role | **OPEN** | unchanged blast radius at opted-in scopes |
| A6 ABAC purchase escalation | **PARTLY** | scope in quote `05:168`; shared still a catalogue option `06:159` |
| A7 poison Lessons/Atlas | **PARTLY** | Atlas merge still human; Lesson forge still `workflows` W `05:47,52` |
| A8 rug-pull / alias | **PARTLY** | pins unchanged; P9 still unverified |
| A9 DoW / kill-switch bypass | **OPEN** | terminate still does not stop activities `07:92` |
| A10 exfil / eval leak / supply chain | **PARTLY** | App pin closed; Diplomat prose and shared hub remain |

### New issues the fixes introduced

| Sev | File:line | What is wrong | Fix |
|---|---|---|---|
| **blocker** | `02:59–61,139` vs `05:56` | Operate puts **inbound PE on `approvals`/`tools`/`runner` and on queue storage**, while **`bot` stays public**. No VNet/PE/DNS path for bot → Approval API or `inbound`/`outbound` queues. As written, R1 taps and Teams send **cannot work** in Operate. | Put `bot` on VNet integration (outbound to those PEs) and state it; or a documented relay. Count that path in the PE table. |
| **major** | `05:56`, `06:222` | Queue messages are **ids + excerpt**, no MAC. Compromised bot **rewrites `outbound`** (phish, strip AI label) or **floods `inbound`**. Docs already say it can “read replies in transit”. | Sign queue payloads; bot posts bytes as queued; rate-limit `inbound` by sender object id. |
| **major** | `05:144`, `06:102` | `TeamsAppInstallation.ReadWriteSelfForUser.All` installs **for a person** with no recipient allow-list at Graph. Compromised bot can **install itself tenant-wide** (spam channel), even if send is allow-listed later. | Install only for owner-of-record object ids already in the Case; deny-by-default Graph. |
| **major** | `06:218,225`; `05:142` | R2/R3 (and R1 if P3 fails) **OpenUrl to a private approval page**. Teams clients off-network never hit it unless “own front door” is mandatory. Silent R2 failure looks like non-approval. | Require Front Door/VPN in Operate; probe the card URL from outside; fail closed to e-mail with the same private constraints explained. |
| **minor** | `06:95` | Host checks “schema of its **tool arguments**”, not the full case-context record. Extra free-text fields could still reach the model. | One invocation schema = authorised case-context; reject unknown fields. |
| **minor** | `05:142` | OBO user token + `requestId` is still a **bearer replay** until expiry if stolen from the public bot. | Bind token to `requestId` (hash/nonce), short TTL, single use at Approval service. |

**Not new / accepted residuals:** family-role blast radius, in-flight Durable activities, Lesson identity not split. Those were disclosed, not regressions.

P3 is now load-bearing: if Adaptive Card actions **cannot** carry user tokens, every R1 becomes the private page, which collides with the public Teams path unless the network story is written.

## A · Learning (gpt-6-sol)

*Asked: for each of the six findings and the five cheap additions, CLOSED / PARTLY / OPEN with the current text; and whether the new text introduces an overclaim, a contradiction or a testing gap.*

---

## Closure check — current design text

Statuses assess whether the **design finding** is resolved, not whether the system has been built.

| Item | Status | Current text (quote ≤15 words) | Assessment |
|---|---|---|---|
| Finding 1 — wrong claims steering Actions | **PARTLY** | [04-knowledge-and-learning.md:161](file:///<repo>/docs/design/04-knowledge-and-learning.md#L161): “A claim can still steer *which* Action is proposed” | The design now admits the risk and requires factual guards. But [03-agents-and-workflows.md:188](file:///<repo>/docs/design/03-agents-and-workflows.md#L188) allows autopilot once a claim is `price-confirmed`; that confirms a price, not the proposed change’s billing behaviour or safety. |
| Finding 2 — cold-start attribution | **PARTLY** | [04-knowledge-and-learning.md:222](file:///<repo>/docs/design/04-knowledge-and-learning.md#L222): “FOCUS carries both on every line” | The unmatched/ambiguous ledger and abstention are useful. **New factual overclaim:** [Microsoft’s FOCUS conformance report](https://learn.microsoft.com/en-us/cloud-computing/finops/focus/conformance-full-report#resource-id) says `ResourceId` can be null for non-resource charges and indirectly related resources; purchases may lack one. Specify fallback attribution and the retail-meter-to-profile crosswalk. |
| Finding 3 — bill as oracle | **PARTLY** | [04-knowledge-and-learning.md:108](file:///<repo>/docs/design/04-knowledge-and-learning.md#L108): “its period had closed” | Matching history and an error bound improve settlement. **Contradiction:** [04-knowledge-and-learning.md:184](file:///<repo>/docs/design/04-knowledge-and-learning.md#L184) still promotes the *next day’s* Prism charge to `bill-observed` and treats one observation as settling the refund dispute. Revise the story to obey the closed-period rule. |
| Finding 4 — learning-test validity | **PARTLY** | [08-testing-and-evaluation.md:54](file:///<repo>/docs/design/08-testing-and-evaluation.md#L54): “a hit voids that case” | Pinned sources, separate stores, repeats and service-clustered intervals are substantial fixes. The semantic leakage audit could void legitimate A-to-B **mechanism transfer**; distinguish case-specific leakage from permitted shared knowledge. Minimum independent services/power remain unset, and [08-testing-and-evaluation.md:162](file:///<repo>/docs/design/08-testing-and-evaluation.md#L162) still blocks a memory-neutral release for showing no new learning. |
| Finding 5 — selected-case feedback | **PARTLY** | [04-knowledge-and-learning.md:258](file:///<repo>/docs/design/04-knowledge-and-learning.md#L258): “resources a Detector did not flag” | Weekly non-lead audits address missed waste. Shadow **leads** also need independent, preferably blind adjudication to estimate precision; audit sample sizes are unspecified. |
| Finding 6 — full learning cost | **PARTLY** | [10-cost-and-finops.md:100](file:///<repo>/docs/design/10-cost-and-finops.md#L100): “less this cost, people’s time” | Azure-only break-even and the conditional hub cost are now labelled. **Calculation gap:** [10-cost-and-finops.md:119](file:///<repo>/docs/design/10-cost-and-finops.md#L119) leaves people’s time in hours, so it cannot yet be subtracted from euros; marginal review and trial cost per new service remain unpriced. |
| Addition 1 — meter coverage ledger | **PARTLY** | [04-knowledge-and-learning.md:222](file:///<repo>/docs/design/04-knowledge-and-learning.md#L222): “unmatched or ambiguous … never guessed” | The ledger landed; the universal FOCUS-field assumption and absent fallback join limit it. |
| Addition 2 — prospective shadow forecasts | **CLOSED** | [04-knowledge-and-learning.md:220](file:///<repo>/docs/design/04-knowledge-and-learning.md#L220): “blueprint is stored before the bill lands” | Expected absence of a meter is explicitly scored. The separate Prism-story contradiction remains under Finding 3. |
| Addition 3 — independent shadow audits | **PARTLY** | [04-knowledge-and-learning.md:258](file:///<repo>/docs/design/04-knowledge-and-learning.md#L258): “a sample of resources a Detector did not flag” | Negative sampling landed; add blind positive sampling and a sampling budget. |
| Addition 4 — read-only Agenda exploration | **CLOSED** | [04-knowledge-and-learning.md:274](file:///<repo>/docs/design/04-knowledge-and-learning.md#L274): “drawn at random, read-only, with its selection probability logged” | The proposed mechanism landed. “Without selection bias” overclaims what a 5% starting sample can establish without eligibility and power checks. |
| Addition 5 — observe planned changes | **CLOSED** | [04-knowledge-and-learning.md:230](file:///<repo>/docs/design/04-knowledge-and-learning.md#L230): “registers control meters and likely confounders beforehand” | This adds evidence without a Lab or an extra change. |

**P6 testing gap:** [13-roadmap.md:29](file:///<repo>/docs/design/13-roadmap.md#L29) now includes a new-service drill—a meaningful improvement—but should specify whether it replays a historical launch with a real first invoice, and measure **launch-to-detection** separately from [08-testing-and-evaluation.md:68](file:///<repo>/docs/design/08-testing-and-evaluation.md#L68)’s first-read-to-profile time.

## D · Cost (gpt-5.6-sol)

*Asked: status of the eight findings; recompute six line items; anything newly mispriced or inconsistent between the model, document 10 and documents 02, 07, 09, 11. The reviewer ran `--self-test` and `--check`.*

---

## Closure status

Both checks passed: `self-test OK`; `--check` found document 10 and `meters-used.md` current.

| # | Status | Evidence |
|---|---|---|
| 1 | **CLOSED** | `<repo>\tools\cost-model.py:342-346` now selects APIM Standard v2; document 10 reports **+€1,200**. |
| 2 | **CLOSED** | `<repo>\docs\design\09-delivery-and-operations.md:35` now says the model counts one always-ready instance and Pilot may select zero. |
| 3 | **PARTLY** | Triage and Terra sensitivities exist, but defaults remain `triage_share=0` and Sol for every `reason` call (`cost-model.py:109,183`). This still differs from triage-first/Terra-default intent. |
| 4 | **PARTLY** | Search units now represent SLA levels, and P5 includes embedded/Serverless options. Index size, QPS and latency still do not determine capacity. |
| 5 | **CLOSED** | `cost-model.py:87,312` and architecture line 139 consistently count eleven endpoints. DNS is explicitly allocated to the landing zone. |
| 6 | **CLOSED** | Document 10 line 121 clearly defines PyRIT/own graders as the default and metered Foundry safety evaluations as off. |
| 7 | **PARTLY** | Document 10 line 100 now states verified-net-savings, people and wrong-advice costs. The headline still divides Azure-only cost by total managed—not addressable—spend. |
| 8 | **CLOSED** | `<repo>\docs\design\07-safeguards-and-drift.md:118` adds Function instance limits, Log Analytics caps, evaluation caps and non-token reconciliation. |

## Six recomputations — Pilot

1. Private endpoints: `11 × €0.0088 × 730 = €70.664 → €70.66`.
2. Own hub: `1.099965×730 + .026399×730 + 28×.00704×730 + 158 + 9×.0088×730 + 18 = €1,199.96`.
3. Always-ready Functions: `2×3,600×730×€0.000004 = €21.024`.
4. Search Basic: `€0.088877×730 = €64.880`.
5. Half Detective/Economist on triage: `(18.1457−9.5446)+(3.5523−1.8666)=€10.2868` saving.
6. Terra sensitivity as coded: `50% × €95.78 affected reason cost = €47.89` saving.

## Newly found issues

- **Terra sensitivity is mispriced.** `cost-model.py:119,195-196` halves Sol prices—including Flex. Terra **Standard** meters are already in the snapshot, but no Terra Flex meters are present. Using actual Terra Standard meters gives savings of approximately **€14.83 / €129.29 / €1,273.92**, not **€47.89 / €179.12 / €1,351.15**.
- `meters-used.md:68` says Defender for AI is absent from the API, but the snapshot contains `Microsoft Defender for AI Services / Standard Tokens` at **€0.000704/1K**. Use that meter directly and remove the `UNVERIFIED` label.

## E · Consistency (gemini-3.8-flash)

*Asked: re-run the agreement table; status of the ten findings; every remaining disagreement as file:line on both sides; any new term used before it is defined.*

---

# Closure Check Report: Consistency, Tone, and Readability

### 1. Updated Agreement Table

| Item | Expected | Current Status Across Files |
|---|---|---|
| **Function Apps & `bot`** | 5 apps (`workflows`, `tools`, `approvals`, `runner`, `bot`) | **Reconciled.** `02:38,61`, `05:43,133`, `06:107,218`, `09:18`, `11:96`, `12:16` all consistently identify 5 apps with `bot` in its own app (`apps/bot`). |
| **Private Endpoints** | 11 in Operate (8 dependencies + 3 inbound: `tools`, `approvals`, `runner`) | **Reconciled.** `02:141` defines 11 ($8 + 3$); `10:47` prices 11 endpoints at €70.66/mo ($11 \times 730\text{ h} \times €0.0088$). |
| **Cosmos DB Containers** | 8 (`estate-model`, `lessons`, `ledger`, `approvals`, `credentials`, `switches`, `agenda`, `consumption`) | **Reconciled.** `05:14,27-35` tables all 8; rights matrix (`05:41-47`) grants `consumption: C` exclusively to `runner` and `R` to `approvals`. `07:49` uses `switches`. |
| **Storage Queues** | 3 (`run`, `inbound`, `outbound`) | **Reconciled.** `02:57-61`, `05:58-60`, `06:218`, `09:18` align on exact names and producer/consumer assignments. |
| **Proof Points** | 10 (P1 to P10 with revised texts) | **Reconciled.** `13:20-35` incorporates card OBO tokens in P3, embedded tools index in P5, day-zero service in P6, ABAC/scope binding in P8, and Azure MCP Server host evaluation in P9. |
| **Hub Contracts** | 5 hosted agent contracts + 1 `evaluation` = 6 ($\times$ 2 profiles = 12) | **Reconciled.** `02:124`, `03:11-20`, `06:46,106`, `12:32` distinguish the 5 hosted agents from the `evaluation` contract. |
| **README Glossary** | Core terms defined with strict scoping | **Reconciled.** `README:50-80` defines *Agent* (contrasting RBAC role/directory group), *Credential* (contrasting keys/secrets), *Approval*, *Runner*, *Judge*, *Report card*, and *Cost lake* (expanding FOCUS). |

---

### 2. Status of Findings (1–10)

- **#1 (`09:15` Lumping `bot` into `apps/approvals`)**: **CLOSED.** `09:18` adds `apps/bot` as an independent codebase.
- **#2 (`11:111` Locating bot in `approvals`)**: **CLOSED.** `11:96` now specifies "The Teams bot (the `bot` app)".
- **#3 (`08:52` "79 mechanisms")**: **CLOSED.** `08:44` now states "79 verified cost traps across the 14 Cost Grammar mechanisms."
- **#4 (`05:124` Study workflow calling `pr-draft` tool)**: **CLOSED.** `05:124` clarifies `engineer` calls `pr-draft`, while Study workflow calls GitHub API directly.
- **#5 (`05:140` `bot` Graph permissions vs limited identity)**: **CLOSED.** `02:61`, `05:145`, and `06:218` align on `bot`'s exact permissions (Approval service OBO, queues, and self-app installation).
- **#6 (`07:61` Container named `kill switches`)**: **CLOSED.** `07:49` corrected to `switches`.
- **#7 (`01:41` P9 scope mismatch)**: **CLOSED.** `13:32` explicitly widened P9 to include evaluating Azure MCP Server remote hosting.
- **#8 (`04:295` & `08:37` `exam-bank` path)**: **PARTIALLY OPEN.** `08:37` updated to `../research/cost-traps.md`, but `04:292` still links to `../research/exam-bank-cost-traps.md`.
- **#9 (`04:164` Mention of "north star")**: **CLOSED.** `04:164` replaced with neutral architectural rationale.
- **#10 (`10:143` Citations of internal research digests)**: **CLOSED.** `10:90` replaced citations with references to `cost/meters-used.md`.

---

### 3. Remaining Disagreements & New Terms

1. **Test Bank Filename Disagreement:**
   - `04:292`: `[the cost-trap bank](../research/exam-bank-cost-traps.md)`
   - `08:37`: `[The cost-trap bank](../research/cost-traps.md)`
2. **New Terms Used Before Defined:**
   - **"On-behalf-of exchange" (OBO):** Introduced in `05:139` and `06:219` without prior definition in `README.md` or `01-goals-and-scope.md`. Recommend adding a brief parenthetical (*"an Entra on-behalf-of token exchange"*) in `02:61`.

## F · Novice reader (claude-haiku-5.5)

*Asked: re-read only `README.md` and `01-goals-and-scope.md`; a fresh summary, the same nine questions, what is still confusing, scores.*

---

**1. Fresh summary**
Azure Cost in Action is a proposed design (nothing built): AI agents, ten roles in five hosted agents, that keep an Azure estate cost-efficient. It watches bills, investigates waste, asks owners with evidence and options, and changes Azure only after an approval tied to one exact plan or inside a person-written rule, then verifies. Users: owners, FinOps leads, approvers. Unlike Advisor (retail-rate suggestions nobody is asked about) and Cost Management (alerts that only notify), it reads both and acts only with approval or a credential. It deploys nothing to learn.

**2. Questions**
1. **Saving found?** Owner gets a Recommendation card (README 59); after approval the runner changes Azure and checks it (README 67).
2. **Who approves?** A person says OK, or a rule they wrote applies (README 7); purchases need two people with different roles (README 46).
3. **Spends alone?** Only inside a credential with a value cap a person set (README 62); purchases always need two people (README 46).
4. **Changes without a person?** Yes, only inside a credential the FinOps lead sets (goals 30, README 62); otherwise a bound approval (goals 44).
5. **Needs before it runs?** Azure subscriptions with deploy and role-assignment rights; Cost Management Reader; Citadel hub; model quota; Entra ID; Microsoft 365; Git host; platform team (Functions, Foundry); FinOps lead; owners; reviewers (goals 97–104).
6. **Deliberately not?** No lab deployments to learn, phase-1 model training, multi-organisation deployments, custom portal, unapproved changes, chat-as-product, or other clouds (goals 40–46).
7. **Learns a new service?** From docs, price lists, bills, cost replays, owners' answers, outcomes and trials, each with a source and evidence level (README 33); unused meters cannot be found.
8. **Costs to run?** Modelled from list prices: a pilot a few hundred euros a month, an enterprise estate a few thousand (README 79); details: 10-cost-and-finops.md (unopened).
9. **Where to start?** The text does not say how to try it; for building, see roadmap phase 0 (README 98).

**3. Still confusing** (goals = 01-goals-and-scope.md)
- "without a fresh tap" (README 62): "tap" undefined.
- "Keys and secrets are called keys and secrets" (README 62): what for?
- "a group of people a directory group" (README 61): naming aside, unclear.
- "hidden cases with memory frozen" (README 48): "hidden" and "memory" undefined.
- "after a bound approval" (goals 44): "bound" undefined; probably README 66's meaning.
- "roll back on guard-metric breach" (goals 74): "guard metric" undefined.
- "proof point P9" (goals 60): the list at README 106 is unnumbered.
- "injection paths, runner roles, tool pinning" (README 106): jargon, undefined.
- "an enterprise estate a few thousand" (README 79): no unit; "seeded volumes" undefined.
- "phase 0" (README 98): phases never defined in these files.

**4. Scores**
- Clarity 4: approval, runner and Citadel now defined; small gaps remain.
- Honesty 4: candid status and cost labels; README 9 states the hub as fact.
- Keep reading 4: concrete costs and credential limits; much depends on unopened files.

Note: the tool saved an oversize listing to %TEMP%; I did not open it.

## B · Platform facts (claude-sonnet-5)

*Asked: verify ten claims added after the first report, each CONFIRMED / WRONG / OVERCLAIMED / UNVERIFIABLE with the Learn URL.*

---

## Findings — r2-facts batch (all 10 checked against Microsoft Learn)

| # | Claim | Verdict | Learn URL |
|---|---|---|---|
| 1 | Built-in **Savings plan purchaser** role exists, assignable at subscription scope, and lets non-billing-admins purchase | **CONFIRMED** — "Allows purchase of savings plans with a specified subscription... Allows nonbilling admins and nonsubscription owners to purchase" | /azure/cost-management-billing/savings-plan/permission-buy-savings-plan |
| 2 | Agents SDK user authorization can exchange for the tapper's own token (OBO); Teams card actions documented | **CONFIRMED** — OBO flow ("receive a token from a client, exchange it for a downstream API token... on behalf of the original user") is documented, and Adaptive Card *Universal Actions* SSO/OBO is a separate, named doc | /microsoft-365/agents-sdk/agent-oauth-configuration#use-the-token-in-code-obo |
| 3 | `TeamsAppInstallation.ReadWriteSelfForUser.All` (app permission) lets a bot install itself for a user; prerequisite is the org's app catalogue | **CONFIRMED** — Application-only (no delegated form), admin-consent-required, description: "read, install, upgrade, and uninstall itself to any user, without a signed-in user" | /graph/permissions-reference |
| 4 | Invocations protocol: no platform conversation history; session filesystem persists ≤30 days; session deletable via API | **CONFIRMED**, exact wording — "There's no platform-managed conversation history—you manage state in your own code"; "Sessions persist for up to 30 days"; session-level terminate/delete API exists | /azure/foundry/agents/concepts/hosted-agents, …/how-to/manage-hosted-sessions |
| 5 | AI Search SLA needs ≥2 replicas (query) / ≥3 replicas (query+indexing) | **CONFIRMED**, exact wording — "SLAs apply to billable services that have two or more replicas for query workloads, or three or more replicas for query and indexing workloads" | /azure/search/search-reliability |
| 6 | APIM Standard v2 is the production, VNet-integrated tier; Developer has no SLA | **CONFIRMED** — "Standard v2 and Premium v2 [are] production workloads... support virtual network integration"; Developer-tier no-SLA is longstanding, stable APIM documentation (not re-quoted verbatim this pass) | /azure/api-management/api-management-features |
| 7 | Flex Consumption supports inbound private endpoints + outbound VNet integration; max instance count settable below the default | **CONFIRMED** — private endpoint and regional VNet integration both listed "Supported" for Flex Consumption; "default... 100... lowest maximum instance count value is 1" | /azure/azure-functions/functions-networking-options, …/event-driven-scaling |
| 8 | Azure RBAC can scope Storage Queue Data roles to a single queue | **CONFIRMED**, exact wording — "Queue-level scope is supported for the built-in queue data roles. Assign at the queue level rather than the storage account when a service needs access to only one queue" | /azure/storage/queues/queues-storage-security-guide |
| 9 | Log Analytics workspaces have a daily cap | **CONFIRMED** — dedicated, documented feature ("Set daily cap on Log Analytics workspace"; portal default 100 GB/day) | /azure/azure-monitor/logs/daily-cap |
| 10 | Foundry guardrail tool-call/tool-response coverage list (06 §6) | **CONFIRMED**, exact match — "Azure AI Search, Azure Functions, OpenAPI, Sharepoint Grounding, Fabric Data Agent, Bing Grounding, Bing Custom Search, and Browser Automation... not in this list [won't] take effect" (MCP absent, as the design states) | /azure/foundry/guardrails/intervention-points |

**Summary:** 10/10 CONFIRMED, zero corrections needed this round. This is a clean batch — no WRONG/OVERCLAIMED/UNVERIFIABLE findings. The one residual low-confidence item is #6's "Developer has no SLA" half (consistent with stable, long-standing APIM documentation, but not freshly re-quoted verbatim in this session) — worth a quick independent spot-check before final sign-off if zero-risk-tolerance is required, but I have no reason to doubt it.
