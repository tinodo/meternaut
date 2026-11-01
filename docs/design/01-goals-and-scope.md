# Goals and scope

**What this document answers.** What the system is for and how we will know it works; who it serves; what is in and out of scope; where it sits next to Azure's own cost tools; what an organisation needs before it can run it.

## 1. The problem

Cost advice is written by people, and people do not scale. Azure has hundreds of services, thousands of ways to be charged and weekly changes, so every rule covers the well-known head and goes stale the day it is written. Context decides: the same setting is waste in one estate and the reason the quarter-close works in another. And owners act on advice they can inspect and argue with, not on a list they never open.

So the scarce thing is not detection. It is *knowledge*: how each service really charges, what really drives this bill, what a change really does, and what is really needed here. The system exists to produce and keep that knowledge, and to turn it into decisions that people make and changes that are safe.

## 2. Goals and how we measure them

| Goal | Measure | Should |
|---|---|---|
| Explain the bill | Share of spend whose purpose, need and cost-to-reduce the system can state with confidence | Rise |
| Find what no rule describes | Rediscovery of known waste with no rule written for it; time to profile a new service or price change | Rise; fall |
| Get owners to decide | Minutes of a person's attention per decision; cases waiting on an answer | Fall |
| Act safely | Changes without a bound approval or a valid credential; reversed changes ("boomerangs"); regret | Zero; fall |
| Be trustworthy | Calibration (when it says 80 %, is it right 80 % of the time); refuted beliefs kept and visible | Tighten |
| Pay for itself | Verified net savings after the system's own cost; share of managed spend needed to break even ([cost](10-cost-and-finops.md)) | Rise; stay small |
| Stay open | Share of world knowledge (Atlas, Action catalogue) that is open source; estate knowledge never leaves the organisation | Rise; stays 0 |

## 3. Who it serves

| Role | What they do | What they get |
|---|---|---|
| Resource owner | Decides on recommendations; teaches the system | One short, explained question instead of a list; changes made for them |
| FinOps lead | Sets credentials and attention budgets (messages a week, quiet hours); approves commitments with a second person | Verified savings, a report card, a weekly digest of what was learned |
| Platform owner | Runs the platform; holds the kill switches; opts scopes in | A system that can be stopped, audited and upgraded |
| Atlas reviewer | Reviews proposed changes to shared knowledge | Small, evidenced pull requests |
| Security reviewer | Reviews contracts, roles and the action catalogue | A complete audit trail and tested safeguards |
| Second approver | A budget holder or finance partner for purchases | A bound plan and a quote, not a story |

## 4. Scope

| In scope | Out of scope (and why) |
|---|---|
| Reading cost, usage, inventory, configuration, Advisor and Cost Management signals | **Deploying resources to learn.** There is no lab: it costs real money and needs its own governance. Learning comes from documents, price lists, bills, replays, owners' answers and small approved trials: one reversible change to a resource an owner already runs, never a resource created to be tested |
| Studying how Azure charges and keeping that knowledge tested and current | Training or fine-tuning models in phase 1 |
| Investigating, challenging, quantifying and recommending | Operating for several organisations from one deployment (single-tenant) |
| Asking and teaching people in Teams, email and a small web page | A custom portal beyond the approval and lesson page and Workbooks |
| Changing resources from a versioned Action catalogue, after a bound approval or inside a human-written credential | Changing anything without a bound approval or valid credential |
| Commitment purchases, prepared by the AI, approved by two named people with different roles, executed by the AI | Chat as the product: conversation is one way to talk to the system, not what it is |
| Learning, evaluation and drift control as part of the system | Other clouds |

Fabric and Databricks are not ruled out: they are judged on merit and are **not needed in phase 1**; [the technology register](11-technology-register.md) says when they would earn a place.

## 5. Where it fits

It reads what Azure already offers, treats it as leads and as a baseline to beat, and covers what those tools cannot.

