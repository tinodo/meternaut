**Model:** claude-sonnet-5.5 | **Files read:** `docs/design/11-technology-register.md`, `docs/design/12-decisions.md`, `docs/design/13-roadmap.md` (cross-reference checks in `docs/design/02-architecture.md`, `docs/design/03-agents-and-workflows.md`, `docs/design/06-security-and-governance.md`, `docs/design/08-testing-and-evaluation.md`).

## 1. Verdict

**Mostly.** The architecture is technically astute, demonstrating deep, accurate grounding in late-2026 Azure platform realities (such as Flex Consumption, source-code hosted agents, and the AI Hub Gateway accelerator), and an outside architect can readily understand and respect the core boundaries. However, several sections suffer from visible conversation and internal review residue—including an errata bullet labeled "Two corrections," an internal prompt artifact citing "817 updates," and undefined project jargon like "verified bank rows" and "credentials"—that undermine external trust and should be cleaned up before public release.

## 2. Findings

| # | Severity | File:line | Class | Quote | Why | Fix |
|---|---|---|---|---|---|---|
| 1 | Blocker | `11-technology-register.md:151` | 1 | `- **Two corrections:** dashboards with Grafana is still preview, and the Copilot harness (preview, 2026-10-28) cannot use bring-your-own-model` | "Two corrections:" is explicit reviewer-rebuttal and drafting residue left in public design docs. Reads like raw meeting notes. | Replace with: `- Dashboards with Grafana remain preview; the Copilot harness does not support bring-your-own-model and cannot sit behind the hub. [Learn](https://learn.microsoft.com/azure/foundry/agents/concepts/limits-quotas-regions)` |
| 2 | Blocker | `11-technology-register.md:8, 140` | 1 | `The input was the 817 Microsoft AI updates of 2025-10-31 to 2026-10-31; items that touch the design were re-checked.` | "817 Microsoft AI updates" and "What the update list changed in the design" are internal scraping artifacts unknown to an external reader. | Line 8: `Evaluated against current Microsoft Azure AI releases as of 2026-11-01.` Line 140 heading: `## Recent platform updates and architectural implications`. |
| 3 | Major | `12-decisions.md:21` | 1 | `The Librarian returns a change set and the Study workflow opens the pull request, so no role in `study` holds a propose tool.` | Placed under `**Instead of.**` (rejected alternatives). It is not an alternative, but an argument defending why `study` has no propose tool. | Move sentence into `**Decision.**` of Decision 3, and delete from `**Instead of.**`. |
| 4 | Major | `12-decisions.md:54` | 2 | `Credentials (autopilot) are policies evaluated in code on facts the model cannot set, never for purchases.` | "Credentials" in cloud architecture denotes authentication secrets (keys, tokens), not policy-governed autonomous execution rights. | Replace with: `Autonomous execution grants (autopilot) are policies evaluated in code on facts the model cannot set, never for purchases.` |
| 5 | Major | `12-decisions.md:73` | 2 | `Only verified bank rows become gold, adjudicated by a person; sealed rotating test sets.` | Cold readers assume "bank rows" refers to financial bank transactions rather than the internal Cost-trap bank (`docs/research/cost-trap-bank.md`). | Replace with: `Only verified cost-trap benchmark cases become gold labels, adjudicated by a person ([evaluation](08-testing-and-evaluation.md)); sealed rotating test sets.` |
| 6 | Major | `13-roadmap.md:13-18, 29` | 4 | `| P10 | Tokens per case and the model per alias; does the cost model match the bill? | ... | Phase: 1 |` | P10 is assigned to Phase 1 in the proof points table and Decision 5, but Phase 1's exit criteria list P4–P7, omitting P10 entirely. | Add `P10 token consumption and cost-model calibration results;` to Phase 1 Exit criteria (`13-roadmap.md:14`). |
| 7 | Major | `13-roadmap.md:24` | 3 | `Retrieval quality and cost per query on the Atlas questions` | P5 merely names metrics to observe rather than defining an objective pass condition, violating the rule that pass criteria are pre-stated. | Replace with: `A retrieval option achieves target retrieval precision on the Atlas suite within the target cost budget per query.` |
| 8 | Major | `12-decisions.md:28, 30` | 4 | `## 6. The Atlas lives in Git and is served from AI Search; humans merge · Accepted` | Title marks decision Accepted, but line 30 states: "Retrieval options (Serverless, Foundry IQ) are Proposed, settled by P5." | Clarify line 30: `AI Search Basic is adopted as baseline; Serverless and Foundry IQ retrieval options are evaluated under proof point P5.` |
| 9 | Major | `11-technology-register.md:41` | 2 | `Onboard to the adopter's hub, or deploy from `hub/` at a pinned commit.` | "Citadel" is an internal project code name (upstream repo is `Azure-Samples/ai-hub-gateway-solution-accelerator`), and no `hub/` directory exists. | Replace with: `Onboard to the adopting organisation's AI Hub Gateway Solution Accelerator ("Citadel"), or deploy from the upstream repository at a pinned commit.` |
| 10 | Minor | `11-technology-register.md:31` | 1 | `Listed for Data Zone Standard in seven EU regions; Large 4: UNVERIFIED` | In the Mistral Large 3 row, `Large 4: UNVERIFIED` is internal scratchpad residue. | Delete `; Large 4: UNVERIFIED`. |
| 11 | Minor | `12-decisions.md:68` | 1 | `The honest gap: a meter nobody has used cannot be discovered this way` | "The honest gap" is conversational commentary rather than architectural specification. | Replace with: `Known boundary: a meter not yet observed in bills or documentation cannot be discovered this way...` |
| 12 | Minor | `12-decisions.md:73` | 1 | `Cost · security · reversibility. The point · quotas double as safety limits · high.` | Writing "The point" under Cost is conversational filler. | Replace `The point` with `Designed to scale to zero with minimal idle overhead`. |
| 13 | Minor | `11-technology-register.md:8` | 2 | `approval classes R1 to R3 in [security](06-security-and-governance.md)` | Risk tiers R1, R2, and R3 are used across Decisions and Roadmap milestones without brief definition for first-time readers. | Add inline gloss on first use: `(Risk tiers defined in [security](06-security-and-governance.md): R1 reversible low-cost, R2 configuration, R3 commitment)`. |
| 14 | Minor | `13-roadmap.md:5` | 1 | `which ten questions are settled by measurement rather than argument` | "settled by measurement rather than argument" is conversational posture from review debates. | Replace with: `which ten architectural questions are validated through empirical proof points`. |
| 15 | Minor | `13-roadmap.md:34` | 2 | `Measured tokens per case are far above the seed` | "the seed" is undefined shorthand for baseline token estimates. | Replace with: `Measured tokens per case significantly exceed initial cost-model estimates`. |

