# Meternaut

> **Every euro spent on Azure has a reason. This AI learns the reasons — and finds, tests and fixes the euros that have none.**
>
> *Status: an idea, a design and a plan, and a first environment (the Citadel gateway and its model) that is deployed through a workflow and has passed its first checks — see [Status](#status).*

## Read this first

**What this is.** A plan for an AI system that finds money that Azure customers spend for no reason, explains it in plain words to the person who owns it and, only after that person says yes, fixes it. It would run on Microsoft Foundry.

**What exists today.** The documents below (the idea, the design, the experience design and the build plan), and the first environment, which is deployed: the central AI gateway (Citadel's rules, on an existing API Management instance) with a private model behind it, set up only through a workflow ([the changelog](CHANGELOG.md) says what was deployed and what was checked). No agent exists yet, and nothing that finds or fixes savings. A first set of tools and a small gateway built earlier were removed on 2026-11-03, so that the design comes first; they stay in the history at the git tag `implementation-v0`.

**What comes next.** [The first environment](docs/proposals/01-first-environment.md) was approved on 2026-11-03 and is deployed and checked. The usage recording that the owner ordered on 2026-11-04 was first built with a Logic App and then rebuilt the same day without any key, on a function app with a managed identity (the changelog says what was deployed and what was checked). Not built yet: the way back (a remove action). After that come the build plan's first slices.

![Five faculties — STUDY, SURVEY, TEST, ACT, GROW — around one shared memory, with the world, the Commons, the estate, the agreement and the people around them](docs/img/living-system.svg)

## The idea

Cost optimisation has a bottleneck: **somebody has to work out *why* each euro is spent and what it would take to spend less.** That knowledge is produced by hand, one service and one estate at a time — so advice is thin, late, and ignored.

This project, **Meternaut** (an explorer of billing meters), imagines an AI that **does the knowledge work itself — like a scientist for Azure's economics**. It starts from what Azure already tells you — Cost Management, budgets, Advisor — and closes the loop on it (the owner who never opens a recommendations blade gets a short, explained question), then goes where those tools cannot. In this idea it does five kinds of work:

- **STUDY** — it learns how every Azure service *really* charges. It reads the documentation, price lists and specifications and writes a Service Cost Profile with receipts (a source, a date and a quote) into the **Atlas**, an open map of how Azure charges; it has a provisional profile for a brand-new service within hours; and it checks every profile against the one fact that cannot argue back: the bills people already pay. It reasons from a *Cost Grammar* — fourteen ways money arises, such as capacity, consumption, stock, flow and commitment — not from a list of rules.
- **SURVEY** — it understands each estate: what things are *for*, who owns them, when they are busy, what must not be touched, which agreement the estate sits under and what the system may see and do there.
- **TEST** — it investigates, argues with itself (a Skeptic whose job is to break every case), asks *"what happens to the bill if…?"*, and finds things out without deploying anything just to measure it: it asks, reads the bill, replays history, follows changes people were making anyway and pools what other estates have seen — and, rarely, runs one small guarded trial on something an owner already runs.
- **ACT** — it works *with* people: short, specific questions and decisions in Teams and email, an AI in the meeting, changes carried out only with a human's OK or inside a rule a human wrote. Autonomy is **earned** per domain, and shrinks when trust shrinks.
- **GROW** — it scores every prediction against reality, is evaluated on test cases it cannot see, learns from every answer, and shares what it learns about *Azure* in an open **Commons**: what it reads in public sources, after review, and from customer estates only a privacy-reviewed scope and aggregate, and only when several organisations contribute the same observation.

**It is meant to fit the agreement you actually have:** Enterprise Agreement (EA), Microsoft Customer Agreement (MCA) bought directly, sold through a partner (CSP), or pay-as-you-go; billing-level access or one lonely subscription. It finds out what it may see and do, labels every number with the rates it rests on, and hands each purchase to the person who can make it.

It is a research programme with hands: agents on Microsoft Foundry that study, test and act, with a person in the loop at five places.

> **How to tell whether it learns:** sealed test cases it cannot see — rediscovering waste nobody wrote a rule for, staying quiet on decoys, carrying what it learned on one service over to the next ([getting smarter](docs/07-getting-smarter.md)).

### What it looks like from the outside (an invented example)

> **Retail QA environment — switch it off at night and weekends?** · for its owner · *about €710 a month, priced at the rates on your bill* · fully reversible
> **Why I think so:** six people use it, 07:45–18:30 on weekdays only (11 weeks of access records). **The catch I checked:** two nights show activity — last Tuesday of the month, 02:10–02:50. *Is that a job you need?*
> **A.** Switch off nights and weekends · **B.** …with a wake-up window on the last Tuesday · **C.** Create it per test run instead (I can open the change) · **D.** Do nothing — about €23 a day.
> **[A] [B] [C] [D] · Explain · Challenge · Teach** — and the owner's answer teaches it: *"that's the month-end regression."*

## Where to start

| Read | What it is |
|---|---|
| **[01 · The north star](docs/01-north-star.md)** | **The entire idea.** Start here. |
| [02 · Studying Azure](docs/02-learning-azure.md) | How the AI learns Azure's economics — the Atlas, the Cost Grammar, claims with receipts, day zero for a new service |
| [03 · The estate and the investigation](docs/03-estate-and-investigation.md) | How it understands a customer, follows the directory, learns what it may see and do, hunts and challenges hypotheses, and answers "what happens to the bill if…" |
| [04 · Finding out without spending](docs/04-finding-out-without-spending.md) | How it learns what it cannot read: ask, look, replay, follow, pool — and, rarely, a small guarded trial |
| [05 · Recommend, act, verify](docs/05-recommend-act-verify.md) | The Recommendation, Actions, earned autonomy, purchases under every agreement, and verifying it worked |
| [06 · People and conversation](docs/06-people-and-conversation.md) | Teams cards, email, text, voice, an AI in the meeting — and how every conversation teaches it something |
| [07 · Getting smarter](docs/07-getting-smarter.md) | Predictions, evaluation on sealed cases, the report card and the Commons |
| [08 · The outer rims](docs/08-outer-rims.md) | "What if?" ideas — default-drift radar, polite scream tests, the renewal radar, the cost weather map… |
| [09 · The learning contract](docs/09-the-learning-contract.md) | **What exactly changes when it learns** — six things, how each updates, when it is relied on, how it is tested |
| [10 · The press release from the future](docs/10-press-release-from-the-future.md) | A fictional announcement and the tough questions |
| **[The design](docs/design/README.md)** | How it is built: architecture, agents and workflows, security, safeguards, testing, cost, decisions and the roadmap |
| **[The experience design](docs/experience/README.md)** | What people see, receive and decide: personas and journeys, Teams cards, letters, web pages, dashboards, attention and trust, accessibility, testing |
| **[The build plan](docs/build-plan/README.md)** | What is built first: the slices of phases 0 and 1a, what the adopting organisation provides and decides, the first checks, cost and effort. A plan only |
| **[The first environment](docs/proposals/01-first-environment.md)** | The approved plan for what is set up first (the central AI gateway, Citadel), in what order, and what is checked at each step. Deployed only through a workflow; the changelog says how far it is |
| Research | [the landscape through the lens of learning](docs/research/landscape.md) · [inspirations: how agents learn](docs/research/inspirations.md) · [the cost-trap bank: 145 sourced cost traps](docs/research/cost-trap-bank.md) |

**Short on time?** The picture above, then [the first minute of the north star](docs/01-north-star.md#in-one-minute).

## The design

The [design](docs/design/README.md) is an index and fourteen short documents in plain language. In outline: seven workflows (plain code) call five hosted agents (ten roles) on Microsoft Foundry and Microsoft Agent Framework, and every model and tool call goes through the adopting organisation's governance hub (Citadel, an API Management gateway). Agents read and propose; one component — the action plane — is the only thing that changes Azure, and only what a person approved or a rule a person wrote allows. [Agreements and access](docs/design/14-agreements-and-access.md) says what the system does under each Azure agreement and with each level of access. The cost model puts a pilot at a few hundred euros a month at list prices (a calculation, not a measurement); the model and its sources are in [cost and FinOps](docs/design/10-cost-and-finops.md).

## The experience

The [experience design](docs/experience/README.md) is an index and fifteen short documents on what each person sees, receives and decides: personas and journeys, seventeen Teams card templates with renderings, e-mail letters, the approval and notes pages, dashboards, the attention budget and the trust mechanics, reviewers' surfaces, optional voice and meetings, accessibility and language, and how the experience is tested. At its centre is a message that carries one decision for one person, with its evidence one tap away, and asks for nothing that person has not seen in full. [What the experience needs of the technical design](docs/experience/15-asks-of-the-technical-design.md) lists what the system must do for it, and where the design says so.

## The build plan

The [build plan](docs/build-plan/README.md) is an index and four documents on what to build first and how to know that each step works: seventeen slices across phase 0 (foundations, with a week-0 check of the pilot's bill and a small demonstration that new evidence improves answers) and phase 1a (first value on one estate, first for one workload, ending with a Monday digest and findings that the FinOps lead confirms), what the adopting organisation provides and decides before starting, fourteen first checks with their pass conditions and fallbacks, and what it costs and where it can go wrong. The plan itself builds nothing: see Status for what has been built.

## Status

- **Ideation (v5)** — the north star, a deep-dive per faculty and the learning contract. It is the idea the design answers to.
- **Design (v5)** — the architecture, security and governance, testing, cost model, decisions and roadmap, with what the experience needs of the system placed in it. The system itself is not built; the end of the [design index](docs/design/README.md) lists what is unproven.
- **Experience design (v1)** — personas, journeys, cards, letters, pages, dashboards, attention and trust, accessibility and testing. Nothing is built; the cards are templates that tools check and render.
- **Build plan (v2)** — the first two phases as slices, with the first checks, a week-0 check of the pilot's bill and an early demonstration of learning. A first set of tools, a test harness and a small development gateway were built from it and removed on 2026-11-03, because the design comes first; they stay in the history at the git tag `implementation-v0`, and the [changelog](CHANGELOG.md) says what they were. The repository held no code and no pipelines for a day; the first environment's workflow, templates and tools came back on 2026-11-03 (see the next item). What was deployed from the first ones has been deleted from Azure.
- **First environment (deployed and checked; not complete)** — what is set up first and in what order: [the proposal](docs/proposals/01-first-environment.md). The workflow ([`deploy-hub.yml`](.github/workflows/deploy-hub.yml)), the templates ([`environment/`](environment/)) and the tools ([`tools/`](tools/)) are in the repository, and the gateway and its first model are deployed and have passed their first checks (a call with the right key is answered; a missing key, a wrong key, an unlisted model and a call over the token limit are each refused). Not built: the way back (a remove action). The usage recording (ordered on 2026-11-04) is rebuilt without any key (a function app on the Flex Consumption plan with a managed identity, private endpoints, no policy opt-out); the changelog says what is deployed and checked. The [changelog](CHANGELOG.md) says what has been deployed and checked.
- **Version numbers** are release tags in this repository; the [changelog](CHANGELOG.md) says what each one changed.
- **Licence:** MIT ([LICENSE](LICENSE)) covers everything in this repository, the documents included.
- **Principles:** Microsoft technology for the product (open standards and repository tooling are the exceptions) · aligned with the Cloud Adoption Framework and the Well-Architected Framework · open source · fully AI-infused · human-in-the-loop.
- **Trademarks:** Azure, Microsoft Foundry, Microsoft Agent Framework, Microsoft Teams and Microsoft 365 are trademarks of the Microsoft group of companies, named here only to say what Meternaut is built on and works with.
- **How the decisions were challenged:** [`docs/reviews/`](docs/reviews/README.md). **What changed and when:** the [changelog](CHANGELOG.md). **Rules for anyone — human or agent — working here:** [AGENTS.md](AGENTS.md).

Check the documents with `python tools/check-docs.py --strict` (standard library only).
