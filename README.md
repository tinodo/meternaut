# Azure Cost in Action

> **Every euro spent on Azure has a reason. This AI learns the reasons — and finds, tests and fixes the euros that have none.**

![Five faculties — STUDY, SURVEY, TEST, ACT, GROW — around one shared memory, with the world, the commons, the estate, the people and the lab around them](docs/img/living-system.svg)

## The idea

Cost optimisation has a bottleneck nobody talks about: **somebody has to work out *why* each euro is spent and what it would take to spend less.** That knowledge is produced by hand, one service and one estate at a time — so advice is thin, late, and ignored.

This project imagines an AI that **does the knowledge work itself — like a scientist for Azure's economics**. It starts from what Azure already tells you — Cost Management, budgets, Advisor — and closes the loop on it (the owner who never opens a recommendations blade gets a short, explained question), then goes where those tools cannot:

- **STUDY** — it learns how every Azure service *really* charges: reads the documentation, price lists and specifications, writes a Service Cost Profile with receipts, and has a provisional profile for a brand-new service within hours. It reasons from a *Cost Grammar* — fourteen ways money arises, such as capacity, consumption, stock, flow and commitment — not from a list of rules.
- **SURVEY** — it understands each estate: what things are *for*, who owns them, when they are busy, what must not be touched.
- **TEST** — it investigates, argues with itself (a Skeptic whose job is to break every case), asks *"what happens to the bill if…?"*, and **runs experiments** in a walled-off Lab where it can build things, break them and watch the bill form.
- **ACT** — it works *with* people: short, specific questions and decisions in Teams and email, an AI in the meeting, changes carried out only with a human's OK. Autonomy is **earned** per domain, and shrinks when trust shrinks.
- **GROW** — it scores every prediction against reality, is examined on tests it cannot see, learns from every answer, and shares what it learns about *Azure* — never about a customer — in an open **Commons**.

It is **not** a rulebook, a chatbot or a dashboard. It is a research programme with hands, run by agents (imagined on Microsoft Foundry), with humans at five places in the loop.

> **How we will know it learns:** an exam it cannot see — rediscovering waste nobody wrote a rule for, staying quiet on decoys, carrying what it learned on one service over to the next. The findings that started this project are just two of its questions ([the founding exam](docs/07-getting-smarter.md#8-the-founding-exam)).

### What it looks like from the outside

> **Retail QA environment — switch it off at night and weekends?** · for Priya Nair · *about €710 a month* · fully reversible
> **Why I think so:** six people use it, 07:45–18:30 on weekdays only (11 weeks of access records). **The catch I checked:** two nights show activity — last Tuesday of the month, 02:10–02:50. *Is that a job you need?*
> **A.** Switch off nights and weekends · **B.** …with a wake-up window on the last Tuesday · **C.** Create it per test run instead (I can open the change) · **D.** Do nothing — about €23 a day.
> **[A] [B] [C] [D] · Explain · Challenge · Teach** — and her answer teaches it: *"that's the month-end regression."*

## Where to start

| Read | What it is |
|---|---|
| **[01 · The north star](docs/01-north-star.md)** | **The entire idea.** Start here. |
| [02 · Studying Azure](docs/02-learning-azure.md) | How the AI learns Azure's economics — the Atlas, the Cost Grammar, claims with receipts, day zero for a new service |
| [03 · The estate and the investigation](docs/03-estate-and-investigation.md) | How it understands a customer, follows the directory, hunts and challenges hypotheses, and answers "what happens to the bill if…" |
| [04 · Experiments and the Lab](docs/04-experiments-and-the-lab.md) | How it finds out instead of guessing — billing benches, the wind tunnel, the Time Machine, the Terrarium |
| [05 · Recommend, act, verify](docs/05-recommend-act-verify.md) | The Brief, Moves, earned autonomy, purchases, and verifying it worked |
| [06 · People and conversation](docs/06-people-and-conversation.md) | Teams cards, email, text, voice, an AI in the meeting — and how every conversation teaches it something |
| [07 · Getting smarter](docs/07-getting-smarter.md) | Predictions, the Exam it cannot see, the report card, the Commons, and the founding exam |
| [08 · The outer rims](docs/08-outer-rims.md) | 37 "what if?" ideas — default-drift radar, polite scream tests, the cost weather map… |
| [09 · Guardrails, later](docs/09-guardrails-later.md) | The themes we will answer when it is time, and how the idea lines up with CAF, WAF and the FinOps Framework |
| [10 · What next](docs/10-what-next.md) | The steps from idea to a first experiment that shows whether it learns |
| [11 · The learning contract](docs/11-the-learning-contract.md) | **What exactly changes when it learns** — six things, how each updates, when it is relied on, how it is tested |
| [12 · The press release from the future](docs/12-press-release-from-the-future.md) | A fictional announcement and the tough questions |
| Research | [the landscape through the lens of learning](docs/research/landscape.md) · [inspirations: how agents learn](docs/research/inspirations.md) · [the exam bank: 145 sourced cost traps](docs/research/exam-bank-cost-traps.md) |

**Short on time?** The picture above, then [the first minute of the north star](docs/01-north-star.md#in-one-minute).

## Status

- **Ideation (v4).** A north star, a deep-dive per faculty, and a plan for what to design next. No code yet — by design.
- **Private** until the owner says otherwise. **MIT** licensed ([LICENSE](LICENSE)).
- Constraints from the brief: Microsoft technology only · aligned with the Cloud Adoption Framework and Well-Architected Framework · open source · fully AI-infused · human-in-the-loop · not a chatbot.
- Earlier versions (v1 → v3.2.1) are preserved in [`docs/_archive/`](docs/_archive/) (`round-1-v1`, `round-2-v2`, `round-3-v3.2.1`) and as the git tags `ideation-v1` … `ideation-v3.2.1`; see the [changelog](CHANGELOG.md) for why this version replaced them. Every version is reviewed by independent agents before it is called done — the record is in [`docs/reviews/`](docs/reviews/README.md). Rules for anyone — human or agent — working here are in [AGENTS.md](AGENTS.md).

Check the documents with `python tools/check-docs.py --strict` (standard library only).
