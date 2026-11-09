# AI security and governance: the controls of layers 1 and 4, and the checks that watch them

**Status, 2026-11-09: built, deployed from the owner's machine and read back in Azure.** What has not run or could not be read is in [the changelog](../../CHANGELOG.md) (the entry of 2026-11-09) and in the last read of `drift-check`: 17 of its 24 controls PASS, one FAIL that was a false alarm of the app's own check (fixed), and six UNKNOWN, each with its reason. The owner ordered the AI security as [rule 33](../../AGENTS.md): policies, guardrails, telemetry, drift checks that fail closed, Microsoft Entra Agent ID and Microsoft Agent 365, each with a read-only check, and each gap named with who can close it. A part is done when it has run in Azure and its result was read back ([rule 32](../../AGENTS.md)). The agent harness, the evaluations, the red team and the in-app half of the drift check are in [the proposal 11-agent-harness-and-evaluation.md](11-agent-harness-and-evaluation.md). The hand steps are in [the bootstrap page](../../environment/BOOTSTRAP.md#added-on-2026-11-08-for-the-ai-security-built-not-deployed).

## The four layers

The owner's word *Citadel* is the AI Citadel Blueprint of Microsoft: four layers. Its layer 1 reference implementation runs on classic API Management, which the owner ruled out in favour of Azure's separate AI Gateway service ([the decision record](08-ai-gateway.md)). So its patterns are adopted on that service, by hand, and the limits are said below.

| Layer | What it is here | Built by |
|---|---|---|
| L1 Governance hub | The AI Gateway: limits, content safety, an access list for each caller, telemetry, alerts, one workbook | This page |
| L2 Agent operations | The Foundry resource, its guardrail, its models; the harness, evaluations and red team | This page for the resource, proposal 11 for the rest |
| L3 Agent management | Microsoft Entra Agent ID and Microsoft Agent 365 | A read here, the rest in proposal 11 |
| L4 Security foundation | Azure Policy, roles, network exposure, Defender, the release that runs, the silence of a check | This page |

## What the landing zone already gives

Read on 2026-11-08 (read only, with the owner's own session). The landing zone assigns its guardrail sets for Cognitive Services and Open AI to the project's group, at the effect that only reports, and a policy that makes a diagnostic setting for the Foundry resource: it sends the audit category to the landing zone's central workspace. So nothing of that is assigned or made a second time, no exemption is made or asked for, and the checks read the compliance and report it. The group also sees six policy exemptions that exist above it; the first run of `drift-check` prints them and the owner accepts the ones he knows, in a repository variable, so that a new one is a finding. The Defender for Cloud plan AI is on for the subscription (prompt evidence on, model scanner off).

## The controls

Each row: what it is, where a person sees it, which check watches it (the ids of `tools/drift-check.py`, whose run prints PASS, FAIL or UNKNOWN for each), what it does not stop, and its status. A person who cannot see a thing where it is named here reports a defect.

| Control | Where a person sees it | Check | What it does not stop | Status |
|---|---|---|---|---|
| Token, request and cost limits per caller; content safety at Medium on each model | AI Gateway portal, the gateway's workspace; the gateway in the Azure portal | I-gateway-policies, I-gateway-models | A prompt that stays under the limits and the severity | Service: preview. Ran in Azure 2026-11-07 |
| Access list per caller, [one entry for each identity](../../environment/aigateway/contracts.json) | The workbook, panel Callers; the alert rule for a call outside the list | I-gateway-roles | The role covers every alias, so the aliases are what a caller is meant to call, not what Azure enforces | Hand-made pattern; the service has no such object |
| Telemetry exporter to the project's Application Insights, `payloadCapture` written as false | The workbook; the workspace tables OTelSpans and OTelLogs | I-telemetry | Nothing: it records. It sends no prompt and no answer, and the service redacts nothing if capture is ever turned on, so no parameter can turn it on | Service and OpenTelemetry ingestion: preview |
| Eight alert rules and one action group (e-mail to the budget's addresses) | Monitor, Alerts, rules `alert-meternaut-ai-*` | I-alerts | They tell 15 to 60 minutes after the fact. Their e-mail holds the rule's name, a count and a link, never a line of telemetry or a word of the estate | General availability |
| The workbook *Meternaut AI security* | Monitor, Workbooks | I-alerts | A person has to open it | General availability |
| Guardrail `meternaut-agents`, on every model deployment, with sixteen filters named one by one, each blocking: hate, sexual, violence and self-harm from the severity Medium, profanity, protected material and the Prompt Shields | Foundry portal, Guardrails; the deployments | I-guardrail, I-deployments | Agent-level guardrails, which Microsoft does not offer for models behind a gateway; an attack below what the filters detect | Deployment filter: generally available |
| The Foundry resource: no public access, no key, network rules deny, an identity | Foundry resource, Networking | I-foundry-flags | A person with the right to change it | General availability |
| Approved models only, models direct from Azure and not in preview: policy at the group, Audit first, then Deny | Policy, Compliance; Foundry portal, Operate, Compliance | I-policy-assignments, I-policy-compliance | A deployment already made is reported, not removed. The preview guardrail initiative is behind a switch and can only audit; it reads only the filters that the guardrail names itself, so the template names all sixteen | Policies: generally available; the initiative: preview |
| Model retirement watch: a notice at 180 days, a warning at 90, a failure at 30 | The summary of `drift-check` | I-model-lifecycle | A model that is retired early without notice | General availability |
| The project's connection to the gateway, with the project's own identity | Foundry portal, Admin, Connected resources | I-connection | Whether the Agent Service sends the right token is shown by its calls, not by the connection | Preview |
| No identity of Meternaut can change Azure; nothing public that was not accepted | Access control of the group; the resources | I-role-assignments, I-network | The approver's own rights ([rule 29](../../AGENTS.md)) | General availability |
| The Operator and the project's own identity hold Foundry User on the Foundry project, and no role at any scope above it that can change Azure or reaches the model deployments | Access control of the Foundry project, and of the scopes above it | I-operator-role, I-project-role | Foundry User also lets the Operator create, change and run the project's agents: no narrower built-in role reads them. The way back is to delete the assignment. The other identities are read at the group alone, for writes | General availability |
| Microsoft Agent 365 logging of the Foundry resource: flag true and status Enabled, read on the real resource 2026-11-08 | Microsoft 365 admin center, Agents (portal only) | I-agent-365 | Content: Agent 365 governs identity and registry. The licence, the Global Administrator's one-time consent and the registry's list are for a person to look at | General availability; set by the platform, written by nothing here |
| Entra Agent ID: an owner or a sponsor for each agent identity | Entra admin center, Agent identities | I-entra-agents (UNKNOWN until a reader holds a directory right) | A coerced owner | General availability |
| The console's app registration holds no secret and no certificate ([rule 23](../../AGENTS.md)) | Entra admin center, App registrations | I-entra-console (UNKNOWN until a reader holds a directory right) | A secret added between two runs | General availability |
| Defender for Cloud plan AI | Defender for Cloud, Environment settings | I-defender (UNKNOWN without Reader on the subscription) | Microsoft lists Sweden Central as not covered, so the plan does not say that this resource is | General availability |
| Foundry logs to a workspace | The resource's Diagnostic settings | I-diagnostics | Prompts and answers are not in the audit category | General availability |

## The release that runs

The action `cases` gives the app two settings, `BUILD_COMMIT` (the git commit of the run) and `PACKAGE_SHA256`, the SHA-256 of the app's own files: `function_app.py` and the Python and JSON files of the package `cases/`, line ends read alike, so a Windows checkout, a Linux checkout and the folder that the platform unpacked give one digest ([`tools/source-digest.py`](../../tools/source-digest.py); the app's own module makes the same one, and a test holds the two to each other). A digest of the zip would change with every run, so the zip is not the identity; the run's summary records two zip hashes beside it, that of the sources archive that the run sent to the Operator and that of the exact package that the Operator built and published. After the code is published and the app answers, the run writes the two values as tags of the app, which a reader of the group sees. `I-release` compares the tag with the commit of main: the same commit passes; another commit with the same digest passes (main changed nothing of the app); another digest fails (a merge was not deployed, or the app was changed outside the workflow); no tag is UNKNOWN. The in-app check (proposal 11, control `A-RELEASE`) computes the same digest over the files that run and holds it against `PACKAGE_SHA256`.

## Silence is a finding

An app that watches itself can be made to say that all is well, or to say nothing. So the check has a second half that does not rest on the app. `tools/drift-check.py` runs from a runner, as the Hub action `drift-check` (with the deploy identity) and as the workflow `drift.yml` (with a read-only identity that the owner makes once: step G4). It only reads: every call is a GET, plus two queries, and the tool refuses any other call before it is made. It reads the lines that the app's own daily check logs, so a check that stopped is `I-heartbeat`, and a control that the app reports failing is `I-inapp-results`. An alert rule says the same from Azure: no `drift.pass` or `drift.fail` line for 26 hours, evaluated hourly, told once when it begins and once when it ends. `drift.yml` has no timer until the identity exists; a timer would spend minutes of GitHub Actions that are limited ([rule 35](../../AGENTS.md)).

**The lines that the app logs.** The Functions host sends the app's log lines to Application Insights as traces, and the app has no telemetry library, so the lines are the telemetry. `harness.trip` and `harness.run`, then a space, then a compact JSON object of codes, counts and hashes, and no text of the estate. `drift.pass`, `drift.fail` or `drift.unknown`, then a space, then `{"control", "layer", "state", "detail", "readAt"}`, the shape of every result of both halves. The History's wrapper `meternaut_event {json}` with the same name as its type is read as well.

## What is checked before anything is made

Every part that needs a right or a provider that is missing stops its action first, before anything is changed, with a message that names the right, who gives it and where. `governance` needs *Resource Policy Contributor* on the group for the deploy identity (step G1) and four providers; `base` and `gateway-telemetry` need `Microsoft.Monitor` (G2, not registered in the pilot subscription on 2026-11-08); `gateway-telemetry` needs *Monitoring Metrics Publisher* for the gateway's identity on the data collection rule that the platform manages (G3). Every Hub run first reads that CI passed for its commit, so the Hub does not repeat the tests ([the bootstrap page](../../environment/BOOTSTRAP.md#added-on-2026-11-08-for-the-ai-security-built-not-deployed) says what it no longer does and why).

## What it costs

Read from the Azure Retail Prices API on 2026-11-08, in euro, for Sweden Central. Nothing here is near the 50 euro a month at which the owner decides.

| Part | Price | A month |
|---|---|---|
| Eight log alert rules, each evaluated every 15 minutes or less often | 0.4489 each | 3.59 (seven without the rule for the access list: 3.14) |
| The workbook, the action group's e-mail, the policy assignments | No meter | 0 |
| Gateway telemetry and the Foundry setting where the landing zone made none, into the workspace | First 5 GB a month free, then 2.6841 a GB. A few hundred megabytes at this volume | 0 |
| Retention of the two gateway tables, capped at 30 days, nothing archived | 31 days are included | 0 |
| Metrics of the OpenTelemetry ingestion into the managed Azure Monitor workspace | 0.1436 for ten million samples | Cents |
| The drift check: a runner (about two minutes of GitHub Actions) and the app's daily timer | | Cents |

About 3.6 euro a month, and the alert rules are the whole of it. The budget of the group warns at 80 percent. Microsoft Agent 365 licences are the tenant's own (a trial of 25).

## What is not built, and who can close it

- **Agent-level guardrails for models behind a gateway.** Microsoft does not support them (preview, and not for connected models). The deployment filter, the gateway's content safety and the app's harness stand in. Nobody here can close it; Microsoft can.
- **Defender for Cloud in Sweden Central.** The plan is on; Microsoft lists the region as not covered. On 2026-11-09 it mailed the owner an alert for a blocked jailbreak attempt. Moving the resources or accepting the gap is the owner's decision.
- **Purview data security for AI.** It does not support a network-isolated Foundry resource. Revisit when Microsoft does.
- **A policy for the AI Gateway resource.** No built-in policy targets it. The drift check reads the gateway's policies, models, roles and exporter instead.
- **Customer-managed keys.** The policy is built, with the kinds that it leaves out emptied so that the Foundry resource is judged, and it is off: keys need a key vault with purge protection, and the owner has not decided.
- **The Citadel Governance Hub itself.** It is classic API Management; its access objects for each use case, its usage ingestion and its chargeback are not adopted. The access list, the telemetry, the alerts and the workbook are the pattern on the separate service.
- **A timer for the independent check.** It waits for the read-only identity (G4).
- **Agent 365 beyond logging.** Frontier enrolment, consent and agent users are portal-only and a Global Administrator's; agent users are not available to prompt agents.
- **The Foundry resource's own data plane.** It is private, so the agents' definitions are read by the app's check, proposal 11.
