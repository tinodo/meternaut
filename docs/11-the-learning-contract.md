# The learning contract — what changes when it learns

> **What this answers:** *The north star says the AI "learns". What exactly changes when it does — and what evidence would let us say it really did?*
> Storing a lesson is not learning. A system has learned only if **something that governs its future behaviour has changed, in a way that improves its results on a test it could not game.** This page names the things that change, what each is made of, how it is updated, when it is relied on, and how it is tested.
> Part of the [north star](01-north-star.md). Idea-level: the contract, not the implementation.

---

## 1. Six things that change

| # | What changes | Made of | Evidence it consumes | How it updates | Relied on when | Tested by |
|---|---|---|---|---|---|---|
| **1** | **Beliefs about Azure** — the [Atlas](02-learning-azure.md) | *claims*, each with a [scope](#2-verified-has-a-scope) and a confidence | documents, price lists, specifications, Lab results, real outcomes | evidence for and against each scoped claim accumulates; every kind of source has a learned reliability; conflicting evidence lowers confidence *and* triggers a Lab test | it has been **replicated** across conditions and **reviewed**, not merely read — and, before it backs advice for an estate, **commercially verified** there ([the gates](#the-gates--one-word-is-not-enough)) | predicting meters and behaviours on held-out services; transfer; regression |
| **2** | **What to do next** — the Agenda, tactics, experiments, wording | a *policy* for choosing: which question, source, tactic, experiment or phrasing | outcomes: what a choice turned out to be worth, per euro and per human minute | each option keeps a running estimate of verified value; most effort goes to the best estimate, a **protected share explores** the rest (the curiosity budget) | its choices beat a random or fixed order in ablations | A/B and ablation runs in the Terrarium and shadow estates |
| **3** | **Compiled knowledge** — Detectors, Moves and the investigation recipes the Detective reuses | *code* with a test | a confirmed finding, its data, and the checks that would have caught it | written → back-tested → tested in the Lab → run in shadow → active; carries its **validity domain, blind spots and expiry** | shadow precision and harm record are good enough | held-out cases, decoys, the Forger |
| **4** | **Predictions of consequence** — the [Consequence Engine](03-estate-and-investigation.md#11-the-consequence-engine--what-happens-to-the-bill-if) | a *causal model* of what drives cost, reliability and performance, with explicit assumptions | interventions in the Lab, natural experiments, trials, realised outcomes | structure and parameters are refitted from *interventions* and comparison groups, not only from correlations | its calibration record in that domain is good | predicted vs realised, scored with proper scoring rules |
| **5** | **Understanding of one estate** — the Estate Model and Lesson Book | *testimony* from people (attributed, scoped, expiring) and observation | what people say, what telemetry shows | testimony is adopted provisionally and **widened only with corroboration** | it has survived contact with evidence, and its owner re-confirms | the teachability exam; correction rate |
| **6** | **The method itself** — procedures, model routing, how it speaks | procedures and prompts as versioned artefacts | exam results, ablations, the report card | the system *proposes* a change; the change is tested; people approve | it improves the held-out exam without hurting anything else | the Exam, with the Goodhart watch |

Two things the table does **not** claim: that an AI model's weights are retrained (almost none of this needs it), or that memory alone is learning. Rows 1–5 are *knowledge that a defined process updates*; row 6 is the process itself.

---

## 2. "Verified" has a scope

Reviewers rightly pointed out that "verified" hides a great deal. A Lab can establish that a meter appears and behaves as predicted *in the Lab*; it cannot establish what a particular customer pays. So there are **two kinds of verified**, and they are never interchangeable:

| Kind | Meaning | Scope it names |
|---|---|---|
| **Mechanism-verified** | the claim matched its written prediction in a *named Lab scope* | service · SKU · API version · region · offer · feature set · load condition · date · test environment |
| **Commercially verified** | the claim has been reconciled against *one customer's own bill* | that customer's price level (list, contracted or effective), agreement treatment, region, billing lag and allocation rules |

Consequences that run through the design:

- A **new service's first profile is a *provisional mechanism profile***. It can raise questions, start watches and tell people what to look at. It **never produces savings advice** for an estate until it has been commercially verified there.
- Every Atlas claim carries its **scope vector**. A claim seen once is weak; a claim that holds across five regions and three agreement types is strong; a claim that fails somewhere has *learned where it does not hold* — which is itself knowledge.
- The [Commons](07-getting-smarter.md#7-the-commons) distributes *scoped claims and the recipes to re-test them*, never "universal" facts.
- Speed claims are about the **draft**: a provisional mechanism profile within hours of an announcement is an aspiration; commercial verification waits for a bill (hours to days) and for the customer's own export.

The full life of a claim — from *heard* to *mechanism-verified*, *replicated*, *commercially verified* and *stale* — is drawn in [studying Azure, §4](02-learning-azure.md#4-from-reading-to-knowing-claims-receipts-life-cycle). What a general claim can be compiled into — a Detector or a Move — has its own life cycle, in [the Lab, §13](04-experiments-and-the-lab.md#13-dreaming--consolidation-while-the-world-is-quiet).

### The gates — one word is not enough

"Trusted" is never used alone, because different things must be true before different uses. Each gate is a separate question with its own evidence:

| Gate | The question | Evidence | Granted by | What it allows |
|---|---|---|---|---|
| **Replicated** | has it held in more than one condition, or when someone else re-ran it? | other regions, agreements and dates; an independent re-run | the Lab; another lab or organisation in the Commons | being offered beyond a draft |
| **Reviewed** | has someone tried to break it, and has a person with standing read it? | the Skeptic's attack; a maintainer's or an owner's review | the Skeptic and a person | being relied on to start a watch, ask a question or nominate a lead |
| **Commercially verified** | does it match *this* customer's own bill? | reconciliation against the customer's export and price book | the Economist, open to Finance's challenge | being the basis of a *savings* claim for that estate |
| **Credentialed** | has it earned permission to act on its own, in this domain? | the Move's record, the credential exam, shadow results | people; it demotes itself when it slips | a Move running without a human OK |

---

## 3. Counterfactual evidence, not proof

Replays, wind-tunnel frontiers and Lab results are **counterfactual evidence under stated assumptions**. The word *prove* is not available to them: production has rare traffic, quota contention, dependencies, commitments, human operations and untested interactions that no replay contains. So every such result carries an **external-validity envelope** — what was held constant, how faithful the traffic was, what scale was tested, which interactions were *not* tested, which agreement was assumed.

Only two things may support **"safe in this estate"**: a *guarded trial* (one small reversible change, with a guard metric and an owner who said yes) or *observation after the change*. Everything before that is evidence that raises or lowers confidence.

The Consequence Engine is therefore built as a **causal model**, not a table of correlations. Where it can, it learns from *interventions* (in the Lab, in trials), and from **natural experiments** — a team changes something for its own reasons, and the system compares before and after against a matched group of untouched resources (the difference-in-differences idea, in plain words: *how much did they diverge, beyond what both would have done anyway?*). Where there are no good comparison resources, it says so and widens the interval.

---

## 4. People are witnesses, not oracles

What a person says is **testimony** — attributed, dated, scoped, and fallible. A departing owner describes an obsolete rhythm; an engineer answers "not mine" because it is easier; a participant states a constraint with confidence and no source. So:

- A statement is adopted **provisionally**, at the scope it was given (*this resource*, not *everything of this kind*).
- It is **widened only with corroboration**: telemetry that agrees, a second person, repeated outcomes. A claim about ownership, intent or constraints that would change a decision is *checked*, not just recorded.
- It **expires**, and it can be re-asked cheaply when evidence changes.
- Success is **decision burden**, not question count: how much of a person's time a decision cost, how many cases wait on an answer, and how often an answer later needed correcting.

---

## 5. What "better" is measured against

The seed matters. A few expert-written Profiles and the Cost Grammar bootstrap the system, and any honest test of *learning* must separate **what we wrote** from **what it added**:

| Baseline | What it is | What beating it shows |
|---|---|---|
| **Retrieval only** | the same sources, no experiments, no feedback | the learning is more than search |
| **The expert seed** | the hand-written Profiles and Grammar, frozen | the system adds knowledge beyond what we gave it, over time (a learning curve) |
| **A practitioner** | an experienced FinOps person with the same access | it is useful in practice, not only on paper |

A system that cannot beat *retrieval only* on held-out billing behaviour — and show **transfer** after a single correction — is a search engine with a good memory. This is the test the [first experiment](10-what-next.md) is built to run.

---

## 6. Does it pay for itself?

Savings are only half of the ledger. The all-in **cost to serve** includes models, the Lab, orchestration, the people who review and reconcile, Finance's time, and upkeep of the Commons. It is counted against **verified incremental value** — savings *beyond what the customer's existing tools and people would have found anyway*.

- **Value per human minute** and **cost per verified euro** are on the [report card](07-getting-smarter.md#4-the-report-card), next to the savings.
- There is a **minimum opportunity size**: below some level of spend, the right answer is a standing rule, a budget alert or an existing recommendation — and the system says so rather than deploy itself.
- A "spend more" Move is an **investment recommendation**, never a saving. It counts only after the business owner and Finance have named, in advance, the outcome metric that will show whether it paid off.
- The Lab's portfolio of experiments is judged on **learning return**: what the knowledge it produced was worth, against what it cost, over a quarter — not only per-experiment caps.

---

## 7. One vocabulary

The documents use many words for related things. This is the crosswalk; where two words meant the same, one is kept.

| Word | Means | Lives in |
|---|---|---|
| **Claim** | one scoped statement about how Azure behaves, with receipts and a confidence | the Atlas |
| **Profile** | the collected claims about one service (a *Service Cost Profile*) | the Atlas |
| **Law** | a regularity across services that has survived replication and transfer tests | the Cost Grammar |
| **Lesson** | something a *person* taught, or a refuted hypothesis's "why it looked true" — scoped, expiring | an estate's Lesson Book (generic lessons become Patterns) |
| **Pattern** | a lesson found in several estates, estate-independent | candidate for a Detector or an Atlas claim |
| **Detector** | a cheap, scoped, expiring *lead generator* compiled from a confirmed finding — it nominates, investigators decide | the Commons and each estate |
| **Move** | a tested, versioned way to change something, with rollback | the Commons |
| **Credential** | earned, expiring permission to run Moves on their own in one domain | an estate |
| **Experiment Ledger** | the system-wide register of predictions and results | the Lab |
| **Lab Notebook** | the page of one experiment (hypothesis, prediction, result, surprise) | the Lab |
| **Case notebook** | the working file of one investigation | an estate |
| **Unexplained Spend Ledger** | the part of the bill the system cannot yet explain | an estate |
| **Terrarium** | miniature estates with planted waste and decoys, for exams and Detector back-tests | the Lab |
| **Technical lead** | the human who can change a resource safely (one of the hats) | an estate's human graph |
| **Team agent** | an agent that represents one team's constraints in negotiations | an estate |
| **Atlas maintainer** | a human who stewards one service's Profile in the Commons | the Commons |
| **Claim states** | heard · disputed · tested · mechanism-verified · replicated · commercially verified · refuted · stale · retired — evidence about Azure | the Atlas |
| **Detector and Move states** | drafted · back-tested · lab-tested · attacked · reviewed · shadow · active · demoted · retired | the Lab and the Commons |
| **Commons tiers** | *draft* → *replicated* → *maintained*: how a claim is shown outside the organisation | the Commons |
| **Lesson rungs** | observation → lesson → pattern; a pattern is a *candidate* for a claim or a Detector, each of which then follows its own life cycle | an estate's Lesson Book |
| **Gates** | replicated · reviewed · commercially verified · credentialed — [separate questions, never one word "trusted"](#the-gates--one-word-is-not-enough) | the Atlas and the Moves |
| **Tell** | a signal that something deserves a look — a meter that appears after a change, a metric that goes silent | the Atlas and the Agenda |

A **Detector** is deliberately *not* a verdict. Prices, workloads and meaning change, so each Detector declares its **validity domain** (where it applies), its **blind spots**, a **novelty trigger** (conditions under which it must hand back to an investigator) and an **expiry** — and the expensive reasoning is kept not only for the new, but for the ambiguous and the shifted.
