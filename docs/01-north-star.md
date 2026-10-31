# Azure Cost in Action — the north star

> **Status:** ideation **v4** · 2026-10-31 · This is the whole idea in one place. Each part has its own deeper document: [studying Azure](02-learning-azure.md) · [the estate and the investigation](03-estate-and-investigation.md) · [experiments and the Lab](04-experiments-and-the-lab.md) · [recommend, act, verify](05-recommend-act-verify.md) · [people and conversation](06-people-and-conversation.md) · [getting smarter](07-getting-smarter.md) · [the outer rims](08-outer-rims.md) · [the learning contract](11-the-learning-contract.md).
> Nothing here is a technical design. It is what we want to exist.

![The living system: five faculties around a shared memory](img/living-system.svg)

## The sentence on the wall

> **Every euro spent on Azure has a reason. This AI learns the reasons — and finds, tests and fixes the euros that have none.**
>
> *A scientist for Azure's economics. Not a rulebook.*

## In one minute

1. **Azure outruns every rulebook.** Hundreds of services, thousands of ways to be charged, changes every week. Cost advice written by people covers the well-known head, misses the long tail, and goes stale the day it is written.
2. **So we do not write the advice. We build an AI that learns Azure's economics for itself.** It reads everything Microsoft publishes, decodes how every meter works and — because documents can be wrong or silent — **tests how things really bill, in a lab of its own.**
3. **It studies each estate like a scientist.** It explains where every euro goes, forms hypotheses about waste, tries hard to disprove them, runs experiments, and only then recommends a change — with the evidence, the alternatives and the consequences on the table.
4. **It works with the people who own things.** In Teams, in email, by voice, in meetings. It asks the cheapest question that settles a doubt, learns from every answer, and changes something only when a human says OK — or inside rules humans wrote.
5. **Everything it learns compounds.** What is true about Azure becomes an open, versioned, *tested* body of knowledge that anyone can use and improve. What is true about your estate stays yours. The longer it runs, the less it has to ask and the more it finds.

**What it is not:** a dashboard; a rulebook with a Teams webhook; a chatbot bolted onto the bill; a list of recommendations somebody typed. It is a long-running research programme with a memory, a lab and colleagues.

---

## 1. The problem behind the problem

**Advice is written by people, and people do not scale.** Every rule in every cost tool exists because someone understood one service well enough to write it down. Azure has hundreds of services and thousands of ways to be charged, and it changes weekly. So the rules cover the services everyone uses — and miss the long tail, where most surprises hide. And each rule is frozen the day it is written.

**Context decides.** The same setting is waste in one estate and the reason the quarter-close works in another. A rulebook cannot know which. Understanding can.

**People act on what they trust.** Owners ignore advice they cannot explain, check or argue with. Trust comes from reasoning you can inspect, evidence you can re-run and a track record you can see.

**Knowledge rots.** Prices move, SKUs appear and vanish, behaviours shift, documents are revised. A static catalogue is a little more wrong every day.

**So the scarce thing is not detection. It is knowledge** — knowing how each service really charges, what really drives each bill, what a change really does, and what is really needed here. Producing and maintaining that knowledge is exactly what an AI with tools, patience, a lab and good colleagues can do at a scale no team of people can.

---

## 2. The big idea: science, industrialised

We build an AI that **does science on Azure's economics**. The scientific method is not a metaphor here; it is the operating system.

| Science | What the system does |
|---|---|
| **Observe** | Reads the bill, the estate, telemetry — and everything the world has written about Azure |
| **Ask** | Keeps an **Agenda** of open questions: what is unexplained? what is surprising? what just changed? |
| **Hypothesise** | "Spend grew 9% a month with no change in the design." "That default flipped a meter on." "This commitment no longer covers what we run." |
| **Predict** | Writes down what should be true *if the hypothesis is right* — before looking |
| **Test** | Analyses data, replays history, runs experiments in its Lab, asks the cheapest decisive question |
| **Peer review** | A sceptical agent tries to break it; humans review what becomes "known" |
| **Publish** | Findings become Atlas entries, detectors and Moves — and, when general, go to the open **Commons** |
| **Replicate** | Knowledge is re-tested on a schedule; claims that stop reproducing are retired |
| **Apply** | A tested **Move** changes something, with the owner's OK |
| **Measure** | Predictions are scored against what happened; the system keeps a **report card** |

