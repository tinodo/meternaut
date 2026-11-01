# Round 2 · B — Platform facts on Microsoft Learn (model: claude-sonnet-5)

> Raw report, saved exactly as the reviewer returned it (everything below the rule). Reviewed on 2026-11-01: documents 02, 03, 05, 06, 07, 09 and 11 of the written design (commit `3543f3b`). Lens: the most load-bearing claims about Microsoft products, each checked against Learn. Line references like `11:46` mean line 46 of `11-technology-register.md`. The orchestrator's spot-checks of what this reviewer cited are in the [disposition](disposition.md).

---

# Round 2 Review — Platform Facts Lens

## Verdict
This document set treats Microsoft Learn as a primary source unusually carefully: of the 36 load-bearing platform claims I checked against Learn (spanning all required topics a–m), 35 were **CONFIRMED**, several to the exact wording. I found **one factual error** (a tier-support claim in the technology register) and a handful of narrow sub-claims I could not independently verify in the time available. No blocking issues were found — the design can proceed on its platform facts as written, with the one correction below applied.

## Top fixes
1. **Fix the APIM tier claim** (11:46): `llm-content-safety` is documented on the Consumption tier; only MCP servers are excluded from it. Don't conflate the two.
2. Add a direct citation anchoring the "eight private endpoints" count (02:138) — it is correct, but it is a synthesis across 3 separate Learn pages, not a single sourced fact, so it will go stale silently if any one underlying requirement changes.
3. Verify independently (not blocking, just unresourced in the design itself): the Decisions API's `gpt-6-luna`-only / East US 2 exclusion claim (11, GPT-6 Luna row).
4. Verify the exact tool list Foundry hosted-agent guardrails cover for tool-call/response screening (06, "Foundry guardrails are preview" paragraph) — I confirmed the general preview/MCP-gap framing but not the enumerated tool list.
5. No other changes needed on platform facts in these 7 files.

## Findings table

| # | Severity | File:line | Quote (≤25 words) | What is wrong | Proposed fix |
|---|---|---|---|---|---|
| 1 | Minor | 11-technology-register.md:46 | "MCP servers and `llm-content-safety` are documented for every tier except Consumption." | **WRONG.** Learn's `llm-content-safety` policy page lists Gateways as "classic, v2, **consumption**, self-hosted, workspace" — it runs on Consumption. Only MCP server management is excluded from Consumption ("Classic tiers: Developer, Basic, Standard, Premium; v2 tiers: Basic v2/Standard v2/Premium v2" — no Consumption). | Rewrite: "MCP servers are documented for every tier except Consumption; `llm-content-safety` is documented for every tier, including Consumption." (learn.microsoft.com/azure/api-management/llm-content-safety-policy, …/mcp-server-overview) |

No other item in the seven reviewed documents produced a confirmed WRONG, OUTDATED, or OVERCLAIMED verdict. The remainder of this report lists what I verified and what I could not, per the brief's instruction to spend words on what isn't confirmed — there is very little of that here.

### Claims I could not fully verify (not asserted as wrong — just not independently closed out)
- **06, "Foundry guardrails are preview"** — the claim that tool-call/response controls cover only "Azure AI Search, Azure Functions, OpenAPI, SharePoint, Fabric data agent, Bing, Browser Automation" and skip MCP. I confirmed the Toolbox/guardrails scope-and-limitations framing exists but did not pin the exact seven-tool enumeration to a single page.
- **11, GPT-6 Luna / Decisions API row** — "runs on `gpt-6-luna` only and excludes East US 2." Too narrow a product surface to confirm in the time available; no contrary evidence found either.
- **08:113** — "two Learn pages list different EU regions for cloud [red-teaming] runs." I confirmed one region list (East US 2, France Central, Sweden Central, Switzerland West, US North Central) but did not locate a second, conflicting page to corroborate the discrepancy claim.
- **05:139** — exact Graph permission name `TeamsAppInstallation.ReadWriteSelfForUser.All` for bot self-install — plausible and consistent with Teams proactive-messaging patterns, not independently re-derived from a fetched page.
- **11, Azure MCP Server row** — exact version/date "(3.0.0, 2026-10-12)" and "4.0 betas weekly" cadence — not independently checked; the broader claims (GA, Reader-only pattern, Container Apps-only remote hosting) were confirmed.
- **(i) "Quote-bound purchase" full mechanics** — I confirmed the role/permission facts precisely (custom roles cannot buy; must use built-in Owner/Reservation Purchaser; `Role Based Access Control Administrator` + a condition is the correct, real delegation primitive — this is genuine Azure ABAC, not a design invention) but did not separately re-verify the "calculate → stored quote id → purchase" API sequence end to end.

