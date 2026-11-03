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

## External validation (design v3)

After the release, an independent AI reviewer read the design and filed 26 findings in two reports (in Dutch, kept as received). Each finding was checked against the files before anything changed: 10 were confirmed and fixed, 6 were partly right, 5 were already covered or stale, 2 were not adopted and 3 were judgements that the changes reflect.

| Reviewer | Read | Raw report | Disposition |
|---|---|---|---|
| An independent AI reviewer (model not stated), two reports | A: knowledge and learning, testing and evaluation · B: goals, architecture, data, security, delivery, cost, register, decisions, agreements, roadmap and tools | [raw-validation-1](validation-1/raw-validation-1.md) | [disposition](validation-1/disposition.md) |

## Experience design

The experience layer (what people see, receive and decide) was designed on top of the released design. Its decisions were challenged by four reviewers on different model families before any document was written ([brief.md](experience-round-1/brief.md)). The written documents were then read cold by readers on other models ([brief-cold-reader.md](experience-round-2/brief-cold-reader.md)), and closure checkers verified every finding against the fixed text ([brief-closure.md](experience-round-2/brief-closure.md)). Two final checkers then read the fixes for what they broke.

| Round | Reviewers (models) | Raw reports | Disposition |
|---|---|---|---|
| **Experience · Round 1** — the decisions, the card templates and the wireframes | A people, attention and trust (gpt-6.1-sol) · B the adversary (grok-4.7) · C FinOps, finance and agreements (gemini-4-argon) · D platform feasibility and accessibility (claude-sonnet-5) | [A](experience-round-1/raw-a-people.md) · [B](experience-round-1/raw-b-adversary.md) · [C](experience-round-1/raw-c-finops.md) · [D](experience-round-1/raw-d-platform.md) | [disposition](experience-round-1/disposition.md) |
| **Experience · Round 2** — the finished documents, the templates and the wireframes, read cold: 126 findings, 24 of them blockers | A the resource owner (claude-sonnet-5.5) · B FinOps and finance (gpt-6-sol) · C Teams cards (gpt-5.6-sol) · D letters and pages (grok-4.6) · E attention, trust and inclusion (gemini-4-argon) · F platform, reviewers, voice and testing (gpt-6.1-terra) · G a novice at the front door (claude-haiku-5.5) · H cross-document consistency (gpt-5.3-codex) | [A](experience-round-2/raw-a-owner.md) · [B](experience-round-2/raw-b-finops.md) · [C](experience-round-2/raw-c-teams.md) · [D](experience-round-2/raw-d-web.md) · [E](experience-round-2/raw-e-trust.md) · [F](experience-round-2/raw-f-platform.md) · [G](experience-round-2/raw-g-novice.md) · [H](experience-round-2/raw-h-consistency.md) | [disposition](experience-round-2/disposition.md) |
| **Experience · Closure** — every round-2 finding checked against the fixed text, and the fixes checked for new defects | 1 platform and consistency (gpt-6-sol) · 2 owner and Teams cards (gpt-6.1-terra) · 3 trust, letters and pages (claude-sonnet-5.5) · 4 FinOps and novice (grok-4.7) | [1](experience-round-2/closure-1.md) · [2](experience-round-2/closure-2.md) · [3](experience-round-2/closure-3.md) · [4](experience-round-2/closure-4.md) | [disposition](experience-round-2/disposition.md) |
| **Experience · Final check** — every part-closed or new item of the closure round checked again, and the fixes read for what they broke | 1 platform, owner journeys and Teams cards (gemini-4-argon) · 2 trust, letters, pages, FinOps and the records (gpt-6.1-sol) | [1](experience-round-2/final-1.md) · [2](experience-round-2/final-2.md) | [disposition](experience-round-2/disposition.md) |

## Design v5 (what the experience needs of the technical design)

The experience layer asked 29 things of the technical design ([experience 15](../experience/15-asks-of-the-technical-design.md)). Writers placed them in the design documents from one shared sheet of settled wording ([writer-sheet.md](design-v5/writer-sheet.md)); two reviewers on other model families then read the result against the brief in [brief.md](design-v5/brief.md), one for landing, contradictions and the repository's rules, one as an adversary for security, cost and Microsoft facts.

| Round | Reviewers (models) | Raw reports | Disposition |
|---|---|---|---|
| **Design v5** — the technical design after the 29 asks were placed | A landing, contradictions and rules (gpt-6.1-sol): 29 rows, 11 Majors · B adversary, cost and Microsoft facts (grok-4.7): 2 Blockers, 5 Majors | [A](design-v5/raw-a-landing.md) · [B](design-v5/raw-b-adversary.md) | [disposition](design-v5/disposition.md) |
| **Design v5 · Closure** — every finding of the two reviewers checked against the fixed text, and the fixes read for what they broke | 1 (gpt-5.6-sol): 14 closed, 5 closed in part, 12 new defects | [1](design-v5/closure-1.md) | [disposition](design-v5/disposition-closure.md) |

## Build plan (phase 0 and phase 1a)

The plan for the first two phases of the roadmap is a plan only; nothing in it is built. Its specification was reviewed by two reviewers on different model families before any plan document was written; the revised specification, which the plan's writers worked from, is [spec-v2.md](build-plan-v1/spec-v2.md). The brief for the readers of the written plan is [brief-cold-reader.md](build-plan-v1/brief-cold-reader.md); the written plan was then read cold by five readers on other model families, and two checkers verified every finding against the fixed plan ([brief-closure.md](build-plan-v1/brief-closure.md)), and a final checker read the fixes ([brief-final.md](build-plan-v1/brief-final.md)).