| Offering | What it does well | What it leaves open | How this system uses it |
|---|---|---|---|
| [Azure Advisor](https://learn.microsoft.com/azure/advisor/advisor-cost-recommendations) | Rule-based cost recommendations in the portal | Savings are computed at retail rates and ignore discounts and commitment coverage; nobody is asked; nothing is changed | Recommendations become leads, checked like any claim; baseline for evaluation |
| [Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-improved-exports) | Reporting, budgets, anomaly alerts, exports | Budgets and alerts notify; they do not stop spend or explain it | Exports in the FOCUS cost format feed the cost lake, the system's store of bills and prices; alerts are Watch signals |
| [FinOps toolkit](https://learn.microsoft.com/cloud-computing/finops/toolkit/finops-toolkit-overview) and hubs | Open-source data foundation and reports | Reports, not decisions or actions | Reuse where an organisation has one (an adapter in phase 4); otherwise a lean lake |
| [Azure Copilot Optimization agent](https://learn.microsoft.com/azure/copilot/optimization-agent) (preview) | Explains and scripts optimisations in chat | Virtual machines and scale sets only, at most ten items per query, no budgets or alerts | A baseline in evaluation; its scripts never bypass the approval path |
| Azure MCP Server and cost MCP toolsets | Ready read tools for agents | Tool access is not authorisation; remote hosting is documented on Container Apps only | A candidate for generic reads, evaluated in proof point P9 ([roadmap](13-roadmap.md)); our own typed `estate-read` is the default |
| Azure Policy and Defender for Cloud | Governance and security posture | Not cost | Guard the platform itself |

## 6. Requirements

**What it must do.**

| # | Requirement |
|---|---|
| F1 | Build and maintain the Atlas: claims with sources, scope and evidence level, re-checked on a schedule |
| F2 | Build an Estate model per organisation: resources, purpose, rhythms, owners, constraints |
| F3 | Watch cost, usage and change on clocks that fit each signal (minutes for alerts and metrics, daily for bills, slower for prices and documents) and open Cases from leads |
| F4 | Investigate with hypotheses, challenge them independently, quantify options and consequences |
| F5 | Tell the right owner in plain words, with evidence, options and "do nothing"; every message offers three buttons: Explain (why), Challenge (I disagree) and Teach (here is what you missed) |
| F6 | Plan, approve, run and verify changes from the Action catalogue; roll back when a guard metric (a measure the change must not worsen) breaches |
| F7 | Prepare commitment purchases for two-person approval |
| F8 | Verify outcomes against registered predictions; keep a calibration record |
| F9 | Evaluate itself on change and in production; report what it is bad at |
| F10 | Share world knowledge as open source; never share estate knowledge |

**How well (targets are parameters of each adopter).**

| Quality | Target |
|---|---|
| Safety | No Azure change without a bound approval or valid credential; every change reversible or two-person |
| Auditability | Every recommendation, approval and action traceable to the facts, versions and people involved |
| Cost | Idle floor (the cost when nobody uses it) and per-case cost small enough that break-even is a small share of managed spend |
| Explainability | Every recommendation shows its evidence and how to check it |
| Privacy | Personal data minimised; ids, not names, in the audit log |
| Availability | Workflows resume after failure; nothing runs unapproved during an outage |
| Operability | Stoppable at three levels (everything, one Action, one estate); drift detected where it starts |
| Extensibility | New services learned through the Atlas; new Actions added by pull request |

## 7. What an organisation needs

| Need | For | Notes |
|---|---|---|
| Azure subscriptions and rights to deploy and assign roles | Deploying the platform; opting scopes in | Owner, or Contributor plus a role-assignment right |
| Read access to cost data at the scopes to manage | The cost lake | Cost Management Reader; [exports](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-improved-exports) depend on the agreement type and scope |
| A Citadel governance hub | Models and tools through one door | The organisation's own, or the accelerator deployed from this repository |
| Model quota in the chosen region | The model aliases | Quota is per subscription and tiered |
| Microsoft Entra ID | Sign-in, groups, agent identities | P1 for Conditional Access on approvers; P2 or Governance for PIM (optional) |
| Microsoft 365 (Teams, Exchange Online) | Cards and email | Fallback: the web page |
| A Git host (GitHub or Azure DevOps) | Atlas and Action pull requests | |
| People | Running and governing the system | A platform team that can run Azure Functions and Foundry; a FinOps lead; owners who answer cards; Atlas and security reviewers (section 3) |
| Optional: Microsoft Agent 365 or Microsoft 365 E7 licences | Conditional Access and governance for agent identities | The hub's JWT and RBAC are the baseline without it |

## 8. Scenarios used for sizing

Sizing uses three scenarios, Pilot, Team and Enterprise: 5, 50 and 1,000 subscriptions, and 20, 200 and 2,000 Cases a month that reach an owner. They are parameters, not forecasts; [cost and FinOps](10-cost-and-finops.md) gives all of them.

Next: [the architecture](02-architecture.md).
