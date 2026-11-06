# The Watch investigates with agents in Foundry — a decision record

**Status: ordered by the owner on 2026-11-06 ("It must find it on its own", and "agents in Foundry are not an option"). Built, deployed and run once on the real estate on 2026-11-06 (the changelog says what it found); a claim below that no real run has shown says so.** This page records one decision: the Watch no longer finds waste with a fixed list of queries that a person wrote. Two agents in Microsoft Foundry find it, with generic read-only tools. It builds on [the first cases](02-first-cases.md) and leaves the approval loop of [the loop](04-the-loop.md) and [run as the approver](05-run-as-the-approver.md) as it is.

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
3. The Investigator runs with a budget of tool calls and seconds. It starts from what costs most and works down the cost by service, forms a hypothesis, measures, and ends with one JSON object: findings, each with resource handles, a basis (no usage, low usage, oversized, duplicated, unused feature, commitment that does not fit, other), a proposal (delete, change, investigate), the measurements that it rests on, a confidence and a sentence, and a list of what it looked at (`examined`). When a measurement has data for some resources of a type and none at all for others, it reports the others as one finding to investigate: an absent measurement is no proof of idleness by itself, but the difference is a reason for a person to look.
4. Code checks every finding (next section). Then the guards run for each resource: a lock, a keep tag, a resource that is too new, a group that a platform manages, an unreadable guard. A resource with a guard on is left out of the finding.
5. The Skeptic judges all surviving findings in one run. It is shown every resource that will become a case, with the evidence rows that code attached (the measurements that are not zero first, so that evidence against the claim is seen).
6. Code decides, as before: a finding is *proposed* only when no guard is on, the Skeptic agrees, the confidence is at least 0.7 and code confirmed at least one measurement that the finding rests on. A finding with no confirmed measurement, a confidence outside 0 to 1 (it counts as 0), a missing or doubled verdict of the Skeptic, or a resource that the Skeptic was not shown goes to a person, and the case says so. Each resource of a finding becomes one case, so the History, the notebook page and the letters work unchanged. The word *change* joins *delete*, *keep* and *investigate*.
7. A plan, and so an approval, exists only for waste that Meternaut planted itself. Every other proposal is a recommendation for a person. Nothing changes in Azure without a person ([rule 29](../../AGENTS.md)).

## What code checks

An agent's answer is data, as a model's answer always was ([rule 26](../../AGENTS.md)).

- Every number that an agent cites must equal the number that a tool returned in this run. An entry that differs is thrown away, and so is the claim that rests on it.
- A claim of *no usage* keeps only the resources whose cited measurement is zero in every measurement of that metric that a tool made in this run (a 30-day total of 2,900 followed by a one-day total of 0 does not make a resource idle).
- A handle that no tool gave is dropped. A finding with no verified handle is dropped.
- Money is computed by code from the cost lines. An agent never writes a figure, and a figure about money in its text is removed on a best-effort basis (a number with a currency word or sign, or a number with a period word in a sentence that talks about saving, cost or price); counts such as the number of resources with data are left alone.
- No resource name, tag, identifier or other text that somebody wrote about a resource ever enters a tool answer: a resource is a handle (`r1`, `r2`) with a meaning in this run only. A string in a tool answer has to pass a word check. A test feeds hostile names and tags to every tool, and a check against the real estate found none of 643 real names and tag values in any answer.
- Limits: a soft budget of 40 tool calls (the default, and the ceiling; the first real run used all of 24 and left much of the estate unlooked): a call beyond it is not run and the agent is told `budget-used-up`, and it has three more rounds to write its answer before the run fails and its findings are lost; the same is done to every call after 70% of the Investigator's time has passed, so that a run that is slowed down still ends with its answer; a hard limit of 420 seconds (ceiling 600) for the whole investigation, of which the Investigator gets what is left after a reserve of up to 120 seconds for the Skeptic, 8 findings, 60 resources in a finding, 60 cases in a run. The History says how many calls were refused, and whether the budget or the time was the cause.

## The History lines

The investigation writes three kinds of line in the form that [the first cases](02-first-cases.md) describe, and the cases that it opens end in `case.result` like every other case. [`tools/cases-check.py`](../../tools/cases-check.py) prints them in plain words after a run and fails the check when the investigation was meant to run and did not.

