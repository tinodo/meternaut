# The estate and the investigation — how the AI understands a customer and finds what is wrong

> **What this answers:** *How does the AI understand this estate — what things are for, who owns them, what must not be touched? How does it investigate: find, explain, prove? And how does it work out the cost implications of any change before it happens?*
> Part of the [north star](01-north-star.md). Idea-level: what the system must be able to do, not how it is built.

---

## 1. The Estate Model — a story, not an inventory

An inventory says *what exists*. The **Estate Model** says what exists, how it connects, **what it is for**, who needs it, when it is busy and what must never be touched. It is the AI's understanding of one customer, kept inside that customer's boundary, and it is built from many kinds of reading.

| Layer | What it holds | Read from (with permission) |
|---|---|---|
| **Inventory and topology** | every resource and how they connect: network paths, dependencies, shared platforms | the resource inventory, network and dependency data |
| **Configuration and change** | what each thing is set to, and how it got there — who changed it and when | configuration, change history, deployment logs |
| **Usage** | what each thing actually does: load, connections, access, throughput, errors | telemetry, metrics, access records |
| **Money** | the bill, line by line, in the customer's *effective* prices | cost data, price sheet, agreement, commitment portfolio |
| **Origin** | the code and infrastructure definitions that create each thing, and the repository and pipeline behind them | source repositories, deployment pipelines |
| **People** | who owns, builds, pays for, depends on and approves — and who just left | directory, role assignments, commit and ticket history |
| **Intent** | what each workload is *for* | names, tags, documents, diagrams, tickets, conversations |
| **Rhythms** | when it is busy, quiet, critical | usage history, the business calendar |
| **Constraints** | what must not change: compliance, disaster-recovery roles, freezes, contracts | policies, wikis, owners |
| **Lessons** | what people have taught it | the [Lesson Book](#10-the-lesson-book--memory-you-can-read) |

The model is a living twin: it updates continuously, carries a confidence on every statement, and is **explicit about what is inferred and what a human confirmed**.

---

## 2. Understanding intent

The most important fact about a workload — *what is it for?* — is almost never written down in one place. The Surveyor assembles it:

- **Names and tags** — `payments-dr-weu`, `exp-recsys-2024`.
- **Deployment history** — created by a pipeline named `launch-campaign-q4`; last changed in July.
- **Traffic shape** — a nine-to-five curve with a quarter-end spike; or a flat line with a nightly burst.
- **Code and infrastructure definitions** — the repository's README, its owners file, the service it belongs to.
- **Pictures** — architecture diagrams, whiteboard photos in a wiki, a slide in an old design review: the AI can read images.
- **Words** — tickets, post-mortems, chat threads in channels where it has been invited.
- **The contract** — what the commitment portfolio and agreement say about how the customer expects to use Azure.

The result is an **intent statement** with a confidence and its evidence: *"Disaster-recovery replica of the payments platform; passive by design; must be able to take full load within 30 minutes (source: runbook, 2025-02)."* High-stakes or low-confidence statements are confirmed by a person — usually in a single question, asked once and remembered.

Intent is what turns *"this is idle"* into *"this is idle on purpose"*.

---

## 3. Rhythms and the business calendar

A resource that is quiet in March can be the star of November. The Surveyor learns, per workload:

- **The daily and weekly shape** — office hours, batch windows, weekend lulls.
- **The seasons** — quarter close, campaigns, tax filing, harvest, Black Friday.
- **Events** — launches, audits, migrations, freezes — from calendars, release plans and people.
- **How the rhythm itself is changing** — growth, new regions, a product sunset.

Rhythm decides *how long it has to look* before it may say "unused": a month of silence means one thing for a daily job and another for a yearly one. It also decides **when to ask** and **when to act**.

---

## 4. The human graph — following the directory

Cost is decided by people, so the AI must know *which* people. For every resource it resolves a set of **hats**, not a single owner:

| Hat | Question |
|---|---|
| **Accountable owner** | who answers for it? |
| **Technical steward** | who can change it safely? |
| **Budget holder** | whose money is it? |
| **Consumers** | who depends on it, visibly or silently? |
| **Change authority** | who must agree to a change — a change board, a platform team, a customer? |

Ownership is inferred from a **waterfall of evidence**, strongest first: an explicit, current tag; the repository's owners file; the identity that deploys it; role assignments; commit, ticket and chat history; the directory's manager chain. Each signal adds confidence; **no inference is "confirmed" until a human says so**. When the evidence conflicts or runs out, the Surveyor asks — one question, to the likeliest person, in the place they work — and the answer is remembered.

It follows the **directory**: managers, delegates, the person on leave, the person who just changed team, working hours, time zones, preferred language. When someone leaves, their things do not become nobody's: they are flagged within days, with a proposal for a new owner.

**Things with no owner** go to a **named custodian** — a person or team who agrees to be the owner of last resort — never to a countdown that quietly deletes them. An orphan is an *ownership* problem first and a cost problem second.

---

## 5. The bill as a tree — and the ledger of what is unexplained

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

A leaf for which it can answer all four is **explained**. A leaf for which it cannot is on the **Unexplained Spend Ledger**. Two numbers fall out, and both are headline measures:

- **Explained spend** — the share of the bill that is explained. It should rise.
- **Explained-but-wasteful spend** — the part that is explained and shown to exceed its need. That is the savings pipeline.

The ledger is not a report. It is the **engine of curiosity**.

---

## 6. The Agenda — what the system is wondering about

The **Agenda** is the AI's ranked list of open questions. It is fed from many directions at once:

| Source of questions | Example |
|---|---|
| **Unexplained spend** | a large block with no intent, no owner, or no demand signal |
| **Growth and surprise** | spend rising 9% a month with no matching change in the architecture |
| **Model residuals** | the cost model derived from the blueprint disagrees with the bill — [bill versus blueprint](#9-bill-versus-blueprint) |
| **New knowledge** | a profile was just published or revised: *which of our things does it touch?* |
| **Change in Azure** | a price moved, a SKU appeared, a service retires |
| **Weak foundations** | a belief it relies on is old, high-impact and weakly verified |
| **Detectors without evidence** | a "tell" the Atlas knows has no matching measurement in this estate: a blind spot |
| **Human hunches** | *"I bet the test environments sit idle at weekends."* — the [Hunch Box](08-outer-rims.md) |

Questions are ranked by **value of information**: how much money (or risk) hinges on the answer, how likely the answer is to change what we do, and how cheap it is to find out. A question about a large unexplained block that one conversation could resolve outranks a fascinating question about a small, slow-moving meter. The ranking is itself learned: when the system's guesses about what would matter turn out right, it trusts them more.

The **Conductor** owns the Agenda, spends the research budget and decides, hourly, what to pick up next. It is also where *curiosity* lives — a protected share of effort for questions with no immediate payoff but high expected learning.

---

## 7. The investigation toolkit

| Technique | In plain words |
|---|---|
| **Decomposition** | break a cost into meters, resources, configurations, decisions |
| **Differential diagnosis** | list *competing* explanations and look for the evidence that separates them |
| **Consumer analysis** | "who reads, calls or depends on this?" — including the infrequent and the invisible |
| **Time-series forensics** | find when a cost changed, and what else changed that day |
| **Cohort comparison** | compare with similar workloads in the estate, or with anonymised patterns from the Commons |
| **Before / after** | check the effect of a past change |
| **Counterfactual replay** | replay history under another configuration — the [Time Machine](04-experiments-and-the-lab.md) |
| **Dependency tracing** | what breaks, or moves, if this changes? |
| **Reading the source** | the code and infrastructure definitions, to find what produces the cost — and to fix it *there* |
| **Reading the contract** | what the agreement and commitments change about the answer |
| **Asking** | the cheapest decisive test, when only a person knows |

Each tactic has a track record per mechanism, so the Detective gets better at choosing.

### Hypotheses, challenge and verdict

Every candidate becomes a hypothesis and follows the [life cycle in the north star](01-north-star.md#5-test--how-it-investigates) — born, triaged, investigated, **challenged**, tested, asked about, parked or split, and finally *confirmed* (a **Case**, or a **Detector** if it is general), *refuted* (a **Lesson** — why it looked true), or dropped. Three details matter:

- **Triage is economic.** "Is this worth a person's time?" is decided early, because a correct finding worth nothing is still noise.
- **The Skeptic is adversarial by design.** It is rewarded for good objections, not for agreement. Its standard questions: *Who else uses this? What happens at the peak? What did the last incident teach? What does compliance require? Is the metric lying — sampled, delayed, missing a consumer?* — and, for every Case, a **pre-mortem**: *"imagine we did this and it went badly; what happened?"*
- **Refuted hypotheses are kept.** "It looked unused because the audit job runs once a quarter" is a lesson that prevents the same mistake in every estate with a quarterly job.

### Evidence grades

Each piece of evidence is graded so a reader can weigh it: **measured** (telemetry, bill, experiment) → **observed** (configuration, history) → **reported** (a person said so) → **inferred** (the AI's reasoning) → **assumed**. A Case lists which of its claims rest on which grade — and what **would change its mind**.

---

## 8. The Case notebook

Every investigation leaves a **notebook**: the question, the hypotheses, the queries and their results, the charts, the experiments, the Skeptic's objections and the verdict — readable by a person, re-runnable by anyone. It is the answer to *"why do you think so?"* A Brief links to it; an Atlas entry cites it; an auditor can replay it. A recommendation with no notebook is not a recommendation.

---

## 9. Bill versus blueprint

Alongside "start from the bill", the system works from the other end. From the architecture — the infrastructure definitions, the diagrams, the documents — it builds an **expected cost model** for each workload: *"given this design and this traffic, the bill should be about X, made of these meters."* Then it compares with the actual bill.

- A **residual** — actual above expected — is a lead: a meter nobody modelled, a default that switched something on, a job that retries, traffic that takes a longer path.
- A **negative residual** is a lead too: something the design assumes exists but does not, or a discount applied that nobody planned.
- A **stable residual** teaches the model; a **growing** one goes straight to the Agenda.

It is the way physicists find a missing planet: the model is good enough that its failures are informative.

---

## 10. The Lesson Book — memory you can read

Everything people teach the system lands in a **Lesson Book** — plain language, human-editable, never hidden inside a model:

```
LESSON  "Weekend idleness is expected in development subscriptions."
SCOPE   the three development subscriptions of team Atlas   (proposed to widen: all development subscriptions — pending)
SOURCE  Maria Janssen, in reply to a card, 2026-09-12
EVIDENCE telemetry shows weekend troughs in all three
EXPIRES 2027-09-12 (review)   STATUS Active · applied 14 times · 0 reversals
```

A lesson has a **scope** (this resource, this team, this organisation, everywhere), an **owner**, **evidence**, an **expiry** and a **track record**. The AI may *propose* widening a lesson (*"remember this for all development subscriptions?"*); a person says yes, no or "only here". Lessons can be disputed, corrected and retired. Because memory is visible, it can be trusted — and because it expires, it cannot quietly rot.

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

1. **Decode** the change into meters, using the Atlas — including the ones nobody remembers: *flipping this switch adds that meter; this replica count multiplies that one; this private connectivity adds data processing*.
2. **Place it in this estate**: the real demand, the real prices, the real rhythm — not list price at an average load.
3. **Return a range, not a number**, with the assumptions that drive it, and a **cost of being wrong**: what happens if the demand is half, or double.
4. **Show the non-cost consequences** next to the cost, using the Well-Architected pillars as the checklist — a saving that costs resilience is a different offer.
5. **Remember it**: the prediction is filed in the Ledger and scored when reality arrives.

This is the engine behind **shift-left**: the cost of a decision shown *at the moment it is made*, in the pull request, the design review and the planning meeting — not three weeks later on the bill.

### A worked example

> A pull request turns on cross-region replication for a data store "for resilience". The Consequence Engine reads the change, decodes the meters from the Atlas — storage in the second region, replication traffic between regions, a higher-priced SKU that the feature requires — and reads the estate: the store holds 4 TB and grows 6% a month; the change rate is high. It answers in a comment on the pull request: *"About €1,900 a month, rising to about €2,600 within a year; €700 of that is replication traffic and depends on the change rate, which is the uncertain part. If this store is not in the disaster-recovery plan for the payments platform, the resilience gain is small; if it is, this is cheap. Alternative: replicate only the two tables the runbook lists — about €480."* The author replies, the AI files the lesson, and the prediction goes in the Ledger.

---

## 12. The first 24 hours in a new estate

No customer-specific training is needed to start, because the world is already known — the Atlas arrives knowing Azure.

1. The Surveyor inventories what it is allowed to see and reads the bill.
2. Every meter on the bill is decoded at once by the Atlas; the grammar labels each as capacity, stock, flow and so on.
3. The Conductor builds the first Unexplained Spend Ledger and the first Agenda: biggest blocks first.
4. The Surveyor drafts intent statements and owners for the largest blocks, with confidence.
5. By the end of the day the owners of the five largest unexplained blocks each receive **one** question — nothing else. The rest of the week is the system *listening*.

---

## 13. Privacy of understanding

The Estate Model and the Lesson Book describe a customer's business and its people. They stay within the customer's own boundary; only *derived, anonymised statistics* — "this kind of advice paid off in 71% of cases" — can ever be offered to the [Commons](07-getting-smarter.md#7-the-commons), and only with the customer's say-so. People-data is handled with care (the system works out who *owns* things, not how well they work), and the detailed rules come with the [guardrails](09-guardrails-later.md).
