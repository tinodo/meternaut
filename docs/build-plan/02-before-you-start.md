# Before you start

**What this document answers.** What the adopting organisation must provide, decide and name before and during [phase 0 and phase 1a](README.md#the-shape-at-a-glance); how to choose the first estate; who does what; and when a slice is done.

Terms follow the design's [glossary](../design/README.md#words-used-in-this-design). Slice numbers (0.2, 1a.1) come from [the slices](01-the-slices.md), and check numbers (C4) from [the first checks](03-first-checks.md#the-checks).

## What the adopting organisation provides

Start every request in week 0, the week of slice 0.0 and before any slice that needs it begins. Lead times are the organisation's own, and tenant permissions and mailbox scoping can take weeks.

| Need | Who can grant it | What to ask for first | Needed by |
|---|---|---|---|
| Two Azure subscriptions for the solution: dev and prod | An Azure administrator, or whoever creates subscriptions under the agreement | Create both first: a new subscription can need up to 48 hours before Cost Management features work ([Learn](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets)). Give the platform team Owner (or Contributor with the right to assign roles) on dev. On prod, deployments run from the pipeline, and anyone else needs a time-boxed elevation ([design 09](../design/09-delivery-and-operations.md#7-incident-playbooks)). Dev holds no role on any production scope | 0.1 |
| Roles for the pipeline and for emergencies | An Azure administrator, with the platform team lead | The pipeline's deployment identity (created in 0.1) needs Owner, or Contributor plus User Access Administrator, on its subscription. Name the break-glass accounts that the solution's Deployment Stack leaves out of its deny setting ([design 09](../design/09-delivery-and-operations.md#4-deployment-stacks-and-the-runner)) | 0.1 |
| A Citadel governance hub, the gateway for every model and tool call | The hub owner. Without a hub: someone with Owner, or Contributor plus User Access Administrator, on a third subscription, kept apart from dev and prod, for Microsoft's open-source [accelerator](https://github.com/Azure-Samples/ai-hub-gateway-solution-accelerator) | Dev contracts (each agent's entry in the hub: its token limit, allowed tools and model aliases) and the hub's way of publishing a tool; or, without a hub, the decision to deploy the accelerator (next section) | 0.2 |
| Model quota in the chosen region; hosted agents available there; a second model family that can be deployed in that region and data boundary | The Foundry or AI platform owner | Quota for each model alias (a name such as `judge` that the hub maps to a model), and a check of the region against the [hosted-agent region list](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents#region-availability). The second family serves `judge`, the model that scores the others' answers, which must differ from the family that reasons | 0.2 |
| Permission to create app registrations, assign app roles and add federated identity credentials | An Entra administrator | The permission itself, or a named person who creates these objects on request | 0.1 |
| A GitHub organisation with OpenID Connect to Azure, rulesets and code owners | The GitHub organisation owner | The settings, and a team for each code-owner group: platform team, security reviewers and Atlas reviewers (they merge changes to the Atlas, the system's sourced claims about Azure, and to the Detectors, its saved cheap checks) | 0.1 |
| Exchange Online: a shared mailbox to send from, a test mailbox, and access scoped by [Exchange RBAC for Applications](https://learn.microsoft.com/exchange/permissions-exo/application-rbac) | An Exchange or Microsoft 365 administrator (Organization Management or Exchange Administrator); an Entra administrator for the app's permissions | Both mailboxes (the shared one named with "(AI)"), the role `Application Mail.Send` limited to the shared mailbox, and a mail-flow rule that rejects mail from it to any address off the allow-list. The sender app must hold no organisation-wide mail permission in Entra: the two kinds of grant add up. A changed grant takes 30 minutes to 2 hours to apply | 0.5 |
| Networks for the Operate profile: production, and a dev network for the pre-release `operate` environment | A network administrator | In each, in the Foundry region: a subnet for the Foundry agents, delegated to `Microsoft.App/environments` (at least /27, /24 recommended, used by one Foundry account only; [Learn](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks)); a second delegated subnet for the Function apps, which cannot share the agents' ([Learn](https://learn.microsoft.com/azure/azure-functions/flex-consumption-how-to#configure-virtual-network-integration)); a subnet for the private endpoints (nine in phase 1a, eleven by phase 3); links to the private DNS zones; and peering with the hub's network. A deployment runner inside the network is a decision | 1a.1 |
| Cost data for the estate | The estate owner (accountable for the estate's subscriptions) or the billing owner (holds the agreement) | One export, created once by the estate owner or the billing owner after slice 1a.1 has deployed the cost lake: the system holds only read roles in phase 1a, and creating an export is a write to the estate's scope. In week 0, name the creator and check their roles ([the firewalled lake](#choosing-the-first-estate)) | 1a.2 |
| Read roles on every scope of the first estate: Reader, Cost Management Reader, Monitoring Reader, and Log Analytics Reader where logs are read | The estate owner. For the cost setting: an enterprise administrator (Enterprise Agreement, EA), a billing profile owner (Microsoft Customer Agreement, MCA) or, for a partner-sold subscription, the partner | The four assignments for the solution's read-only identities and, in week 0, for the named person who reads the first month; and the agreement's cost visibility switched on ([Learn](https://learn.microsoft.com/azure/cost-management-billing/costs/assign-access-acm-data)). No write role in phase 1a | 0.0 (the named person), 1a.1 (the identities) |
| Licences: GitHub Enterprise Cloud for a private repository (Team has rulesets but no required reviewer on an environment, which the production release needs); Exchange Online, for the shared mailbox; Microsoft Entra ID P1, for the extra sign-in check that approvers face | The licence owner | Whether each is held ([GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments#required-reviewers), [Entra](https://learn.microsoft.com/entra/identity/conditional-access/overview#license-requirements)) | 0.1 (GitHub), 0.5 (Exchange), phase 2 (Entra) |
| Names for the roles of [the operating model](../design/09-delivery-and-operations.md#6-operating-model), the estate owner, and one person for each request above | The platform team lead | The names, with at least two people who can be paged and can pull or release a kill switch (a stop for all work, or one part) | 0.1 |

If a request cannot be granted, check C4 (mail) and check C13 (cost data) say what to do instead. For every other request there is no fallback: the slice that needs it waits.

## Decisions the adopting organisation makes

Each decision has a default, or is marked **required** because no default is safe. Write each one down in a pull request before the slice that needs it starts. A decision that shapes a request is needed in week 0.

| Decision | Default, or required | Who decides | Needed by |
|---|---|---|---|
| The first estate, its first workload and its level of access | **Required.** The next section says how to choose. How the access changes slices 1a.2 and 1a.5 is in [agreements and access](../design/14-agreements-and-access.md) | The FinOps lead, with the estate owner | Week 0 |
| The data boundary for estate data | **Required.** Global deployments may process data in any Azure region; Data Zone deployments keep it in one data zone, at about a fifth more per token on current models ([Learn](https://learn.microsoft.com/azure/foundry/foundry-models/concepts/deployment-types), [cost document](../design/10-cost-and-finops.md#what-the-numbers-say)). Global Standard suits public documents and synthetic data; for estate data choose it only on purpose and in writing | Security reviewers, with whoever keeps the organisation's data-protection records | Week 0 |
| The region | Sweden Central is the starting value, subject to the check under this table | The platform team lead, with the hub owner | Week 0 |
| The hub: the organisation's own, or a new one from the accelerator | **Required.** A new hub adds 2 to 3 person-weeks in slice 0.2 (a scenario parameter), and [the cost document](../design/10-cost-and-finops.md#what-the-numbers-say) prices a gateway of its own | The platform team lead, with the hub owner | Week 0 |
| The deployment runner for private deployments | **Required.** A small self-hosted runner inside the network, or GitHub larger runners with [Azure private networking](https://docs.github.com/en/organizations/managing-organization-settings/about-azure-private-networking-for-github-hosted-runners-in-your-organization). A runner on the public internet, such as a standard GitHub-hosted one, cannot deploy to the private Foundry endpoint ([Learn](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks)) | The platform team lead, with the network administrator | Week 0 |
| For each funded stage (week-0 feasibility, foundations, the learning demonstration, the first workload): a named owner, a spending cap and its review point; also the daily cap on model spend and the thresholds of the solution's budgets and alerts | **Required.** Parameters in the repository; the system cannot raise them ([design 07](../design/07-safeguards-and-drift.md#3-stopping-the-system)). A funded stage stops at its cap and goes to its review ([the reviews](04-cost-effort-and-risks.md#the-three-reviews)); foundations is reviewed at the phase 0 exit. Start from the modelled lines of [the cost document](../design/10-cost-and-finops.md#how-to-read-the-numbers) | The FinOps lead, with the platform team lead | Week 0 (caps and review points), 0.1 (budgets), 0.6 (daily cap) |
| An always-ready instance for the Function apps that run Durable Functions | One, as [the cost model](../design/10-cost-and-finops.md#what-the-numbers-say) counts it. A pilot can set none and accept cold starts, a slow first call after idle time | The platform team lead | 0.4 |
| The language of the Monday digest (the weekly e-mail to the FinOps lead) | English, the language of the first message catalog ([language](../experience/11-access-language-inclusion.md#language)). Any other needs its own catalog. One language in phase 1a, checked by a native speaker before it goes live | The FinOps lead | 0.5 |
| The pilot release gate (check C11) | **Required**, before the first production release. [The first checks](03-first-checks.md#the-checks) give a recommended default and the alternative | Security reviewers and Atlas reviewers, who merge the change | 1a.1 |
| The organisation's own records for production estate data: AI Act classification, data-protection impact assessment, lawful basis and the data boundary above | **Required.** They are the organisation's own records ([compliance mapping](../design/06-security-and-governance.md#11-compliance-mapping)) | The people who keep those records, with security reviewers | Before 1a.1 reads production data |
| How many confirmed findings that count end phase 1a ([the finding record](#what-is-recorded-for-each-finding)) and the margin for check C8 (how far measured cost may differ from the cost model; starting value 30 %) | **Required.** The FinOps lead proposes the number and the margin for `evaluation/` by pull request before 1a.6a starts. A starting value for the number: five to ten findings | The FinOps lead | 1a.6a |
| Whether to use Teams | No default; not needed before phase 2. Without Teams, e-mail and the web page (built in phase 2) carry everything | The platform team lead, with the Microsoft 365 administrator | Before phase 2 |

**The region check.** Learn flags Sweden Central, like West Europe, North Europe and Germany West Central, as in high demand for new AI Search services ([Learn](https://learn.microsoft.com/azure/search/search-region-support)). In week 0, before any quota request, the platform team checks by hand that the portal offers a Basic search service in the region and that hosted agents, Flex Consumption and both model families are available there; if not, it picks a region where all work. The pre-flight job (a pipeline step that checks region, quota and capacity before anything is deployed; [design 09](../design/09-delivery-and-operations.md#2-infrastructure-as-code)) repeats the checks from slice 0.2.

## Choosing the first estate

An estate is the set of Azure scopes (such as subscriptions and resource groups) that the system reads. Choose the first one against these points:

- **Owners who answer.** From phase 2 the system asks them.
- **A FinOps lead who reads the digest every week** and confirms the findings that end phase 1a.
- **Enough spend for findings to matter, and a size a first Case can read:** the Pilot scenario of [the cost document](../design/10-cost-and-finops.md#how-to-read-the-numbers), five subscriptions and about 500 resources, is a guide.
- **A first workload** inside it: a group of resources that serve one purpose for one team, with spend large enough for a finding to matter ([the first-workload milestone](01-the-slices.md#phase-1a-first-value-on-one-estate)).
- **A bill per resource** (check C13, and the table below).
- **A stated access level.** Cost Management access on a subscription is enough to start. Billing-level roles add prices and purchase paths ([design 14](../design/14-agreements-and-access.md#3-cost-reach-and-resource-reach)). Without cost access the estate cannot pass the [exit of phase 1a](01-the-slices.md#phase-1a-first-value-on-one-estate).
- **No change freeze in the first months**, so that a finding can be acted on.
- **Not the solution's own dev subscription** (synthetic data, no role on production).

The exit of phase 1a includes explained spend, the share of the bill tied to an owner, a purpose and a billing mechanism. Measuring it needs a bill per resource, which only the first three paths below give.

| Path, tried in this order | Works for | A bill per resource? |
|---|---|---|
| Export in FOCUS, the FinOps Foundation's open cost format | EA and MCA, direct or through a partner, at billing, subscription or resource group scope | Yes |
| [Cost Details API](https://learn.microsoft.com/azure/cost-management-billing/automate/get-small-usage-datasets-on-demand) | EA and MCA, not management groups | Yes: one month a report, up to 13 months back (thirteen monthly calls seed the history); refresh the open month at most daily, respecting Retry-After |
| An export of another dataset where one is available, else the [Usage Details API](https://learn.microsoft.com/azure/cost-management-billing/automate/get-usage-details-legacy-customer) (legacy; retirement planned, no date set) | Pay-as-you-go, MSDN, Visual Studio | Yes |
| Query API | Every supported agreement | No: totals only, with two group-bys, throttled |
| None | No cost access: resource roles only | No: list prices only |

An export needs [Cost Management Contributor](https://learn.microsoft.com/azure/cost-management-billing/costs/understand-work-scopes#roles-used-in-cost-management-on-rbac-scopes), Contributor or Owner on the subscription, or a billing role at billing scope, and is created once by the estate or billing owner, after slice 1a.1 has deployed the cost lake. The other paths need only Cost Management Reader. Pay-as-you-go subscriptions cannot export in FOCUS, so columns mapped to the same layout fill the cost lake there. Under a partner agreement the partner must first switch cost visibility on for the customer's tenant; it is off by default. [Agreements and access](../design/14-agreements-and-access.md#cost-data-paths) has the full table with its sources.

**A closed month.** A billing period counts as closed from the sixth day after it ends (under an Enterprise Agreement it is the calendar month): Azure closes it typically up to 72 hours later, and usage charges can change until the fifth day ([Learn](https://learn.microsoft.com/azure/cost-management-billing/costs/understand-cost-mgt-data#cost-and-usage-data-updates-and-retention)). Compare the lines' total with Cost Management's for the same dates or, where the Cost Details API accepts one, the same billing period (Enterprise Agreement) or invoice (Microsoft Customer Agreement, at a billing profile or customer scope) ([Learn](https://learn.microsoft.com/rest/api/cost-management/generate-cost-details-report/create-operation)).

**The firewalled lake.** The lake's storage account is behind a firewall, so during creation or a later change of the export, the creator also needs Owner on that account or a custom role with `Microsoft.Authorization/roleAssignments/write` and `Microsoft.Authorization/permissions/read`; the platform team grants it by time-boxed elevation. The account must allow trusted Azure services and have its copy scope set to From any storage account, which the template sets, and the estate must be in the solution's tenant, because Learn supports firewalled exports only within one tenant ([Learn](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-improved-exports)). If the solution's Deployment Stack blocks the creator's write on the account, the exception is a reviewed change to the stack's exclusions in `infra/`, released like any other and removed afterwards.

An estate that offers only the Query API, or no cost access, can still run Cases with labelled figures, but it cannot pass the exit. Choose another first estate, or state in writing that the pilot cannot pass.

Write down which agreements and levels of access the pilot covers, as a table of agreement by access. Check C5 compares what the system finds with the portal; every combination left out is recorded as unproven, never as passed.

## What is recorded for each finding

Each finding that the FinOps lead confirms gets one record in the ledger. The FinOps lead decides every field; the system proposes values and shows its evidence. A second person, the estate owner or anyone else who did not build the system, reads every finding that would count and agrees that its facts and price are right, that it is distinct, that it adds discovery or follow-through and that the opportunity justifies the effort.

| Field | What it says |
|---|---|
| **Distinct** | Whether the finding differs from every earlier one, or duplicates one, which is named. The same resource, mechanism and change count once |
| **Opportunity** | A range of money a month with its price basis (contracted, billed or list), the evidence level of the claim behind it and the Case that priced it. It is credible when the price rests on the bill or a price list, not a guess |
| **Effort** | What acting takes: low (one reversible setting, changed by the owner), medium (a change that needs a test or a window) or high (a project or a purchase) |
| **Adds** | *Discovery* when Azure's own advice (Advisor, Cost Management alerts and views) shows nothing like it; *follow-through* when that advice shows it and the finding adds the owner, a price on a named basis or the evidence that applies here; *nothing new* when it only restates that advice |

A finding counts toward the number that ends phase 1a only when the second reader agrees. All findings stay on record, so the share that counts is known. A confirmation says a finding is true and worth acting on; it is stored as a confirmation, never as an outcome, and it is never a claim of realised savings, which are verified only after a change and a bill that shows them.

## Who does what

The roles are those of [the operating model](../design/09-delivery-and-operations.md#6-operating-model). Name a person for each in week 0, except the five readers, who are named before slice 1a.7 starts.

| Who | What they do in phase 0 and phase 1a |
|---|---|
| Platform team | Builds and releases the system, and is on call in business hours on a rota the organisation sets. Can pull any kill switch, as can the FinOps lead and the security reviewers (by the runbook until the page exists in phase 3). Its lead is the design's platform owner |
| FinOps lead | The first user: reads the digest each week, confirms findings and decides each field of their record. Proposes the number of findings and the margin for check C8, and names the five readers of the digest |
| Security reviewers | Own `.github/` and the red-team results, and, with the platform owner, the hub contracts and the Action catalogue (empty until phase 3). With the Atlas reviewers, merge the change to the pilot release gate |
| Atlas reviewers | Merge Atlas and Detector pull requests and decide the right answers (gold labels) the system is scored against, including the cases and decoys of check C14. Own `evaluation/` and merge each pass-condition number written there |
| Estate owner | Deploys the onboarding module on the estate's scopes ([onboarding an estate](../design/09-delivery-and-operations.md#9-onboarding-an-estate)), grants the read roles, and reads the findings that would count |
| The people who answer the requests above | One named person for each administrator or owner in the first two tables: Azure, Entra, Exchange, network, billing, hub, GitHub, Foundry and licences |
| Five readers, and a native speaker of the digest's language | Read the digest cold before it goes live (slice 1a.7); named by the FinOps lead before 1a.7 starts |

## Working agreements and done

- **One main branch.** Work happens on short-lived branches and reaches main only by pull request. Every path has a code owner ([design 09](../design/09-delivery-and-operations.md#1-the-repository)).
- **The pipeline runs in this order:** lint and schema checks; the pre-flight job; the tests that call no model; Bicep what-if (a preview of what a deployment would change); secret scan and software bill of materials; deploy to dev; isolation and negative tests (proof that dev cannot reach prod and that forbidden calls fail); a subset of the evaluation ([design 09](../design/09-delivery-and-operations.md#3-pipelines-and-releases)).
- **Nothing reaches prod except from a tag with a release record,** one file that lists the exact version or hash of everything the release contains.
- **No secret lives in the repository or in a parameter file.**
- **Prompts, contracts, tool pins (the hub's stored fingerprints of tools) and templates are code.** They change by pull request and pass the same gates.

**A slice is done when**

1. its stage of each check passes (for a slice built in two passes, the stages that belong to that pass) and its evidence is stored ([how a check works](03-first-checks.md#how-a-check-works));
2. its tests run in the pipeline;
3. its cost line in the cost model matches what was deployed;
4. its operational steps are in a runbook (exact commands for operating it); and
5. the person it was shown to has accepted it.

In week 0 the platform team checks each prerequisite in the first table by hand, so a missing or wrong grant is found before its slice starts. The pre-flight job then gains the same access check, in the slice that first needs it.
