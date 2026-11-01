# The rubber-duck record

Every version of the ideation is reviewed by independent agents before it is called done. This folder keeps what they said, verbatim, and what was done about it.

| Round | Reviewers | Raw reports | Disposition |
|---|---|---|---|
| **v4 · Round 1** — reviewed at commit `d267654` | A visionary / AI researcher · B FinOps and Azure domain (Learn-grounded) · C the skeptic · D brief-compliance and anti-pattern audit | [A](v4-round-1/raw-a-visionary.md) · [B](v4-round-1/raw-b-finops-domain.md) · [C](v4-round-1/raw-c-skeptic.md) · [D](v4-round-1/raw-d-brief-compliance.md) | [disposition](v4-round-1/disposition.md) |
| **v4 · Round 2** — reviewed at commit `cbd6756` | A fresh reader through the operator's eyes · B1 Azure billing fact-check · B2 products and commercial-rules fact-check · C disposition-truth and consistency audit | [A](v4-round-2/raw-a-fresh-reader.md) · [B1](v4-round-2/raw-b1-factcheck-gallery.md) · [B2](v4-round-2/raw-b2-factcheck-commit-advisor.md) · [C](v4-round-2/raw-c-disposition-audit.md) | [disposition](v4-round-2/disposition.md) |

**How the record is kept.** Raw reports are saved exactly as the reviewers returned them, with a header and the orchestrator's spot-checks appended — every quoted passage is checked against the files, and every external fact the reviewers relied on is re-checked against its primary source before it is used. The disposition says, finding by finding, what was accepted, what was adjusted and why, and where the change landed. Earlier rounds (v1 → v3.2.1) are in [the archive](../_archive/round-3-v3.2.1/reviews/).

## Design

The first design (`design-v1`) was withdrawn on 2026-11-01. Its review record — two rounds with a different model on each lens, a targeted third pass and its closure checks — is kept in [the archive](../_archive/design-v1/reviews/). The record of the second design is kept here: every decision was challenged by independent models before any document was written (round 1), and the finished design was challenged again by other models (round 2). For these records the orchestrator's spot-checks are in each round's disposition rather than appended to the raw reports.

| Round | Reviewers (models) | Raw reports | Disposition |
|---|---|---|---|
| **Design v2 · Round 1** — the decisions, before any document was written | A cost and simplicity (gemini-4-argon) · B security and safety (grok-4.7) · C AI engineering and platform facts (gpt-6.1-sol) | [A](design-v2-round-1/raw-a-cost-simplicity.md) · [B](design-v2-round-1/raw-b-security-safety.md) · [C](design-v2-round-1/raw-c-ai-platform.md) | [disposition](design-v2-round-1/disposition.md) |
