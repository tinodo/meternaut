# Build plan (phase 0 and phase 1a): specification for review

Repository: `<repo>` (private; AGENTS.md rule 1). This is a PLAN only: nothing is built, no resource is deployed, no code is written. The plan says what is built first, in what order, what is shown at each step, what must be checked before it is relied on, what it costs to run and to build, and what the adopting organisation must provide.

## Audience and rules

- A platform team and a FinOps lead at an adopting organisation who will build the system from `docs\design\` (technical design) and `docs\experience\` (what people see), and a contributor who wants to know where to start. A stranger must be able to read it cold.
- AGENTS.md binds the plan: write for the community (no "the operator", nothing about any person's tenant, landing zone, licences or preferences; say "the adopting organisation"); never harden a hedge; no conversation residue; no review history in the plan (history lives in `docs\reviews\`); no assumptions section and no risk register in the style of a form: risks appear where they matter, with what is done about each; examples are invented and labelled; never the two original findings; no lab, exam, Terrarium, wind tunnel, time machine, learner; "agreement", never "contract", for an Azure agreement; do not mention Fabric or Databricks; pictures show loops, hubs, parallel work or state changes, never one linear pipeline (Mermaid, at most 15 nodes).
- The plan uses the design's words (Hub, contract, hosted agent, Operate and Evaluate profile, capability profile, cost lake, Estate model, Atlas, Detector, Case, Credential, R1 to R3, proof points P1 to P10). It defines no new term.
- Sizes and costs are labelled *scenario parameters* (starting estimates), replaced by measurement; the plan never types a euro figure of its own: cloud cost is stated by pointing at the Pilot column of `docs\design\10-cost-and-finops.md`.
- Facts about Microsoft products are verified on Learn the day they are written.

## The document set (folder `docs\build-plan\`)

| File | Answers | Target words |
|---|---|---|
| `README.md` | What the plan is, the shape of the first phases at a glance (one picture), how to read the folder, what is out of scope, what the adopting organisation must decide first | at most 1,200 |
| `01-the-slices.md` | The slices of phase 0 and phase 1a, one table row and one short section each: what exists at the end, what is shown and to whom, what it depends on, which proof point or first check it answers, size; the dependency picture; what comes after phase 1a | at most 3,000 |
| `02-before-you-start.md` | What the adopting organisation provides (by need, with the owner and what to request first), the decisions it makes with the default and what each changes, how to pick the first estate, who does what, the working agreements and the definition of done | at most 2,500 |
| `03-first-checks.md` | The things nobody knows yet and that the build must settle early: for each, why it matters, how it is checked, the pass condition, the fallback, the slice where it happens | at most 2,500 |
| `04-cost-effort-and-risks.md` | What phase 0 and phase 1a cost to run (by pointing at the cost document), how much work they are (sizes by slice, as scenario parameters, and the people they need), what is not modelled, what could change the plan, how the plan is revised at each exit | at most 2,000 |

Total at most 11,200 words; the lint budget for the folder is 12,000.

## Principles (README states them in one table; the other documents follow them)

1. **Riskiest first, thinnest path first.** Work is ordered by what could change a choice. A walking skeleton (one synthetic lead through Watch, a Case, the Diplomat, the send step, to a test e-mail) exists at the end of phase 0, before any depth is added.
2. **Read-only until phase 3.** Phase 0 and phase 1a deploy no action role and no runner role; "zero writes to Azure" is an exit criterion of 1a. Kill switches exist from the first Operate deployment.
3. **Every slice ends in something shown**, to the FinOps lead or the platform team, with evidence that is recorded (a CI result, a hub log, a test e-mail).
4. **Evaluation grows with the code.** No role is deployed without a component suite, and no tool without a pinning and a negative test.
5. **Cost is visible from the first deployment.** Budgets and anomaly alerts on the solution's own subscriptions are the first infrastructure; cost per Case is read from hub logs from the first Case.
6. **One repository, one release record**; Bicep with Azure Verified Modules; GitHub Actions with OpenID Connect; zip deployment; no container registry (design 09).
7. **A slice is done when** its exit check passes, its tests run in CI, its cost line in the model matches what was deployed, its operational steps are in a runbook, and the person it was shown to has accepted it.
8. **Builders may use AI coding assistants.** The same gates apply to every change: CI checks, code owners, review.

## Slices

Sizes are person-weeks as scenario parameters (a range for a team that knows Azure Functions, Bicep and the Agent Framework; first slices include learning). "P" is a proof point of the roadmap (`docs\design\13-roadmap.md`); "C" is a first check (03).

### Phase 0: foundations (exit: P1, P2 and P9 pass; a fresh deployment of dev from scratch works; the isolation test passes)

| Slice | What exists at the end | Shown | Depends on | Answers | Size |
|---|---|---|---|---|---|
| 0.1 Repository, pipelines and gates | The repository layout of design 09 §1 with CODEOWNERS and rulesets; CI running lint, schema checks, secret scan, SBOM, the docs lint and the card lint; OpenID Connect to the dev subscription; budgets and anomaly alerts on the solution's subscriptions as Bicep | A pull request blocked by a failing check and merged by a code owner | A GitHub organisation and a dev subscription | none | 2 to 3 |
| 0.2 The Evaluate profile from code | Bicep with Azure Verified Modules for the `evaluate` profile: Foundry account, five Function apps (empty), Cosmos DB serverless, Blob, Key Vault, AI Search free; hub onboarding: dev contracts and the published tools; a pre-flight job for region, quota and capacity | `azd provision` from an empty subscription, then a negative test: a direct model call fails | 0.1; a Citadel hub (the organisation's, or the accelerator at a pinned commit) | C1 | 4 to 5 |
| 0.3 One hosted agent through the hub, one workflow calling it | A minimal role on the Agent Framework, deployed from a zip through its contract; a Durable workflow that invokes it, waits on a timer and resumes | The call traced in hub logs; a deadline that survives an hour of waiting | 0.2 | P1, P2, C2 | 3 to 4 |
| 0.4 Tool publishing and pinning | A stub `estate-read` tool published through the hub as MCP; its pin; a drift test | A changed tool description is rejected | 0.2 | P9, C3 | 2 |
| 0.5 Synthetic estate and evaluation skeleton | The synthetic-estate generator with planted waste and decoys; the first component suite; the isolation test (dev identities reach nothing in production); the cost model check in CI | The suite scoring a planted-waste case | 0.1, 0.2 | none (isolation test) | 3 to 4 |
| 0.6 The walking skeleton | One synthetic lead flows through Watch to a Case with stub roles, to a drafted digest, the send step and an e-mail to a test mailbox with the AI marks; the template lives in Git | The test e-mail arrives from the shared mailbox, to an allow-listed address only, with the AI label and footer | 0.3, 0.4, 0.5 | C4 | 2 to 3 |

### Phase 1a: first value on one estate (exit as in the roadmap: P4 and P7 (read paths) pass; explained spend measured; zero writes to Azure; the FinOps lead confirms a pre-set number of findings as true and worth acting on, each priced on a named basis; cost per Case and per confirmed finding read from hub logs, dead ends included, with people's hours recorded beside it)

| Slice | What exists at the end | Shown | Depends on | Answers | Size |
|---|---|---|---|---|---|
| 1a.1 The first estate and the Operate profile | The first estate chosen (02); the `operate` profile deployed with read roles only (Reader, Cost Management Reader, Monitoring Reader, Log Analytics Reader), private endpoints, a runner inside the network, prod contracts; kill switches; the capability probe running on every scope | Every scope has a capability profile; a read works and a write fails | Phase 0 exit; the adopter's prerequisites | P4 (probes), C5 | 4 to 5 |
| 1a.2 The cost lake | Cost data by the best path the profile shows (exports, else the Cost Details or Query API) in FOCUS, with the ingestion manifest; DuckDB analysis in the `tools` app | The first run lands; explained spend is measured | 1a.1 | P4, C6 | 3 to 5 |
| 1a.3 The Estate model and its refresh | The Surveyor and the Estate refresh workflow; owners resolved from the directory as guesses; counts match Resource Graph | Ten sample resources resolve to named owners | 1a.1 | none | 3 to 4 |
| 1a.4 Atlas v0 | Claims, with source, scope and evidence level, for the services the first estate uses; retrieval through the `atlas` tool; Atlas reviewers merge by pull request | A Recommendation draft that cites an Atlas claim | 0.4 | none (P5 is phase 1b) | 3 to 4 |
| 1a.5 Watch and the first Detectors | The Watch workflow; Detectors compiled from adjudicated Verified rows of the cost-trap bank, back-tested; leads | A lead on a real resource, with its evidence | 1a.2, 1a.3 | none | 3 to 4 |
| 1a.6 Cases that only report | The Detective, Skeptic and Economist; the Case workflow with the challenge loop; typed records; the price simulator; contracts and quotas; the injection suites on every read path | A Case from lead to priced Recommendation draft, with the Skeptic's objections; cost per Case read from hub logs | 1a.4, 1a.5 | P7, P10, C7, C8 | 6 to 8 |
| 1a.7 The Monday digest | The Diplomat writes the digest; the send step; e-mail through Graph with the letter rules of the experience design; first-contact e-mail to the FinOps lead; templates and the letter's tests in Git | The digest arrives by 09:00 on a Monday, renders in classic Outlook and cites its sources | 1a.6, 0.6 | C4 | 3 to 4 |
| 1a.8 Confirm and measure | The FinOps lead's confirmations recorded in the ledger; cost per Case and per confirmed finding; people's hours recorded | The pre-set number of confirmed findings is reached, or the plan is revised | 1a.7 | P10 | 2 to 3 (mostly the FinOps lead's calendar) |

Phase 0 is 16 to 21 person-weeks and phase 1a 27 to 37; the whole first stretch is 43 to 58 person-weeks: about five to seven months for two people, three to five for three. The sizes are replaced by measurement at the end of slice 0.3.

### What comes after (one section, from the roadmap)

Phase 1b (the system learns: Study on its clock, the report card, baselines, P5, P6, P10), phase 2 (Teams, web pages for every owner, preferences and the notification policy, Lessons; the client matrix is its exit criterion), phase 3 (the action plane; P3 and P8), phase 4 (Credentials and purchases), phase 5 (open up). The plan is detailed only as far as 1a; it is revised at each exit with the measured sizes and the proof points' results.

### Dependencies (picture): parallel tracks

Tracks that run in parallel once 0.2 exists: Platform and pipelines (0.1, 0.2, 1a.1); Agents and workflows (0.3, 1a.6); Data (1a.2, 1a.3); Knowledge (0.4, 1a.4, 1a.5); Engagement (0.6, 1a.7); Evaluation (0.5, and every slice adds its suites). A Mermaid flowchart with 12 to 15 nodes (slices as nodes, arrows for "depends on", subgraphs for tracks) plus a state diagram of a slice's life with back-edges: Planned, Building, Checked, Shown, Accepted; Checked back to Building when a check fails; Shown back to Building when it is not accepted; Accepted to Revisited when a proof point changes a choice.

## First checks (03)

Each is a short test with a pass condition and a fallback; none deploys anything just to learn (rule 11 (c)): they use the build's own environments.

| # | Check | Slice | Pass condition | Fallback |
|---|---|---|---|---|
| C1 | The hub path works end to end: hosted agent, hub, model and tool, per-agent token and quota, Responses API; a direct model call fails; an agent without a role cannot read the estate | 0.2 | Calls succeed; the direct call and the unauthorised read fail | Chat Completions route; a prompt agent for simple roles |
| C2 | Workflows call hosted agents reliably (auth, timeouts, session reuse, idle tails); storage backend or Durable Task Scheduler | 0.3 | Calls complete within the deadline; idle tails within budget; backend chosen on measured price and recovery | Own adapter around the generally available Agent Framework core; the other backend |
| C3 | The hub rejects a changed tool (name, description, schema, server digest); whether an optional Azure MCP Server earns its host | 0.4 | A changed tool is rejected | Block `tools/list` changes in the contract; typed tools only |
| C4 | The letter path: Graph `sendMail` as MIME carries the headers `x-ai-generated: true` and `X-Auto-Response-Suppress`; Exchange RBAC for Applications limits the app to the one shared mailbox; the mail-flow rule rejects any recipient not on the allow-list; the letter renders in classic Outlook and in the new Outlook | 0.6 and 1a.7 | Every one holds on the adopting organisation's tenant | Teams or the web page carry what e-mail cannot |
| C5 | The capability probe classifies each agreement and level of access the way the portal shows it | 1a.1 | Agreement type, billing reach and cost access agree with the portal on every scope of the first estate | The estate owner states agreement and access by hand |
| C6 | Cost data holds at the first estate's volume (DuckDB in a 4 GB instance; ingestion and refresh within budget) | 1a.2 | Queries and refresh finish within the stated budget | Azure Data Explorer; provisioned Cosmos DB throughput |
| C7 | No untrusted-text path reaches a propose tool or a write | 1a.6 | A red team finds none; screening catches seeded attacks | Split the role into its own hosted agent |
| C8 | Tokens and cost per investigation, per Case that reaches an owner and per confirmed finding, dead ends included; the cost model matches the bill | 1a.6 and 1a.8 | Measured cost within a stated margin of the model | A cheaper model tier; smaller prompts; more Detectors |
| C9 (before phase 2) | The Teams client matrix: buttons on phone widths, links opening in an embedded view or the system browser (security keys and passkeys do not work in embedded views), the AI-generated label and thumbs on a card message, `text` or `summary` in the toast, right-to-left, the `Action.Execute` fallback | Prepared early; run when the Teams app exists | The matrix is filled in and every failure has a decided fallback | Cards only open the page; e-mail carries the letters |
| C10 (before phase 2) | The approval page: step-up with an authentication context in the system browser, a phishing-resistant method for R3, reachability on the private endpoint, the page when the app is down | Phase 2 start | A person can approve in each supported browser; the failure messages are the ones the experience design shows | The page only after an e-mail link; a published front door where approvers work off-network |

Checks for phase 3 (P3 approval integrity, P8 runner roles) and phase 4 are named, not planned.

## Before you start (02)

**What the adopting organisation provides**, by need, with the person who can give it and what to request first (lead times are the organisation's own; start every request in week 0): a dev subscription and a prod subscription for the solution (and the estate's scopes, read-only); a Citadel hub (its own, or the accelerator at a pinned commit, which needs Owner or Contributor with User Access Administrator); model quota in the chosen region and a check that hosted agents are available there; Entra permissions to create app registrations, federated credentials and app roles; Entra ID P1 for authentication contexts (needed from phase 2); a Microsoft 365 tenant with an Exchange Online shared mailbox and the permission to scope the app to it with Exchange RBAC for Applications; a GitHub organisation (OpenID Connect, rulesets, code owners); a delegated subnet, private DNS and a runner inside the network for Operate; named people for the roles of design 09 §6.

**Decisions the adopting organisation makes**, each with a default and what it changes: the first estate and its access level; the data boundary for estate data (Data Zone, a fifth more per token, or Global Standard); region (default Sweden Central, checked by the pre-flight job); reuse its hub or deploy the accelerator; an always-ready Functions instance for the Durable group (cost against cold starts); the runner for private deployments (self-hosted, or GitHub larger runners with Azure private networking); the pre-set number of confirmed findings that ends phase 1a (default: stated by the FinOps lead before 1a.6 starts, never after); Teams or not in phase 2.

**Choosing the first estate.** Criteria: owners who answer; a FinOps lead who will read the digest weekly; enough spend for findings to matter but a size that a first Case can read; a stated access level (subscription-level Cost Management access is enough to start; billing-level roles add prices and purchase paths; without cost access the system works at list prices and says so); no change freeze in the first months; and it must not be the dev subscription of the solution. How each access level changes what slice 1a.2 and 1a.5 deliver is in design 14.

**Who does what** (design 09 §6 roles): the platform team builds, releases and is on call (business hours); the FinOps lead is the first user and the person who confirms findings; security reviewers own contracts, the Action catalogue (empty until phase 3), `.github/` and the red-team results; Atlas reviewers merge Atlas and Detector pull requests and adjudicate gold labels; the estate owner deploys the onboarding module. The plan assumes no other role.

**Working agreements.** Trunk with short-lived branches; every path has a code owner; CI order: lint and schema, zero-LLM suites, what-if, secret scan and SBOM, deploy to dev, isolation and negative tests, evaluation subset; nothing deploys to prod except from a tag with a release record; no secret in the repository or in a parameter file; prompts, contracts, tool pins and templates are code. **Definition of done** is principle 7.

## Cost, effort and risks (04)

- **Cost to run.** Phase 0 runs the Evaluate profile only; phase 1a adds the Operate profile at read-only scope. The cost document's Pilot column prices the full Operate profile (five apps, eleven private endpoints, the runner, the bot); phase 1a uses fewer parts, so the Pilot total is an upper bound. The plan names which lines of the cost model 1a does not need (the `runner` and `bot` apps' executions, the two private endpoints of the `approvals` and `runner` apps, Content Safety on owner replies) and does not re-price them. Evaluation tokens are the main variable cost of phase 0 (cost document).
- **Effort.** The sizes above, by slice and by role (platform team, FinOps lead hours, security reviewer hours, Atlas reviewer hours): the FinOps lead and reviewers' time is small per week and calendar-bound.
- **Not modelled**: people's time beyond the sizes, platform operations, licences the organisation already owns, a second region.
- **Risks, with what is done about each**: preview features (hosted agents, Flex for models, Agent Framework hosting): each is behind a switch with a generally available fallback, and the first checks test the fallback too; the hub accelerator changes: pinned, re-tested with C1 and C3 before upgrading; private-network deployment friction: slice 0.2 includes the runner decision and a pre-flight; quota and region limits: the pre-flight job; tenant permissions and mailbox scoping take time: requested in week 0; a slow confirmation by the FinOps lead: the exit criterion is a number stated in advance and a calendar slot for 1a.8 held from the start of 1a.6; the cost model's seeds are wrong: C8 replaces them; scope creep from phase 2 features: a slice's exit check is the only scope.
- **What could change the plan**: the table of the roadmap, plus a proof point failing (each has a fallback that changes a choice, not the project; P6 in phase 1b is the exception).
- **Revision**: at each phase exit the plan is re-issued with the measured sizes, the results of the checks and the next phase detailed to the same depth.

## What the plan leaves out on purpose

Calendar dates and staffing commitments (they belong to the adopting organisation); phases 1b to 5 in detail; build instructions (the repository will hold them); any resource deployment; costs of people.

## Questions for the reviewers

1. Is the order right? Would you move a slice earlier or later, merge or split slices, or add one (for example the report card, the first Study run, or the kill-switch drill)?
2. Are the dependencies complete? Is anything shown without what it needs?
3. Are the first checks the right ones, with passable pass conditions and real fallbacks? What is missing from the design's proof points or the experience design's unverified items?
4. Are the sizes plausible as starting estimates for a small team? Which is most likely too small or too large, and why?
5. What would stop a team from starting on Monday after reading it (a missing prerequisite, an undefined term, a decision hidden in a table)?
6. Does anything contradict the design or the experience design? Cite file and line.
7. What are the three most likely ways this plan fails, and what would you add so that it does not?
