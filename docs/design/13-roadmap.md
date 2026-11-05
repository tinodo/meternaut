# Roadmap

**What this document answers.** In what order the system is built; what must be true before each phase ends; which ten questions are answered by measurement; what could change the plan.

## 1. Phases

A phase starts when the previous phase's exit criteria are met. A hosted agent, its hub contract and its tools are deployed in the phase that first needs them. "Phase 1" elsewhere means 1a and 1b together. Phase 1b may overlap phase 2; phase 3 starts only after 1b's exit, because P6 tests whether the system learns at all.

| Phase | What exists at the end | Exit criteria |
|---|---|---|
| **0 Foundations** | Repository, Evaluate profile deployed from code, hub onboarding (dev contracts, published tools), synthetic-estate generator, zero-LLM checks in CI, evaluation harness skeleton, cost model, one minimal hosted agent and workflow, the mail path, the thin path from a synthetic lead to a test e-mail, a week-0 check that the pilot's bill supports analysis, and a small demonstration that new evidence improves answers | P1, P2 and P9 pass; a fresh deployment of dev from scratch works; isolation test (dev cannot reach prod) passes; a first kill-switch drill has run in dev; the feasibility and learning reviews of the build plan have decided to go on |
| **1a First value on one estate** | The Operate profile with read roles only, and the prod contracts; the cost lake and capability profile of the first estate's scopes; Estate refresh; Watch workflow; Atlas v0; seed Detectors; Cases that investigate, challenge and quantify but only *report*; the Monday digest, written by the Diplomat and e-mailed to the FinOps lead | P4 and P7 (read paths) pass; explained spend measured on the estate; zero writes to the estate; the FinOps lead confirms a pre-set number of findings as true and worth acting on (each distinct, credibly priced on a named basis, adding discovery or follow-through to Azure's own advice, and agreed by a second reader); cost per case and per confirmed finding read from hub logs, dead ends included, with people's hours beside it |
| **1b Show that it learns** | Study workflow on its clock; Atlas growth; report card v0; the baselines; the sealed and later-in-time sets | P5, P6 and P10 results; on the sealed set the system beats the retrieval-only and Advisor-only baselines and **updated memory beats frozen memory** |
| **2 Recommend and ask** | Teams cards, e-mail and the web page for every owner, Respond workflow, directory resolution, Lessons taught by owners; the Auditor settles changes that owners make themselves | Decision burden measured; calibration record running; reply-path injection suite passes; recipients are always resolved from the directory; the first owner-made saving verified in the bill; the client matrix passes before go-live (every card type on each supported Teams client); the accessibility audit is scheduled yearly |
| **3 Act** | Action plane: catalogue of the first Actions across several families, planner, approval service with bound records, runner with per-family roles, verifier, kill switches, audit log; R1 and R2 in non-production | P3 and P8 settled; fail-closed, replay, time-of-check and unknown-outcome tests pass; game days (runner crash, approval outage, kill switch) passed; first saving from a system-run Action verified against a counterfactual |
| **4 Earn autonomy and purchases** | Credentials for R1 and low R2 in named domains; R3 flow with two approvers and a time-boxed purchase role, or a purchase request to the billing owner or the partner where the agreement requires it; Strategy workflow (commitment coverage, renewals; it needs the capability profile's *commitments visible* flag); shared cases; more Actions; optional FinOps-hub adapter | Report card shows calibrated predictions in each credential's domain; red-team suite passes before each credential; purchase dry run with the reservation *calculate* API; incident drills passed |
| **5 Open up** | Contribution flow for the Atlas and Action catalogue with the same gates; anonymised outcome statistics; optional voice, avatar and meeting modules; second-region recovery | External pull requests pass the same checks; nothing leaves an estate except a privacy-reviewed scope and aggregate that its owner has agreed to share |

**Superseded in part on 2026-11-05:** the runner's per-family roles (phase 3), Credentials and the purchase role (phase 4) and P8. A change runs as the approver; see [decision 24](12-decisions.md#24-a-change-runs-as-the-approver-meternaut-holds-no-right-to-change-azure--accepted) and [proposal 05](../proposals/05-run-as-the-approver.md).

### What the experience needs, by phase

| Phase | What the [experience design](../experience/README.md) needs from the system |
|---|---|
| **1a** | The send step, the AI marks on e-mail, and the Monday digest's template in Git with CI checks; the notification policy with fixed settings for one allow-listed reader, the FinOps lead (the platform owner joins in phase 2), who is introduced by an agreed message and not by the owner first-contact flow |
| **1b** | The report events and Workbooks as code (report card v0); Atlas proposals from a fork |
| **2** | Teams delivery and the verb contract; cards only to directory members; the web pages and their read APIs; preferences and first contact; the notification policy for everyone and coverage routing; the rules for conversation buttons and a Lesson's scope; feedback capture; the saving rule |
| **3** | The approval rules that belong to P3: one decision per approver on one plan, two different people for R3, the daily cap and alarm, the rollback grant; "I did not approve this"; approver readiness for R2 (the test sign-in with an authentication context); the kill switch page and its runbook fallback |
| **4** | Credentials: their page and notices, "Pause changes here"; approver readiness for R3 (the phishing-resistant sign-in); the commitment's pace; the monthly letter and its CSV; the rules for e-mail requests to a partner or a billing owner |
| **5** | The voice and meeting modules and developer cost comments |

## 2. Ten proof points

Each proof point has a fallback so a failed test changes a choice, not the project; P6 is the exception. The numbers behind each pass condition (a budget, a margin, a time window) are written down before the measurement, never after.

| # | Question | Passes when | Phase | Fallback |
|---|---|---|---|---|
| P1 | Does the hub path work end to end (hosted agent → hub → model and tool, per-agent JWT and quotas, Responses API)? What can a hosted agent do with no grants? | Calls succeed; a direct model call fails; an agent without a role cannot read the estate | 0 | Chat Completions route; prompt agent for simple roles |
| P2 | Do workflows call hosted agents reliably (auth, timeouts, session reuse, idle tails)? Storage backend or Durable Task Scheduler? | Calls complete within the deadline; idle tail within budget; a backend chosen on measured price and recovery | 0 | Own adapter around the GA Agent Framework core; the other backend |
| P3 | Is approval integrity real (canonical plan, opaque id, the tapper's own token carried by a Teams card action, what a token fetched without a tap can approve, card timeout, web page with Conditional Access, single-use consumption, two-role dry run)? | Every tamper, replay and mismatch test fails closed; cards acknowledge in time; a token fetched without a tap approves no more than the R1 cap allows | 3 | One always-ready instance; cards only open the web page |
| P4 | Does cost data hold at Team and Enterprise volume (DuckDB in a 4 GB instance; Cosmos DB serverless limits)? Does the capability probe classify each agreement and level of access the way the portal shows it ([agreements and access](14-agreements-and-access.md))? | Queries and refresh finish in budget; the probes agree with the portal on every agreement type and level of access the pilot estates cover | 1a | Azure Data Explorer; provisioned Cosmos DB throughput; the estate owner states agreement and access by hand |
| P5 | Which retrieval for the Atlas: Basic, Serverless (preview), an embedded index in the `tools` app, or Foundry IQ? Semantic ranker on or off? | The chosen option meets the retrieval-quality target on the Atlas questions within the per-query budget (both numbers fixed beforehand) | 1b | Basic with direct hybrid retrieval |
| P6 | How good are Detective and Skeptic against the baselines on source-verified bank rows, and on a launch after the memory snapshot? | Rediscovery above baselines on the sealed set, decoys stay quiet; for a launch after the snapshot, a documented-only profile within a day of the launch, its meters joined to the bill with the unmatched share reported, and a first-invoice prediction, recorded with the snapshot's hash before the invoice, inside the stated error (a replayed launch is reported as a replay) | 1b | Narrower scope; better prompts. If updated memory still does not beat frozen memory, the learning claim is withdrawn and the goals reopen |
| P7 | Can any untrusted-text path reach a propose tool or a write? | Red team finds none; screening catches seeded attacks | 1a and 3 | Split the role into its own hosted agent |
| P8 | Per-family runner roles or time-boxed assignment for purchases: propagation, revocation, attribute-based access control limits? Does the approval record bind the purchase scope? | Assignment appears and disappears within a measured window; a purchase with any other scope than the approved one is refused | 3 and 4 | Standing role with alerts on every use, documented as weaker |
| P9 | Does tool pinning at the hub catch a changed tool (name, description, schema, server digest)? Is an optional Azure MCP Server worth its host? | A changed tool is rejected; the Azure MCP Server is adopted only if it earns its host over the typed `estate-read` | 0 | Block `tools/list` changes in the contract; typed tools only |
| P10 | Tokens and cost per investigation, per case that reaches an owner and per finding an owner confirms, dead ends included; the model per alias; does the cost model match the bill? | Measured cost within a stated margin of the model | 1a and 1b | Cheaper large tier; smaller prompts; more Detectors |

## 3. What could change the plan

| Change | Effect |
|---|---|
| Preview features reach general availability ([the register](11-technology-register.md) lists them) | Switch on behind the existing flag; remove the fallback after a stable period |
| The hub accelerator changes its contracts or defaults | Contracts are code: re-test with P1 and P9 before upgrading |
| Measured tokens per case are far above the cost model's starting volumes | Re-run the cost model; push more work into Detectors and Batch |
| A cheaper model passes the evaluation for an alias | Change the alias mapping; nothing else changes |
| A very large estate outgrows one process scanning the lake | Add a data adapter (a FinOps hub, Azure Data Explorer); the tools stay the same |
| An adopter needs agent data in its own resources | Turn on Foundry bring-your-own data: two more endpoints and two small stores |
