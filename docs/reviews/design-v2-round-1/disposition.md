# Design v2 · Round 1 — disposition

Three independent reviewers (three model families, three lenses) challenged the decisions D1–D22 of the first design specification on 2026-11-01, before any design document was written: [A · cost and simplicity](raw-a-cost-simplicity.md) (gemini-4-argon), [B · security and safety](raw-b-security-safety.md) (grok-4.7), [C · AI engineering and platform facts](raw-c-ai-platform.md) (gpt-6.1-sol). This page says, finding by finding, what was accepted, what was adjusted and what was rejected, and where the change landed. The specification itself is a working file; its decisions are carried by the [design](../../design/README.md), see [decisions](../../design/12-decisions.md).

## What changed

| # | Finding (reviewer) | Disposition | Landed in |
|---|---|---|---|
| 1 | Approval is a row plus a card; replay, two hats and time-of-check gaps unspecified; "separation of duties is enough" is wrong (B, reverse D11) | **Accepted.** Approval is a bound, displayed, single-use, fail-closed authorization; the card carries an opaque id; two distinct directory roles for purchases | Approval decision (06, 05) |
| 2 | A credential can be matched on tags or logs the model influences (B) | **Accepted.** Credentials are policy records evaluated in code against facts the model cannot set; each run still writes a single-use authorization; never for purchases | 06, 03 |
| 3 | One estate key for seven agents; headers are not identity (B) | **Accepted, adjusted.** Contract per hosted agent with the agent's Entra token; the key stays but is not identity | Hub decision (02, 06) |
| 4 | Ten hosted agents bill idle tails and multiply deployments (A); hosting is not required for tool use (C) | **Adjusted.** Ten roles stay; five hosted agents, one per trust boundary; hosted or prompt chosen by capability | Agents decision (03) |
| 5 | Filters do not cover the paths that matter; MCP responses are not screened (B); Content Safety on every prompt is costly (A) | **Accepted, adjusted.** Screen where untrusted text enters; structured tool output plus screened excerpts; hub screening only on the two contracts that take raw external text | 06, 05 |
| 6 | Standing purchase identity; PIM cannot help (B) | **Accepted, corrected.** Time-boxed assignment created and removed by the approval service; alarms disable the identity. "Deny assignment" **rejected**: no supported way to add one for this | 06 |
| 7 | Denial of wallet beyond the workflow (B, A) | **Accepted.** Hub quotas per contract, in-agent bounds, a run-rate trip; budgets only alert | 07, 10 |
| 8 | Tool rug pull; schema hash is not behaviour (B) | **Accepted.** Pin the digest, reject `tools/list` drift, structured outputs. B's "Azure MCP has no read-only mode" is **wrong** (see spot-checks) | 05, 06 |
| 9 | Untrusted text reaches the Engineer through the case notebook (B, C) | **Accepted.** Engineer receives structured fields only; authorized case-context record with provenance; the Skeptic re-retrieves facts itself | 03, 06 |
| 10 | Activities run at least once; unknown outcomes; purchases must never be retried blindly (C, A) | **Accepted.** Idempotency by plan id, resolve unknown outcomes by lookup, single-flight per resource, parked poison cases | 03, 07 |
| 11 | Evidence is not causality; learning must be shown by frozen-versus-updated comparisons (C) | **Accepted.** Scoped evidence, registered predictions, load-normalised trials, honest limits | 04, 08 |
| 12 | Evaluation can reward familiarity; 66 of the 145 bank rows are partial or unverified (C) | **Accepted.** Only verified rows are gold, human-adjudicated; sealed rotating tests; splits by service and time | 08 |
| 13 | Evaluation could cost more than production (A) | **Accepted.** Three tiers: zero-LLM checks on every change, LLM suites on change on Flex, sampled production scoring | 08, 10 |
| 14 | Cost truth: exports are cumulative and rerated; billed versus effective cost (C) | **Accepted.** Manifest-based replacement ingestion, reconciliation | 05, 10 |
| 15 | Topology over-constrained; BYO VNet can use platform-managed data (C) | **Accepted and verified.** Operate uses BYO VNet with platform-managed Foundry data; bring-your-own data only on request; Sweden Central is a default, not a requirement | 02, 10 |
| 16 | Container Apps need a registry (Premium behind a private link) (A) | **Accepted.** One compute family: Azure Functions Flex, zip deployment; no registry | 02, 09 |
| 17 | Durable Task Scheduler Consumption: no high availability, 30-day retention, preview (A) | **Accepted.** Azure Storage provider is the default | 02 |
| 18 | Hub usage pipeline is a €321 floor (A) | **Adjusted.** Not this solution's cost; a fork can replace it with log queries; stated in the cost document | 10, 09 |
| 19 | Evaluate profile must still use a hub and must not reach production (A, B) | **Accepted.** Dev contracts; identities with no production roles; isolation tested in CI | 02, 08 |
| 20 | Missing: single-flight, ARM throttling, Teams acknowledgement, self kill switch (A); strategy workflow, recovery, detector shadow rollout, traffic inventory (C); RBAC matrix, break-glass, incident playbooks, SBOM (B) | **Accepted.** Each has a home | 02, 03, 05, 06, 07, 09 |
| 21 | Stop does not cancel runs in flight; Routines are GA; card routing is .NET or JavaScript; Deployment Stack deny settings can block the runner (C) | **Accepted.** | 07, 03, 05, 09 |
| 22 | Default `reason` model: a cheaper large tier (A) | **Accepted as a candidate**, decided by evaluation | 11 |
| 23 | Drop the Lesson Book page (A) | **Deferred.** Lessons are records first; the page is small and comes with phase 2 | 03, 13 |
| 24 | Share Foundry's Cosmos and Storage with ours (A) | **Rejected** for approvals and audit data (separation); moot once Foundry data is platform-managed | 02 |

## Orchestrator spot-checks (2026-11-01)

Facts a reviewer cited were re-checked against the primary source before use.

| Claim | Result |
|---|---|
| A: Durable Task Scheduler Consumption has no high availability and keeps data 30 days | Confirmed on Learn; one Learn page labels Consumption "(preview)" |
| A: GPT-6.1 Terra costs about half of Sol | Confirmed in the price snapshot: input 1.06 against 2.11 (EUR per 1M tokens, Data Zone), output 5.28 against 10.56 |
| A: hosted agents deploy from a zip without a registry | Confirmed ("Deploy a hosted agent from source code") |
| A: private networking forces your own Cosmos, Storage and Search | **Incomplete.** True of the standard setup; Learn also lists BYO VNet with platform-managed data resources (template 11) |
| B: Azure MCP Server has no read-only mode | **Wrong.** The start options list "Read only" (default false) |
| B: PIM cannot make service principals eligible | Confirmed on Learn; time-bound assignments for them are possible, so create-and-remove works |
| C: card routing is not available in the Python Agents SDK | Confirmed on Learn |
| C: 65 bank rows are partial or unverified | **66** (33 partial, 33 unverified of 145); the conclusion stands |
| C: Sweden Central is not uniquely required | Accepted as a default; the earlier "only region" finding counted managed VNet and Serverless Search, which this design does not need |
| B, C: tool-response controls do not cover MCP; Routines are GA; stopping does not end runs in flight | Reviewer-verified; consistent with the evidence gathered on 2026-10-31; not re-fetched |

Reviewer C ran 27 minutes and was asked to finalise; it marked what it had not reached UNVERIFIED. No reviewer estimate of cost is used: the numbers in the [cost document](../../design/10-cost-and-finops.md) come from the cost model.