| `type` | When | Fields besides `v`, `ts`, `runId` and `requestId` |
|---|---|---|
| `investigation.started` | Both agents are ready and the Investigator is about to run | `investigator`, `skeptic` (the agent and its version), `modelInvestigator`, `modelSkeptic`, `maxCalls`, `maxSeconds` |
| `investigation.finding` | One line for each finding of the Investigator, with what the checks of code made of it | `finding`, `basis`, `proposal`, `confidence`, `claimed` (resources the agent listed), `handles` (left after the checks), `unknown`, `unproven`, `unmeasured` (no measurement of the finding was confirmed for them), `repeated`, `judgedLately`, `guarded`, `capped`, `shown` (how many the Skeptic was shown), `coveredCostUsd30d`, `verdict` (the Skeptic's), `kept`, `reason`, `note`, `summary` |
| `investigation.finished` | The investigation ends, well or badly | `ok`, `toolCalls`, `tokens`, `seconds`; when it ended well also `examined` (one phrase for each service or type that the Investigator looked at, with what it concluded or why it could not judge), `findingsKept`, `findingsDropped`, `cases`, `guarded`; when badly `note` |

The tokens of the investigation are on its own line. The `tokens` of `run.finished` count only what went through the gateway.

## The model path: the one exception to the gateway rule

Foundry agents call the models of their own resource directly. That does not pass the API Management gateway, so the access agreement's token limits and its usage records do not apply to them. The owner asked whether that is a Citadel architecture, and it is not. There are three ways to put the gateway in the path, and none of them fits the estate today:

| Option | What it needs | Verdict |
|---|---|---|
| **Agents call their own resource (built)** | Nothing more. No key. The guardrail, the traces, the role on the project and Defender for Cloud's AI protection apply | Used now, as a disclosed exception. The deployments' own quota is the token limit (the Investigator's deployment has 50 thousand tokens a minute, see [the rate of the model](#the-rate-of-the-model)) |
| **Foundry's API Management connection** | The gateway must be Standard v2 or Premium; Learn calls the connection preview, and the project's identity needs access at the gateway | Not possible: the gateway is the Developer tier |
| **Foundry's generic model-gateway connection** | An API key or an OAuth client secret stored in the connection | Possible, with one key in a place that the platform keeps. [Rule 23](../../AGENTS.md) says no key, and the owner decides |
| **Move the gateway to Standard v2** | A larger instance, at a price well above the 50 US dollar line | The owner's decision |

## Identity, network, guardrail, tracing

- **Roles.** The cases app's identities hold *Foundry User* on the project and nothing else on the new resource: the app may create the agents and run them. The identities are the user-assigned `id-meternaut-cases` and, once the app has one, its system-assigned identity, which takes over from it (see below). The app reads the estate with Reader and Cost Management Reader as before. The project's identity holds *Monitoring Metrics Publisher* on Application Insights, to send the agents' traces with Microsoft Entra ID.
- **Network.** The resource has no public access and one private endpoint. The template makes no private DNS zone, link or zone group; the landing zone's policy registered the endpoint in its three central zones ten minutes after it was made, and the app reached the project through it on the first run.
- **Guardrail.** Prompt Shields block attacks in user input and instructions hidden in tool results, on top of Microsoft's default content filter. Learn lists tool-result scanning as a preview feature, so the typed tool answers stay the first defence.
- **Tracing.** The project has an Application Insights connection with the project's managed identity and no key.

## The rate of the model

An agent that calls tools reads everything said so far again at every step, so the tokens of a run grow with the square of its steps and not with their number. The second real run (2026-11-06) stopped in its 12th step with HTTP 429 (`rate_limit_exceeded`) from a deployment of 20 thousand tokens a minute: eleven steps had read 65 thousand tokens in 52 seconds, with the input of a step growing from 2.9 to 7.9 thousand tokens, and 40 steps would take it to about 21 thousand each. The client had waited 1 to 4 seconds twice, which does not give the tokens of a minute back, and the run lost its findings. Four things changed, and none of them makes the agent less free:

- **The capacity.** The Investigator's deployment has 50 thousand tokens a minute (`agentCapacity` in [`models.json`](../../environment/models.json); the Skeptic reads one prompt and keeps 20). A capacity is a rate limit and not a charge: the models bill by token, so nothing is paid for it while no agent runs.
- **Patience.** A step of a run that the service answers with 429 or 503 is asked again up to six times, after 8 seconds (with jitter), then 16, then 30 at most, or as long as a Retry-After of up to 90 seconds says. The pauses stay inside the time of the run, a 429 comes before the model produced anything so the same input is sent again, and a note of the History says how often it happened.
- **Fewer steps.** The instructions tell the Investigator to ask for calls that do not depend on each other in one step, which lowers the number of steps and so the tokens that every step reads again.
- **An answer before the limit.** After 70% of its time the Investigator's tool calls are refused as if its budget were used up, so a run that is slow because of its model still ends with the answer that it has.

## The identity of the cases app

The owner prefers system-assigned identities, so the cases app moves from its user-assigned identity `id-meternaut-cases` to an identity of its own, in two steps ([the bootstrap page](../../environment/BOOTSTRAP.md) has the details). The first step adds the new identity next to the old one and changes no setting, so the app keeps running on the old identity. The template of the app gives the new identity every role that the old one has inside the project's resource group. The template of the Foundry resource gives it *Foundry User* on the project as soon as the app has it: the workflow reads the object id from the app and passes it as `casesSystemPrincipalId`, and the template gives no role while that is empty.

Between the steps a person with the owner's session gives the new identity what only a person can give: the reads that the old identity has outside the resource group (with `tools/access-requirements.py`) and the right to send letters from the shared mailbox (with `tools/exchange-setup.py`). Then the person waits for Azure and Exchange to apply them. The second step moves the settings to the new identity and takes the old one off the app. The old identity is removed after that, by a person and not by the workflow: `tools/access-requirements.py retire` finds its grants by its object id, so it runs while the identity still exists. One user-assigned identity stays, `id-meternaut-console-auth`: Microsoft documents the secretless sign-in of an App Service app only with that kind, the app registration of the console trusts it, and it holds no role.

## Not built, and not shown yet

- **The guardrail on the agents themselves.** The guardrail is on the two model deployments, which every model call of the agents passes. The agent definition can also carry `rai_config` with the name of a policy (it is in the REST reference of Foundry's agents), and that is where the tool-response scan of Prompt Shields (preview) would be attached. Meternaut does not set it yet: Learn does not say whether the value is the policy's name or its resource id, and a policy that does not exist is silently not applied. It is the next step once the first run shows that the agents work, and a red-team scan will show whether the shields fire.
- **Microsoft Agent 365.** It is generally available. A Foundry agent that is published appears in its registry, but the tenant needs a Microsoft 365 Copilot licence, enrolment in the Frontier preview and a global administrator who accepts the terms. A person with those rights does that; code cannot. Whether a guest user can hold them is not documented.
- **Evaluations.** Built-in evaluators for agents (task adherence, tool call accuracy, intent resolution) and red teaming are preview. A first week with the Investigator's traces is the next step.
- **Shown by the real runs (2026-11-06):** the agent calls, the version pins, the conversation and the function-call loop worked as written through the private endpoint, with the key `agent_reference` (the fallback to `agent` was not needed; it stays, because the documents differ), and the agents' traces reached Application Insights with the project's identity. A run that reached 70% of its time had its later tool calls refused as built, and its agent wrote the answer that it had (36 calls, 61,000 tokens, 289 seconds). **Not shown yet:** structured output, whether the guardrail's shields fire, and the repeat of a step after a 429 (the run after the fix did not get one). The REST reference names the agent in a response with `agent_reference` and the article on function calling with `agent`. The client sends `agent_reference` first, and if the first response is refused with an HTTP 400 or 422, whatever it says, it sends that one call again with `agent`, keeps the key that worked and says so in a note of the History.
- **Two runs at once** that create the same agent at the same moment are handled with a read after a conflict.

## What a person had to do once

The deploy identity's role-assignment condition lists the roles that it may give to a service principal. *Foundry User* had to be added to it, by a person with the owner's session, as the earlier additions were ([the bootstrap page](../../environment/BOOTSTRAP.md)). It was done on 2026-11-06 with one in-place update of the assignment, read back. Then the actions `foundry` and `cases` ran, and `cases-run` showed the first investigation in the History.

## Sources (Microsoft Learn, read on 2026-11-06)

[Quickstart: Create a prompt agent](https://learn.microsoft.com/azure/foundry/agents/quickstarts/prompt-agent), [Use function calling with Foundry agents](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/function-calling), [Bring your own model to Foundry Agent Service](https://learn.microsoft.com/azure/foundry/agents/how-to/ai-gateway), [Create a project for Microsoft Foundry](https://learn.microsoft.com/azure/foundry/how-to/create-projects), [Prompt shields content filtering](https://learn.microsoft.com/azure/ai-foundry/openai/concepts/content-filter-prompt-shields), [Set up tracing in Microsoft Foundry](https://learn.microsoft.com/azure/foundry/observability/how-to/trace-agent-setup).
