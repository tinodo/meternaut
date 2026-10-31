# Changelog

All notable changes, newest first. Versions are git tags. Earlier versions are archived under [`docs/_archive/`](docs/_archive/) and are never edited.

## v4 — 2026-10-31 — rebuilt around a learning system (tag `ideation-v4`)

**Why.** The operator rejected the whole v1 → v3.2.1 package. It was built around his two example findings (cast as "seed examples" and release plays); it lacked the heart of the idea — *how the AI learns about new Azure services, gathers knowledge, investigates cost implications, experiments and recommends*; it was buried in governance paperwork (decisions, assumptions, risks, kill criteria, a threat catalogue) that has no place in ideation; and its pictures were linear pipelines.

**What changed.** The entire live package was replaced. **v3.2.1 is archived untouched** in [`docs/_archive/round-3-v3.2.1/`](docs/_archive/round-3-v3.2.1/) (tag `ideation-v3.2.1`), and its reusable parts — interaction concepts, ownership, moonshots, the 145-trap research, the guardrail inventory — were mined, not deleted.

### New
- A **north star** — [01](docs/01-north-star.md): "a scientist for Azure's economics", five faculties (STUDY · SURVEY · TEST · ACT · GROW) around one memory, four clocks, a cast of 13 agents.
- Six deep-dives: [02 Studying Azure](docs/02-learning-azure.md) (Atlas, a 14-mechanism Cost Grammar, claims with scoped receipts, Knowledge CI, day zero — with a real, documented example) · [03 The estate and the investigation](docs/03-estate-and-investigation.md) (Estate Model, human graph, Agenda, Skeptic, causal Consequence Engine, a gallery of 34 cases across every mechanism) · [04 Experiments and the Lab](docs/04-experiments-and-the-lab.md) · [05 Recommend, act, verify](docs/05-recommend-act-verify.md) (what happens to an Advisor card, Moves, earned autonomy, the Commitment Desk, verification) · [06 People and conversation](docs/06-people-and-conversation.md) · [07 Getting smarter](docs/07-getting-smarter.md) (predictions, the Exam and its independence, the report card, the Commons).
- [11 The learning contract](docs/11-the-learning-contract.md) — what *changes* when it learns (six things, each with evidence, update rule, trust threshold and test), what "verified" means, counterfactual evidence versus proof, baselines, and whether it pays for itself.
- [08 Outer rims](docs/08-outer-rims.md) (37 learning-centred ideas) · [09 Guardrails, later](docs/09-guardrails-later.md) (themes, plus the CAF / WAF / FinOps map) · [10 What next](docs/10-what-next.md) (a first experiment with baselines) · [12 Press release from the future](docs/12-press-release-from-the-future.md).
- Research: [the landscape through the lens of learning](docs/research/landscape.md), [inspirations — how agents learn](docs/research/inspirations.md) (24 papers, every identifier checked against arXiv), and the 145-trap catalogue re-cast as an [exam bank](docs/research/exam-bank-cost-traps.md).
- Three pictures built from loops, hubs and state changes: [living system](docs/img/living-system.svg), [four clocks](docs/img/four-clocks.svg), [escalation as widening circles](docs/img/escalation-rings.svg).
- A new [`tools/check-docs.py`](tools/check-docs.py): links, anchors (GitHub slug rules), diagrams, orphans, and guards against the operator's two examples creeping into the design, governance paperwork returning, and pipelines in disguise.
- [`docs/reviews/`](docs/reviews/README.md): rubber-duck round 1 (four independent reviewers) with raw reports, spot-checks and a disposition.

### Removed from the live package (kept in the archive)
Decision register, assumption and risk registers, kill criteria, spikes, the 305-row opportunity catalog as a design artefact, release plans built on the two examples, the threat catalogue, and every linear pipeline picture.

### Rules
[`AGENTS.md`](AGENTS.md) now also records: this is a learning system, not a rulebook; the two original findings are exam questions only; pictures show loops; ideation is not technology; no governance paperwork during ideation.

## Earlier versions (v1 → v3.2.1) — superseded by v4

- **v3.2.1** — the repository stays private until the operator says to switch it; `AGENTS.md` added.
- **v3.2** — licence decided: MIT; `LICENSE` added.
- **v3.1** — a patch after two post-v3 audits (17 defects: catalog reclassification, normative text, evidence re-verified).
- **v3** — after review round 2: a red team, a Learn-grounded fact-check and a consistency review; the safety model made one normative set of rules.
- **v2** — after review round 1: three reviewers, 41 findings accepted; plan, research and decision status added.
- **v1** — the first ideation pass: a vision, an opportunity catalog, an agent crew, interaction concepts and a follow-up plan.

The full text of those entries is in [`CHANGELOG-through-v3.2.1.md`](docs/_archive/round-3-v3.2.1/CHANGELOG-through-v3.2.1.md); the tags are `ideation-v1` … `ideation-v3.2.1`.
