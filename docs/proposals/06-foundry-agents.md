# The Watch investigates with agents in Foundry — a decision record

**Status: ordered by the owner on 2026-11-06 ("It must find it on its own", and "agents in Foundry are not an option"). Built and tested with fakes on a branch; not deployed when this page was written. A claim below that no real run has shown says so.** This page records one decision: the Watch no longer finds waste with a fixed list of queries that a person wrote. Two agents in Microsoft Foundry find it, with generic read-only tools. It builds on [the first cases](02-first-cases.md) and leaves the approval loop of [the loop](04-the-loop.md) and [run as the approver](05-run-as-the-approver.md) as it is.

## The problem

The first Watch had seven detectors, each a Resource Graph query for one kind of resource, and two prompts that judged a few typed facts. It found seven leads in an estate of 453 resources, four of them private endpoints of another project, and it could find nothing that a person had not written a query for first. The owner's order is the opposite: nobody tells the app what to look for.

The model account of the first environment also cannot hold agents. It was made with project management off, and Microsoft Learn says that setting cannot be changed after the resource exists ([Create a project for Microsoft Foundry](https://learn.microsoft.com/azure/foundry/how-to/create-projects)). It had no managed identity, no project and no agent, and its deployments used the default content filter only.

## The decision

1. **A new Foundry resource, next to the old one.** Project management on, a system-assigned identity, no public access, no keys, one private endpoint, one project (`meternaut`), the same two model deployments, and a guardrail with Prompt Shields. The old account stays and keeps serving the gateway. The template is [`environment/foundry/main.bicep`](../../environment/foundry/main.bicep); the workflow action is `foundry`.
2. **Two agents, as prompt agents in that project.** The *Investigator* has function tools that the app runs. The *Skeptic* has none and is another model. Their definitions are in [`cases/agents.py`](../../src/case-functions/cases/agents.py), and the app makes sure at the start of each investigation that the project holds the current version of each.
3. **Generic tools, no list of what to find.** The tools list resources, show cost by service and by resource, show the metrics that Azure offers for a type, measure one, show Advisor's cost items and the plans and features that Azure bills per resource or per use once they are switched on, and describe a resource ([`cases/toolbox.py`](../../src/case-functions/cases/toolbox.py)). No instruction, tool description or test fixture names a kind of resource, a metric or a threshold. A test scans the agents' file for such words, so that nobody can later tell an agent what to look for.
4. **The fixed detectors shrink.** When the investigation ran, only the waste that Meternaut planted itself still goes through the older Detective and Skeptic, because the approval loop needs it. When the investigation does not run, the older path runs for every lead, as before.

## The flow

1. The Watch starts as before (daily timer, or an event on the control hub).
2. The app makes sure that both agents exist in the project, with the current definition (one read when nothing changed).
3. The Investigator runs with a budget of tool calls and seconds. It starts from what costs most, forms a hypothesis, measures, and ends with one JSON object: findings, each with resource handles, a basis (idle, oversized, duplicated, unused feature, commitment that does not fit), a proposal (delete, change, investigate), the measurements that it rests on, a confidence and a sentence.
4. Code checks every finding (next section). Then the guards run for each resource: a lock, a keep tag, a resource that is too new, a group that a platform manages, an unreadable guard. A resource with a guard on is left out of the finding.
5. The Skeptic judges all surviving findings in one run, with the evidence rows that code attached.
6. Code decides, as before: a finding is *proposed* only when no guard is on, the Skeptic agrees and the confidence is at least 0.7. Each resource of a finding becomes one case, so the History, the notebook page and the letters work unchanged. The word *change* joins *delete*, *keep* and *investigate*.
7. A plan, and so an approval, exists only for waste that Meternaut planted itself. Every other proposal is a recommendation for a person. Nothing changes in Azure without a person ([rule 29](../../AGENTS.md)).

## What code checks

An agent's answer is data, as a model's answer always was ([rule 26](../../AGENTS.md)).

- Every number that an agent cites must equal the number that a tool returned in this run. An entry that differs is thrown away, and so is the claim that rests on it.
- A claim of *no usage* keeps only the resources whose cited measurement is zero.
- A handle that no tool gave is dropped. A finding with no verified handle is dropped.
- Money is computed by code from the cost lines. An agent never writes a figure, and a figure in its text is removed.
- No resource name, tag, identifier or other text that somebody wrote about a resource ever enters a tool answer: a resource is a handle (`r1`, `r2`) with a meaning in this run only. A string in a tool answer has to pass a word check. A test feeds hostile names and tags to every tool, and a check against the real estate found none of 643 real names and tag values in any answer.
- Limits: a soft budget of 24 tool calls (ceiling 40): a call beyond it is not run and the agent is told `budget-used-up`, and it has three more rounds to write its answer before the run fails and its findings are lost; a hard limit of 420 seconds (ceiling 600) for the whole investigation, of which the Investigator gets what is left after a reserve of up to 120 seconds for the Skeptic, 8 findings, 60 resources in a finding, 60 cases in a run. The History says how many calls were refused.

## The History lines

The investigation writes three kinds of line in the form that [the first cases](02-first-cases.md) describe, and the cases that it opens end in `case.result` like every other case. [`tools/cases-check.py`](../../tools/cases-check.py) prints them in plain words after a run and fails the check when the investigation was meant to run and did not.

| `type` | When | Fields besides `v`, `ts`, `runId` and `requestId` |
|---|---|---|
| `investigation.started` | Both agents are ready and the Investigator is about to run | `investigator`, `skeptic` (the agent and its version), `modelInvestigator`, `modelSkeptic`, `maxCalls`, `maxSeconds` |
| `investigation.finding` | One line for each finding of the Investigator, with what the checks of code made of it | `finding`, `basis`, `proposal`, `confidence`, `claimed` (resources the agent listed), `handles` (left after the checks), `unknown`, `unproven`, `repeated`, `judgedLately`, `guarded`, `capped`, `coveredCostUsd30d`, `verdict` (the Skeptic's), `kept`, `reason`, `summary` |
| `investigation.finished` | The investigation ends, well or badly | `ok`, `toolCalls`, `tokens`, `seconds`; when it ended well also `examined` (what the Investigator says it looked at), `findingsKept`, `findingsDropped`, `cases`, `guarded`; when badly `note` |

The tokens of the investigation are on its own line. The `tokens` of `run.finished` count only what went through the gateway.

## The model path: the one exception to the gateway rule

Foundry agents call the models of their own resource directly. That does not pass the API Management gateway, so the access agreement's token limits and its usage records do not apply to them. The owner asked whether that is a Citadel architecture, and it is not. There are three ways to put the gateway in the path, and none of them fits the estate today:

| Option | What it needs | Verdict |
|---|---|---|
| **Agents call their own resource (built)** | Nothing more. No key. The guardrail, the traces, the role on the project and Defender for Cloud's AI protection apply | Used now, as a disclosed exception. The deployments' own quota is the token limit |
| **Foundry's API Management connection** | The gateway must be Standard v2 or Premium; Learn calls the connection preview, and the project's identity needs access at the gateway | Not possible: the gateway is the Developer tier |
| **Foundry's generic model-gateway connection** | An API key or an OAuth client secret stored in the connection | Possible, with one key in a place that the platform keeps. [Rule 23](../../AGENTS.md) says no key, and the owner decides |
| **Move the gateway to Standard v2** | A larger instance, at a price well above the 50 US dollar line | The owner's decision |

## Identity, network, guardrail, tracing

- **Roles.** The cases app's identity holds *Foundry User* on the project and nothing else on the new resource: it may create the agents and run them. It reads the estate with Reader and Cost Management Reader as before. The project's identity holds *Monitoring Metrics Publisher* on Application Insights, to send the agents' traces with Microsoft Entra ID.
- **Network.** The resource has no public access and one private endpoint. The template makes no private DNS zone, link or zone group; the landing zone's policy registers the endpoint in its central zones. Whether the app's network sees that record is not yet shown: the first run reports it.
- **Guardrail.** Prompt Shields block attacks in user input and instructions hidden in tool results, on top of Microsoft's default content filter. Learn lists tool-result scanning as a preview feature, so the typed tool answers stay the first defence.
- **Tracing.** The project has an Application Insights connection with the project's managed identity and no key.

## Not built, and not shown yet

- **The guardrail on the agents themselves.** The guardrail is on the two model deployments, which every model call of the agents passes. The agent definition can also carry `rai_config` with the name of a policy (it is in the REST reference of Foundry's agents), and that is where the tool-response scan of Prompt Shields (preview) would be attached. Meternaut does not set it yet: Learn does not say whether the value is the policy's name or its resource id, and a policy that does not exist is silently not applied. It is the next step once the first run shows that the agents work, and a red-team scan will show whether the shields fire.
- **Microsoft Agent 365.** It is generally available. A Foundry agent that is published appears in its registry, but the tenant needs a Microsoft 365 Copilot licence, enrolment in the Frontier preview and a global administrator who accepts the terms. A person with those rights does that; code cannot. Whether a guest user can hold them is not documented.
- **Evaluations.** Built-in evaluators for agents (task adherence, tool call accuracy, intent resolution) and red teaming are preview. A first week with the Investigator's traces is the next step.
- **Not tried on the service:** the agent REST calls and their shapes (they were read on Learn and checked against the REST reference and its TypeSpec on 2026-11-06, which agree with the code), that the models are supported for agents in the region (the availability table says yes), structured output, and that the project's data plane answers through the private endpoint. The REST reference names the agent in a response with `agent_reference` and the article on function calling with `agent`. The client sends `agent_reference` first, and if the first response is refused with an HTTP 400 or 422, whatever it says, it sends that one call again with `agent`, keeps the key that worked and says so in a note of the History.
- **Two runs at once** that create the same agent at the same moment are handled with a read after a conflict.

## What a person has to do once

The deploy identity's role-assignment condition lists the roles that it may give to a service principal. *Foundry User* has to be added to it, by a person with the owner's session, as the earlier additions were ([the bootstrap page](../../environment/BOOTSTRAP.md)). Then the actions `foundry` and `cases` run, and `cases-run` shows the first investigation in the History.

## Sources (Microsoft Learn, read on 2026-11-06)

[Quickstart: Create a prompt agent](https://learn.microsoft.com/azure/foundry/agents/quickstarts/prompt-agent), [Use function calling with Foundry agents](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/function-calling), [Bring your own model to Foundry Agent Service](https://learn.microsoft.com/azure/foundry/agents/how-to/ai-gateway), [Create a project for Microsoft Foundry](https://learn.microsoft.com/azure/foundry/how-to/create-projects), [Prompt shields content filtering](https://learn.microsoft.com/azure/ai-foundry/openai/concepts/content-filter-prompt-shields), [Set up tracing in Microsoft Foundry](https://learn.microsoft.com/azure/foundry/observability/how-to/trace-agent-setup).
