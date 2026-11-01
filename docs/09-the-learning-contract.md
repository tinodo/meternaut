# The learning contract — what changes when it learns

> Storing a lesson is not learning. A system has learned only if **something that governs its future behaviour has changed, in a way that improves its results on a test it could not game.** This page names what changes, how each is updated, when it is relied on and how it is tested — and the two labels every claim carries: an *evidence level* and a *scope*.
> Part of the [north star](01-north-star.md). Idea-level: what the system commits to, not how it is built.

---

## 1. Six things that change

| # | What changes | Learns from | Updates by | Relied on when | Tested by |
|---|---|---|---|---|---|
| **1** | **Beliefs about Azure** — the [Atlas](02-learning-azure.md), the open knowledge base of how Azure charges: *claims* with a [scope and an evidence level](#2-evidence-has-a-scope) | documents, price lists, pooled observations; per estate, its bills and outcomes | evidence for and against accumulates per scoped claim; in an estate, the first bill line that contains a meter settles a contradiction | **replicated**, **reviewed** and, for advice on an estate, **bill-observed** there ([the gates](#the-gates--one-word-is-not-enough)) | held-out services; transfer; regression |
| **2** | **What to do next** — a *policy* for choosing the question, source, way of finding out or phrasing | what each choice turned out to be worth, per euro and per human minute | a running estimate per option; most effort goes to the best, a **protected share explores** | it beats a random or fixed order | ablations on sealed cases and replays |
| **3** | **Compiled knowledge** — Detectors, Actions, investigation recipes: *code* with a test | a confirmed finding and the checks that would have caught it | back-tested on recorded bills → attacked by the Skeptic (tries to refute everything) → shadow (nominates privately, changes nothing) → active, with a **validity domain, blind spots and expiry** | its shadow precision and harm record are good enough | held-out cases and decoys |
| **4** | **Predictions of consequence** — the [Consequence Engine](03-estate-and-investigation.md): a *causal model* with explicit assumptions | followed changes, replays checked against bills, trials, outcomes | refitted from *changes that really happened* and comparison groups | its calibration in that domain is good | predicted vs realised, with proper scoring rules |
| **5** | **Understanding of one estate** — the Estate Model and Lesson Book: *testimony* (attributed, scoped, expiring) and observation | what people say; what telemetry and the bill show | adopted provisionally, **widened only with corroboration** | it has survived evidence and its owner re-confirms | teachability test cases; correction rate |
| **6** | **The method itself** — procedures, model routing, how it speaks: versioned procedures and prompts | evaluation results, ablations, the report card | the system *proposes* a change and tests it; people approve | it improves the sealed evaluation without hurting anything else | the evaluation, with a person watching for gaming |

None of this learning depends on retraining a model's weights. Rows 1–5 are *knowledge that a defined process updates*; row 6 is the process itself.

---

## 2. Evidence has a scope

*Verified* hides a great deal: by what, where, for whom? So a claim never says it; it carries an **evidence level** (what kind of evidence stands behind it) and a **scope** (where it holds).

| Level | Confirmed by | Lives in | It lets the system say |
|---|---|---|---|
| **documented** | a source says so, and its receipt (link, date, quoted text) proves it | the Atlas | leads, questions and watches; advice marked *documented only* |
| **price-confirmed** | a published price list shows the meter, unit and rate | the Atlas | the price part is right, at list prices |
| **bill-observed** | a real bill line of one estate behaved as predicted: the period had closed and the residual was inside the stated error | that estate's Ledger (its record of predictions, decisions and outcomes) | a **savings claim** for that estate |
| **outcome-confirmed** | a change based on the claim gave the predicted effect, normalised for load, against a counterfactual | that estate's Ledger | the measured effect; a Detector candidate |

Levels describe evidence; they are not grades of truth. A claim with no price in it (*a VM that is stopped but not deallocated still bills compute*) skips *price-confirmed*; a failed re-check or a restated bill makes any claim *stale*. A customer's own price sheet stays in the estate and supplies its *contracted* rates; a figure priced on it is an expected saving only once a bill line agrees.

A **scope** names **service · SKU or API version · region · offer · agreement type · feature set · load · date**. Agreement and region are part of it, not footnotes: rates, discounts, reports and purchase rights differ between an Enterprise Agreement, a Microsoft Customer Agreement bought directly, a purchase through a partner and pay-as-you-go, and prices differ by region. For the upper two levels the scope is one estate: its agreement type, **price basis** (contracted, billed or list), region, billing lag and allocation rules.

- A **new service's first profile is *documented***: it can raise questions, start watches and back a labelled scenario, never a **savings promise**; a meter nobody has used stays *documented only* until a bill line of that estate confirms it, and the Agenda keeps the question open.
- **A claim confirmed on one estate's bill is not confirmed on another's:** other rates, another agreement, another region, another load. Pooled observations raise confidence and say what to look for; until a bill line of its own agrees, the claim rises no higher than *documented* or *price-confirmed* there.

### The gates — one word is not enough

"Trusted" is never used alone: each gate asks a separate question about a *use*, while the level says what stands behind the claim:

| Gate | The question | Evidence | Granted by | Allows |
|---|---|---|---|---|
| **Replicated** | held in more than one condition, or re-checked by someone else? | other dates and regions; pooled observations; an independent re-run | Knowledge CI (the re-check recipes); other organisations, through the Commons (the open, shared half of the knowledge) | being offered beyond a draft |
| **Reviewed** | has someone tried to break it, and has a person with standing read it? | the Skeptic's attack; a maintainer's or owner's review | the Skeptic and a person | starting a watch, asking a question, nominating a lead |
| **Bill-observed** | does it match *this* estate's bill, at the price basis the advice uses? | reconciliation with the cost export and price sheet, period closed | the Economist (quantifies options, replays history), open to Finance's challenge | a *savings* claim for that estate |
| **Outcome-confirmed** | did a change based on it do what was predicted here? | the Auditor's load-normalised measurement against a counterfactual | the Auditor (checks outcomes against predictions) | counting a saving as achieved |
| **Credentialed** | has this Action earned permission to run on its own in this domain? | its outcome-confirmed record, shadow runs, the report card | people | autopilot, the top of the **autonomy ladder**: running without a fresh OK |

When two gates disagree, the lower verdict stands until new evidence settles it. If a challenge succeeds after advice has gone out, the claim is downgraded, the owners whose advice rested on it are told, and the Ledger keeps the correction. A credential is withdrawn when an Action's regret rate passes a stated threshold over a stated window, or after one regret of a defined severity; a person with authority can revoke it at any time.

---

## 3. Counterfactual evidence, not proof

Replays and followed changes are **counterfactual evidence under stated assumptions**; *prove* is not available to them, because production has rare traffic, quota contention and human operations that no replay contains. A replay earns a hearing only after it has reproduced the real bill of the month it replays, and every result carries an **external-validity envelope**: what was held constant, what scale was covered, what was *not* tested, which agreement and price basis were assumed.

Only two things may support **"safe in this estate"**: a *guarded trial* (one small reversible change to something an owner already runs in non-production, with the owner's yes after seeing a cost ceiling, a guard metric and automatic rollback; it can move the bill) or *observation after the change*. The Consequence Engine, a **causal model**, learns from **followed changes**: a team changes something for its own reasons, the system has written its prediction and control meters down first, and afterwards compares before and after against untouched look-alikes, for the divergence beyond what both would have done anyway — or says there is no good comparison and widens the interval.

---

## 4. People are witnesses, not oracles

What a person says is **testimony** — attributed, dated, scoped, and fallible: a departing owner describes an obsolete rhythm; an engineer answers "not mine" because it is easier. So:

- A statement is adopted **provisionally**, at the scope it was given (*this resource*, not *everything of this kind*).
- It is **widened only with corroboration**: telemetry that agrees, a second person, repeated outcomes. A claim about ownership, intent or constraints that would change a decision is *checked*, not just recorded.
- It **expires**, and is re-asked cheaply when evidence changes.
- Success is **decision burden**, not question count: the time a decision cost a person, how many cases wait on an answer, and how often an answer needed correcting.
- A question nobody answers follows the escalation path in [people and conversation](06-people-and-conversation.md), then expires and is recorded as unanswered; silence is never consent.

---

## 5. What "better" is measured against

Expert-written Profiles and the Cost Grammar bootstrap the system, so a test of *learning* must separate **what we wrote** from **what it added**:

| Baseline | What it is | What beating it shows |
|---|---|---|
| **Retrieval only** | the same sources and tools, with a memory that does not learn | the learning is more than search: better held-out billing behaviour and **transfer** after a single correction |
| **The expert seed** | the hand-written Profiles and Grammar, frozen | the system adds knowledge beyond what we gave it, over time (a learning curve) |
| **A practitioner** | an experienced FinOps person with the same access | it is useful in practice, not only on paper |

The **evaluation** is independent and sealed: a harness holds the test cases and their answer keys; during development the system sees neither, and at evaluation the harness gives it each case's input and keeps the answer key. The cases stay hidden from the system under test while they are sealed; a worn-out set is retired into the development set and replaced by fresh cases. Test estates are *generated data* — files, never deployed resources — with planted waste and **decoys**, things that look wasteful for a good reason; code, not a model, decides what is planted. Answer keys come from the [cost-trap bank](research/cost-trap-bank.md), each adjudicated by a person. Splits are by **service and by time**, never by random row. Learning is shown by running the same sealed cases with the memory *frozen* at a date and with the memory *updated* since: the difference is what learning added.

---

## 6. Does it pay for itself?

The all-in **cost to serve** (models, orchestration, the people who review and reconcile, Finance's time, upkeep of the Commons, the effect of any trial on the bill) is counted against **outcome-confirmed incremental value**: savings *beyond what the customer's existing tools and people would have found anyway*, judged over a quarter. Learning never provisions anything just to measure it.

- **Value per human minute** and **cost per outcome-confirmed euro** sit on the [report card](07-getting-smarter.md) next to the savings.
- Every figure states its **price basis** (contracted, billed or list); without a bill it is a scenario at list prices, and only a bill line makes it an *expected saving*. The report card shows how closely predicted and outcome-confirmed savings agree for each basis.
- Below a **minimum opportunity size** the right answer is a standing rule, a budget alert or an existing recommendation, and the system says so.
- A "spend more" Action is an **investment recommendation**, never a saving; it counts only once the business owner and Finance have named, in advance, the outcome metric that will show whether it paid off.

---

## 7. One vocabulary

The documents use many words for related things. This is the crosswalk: one word is kept for each.

| Word | Means |
|---|---|
| **Atlas** | the open, versioned map of how Azure charges; its dossier on one service is a **Profile** |
| **Claim** | one statement about Azure, with receipts, scope, evidence level and confidence |
| **Scope** | where a claim holds: service, SKU, region, offer, **agreement type**, feature set, load, date |
| **Evidence level** | documented → price-confirmed → bill-observed → outcome-confirmed (also *disputed*, *stale*, *refuted*, *retired*) |
| **Gates** | replicated · reviewed · bill-observed · outcome-confirmed · credentialed: [separate questions, never one word "trusted"](#the-gates--one-word-is-not-enough) |
| **Agreement type** | Enterprise Agreement, Microsoft Customer Agreement bought directly, sold through a partner, pay-as-you-go, and the offers around them |
| **Price basis** | what a number rests on: **contracted**, **billed** or **list** |
| **Reach** | what the system may see and do in one scope (billing reach; subscription reach with or without costs); what it found by trying — at onboarding, weekly and at once after Azure refuses a request — is the **capability profile** |
| **Lesson** | what a *person* taught, kept in the **Lesson Book**, scoped and expiring; a recurring lesson is a **pattern**, a candidate for a Detector or, after review, an Atlas claim |
| **Detector** | a cheap, scoped, expiring lead generator compiled from a confirmed finding: it nominates, investigators decide; each declares its validity domain and blind spots |
| **Ledger** | an estate's record of what the system predicted, decided and measured |
| **Unexplained Spend list** | the bill lines not yet explained; it drives the Agenda and is not part of the Ledger |
| **Routes** | the six ways of finding out, cheapest first: **Ask · Look · Replay · Follow · Pool · Trial** ([details](04-finding-out-without-spending.md)) |
| **Autonomy ladder** | observe → advise → assist (one tap) → autopilot inside a rule a human wrote; autopilot is a **Credential**, earned per domain on the report card and revoked when regret appears |
| **Case** | a confirmed finding about one estate, with its notebook; a Recommendation is made from it ([estate and investigation](03-estate-and-investigation.md)) |
| **Recommendation** | the decision card: what, why, options including *do nothing*, consequences, what its numbers rest on |
| **Action** | a tested, versioned, reviewable change recipe, with rollback |
| **Purchase request** | the whole case for a commitment, written for whoever may make the purchase when the system may not; purchases are prepared at the **Commitment Desk** ([recommend, act, verify](05-recommend-act-verify.md)) |
| **Evaluation** | independent testing on **sealed test cases**; test estates are generated data |
| **Report card** | the scored record of an evaluation, kept inside the organisation: calibration, outcome-confirmed savings, regrets, surprises, its own cost, and what the system is worst at |

The **evidence level**, **price basis** and **reach** travel together on every Recommendation.
