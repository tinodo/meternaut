# The rubber-duck record

Every version of the ideation is reviewed by independent agents before it is called done. This folder keeps what they said, verbatim, and what was done about it.

| Round | Reviewers | Raw reports | Disposition |
|---|---|---|---|
| **v4 · Round 1** — reviewed at commit `d267654` | A visionary / AI researcher · B FinOps and Azure domain (Learn-grounded) · C the skeptic · D brief-compliance and anti-pattern audit | [A](v4-round-1/raw-a-visionary.md) · [B](v4-round-1/raw-b-finops-domain.md) · [C](v4-round-1/raw-c-skeptic.md) · [D](v4-round-1/raw-d-brief-compliance.md) | [disposition](v4-round-1/disposition.md) |
| **v4 · Round 2** — reviewed at commit `cbd6756` | A fresh reader through the operator's eyes · B1 Azure billing fact-check · B2 products and commercial-rules fact-check · C disposition-truth and consistency audit | [A](v4-round-2/raw-a-fresh-reader.md) · [B1](v4-round-2/raw-b1-factcheck-gallery.md) · [B2](v4-round-2/raw-b2-factcheck-commit-advisor.md) · [C](v4-round-2/raw-c-disposition-audit.md) | [disposition](v4-round-2/disposition.md) |

**How the record is kept.** Raw reports are saved exactly as the reviewers returned them, with a header and the orchestrator's spot-checks appended — every quoted passage is checked against the files, and every external fact the reviewers relied on is re-checked against its primary source before it is used. The disposition says, finding by finding, what was accepted, what was adjusted and why, and where the change landed. Earlier rounds (v1 → v3.2.1) are in [the archive](../_archive/round-3-v3.2.1/reviews/).

## Design phase 1

The design ([docs/design](../design/README.md)) is reviewed in **two rounds with a different model family on each lens in each round**, against one standing brief: [the design review brief](design-review-brief.md). The lenses are *architecture*, *security, safety and compliance*, *cost and operability*, *AI engineering, evaluation and drift*, and *platform fact-check*.

| Round | Lens and model | Raw report | Disposition |
|---|---|---|---|
| **Design · Round 1** — reviewed at commit `20390d4` | A architecture (gpt-6.1-sol) · B security, safety, compliance (gemini-4-argon) · C cost and operability (grok-4.7) · D AI engineering, evaluation, drift (gpt-6-sol) · E platform fact-check (gpt-5.6-sol) | [A](design-v1-round-1/raw-a-architecture.md) · [B](design-v1-round-1/raw-b-security.md) · [C](design-v1-round-1/raw-c-cost-ops.md) · [D](design-v1-round-1/raw-d-ai-engineering.md) · [E](design-v1-round-1/raw-e-platform-factcheck.md) | [disposition](design-v1-round-1/disposition.md) |
| **Design · Round 2** — reviewed at commit `7baddcf` (the design after the Round-1 revisions) | A architecture (gemini-4-argon) · B security, safety, compliance (grok-4.7) · C cost and operability (gpt-6.1-sol) · D AI engineering, evaluation, drift (claude-sonnet-5) · E platform fact-check (claude-sonnet-5.5) | [A](design-v1-round-2/raw-a-architecture.md) · [B](design-v1-round-2/raw-b-security.md) · [C](design-v1-round-2/raw-c-cost-ops.md) · [D](design-v1-round-2/raw-d-ai-engineering.md) · [E](design-v1-round-2/raw-e-platform-factcheck.md) | [disposition](design-v1-round-2/disposition.md) |
| **Design · targeted third pass** — the parts Round 2 redesigned (the authority chain, the leaf-call rule, the spend budget, the contract × environment model), reviewed at commit `6694d15` | T-A authority chain and leaf-call rule (gpt-6.1-terra) · T-B spend budget and contract × environment model (grok-4.6); each on a model no earlier round used; each then checked that its findings were closed | [T-A](design-v1-third-pass/raw-ta-authority-chain.md) · [T-B](design-v1-third-pass/raw-tb-spend-and-contracts.md) | [disposition](design-v1-third-pass/disposition.md) |
