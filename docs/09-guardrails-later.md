# Guardrails — the questions we will answer later

> You said it first: *"Before you start coding, we need to define a lot of guardrails, which we have to do later."* This page exists so that "later" has a shape. It holds **no answers** — ideation does not need them — only the **themes** that a learning, acting AI makes unavoidable, so nothing is forgotten when the time comes.
> Part of the [north star](01-north-star.md).

---

## Your starting constraints

These came with the brief and are the fixed points every later design must respect:

- It runs on **Microsoft platforms and technology** — Azure, Power Platform, Microsoft 365, or other Microsoft services — and nothing else.
- It is aligned with the **Cloud Adoption Framework** and the **Well-Architected Framework**.
- It is **open source** (MIT).
- It is **fully AI-infused** — and **human-in-the-loop**.
- It is **not a chatbot**: it runs workflows, research programmes and campaigns.

---

## The human-in-the-loop spine

Detailed rules come later; the *shape* is already set. Human oversight sits in five places, not one button at the end — what counts as known, what it spends to learn, what it changes, how much autonomy it has earned, and how it speaks. They are set out in [the north star](01-north-star.md#14-where-humans-stay-in-charge).

---

## How the idea lines up with CAF, WAF and the FinOps Framework

Two of the brief's constraints are frameworks the design is meant to *use*, not merely respect. At idea level:

| Framework | What it offers | Where it lands in the idea |
|---|---|---|
| **Well-Architected Framework** — the five pillars (reliability, security, cost optimisation, operational excellence, performance efficiency) | the checklist for trade-offs | the [Consequence Engine](03-estate-and-investigation.md#11-the-consequence-engine--what-happens-to-the-bill-if) shows every option's effect on all five, so a saving that costs reliability is a different offer; the Skeptic's questions are drawn from the pillars; Briefs carry the trade-off |
| **Cloud Adoption Framework** — the Govern and Manage methodologies (cost management is one of the domains governance covers) | the operating context: policy, budgets, accountability, operations | the system is a *participant in an organisation's governance*, not a replacement: standing rules in plain language, budgets and anomaly alerts as inputs, owners and tags from the human graph, savings co-signed by Finance |
| **FinOps Framework** — *Inform → Optimize → Operate*, and capabilities such as allocation, anomaly management, rate and usage optimisation (Microsoft Learn's FinOps Framework page still says "workload optimization"), forecasting and unit economics | a capability map and a shared language | **Inform**: the Estate Model, explained spend, allocation views · **Optimize**: Briefs, Moves and the Commitment Desk, with rate and usage savings kept apart · **Operate**: rituals, the report card, verification · **unit economics** as the measure of value |
| **FOCUS** — the open cost-and-usage format | a common shape for cost data | one of the surfaces the Atlas reads and reconciles |

---

## The themes

A learning system adds new questions to the usual ones. Grouped as they are likely to be tackled:

### About what the system may learn from
- **Everything it reads is data, never instructions.** Documentation, forum posts, tags, code comments, tickets — all can be wrong or hostile. How are they kept from steering the AI?
- **What may it learn from people**, how long is it kept, who can see and delete it? (People-data, works councils, the right to be forgotten, and the principle that the system works out *who owns things*, never how well anyone works.)
- **How are lessons governed** — scope, expiry, conflict, deletion — so memory stays trustworthy?
- **How does knowledge earn trust** — what does "verified" mean, who reviews, what is the standard of evidence?

### About what it may do
- **The Lab** — what it may create, how much it may spend, what it may never touch, how it is walled from any customer.
- **Acting on behalf of a person** — identity, least privilege, the rule that the AI never has more power than the human who said yes.
- **Autonomy credentials** — how they are granted, recorded, reviewed, revoked, and how the AI *self-demotes*.
- **Purchases and irreversible changes** — two keys, snapshots, cooling-off periods, and the commitment rules.
- **Rollback and blast radius** — how guards and undo are specified and tested.

### About the people and the places
- **Data protection and sovereignty** — where data lives, what leaves, the position of the European rules and any sector rules.
- **Regulation of AI itself** — how the system is classified, documented and overseen under the AI rules that apply.
- **Security** — the AI as a privileged identity; the attack surface of an agent that reads the internet and talks to people.
- **Communication** — consent for meeting participants and recordings, labelling of AI voice and avatar, accessibility, language.

### About the knowledge it shares
- **The Commons** — what may be shared, how it is anonymised, how contributions are reviewed, how poisoned or sloppy claims are kept out, who maintains it.
- **Licensing and provenance** of everything it publishes.

### About itself
- **Auditability and replay** — every claim, decision and action must be reconstructable.
- **The AI's own bill** — budgets, model choices, and the rule that the system optimises itself with the same grammar.
- **Model and platform change** — what happens to the exam, the report card and the credentials when a model or a service changes.
- **Evaluation** — how the Exam, the Examiner and the report card are themselves governed so they cannot be gamed.

---

## Where the earlier inventory lives

An earlier round of this project inventoried guardrail topics in depth — 14 domains and roughly 109 questions. It was built for a different design, so it is *not* carried over; but it remains as raw material for that later work:

- [the archived guardrail inventory](_archive/round-3-v3.2.1/ideation/08-trust-safety-and-guardrail-topics.md) (read it as a checklist of questions, not as decisions).

When the time comes, the plan is to start from the five spine points and the themes above, ask *what could go wrong* in each, and write the guardrails as **small, testable commitments** — each one something the Exam or a Lab check can verify.
