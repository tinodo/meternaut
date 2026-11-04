# The first cases — a proposal

**Status: approved on 2026-11-04 (the owner: "GO"), built and deployed the same day, and waiting for the rights that are listed under "Hand steps". The changelog says what has been checked and what has not.** This page says what the first piece of Meternaut's own work is, what it reads, what it writes, who may do what, and what is checked. It follows slice 0.4 and 1a.5 of the [build plan](../build-plan/01-the-slices.md), cut down to the smallest part that shows the whole idea on real data, and it builds on the [first environment](01-first-environment.md): the gateway, the private model account and the usage recording. A review by a second model family read it on 2026-11-04 and its findings changed the design: a model sees no name from the estate, the blob rights are per container, and the limits are written down at the end of this page.

## What it is for

Meternaut's job is to find waste in an Azure estate, explain it to the person who owns it, and, after that person's OK, remove it. Nothing of that exists yet except the gateway that every model call passes through. The first cases build the first half of the loop, and only read:

1. Look at the pilot estate and list **leads**: resources that look like waste.
2. For the leads that cost most, let two model roles work on each one through the gateway: a **Detective** that states what the lead is, why it looks like waste and what to do, and a **Skeptic** that tries to break that claim.
3. Apply **guards** written in code (a lock, a keep tag, a resource that is too new) that a model cannot argue with.
4. Write every step to a **History**: what ran, what was found, what each model said, what it cost in tokens, and what was decided.

No Azure resource is changed, and nobody is messaged: the owner reads the History. The messages, the approval and the change come in the next slice, and they need what this slice proves first: that the readers, the gateway path, the roles and the History work on the real estate.

```mermaid
flowchart TB
    trigger["Daily timer, or one control event"] --> watch["Watch: detectors read Resource Graph and Advisor"]
    watch --> rank["Rank the leads by their cost lines and take the first three"]
    rank --> evidence["Evidence for one lead, computed by code"]
    evidence --> detective["Detective: a model, through the gateway"]
    detective --> guards["Guards, in code"]
    guards --> skeptic["Skeptic: a model, through the gateway"]
    skeptic --> verdict["Verdict: proposed, needs a person, or dropped"]
    verdict -->|next lead| evidence
    watch -.-> history["History: one event per step"]
    evidence -.-> history
    detective -.-> history
    skeptic -.-> history
    verdict -.-> history
```

## What the pilot estate offers

The first estate is the subscription that already holds Meternaut. What was read from it on 2026-11-04 decides the design.

| Fact | Consequence |
|---|---|
| The subscriptions are internal offers: no invoice exists. Cost Management still returns cost lines in US dollars for every subscription, per resource | The price basis of every figure is written as "Cost Management cost lines, not an invoice". A saving is checked against later cost lines, not against a bill |
| Cost Management limits the Query API by processing units: about one unit for each month of data queried | One query per subscription and day, for 30 days |
| Azure Advisor shows no cost recommendation in the pilot subscription, and a few in two platform subscriptions | Advisor is one source of leads, not the only one. Resource Graph finds more |
| Resource Graph finds four private endpoints in the pilot subscription whose connection is not approved. They belong to another project | The first real leads exist already. Meternaut reads them and never changes them: only resources that Meternaut itself made may be changed, in a later slice |
| The tenant has Exchange Online and Teams, and the owner is its administrator | The e-mail and Teams paths of the design are possible. Each needs an administrator's steps, so they are the next slice |
| The gateway always requires the access product's key; a token is an extra layer, not a replacement | The Watch reads the key from the gateway with its own identity at the start of a run, keeps it in memory and never logs it. It is the one remaining key, as in [rule 23 of AGENTS.md](../../AGENTS.md) |

## What is built