## 3. Sentences I would delete

1. `11-technology-register.md:8` — `The input was the 817 Microsoft AI updates of 2025-10-31 to 2026-10-31; items that touch the design were re-checked.`
2. `11-technology-register.md:31` — `Large 4: UNVERIFIED`
3. `11-technology-register.md:151` — `- **Two corrections:** dashboards with Grafana is still preview, and the Copilot harness (preview, 2026-10-28) cannot use bring-your-own-model, so it cannot sit behind the hub. [Learn](https://learn.microsoft.com/azure/foundry/agents/concepts/limits-quotas-regions)`
4. `12-decisions.md:21` — `The Librarian returns a change set and the Study workflow opens the pull request, so no role in `study` holds a propose tool.`
5. `12-decisions.md:73` — `The point · `
6. `13-roadmap.md:5` — `which ten questions are settled by measurement rather than argument`

## 4. Fact checks

1. **Foundry Hosted Agents (`11:19`):** Claimed GA with source-code ZIP deployment without customer ACR.
   - **URL:** `https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents` and `.../how-to/deploy-hosted-agent-code`
   - **Result:** **Verified.** Hosted agents are GA. Source-code ZIP deployment via `azd deploy` or REST API `create_version_from_code` (remote build) is supported without an ACR in the user subscription.
2. **Functions Flex Consumption (`11:88`):** Claimed GA and scales to zero.
   - **URL:** `https://learn.microsoft.com/azure/azure-functions/flex-consumption-plan`
   - **Result:** **Verified.** Flex Consumption plan hosting is GA, providing serverless event-driven scaling to zero with virtual network integration (rolling updates remain preview).
