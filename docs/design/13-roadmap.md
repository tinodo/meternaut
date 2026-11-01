# Roadmap

**What this document answers.** In what order the system is built; what must be true before each phase ends; which ten questions are settled by measurement rather than argument; what could change the plan.

## 1. Phases

Each phase ends with something an organisation can use and something that was measured. A phase does not start because the previous one is "done" on paper but because its exit criteria were met.

| Phase | What exists at the end | Exit criteria |
|---|---|---|
| **0 Foundations** | Repository, Evaluate profile deployed from code, hub onboarding (dev contracts, published tools), synthetic-estate generator, zero-LLM checks in CI, evaluation harness skeleton, cost model | P1, P2 and P9 pass; a fresh deployment of dev from scratch works; isolation test (dev cannot reach prod) passes |
| **1 Read and explain** | Cost lake, Estate refresh, Atlas v0, Study and Watch workflows, seed Detectors, Cases that investigate, challenge and quantify but only *report*; Monday digest to the FinOps lead; report card v0 | P4, P5 and P6 results; on the sealed set the system beats the retrieval-only and Advisor-only baselines and **updated memory beats frozen memory**; explained spend measured on a first estate; zero writes to Azure; injection suite passes on all read paths (P7) |
| **2 Recommend and ask** | Diplomat, Teams cards and email, the web page, Respond workflow, directory resolution, Lessons; Operate profile in production; prod contracts | Decision burden measured; calibration record running; reply-path injection suite passes; recipients are always resolved from the directory; the first estate runs in the Operate profile |
| **3 Act** | Action plane: catalogue of the first Actions across several families, planner, approval service with bound records, runner with per-family roles, verifier, kill switches, audit log; R1 and R2 in non-production | P3 and P8 settled; fail-closed, replay, time-of-check and unknown-outcome tests pass; game days (runner crash, approval outage, kill switch) passed; first savings verified against a counterfactual |
| **4 Earn autonomy and purchases** | Credentials for R1 and low R2 in named domains; R3 flow with two approvers and a time-boxed purchase role; Strategy workflow (commitment coverage, renewals); shared cases; more Actions; optional FinOps-hub adapter | Report card shows calibrated predictions in each credential's domain; red-team suite passes before each credential; purchase dry run with the reservation *calculate* API; incident drills passed |
| **5 Open up** | Contribution flow for the Atlas and Action catalogue with the same gates; anonymised outcome statistics; optional voice, avatar and meeting modules; second-region recovery | External pull requests pass the same checks; nothing from an estate leaves it |

## 2. Ten proof points

Questions whose honest answer is a measurement. Each has a fallback so a failed test changes a choice, not the project.

| # | Question | Passes when | Phase | Fallback |
|---|---|---|---|---|
| P1 | Does the hub path work end to end (hosted agent → hub → model and tool, per-agent JWT and quotas, Responses API)? What can a hosted agent do with no grants? | Calls succeed; a direct model call fails; an agent without a role cannot read the estate | 0 | Chat Completions route; prompt agent for simple roles |
| P2 | Do workflows call hosted agents reliably (auth, timeouts, session reuse, idle tails)? Storage backend or Durable Task Scheduler? | Calls complete within the deadline; idle tail within budget; a backend chosen on measured price and recovery | 0 | Own adapter around the GA Agent Framework core; the other backend |
| P3 | Is approval integrity real (canonical plan, opaque id, Teams sign-in and card timeout, web page with Conditional Access, single-use consumption, two-role dry run)? | Every tamper, replay and mismatch test fails closed; cards acknowledge in time | 3 | One always-ready instance; cards only open the web page |
| P4 | Does cost data hold at Team and Enterprise volume (DuckDB in a 4 GB instance; Cosmos DB serverless limits)? | Queries and refresh finish in budget | 1 | Azure Data Explorer; provisioned Cosmos DB throughput |
| P5 | Which retrieval for the Atlas: Basic, Serverless (preview) or Foundry IQ? Semantic ranker on or off? | Retrieval quality and cost per query on the Atlas questions | 1 | Basic with direct hybrid retrieval |
| P6 | How good are Detective and Skeptic on verified bank rows against the baselines? | Rediscovery above baselines on the sealed set, decoys stay quiet | 1 | Narrower scope; more Detectors; better prompts |
| P7 | Can any untrusted-text path reach a propose tool or a write? | Red team finds none; screening catches seeded attacks | 1 and 3 | Split the role into its own hosted agent |
| P8 | Per-family runner roles or time-boxed assignment for purchases: propagation, revocation, ABAC limits? | Assignment appears and disappears within a measured window | 3 and 4 | Standing role with alerts on every use, documented as weaker |
| P9 | Does tool pinning at the hub catch a changed tool (name, description, schema, server digest)? | A changed tool is rejected | 0 | Block `tools/list` changes in the contract |
| P10 | Tokens per case and the model per alias; does the cost model match the bill? | Measured cost within a stated margin of the model | 1 | Cheaper large tier; smaller prompts; more Detectors |

## 3. What could change the plan

| Change | Effect |
|---|---|
| Preview features reach general availability (native MCP on Functions, Foundry guardrails for agents, Serverless AI Search, the Agent Framework hosting and durable packages) | Switch on behind the existing flag; remove the fallback after a stable period |
| The hub accelerator changes its contracts or defaults | Contracts are code: re-test with P1 and P9 before upgrading |
| Measured tokens per case are far above the seed | Re-run the cost model; push more work into Detectors and Batch |
| A cheaper model passes the evaluation for an alias | Change the alias mapping; nothing else changes |
| Fabric or Databricks becomes the better home for cost data at very large scale | Add a data adapter; the tools stay the same |
| An adopter needs agent data in its own resources | Turn on Foundry bring-your-own data: two more endpoints and two small stores |

See also [the decisions](12-decisions.md), [the cost](10-cost-and-finops.md) and [the technology register](11-technology-register.md).