| Part | What it is | Identity and rights |
|---|---|---|
| A second function app on the Flex Consumption plan | Python 3.13. The only library is the Functions host library; every call is a plain HTTPS call. It shares the integration subnet, the storage account and the Event Hubs namespace of the usage recording, and has a plan, an identity and a package container of its own | A new user-assigned identity |
| `watch-daily` | A timer function, every day at 05:30 UTC | Runs the Watch |
| `cases-control` | An Event Hubs trigger on a new hub, `cases-control`. One event starts one Watch now; the deployment workflow sends it and reads the result from the telemetry. The event carries only the job name `watch` and a request id: it cannot choose a scope, a model, a budget or a detector | The workflow may send to that hub; the function reads it |
| The detectors | Resource Graph queries, one per kind of lead: private endpoint with no approved connection, unattached managed disk, public IP address attached to nothing, Standard load balancer with no backend addresses (a lead from its configuration; nothing says that it carries no traffic), App Service plan with no app, stopped virtual machine that is not deallocated, and each Azure Advisor cost recommendation | **Reader** and **Cost Management Reader** on the pilot subscription. Neither reads a secret or changes anything |
| The History | One structured line per step in the function app's telemetry, kept for a year, and a workbook in the Azure portal that lists the runs, the findings and the steps, for all runs or for one | Read access to the Application Insights component |
| The model path | The Detective and the Skeptic call the gateway's chat route with the first access product, through the same route as the gateway test. They use two different models, so that the Skeptic is more independent of the Detective | A custom role that reads that one product subscription's key |

## What a model sees

