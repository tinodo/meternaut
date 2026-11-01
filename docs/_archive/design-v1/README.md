# design-v1 — withdrawn

> Frozen on 2026-11-01 as the git tag `design-v1`. **It was withdrawn and replaced by [`design-v2`](../../design/README.md).** Nothing here is edited; it is kept so the history is honest.

## What it was

A first design of Azure Cost in Action on Microsoft Foundry, the Microsoft Agent Framework and the Citadel governance hub: fourteen documents (about 157,000 words), 37 decision records, 34 research spikes, a cost model, and three review passes by nine models.

| Folder | What it holds |
|---|---|
| [`design/`](design/README.md) | The fourteen design documents, the research evidence and the price snapshot it was built on |
| [`reviews/`](reviews/) | The review record: round 1, round 2, the targeted third pass and its closure checks |

## Why it was withdrawn

- **It was too heavy to read and too heavy for the problem.** A reader could not get through it, and most of its length went into one over-built approval and execution mechanism.
- **It invented constraints and assumptions.** A hedge ("probably not Databricks or Fabric") became a hard constraint, a stated preference became a licence assumption, and personal context ended up in a document meant for a community.
- **It added a lab where agents deploy resources to experiment.** That costs real money, needs its own governance, and was never required to learn how Azure bills.
- **Its jargon hid the design.** Terms such as "exam", "spine", "leaf" and "authority chain" were defined inside the documents and nowhere a newcomer would look.

[`design-v2`](../../design/README.md) starts again from the brief, in plain words, at a size a person can read.