### What it knows: three kinds of knowledge, one memory

| | Is true for… | Lives in | Learned from |
|---|---|---|---|
| **World knowledge** | everyone on Azure | the **Atlas** | documents, price lists, schemas, the Lab, the community |
| **Estate knowledge** | this one customer | the **Estate Model** and the **Lesson Book** | the bill, telemetry, configuration, code, conversations |
| **Experience** | "what happened when we did X" | the **Experiment Ledger** and the outcome record | experiments, trials, results of real changes |

And a fourth, quieter kind: **knowing how sure it is**, and **what is worth learning next**. Every claim carries its receipts, its *scope* and a confidence; the Agenda ranks questions by what finding the answer is worth.

### What "learning" means here

Storing a lesson is not learning. A system has learned only if something that governs its future behaviour has *changed*, in a way that improves its results on a test it could not game. Six things change, each by a defined process and each tested on the Exam: **its beliefs about Azure** (claims whose evidence accumulates, and which count as trusted only once replicated); **what it chooses to do next** (a policy that learns which questions, sources and experiments pay off); **compiled knowledge** (Detectors and Moves that are written, back-tested, run in shadow and expire); **its predictions of consequence** (a causal model refitted from interventions); **its understanding of one estate** (people's testimony, widened only with corroboration); and **its own method**. It is measured against *retrieval only* and against the *expert-written seed* — so we can tell what it added. [The learning contract →](11-the-learning-contract.md)

### How it works: five faculties, not five stages

The picture at the top is not a pipeline. Five faculties run **at the same time**, around one shared memory, and each feeds the others:

| Faculty | In one line | Agents |
|---|---|---|
| **STUDY** | Learns Azure — every service, meter, price, change | Scholar, Cartographer |
| **SURVEY** | Understands this estate — what exists, what it is *for*, who owns it, what is sacred | Surveyor |
| **TEST** | Investigates and experiments — hypotheses, evidence, refutation, the Lab | Detective, Skeptic, Experimenter, Economist |
| **ACT** | Changes things with people — conversation, Moves, verification | Diplomat, Engineer |
| **GROW** | Gets smarter — scores itself, sits exams, curates knowledge, shares it | Auditor, Examiner, Librarian |

A few ways they feed each other — there is no "first":

- A **new service profile** (STUDY) immediately sends the Agenda hunting for which resources in which estates it concerns (SURVEY → TEST).
- A **human's answer** (ACT) corrects the Estate Model (SURVEY) and may refute a belief in the Atlas (STUDY).
- An **experiment** (TEST) settles a contradiction between two documents (STUDY) and sharpens a prediction (GROW).
- An **exam score** (GROW) tells STUDY where its knowledge is thin, so it learns that next.

### Four clocks

The same system runs on four clocks at once:

| Clock | Tempo | What happens |
|---|---|---|
| **Watch** | minutes to hours — on fast signals (metrics, activity, deployments); the bill itself lags by hours to days | spend that suddenly runs away; a meter that should not be moving |
| **Cases** | days to weeks | investigate → decide with an owner → change → verify |
| **Strategy** | months | architecture, commitments, platform shifts, price changes |
| **Learning** | always | reading, experiments, exams, re-checking what it thinks it knows |

![Four clocks](img/four-clocks.svg)

---

## 3. STUDY — how it learns Azure

Studying Azure means building and tending the **Atlas**: a living, open, versioned map of *how Azure charges and what drives the charge*. For every service the Atlas holds a **Service Cost Profile** — a dossier in plain language, every line backed by receipts (sources, experiments, dates, confidence). [Full detail →](02-learning-azure.md)

Four moves, repeated forever:

1. **Read.** Everything Microsoft publishes — documentation, price lists, release notes, limits and quotas, architecture guidance — and the machine-readable surfaces: price meters, resource schemas, metric catalogues, export formats. Plus the community. The output is not summaries but **claims with receipts**: *"this meter bills per started hour — source, date, quote."*
2. **Decode.** Every meter is explained with the **Cost Grammar**: *how does the money arise* (capacity? consumption? stock? flow?), *what shows it is really needed* (the demand signal), *what can be changed* (the levers) and *what changing it trades away*. The grammar is what lets the AI reason about **a service it has never seen** — it recognises the shape of the meter, not the name of the product.
3. **Test.** Documents are evidence, not truth. Anything load-bearing, contradictory or silent goes to **the Lab**: deploy it, drive load, watch the meters appear in the usage data, write down what really happened — including the delays, minimums, rounding and hidden meters no document mentions.
4. **Keep fresh.** Every claim carries a re-check recipe — **knowledge CI**, unit tests for facts. When Microsoft changes a price, retires a SKU or alters behaviour, claims fail their re-check, profiles are marked stale, and every affected estate is told — in *both* directions: *"this just got more expensive for you"* and *"this just got cheaper — move?"*

### The Cost Grammar — fourteen ways money arises

Every meter, in every service, is one or a few of **fourteen mechanisms**: *capacity* (you pay for what you provision), *consumption* (what you use), *stock* (what you keep), *flow* (what moves), *feature* (a switch turns on a meter), *multiplier* (dimensions multiply), *tier / step* (price jumps at thresholds), *commitment* (pay ahead for a discount), *time quantum* (billing granularity), *coupling* (a thing drags in other meters), *leftover* (billing continues after the parent is gone), *rate and benefit* (the price per unit is negotiable), *allowance* (an included amount, then paid) and *time cliff* (a price changes on a date). Each comes with a question to ask, a **signal of real need** and typical levers — [the full grammar is in 02](02-learning-azure.md#2-the-cost-grammar--how-it-reasons-about-services-it-has-never-seen). It is the seed of a living taxonomy: when the AI meets a meter that fits none of these, it proposes a new mechanism, and the humans who review knowledge decide whether it earns a place.

### A day-zero story (the service is invented)

*A story, not a measurement.* Tuesday 09:00: Microsoft announces **Azure Prism**, a managed retrieval service. By 10:30 four parallel readers have decoded six meters with the grammar — a *Prism Unit* is **capacity**, a *Query Unit* **consumption**, *snapshot GB-months* **stock**, *replicas* a **multiplier**, the private-link add-on **coupling**, the preview price a **time cliff** — and found two documents that disagree about whether scaling down refunds a started hour. The Experimenter writes its prediction down first and takes the disagreement to the Lab. By Wednesday morning the prediction is confirmed, a second trap (snapshots keep billing after an index is deleted) is found, and a **provisional Profile v0.1** is published, every line linked to its receipts and marked mechanism-verified in the Lab only. The Agenda then asks *which resources in which estates are Prism?* — two preview deployments, one team — and the Diplomat asks that team one question: **"This goes from free to paid on 1 March. Do you want a heads-up plan?"** Nobody wrote a Prism rule. A real example, read on the day this was written, is in [studying Azure, §6](02-learning-azure.md#6-day-zero--a-new-service-feature-or-price-change).

---

## 4. SURVEY — how it understands an estate

The **Estate Model** is the AI's understanding of one customer. Not an inventory — a *story*: what exists, how it connects, **what it is for**, who needs it, when it is busy, what must never be touched. [Full detail →](03-estate-and-investigation.md)

- **Reads widely** (with permission): the bill, the resource inventory, configuration and change history, telemetry, the native recommendations, budgets and anomaly alerts (Advisor and Cost Management), infrastructure-as-code and the repositories behind it, wikis, architecture diagrams (it can read pictures), tickets and post-mortems, the commercial agreement and price sheet, the organisation chart.
- **Infers intent.** A workload's *purpose* is rarely written anywhere; the AI assembles it from names, tags, deployment history, traffic shape, code and conversation — and confirms the important guesses with a human.
- **Learns rhythms.** Daily, weekly, seasonal, and the *business calendar*: the quarter-close, the launch, the audit week. A quiet resource in March can be the star of November.
- **Follows the directory.** Owners from tags, directory, commit and deployment history, role assignments and ticket traffic; managers, delegates, presence, time zones, languages; and a **named custodian** for things that have no owner at all.
- **Remembers what people taught it** in a **Lesson Book** — human-readable, scoped, expiring, editable. Memory you can read.

**Where Cost Management and Advisor fit.** They are *inputs* and *a baseline to beat* — never ignored, never trusted blindly. Their findings enter the Agenda as leads and are checked like any other claim (Advisor's own documentation says its VM savings are computed at retail rates and ignore existing commitment coverage). Part of the value is simply **closing the loop** on what Azure already recommends — the owner who never opens a recommendations blade gets a short, specific, explained question — and the rest is everything those tools cannot see. [What happens to an Advisor card →](05-recommend-act-verify.md#1a-what-happens-to-an-advisor-card--and-to-a-budget-alert)

---

## 5. TEST — how it investigates

It starts from the money. Every euro on the bill should become **explained**: the AI can say *what it is for, who needs it, how much of it is needed, and what it would take to need less*. What it cannot yet say is the **Unexplained Spend Ledger** — and that ledger is the engine of the **Agenda**. [Full detail →](03-estate-and-investigation.md)

The Agenda is the AI's curiosity, ranked by *what finding the answer is worth*:

- spend nobody can explain, and spend that is growing;
- a gap between **bill and blueprint** — a cost model built from the architecture, compared with the bill; the residual is a lead;
- a Profile that was just published or a price that just moved: *which of our things does this touch?*;
- a belief it relies on that is old, high-impact and weakly verified;
- a **hunch** from a human: *"I bet the test clusters sit idle at weekends — look into it."*

Each question becomes a **hypothesis** with a life of its own — not a line on a conveyor belt:

```mermaid
stateDiagram-v2
    [*] --> Born: from the Agenda, a pattern, a surprise or a human hunch
    Born --> Triage: is it worth the effort?
    Triage --> Investigating
    Triage --> Dropped: not worth it
    Investigating --> Challenged: the Skeptic attacks it
    Challenged --> Investigating: it survives, with new questions
    Challenged --> Refuted: it breaks
    Investigating --> Experiment: evidence is not enough
    Experiment --> Investigating: results
    Investigating --> AskingAHuman: only a person knows
    AskingAHuman --> Investigating: the answer arrives
    Investigating --> Waiting: needs more history
    Waiting --> Investigating: the clock has run
    Investigating --> Split: it was really two ideas
    Split --> Born
    Investigating --> Confirmed: it holds
    Confirmed --> Case: worth a human's attention
    Confirmed --> Detector: general enough to watch for everywhere
    Refuted --> Lesson: why it looked true is knowledge too
    Case --> [*]
    Detector --> [*]
    Lesson --> [*]
    Dropped --> [*]
```

**The Skeptic** is an agent whose only job is to break the case: *who else reads this? what happens at the peak? what did the last incident say? what does compliance require? is the metric lying — sampled, delayed, missing a consumer?* A refuted hypothesis is not waste: **"why it looked true"** is some of the most valuable knowledge the system keeps.

**The Consequence Engine** works in both directions. *Backwards:* why is the bill what it is? *Forwards:* **what happens to the bill — and to reliability, performance and security — if we do X?** For a design review, a pull request, a migration, a retention policy, a growth spike, a price change. It knows the hidden consequences — *flipping this switch adds that meter; that replica count multiplies this one* — because the Atlas does.

### A worked investigation

> *The bill for a customer-facing app has crept up 9% a month for four months, with no change in traffic and no change in the design anyone remembers.* The Agenda ranks it high: **unexplained, and growing.** The blueprint model — built from the infrastructure code — expects a modest bill; the **residual** is a data-transfer meter it has no line for. The Atlas knows that meter: **flow, priced by path** — traffic that crosses regions is billed, traffic inside a region is not.
> The Detective finds the change: on 9 October a deployment moved the web tier to a second region "for latency"; the database stayed behind, so every request now crosses regions. The hypothesis — *an unintended coupling, not growth* — predicts that the transfer meter tracks request volume. It does.
> The Skeptic asks: *was this planned — a half-finished migration, a disaster-recovery design?* The pipeline history says the database move is still "queued". *Would moving the database fix it, and at what risk?* The **Time Machine** replays last month's traffic against a co-located layout in the Lab: latency improves and the meter disappears; the Consequence Engine adds the migration cost and a week of risk — as evidence under stated assumptions, not as proof.
> The directory points to the platform team. The Diplomat asks **one** question: *"Is the database move still planned for this quarter?"* — "Yes, in January."
> The Brief offers three options: wait for January and accept about €2,300 a month until then; add a read cache in the second region now (cheap, partial); or move the database now with the migration Move. The system also writes a **Lesson** — *this team stages regional moves: web tier first, data later* — and a Detector idea: *a tier moved without its data.*

---

## 6. TEST — how it experiments

Reading and analysing is not enough. Sometimes the only way to know is to try. [Full detail →](04-experiments-and-the-lab.md)

| Experiment | It learns | Where |
|---|---|---|
| **Billing experiment** | how a service *really* bills: granularity, minimums, rounding, delays, hidden meters | **the Lab** |
| **Signal experiment** | which telemetry actually reflects demand — and where there is a blind spot | the Lab |
| **Prediction (shadow)** | whether its beliefs hold: it predicts, then compares | anywhere |
| **Replay and counterfactual** | what *would have* happened with another configuration | **the Time Machine** |
| **Trial** | what a small, reversible change does in practice | on one real resource, with consent |
| **Question** | the one thing only a person knows | **the cheapest experiment of all** |

**The Lab** is a dedicated, budget-capped sandbox subscription where the agents are allowed to create, break and delete things, drive synthetic load and watch the bill form. It is how Azure's economics become *measured* rather than *quoted*. It also runs a **wind tunnel**: benchmark rigs that map the *cost / performance frontier* of a service, so a recommendation says "this configuration costs 40% less and, in our tests, stays inside your latency target" instead of "the spec sheet says so".

Experiments are designed like experiments: a hypothesis, a **prediction written down first**, a budget, a stop condition, an analysis plan. They are chosen by **value of information** — cheapest decisive test first: *a question, then data already collected, then replay, then the Lab, then a live trial.* **Surprises** — the gap between prediction and result — are logged as first-class knowledge. Every result carries an **external-validity envelope** (what was held constant, what scale was tested, what was *not*): replays and Lab results are counterfactual evidence under stated assumptions, and only a guarded trial or observation after the change supports "safe in this estate". The Lab pays its own way: if learning costs more than it is worth, it stops.

---

## 7. ACT — how it works with people

This is where the AI meets owners, FinOps leads, finance partners, engineers. [Full detail →](05-recommend-act-verify.md) · [People and conversation →](06-people-and-conversation.md)

**A Brief, not a recommendation.** What it proposes, why it thinks so (and how to check), the alternatives including *do nothing*, the consequences with ranges, what it has already tested, what would change its mind, the effort, how reversible it is, exactly what it will do on *yes*, and how everyone will know it worked.

**A conversation, not a notification.** Teams cards for decisions and teaching, email for digests and formal approvals, a call or a text only when it is truly urgent, a participant in the monthly cost review — an AI in the room (voice, even an avatar) that can pull up its reasoning and answer "why?" live. Every message carries **Explain** (show the reasoning and the receipts), **Challenge** (red-team this) and **Teach** (here is something you should know).

**Teachable.** Every answer is a lesson. *"Not now — this runs the quarter-close"* becomes a calendar. *"That's our DR environment"* becomes a scope — and the AI proposes the generalisation and asks whether to remember it for this resource, this team or everywhere.

**Moves.** Actions are **Moves**: tested, versioned, reviewable recipes — resize, schedule, tier, clean up, open a pull request against the infrastructure code, propose a policy, prepare a commitment purchase. The AI can **write new Moves**, test them in the Lab, and offer them for human review — the way a good engineer contributes a tool to the team.

**Autonomy is earned.** The ladder is short: *observe → advise → assist (one tap) → autopilot inside a rule a human wrote*. Autopilot is granted as a **credential per domain** — "storage tiering in non-production, up to this value" — on the strength of the report card, by people, and revoked when regret appears.

**Purchases get the most care.** Reservations and savings plans are prepared by the AI, approved by two named humans with different hats, and then executed by the AI on their say-so — never on its own judgement.

**Verification.** Every change is checked against the prediction made before it: the saving is measured against a counterfactual, regret and "boomerangs" (the change reversed within weeks) are recorded, and drift is guarded — preferably by **fixing the source** (a pull request on the infrastructure code), so the next deployment does not quietly undo it.

---

## 8. GROW — how it gets better

[Full detail →](07-getting-smarter.md)

- **Everything is a prediction.** Every recommendation says what will happen and by when. The outcome scores it. Over time the AI keeps a *calibration record*: when it says 80%, how often is it right?
- **The Lesson Book** keeps what people taught it — with scope, expiry and the evidence — so it can be read, corrected and retired.
- **The Exam.** An independent agent sets exams the system cannot see in advance: *rediscovery* (hide known waste in synthetic and real-but-labelled estates — does it find it with no rule for it?), *new-service races*, *transfer* (learn on service A, test on service B), *teachability*, *explanation quality*, *communication*. Results go on a **report card** kept inside the organisation — including what it is bad at. (An open benchmark is separate; see the Commons.)
- **It learns how to learn.** Which sources yielded true claims? Which investigation tactics paid off for which kind of service? Which phrasing gets a useful answer? The system tunes its own *method*.
- **The Commons.** The world-knowledge half — Atlas, Moves, lab recipes, detectors, exam questions — is **open source** and versioned, maintained by the AI *proposing changes for human review* and by the community. Estate knowledge never leaves the customer. Even the *outcome statistics* ("how often does this advice pay off?") can be shared without sharing a byte of data. The knowledge is the open-source asset, not just the code.

---

## 9. The cast

A small society of specialists — more like a research group than a pipeline.

| Agent | Faculty | What it does | What it learns from |
|---|---|---|---|
| **Scholar** | STUDY | Reads the world; extracts claims with receipts; watches for change | sources, diffs, announcements |
| **Cartographer** | STUDY | Decodes meters; keeps the Atlas coherent; evolves the taxonomy | claims, Lab results |
| **Surveyor** | SURVEY | Builds the Estate Model; resolves owners; infers intent and rhythms | the estate, people |
| **Detective** | TEST | Forms and tests hypotheses; writes case notebooks | evidence, outcomes |
| **Skeptic** | TEST | Tries to refute everything, including the Atlas | counter-examples |
| **Experimenter** | TEST | Designs and runs experiments; runs the Lab; keeps the Ledger | its own predictions |
| **Economist** | TEST | Quantifies options, consequences and trade-offs; searches the design space | outcomes |
| **Diplomat** | ACT | Talks to people; asks, explains, negotiates, *teaches and is taught* | answers, reactions |
| **Engineer** | ACT | Writes, tests and runs Moves; opens pull requests; guards against drift | results of changes |
| **Auditor** | GROW | Verifies outcomes against predictions; measures regret and cost-to-run | the ledger |
| **Examiner** | GROW | Sets independent exams; publishes the report card | exam results |
| **Librarian** | GROW | Curates the Lesson Book and the Commons; guards provenance | review outcomes |
| **Conductor** | all | Runs the research programme: Agenda, budgets, priorities | everything |

---

## 10. What the learning looks like from the outside

The system is only trustworthy if its learning is *visible*. The clearest window is a short letter every Monday; the cards, the AI in the meeting and the way an Atlas change looks to a reviewer are in [people and conversation](06-people-and-conversation.md) and [studying Azure](02-learning-azure.md#12-the-atlas-seen-from-outside).

**The Monday email — "What I learned this week"**

```
This week I learned
  · A new service profile: Azure Prism (provisional — review?)        [3 claims verified in the Lab]
  · A belief I held was wrong: "scaling down refunds the hour" — Refuted (2 experiments)
  · 4 lessons from your team, 1 I'd like to generalise: "Weekend idleness is expected
    in dev subscriptions" — remember for all dev subscriptions?        [Yes] [Only this team] [No]
Today I'm wondering about
  · Why storage in the payments subscription grows 9% a month with no matching architecture
  · Which of your 31 database servers are sized for the 2024 migration
My report card: predictions 81% right (I said 79%) · explained spend 72% (+3) · I asked you
11 questions this month (was 19)
```

---

## 11. A first day, a first quarter, a first year

**The first 24 hours in a new estate.** The Surveyor inventories and reads the bill. The Atlas — already knowing Azure — decodes every meter on it at once. The Conductor builds the first Unexplained Spend Ledger; the Detective starts with the biggest unexplained blocks. No customer-specific *model training* is needed to start — the world is already known — and the first thing the AI learns about a customer is its own price book and agreements. Once the bill data has caught up (hours to days), the owners of the five largest unexplained blocks each receive **one** question.

**The first quarter.** The Estate Model fills in: intent for the main workloads, a calendar, an owner for almost everything. The first Briefs go out; a few are accepted, several declined *with reasons* — each reason becomes a lesson. Explained spend climbs. The first Moves are tried in non-production; the first verified savings are measured against counterfactuals. The system asks fewer questions each week.

**The first year.** The Atlas has hundreds of verified profiles and a refuted-beliefs shelf. The report card shows calibration improving. Some domains have earned autopilot credentials; others have not, and the card says why. When Microsoft ships something, the Atlas has a provisional profile within hours and the estate is told what it may mean *for it* — firm advice follows once a bill confirms it. A part of the Commons has been used by other organisations. The system now finds things no one has a name for — and **names them**, as new Atlas mechanisms and detectors, for human review.

---

## 12. The outer rims

A taste of what the north star opens up. Detail and many more in [the outer rims](08-outer-rims.md).

- **Dreaming.** Overnight the system explores alternative architectures for your biggest spend in the Lab and wakes up with a map of options: *"I tried 40 configurations; here is the frontier."*
- **Law-finding.** From hundreds of experiments it infers regularities across services — *"a thing that is stopped but not released often keeps its most expensive meter"* — and is tested on whether they predict services it has never touched.
- **Self-writing Detectors.** For every confirmed, general finding the AI writes a cheap, scoped, expiring *lead generator*, back-tests it and proposes it for review: expensive reasoning once for the pattern, cheap nominations afterwards — with the ambiguous cases still going to a Detective.
- **The Forger.** An adversary that forges clever waste and plausible decoys to fool the Detectives, so the Exam stays hard.
- **The Hunch Box.** Anyone can submit a hunch; the system investigates and reports back with evidence — and the good ones become Detectors.

---

## 13. Why this is an agent idea, not a chatbot idea

A chatbot answers. This system **runs research programmes**: long-lived, multi-step, partly parallel, resumable; it **remembers**; it uses **tools** (price lists, queries, the Lab, change recipes); it **delegates** among specialists; it is **evaluated** on exams it cannot see; its work is **traced** so it can be replayed and reviewed; and it works alongside humans who teach, decide and review. Those are the ingredients agent platforms such as Microsoft Foundry are for — which is why Foundry is the natural home we imagine. The *workflows* are research programmes and campaigns, not scripts. Chat is one way to ask the system a question; it is not the product.

The product will run on Microsoft's platforms and technology. The *ideas* may come from anywhere — [the research that inspired this](research/inspirations.md) ranges from agents that write and keep their own skill libraries, to agents that keep memory and reflect on it, to automated scientific discovery.

**Built on Microsoft's own frameworks.** The Well-Architected pillars are the checklist for every consequence the system shows (a saving that costs reliability is a different offer); the Cloud Adoption Framework's Govern and Manage disciplines are the operating context it works inside; and the FinOps Framework's *Inform → Optimize → Operate* lifecycle is the capability map for what it does. [How the idea lines up →](09-guardrails-later.md#how-the-idea-lines-up-with-caf-waf-and-the-finops-framework)

---

## 14. Where humans stay in charge

Human-in-the-loop is not a button on the end. It is five places in the design. Detailed guardrails come in a later phase — [what we will design then](09-guardrails-later.md) — but these five are the spine.

1. **What counts as known.** Knowledge becomes *trusted* only after peer review — by the Skeptic and by people — and carries its receipts forever.
2. **What it spends to learn.** The Lab and every experiment have budgets people set.
3. **What it changes.** Every change has a human's OK, or a rule a human wrote — and purchases always have named humans.
4. **How much autonomy it earns.** Credentials per domain, granted and revoked by people, based on the report card.
5. **How it speaks.** Tone, timing and attention limits are set with the people it talks to. Silence is never consent.

---

## 15. The honest limits

The design does not hide where learning can fail; it builds the answers in. Documents and bills disagree, and the Lab cannot reproduce everything ([studying Azure, §8](02-learning-azure.md#8-knowing-what-it-does-not-know)); a claim verified in a Lab is not verified on a customer's bill ([the learning contract, §2](11-the-learning-contract.md#2-verified-has-a-scope)); replays are evidence, not proof ([§3](11-the-learning-contract.md#3-counterfactual-evidence-not-proof)); people are witnesses, not oracles ([§4](11-the-learning-contract.md#4-people-are-witnesses-not-oracles)); an exam can be gamed, so it is independent, rotated and audited, and no single number is optimised alone ([getting smarter, §3 and §5](07-getting-smarter.md#3-the-exam)); and the system's own cost is counted against its savings ([§6](11-the-learning-contract.md#6-does-it-pay-for-itself)).

---

## 16. How we will know it is learning

| Measure | It should… |
|---|---|
| **Explained spend** — the share of spend whose purpose, need and cost-to-reduce the system can state with confidence | rise |
| **Time to profile** a new service, feature or price change | fall — to a provisional mechanism profile in hours (commercial verification waits for the bill) |
| **Rediscovery rate** on the Exam — known waste found with no rule for it | rise |
| **Transfer** — right after one correction, on a service it has not seen | rise |
| **Beating the baselines** — against retrieval-only and the expert-written seed | widen |
| **Calibration** — "80% sure" means right 80% of the time | tighten |
| **Atlas coverage and freshness** — meters on real bills with a verified profile; median age of claims | broaden and stay young |
| **Decision burden** — a person's minutes per decision, and cases waiting on an answer | fall: it learns, so it asks less, and asks better |
| **Surprises per month** | stay above zero: it is still discovering |
| **Verified net savings** — after what the system itself costs to run | rise |
| **Value per human minute** — verified value for each minute of a person's attention | rise |

### The founding exam

The two findings that started this project are exam questions like any other, with no special place in the design. They are described, and marked, in [getting smarter, §8](07-getting-smarter.md#8-the-founding-exam).

---

## Glossary

| Term | Meaning |
|---|---|
| **Atlas** | The living, open, versioned map of how Azure charges and what drives the charge |
| **Service Cost Profile** | The Atlas's dossier on one service: how it bills, its levers, tells, traps, evidence |
| **Cost Grammar** | The mechanisms by which money arises (capacity, consumption, stock, flow …) × the signal of real need × the levers |
| **Estate Model** | The AI's understanding of one customer's estate, including intent, rhythms and people |
| **Lesson Book** | What people taught the system — scoped, dated, expiring, editable |
| **Agenda** | The ranked list of questions the system is working on |
| **Explained spend** | Spend whose purpose, need and cost-to-reduce the system can state with confidence |
| **Hypothesis / Case** | A testable claim about cost or waste / one that survived and deserves a human |
| **Skeptic** | The agent whose job is to break the case |
| **Consequence Engine** | Answers "what happens to the bill — and to risk — if we do X?" |
| **Lab** | The sandbox where agents run billing and signal experiments |
| **Time Machine** | Replay of history under alternative configurations |
| **Wind tunnel** | Benchmark rigs that map a service's cost/performance frontier |
| **Experiment Ledger** | The system-wide register of predictions and results (each experiment's page is a **Lab Notebook**) |
| **Brief** | The decision document a human receives |
| **Move** | A tested, versioned, reviewable change recipe |
| **Credential** | Earned, revocable permission for autopilot in one domain |
| **Exam / report card** | Independent evaluation of the system / its record, kept inside the organisation |
| **Knowledge CI** | Re-check recipes that keep every claim honest |
| **Commons** | The open, shared half of the knowledge |
| **Claim and scope** | One statement about Azure with its receipts — and the region, offer, load and date it was tested in |
| **Mechanism-verified / commercially verified** | Matched its prediction in a named Lab scope / reconciled against one customer's own bill |
| **Detector** | A cheap, scoped, expiring lead generator compiled from a confirmed finding; it nominates, investigators decide |
| **Terrarium** | Miniature estates with planted waste and decoys, for exams and Detector back-tests |
| **Unexplained Spend Ledger** | The part of the bill the system cannot yet explain — the engine of the Agenda |