A model never receives a name from the estate. The security design says it plainly: [prompts get ids, not names](../design/06-security-and-governance.md#7-data-protection-and-privacy), and a name, a tag or a description is the text that an attacker can write. So the prompt of the Detective and of the Skeptic holds only what code has built from fixed values:

- an opaque case id (`c1`, `c2`) and the name of the detector;
- the resource type, only when it is on the closed list of the types that the detectors and Advisor look for (otherwise `other`);
- typed facts, each a word from a closed list, a number, a flag or a list of those: a connection state, a SKU only when it is on a list of known values (otherwise `other`), a disk state, a size bucket, an age in whole days, a power state, and for a virtual machine the size family (`d`, `e`, `nc` and so on) from a list of known families (otherwise `other`) with the number in the size name, which is the number of vCPUs for most families. A fact that is anything else stops the case before a prompt is built;
- the guard flags: locked, keep tag, too new, in a managed group, and unverified (a guard could not be read);
- the 30-day cost, rounded, computed by code from the cost lines.

For an Advisor lead the prompt holds Advisor's category, its impact and its recommendation type id, and no free text. A model's answer is checked against a fixed schema; each string is cut to 300 characters, stripped of control characters and links. A test plants a hostile name and a hostile tag in the estate data and fails if either one appears in any prompt. The History is written by code and does carry the resource id, name and group, for the person who reads it: they are never sent back to a model.

## The History

Each line of the telemetry is `meternaut_event ` and one compact JSON object. The workbook parses it. A line never holds a secret, a key, a token or an e-mail address, and the text that comes from a model is shortened and stripped of control characters.

| `type` | When | Fields besides `v`, `ts`, `runId` and `requestId` |
|---|---|---|
| `run.started` | A run begins | `trigger` (timer or control), `scopes`, `detectors` |
| `run.note` | Something did not work but the run goes on: a detector or a subscription that could not be read, cost lines that were not available | `note` |
| `lead.found` | A detector returns a lead | `leadId`, `detector`, `resourceId`, `resourceType`, `resourceName`, `resourceGroup`, `costUsd30d`, `rank` |
| `case.started` | A lead is taken up | `caseId`, `leadId` |
| `case.step` | One step of a case ends | `caseId`, `step` (evidence, detective, guards, skeptic), `model`, `promptTokens`, `completionTokens`, `ms`, `ok`, `note` |
| `case.result` | A case ends | `caseId`, `leadId`, `detector`, `resourceName`, `resourceType`, `resourceGroup`, `costUsd30d`, `status` (proposed, needs_human, dropped, error), `recommendation`, `confidence`, `monthlySavingUsd`, `summary`, `objections`, `guards` |
| `run.finished` | The run ends | `ok`, `leads`, `cases`, `proposed`, `needsHuman`, `dropped`, `errors`, `tokens`, `seconds` |
| `run.failed` | The run cannot continue | `reason` |

A figure that a person could read as money (`costUsd30d`, `monthlySavingUsd`) is computed by code from the cost lines. A model never supplies one: its output is checked against a fixed schema, and a number that it adds is dropped.

## Safety

- **Read only.** The identity has Reader and Cost Management Reader and nothing that writes. The function app has no write call to Azure in its code, and a test fails the build if one appears. Its HTTP client holds a list of the calls that the app may make (the reads, two queries, the key and the chat route) and refuses any other method or address before the call leaves the app; a test tries writes, deletions, lock changes and calls to other hosts.
- **Text from the estate never reaches a model** (see "What a model sees"). A hostile name or tag can therefore not steer a model, and the History, which does show names, is written by code.
- **The model does not decide alone.** A guard in code turns any result into "needs a person" when the resource has a lock, a tag that says to keep it, is younger than seven days, or sits in a group that a platform manages. The model's output cannot lift a guard. A lock is looked for twice: in the list of all locks of the subscription (which returns the locks at, above and below its scope), and, for each case, in the lists of the case's own scopes, the resource and its group, with the filter that returns the locks at or above a scope. A list that cannot be read makes the case `unverified`, and that is a guard too.
- **A budget per run.** The limits are ceilings in the code: at most three cases per run, 2,000 completion tokens for each call, at most 6,000 characters of case in a prompt, at most 40,000 tokens for the whole run, and 15 minutes. A setting of the app can lower a ceiling and never raise it, and the template caps the number of cases at three. Before every case and every call the run adds the tokens already used, the cap of the call and a reserve for its prompt, and when that is more than the budget it stops and says so in a note. The 15 minutes hold for the whole run, calls included: no call starts after the deadline, no timeout reaches past it and no pause is taken that would end after it. The gateway's own limits (a rate per minute and an allowance per month) apply on top.
- **Retries only where they are safe.** A model call is repeated, at most twice, only when the gateway says "not now" (429 or 503), and a wait of more than a minute is a refusal, not a wait. A model call whose answer did not arrive (a network error, 500, 502, 504) is not repeated, because it may have been carried out and paid for already: it ends that case with the status `error`. Any other refusal by the gateway ends that case the same way, and nothing is retried in a loop. A read of the estate is repeated at most twice, with a pause, for network errors, throttling and server errors.
- **A control event cannot widen a run.** It names the job `watch` and a request id and nothing else. An event that is older than 15 minutes, or names another job, is refused and recorded.
- **No key stored.** The only key is the access product's, read at the start of a run with the identity, held in memory, never logged, and read again once if the gateway answers 401. A test scans every log line and every History line of a full run, including a failing one, for the key.
- **Storage rights per container.** The identity may write to its own package container and to the three containers that every Functions host of the account shares (host locks, host secrets, Event Hubs checkpoints). It has no right on the container that holds the usage recording's code, so it cannot read or replace that code.

## Hand steps

Anything outside a workflow is break-glass: it needs the owner's written word and is reported at once ([rule 18 of AGENTS.md](../../AGENTS.md)). Three are needed, and only the first two are done by hand; each is done once.

1. **Reader and Cost Management Reader** for the new identity on the pilot subscription. The deployment workflow's identity has no right there and must not get one.
2. **A custom role** with one action, `Microsoft.ApiManagement/service/subscriptions/listSecrets/action` (and read of the subscription), assigned to the new identity on the one gateway subscription of the first access product, and on nothing else. The role is defined once in the gateway's subscription.
3. The monthly token allowance of the first access product is raised from 500,000 to 2,000,000. It is a number in the repository, applied by the workflow action that adds the access product to the gateway; no hand step.

The allowance and the standing limit: [rule 15(g)](../../AGENTS.md) allows 25 EUR of model calls in total and 5 EUR a day. At the output price of the dearer of the two models (10.56 EUR for a million tokens, DataZone Standard, from the price snapshot) the whole allowance costs at most 21 EUR, even if every token were an output token. A test holds that.

## Price

About zero a month more. The function app stays inside the Flex Consumption free grant, the storage account, the namespace and the private endpoints already exist, a year of retention for a few megabytes of events costs cents, and the tokens are small: a run is capped at 40,000 tokens, which is at most about 0.42 EUR even if every token were an output token of the dearer model, and a typical run (six calls, about 5,000 tokens) costs a few cents. The model calls show in the usage records like any other call.

## What proves it

| Check | Shown by |
|---|---|
| The detectors return the four known leads and nothing that is managed by a platform | Unit tests against recorded Resource Graph answers; the first control run |
| A figure is never a model's | A test that feeds a model answer with invented numbers and finds them dropped |
| No text from the estate reaches a model | A test that plants a hostile name and tag in the estate data and scans every prompt |
| A guard wins | Tests for each guard with a model that says "delete" |
| The key is not logged | A test that scans every log line and History line of a full run, a failing one included |
| Every limit holds | Tests for the ceilings of the settings, the cases per run, the tokens per run (inside a case and across cases), the deadline (before the first call, during the read and between cases), the retry rules, the stale control event and the refusal by the gateway |
| The path works on the real services | A control run reads the estate, takes three leads through both roles, and the History holds the whole run |
| The gateway recorded the calls | The usage recording shows the new calls under the first access product |
| The History is readable | The workbook's queries return the run, its leads and its steps, for all runs and for one |

## Known limits

Written down so that nobody has to find them.

- **Reader is the built-in role on the whole pilot subscription.** It reads names, tags and properties of every resource there, more than the seven detectors need. A custom role that lists only the needed read actions is the next tightening; it is one more role definition outside a workflow, so it waits until the list of detectors is stable.
- **The two apps share three host containers.** Both Functions hosts of the account write locks, host secrets and checkpoints to the same three containers, so each app could disturb the other's host state. Neither can reach the other's code. A storage account of its own for the cases would add three private endpoints to the price, so it is not done.
- **The control hub trusts its senders.** Whoever holds the Event Hubs Data Sender role on that hub, or above it, can start a Watch. A Watch is read only and capped, so the worst case is extra tokens, but the workflow does not check who else holds that role.
- **No durable run record.** A timer run and a control run can overlap, and a restart in the middle of a run loses the rest of that run; the next run starts again. Both only read.
- **No daily token ledger.** The gateway limits tokens per minute and per month, not per day. The run cap is what keeps a day under 5 EUR: more than about twelve worst-case runs in one day would not. Runs are started by the workflow on the owner's word, so that cannot happen by accident.
- **Tokens of a lost call are not counted by the run.** A model call that the gateway carried out but whose answer did not arrive costs tokens that the run's own total does not hold. The gateway's allowance does count them, and the run is not repeated.
- **The lock filter is documented, not yet seen at work.** Azure PowerShell documents `atScope()` as "all locks at or above the specified scope"; the pilot subscription has no lock at all, so the first lock that exists there is the first proof. A list that cannot be read stops the case as `unverified` in the meantime.
- **Cost lines, not invoices.** A figure is the resource's cost lines of the last 30 days, and the saving if it is removed is that figure (Advisor's own figure for an Advisor lead). It is an estimate. Cost Management throttles its Query API: one 30-day query is about one processing unit, and a throttled answer is waited for at most 60 seconds, then the run goes on without cost lines and says so.

## Not built, and next

The Teams card and the e-mail to the owner of a resource, the approval, the one writer that makes a change, the check against later cost lines, and the agents' move into the Foundry Agent Service as hosted agents. The next slice takes a resource that Meternaut made for the purpose (an unattached disk and a public address in the project's own group, tagged as planted waste) through the whole loop, including a person's OK and the removal, because no other project's resource may be changed. It needs the owner's administrator steps for the shared mailbox and the Teams app.
