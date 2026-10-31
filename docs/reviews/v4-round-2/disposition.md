# Round 2 — disposition

> **What was reviewed:** the revised v4 at commit `cbd6756`, by four independent read-only reviewers — [A fresh reader through the operator's eyes](raw-a-fresh-reader.md), [B1 Azure billing fact-check (gallery and grammar)](raw-b1-factcheck-gallery.md), [B2 products and commercial-rules fact-check](raw-b2-factcheck-commit-advisor.md) and [C disposition-truth and consistency audit](raw-c-disposition-audit.md). Each raw report has the orchestrator's spot-checks appended.
> **Result:** nothing Critical. The fresh reader found the complaint answered (the day-zero loop, the Lab, the learning contract) and asked for more scenes, one clean separation of "trusted", and a cleaner boundary around the two examples. The fact-checkers found **four wrong and eight over-general statements** in the gallery and grammar, one stale framework name and a handful of unsupported exam-bank claims. The auditor found that the round-1 disposition was **mostly but not fully true** (two header claims and about fifteen rows overstated what had landed), that three families of "state" words were still being mixed, and **eight ways to slip past the lint**. All of it was taken except where noted.
> **Spot-check summary.** Every quote from reviewers A and C was found verbatim at the cited line (A: 14 of 14; C: all of those checked, including each Mermaid, vocabulary and count claim). The facts behind the four "wrong" verdicts and the other highest-risk corrections were re-read on Microsoft Learn and on the Mermaid grammar by the orchestrator (see the appendices of the raw reports). Not every one of B1's 79 and B2's 63 rows was re-verified; the raw reports say which were.

**Legend.** ✅ accepted as asked · 🔧 accepted with a different shape · ◐ accepted in part · ⛔ not done (with reason).

---

## A — fresh reader

| ID | | What was done | Where |
|---|---|---|---|
| **A2-01** Major — the examples still echoed | 🔧 | The two networking decodes (a firewall, a NAT gateway) left the decode table; a stopped-but-allocated VM and a stoppable managed database replaced them. The landscape row on a security analytics product no longer names the unused-table detail. The lint now also reads SVG text, matches across hard-wrapped lines and knows more paraphrases. The sourced rows stay in the exam bank, which is where they belong. | [02 §2](../../02-learning-azure.md#the-grammar-at-work-on-real-services-illustrative-decodes), [landscape](../../research/landscape.md), lint |
| **A2-02** Major — the north star re-specifies the deep dives | ◐ | **Kept whole by design** (the brief asked for one document with the entire idea) but made easier to enter: a two-minute / ten-minute **reading path** at the top, the glossary cut to the terms needed to read it with a pointer to the crosswalk, new scenes placed in the deep dives rather than in 01. ⛔ *Not done:* moving the cast, the Monday letter, the timeline, the outer rims, the limits and the measures out of 01. | [01](../../01-north-star.md) |
| **A2-03** Major — no multi-party decision | ✅ | A **decision room** — one thread for everyone who holds a piece of a shared platform, a private card each, an allocation proposed and argued over, objections that change the plan, one accountable name, verification per party. Pointer in 01 §7; the multi-unit organisation added to the estate document. | [05 §1b](../../05-recommend-act-verify.md#1b-when-more-than-one-person-owns-the-answer), [03 §4](../../03-estate-and-investigation.md#an-organisation-made-of-organisations), [01 §7](../../01-north-star.md#7-act--how-it-works-with-people) |
| **A2-04** Major — "trusted" meant three things | ✅ | **The gates** — replicated, reviewed, commercially verified, credentialed — as four separate questions with their own evidence, in the learning contract; "trusted" is gone as a bare word everywhere (north star, Commons tiers *draft → replicated → maintained*, Moves *active*). Claim, Detector/Move and lesson states are three families, each mapped in the crosswalk. | [11 §2](../../11-the-learning-contract.md#the-gates--one-word-is-not-enough), [11 §7](../../11-the-learning-contract.md#7-one-vocabulary), 01 §2 and §14, [07 §7](../../07-getting-smarter.md#7-the-commons) |
| **A2-05** Minor — voice | ✅ | Five lines rewritten to say what happens (04 §13, 03 §9, 05 §10, 08 §G) and a clever heading renamed (07 §7). | as listed |
| **Top-10 missing scenes** | ✅ | 1 allocation arbitration and 3 shared-platform decision → 05 §1b · 2 the CFO's portfolio and 4 the forecast-to-close rhythm → [06 §15](../../06-people-and-conversation.md#a-target-not-a-pile-of-briefs--the-executives-quarter) · 5 a meter that fits no mechanism → [02 §2](../../02-learning-azure.md#when-nothing-fits--a-story-the-service-is-invented) · 6 a claim disproved by replication and 10 a contributor's journey → [07 §7](../../07-getting-smarter.md#a-claim-challenged--a-story) · 7 trust recovery after a rollback → [05 §9](../../05-recommend-act-verify.md#a-rollback-and-what-it-did-to-trust) · 8 feedback to Azure's documentation owners → one sentence of the 07 §7 story (not a new outer-rim idea, so the count of 37 stands) · 9 a federated enterprise → 03 §4 | as listed |

## B1 — Azure billing facts (gallery, grammar)

Of 79 claims: 47 confirmed, 13 partly, 4 wrong, 8 over-general, 7 with no Azure claim.

| What | | What was done | Where |
|---|---|---|---|
| **Wrong ×4** | ✅ | Inter-zone chatter is not charged (replaced by peered virtual networks, in the gallery and in the "network paths" row); backups replicate to *one* paired region, not three; capacity reservations are not a discount (removed from the rate levers, noted beside the commitments). | [03 §14](../../03-estate-and-investigation.md#14-a-gallery-of-cases--breadth-not-rules), [02 §9](../../02-learning-azure.md#9-learning-the-commercial-reality) |
| **Over-general ×8** | ✅ | Versioning is not available on hierarchical-namespace accounts; whether disks and addresses go with a VM is per resource; zone redundancy costs extra on some services and not others; started-hour granularity is per meter (the example now names a managed database); a multiplier quadruples the bill only when both dimensions double; "a tier you can never leave" became "some services will not let you step back down"; the worked investigation no longer says traffic inside a region is free. | 03 §14, 02 §2, [01 §5](../../01-north-star.md#a-worked-investigation) |
| **Partly ×13** | ✅ (12 of 13) | Registry retention covers untagged manifests only; private endpoints bill per hour while they exist; marketplace eligibility depends on the offer and how it was bought; dev/test wording simplified; allowances are per subscription and month; Flex Consumption is Linux-only and Linux Consumption retires on 30 September 2028; the container idle rate excepts serverless GPU; the search serverless preview has no SLA and cannot be converted; retention features overlap rather than multiply; the 90-day activity log added to the retention note; price-level currencies. ⛔ *Support plans as a non-resource charge* was not fetched by the reviewer and was left as it is. | as above, [03 §1](../../03-estate-and-investigation.md#1-the-estate-model--a-story-not-an-inventory) |
| **Unverified, so no longer stated as fact** | ✅ | The NAT gateway "no stopped state" claim and VM compute billing granularity. | 02 §2 |

## B2 — products and commercial rules

Of 63 claims: 46 confirmed, 10 partly, 2 outdated or renamed, 3 over-general, 2 unverifiable.

| What | | What was done | Where |
|---|---|---|---|
| **CAF and FinOps names** | ✅ | The Govern and Manage *methodologies* (cost management is one of the domains governance covers) replace "the Govern (cost management) discipline"; Learn's FinOps page still says "workload optimization", so the mapping says *rate and usage optimisation* and notes it. | [09](../../09-guardrails-later.md#how-the-idea-lines-up-with-caf-waf-and-the-finops-framework), 01 §13 |
| **Native-tool statements** | ✅ | Anomaly alerts are email, budget alerts can also call an action group; FinOps alerts are Logic Apps, the toolkit's agent plugin is read-only; the official name is *Azure Copilot Optimization Agent*; the SRE Agent learns from every conversation; the Advisor Resource Graph row is now Confirmed; Learn pages carry source metadata, some pointing at private repositories. | [landscape](../../research/landscape.md) |
| **Exam-bank rows** | ✅ | NET-012 (Basic public IPs stay operational but unsupported), STOP-007, STOR-004 (CLI default documented, portal default not), STOR-011 and STOP-001 (confirmed, status raised), DATA-006 (right source: the prepay page), DB-004 and REGION-004 (the "exactly 2×" ratio could not be sourced and was removed; status lowered to Partial), COMMIT-002, and the Databricks auto-termination default. | [exam bank](../../research/exam-bank-cost-traps.md) |
| **Papers** | ✅ | AIOpsLab no longer attributed to "Microsoft Research"; ABACUS described only as far as its abstract goes. | landscape, inspirations |
| **Commitment terms; MACC conditions; telephony** | ✅ | "one or three years" became "a fixed term"; marketplace purchases must be marked *Azure benefit eligible*; voice and text are not Teams features. | 05 §7, 05 §11, 06 §4 |

## C — disposition truth and consistency

| ID | | What was done | Where |
|---|---|---|---|
| **C2-01** the first experiment read as a stop rule | ✅ | The last sentence now says what the result *shows* (where the learning is, which faculty to strengthen); the five success bullets became one description. | [10](../../10-what-next.md) |
| **C2-02** provisional profiles and advice | ✅ | "A Brief never rests on a provisional or doc-only profile for a savings claim"; "firm" dropped. | 02 §8, 01 §11, 08 |
| **C2-03** public report card | ✅ | "Shown to the organisation"; only the open benchmark is public. | 02 §8, 04 §15, 12 |
| **C2-04** `LabProven`, "proof boundary" | ✅ | `LabTested`; "assurance boundary"; the tagline and other residues ("proven", "proof") replaced. | 04 §13, 05 §4, README, 01 |
| **C2-05** the Forger half-promoted | ✅ | Removed from the outer-rim teasers; named in the Examiner's row of the cast (still 13 agents). | 01 §9, §12 |
| **C2-06** `;` in state labels | ✅ | Removed; the lint now rejects it (the Mermaid grammar ends a description at `;`). | 04 §13, 06 §5, lint |
| **C2-07** "no" and "success" skipped the Lesson | ✅ | Declined → Lesson → Offered again on a re-open condition; Sustained → Lesson. | 05 §9 |
| **C2-08** one exam in the picture | ✅ | The picture now shows the training Terrarium, the public benchmark and the credential exam; only the training exam feeds lessons back. | 07 §3 |
| **C2-09** three families of states | ✅ | Claim states (02), Detector and Move states (04: `Active`, not "trusted"), lesson rungs (07: a pattern is a *candidate* claim or Detector) — kept apart and mapped in 11 §7. | 02 §4, 04 §13, 07 §2 and §7, 11 §7 |
| **C2-10** vocabulary | ✅ | *Experiment Ledger* in the Lab hub; *technical lead* (not steward); *claims* (not "entries"); "playbook" removed; *tell* defined. | 04, 03, 06, 11 §7 |
| **C2-11** "mechanism" column holds non-mechanisms | ✅ | Column renamed *Where it shows up*; "a cap that bites" flagged as a candidate mechanism. | 03 §14, 02 §6 |
| **C2-12** absolutes and unscoped "verified" | ✅ | Hedged in 01, 07, 12 and the four-clocks picture (the Watch clock "on fast signals"). | as listed |
| **C2-13 … C2-19** | ✅ | The law reworded in the outer rims; the link in the limits paragraph retargeted; archive folders named and the tag claim made true by tagging; "four rules", EUR 215 and five evidence grades; glosses at first use; AGENTS rule 5 corrected and a purchase rule (10) added; the cross-region story kept only in the north star. | as listed |
| **Disposition rows** | ✅ | Both header claims and every row in the auditor's table were made true or reworded in place in the [round-1 disposition](../v4-round-1/disposition.md), each marked. | round 1 |
| **Missing from the round-1 disposition** | ◐ | "Multiply" wording, the Databricks default, "every metric", the Learn-source remark — done. ⛔ *Not added:* "a spending limit does not prevent all charges" (not verified); the liability question for published claims (guardrails later); cosmetic remarks on two pictures. | — |
| **Lint-defeat list ×8** | ◐ | Done: guards now cover every live document except AGENTS, CHANGELOG and the review record, and the text of SVGs; wrapped lines and more paraphrases are matched; more governance vocabulary is rejected; the purchase wording is guarded; labelled edges (`A -- go --> B`) are read, the pipeline threshold is 70%, and state diagrams are checked for `;` and for straight lines; unchecked link forms raise a warning; orphans are checked everywhere. ⛔ *Accepted as limits:* a paraphrase can still slip past a pattern; a decorative hub can hide a pipeline; ASCII pictures are not tested; the archive and raw reports are exempt by rule. | `tools/check-docs.py` |

---

## The one tension, and how it was resolved

**A asked for more scenes (ten of them) and, in the same breath, for a shorter north star.** Both are right, and they are reconciled by *where* things go: every new scene lives in a deep dive (05, 06, 02, 07, 03), the north star gained only a reading path and a three-line pointer, and its glossary lost entries that the crosswalk covers. The north star is about 6,350 words (6,701 in the draft that round 1 reviewed, 6,224 after it), and the twelve documents about 43,300 (33,152 in that draft, 41,000 after round 1). The judgement from round 1 stands: the operator complained about paperwork and a missing heart, not length.

## Tooling after round 2

`tools/check-docs.py` — see the list under *Lint-defeat list* above. Self-test extended (labelled edges, state diagrams, `;`, wrapped lines, governance vocabulary, purchase wording, link forms); each new guard was also shown to fire on a throwaway probe file, which was then deleted. Strict run clean.
