# The rubber-duck record

Every version of the ideation is reviewed by independent agents before it is called done. This folder keeps what they said, verbatim, and what was done about it.

| Round | Reviewers | Raw reports | Disposition |
|---|---|---|---|
| **v4 · Round 1** — reviewed at commit `d267654` | A visionary / AI researcher · B FinOps and Azure domain (Learn-grounded) · C the skeptic · D brief-compliance and anti-pattern audit | [A](v4-round-1/raw-a-visionary.md) · [B](v4-round-1/raw-b-finops-domain.md) · [C](v4-round-1/raw-c-skeptic.md) · [D](v4-round-1/raw-d-brief-compliance.md) | [disposition](v4-round-1/disposition.md) |
| **v4 · Round 2** — reviewed at commit `cbd6756` | A fresh reader through the operator's eyes · B1 Azure billing fact-check · B2 products and commercial-rules fact-check · C disposition-truth and consistency audit | [A](v4-round-2/raw-a-fresh-reader.md) · [B1](v4-round-2/raw-b1-factcheck-gallery.md) · [B2](v4-round-2/raw-b2-factcheck-commit-advisor.md) · [C](v4-round-2/raw-c-disposition-audit.md) | [disposition](v4-round-2/disposition.md) |

**How the record is kept.** Raw reports are saved exactly as the reviewers returned them, with a header and the orchestrator's spot-checks appended — every quoted passage is checked against the files, and every external fact the reviewers relied on is re-checked against its primary source before it is used. The disposition says, finding by finding, what was accepted, what was adjusted and why, and where the change landed. Earlier rounds (v1 → v3.2.1) are in [the archive](../_archive/round-3-v3.2.1/reviews/). The v4 dispositions link to the ideation documents of that version, which are kept at the git tag `ideation-v4`; the lint does not check those links.

## Design

The first design (`design-v1`) was withdrawn on 2026-11-01. Its review record — two rounds with a different model on each lens, a targeted third pass and its closure checks — is kept in [the archive](../_archive/design-v1/reviews/). The record of the second design is kept here: every decision was challenged by independent models before any document was written (round 1), and the finished design was challenged again by other models (round 2). For these records the orchestrator's spot-checks are in each round's disposition rather than appended to the raw reports.

| Round | Reviewers (models) | Raw reports | Disposition |
|---|---|---|---|
| **Design v2 · Round 1** — the decisions, before any document was written | A cost and simplicity (gemini-4-argon) · B security and safety (grok-4.7) · C AI engineering and platform facts (gpt-6.1-sol) | [A](design-v2-round-1/raw-a-cost-simplicity.md) · [B](design-v2-round-1/raw-b-security-safety.md) · [C](design-v2-round-1/raw-c-ai-platform.md) | [disposition](design-v2-round-1/disposition.md) |
| **Design v2 · Round 2** — the written design (commit `3543f3b`), a closure check of the fixes by the same reviewers, and a last verification by gpt-6.1-sol | A learning and the core idea (gpt-6-sol) · B platform facts on Microsoft Learn (claude-sonnet-5) · C security, safety and compliance, adversarial (grok-4.6) · D cost honesty (gpt-5.6-sol) · E consistency, tone and readability (gemini-3.8-flash) · F a novice reader who saw only two documents (claude-haiku-5.5) | [A](design-v2-round-2/raw-a-learning.md) · [B](design-v2-round-2/raw-b-learn-facts.md) · [C](design-v2-round-2/raw-c-security.md) · [D](design-v2-round-2/raw-d-cost.md) · [E](design-v2-round-2/raw-e-consistency.md) · [F](design-v2-round-2/raw-f-novice.md) · [closure checks](design-v2-round-2/raw-closure-checks.md) · [final verification](design-v2-round-2/raw-final-verification.md) | [disposition](design-v2-round-2/disposition.md) |

## Stranger test (ideation v5 and design v3)

Before this release every live document was given, cold, to readers who had never seen the repository, with one question per sentence: *why does this sentence exist, for someone who was not in the room?* The readers looked for reasoning residue, undefined terms, contradictions, overclaims and wrong product facts, and checked the claims that mattered on Microsoft Learn. Each reader had a different model from its neighbours and read only the files it was assigned. The brief they were given is [brief-cold-reader.md](stranger-test-v5/brief-cold-reader.md).

