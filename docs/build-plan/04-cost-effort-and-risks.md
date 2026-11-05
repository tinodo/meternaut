# Cost, effort and risks

**What this document answers.** What phase 0 and phase 1a cost to run, how much work they are, where the plan can go wrong and what is done about it, what could change the plan, and when the plan is revised. The plan states no euro figure of its own: cloud cost is in the [cost document](../design/10-cost-and-finops.md).

## What phase 0 and phase 1a cost to run

The cost document prices the system at three scales (its Pilot, Team and Enterprise columns) and shows in a sensitivity table what single changes do to the total. A tool generates the figures from list prices (no taxes, support plans or negotiated discounts) and from starting volumes that measurement replaces. The figures are priced for Sweden Central; in another region, fetch the price snapshot again (`tools/fetch-prices.py`) before slice 1a.1 compares the fixed lines.

**Phase 0** runs the [Evaluate profile](../design/02-architecture.md#7-two-profiles-one-codebase) only, on synthetic data. Evaluation tokens are its main variable cost. The cost document's Evaluate rows price evaluation across all roles, a ceiling that phase 0, with one minimal role, stays below. The evaluation contract in the [hub](../design/README.md#words-used-in-this-design) has a daily cap that stops a runaway suite ([evaluation costs](../design/08-testing-and-evaluation.md#9-what-evaluation-costs)).

**Phase 1a** keeps the dev environment and deploys the Operate profile without the `bot`, `approvals` and `runner` apps and the two private endpoints of the last two. The Pilot column prices the full profile, with its eleven private endpoints, so phase 1a sits slightly under it. It is a **reference scenario** (five subscriptions, 500 resources and starting volumes), **not an upper bound**: a larger first estate costs more. The idle floor (search unit, private endpoints, always-ready Functions instance, Durable state, stored data) bills from the day [slice](01-the-slices.md#how-a-slice-works) 1a.1 deploys the profile, with or without a [Case](../design/README.md#words-used-in-this-design).

Measurement replaces the reference in three places. Slice 1a.1 checks the deployed fixed lines (private endpoints, search unit, always-ready instance) against the cost model, records the result as the slice's cost line and checks the Azure Language PII rate, which the cost document marks as unverified, against the vendor's page. Slice 1a.8 compares the model with the bill of one closed billing month ([check](03-first-checks.md#the-checks) C8) and replaces the seeded volumes and the Durable storage estimate with measured ones. From the first Case, hub logs give the cost per Case and per confirmed finding, dead ends included, with people's hours beside them.

**Two funded stages** cost little: slice 0.0 deploys nothing, and slice 0.7 spends model tokens on a few cases through the hub, inside its spending cap.

**Not used in phase 1a.** The Pilot column prices the whole Operate profile at full scale. `python tools/cost-model.py --lines Pilot` lists the volumes behind each line. Phase 1a does not use these parts, and Study is the largest of them:

| In the Pilot column | Why phase 1a does not use it |
|---|---|
| The line for [Study](../design/03-agents-and-workflows.md#4-seven-workflows) (the workflow that reads public documents), and its share of the hosted-agent, Functions, semantic-ranker and content-safety lines | Study runs on its clock from phase 1b |
| The [Engineer's and the Auditor's](../design/03-agents-and-workflows.md#1-ten-roles-in-five-hosted-agents) calls in the per-Case token line | A phase 1a Case only reports: nothing to plan, nothing to verify |
| The owner-reply share of the content-safety and PII-detection lines | Owners reply from phase 2 |
| The `bot`, `approvals` and `runner` apps, the private endpoints of the last two, and Azure Bot Service | They wait for the phase that first uses them: the bot and the `approvals` app for phase 2, the `runner` for phase 3. The cost document gives the apps no line: the five apps share one Functions line, and Teams delivery has no meter ([pricing](https://azure.microsoft.com/pricing/details/bot-services/)). |

**Superseded in part on 2026-11-05:** the phase 3 `runner` app as a writer with rights of its own. A change runs as the approver; see [decision 24](../design/12-decisions.md#24-a-change-runs-as-the-approver-meternaut-holds-no-right-to-change-azure--accepted) and [proposal 05](../proposals/05-run-as-the-approver.md).

**Not in the totals:** the hub (shared platform cost; without one, the sensitivity table's own-hub row prices a production gateway and slice 0.2 takes more effort); a deployment runner inside the network (the organisation chooses and prices it); the pre-release `operate` environment, which bills while it exists; licences to check (Entra ID P1 for authentication contexts from phase 2, [Learn](https://learn.microsoft.com/entra/identity/conditional-access/overview#license-requirements); Microsoft 365 for Exchange Online and, from phase 2, Teams; the GitHub plan and its pipeline minutes); and people's time, which the plan does not price.

Three [decisions](02-before-you-start.md#decisions-the-adopting-organisation-makes) move the total, and the sensitivity table prices each: the data boundary for estate data, the always-ready Functions instance, and a hub of the organisation's own. Phase 1a makes no change to the estate, so the system saves nothing by itself; the cost document's break-even row says what share of managed spend it must save to pay for itself on cloud cost alone.

## How much work it is

Sizes are in person-weeks and are **scenario parameters**: starting estimates for a team that knows Azure Functions, Bicep and the Agent Framework, replaced by measurement.

| Slice | Person-weeks |
|---|---|
| 0.0 Pilot feasibility | 1 to 2 |
| 0.1 Repository, pipelines and gates | 2 to 3 |
| 0.2 Evaluate profile and hub path | 4 to 5, or 6 to 8 if the [hub accelerator](../design/02-architecture.md#6-the-landing-zone-and-the-hub) is deployed |
| 0.3 Published tool, pins and first suite | 4 to 5 |
| 0.4 One hosted agent, one workflow | 3 to 4 |
| 0.5 The mail path | 2 to 3 |
| 0.6 Thin path end to end, first drill | 3 to 4 |
| 0.7 Learning demonstration | 3 to 4 |
| **Phase 0** | **22 to 30** |
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
| **Both phases** | **60 to 82** |

The plan needs two or three builders from the platform team, a few hours a week from the [FinOps lead](02-before-you-start.md#who-does-what) (more in slices 1a.7 and 1a.8), and hours from security reviewers (hub contracts, the gate change in C11, the red-team session) and Atlas reviewers (claims, Detectors and the cases of C14).

In calendar time, 60 to 82 person-weeks is roughly nine to twelve months for two builders and six to eight for three, before the organisation's approvals and before a billing month closes; the months are scenario parameters too. Most slices wait for an earlier one ([what depends on what](01-the-slices.md#what-depends-on-what)), so a second builder does not shorten a slice that one person takes alone. The longest chains of slices that each start after another are 9 to 12 person-weeks to the learning review, at most 37 to 51 to the first-workload milestone and 43 to 59 to the end of phase 1a: about 3, 11 to 15 and 12 to 17 months with one builder on each slice, and the shorter estimates assume that builders share the long slices. With the hub accelerator, phase 0 is 24 to 33, both phases 62 to 85, and each chain 2 to 3 longer. A size covers both passes of a slice, so the figure for the milestone is a ceiling: the first pass for one workload needs less, and the first slices show how much.

**The schedule is provisional, not a commitment.** After each slice the team records the person-weeks it took beside its size, and the speed measured so far replaces the starting estimate for the slices that follow.

## Where it can go wrong

| What could go wrong | What is done about it |
|---|---|
| **The pilot cannot support analysis:** no per-resource bill, a missing grant, or no hub, region or quota. | Slice 0.0 finds out in week 0, before anything that bills is deployed, and the feasibility review decides. |
| **The central idea does not show,** and months of building follow. | Slice 0.7 and check C14 test it at small scale before phase 1a, and the learning review decides. C14 shows that the loop works, not how far it generalises: P6 in phase 1b tests that. |
| **The first findings are not worth acting on:** duplicates, small, or only a restatement of Azure's advice. | The finding record counts only findings that are distinct, credible and add discovery or follow-through, and the workload review reads them before anything is widened. |
| **Spend runs away.** | Budgets and anomaly alerts on the solution's own subscriptions are the first infrastructure (slice 0.1). They only alert: Azure checks budgets every 24 hours and does not stop consumption ([Learn](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets)). The stops are the hub's token quotas, the kill switch that trips when a day's model spend passes its cap (drilled in C12) and the spending cap of each funded stage. |
| **The cost model is wrong,** or the first estate is bigger than the Pilot scenario. | Slice 1a.1 checks the deployed fixed lines against the model. C8 reads tokens per Case from hub logs, and slice 1a.8 compares the model with a closed bill, within a margin written down beforehand. |
| **Convincing advice with no price behind it,** because the first estate offers only totals, or no cost access. | C13 checks for a per-resource bill path in week 0 and again before slice 1a.2. Without one the phase 1a exit cannot be reached: choose another estate, or state in writing that the pilot cannot pass. |
| **Detectors promoted too early** turn false alarms into the Monday digest. | In phase 1a Detectors run in shadow only, and a sample of their leads is graded blind. A person decides on promotion, on numbers written into each Detector beforehand; it is no part of the exit. |
| **A mail grant that is too broad,** or mail that is accepted but never arrives. | Check C4: only the scoped Exchange role, no organisation-wide Entra mail permission, and delivery proved by receipt. If the path fails, a person sends the digest by hand, and slices 0.5 and 1a.7 stay open. |
| **A release gate that cannot be met before phase 1b:** the Capability gate needs sealed test cases and baselines. | A reviewed change to the gate is merged before the first production release (C11). |
| **Preview features:** Flex processing for model calls ([Learn](https://learn.microsoft.com/azure/foundry/openai/how-to/flex-processing)) and the Agent Framework's Foundry hosting package ([Learn](https://learn.microsoft.com/agent-framework/hosting/foundry-hosted-agent)). | Each sits behind a switch with a generally available fallback: Standard processing and a thin adapter of our own around the generally available Agent Framework core. The [technology register](../design/11-technology-register.md) lists the rest. |
| **The hub accelerator changes** its contracts or defaults. | One commit is pinned. An upgrade is tried in dev first, and C1 and C3 run again before it reaches production. |
| **Private-network friction.** Deploying to a private Foundry account fails from a public workstation, and Learn calls DNS the most common failure ([Learn](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks)). | The deployment runner is a required decision in [02](02-before-you-start.md#decisions-the-adopting-organisation-makes), and the platform team checks the network by hand in week 0. |
| **Quota and region limits.** Learn flags Sweden Central, the default region, as in high demand for new AI Search services ([Learn](https://learn.microsoft.com/azure/search/search-region-support)). | The platform team checks in week 0 that the region accepts a new search service ([the region check](02-before-you-start.md#decisions-the-adopting-organisation-makes)); the pre-flight job (slice 0.2) repeats it, then checks model quota, hosted-agent availability and a second model family for the judge. |
| **Permissions and mailboxes wait on other teams.** | Every request in [02](02-before-you-start.md#what-the-adopting-organisation-provides) starts in week 0, with a named person. |
| **The FinOps lead confirms findings slowly.** | The number of findings is written down before work on the Cases starts, and a calendar slot is held from the start of slice 1a.6a. |
| **Scope creep from phase 2.** | A slice's check is its only scope. A feature that no phase 1a check needs waits for its phase. |

The Microsoft pages linked above were read on 2026-11-02.

## The three reviews

Three reviews can change the plan before a phase exit. Each is held at a review point of its funded stage, by the stage's named owner with the FinOps lead and the platform team lead, and ends in one of three answers: go on, change something and repeat, or stop. The answer and its reason are recorded in the repository, never the estate's data.

**Four funded stages** each have a named owner, a spending cap and a review point: week-0 feasibility (slice 0.0), foundations (0.1 to 0.6), the learning demonstration (0.7) and the first workload (the first pass of 1a.1 to 1a.6b). A review point is an event, never a date: the stage's work is finished, its budget's warning alert fires or one of its checks fails, whichever comes first. Three end in the reviews below; foundations is reviewed at the phase 0 exit, against [the roadmap's exit tests](../design/13-roadmap.md#1-phases), by the same people with the same answers. The workload review also sets the owner, cap and review point of the next stage.

**A funded stage stops at its spending cap.** It is charged the model tokens of its hub contracts at their token price (from the hub's logs) and the resources tagged with its name (from Cost Management). A tag reaches cost data only for resource types that carry it and only after a refresh, so resources are tagged when created. Cost data is 8 to 72 hours late, so the cap is set below what the organisation can afford to lose. The owner reads the total each working day, and the budgets of slice 0.1 alert at their thresholds. At the cap new work stops: the owner suspends the hub contract and, until the kill switch of 0.6 exists, a harness stops itself at its call limit and cap. The stage's resources are then deleted or kept on purpose, so that the idle floor does not bill unnoticed, and the review records which.

| Review | Held | Question | Evidence | If the answer is no |
|---|---|---|---|---|
| Feasibility | End of week 0, before slice 0.2 deploys anything that bills | Can this pilot's data support meaningful analysis? | The record of slice 0.0: a closed month reconciled (C13), its price basis, and the named owner, access, hub, region and quota | Choose another estate or workload, get the missing grant, or stop |
| Learning | After slice 0.7, before slice 1a.1 | Did a quoted claim, accepted by a person, change the answers on unseen cases while look-alikes stayed quiet? A pass says nothing about retrieval from the Atlas or the Case path | The report of C14, with its limits and its cost | Change what failed and repeat once on new cases; if that fails, change the learning design before building on, or stop |
| Workload | At the first-workload milestone, before anything is widened | Is what the first workload produced worth acting on, and is the way to widen sound? | The workload's finding records, the cost per Case, and the effort and speed measured so far | Fix the weakest step and repeat, choose another workload, or stop |

## What could change the plan

[The roadmap](../design/13-roadmap.md#3-what-could-change-the-plan) lists six changes that alter the work, and what each does. Three show up in a check first: measured tokens per Case far above the cost model's starting volumes (C8), an estate too large for one process to scan the cost lake (C6), and a change in the hub accelerator's contracts or defaults (C1 and C3).

A failing proof point changes a choice, not the project: the check is recorded as failed, its fallback is applied and tested, and the slice's exit moves. The exception is P6 in phase 1b: if updated memory does not beat frozen memory, the learning claim is withdrawn and the goals reopen.

## How the plan is revised

At each phase exit the plan is issued again as a new version. Measured sizes replace the starting estimates, the results of the checks and reviews are recorded, and the next phase is planned to the same depth as this one. The exit of phase 1a therefore brings a version that plans phase 1b.
