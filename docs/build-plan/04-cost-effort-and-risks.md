# Cost, effort and risks

**What this document answers.** What phase 0 and phase 1a cost to run, how much work they are, where the plan can go wrong and what is done about it, what could change the plan, and when the plan is revised. The plan states no euro figure of its own: cloud cost is in the [cost document](../design/10-cost-and-finops.md).

## What phase 0 and phase 1a cost to run

The cost document prices the system at three scales (its Pilot, Team and Enterprise columns) and shows in a sensitivity table what single changes do to the total. A tool generates the figures from list prices (no taxes, support plans or negotiated discounts) and from starting volumes that measurement replaces. The figures are priced for Sweden Central; in another region, fetch the price snapshot again (`tools/fetch-prices.py`) before slice 1a.1 compares the fixed lines.

**Phase 0** runs the [Evaluate profile](../design/02-architecture.md#7-two-profiles-one-codebase) only, on synthetic data. Evaluation tokens are its main variable cost. The cost document's Evaluate rows price the steady state of evaluation across all roles, a ceiling that phase 0, with one minimal role, stays below. The evaluation contract in the [hub](../design/README.md#words-used-in-this-design) has a daily cap that stops a runaway suite ([evaluation costs](../design/08-testing-and-evaluation.md#9-what-evaluation-costs)).

**Phase 1a** keeps the dev environment and deploys the Operate profile in full, except the `bot` app (phase 2). The Pilot column prices that profile, with its eleven private endpoints. It is a **reference scenario** (five subscriptions, 500 resources and starting volumes), **not an upper bound**: a larger first estate costs more. The idle floor (search unit, private endpoints, always-ready Functions instance, Durable state, stored data) bills from the day [slice](01-the-slices.md#how-a-slice-works) 1a.1 deploys the profile, with or without a [Case](../design/README.md#words-used-in-this-design).

Measurement replaces the reference in three places:

- Slice 1a.1 checks the deployed fixed lines (private endpoints, search unit, always-ready instance) against the cost model, records the result as the slice's cost line and checks the Azure Language PII rate, which the cost document marks as unverified, against the vendor's page.
- Slice 1a.8 compares the model with the bill of one closed billing month ([check](03-first-checks.md#the-checks) C8), replaces the seeded volumes with measured ones, and replaces the estimate of the Durable storage account with its billed cost.
- From the first Case, hub logs give the cost per Case and per confirmed finding, dead ends included (investigations that end before anyone is told), with people's hours beside them.

**Not used in phase 1a.** The Pilot column prices the whole Operate profile at full scale. `python tools/cost-model.py --lines Pilot` lists the volumes behind each line. Phase 1a does not use these parts, and Study is the largest of them:

| In the Pilot column | Why phase 1a does not use it |
|---|---|
| The line for [Study](../design/03-agents-and-workflows.md#4-seven-workflows) (the workflow that reads public documents), and its share of the hosted-agent, Functions, semantic-ranker and content-safety lines | Study runs on its clock from phase 1b |
| The [Engineer's and the Auditor's](../design/03-agents-and-workflows.md#1-ten-roles-in-five-hosted-agents) calls in the per-Case token line | A phase 1a Case only reports: nothing to plan, nothing to verify |
| The owner-reply share of the content-safety and PII-detection lines | Owners reply from phase 2 |
| The `bot`, `approvals` and `runner` apps, and Azure Bot Service | The bot waits for phase 2. The `approvals` app carries no code until phase 2 (the pages) and the `runner` none until phase 3. The cost document gives them no line: the five apps share one Functions line, and Teams delivery has no meter ([pricing](https://azure.microsoft.com/pricing/details/bot-services/)). The private endpoints of `approvals` and `runner` are deployed in 1a.1 and billed |

**Not in the totals:**

- **The hub:** shared platform cost. Without one, the sensitivity table's own-hub row prices a production gateway, and slice 0.2 takes more effort.
- **A deployment runner inside the network** (self-hosted, or GitHub larger runners): the organisation chooses and prices it.
- **The pre-release `operate` environment** that a job creates in dev and deletes: it bills while it exists.
- **Licences to check:** Entra ID P1 for authentication contexts, from phase 2 ([Learn](https://learn.microsoft.com/entra/identity/conditional-access/overview#license-requirements)); Microsoft 365 (Exchange Online for the shared mailbox, Teams from phase 2); the GitHub plan and its pipeline minutes.
- **People's time,** which the plan does not price. The cost document notes that at Pilot size a single platform day a month can cost more than the whole cloud bill.

Three [decisions](02-before-you-start.md#decisions-the-adopting-organisation-makes) move the total, and the sensitivity table prices each: the data boundary for estate data, the always-ready Functions instance, and a hub of the organisation's own. Phase 1a makes no change to the estate, so the system saves nothing by itself; the cost document's break-even row says what share of managed spend it must save to pay for itself on cloud cost alone.

## How much work it is

Sizes are in person-weeks and are **scenario parameters**: starting estimates for a team that knows Azure Functions, Bicep and the Agent Framework, replaced by measurement.

| Slice | Person-weeks |
|---|---|
| 0.1 Repository, pipelines and gates | 2 to 3 |
| 0.2 Evaluate profile and hub path | 4 to 5, or 6 to 8 if the [hub accelerator](../design/02-architecture.md#6-the-landing-zone-and-the-hub) is deployed |
| 0.3 Published tool, pins and first suite | 4 to 5 |
| 0.4 One hosted agent, one workflow | 3 to 4 |
| 0.5 The mail path | 2 to 3 |
| 0.6 Thin path end to end, first drill | 3 to 4 |
| **Phase 0** | **18 to 24** |
| 1a.1 First estate and Operate profile | 5 to 6 |
| 1a.2 The cost lake | 4 to 6, including the generator of synthetic cost data that C6 needs |
| 1a.3 Estate model and its refresh | 4 to 5 |
| 1a.4 Atlas v0 | 3 to 4 |
| 1a.5 Watch and the first Detectors | 4 to 5 |
| 1a.6a Price simulator and Economist | 5 to 7 |
| 1a.6b Cases that only report | 7 to 11 |
| 1a.7 The Monday digest | 4 to 5 |
| 1a.8 Confirm and measure | 2 to 3, longer elapsed |
| **Phase 1a** | **38 to 52** |
| **Both phases** | **56 to 76** |

The plan needs two or three builders from the platform team, a few hours a week from the [FinOps lead](02-before-you-start.md#who-does-what) (more in slices 1a.7 and 1a.8), and hours from security reviewers (hub contracts, the gate change in C11, the red-team session) and Atlas reviewers (claims and Detectors).

In calendar time, 56 to 76 person-weeks is roughly eight to eleven months for two builders and five to eight for three, before the organisation's approvals and before a billing month closes; the months are scenario parameters too. Most slices wait for an earlier one ([what depends on what](01-the-slices.md#what-depends-on-what)), so a second builder does not shorten a slice that one person takes alone. The longest chain of slices that each start after another is 43 to 59 person-weeks (about 12 to 17 months with one builder on each slice), and the shorter estimates assume that builders share the long slices. Sizes are re-estimated at the end of slice 0.4 and after the first real Case in slice 1a.6b.

## Where it can go wrong

| What could go wrong | What is done about it |
|---|---|
| **Spend runs away.** | Budgets and anomaly alerts on the solution's own subscriptions are the first infrastructure (slice 0.1). They only alert: Azure checks budgets every 24 hours and does not stop consumption ([Learn](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets)). The stops are the hub's token quotas and the kill switch that trips when a day's model spend passes its cap, drilled in C12. |
| **The cost model is wrong,** or the first estate is bigger than the Pilot scenario. | Slice 1a.1 checks the deployed fixed lines against the model. C8 reads tokens per Case from hub logs, and slice 1a.8 compares the model with a closed bill, within a margin written down beforehand. |
| **Convincing advice with no price behind it,** because the first estate offers only totals, or no cost access. | C13 checks for a per-resource bill path before slice 1a.2. Without one the phase 1a exit cannot be reached: choose another estate, or state in writing that the pilot cannot pass. |
| **Detectors promoted too early** turn false alarms into the Monday digest. | In phase 1a Detectors run in shadow only, and a sample of their leads is graded blind. A person decides on promotion, on numbers written into each Detector beforehand; it is no part of the exit. |
| **A mail grant that is too broad,** or mail that is accepted but never arrives. | Check C4. Only the scoped Exchange role is granted, with no organisation-wide Entra mail permission, because the two add up ([Learn](https://learn.microsoft.com/exchange/permissions-exo/application-rbac)). A denied second mailbox and a received test message prove the path, because Graph's 202 means only "accepted" ([Learn](https://learn.microsoft.com/graph/api/user-sendmail)). If the path fails, a person sends the digest by hand, and slices 0.5 and 1a.7 stay open. |
| **A release gate that cannot be met before phase 1b:** the Capability gate needs sealed test cases and baselines, which 1b builds. | A reviewed change to the gate is merged before the first production release (C11). The recommended default: until 1b exits the gate reports on the development set and cannot block, and only the FinOps lead receives output. |
| **Preview features.** Flex processing for model calls is in preview ([Learn](https://learn.microsoft.com/azure/foundry/openai/how-to/flex-processing)). The Agent Framework's Foundry hosting package is prerelease; the hosted-agent service is generally available ([Learn](https://learn.microsoft.com/agent-framework/hosting/foundry-hosted-agent)). | Each sits behind a switch with a generally available fallback: Standard processing (Flex does not fall back by itself) and a thin adapter of our own around the generally available Agent Framework core. The [technology register](../design/11-technology-register.md) lists the rest. |
| **The hub accelerator changes** its contracts or defaults. | One commit is pinned. An upgrade is tried in dev first, and C1 and C3 run again before it reaches production. |
| **Private-network friction.** Deploying to a private Foundry account fails from a public workstation, and Learn calls DNS the most common failure ([Learn](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks)). | The deployment runner is a required decision in [02](02-before-you-start.md#decisions-the-adopting-organisation-makes). The platform team checks the network by hand in week 0, and the pre-flight job (a pipeline step that checks region, quota and capacity before anything is deployed) gains the same check. |
| **Quota and region limits.** Learn flags Sweden Central, the default region, as in high demand for new AI Search services ([Learn](https://learn.microsoft.com/azure/search/search-region-support)). | The platform team checks in week 0, before any quota request, that the region accepts a new search service ([the region check](02-before-you-start.md#decisions-the-adopting-organisation-makes)). The pre-flight job (slice 0.2) repeats it first, then checks model quota, hosted-agent availability and a second model family for the judge. |
| **Permissions and mailboxes wait on other teams.** | Every request in [02](02-before-you-start.md#what-the-adopting-organisation-provides) starts in week 0, with a named person. Subscriptions come first: a new one can need up to 48 hours before Cost Management features work ([Learn](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets)). |
| **The FinOps lead confirms findings slowly.** | The number of findings is written down before work on the Cases starts, and a calendar slot is held from the start of slice 1a.6a. |
| **Scope creep from phase 2.** | A slice's check is its only scope. A feature that no phase 1a check needs waits for its phase. |

The Microsoft pages linked above were read on 2026-11-02.

## What could change the plan

[The roadmap](../design/13-roadmap.md#3-what-could-change-the-plan) lists six changes that alter the work, and what each does. Three show up in a check first: measured tokens per Case far above the cost model's starting volumes (C8), an estate too large for one process to scan the cost lake (C6), and a change in the hub accelerator's contracts or defaults (C1 and C3).

A failing proof point changes a choice, not the project: the check is recorded as failed, its fallback is applied and tested, and the slice's exit moves. The exception is P6 in phase 1b: if updated memory does not beat frozen memory, the learning claim is withdrawn and the goals reopen.

## How the plan is revised

At each phase exit the plan is issued again as a new version. Measured sizes replace the starting estimates, the results of the checks are recorded, and the next phase is planned to the same depth as this one. The exit of phase 1a therefore brings a version that plans phase 1b.