| Reader (model) | Read | Raw report | Findings |
|---|---|---|---|
| design A (gpt-6.1-sol) | design index, goals and scope, architecture | [raw-design-a](stranger-test-v5/raw-design-a.md) | 17 |
| design B (gemini-4-argon) | agents and workflows, knowledge and learning | [raw-design-b](stranger-test-v5/raw-design-b.md) | 17 |
| design C (grok-4.7) | data and integrations, agreements and access | [raw-design-c](stranger-test-v5/raw-design-c.md) | 16 |
| design D (gpt-5.6-sol) | security and governance, safeguards and drift | [raw-design-d](stranger-test-v5/raw-design-d.md) | 15 |
| design E (claude-sonnet-5) | testing and evaluation, delivery and operations, cost and FinOps | [raw-design-e](stranger-test-v5/raw-design-e.md) | 13 |
| design F (gemini-3.8-flash) | technology register, decisions, roadmap | [raw-design-f](stranger-test-v5/raw-design-f.md) | 15 |
| idea A (gpt-6-sol) | north star, studying Azure | [raw-idea-a](stranger-test-v5/raw-idea-a.md) | 19 |
| idea B (grok-4.6) | estate and investigation, finding out without spending | [raw-idea-b](stranger-test-v5/raw-idea-b.md) | 13 |
| idea C (gpt-5.6-terra) | recommend, act and verify; getting smarter | [raw-idea-c](stranger-test-v5/raw-idea-c.md) | 8 |
| idea D (gpt-6.1-sol) | people and conversation, outer rims | [raw-idea-d](stranger-test-v5/raw-idea-d.md) | 19 |
| idea E (claude-sonnet-5) | the learning contract, the press release | [raw-idea-e](stranger-test-v5/raw-idea-e.md) | 11 |
| idea F (gpt-6.1-terra) | the research documents | [raw-idea-f](stranger-test-v5/raw-idea-f.md) | 38 |
| novice (claude-haiku-5.5) | README, north star, design index | [raw-novice](stranger-test-v5/raw-novice.md) | 20 |

That is 221 findings: 38 blockers, 110 majors and 73 minors. The fixes followed a short list of decisions that the findings had in common ([brief-fixes.md](stranger-test-v5/brief-fixes.md)); each document was fixed by one owner, and claims about Microsoft products were read on Microsoft Learn before they were acted on (one reviewer claim was rejected that way: hosted agents deploy from a source zip, with no container registry).

A second reader then checked every finding against the fixed documents and hunted for contradictions the fixes had created ([brief-closure.md](stranger-test-v5/brief-closure.md)); those reports are kept next to the raw ones, and the contradictions they found were fixed in turn.

| Closure check (model) | Reports it covers | Report |
|---|---|---|
| closure 1 (claude-sonnet-5.5) | design A, B, C | [closure-1](stranger-test-v5/closure-1.md) |
| closure 2 (gpt-6.1-terra) | design D, E, F | [closure-2](stranger-test-v5/closure-2.md) |
| closure 3 (gpt-6-sol) | idea A, B | [closure-3](stranger-test-v5/closure-3.md) |
| closure 4 (grok-4.7) | idea C, novice | [closure-4](stranger-test-v5/closure-4.md) |
| closure 5 (gpt-5.6-sol) | idea D, E | [closure-5](stranger-test-v5/closure-5.md) |
| closure 6 (gpt-6.1-sol) | idea F (research) | [closure-6](stranger-test-v5/closure-6.md) |

Three more cold readers, who had seen none of this, then read the front door and the new documents as they stood after the fixes ([brief-final-read.md](stranger-test-v5/brief-final-read.md)); their findings were fixed or answered too.

| Final reader (model) | Read | Raw report | Findings |
|---|---|---|---|
| final 1 (gpt-6.1-terra) | README, north star | [raw-final-1](stranger-test-v5/raw-final-1.md) | 12 |
| final 2 (claude-sonnet-5.5) | finding out without spending, design index, agreements and access | [raw-final-2](stranger-test-v5/raw-final-2.md) | 14 |
| final 3 (gpt-6-luna) | studying Azure, recommend act verify, the learning contract | [raw-final-3](stranger-test-v5/raw-final-3.md) | 7 |

The [disposition](stranger-test-v5/disposition.md) says what was accepted, what was not and why.