| Round | Reviewers (models) | Raw reports | Disposition |
|---|---|---|---|
| **Build plan v1 · Round 1** — the specification ([spec.md](build-plan-v1/spec.md), [brief.md](build-plan-v1/brief.md)) | A delivery realism (gemini-4-argon): 10 findings · B the adversary (gpt-6-sol): 15 findings | [A](build-plan-v1/raw-a-delivery.md) · [B](build-plan-v1/raw-b-adversary.md) | [disposition](build-plan-v1/disposition.md) |
| **Build plan v1 · Cold readers** — the written plan, 84 findings: 14 Blockers, 55 Majors, 15 Minors | 1 order and dependencies (gpt-6.1-sol) · 2 requests, cost and README (gemini-4-argon) · 3 the checks (grok-4.7) · 4 consistency (gpt-6-sol) · 5 a novice at the front door (claude-haiku-5.5) | [1](build-plan-v1/cold-1.md) · [2](build-plan-v1/cold-2.md) · [3](build-plan-v1/cold-3.md) · [4](build-plan-v1/cold-4.md) · [5](build-plan-v1/cold-5.md) | [disposition](build-plan-v1/disposition-cold-readers.md) |
| **Build plan v1 · Closure** — every cold-reader finding checked against the fixed plan, and the fixes read for what they broke | 1 readers 1, 3 and 4 (gpt-6.1-sol): 30 closed, 14 in part, 1 open, 3 new defects · 2 readers 2 and 5, and the new text (claude-sonnet-5.5): 28 closed, 5 in part, 6 new defects | [1](build-plan-v1/closure-1.md) · [2](build-plan-v1/closure-2.md) | [disposition](build-plan-v1/disposition-closure.md) |
| **Build plan v1 · Final check** — the items the closure round left open or found | One checker (grok-4.7): 24 of 25 closed, 1 in part, 1 new minor defect; fixed | [final-1](build-plan-v1/final-1.md) | [disposition](build-plan-v1/disposition-closure.md) |

## Build plan v2 (the four adjustments)

After the plan was read, four adjustments were asked for: a small learning demonstration brought forward, pilot-data feasibility in week 0, a measurable "worth acting on", and a provisional schedule with one workload end to end first. Two reviewers on different model families read the changed plan against the brief in [brief.md](build-plan-v2/brief.md), and a closure checker verified every finding against the fixed plan ([brief-closure.md](build-plan-v2/brief-closure.md)). The first code, tests and templates were built under the same edition and were reviewed the same way, by a reviewer on another model family, in two rounds.

| Round | Reviewers (models) | Raw reports | Disposition |
|---|---|---|---|
| **Build plan v2 · Round 1** — the changed plan: 24 findings, 1 Blocker, 19 Majors, 4 Minors | A design validity (gpt-6.1-sol): 9 findings · B consistency and arithmetic (grok-4.7): 15 findings | [A](build-plan-v2/raw-a-design.md) · [B](build-plan-v2/raw-b-consistency.md) | [disposition](build-plan-v2/disposition.md) |
| **Build plan v2 · Closure** — every finding checked against the fixed plan, and the fixes read for what they broke | One checker (claude-sonnet-5.5): 18 closed, 4 in part, 11 new minor defects; fixed | [closure-1](build-plan-v2/closure-1.md) | [disposition](build-plan-v2/disposition-closure.md) |
| **Build plan v2 · Final check** — the items the closure round left open or found | The same checker: 15 of 15 closed, 8 new small defects (5 Minor, 3 Nit); fixed | [final-1](build-plan-v2/final-1.md) | [disposition](build-plan-v2/disposition-final.md) |
| **Build review 1** — the code and the templates built so far ([brief](build-plan-v2/brief-build.md)): 13 findings, 4 Blockers, 7 Majors, 2 Minors | One reviewer (gemini-4-argon), against the plan text each part implements | [build-review-1](build-plan-v2/build-review-1.md) | [disposition](build-plan-v2/build-disposition.md) |
| **Build review 1 · Closure** — every finding checked against the fixed files, and the fixes read for what they broke | The same reviewer: 13 closed, 3 new minor defects, fixed | [build-closure-1](build-plan-v2/build-closure-1.md) | [disposition](build-plan-v2/build-disposition-closure.md) |

## The development hub

The hub that every model call of the learning demonstration goes through ([`hub/`](../../hub/README.md)) was deployed to a resource group of its own and checked with calls and refusals; it was withdrawn on 2026-11-03 (see the [changelog](../../CHANGELOG.md)). A reviewer on another model family then read its files, the patch to the accelerator, the access contract and the harness's client against the plan text they implement.

| Round | Reviewer (model) | Raw report | Disposition |
|---|---|---|---|
| **Hub review 1** — the files and the patch as built: 18 findings, 1 Blocker, 8 Majors, 9 Minors | One reviewer (gpt-6.1-sol) | [hub-review-1](hub-v1/hub-review-1.md) | [disposition](hub-v1/hub-disposition.md) |
| **Hub review 1 · Closure** — every finding checked against the fixed files, and the fixes read for what they broke: 8 closed, 9 in part, 1 open, 5 new (3 Majors, 2 Minors) | The same reviewer | [hub-closure-1](hub-v1/hub-closure-1.md) | [disposition](hub-v1/hub-disposition-closure.md) |
