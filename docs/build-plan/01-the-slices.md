# The slices

**What this document answers.** In what order phase 0 and phase 1a are built, as fifteen slices; what each ends with, waits for and costs in effort; and why it sits where it does.

## How a slice works

A slice is a piece of the build that ends in something shown to a named person, with evidence that is stored and, for most slices, checks. A check that spans slices has a stage in each, and a slice is done when its stage passes ([First checks](03-first-checks.md#the-checks)). A slice **starts after** the slices it needs, and its checks can need more ([What depends on what](#what-depends-on-what)). Every number in a pass condition is a **starting value**, written down before the measurement ([How a check works](03-first-checks.md#how-a-check-works)). [Working agreements and done](02-before-you-start.md#working-agreements-and-done) says when a slice is done.

```mermaid
stateDiagram-v2
    [*] --> Planned
    Planned --> Building: what it starts after exists
    Building --> Checked: its checks run
    Checked --> Building: a check failed
    Checked --> Shown: its stage of every check passed and the evidence is stored
    Shown --> Building: not accepted
    Shown --> Accepted: the person it was shown to accepts
    Accepted --> Revisited: a proof point changes a choice
    Revisited --> Building: the change is built
```

## Phase 0: foundations

Phase 0 builds the [Evaluate profile](../design/02-architecture.md#7-two-profiles-one-codebase) from code and one thin path from a synthetic lead to a test e-mail, on synthetic data only. **It ends when** proof points P1, P2 and P9 of [the roadmap](../design/13-roadmap.md#2-ten-proof-points) pass, a fresh deployment of dev from scratch works, and the isolation test passes (dev cannot reach prod), and a first kill-switch drill has run in dev (check C12).

| Slice | What exists at the end | Shown, with recorded evidence | Starts after | Checks | Person-weeks |
|---|---|---|---|---|---|
| [0.1 Repository](#01-repository-pipelines-and-gates) | Repository layout, code owners, CI, OpenID Connect to dev, budgets and anomaly alerts | A pull request blocked by a failing check | [A GitHub organisation, two subscriptions](02-before-you-start.md#what-the-adopting-organisation-provides) | None | 2 to 3 |
| [0.2 Hub path](#02-the-evaluate-profile-and-the-hub-path-from-code) | The Evaluate profile as Bicep; hub onboarding; the pre-flight job | A call through the hub works; a direct model call fails | 0.1, [a hub](02-before-you-start.md#what-the-adopting-organisation-provides) | C1 (first half) | 4 to 5 (6 to 8 with the accelerator) |
| [0.3 Tool and pins](#03-a-published-tool-its-pins-and-the-first-suite) | A stub `estate-read` tool with pins; the synthetic-estate generator; the suite harness | A changed tool is caught; the suite finds planted waste and ignores its decoy | 0.1, 0.2 | C3 (P9) | 4 to 5 |
| [0.4 Agent, workflow](#04-one-hosted-agent-one-workflow) | One minimal role; a Durable Functions workflow that calls it, waits and resumes | The call in hub logs; a one-hour wait that survives a host restart | 0.2, 0.3 | C1 (P1, second half), C2 (P2) | 3 to 4 |
| [0.5 Mail path](#05-the-mail-path) | A shared mailbox; a scoped Exchange role; the send step with an allow-list; an AI-marked template | A test e-mail arrives with its AI marks; a second mailbox is denied | 0.1, [administrators' grants](02-before-you-start.md#what-the-adopting-organisation-provides) | C4 (first part) | 2 to 3 |
| [0.6 Thin path](#06-the-thin-path-end-to-end-and-the-first-drill) | A synthetic lead goes from plain-code stand-ins for [Watch](../design/03-agents-and-workflows.md#4-seven-workflows), a Case and the Diplomat, through the workflow of 0.4, to a digest e-mail; a switch is pulled and released | The test e-mail; the drill's times; a dev identity that reaches nothing in prod | 0.4, 0.5 | C12 (first drill), isolation test | 3 to 4 |

### 0.1 Repository, pipelines and gates

The first infrastructure is budgets and anomaly alerts on the solution's own subscriptions, so cost is visible from the first deployment. **Why first:** every other slice needs a repository that enforces the rules. **Surprise:** a new subscription can need [up to 48 hours](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets) before Cost Management features work, so create both in week 0. **Read:** the [repository layout](../design/09-delivery-and-operations.md#1-the-repository).

### 0.2 The Evaluate profile and the hub path from code

The solution's Foundry account holds no model deployment of its own, and Azure Policy refuses one, so every model call goes through the hub. Each dev contract has a daily token quota from its first call, so a runaway test stops at the quota. **Why here:** the hub path is the riskiest part of the design, so it is proved before any agent exists. **Surprise:** an organisation without a hub deploys [the accelerator](https://github.com/Azure-Samples/ai-hub-gateway-solution-accelerator) at a pinned commit and overrides its loose defaults, which adds 2 to 3 person-weeks. **Read:** check C1 and [the hub and the landing zone](../design/02-architecture.md#6-the-landing-zone-and-the-hub).

### 0.3 A published tool, its pins and the first suite

The hub stores a pin for the stub tool: a fingerprint of its name, description, schema and server digest. The synthetic estate plants waste and decoys, harmless look-alikes that must stay quiet; the first suite scores a plain-code stand-in for the finder against them, which proves the harness before any role exists. **Why before 0.4:** no role is deployed before its suite passes, and no tool before its pins and a negative test. **Surprise:** whether the hub rejects a changed tool inline is [still unverified](../design/06-security-and-governance.md#2-what-can-go-wrong), so check C3 tests it and a scheduled probe catches the rest. **Read:** check C3.

### 0.4 One hosted agent, one workflow

A hosted agent runs the minimal role, and a Durable Functions workflow calls it. Both Durable storage backends run (the Azure Storage provider and the Durable Task Scheduler), and the choice follows measured price and recovery. **Why here:** it needs the hub path of 0.2 and the suite harness of 0.3. **Surprise:** Foundry hosted agents are generally available, but the Agent Framework's [Foundry hosting package is a prerelease](https://learn.microsoft.com/agent-framework/hosting/foundry-hosted-agent), so it sits behind a switch, with an adapter of our own around the generally available core as the tested fallback. **Read:** checks C1 and C2.

### 0.5 The mail path

In phase 1a this is the only way the system reaches people. **Why in parallel:** it needs only 0.1, but mailbox and permission requests can take weeks, so they go out in week 0. **Surprise:** grants in Exchange and in Entra [add up](https://learn.microsoft.com/exchange/permissions-exo/application-rbac), so one organisation-wide `Mail.Send` consent defeats the scope, and a changed grant takes 30 minutes to 2 hours to apply. Graph's [`sendMail`](https://learn.microsoft.com/graph/api/user-sendmail) returns 202 Accepted before delivery, so delivery is proved by receipt. **Read:** check C4.

### 0.6 The thin path end to end, and the first drill

The watch, the Case and the digest are stand-ins in plain code, written for this slice and replaced in 1a.5, 1a.6b and 1a.7; the minimal hosted role of 0.4 stands for the model call. In the drill, synthetic usage passes the daily spend cap, an automatic trip pulls the kill switch, and the runbook's commands release it in stages. **Why here:** that is the cheapest time to find that a part does not fit. **Surprise:** a switch that cannot be read counts as pulled, so a fault in the switch store stops the system by design. **Read:** check C12 and [stopping the system](../design/07-safeguards-and-drift.md#3-stopping-the-system).

## Phase 1a: first value on one estate

Phase 1a reads one real estate and only reports. **It ends when** proof points P4 and P7 (read paths) pass, explained spend (the share of the bill tied to an owner, a purpose and a billing mechanism) is measured, the system has made zero writes to the estate, and the FinOps lead has confirmed a number of findings, written down before work on the Cases starts, each priced on a named basis. Cost per Case and per confirmed finding are read from hub logs, dead ends included, with people's hours beside them. **The exit is reached only when that number is reached.** If it is not reached by the review date the adopting organisation sets, phase 1a stays open and the team decides what to change. The number is never lowered to fit a result; a new number applies only to work done after it is written.

**What a confirmation is:** the FinOps lead's judgement that a finding is true and worth acting on, with its price basis shown. It is not an owner's acceptance and not a verified saving (that needs a change and a bill that shows it).

| Slice | What exists at the end | Shown, with recorded evidence | Starts after | Checks | Person-weeks |
|---|---|---|---|---|---|
| [1a.1 Operate profile](#1a1-the-first-estate-access-and-the-operate-profile) | The first estate readable; the Operate profile in full from code, read roles only; switches and runbook; capability probes | A read works and a write fails on every scope; the pre-release report; the runbook used by two people | Phase 0, the organisation's [prerequisites](02-before-you-start.md#what-the-adopting-organisation-provides) | C5 (raw evidence), C11, C12 (second drill) | 5 to 6 |
| [1a.2 Cost lake](#1a2-the-cost-lake) | Bill lines by the best path each scope allows, in one layout with source and price basis; 13 months of history where the path allows; 93 days of metrics | A closed month matches Cost Management within a tolerance written down beforehand (a pipeline test) | 1a.1, a per-resource bill path ([check C13](03-first-checks.md#c13-the-first-estate-offers-a-per-resource-bill-path)) | C13 (before it starts), C6 | 4 to 6 |
| [1a.3 Estate model](#1a3-the-estate-model-and-its-refresh) | The [Surveyor](../design/03-agents-and-workflows.md#1-ten-roles-in-five-hosted-agents) and the Estate refresh workflow; stored profiles; owners as guesses; cost lines joined to resources | Ten sample resources resolve to candidate owners, which the estate owner checks; counts match Resource Graph; the first explained-spend figure | 1a.1 (the figure needs 1a.2) | C5 (stored profiles), C11 (Safety) | 4 to 5 |
| [1a.4 Atlas v0](#1a4-atlas-v0) | Claims with source, scope and evidence level for the five to ten services the estate has most of (a starting value) | An answer about one of those services that cites a claim | 0.2, 0.3, 1a.1 | None | 3 to 4 |
| [1a.5 Detectors](#1a5-watch-and-the-first-detectors) | The Watch workflow; ten to fifteen Detectors (a starting value), back-tested and run in shadow | A shadow lead on a real resource, beside the Advisor items | 1a.2, 1a.3, 1a.4 | C6 | 4 to 5 |
| [1a.6a Price simulator](#1a6a-the-price-simulator-the-economist-and-typed-records) | `price-sim`, `cost-query`, the [Economist](../design/03-agents-and-workflows.md#1-ten-roles-in-five-hosted-agents); price-basis labels and evidence levels in typed records | A price range with its basis; a replay of last month's bill matches the lake on the same scope, month, currency and cost type, within a tolerance written down beforehand (a pipeline test) | 1a.2, 1a.3, 1a.4 | C8 (start), C11 (Build and action plane) | 5 to 7 |
| [1a.6b Cases](#1a6b-cases-that-only-report) | The `investigate` hosted agent gains the [Detective](../design/03-agents-and-workflows.md#1-ten-roles-in-five-hosted-agents) and the `skeptic` agent is deployed; the Case workflow; prompt-injection tests; the path matrix and a red-team session | A Case from lead to priced Recommendation draft; cost per Case from hub logs | 1a.5, 1a.6a, 0.4 | C7 (P7), C8, C11 (Restraint, Honesty) | 7 to 11 |
| [1a.7 Monday digest](#1a7-the-monday-digest) | The [Diplomat's](../design/03-agents-and-workflows.md#1-ten-roles-in-five-hosted-agents) digest and the send step; a letter to the FinOps lead only; templates and tests | The digest arrives by 09:00 on a Monday and renders in classic Outlook and the FinOps lead's client | 1a.6b (gates passed), 0.5 | C4 (rest, production), C7 (end to end), C11 (Messages and pages) | 4 to 5 |
| [1a.8 Confirm](#1a8-confirm-and-measure) | The FinOps lead's confirmations in the ledger; cost per Case and per confirmed finding; the cost model against a closed bill | The number written down beforehand is reached | 1a.7 | C8 (P10) | 2 to 3, longer elapsed |

### 1a.1 The first estate, access and the Operate profile

The Operate profile is deployed in full, so no later slice changes the network. Only the `bot` app, the one public endpoint, waits for phase 2; the `approvals` and `runner` apps stay empty until phases 2 and 3. A pre-release run in a short-lived Operate environment in dev tests isolation, restores and the kill switch. **Why here:** all real data comes through this profile. **Surprise:** moving from Evaluate to Operate means [a new Foundry account](../design/02-architecture.md#7-two-profiles-one-codebase), and deploying needs [a deployment runner inside the network](../design/09-delivery-and-operations.md#3-pipelines-and-releases). The [Capability gate](../design/08-testing-and-evaluation.md#8-the-path-of-a-change-and-what-blocks-a-release) needs a sealed test set that phase 1b builds, so a reviewed change comes first (check C11). **Read:** checks C5, C11 and C12.

### 1a.2 The cost lake

Every scope's bill lines land in one layout, whichever path delivered them. **Why here:** the Estate model, the Detectors and the price simulator all read the lake. **Surprise:** only a closed month can be reconciled with Cost Management, with scope, month, currency and cost type written down beforehand, and check C13 comes first. **Read:** checks C13 and C6, and [cost data](../design/05-data-and-integrations.md#2-cost-data).

The cost data comes by the first path that works for each scope, in the order of the table in [Choosing the first estate](02-before-you-start.md#choosing-the-first-estate): an export in FOCUS, the Cost Details API, for pay-as-you-go an export of another dataset or the Usage Details API, and last the Query API. The estate or billing owner creates any export, because the system holds only read roles in phase 1a. **A first estate must offer a per-resource bill path** (every path but the Query API) to pass the explained-spend exit; with only the Query API, or no cost access, it can still run Cases with labelled fidelity, but it is a different pilot that cannot pass.

### 1a.3 The Estate model and its refresh

The Estate refresh workflow stores each scope's capability profile, and the Surveyor builds the Estate model. The stub `estate-read` of 0.3 gets its live version here. **Why here:** it needs the scopes of 1a.1, and the explained-spend figure also needs the lake of 1a.2 (the dashed arrow below). **Surprise:** owners come from the directory as guesses, and a guess is never shown as a fact until a person confirms it. **Read:** check C5 and [the Estate model](../design/04-knowledge-and-learning.md#6-the-estate-model).

### 1a.4 Atlas v0

Atlas v0 starts with the services the first estate has most of, counted from Resource Graph, and adds by spend when the lake lands. Atlas reviewers merge every change by pull request. **Why here:** it needs the search of 0.2, the publishing and pins of 0.3 and the services the estate uses, known from 1a.1. **Surprise:** no priced Recommendation appears here, only in 1a.6b, and which retrieval option is best is proof point P5, in phase 1b. **Read:** [the Atlas](../design/04-knowledge-and-learning.md#2-the-atlas).

### 1a.5 Watch and the first Detectors

Detectors come from rows of the cost-trap bank (a catalogue of sourced Azure cost traps) that a person has verified against their sources. **Why here:** Detectors are back-tested on the lake and rest on Atlas claims. **Why shadow:** a Detector promoted too early turns false positives into Monday mail, so promotion is a person's decision on numbers written into each Detector beforehand, and it is not part of the exit. **Surprise:** the first Cases do not wait: [the Agenda](../design/04-knowledge-and-learning.md#6-the-estate-model) also takes Advisor items, anomaly alerts, the Unexplained Spend list and the FinOps lead's hunches. **Read:** check C6 and [Detectors](../design/04-knowledge-and-learning.md#5-detectors-expensive-reasoning-once-cheap-checks-afterwards).

### 1a.6a The price simulator, the Economist and typed records

`price-sim` must reproduce a prior month's bill before it prices anything new, and every price carries its basis: contracted, billed or list ([the price order](../design/14-agreements-and-access.md#the-price-order)). **Why before the Cases:** a Case without a trusted price is an opinion. **Surprise:** this slice cannot start until the FinOps lead has written down, by pull request, how many confirmed findings end phase 1a, the margin for C8 and the review date. **Read:** check C8.

### 1a.6b Cases that only report

This is the largest slice, and the most likely to move. No tool that proposes a change exists yet. **Why here:** it needs leads, prices and a working agent path. **Surprise:** until phase 1b exits, the recommended default is that the Capability gate reports on the development set and cannot block, and every output reaches only the FinOps lead (check C11). **Read:** checks C7 and C8, and [the Detective and Skeptic loop](../design/03-agents-and-workflows.md#5-the-detective-and-skeptic-loop).

### 1a.7 The Monday digest

The 1a letter goes to the FinOps lead only, after an agreed pilot introduction. The owner first-contact flow needs phase 2's page and opt-out, so it is not used. It has no links to the report card or pages. It keeps the sections *What I learned*, *What moved in the bill*, *What I got wrong*, *What I need from you* and *What I cost* of [the Monday letter](../experience/05-letters-and-requests.md#the-monday-letter); *Decisions waiting*, *What I did* and *Wins, verified* have nothing to report before phase 3. It ends with a status block: Cases opened, findings confirmed, explained spend and cost per Case. Each finding carries its evidence in words (the figures, where each came from and the price basis), and a platform-team member shows the full record on request, read with the time-boxed data role of 1a.8.

**Why here:** a digest is sent only once the Cases behind it have passed their gates. **Surprise:** five cold readers, the ten-second test and a native-speaker check come before it goes live, and C4 and C7 (the path matrix, now with the Diplomat and the send step) are repeated end to end for the production deployment; that completes the P7 evidence. **Read:** check C4 and [the letter rules](../experience/05-letters-and-requests.md#the-monday-letter).

### 1a.8 Confirm and measure

A small reviewed command records each confirmation in the ledger, under a platform-team identity with a time-boxed data role, so the ledger's write path stays reviewed. The Respond workflow and the pages replace it in phase 2. **Why last:** it measures what the digest produced. **Surprise:** the effort is small, but a billing month must close and the FinOps lead's calendar sets the pace. **Read:** check C8.

## What depends on what

Solid arrows mean *starts after*, the dashed arrow *its check needs*. Arrows are direct: a slice also waits for what its predecessors wait for.

```mermaid
flowchart LR
    subgraph plat["Platform and pipelines"]
        n01["0.1 Repository, pipelines, gates"]
        n02["0.2 Evaluate profile, hub path"]
        n1a1["1a.1 First estate, Operate profile"]
    end
    subgraph agents["Agents and workflows"]
        n04["0.4 One agent, one workflow"]
        n1a6a["1a.6a Price simulator, Economist"]
        n1a6b["1a.6b Cases that only report"]
    end
    subgraph data["Data"]
        n1a2["1a.2 The cost lake"]
        n1a3["1a.3 Estate model, refresh"]
    end
    subgraph know["Knowledge"]
        n03["0.3 Published tool, pins, suite"]
        n1a4["1a.4 Atlas v0"]
        n1a5["1a.5 Watch, first Detectors"]
    end
    subgraph eng["Engagement"]
        n05["0.5 The mail path"]
        n06["0.6 Thin path, first drill"]
        n1a7["1a.7 The Monday digest"]
        n1a8["1a.8 Confirm and measure"]
    end
    n01 --> n02
    n01 --> n05
    n02 --> n03
    n02 --> n04
    n03 --> n04
    n04 --> n06
    n05 --> n06
    n06 --> n1a1
    n1a1 --> n1a2
    n1a1 --> n1a3
    n1a1 --> n1a4
    n03 --> n1a4
    n1a2 -.->|"explained spend"| n1a3
    n1a2 --> n1a5
    n1a3 --> n1a5
    n1a4 --> n1a5
    n1a2 --> n1a6a
    n1a3 --> n1a6a
    n1a4 --> n1a6a
    n1a5 --> n1a6b
    n1a6a --> n1a6b
    n1a6b --> n1a7
    n05 --> n1a7
    n1a7 --> n1a8
```

| Slice | Starts after (slices) | Its checks pass only with |
|---|---|---|
| 0.1 | None | No check |
| 0.2 | 0.1 | Nothing more |
| 0.3 | 0.1, 0.2 | Nothing more |
| 0.4 | 0.2, 0.3 | The stub tool of 0.3, which C1 calls |
| 0.5 | 0.1 | Nothing more |
| 0.6 | 0.4, 0.5 | Nothing more |
| 1a.1 | 0.6 | Nothing more: 1a.3 stores the profile |
| 1a.2 | 1a.1 | Nothing more |
| 1a.3 | 1a.1 | 1a.2, for the explained-spend figure |
| 1a.4 | 0.2, 0.3, 1a.1 | Nothing more |
| 1a.5 | 1a.2, 1a.3, 1a.4 | Nothing more |
| 1a.6a | 1a.2, 1a.3, 1a.4 | Nothing more |
| 1a.6b | 1a.5, 1a.6a, 0.4 | Nothing more |
| 1a.7 | 1a.6b with its gates passed, 0.5 | The mail path of the production deployment |
| 1a.8 | 1a.7 | A closed billing month |

## Sizes and elapsed time

Sizes are person-weeks and scenario parameters. Phase 0 is 18 to 24, phase 1a is 38 to 52, and the first stretch is 56 to 76, with hub deployment excluded. Only slice 0.2's estimate changes if a hub must also be deployed: 4 to 5 with one, 6 to 8 if the accelerator is deployed, which makes the stretch 58 to 79.

Effort is not elapsed time: allow roughly eight to eleven months for two builders and five to eight for three, with each builder spending four days in five on the project, before the organisation's approvals and before a billing month closes. The longest chain of slices that each start after another is 43 to 59 person-weeks, about 12 to 17 months with one builder on each slice, so these estimates assume that builders share the long slices.

## What comes after phase 1a

The plan is detailed only as far as phase 1a and is [re-issued at each exit](04-cost-effort-and-risks.md#how-the-plan-is-revised). [The roadmap](../design/13-roadmap.md#1-phases) holds the later phases:

- **1b, show that it learns.** The Study workflow, the report card, baselines and sealed test sets. P5 asks which retrieval serves the Atlas; P6 and the rest of P10 ask whether the system beats simpler baselines on sealed test cases and updated memory beats frozen memory. It may overlap phase 2.
- **2, recommend and ask.** Teams cards, e-mail and web pages for every owner, preferences, the Respond workflow and Lessons. The client matrix (C9) and the sign-in test (C10) run before go-live, and a suite of attacks hidden in owners' replies passes.
- **3, act.** The action plane. P3: tampered, replayed and mismatched approvals fail closed. P8: a purchase role appears and disappears within a measured window. C7 runs again once propose tools exist. It starts only after 1b, because P6 tests whether the system learns at all.
- **4, earn autonomy and purchases.** Credentials, purchases approved by two people, the Strategy workflow, and a person-led red-team session before each Credential.
- **5, open up.** A contribution flow, anonymised statistics, optional voice and meeting modules, second-region recovery.
