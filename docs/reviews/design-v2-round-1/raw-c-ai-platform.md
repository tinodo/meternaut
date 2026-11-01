# Round 1 · C — AI engineering and platform facts (model: gpt-6.1-sol)

> Raw report, saved exactly as the reviewer returned it (everything below the rule). Reviewed on 2026-11-01: the decisions D1–D22 of the first design specification. Lens: platform claims checked on Microsoft Learn, agent and learning design, evaluation design. The reviewer ran 27 minutes and was asked to finalise; items it did not reach are marked UNVERIFIED in its report. The orchestrator's spot-checks of what this reviewer cited are in the [disposition](disposition.md).

---

Agent is idle (waiting for messages). agent_id: 8786a312-7fcc-4b3e-abe1-1c55590fb4cd, agent_type: rubber-duck, status: idle, description: Round 1 review: AI engineering and platform facts, elapsed: 1795s, total_turns: 1, model: gpt-6.1-sol

[Turn 0]
## (a) Platform verification

Reviewed the full [spec](<session>/files/design-v2-spec.md), rule 11 and the north star. Checks were made **2026-11-01**. No deployment was tested. Microsoft announcements corroborate dates that Learn omits.

| Claim | Verdict / correction | URL |
|---|---|---|
| Hosted agents GA, 9 July 2026 | **CONFIRMED**: Learn confirms GA; Microsoft’s announcement confirms 9 July. | [Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents), [date](https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-july-august-2026/) |
| Idle timeout/deletion | **CONFIRMED**: 2–240 minutes, default 15; compute deprovisioned, state preserved; session deleted after 30 inactive days. Independent state-store expiry can be disabled. | [Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents) |
| Hosted billing | **CONFIRMED**: active-session CPU/memory, including the idle tail; model/tool charges additional. | [Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents) |
| Hosted regions | **CONFIRMED**: includes France Central, Germany West Central, Poland Central, Sweden Central and West Europe; North Europe absent. | [Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents) |
| Agent Framework 1.0 GA | **CONFIRMED**: Python 1.0 released 2 April; production-ready announcement published 3 April. | [Learn](https://learn.microsoft.com/en-us/agent-framework/support/upgrade/python-2026-significant-changes), [announcement](https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/) |
| Hosting/durable packages prerelease | **CONFIRMED**: Python Foundry hosting, `agent-framework-azurefunctions` and `agent-framework-durabletask` remain prerelease. Service GA does not change that. | [Hosting](https://learn.microsoft.com/en-us/agent-framework/hosting/foundry-hosted-agent), [durable](https://learn.microsoft.com/en-us/agent-framework/hosting/durable-extension) |
| Foundry workflows retire 1 December | **CONFIRMED**: applies to Foundry’s UI workflows, not Agent Framework workflows. | [Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/workflow) |
| Python Durable Functions on Flex | **CONFIRMED**: supported; Azure Storage and DTS are supported backends. Waiting avoids execution-time billing, not necessarily storage/transaction costs. | [Flex](https://learn.microsoft.com/en-us/azure/azure-functions/flex-consumption-plan), [billing](https://learn.microsoft.com/en-us/azure/durable-task/durable-functions/durable-functions-billing) |
| DTS Consumption | **CONFIRMED** billing: actions, no base fee; 500 actions/sec, ≤30-day retention, no HA. **UNVERIFIED GA**: Learn contains conflicting readiness indications, including an explicit preview label. | [Current billing](https://learn.microsoft.com/en-us/azure/durable-task/scheduler/durable-task-scheduler-billing), [preview label](https://learn.microsoft.com/en-us/azure/durable-task/durable-functions/durable-functions-billing) |
| BYOM gateway limitation | **CONFIRMED**: prompt-agent connection uses Chat Completions. **WRONG** inference that tool users must be hosted: MCP, Functions and OpenAPI are supported. Hosted code chooses its own model client/protocol. | [Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/ai-gateway) |
| Foundry IQ GA scope | **CONFIRMED** partial GA: `2026-04-01`, minimal/extractive retrieval; index, Blob, indexed OneLake and Web sources. Planning, synthesis, multi-turn and portals remain preview. | [Learn](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-migrate) |
| Search Basic / Serverless Developer | **CONFIRMED**: Basic has fixed SU billing. Serverless Developer is preview, CU/storage billed, no SLA, aliases or private indexers/shared private links. | [Learn](https://learn.microsoft.com/en-us/azure/search/search-sku-tier) |
| FOCUS exports and latency | **CONFIRMED**: actual/amortized costs combined; Parquet supported; daily exports are cumulative month-to-date. EA/MCA typically 8–24h; PAYG up to 72h; costs can be rerated. | [Exports](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports), [latency](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data) |
| Azure MCP 3.0 / Advisor | **CONFIRMED**: stable release, read-only mode, Advisor metadata/list/summary tools. “Apply” returns IaC guidance, not live remediation. | [Release](https://devblogs.microsoft.com/azure-sdk/azure-mcp-server-3-0-stable-release/), [read-only](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/tools/), [Advisor](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/tools/azure-advisor) |
| Agents SDK / private Teams publishing | **CONFIRMED**: private Foundry publishing requires REST and an authorized, source-IP-filtered public Activity route. Adaptive Card routing is .NET/JavaScript, not Python. | [Publishing](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot), [cards](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/adaptive-cards) |
| Entra Agent ID | **CONFIRMED** automatic per-agent identity, without downstream RBAC grants. However, hosted documentation describes default project inference/state access: “no permissions” does not prove no bypass. | [Identity](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-identity), [defaults](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents) |
| D3/D16 readiness and stopping | **WRONG** labels/implications: Routines are GA; Operate panes/private tracing remain preview. Hosted agents support start/stop; block/unblock concerns custom agents. Stop does **not** terminate existing runs. | [Readiness](https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability), [lifecycle](https://learn.microsoft.com/en-us/azure/foundry/control-plane/how-to-manage-agents) |
| Sweden Central uniquely required | **WRONG** as a requirement: it counts unused managed VNet and optional Serverless Search. Exact accelerator-wide intersection **UNVERIFIED**. Learn also flags constrained new Search capacity there. | [Networking](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/networking-options), [Search regions](https://learn.microsoft.com/en-us/azure/search/search-region-support) |

## (b) D1–D22

“Change” means **Agree-with-change**.

| Decision | Verdict | One-line reason |
|---|---|---|
| D1 | Change | Correct boundary; host-owned metadata and failure states need strengthening. |
| D2 | Change | Good engine; eviction is not workflow expiry; backend choice needs SLOs. |
| D3 | Disagree | Tool use does not require hosting; the required integration is prerelease. |
| D4 | Change | Prove bypass denial and identity attribution; include standalone hub cost. |
| D5 | Change | Pin resolved version/protocol/residency; self-confidence alone is unsafe routing. |
| D6 | Change | Git/Search is defensible; evidence scope and semantic rechecks need contracts. |
| D7 | Change | Specify partitioning, retention, restore and private-evidence separation. |
| D8 | Change | Define corrected-snapshot ingestion and financial reconciliation. |
| D9 | Change | Enforce scopes; Azure Reader does not cover Graph/data-plane permissions. |
| D10 | Change | Add execution deduplication and unknown-outcome recovery. |
| D11 | Agree | Separation of duties is the correct foundation. |
| D12 | Change | Risk classes are not Azure permissions; derive action-specific roles. |
| D13 | Change | Choose .NET/JavaScript card routing and explicitly secure the public bridge. |
| D14 | Change | Distinguish absent RBAC grants from default platform access. |
| D15 | Change | Networking/store choices are separable; profile transitions require new resources. |
| D16 | Change | Use GA telemetry fallback; distinguish lifecycle controls from cancellation. |
| D17 | Change | Independent gold labels and learning comparisons are missing. |
| D18 | Agree | Drift categories cover the relevant surfaces. |
| D19 | Change | Test deny settings against approved actions and rollback. |
| D20 | Change | Compute can scale to zero; Search/APIM/private endpoints retain floors. |
| D21 | Agree | Explicit licence and OSS accounting is appropriate. |
| D22 | Agree | Scope respects the fixed requirements. |

Counts match: **10 logical roles, six workflows, fourteen mechanisms, 145 trap rows**. These are not capacity evidence.

## (c) Top seven problems, ranked

1. **Blocking—execution safety.** [Activities execute at least once](https://learn.microsoft.com/en-us/azure/durable-task/common/programming-model-overview). D1’s three statuses and §5.3’s “bounded rounds” do not specify partial/unknown outcomes, deadlines or deduplication. Add host-stamped results, task/action keys, atomic approval consumption, durable delivery records, cancellation and poison handling. Bound retries, tool calls, concurrency and total spend. Never blindly retry purchases. **Confidence: high.**

2. **Blocking—GA fallback.** D3 combines a GA service with a prerelease hosting integration and falsely excludes tool-using prompt agents. Classify roles by actual capabilities, pin compatible package cohorts, and demonstrate a framework-agnostic hosted protocol fallback using stable Agent Framework core. **Confidence: high on facts; medium on implementation effort.**

3. **Blocking before autonomy—context trust.** §5.2 marks four roles “no” for untrusted text despite consuming derived evidence. JSON validation does not remove injection or establish truth. Define authorized case context, Atlas/Estate versions, timestamps, completeness and token limits; propagate provenance. Give Skeptic independently retrieved facts, not only Detective’s narrative. **Confidence: high.**

4. **Blocking for the learning claim—evidence is not causality.** §5.7’s “outcome-confirmed” can reflect traffic changes or rerating. Prices do not verify billing mechanics. Use scoped evidence dimensions, refutations, registered predictions and load-normalized trials. Link each knowledge change to improved future decisions under frozen-model comparisons. Bill residuals, shadow predictions, replays and approved existing-resource trials replace experiments—but cannot discover unused meters or establish unseen performance frontiers. **Confidence: high.**

5. **Non-Blocking—evaluation can reward familiarity.** The [bank](<repo>/docs/research/exam-bank-cost-traps.md) has **65 explicitly Partial/Unverified rows**. D17’s different-family judge is useful, not independent truth. Human-adjudicate gold labels; split by service/time, not random rows; rotate sealed tests; score failures and R3 cases beyond uniform sampling. Define precisely what confidence predicts. **Confidence: high.**

6. **Blocking for financial claims—cost truth is underspecified.** D8’s exports are cumulative and mutable; D16’s hub logs cannot alone establish fully loaded cost. Define manifests/replacement semantics, BilledCost versus EffectiveCost, commitment coverage, currencies and invoice reconciliation. Include rejected leads, Study, evaluation, hosting idle tails and standalone platform floors. Owner-case counts do not size total work. **Confidence: high.**

7. **Non-Blocking—topology is overconstrained.** D15 chooses BYO VNet but cites managed VNet to mandate Sweden. [Private BYO VNet can use platform-managed stores](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/networking-options). Separate mandatory capabilities from optional templates; validate capacity and price both store variants. Do not treat Evaluate→Operate as an in-place parameter flip. **Confidence: high.**

## (d) Missing principal-engineer expectations

- Monthly strategy/commitment workflow.
- Version-safe recovery of suspended cases; restore tests and explicit RPO/RTO.
- Detector shadow rollout, expiry and retirement.
- Expert-written-detector baseline plus frozen-versus-updated-memory comparisons.
- Complete Citadel traffic inventory, including agent invocation, embeddings, IQ and evaluators.
- Negative-path authorization/bypass tests and redacted production-evaluation inputs.

Absolute euro estimates and end-to-end Citadel enforcement remain **UNVERIFIED**.

## (e) One decision to reverse

**D3’s mandatory one-hosted-agent-per-role mapping.** Retain ten logical specialists, but select prompt versus hosted execution from demonstrated requirements. Reserve hosted code for genuinely custom behaviour—not merely tool use—and require a proven fallback for its prerelease integration.
