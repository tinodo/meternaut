# The estate and the investigation — how the AI understands a customer and finds what is wrong

> How the system understands one estate — what exists, what it is for, what it may see and do, who owns it, what must not be touched — and how it investigates and prices a change before it happens. Part of the [north star](01-north-star.md); the technical design is in [docs/design](design/README.md).

---

## 1. The Estate Model — a story, not an inventory

An inventory says *what exists*. The **Estate Model** says what exists, how it connects, **what it is for**, who needs it, when it is busy and what must never be touched. It is the AI's understanding of one customer, kept inside that customer's boundary and built from many kinds of reading.

| Layer | What it holds | Read from (as far as its reach goes) |
|---|---|---|
| **Inventory and topology** | every resource and how they connect: network paths, dependencies, shared platforms | inventory, network and dependency data |
| **Configuration and change** | what each thing is set to, and who changed it, when | configuration, change history, deployment logs |
| **Usage** | what each thing actually does: load, connections, access, throughput, errors | telemetry, metrics, access records |
| **Money** | the bill, line by line, actual and amortised, under its **agreement** (the kinds are listed below) and at a known **price level**: contracted, billed or list | cost data, price sheet, agreement, commitments |
| **Origin** | the code and infrastructure definitions behind each thing, and the pipeline that deploys it | repositories, pipelines |
| **People** | who owns, builds, pays for, depends on and approves — and who just left | directory, role assignments, commit and ticket history |
| **Intent** | what each workload is *for* — and the unit of value it produces (orders, users, scans) | names, tags, documents, diagrams, tickets, conversations |
| **Rhythms** | when it is busy, quiet, critical | usage history, the business calendar |
| **Constraints** | what must not change: compliance, disaster-recovery roles, freezes, service-level promises | policies, wikis, owners |
| **Lessons** | what people have taught it | the [Lesson Book](#10-the-lesson-book--memory-you-can-read) |

The model is a living twin: it updates continuously, carries a confidence on every statement, and is **explicit about what is inferred and what a human confirmed**. It knows only what has been *kept*. Cost Management shows about 13 months of bills, but Azure itself keeps resource property changes for 14 days, platform metrics for about 93 and control-plane events in the activity log for 90, so how far back the system can look, and what it can replay, depends on what a customer exports and retains. Collecting history from day one is part of onboarding.

### What it may see and do — the capability profile

Azure is sold in several ways, and the way changes what every number means. So the Surveyor, the agent that builds the Estate Model, starts each estate with two questions. **Which agreement is this?** Enterprise Agreement (EA) · Microsoft Customer Agreement (MCA) bought directly · sold through a partner (CSP) · pay-as-you-go, and the offers around them. **What may the system see and do here?** Not what the organisation could reach, but what the access it was given reaches.

| Reach | What it can do | Its numbers say |
|---|---|---|
| **Billing reach** — a role on the billing account, the billing profile or the enrollment | reads the price sheet and commitments, sees every subscription, prepares purchases | "Priced at your contracted rates" |
| **Subscription reach with costs** | reads bill lines, finds waste, advises per subscription | "Priced at the rates on your bill" |
| **Subscription reach without costs** | reads resources, metrics, Advisor; prices what it finds as scenarios at list prices | "Scenario at list prices — your rates are invisible to me" |

Under a partner agreement the partner holds the billing view: the customer's own system has subscription reach, and sees costs, at retail rates, only once the partner enables cost visibility.

Nobody declares which applies: the system **probes**. At onboarding, every week after and at once whenever Azure refuses a request, it tries to read the bill, the price sheet and the commitments, and records what worked in which scope — the **capability profile**, one per scope. A role granted later is noticed at the next probe.

- **Every number carries its price basis** — contracted, billed or list — and a figure is called an *expected saving* only when a bill backs it. Without a bill it is a scenario at list prices, which owners can still act on.
- **Every purchase goes to whoever can make it.** Where the agreement lets it, the system prepares the purchase, two named people approve and it carries it out. Where a partner sells the commitment or a central team holds the billing role, it hands over a *request* — evidence, scope, figure — and watches the bill.
- **It says what more access would buy** — *"with the price sheet I could put your rates on 14 recommendations"* — and leaves the choice to people. It never asks for more than a question needs.
- **An organisation made of organisations has one profile per scope.** A platform team may hold billing reach while each application team holds one subscription; what one may see never reaches the other.

> **(An invented example.)** *The orders team sees only its own subscription: no bill, no rates, no purchases. The system still finds a database that peaks at 11% of its capacity, two disks attached to nothing and an always-on fleet a commitment could cover. Each Recommendation labels its figure: "About €410 a month. Scenario at list prices — your rates are invisible to me." For the commitment it writes a request, not a purchase — three months of usage, the scope, the scenario at list prices — for the platform team that holds billing reach. The orders team fixes the first two that week.*

The technical side is in [the design](design/14-agreements-and-access.md).

---

## 2. Understanding intent

The most important fact about a workload — *what is it for?* — is almost never written down in one place. The Surveyor assembles it from:

- **Names and tags** — `payments-dr-weu`, `exp-recsys-2024`.
- **Deployment history** — a pipeline named `launch-campaign-q4`, last changed in July.
- **Traffic shape** — a nine-to-five curve with a quarter-end spike, or a flat line with a nightly burst.
- **Code and infrastructure definitions** — the README, the owners file, the service it belongs to.
- **Pictures and words** — architecture diagrams, whiteboard photos (the AI can read images), tickets, post-mortems, chat threads in channels where it has been invited.
- **Agreement and commitments** — what they say about how the customer expects to use Azure, where its reach lets it read them.

The result is an **intent statement** with a confidence and its evidence (an invented example): *"Disaster-recovery replica of the payments platform; passive until a failover; must take full load within 30 minutes (source: runbook, 2025-02)."* High-stakes or low-confidence statements are confirmed by a person, in one question, asked once and remembered. Intent is what turns *"this is idle"* into *"this is idle on purpose"*.

---

## 3. Rhythms and the business calendar

A resource that is quiet in March can be the star of November. The Surveyor learns, per workload:

- **The daily and weekly shape** — office hours, batch windows, weekend lulls.
- **The seasons** — quarter close, campaigns, tax filing, Black Friday.
- **Events** — launches, audits, migrations, freezes, from calendars and release plans.

Rhythm decides *how long it has to look* before it may say "unused": a month of silence means one thing for a daily job and another for a yearly one. It also decides **when to ask** and **when to act**.

---

## 4. The human graph — following the directory

Cost is decided by people, so the AI must know *which* people. For every resource it resolves a set of **hats**, not a single owner:

| Hat | Question |
|---|---|
| **Accountable owner** | who answers for it? |
| **Technical lead** | who can change it safely? |
| **Budget holder** | whose money is it? |
| **Consumers** | who depends on it, visibly or silently? |
| **Change authority** | who must agree to a change — a change board, a platform team, a customer, whoever holds the billing role for a purchase? |

Ownership is inferred from a **waterfall of evidence**, strongest first: an explicit, current tag; the repository's owners file; the identity that deploys it; role assignments; commit and ticket history; chat in channels where it is invited; the directory's manager chain. Each signal adds confidence; **nothing is "confirmed" until a human says so**. When the evidence conflicts or runs out, the Diplomat, the agent that talks to people, asks one question of the likeliest person, where they work, and the answer is remembered.

It follows the **directory** — managers, delegates, who is on leave, time zones, languages — using only what the person or the organisation has provided or authorised, and confirming delegates with the person rather than inferring them. When someone leaves or changes team, their things do not become nobody's: they are flagged within days, with a proposal for a new owner.

**Things with no owner** go to a **named custodian**, a person or team who agrees to be the owner of last resort. An orphan is an *ownership* problem first and a cost problem second.

### An organisation made of organisations

Real companies are rarely one estate: a central platform team, an acquired business unit with its own agreement and tagging habits, product teams that run what they like. The system keeps **one Atlas** (the open map of how Azure charges) **but many estates**, each with its own [capability profile](#what-it-may-see-and-do--the-capability-profile). Lessons are scoped to the unit that taught them; an acquired unit's price book and allocation rules are its own; decisions stay local, and the central team sees a roll-up of measured savings and open questions — not the units' private lessons. When two units disagree about how a shared service should be charged, that is a [decision room](05-recommend-act-verify.md), not a ruling by the AI.

---

## 5. The bill as a tree — and the list of what is unexplained

The investigation starts from money. Every euro on the bill is a leaf of a tree:

```
bill
 └─ subscription / billing scope
     └─ resource group · application · team
         └─ resource
             └─ meter  ← the Atlas knows its mechanism and its signal of need
                 └─ configuration choice
                     └─ decision: who chose it, when, why
```

For each leaf the system tries to say four things, with a confidence:

1. **What is it for?** (intent)
2. **Who needs it?** (the hats; real consumers)
3. **How much of it is needed?** (the demand signal vs what is provisioned, stored, produced or moved)
4. **What would it take to need less?** (levers, consequences, effort, risk)

A leaf with all four answers is **explained**; a leaf without is on the **Unexplained Spend list**. Two headline numbers fall out:

- **Explained spend** — the share of the bill that is explained. It should rise.
- **Explained-but-wasteful spend** — the part that is explained and shown to exceed its need.

The list is the **engine of the Agenda**: what the system cannot yet explain is what it investigates next.

**"Unused" means no demonstrated value — not few reads.** To decide whether a leaf is needed, the system follows a **value-flow graph**: data and capacity connected to the consumers that use them and the outcomes those consumers serve. A thing with few readers may carry a critical outcome; a thing with many may carry none. Where the graph has a gap, the gap goes on the Agenda.

---

## 6. The Agenda — what the system is wondering about

The **Agenda** is the AI's ranked list of open questions. It is fed from many directions:

| Source of questions | Example (invented) |
|---|---|
| **Unexplained spend** | a large block with no intent, no owner, or no demand signal |
| **Growth and surprise** | spend rising 9% a month with no matching change in the architecture |
| **Model residuals** | the cost model derived from the blueprint disagrees with the bill — [bill versus blueprint](#9-bill-versus-blueprint) |
| **New knowledge** | a profile was just published or revised: *which of our things does it touch?* |
| **Change in Azure** | a price moved, a SKU appeared, a service retires |
| **Weak foundations** | a belief it relies on is old, high-impact and weakly confirmed |
| **Blind spots** | a sign of waste the Atlas knows about has no matching measurement in this estate |
| **Human hunches** | *"I bet the test environments sit idle at weekends."* — the [Hunch Box](08-outer-rims.md) |
| **Native recommendations and alerts** | an Advisor recommendation, a budget alert, an anomaly alert — checked like any other claim, then routed to the right owner with reasoning ([what happens to an Advisor card](05-recommend-act-verify.md)) |
| **Unknown unknowns** | change-points with no known cause, and meters that fit no mechanism and no Detector |

Questions are ranked by **value of information**: how much money (or risk) hinges on the answer, how likely the answer is to change what we do, and how cheap it is to find out. A question about a large unexplained block that one conversation could resolve outranks a fascinating question about a small, slow-moving meter.

The **Conductor** owns the Agenda, spends the research budget and decides, hourly, what to pick up next. It keeps a simple score per kind of question and per tactic — verified value per euro and per minute of a person's attention — and puts more effort where that score is high. A fixed share of effort is protected for *curiosity*: questions with no immediate payoff but high expected learning.

---

## 7. The investigation toolkit

| Technique | In plain words |
|---|---|
| **Decomposition** | break a cost into meters, resources, configurations, decisions |
| **Differential diagnosis** | list *competing* explanations and look for the evidence that separates them |
| **Consumer analysis** | "who reads, calls or depends on this?" — including the infrequent and the invisible |
| **Cohort comparison** | compare with look-alike workloads here and, through **Pool**, with what other estates have seen |
| **Reading the source** | the code and infrastructure definitions, to find what produces the cost — and to fix it *there* |
| **Reading the agreement** | what the agreement and commitments change about the answer, where its reach lets it see them |

When the data in hand does not settle a question, the Detective picks the cheapest decisive test from six routes ([finding out without spending](04-finding-out-without-spending.md)). The first five cost model tokens and some attention, and change nothing in Azure:

- **Ask** — one short question, put by the Diplomat to the one person who knows.
- **Look** — bills, metrics, change and deployment history, tags: when did the cost change, and what else changed that day? Bills go back about 13 months; a change can be joined to a meter only for the history the estate kept (section 1).
- **Replay** — re-price recorded usage under another SKU, region, offer or commitment, once the replay reproduces that month's real bill. *Evidence under stated assumptions*, never proof.
- **Follow** — the outcome of a change people were making anyway, against predictions and control meters (the same meters on look-alike resources nobody changed) written down first.
- **Pool** — what other estates have already seen, as privacy-reviewed aggregates (section 13).

**Trial** is different: rarely, one small, reversible change to something an owner already runs in non-production. The owner approves it after seeing a cost ceiling and a guard metric rolls it back automatically; it can move the bill, so it is not free. Learning never provisions anything just to measure it.

### Hypotheses, challenge and verdict

Every candidate becomes a hypothesis and follows the [life cycle in the north star](01-north-star.md): triaged, investigated, **challenged**, *gathering evidence*, asked about, parked or split — then *confirmed* (a **Case**, or a **Detector** if it is general), *refuted* (a **Lesson**: why it looked true) or dropped.

- **Triage is economic.** "Is this worth a person's time?" is decided early: a correct finding worth nothing is still noise.
- **The Skeptic's job is to break the case.** It asks *who else uses this, what happens at the peak, what the last incident taught, what compliance requires, whether the metric is lying* (sampled, delayed, missing a consumer) and, for every Case, runs a **pre-mortem**: *"imagine we did this and it went badly; what happened?"*
- **Refuted hypotheses are kept.** "It looked unused because the audit job runs once a quarter" prevents the same mistake in every estate with a quarterly job.

### How the fact was obtained

Each fact in a Case says how it was obtained, so a reader can weigh it: **measured** (telemetry, the bill, the outcome of a change) → **observed** (configuration, history) → **reported** (a person said so) → **inferred** (the AI's reasoning) → **assumed**. A Case lists which claims rest on which — and what **would change its mind**. Atlas claims use a different scale, the four evidence levels: documented → price-confirmed → bill-observed → outcome-confirmed.

---

## 8. The Case notebook

Every investigation leaves a **notebook**: the question, the hypotheses, the queries and results, the charts, the evidence gathered, the Skeptic's objections and the verdict — readable by a person, re-runnable by anyone. It answers *"why do you think so?"* A Recommendation links to it and an Atlas claim cites it. No notebook, no Recommendation.

---

## 9. Bill versus blueprint

Alongside "start from the bill", the system works from the other end. From the architecture — the infrastructure definitions, the diagrams, the documents — it builds an **expected cost model** for each workload: *"given this design and this traffic, the bill should be about X, made of these meters."* Then it compares with the actual bill.

- A **residual** — actual above expected — is a lead: a meter nobody modelled, a default that switched something on, a job that retries, traffic that takes a longer path.
- A **negative residual** is a lead too: something the design assumes exists but does not, or a discount applied that nobody planned.
- A **stable residual** teaches the model; a **growing** one goes straight to the Agenda.

---

## 10. The Lesson Book — memory you can read

Everything people teach the system lands in a **Lesson Book** — plain language, human-editable, never hidden inside a model (an invented entry):

```
LESSON  "Weekend idleness is expected in development subscriptions."
SCOPE   the three development subscriptions of team Orchard   (proposed to widen: all development subscriptions — pending)
SOURCE  the lead of team Orchard, in reply to a Recommendation, 2026-09-12
EVIDENCE telemetry shows weekend troughs in all three
EXPIRES 2027-09-12 (review)   STATUS Active · applied 14 times · 0 reversals
```

A lesson has a **scope** (this resource, this team, this organisation, everywhere), an **owner**, **evidence**, an **expiry** and a **track record**. The AI may *propose* widening a lesson (*"remember this for all development subscriptions?"*); a person says yes, no or "only here".

What a person says is **testimony**, not truth — attributed, dated, scoped and fallible. It is adopted at the scope it was given, **widened only with corroboration** (telemetry that agrees, a second person, repeated outcomes), re-asked cheaply when evidence changes, and judged by *decision burden* rather than question count ([the learning contract](09-the-learning-contract.md)).

---

## 11. The Consequence Engine — "what happens to the bill if…?"

Finding waste looks *backwards*. The **Consequence Engine** also looks *forwards*. For any proposed or actual change it answers: **what happens to the bill — and to reliability, performance, security and sustainability?**

| Asked about | Example |
|---|---|
| a **design or pull request** | "this change enables a feature that switches on a meter" |
| a **policy** | "if we double the retention period, what happens in a year?" |
| a **migration** | "what would it cost to move that platform, run both for two months, and then retire the old?" |
| **growth** | "if traffic doubles next quarter, which meters grow linearly and which jump?" |
| a **price change or new SKU** | "what does this do to our estate?" |
| an **optimisation** | "if we shrink this, what is the saving, the risk, the effort — and what *else* moves?" |

How it thinks, in plain terms:

1. **Decode** the change into meters, using the Atlas — including the ones nobody remembers: *flipping this switch adds that meter; this replica count multiplies that one*.
2. **Place it in this estate**: the real demand and rhythm, not an average load, and the best prices it may see — contracted or billed, else list — with the answer saying which.
3. **Return a range, not a number**, with the assumptions that drive it, and a **cost of being wrong**: what happens if the demand is half, or double.
4. **Show the non-cost consequences** next to the cost, using the Well-Architected pillars as the checklist — a saving that costs resilience is a different offer. They come from the estate's telemetry, its dependencies and what owners say; where those are missing, the answer is "unknown", not a guess.
5. **Remember it**: the prediction is filed in the **Ledger**, the system's record of predictions, decisions and measured outcomes, and scored when reality arrives.

**Under the hood, a causal model.** It models what drives what — configuration → demand → meters → bill, with reliability and performance side-effects — and refits it from changes that really happened: what **Follow** reads when a team changes something, compared with untouched look-alikes, and, rarely, a **Trial**. Its assumptions sit on the page, and where there is no good comparison it widens the range. Counterfactual numbers are *evidence under stated assumptions* ([the learning contract](09-the-learning-contract.md)).

This is the engine behind **shift-left**: the cost of a decision shown *at the moment it is made*, in the pull request, the design review and the planning meeting — not three weeks later on the bill.

### A worked case (an invented example)

> A pull request turns on cross-region replication for a data store "for resilience". The Consequence Engine reads the change, decodes the meters from the Atlas — storage in the second region, replication traffic between regions, a higher-priced SKU that the feature requires — and reads the estate: the store holds 4 TB and grows 6% a month; the change rate is high. It answers in a comment on the pull request: *"About €1,900 a month at your billed rates, rising to about €2,600 within a year; €700 of that is replication traffic and depends on the change rate, which is the uncertain part. If this store is not in the disaster-recovery plan for the payments platform, the resilience gain is small; if it is, this is cheap. Alternative: replicate only the two tables the runbook lists — about €480."* The author replies, the AI files the lesson, and the prediction goes in the Ledger.

---

## 12. The first 24 hours in a new estate

The Atlas already knows Azure. What the system must learn first is the customer's own: what it may see and do, and the agreement, rates and commitments it sits under.

1. The Surveyor **works out what it may see and do**: it probes each scope and records the first capability profile, which fixes the price basis its numbers can honestly carry.
2. It inventories what it may see and, where its reach includes the bill, reads it (billing data lags by hours to days). Without cost access it starts from resources and metrics, and every figure is a scenario at list prices.
3. The Atlas decodes every meter it can see at once, and the Conductor builds the first Unexplained Spend list and the first Agenda: biggest blocks first.
4. The Surveyor drafts intent statements and owners for the largest blocks, with confidence.
5. Day one maps access and resources. Once the bill has caught up, the owners of the five largest unexplained blocks each receive **one** question — nothing else. The rest of the week is the system *listening*.

---

## 13. Privacy of understanding

The Estate Model and the Lesson Book describe a customer's business and its people. They stay inside the customer's boundary, and so do its bills, its price sheet and its measured outcomes: none of them enters the open Atlas. Under **Pool**, and only with the customer's say-so, a scope and an aggregate may be offered to the [Commons](07-getting-smarter.md), privacy-reviewed and published only when several organisations contribute the same observation — never a bill line, a name or an identifier. The system works out who *owns* things, not how well they work; the technical rules are in [security and governance](design/06-security-and-governance.md).

---

## 14. A gallery of cases — breadth, not rules

What the system might bring to a human, across every mechanism (invented examples). Each would come from reasoning with the [Cost Grammar](02-learning-azure.md), the fourteen ways money arises, the estate and a Skeptic's objections. Many have a source-verified entry in the [cost-trap bank](research/cost-trap-bank.md): the claim was found on the cited Microsoft page, and no bill has confirmed it.

| Where it shows up | A case it might bring | Why nobody noticed |
|---|---|---|
| **Rate and benefit** | A fleet of Windows VMs runs at the licence-inclusive rate while the agreement shows eligible licences with active Software Assurance | entitlements live in procurement records, not in the portal |
| **Commitment** | The shutdown an Advisor card recommends would free a reservation benefit that simply moves to another VM — the real saving is about zero, and the real saving is somewhere else | the card prices the VM at retail, ignoring the commitment |
| **Commitment** | A savings plan bought in January sits 30% unused through every August lull | it was sized to the peak, not to the floor |
| **Commitment** | A reservation for an instance family the platform team is migrating away from in Q3 | purchase and roadmap are owned by different people |
| **Flow** | A nightly full copy of a dataset to another region for analytics that only ever read yesterday's changes | the job was written when the dataset was small |
| **Flow** | Backups left on geo-redundant storage — a second, paired region — when the recovery plan names only one | the default was copied from a template |
| **Capacity** | A premium messaging namespace provisioned for a launch, peaking at 8% of its capacity ever since | launches end quietly |
| **Capacity** | A GPU pool kept warm between training runs that are two weeks apart | the idle period is invisible at the monthly level |
| **Capacity × time** | A data-engineering cluster with no auto-termination, still attached on Sunday | nobody owns "turning it off" |
| **Stock** | Versioning, soft delete and snapshots overlapping on a very large blob container that has all three switched on | each protection was added for a good reason, separately |
| **Stock** | A container registry holding thousands of tagged CI images that nobody pulls (built-in retention covers untagged manifests only) | storage is cheap per image and enormous in total |
| **Leftover** | Private endpoints — billed per hour while they exist — whose target services were deleted months ago | the endpoint is a separate object |
| **Leftover** | Managed disks and public IPs left behind by deleted VMs (whether they go with the VM is a per-resource setting) | deleting the parent did not delete the children |
| **Feature** | A default that switched on zone redundancy in the dev copy of a production template (an extra cost on some services, none on others) | it was inherited, never chosen |
| **Feature** | Geo-replication enabled on a registry for a region with no consumers | enabled "just in case" |
| **Tier / step** | A database tier chosen for one premium feature that nobody uses | the feature was needed in the pilot |
| **Allowance** | A plan tier chosen just above its free allowance, for use that fits inside the tier below | the threshold is in the pricing page, not the portal |
| **Time cliff** | A service's preview price ends on 1 March; nine of fourteen estates use it | the end date had no owner |
| **Time cliff** | Function apps on Linux Consumption: the plan retires on 30 September 2028, and the migration doubles as a right-sizing chance | a forced move is also a design review |
| **Time quantum** | A job that stops and starts a managed database instance hundreds of times a day, each start billed for a full started hour | the meter rounds up; the job does not know |
| **Coupling** | Private connectivity that added a per-GB processing meter nobody modelled | it arrived with a security change |
| **Consumption** | A retry loop in an AI agent that quadruples token spend on a pay-as-you-go deployment after a prompt change | tokens are billed after the fact |
| **Consumption × multiplier** | A model swapped for a larger one in a configuration change: the same task now costs several times as much | the change was reviewed for quality, not for price |
| **A cap that bites** | A monthly allocation limit that, once reached, takes an agent offline for the rest of the month while its always-on charge continues | the control was set for cost and caused an outage |
| **Capacity (existence floor)** | Agents created for a trial and forgotten, billing always-on from creation until they are deleted | nothing "uses" them, so nothing alerts |
| **Network path** | Chatty traffic between a service pair that a redesign put into two peered virtual networks | the bill shows a transfer line, not a placement choice |
| **Agreement** | A consumption commitment tracking 11% short at year-end, while eligible spend sits outside the billing account | the burn-down is read once a year |
| **Marketplace** | Two similar marketplace purchases — only one counts toward the commitment, because eligibility depends on the offer and on how it was bought | eligibility is a property of the offer |
| **Governance** | A quarter of the bill is untagged, so it is nobody's budget | tags are optional at creation |
| **Dev/test** | Non-production workloads billed at production rates in a subscription that could sit on a dev/test offer | the subscription type was set once, years ago |
| **Region** | The same SKU at a lower list price in a neighbouring region, with no data-residency reason to stay | placement was decided before pricing diverged |
| **Retention** | A seven-year retention policy on a dataset whose legal requirement is ninety days | policy was set for the strictest dataset in the platform |
| **Unit economics** | Cost per order fell 18% while the bill rose 9% — the growth was good news the bill hid | the dashboard shows the bill, not the unit cost |
| **Spend more** | A cache that lets the database drop two tiers | saving money requires spending some |