3. **Foundry Memory (`11:24`):** Claimed preview and lacks virtual network integration.
   - **URL:** `https://learn.microsoft.com/azure/foundry/agents/concepts/what-is-memory`
   - **Result:** **Verified.** Documented as "Memory (preview)" and explicitly notes: "Virtual network (VNet) integration isn't supported for memory stores."
4. **AI Gateway (`aigateways`) (`11:43`):** Claimed public preview in East US 2 and Sweden Central, lacking feature parity with APIM.
   - **URL:** `https://learn.microsoft.com/azure/ai-gateway/compare-api-management-service`
   - **Result:** **Verified.** In public preview in East US 2 and Sweden Central; documentation confirms full parity with API Management is not planned.
5. **AI Search Serverless (`11:65`):** Claimed public preview.
   - **URL:** `https://learn.microsoft.com/azure/search/search-sku-tier`
   - **Result:** **Verified.** Serverless pricing model for Azure AI Search is documented as `(preview)`.
6. **Durable Task Scheduler (`11:87`):** Claimed Dedicated SKU GA, Consumption SKU preview with 30-day retention and no HA.
   - **URL:** `https://learn.microsoft.com/azure/durable-task/scheduler/durable-task-scheduler-billing`
   - **Result:** **Verified.** Dedicated SKU is GA; Consumption SKU is `(preview)`, retains data up to 30 days, and lacks HA (HA requires 3 CUs on Dedicated).
7. **Foundry Guardrails (`11:46`):** Claimed agent guardrails in preview, model guardrails GA, omits guardrails if `rai_config` absent.
   - **URL:** `https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-guardrails`
   - **Result:** **Verified.** States "Agent guardrails are in preview" and confirms omitting `rai_config` deploys without content safety at the agent boundary.
8. **Microsoft Agent 365 / Entra Agent ID (`11:58`):** Claimed GA since 2026-05-01; requires M365 E7 or Agent 365 plus Entra ID P1.
   - **URL:** `https://learn.microsoft.com/entra/identity/conditional-access/agent-id`
   - **Result:** **Verified.** Prerequisites confirm licensing requires "Microsoft 365 E7" or "Microsoft Agent 365 license paired with at least Microsoft Entra P1 or Microsoft 365 E3."
9. **Foundry IQ (`11:63`):** Claimed minimal retrieval is GA, planning is preview.
   - **URL:** `https://learn.microsoft.com/azure/foundry/agents/concepts/what-is-foundry-iq` and `.../foundry-iq-faq`
   - **Result:** **Verified.** Documentation notes minimal retrieval without LLM is GA, while agentic query planning requires an LLM and is preview.
10. **ACS Email Retirement (`11:97`):** Claimed retiring 30 Sep 2028.
    - **URL:** `https://learn.microsoft.com/azure/communication-services/acs-retirement-and-breaking-changes-guide`
    - **Result:** **Verified.** Guide confirms ACS Email retires on September 30, 2028, recommending M365 High Volume Email or Exchange Online.

## 5. Questions left unanswered

1. **How is the Action plane secured between `approvals` and `runner` Function apps?**
   While Decision 2 specifies five Function apps and Decision 12 specifies per-family roles, the docs omit the concrete network/auth handshake between `approvals` and `runner`, and whether actions execute via ARM REST or Azure CLI.
2. **What objective signals trigger model alias escalation?**
   Decision 5 mandates escalating on objective signals, but omits specific operational criteria (e.g., schema validation error count, detector ambiguity score).
3. **What is the schema and lifecycle of a "Lesson"?**
   Decision 13 and Phase 2 introduce Lessons from owner replies, but leave undefined their internal schema, expiration policies, and how conflicting replies are reconciled.
4. **What minimum Azure permissions are required for Phase 1 pilot estates?**
   Phase 1 exit criteria require explained spend on a first estate with zero writes, but omit the explicit read-only RBAC roles needed to onboard an adopter.
5. **How does the cost lake handle multi-currency or multi-billing-account estates?**
   Decision 8 details FOCUS exports and DuckDB, but leaves unaddressed exchange rate conversions and CSP partner margin reconciliation across disparate scopes.
