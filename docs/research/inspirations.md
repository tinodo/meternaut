# Inspirations — what we learned from how agents learn

> The north star says the **ideas may come from anywhere**, while the product runs on Microsoft technology. These are the ideas — from research and from Microsoft's own agent work — that most shaped the *learning* design, with what each one contributed and what it warns about.
> **Verification:** every paper below was checked against the arXiv listing on 2026-10-31 (identifier, title, first author, date). The one-line summaries describe the papers' well-known central ideas at a high level; they are **not** claims about benchmark numbers, which are deliberately omitted. Read the paper before relying on a detail.
> Part of the [north star](../01-north-star.md). See also [the landscape](landscape.md).

---

## 1. How agents acquire and keep skills

| Work | The idea | What we borrow |
|---|---|---|
| **Voyager: An Open-Ended Embodied Agent with Large Language Models** — Wang et al., [arXiv:2305.16291](https://arxiv.org/abs/2305.16291), May 2023 | A lifelong-learning agent that explores on an **automatic curriculum**, stores what works as an ever-growing **library of executable skills**, and improves them using environment feedback, execution errors and self-verification | The **Agenda** as an automatic curriculum (ranked by value of information); **Moves, Detectors and Lab recipes** as a growing skill library; proof in the Lab as "execution feedback" |
| **Agent Workflow Memory** — Wang et al., [arXiv:2409.07429](https://arxiv.org/abs/2409.07429), Sep 2024 | Agents **induce reusable workflows** from past experience and reuse them | Investigation playbooks the system writes *for itself* from confirmed cases |
| **Large Language Models as Tool Makers** — Cai et al., [arXiv:2305.17126](https://arxiv.org/abs/2305.17126), May 2023 | A strong model **makes** reusable tools; a lighter model **uses** them | **"Expensive reasoning once, cheap detection forever"** — the Detective writes the Detector; a cheap check runs everywhere |
| **Executable Code Actions Elicit Better LLM Agents (CodeAct)** — Wang et al., [arXiv:2402.01030](https://arxiv.org/abs/2402.01030), Feb 2024 | Agents act by writing **executable code** | Moves and Detectors are **inspectable code**, so they can be reviewed, tested and replayed |
| **Toolformer** — Schick et al., [arXiv:2302.04761](https://arxiv.org/abs/2302.04761), Feb 2023 · **ReAct** — Yao et al., [arXiv:2210.03629](https://arxiv.org/abs/2210.03629), Oct 2022 | Models that learn to **use tools**, interleaving reasoning with action | The founding rule: **numbers come from tools, never from model memory** |

## 2. How agents learn from experience

| Work | The idea | What we borrow |
|---|---|---|
| **Reflexion: Language Agents with Verbal Reinforcement Learning** — Shinn et al., [arXiv:2303.11366](https://arxiv.org/abs/2303.11366), Mar 2023 | Agents improve by writing **verbal reflections** on outcomes into memory — no weight updates | The **Lesson Book**, and the principle that a refuted hypothesis yields a written *"why it looked true"* |
| **ExpeL: LLM Agents Are Experiential Learners** — Zhao et al., [arXiv:2308.10144](https://arxiv.org/abs/2308.10144), Aug 2023 | Agents gather experience, extract **natural-language insights** across tasks, and recall past successes | The **maturity ladder** of knowledge — observation → lesson → pattern → Detector → Atlas claim |
| **Generative Agents: Interactive Simulacra of Human Behavior** — Park et al., [arXiv:2304.03442](https://arxiv.org/abs/2304.03442), Apr 2023 | A **memory stream** with retrieval by recency, relevance and importance, plus periodic **reflection** that synthesises higher-level insight | **Dreaming**: the overnight pass that re-reads the day and consolidates it |
| **MemGPT: Towards LLMs as Operating Systems** — Packer et al., [arXiv:2310.08560](https://arxiv.org/abs/2310.08560), Oct 2023 | **Tiered memory management** so long-running agents are not limited by context size | The split between a small always-loaded working set and a large searchable archive |
| **Self-Refine** — Madaan et al., [arXiv:2303.17651](https://arxiv.org/abs/2303.17651), Mar 2023 · **CRITIC** — Gou et al., [arXiv:2305.11738](https://arxiv.org/abs/2305.11738), May 2023 | Iterative improvement with feedback; **self-correction that verifies with external tools** | Brief drafting loops — with the Skeptic checking against *tools and data*, not opinion |

## 3. How agents do science and improve themselves

| Work | The idea | What we borrow |
|---|---|---|
| **The AI Scientist** — Lu et al., [arXiv:2408.06292](https://arxiv.org/abs/2408.06292), Aug 2024 | An end-to-end loop: **idea → experiment → write-up → automated review** | The **Lab Notebook** and the pre-registered experiment; the *review* step becomes an independent Examiner and human review |
| **Darwin Gödel Machine** — Zhang et al., [arXiv:2505.22954](https://arxiv.org/abs/2505.22954), May 2025 | **Open-ended, empirically validated self-modification** of an agent, keeping an archive of variants | The system *proposing changes to its own method* and testing them on the Exam — within limits people set |
| **Self-Taught Optimizer (STOP)** — Zelikman et al., [arXiv:2310.02304](https://arxiv.org/abs/2310.02304), Oct 2023 | A scaffolding program that **recursively improves itself** | The "learning how to learn" section of [getting smarter](../07-getting-smarter.md#6-learning-how-to-learn) |
| **DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines** — Khattab et al., [arXiv:2310.03714](https://arxiv.org/abs/2310.03714), Oct 2023 | **Optimising** prompts and pipelines against a metric | Tuning investigation tactics and communication against the exam — with a Goodhart watch |
| **AgentInstruct: Toward Generative Teaching with Agentic Flows** — Mitra et al., [arXiv:2407.03502](https://arxiv.org/abs/2407.03502), Jul 2024 | Agentic flows that **generate teaching material** | The Terrarium and the Forger as generators of exam and training material |

## 4. How teams of agents work

| Work | The idea | What we borrow |
|---|---|---|
| **AutoGen** — Wu et al., [arXiv:2308.08155](https://arxiv.org/abs/2308.08155), Aug 2023 | Applications as **multi-agent conversations** | The cast as specialists that talk to each other |
| **Magentic-One: A Generalist Multi-Agent System for Solving Complex Tasks** — Fourney et al., [arXiv:2411.04468](https://arxiv.org/abs/2411.04468), Nov 2024 | An **orchestrator** that plans and tracks progress, directing specialist agents | The **Conductor** and the Agenda: one agent that holds the plan and the ledger of what is open |

## 5. Microsoft's own agent work

| Work | Relevance |
|---|---|
| **Azure SRE Agent — memory and skills** ([Memory](https://learn.microsoft.com/en-us/azure/sre-agent/memory), [Skills](https://learn.microsoft.com/en-us/azure/sre-agent/skills)) | The clearest first-party precedent: it learns after each session with no manual training, persists learnings as readable knowledge files, and loads authored skills when relevant — for incidents, not cost |
| **AIOpsLab** — Microsoft Research, [arXiv:2501.06706](https://arxiv.org/abs/2501.06706) | A sandbox that deploys systems, injects faults, generates workload and evaluates agents — the nearest architecture to the **Lab** and the **Terrarium** |
| **Foundry Agent Service** ([overview](https://learn.microsoft.com/en-us/azure/foundry/agents/overview)) | Memory (preview), tracing and evaluations, an **agent optimizer (preview)**, toolboxes and publishing to Teams — the platform primitives the cast would be built from |
| **Azure Updates and its MCP server** ([page](https://azure.microsoft.com/en-us/updates/)) | A machine-readable "something new shipped" signal — the trigger for day-zero learning |

---

## 6. Cautions the literature raises — and how the design answers them

| Caution | Source | Our answer |
|---|---|---|
| **Models cannot reliably self-correct reasoning without outside feedback** | *Large Language Models Cannot Self-Correct Reasoning Yet* — Huang et al., [arXiv:2310.01798](https://arxiv.org/abs/2310.01798), Oct 2023 | The Skeptic must attack with **tools, data and the Lab**, not opinion; self-critique alone never promotes a claim |
| **Optimising a proxy too hard degrades the real goal** | *Scaling Laws for Reward Model Overoptimization* — Gao et al., [arXiv:2210.10760](https://arxiv.org/abs/2210.10760), Oct 2022 | The **Goodhart watch**: no single number is optimised alone; the held-out exam stays hidden; savings are always shown with regret and attention cost |
| **Model confidence can be informative, but only where it is measured** | *Language Models (Mostly) Know What They Know* — Kadavath et al., [arXiv:2207.05221](https://arxiv.org/abs/2207.05221), Jul 2022 | **Calibration is measured per domain** and published; autonomy follows the measured record, not the model's tone |
| **Content an agent reads can carry instructions** | *Not what you've signed up for: … Indirect Prompt Injection* — Greshake et al., [arXiv:2302.12173](https://arxiv.org/abs/2302.12173), Feb 2023 | Everything read — documentation, forums, tags, tickets — is **data, never instructions**, and graded for trust ([guardrail theme](../09-guardrails-later.md)) |
| **Automated science can produce flawed or unjustified results** | the AI Scientist paper discusses its own limitations | Predictions written first; **replication** before trust; an **independent Examiner**; people review what becomes "known" |
| **Self-modifying systems need a bound** | the Darwin Gödel Machine paper stresses sandboxing and oversight | Method changes are *proposals* that people approve; trust is a credential that **shrinks by itself** |

---

## 7. What this changed in the design

- The **Agenda as a curriculum** and the **skill library** (Voyager) → [01](../01-north-star.md#2-the-big-idea-science-industrialised), [04](../04-experiments-and-the-lab.md).
- **Verbal reflection as memory** (Reflexion, ExpeL) → the Lesson Book and its maturity ladder: [03 §10](../03-estate-and-investigation.md#10-the-lesson-book--memory-you-can-read), [07 §2](../07-getting-smarter.md#2-the-lesson-book-matures).
- **Tool-making** (LATM) → "expensive reasoning once, cheap detection forever": [04 §13](../04-experiments-and-the-lab.md#13-dreaming--consolidation-while-the-world-is-quiet).
- **Reflection and consolidation** (Generative Agents) → *dreaming*.
- **Orchestration with a ledger** (Magentic-One) → the Conductor.
- **Sandboxed evaluation** (AIOpsLab) → the Lab, Terrarium and Exam.
- **The cautions** → the Skeptic, replication, the held-out exam, the Goodhart watch, and "data is never instructions".
