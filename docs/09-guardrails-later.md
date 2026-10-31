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

Detailed rules come later; the *shape* is already set. Human oversight sits in five places, not one button at the end ([why](01-north-star.md#14-where-humans-stay-in-charge)):

1. **What counts as known** — knowledge becomes trusted after review, and carries its receipts.
2. **What it spends to learn** — budgets for the Lab and every experiment are set by people.
3. **What it changes** — every change has a human's OK or a rule a human wrote; purchases always have named humans.
4. **How much autonomy it has earned** — credentials per domain, granted and revoked by people, from the report card.
5. **How it speaks** — tone, timing and attention limits set with the people it talks to; silence is never consent.

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
