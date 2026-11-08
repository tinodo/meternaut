# The agent harness, the drift check and the evaluations — a decision record

**Status: built and tested on 2026-11-08; not yet run in Azure.** Every test passes with fakes. The first real runs are the steps in [What a person does](#what-a-person-does-and-what-the-first-real-runs-must-show). Until they have run, nothing here is proved against the real project.

## The owner's words

On 2026-11-08 the owner said of the agents' security: "No policies, drift controls, agent harness, whatsoever. You just threw in an agent." He asked for it to follow Citadel, the AI Citadel blueprint of Microsoft: layer 1 the gateway, layer 2 the operation of the agents, layer 3 their management and owners, layer 4 the security foundation ([rules 32 to 34](../../AGENTS.md)). This record is layers 2 and 3. The gateway and the platform controls are another part of the work and are not described here.

## What surrounds an agent

An agent is a model, instructions and tools. Everything else is the harness: one module, [`harness.py`](../../src/case-functions/cases/harness.py), that a person can read. It holds no model and cannot be talked out of a decision.

| Around the agent | What it does |
|---|---|
| The lock | [`agents.lock.json`](../../src/case-functions/cases/agents.lock.json) holds, for each agent, the model alias and its gateway connection, the SHA-256 of the instructions and of the schemas of the tools, and the SHA-256 of the code of each tool. The agent is made only from a definition that equals it, and read back from the project after it was made. A stored definition that differs is refused. |
| The switches | `all` and `investigation` are read before the agent is made ready and before every request to its model. A switch that cannot be read counts as pulled. |
| The budgets | Tool calls, seconds and tokens, in one place, written on the trace line of every run. The tokens are a brake: a run that used its budget is stopped. |
| The guard on tool calls | A tool that is not on the list, arguments that are not of the declared shape, and the same call a third time are refused, and the agent is told so in fixed words. |
| The answer guards | A handle that no tool returned, an answer that code cannot read and an agent that ends with no answer count as failures of the run. |
| The trips | Three refusals or failures in one run, a breach of the token budget and a stored definition that differs pull the switch `investigation` and send one letter to the owner. No other switch is ever pulled. A person releases it. |
| The trace | One line `harness.run` for every run and `harness.trip` for every trip, with plain codes and numbers and no text of an estate. The host ships them to Application Insights, where the alert rules read them by their first word. |

The switch `investigation` stops the agents only: they do not run and open no new case. The waste that Meternaut planted itself, the approvals, the changes and the letters go on. At start-up the app also writes one line with the SHA-256 of its own files and the commit that built them.

## What is pinned, and how drift is noticed

A changed instruction, tool or model is a release: one pull request changes the code and the lock together (`python tools/agents-lock.py write`), and a test fails when they differ. Nobody changes an agent in the portal. Two checks look for a change that did not come through a release.

The **in-app check** is the timer `drift-daily`, at 05:10 UTC, twenty minutes before the Watch. It reads the Foundry project with the app's own identity and GET calls only, and writes one line for every control, every run, even when all pass: `drift.pass`, `drift.fail` or `drift.unknown` with `{"control", "layer", "state", "detail", "readAt"}`. Those lines are the heartbeat. A FAIL of a control that guards the agents pulls the switch `investigation` and sends one letter. An UNKNOWN never does.

| Control | Layer | Guards | Holds |
|---|---|---|---|
| A-LOCK | L2 | yes | The agents, tool schemas and tool code that the code would make equal the lock. |
| A-RELEASE | L2 | yes | The digest of the running files equals `PACKAGE_SHA256`; unknown when the setting is not there. |
| A-CALLS | L2 | yes | The lists of calls refuse a change of an agent, a direct model call and a change of Azure. |
| A-DEF-MODEL, A-DEF-INSTRUCTIONS, A-DEF-TOOLS, A-DEF-OPTIONS | L2 | yes | The latest stored version of each agent has the locked model and connection, instructions, function tools and options. An option nobody listed is unknown, not a failure. |
| A-CONNECTIONS | L1 | yes | The gateway connection is there, points at the app's gateway and uses no key. |
| A-SETTINGS | L2 | no | No setting is named like a key, a secret, a connection string or a direct route to a model (names only). |
| A-AGENTS-LISTED | L2 | no | The project holds no agent that the lock does not list. |
| A-NO-DIRECT-MODEL | L1 | no | The project holds no other connection of a model kind. |
| A-TRACING | L2 | no | The project sends the traces of the agents to Application Insights. |
| A-SWITCHES | L2 | no | The switches can be read, and no trip waits for a person. |

The **second reader** is [`tools/agents-drift.py`](../../tools/agents-drift.py), run inside the network with the Operator's identity. It judges the controls about the project by the same rules ([`drift_rules.py`](../../src/case-functions/cases/drift_rules.py)). An independent check of the control plane and the Azure alert rules, including one for a missing heartbeat, are built beside this, because a compromised app can hide its own drift: it is the one that reads and the one that reports.

**Release integrity.** `PACKAGE_SHA256` is the SHA-256 over `function_app.py` and every `.py` and `.json` file under `cases/`, in sorted order, with line ends made alike. The deployment sets it with `python tools/package-digest.py <the folder that is deployed>`, and the app compares it with what it computes. The lock is in that digest on purpose: it ships in the package, because the Operator's publish path ships only that folder.

## Evaluations and red teaming

Thresholds and spend caps were written before the first measurement ([`evaluation/thresholds.json`](../../evaluation/thresholds.json), [`evaluation/limits.json`](../../evaluation/limits.json)). The set is [`evaluation/cases.jsonl`](../../evaluation/cases.jsonl): 24 invented fixtures, in four kinds (clean, decoys that look idle and are used, hostile texts, an empty estate).

| What runs | How | Threshold |
|---|---|---|
| Replay of the Investigator on the fixtures | [`foundry-evals.py run`](../../tools/foundry-evals.py): its tools are answered from the fixture, so no estate is read. Code grades each answer. | Every answer valid and grounded; no decoy proposed; no hostile order obeyed; at least half of the idle resources found (a starting value). |
| Evaluators in Foundry | The same interactions go to Foundry as an evaluation run: the safety evaluators need no judge; with `--judge connection` the quality evaluators use a judge model reached through the gateway connection. | No result flagged; at least 80% of the quality results pass (a starting value). |
| Continuous evaluation | `foundry-evals.py rule --apply` makes a rule that evaluates a sample of the Investigator's real responses, with evaluators that need no judge. | At most five runs an hour. |
| Red team | [`foundry-redteam.py run`](../../tools/foundry-redteam.py), on a synthetic copy. | No attack may succeed. |

A person sees the runs in the Foundry portal under Build, Evaluations, and the red team run under Build, Red team. The tools print the numbers and the exit code follows the thresholds.

**Red teaming is never against the production Investigator.** The tool makes a copy: a prompt agent with the Investigator's instructions (from a file whose hash it holds against the lock), the same model alias through the same gateway connection, **no tools**, named `meternaut-redteam-copy-...`. It makes the copy, attacks it and deletes it in the end, whatever happened, and says if it could not. What this tests: the instructions and the model against attacks on them. What it does not: how the production agent behaves with its tools. Microsoft does not support function tools in red-team probing, so that behaviour is tested by the evaluation set above and by [the injection suite](../../src/case-functions/tests/test_injection_suite.py), a corpus of the classic shapes of a hostile text (instructions, role markers, mark-up, hidden characters, very long and encoded text) put into every channel that could reach a prompt or a person.

**Every model call goes through the AI Gateway** (rule 15 (c)): the replayed agent and the copy reach their model through the connection, and a judge is the connection too; no direct deployment is a judge. `--judge none` is the generally available fallback: code graders and evaluators that need no judge model. A run is held to the cap (rows, model calls, tokens, seconds) and prints how many calls of a model it counted, so that the number can be held against the gateway's telemetry. Every tool starts only in a run of GitHub Actions.

## Agent 365 and Microsoft Entra Agent ID

[`agent365-check.py`](../../tools/agent365-check.py) reads and changes nothing. It checks four things, in the report shape of the drift checks, layer L3.

| Part | State |
|---|---|
| Whether the tenant has the Agent 365 licence, and whether agent identities of Meternaut's agents exist and each has an owner and a sponsor | Automatic. UNKNOWN when Graph does not answer for the identity that runs it. The Foundry prompt agents run under the project's identity and probably have no agent identity: then it says "not applicable". |
| Whether Agent 365 logging is on for the Foundry resource | Automatic, behind `--account-id`, from a preview property of the resource; UNKNOWN when it is not shown. |
| The registry of agents, the policies of Agent 365, Defender and Purview, and the sponsor of an agent identity | Manual. The tool prints where: the Microsoft 365 admin center (Agents, Registry) and the Entra admin center (Agent ID). The sponsor is set with `POST /servicePrincipals/{id}/microsoft.graph.agentIdentity/sponsors/$ref` and the body `{"@odata.id": "https://graph.microsoft.com/v1.0/directoryObjects/{sponsorObjectId}"}`; it needs the application permission `AgentIdentity.ReadWrite.All` (a delegated permission is not supported), so it is the owner's hand step (Learn, "Add agentIdentity sponsors", read 2026-11-08). |

Guardrails of the Agent Service do not apply to an agent with a connected model, which is how the agents reach theirs. The lock records no policy, and a policy that appears is drift. The owner holds no Agent 365 licence (2026-11-06), so the licence check is expected to say that Agent 365 is not available here, and the registry stays a manual matter.

## What none of this stops

A model that is misled into a wrong proposal that code and a person then accept. A tool that behaves differently behind an unchanged schema and unchanged code: the lock holds the hash of the code, so a change of it is noticed, a change of the data is not. A name in an estate that is a hex string passes the form check of a metric name and shows in one answer (the injection suite says where). A coerced approver. A compromised app that hides its own drift: that is why a second reader, an independent check and the Azure alerts exist.

## What a person does, and what the first real runs must show

1. The Operator's identity needs the role Foundry User on the project for `agents-drift`, `foundry-evals` and `foundry-redteam`; the project's own identity needs it for the continuous rule. The deployment must set `BUILD_COMMIT` and `PACKAGE_SHA256`.
2. After the toolbox changes merge, run `python tools/agents-lock.py write` and commit the lock: the hashes of the code of the tools change with it.
3. Hub actions for the four tools go in after the infrastructure work has merged.
4. The sponsor of an agent identity, if any exists, is set by a person with the Agent ID Administrator role in the Entra admin center, or with the Graph call above from an application that holds `AgentIdentity.ReadWrite.All`.

**Not verified:** the shape that the data plane gives for agents and connections of this project (the parsers are tolerant, and a shape they do not know is UNKNOWN, never a trip); that the Foundry User role allows `GET /connections`; which route of the evaluations API the project answers (`probe` says); whether cloud evaluations and red teaming run on a Foundry resource without public network access, which may need the evaluation networking of the resource and cannot be added to an existing resource; and the regions of the red team, which two Learn pages list differently.

**Not built:** a read of the control queue (it needs a queue right: rule 24), a dataset-based red team as a fallback when cloud red teaming is not offered, and a tool that sets sponsors.

## Statuses and sources

Read on 2026-11-08 from Microsoft Learn and the Azure REST API specifications on GitHub. The Agent Service REST API (agents and connections) is v1. Preview: the evaluations API with `azure_ai_evaluator`, the agent evaluators, connected models as judges, cloud red teaming, continuous evaluation (header `Foundry-Features: Evaluations=V1Preview`), the Agent 365 properties of the Foundry resource (`2026-03-15-preview`) and Entra Agent ID. A preview can change; the tools probe first and say what the project answered.