### An "accidentally right" / under-sourced fact worth flagging
**02:138, "Eight private endpoints"** is correct, but it is not a fact stated anywhere on Learn as "eight" — it's the design's own sum across independent, unrelated Learn pages (Foundry BYO-VNet private-endpoint-per-data-resource guidance, Flex Consumption's lack of an Azure Files dependency confirmed via "Flex Consumption | A blob deployment container…" vs. "Consumption, Elastic Premium… an Azure Files content share," and generic Storage/Search/Cosmos/Key Vault private-link docs). It happens to be internally consistent and correct today, but nothing ties the "8" to a maintained source, so a future change to any one input (e.g., Durable Functions on Flex Consumption adding a File dependency) would make the number silently wrong with no test or doc-link to catch it. Worth a footnote showing the per-resource math, not just the total.

## What I verified myself (CONFIRMED — primary source and the claim each confirms)

| # | Doc:line | Claim (short) | Learn URL |
|---|---|---|---|
| 1 | 05:123 | ARM what-if needs the same permissions as the deployment | .../azure-resource-manager/templates/deploy-what-if |
| 2 | 03:114 | Durable timers in Python limited to six days | .../durable-task/common/durable-task-timers |
| 3 | 09:34 | Always-ready instances default to 0; Learn recommends 1 for `durable` group | .../durable-functions-azure-storage-provider#flex-consumption-plan |
| 4 | 11 (Functions Flex) | Flex Consumption is GA | .../azure-functions/flex-consumption-plan |
| 5 | 03:25 | Hosted-agent idle timeout configurable 2–240 min | .../foundry/agents/concepts/hosted-agents |
| 6 | 02:63, 03:118 | Idle release at ≤240 min; session deleted after 30 idle days | same as #5 |
| 7 | 02:144, 09:34 | Sweden Central listed; North Europe absent from hosted-agent regions | .../hosted-agents#region-availability |
| 8 | 09 "Zip deployment", 07:43 | Zip (`code_configuration`), `bundled` deps, SHA-256 stored, no registry needed | .../foundry/agents/how-to/deploy-hosted-agent-code |
| 9 | 02:136 | BYO-VNet with platform-managed agent data is a real option | .../foundry/agents/concepts/networking-options |
| 10 | 02:138 | 8 private endpoints (derived; see note above) | same + Flex Consumption networking docs |
| 11 | 05:103 | GA fallback: expose REST API as MCP server in APIM | .../api-management/mcp-server-overview |
| 12 | 06 (Hub control) | `llm-token-limit` has `estimate-prompt-tokens` attribute | .../api-management/llm-token-limit-policy |
| 13 | 09 (playbook) | Suspending a subscription blocks calls; unpublishing a product does not | .../api-management/api-management-subscriptions |
| 14 | 05:135 | Adaptive Card routing: .NET/JS only, not Python | .../microsoft-365/agents-sdk/adaptive-cards |
| 15 | 05:137 | Bot Service: no fixed inbound IPs, no allow-list | .../azure/bot-service/security-faq |
| 16 | 05:137 | Bot Service expects an ack within 10–15 seconds | .../bot-builder-howto-long-operations-guidance |
| 17 | 05:54 | Management-group scope and pay-as-you-go cannot export FOCUS | .../cost-management-billing/costs/tutorial-improved-exports |
| 18 | 05:61 | 8–24h (EA/MCA) / 72h (PAYG); cumulative; closes ~72h; rerated to ~day 5 | .../costs/understand-cost-mgt-data |
| 19 | 05:78 | BilledCost = invoice basis; EffectiveCost = amortised discounts | .../dataset-schema/cost-usage-details-focus |
| 20 | 06:162 | PIM cannot make a service principal eligible | .../role-based-access-control/pim-integration |
| 21 | 06:114 | CA authentication context exists for step-up approval | .../entra/identity-platform/developer-guide-conditional-access-authentication-context |
| 22 | 06:158 | RBAC Administrator + condition (ABAC) can delegate one role/principal pair | .../role-based-access-control/delegate-role-assignments-overview |
| 23 | 06:74/146 | Phishing-resistant authentication strength is a real CA concept | .../entra/identity/authentication/concept-authentication-strengths |
| 24 | 06:157 | A custom role mimicking Reservation Purchaser cannot buy | .../reservations/prepare-buy-reservation |
| 25 | 05:18, 05:188 | Continuous backup copies changes within ~100 seconds | .../cosmos-db/continuous-backup-restore-introduction |
| 26 | 05:188 | Restore omits firewall/private-endpoint/data-plane-role settings | same as #25 |
| 27 | 05:37 | Cosmos zone redundancy is chosen only at account creation | .../reliability/reliability-cosmos-db-nosql |
| 28 | 09 (recovery) | Restore with TTL disabled avoids item expiry on arrival | same as #25 |
| 29 | 09:95 | Deployment Stacks cap `excludedPrincipals` at 5, silently | .../bicep/deployment-stacks#protect-managed-resources |
| 30 | 09:98 | Deny settings don't block RG deletion, resource moves, Graph, or have what-if | .../bicep/deployment-stacks-known-issues |
| 31 | 02, 11:70 | AI Search Basic (not Free) supports private endpoints | .../search/service-create-private-endpoint |
| 32 | 11:72 | Basic tier supports semantic ranking | .../search/search-sku-tier |
| 33 | 08:113 | AI Red Teaming Agent: supports Foundry prompt/hosted-container agents + Azure tool calls; not workflow agents/non-Foundry/non-Azure/function-tool calls; agentic categories cloud-only, single-turn, English-only | .../foundry/concepts/ai-red-teaming-agent |
| 34 | 05, 11 | Azure MCP Server remote hosting documented only via Container Apps | .../azure-mcp-server/how-to/deploy-remote-mcp-server-microsoft-foundry |
| 35 | 05:139 | Proactive Teams messaging needs the bot installed for the person | .../graph-api/proactive-bots-and-messages/graph-proactive-bots-and-messages |
