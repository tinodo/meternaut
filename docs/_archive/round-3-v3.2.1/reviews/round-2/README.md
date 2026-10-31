# Round 2 — review of the v2 package

> **Status:** **done** (2026-10-30). This folder holds the verbatim reports of the second review round (only a header line was added to each, plus the orchestrator's spot-check appended at the end), and [the disposition](disposition.md) — one row for every finding, saying what we did and where. The package was then revised from **v2** to **v3**; v2 is frozen in [`docs/_archive/round-2-v2/`](../../_archive/round-2-v2/) (git tag `ideation-v2`).

Round 2 reviewed **v2** (the package after round 1's findings were applied), so it attacked the *revisions* rather than repeating round 1. The three lenses, and what each found:

| # | Lens | Question | Report | Result |
|---|---|---|---|---|
| 1 | **Red team and disposition audit** | Did any v2 change introduce a new contradiction or a new loophole? Is every row of the [round-1 disposition](../round-1/disposition.md) actually true? Is anything silently dropped? | [01 — red team](01-duck-redteam.md) | **15 findings** (2 Critical, 9 High, 4 Medium) and 5 corrections to the round-1 record; all 10 checkable quotes verified |
| 2 | **Fact-check, grounded in Microsoft Learn** | Do the Azure, Microsoft and WAF/CAF claims in the research notes, the catalog evidence map and the deep dives hold against primary sources today? | [02 — fact-check](02-factcheck-learn.md) | **38 claim rows:** 26 confirmed, 11 "Partly", 1 mixed; top-five corrections confirmed by the orchestrator, one "Partly" (the 63% figure) was too cautious |
| 3 | **Brief compliance and consistency** | Does the package still do what the original brief asked, and are definitions, counts, anchors and cross-references consistent (classes, invariants, threats, Release-1 scope, kill criteria)? | [03 — consistency](03-duck-consistency.md) | **9 findings** and a 31-row brief-compliance table; 8 of 9 verified — **R2-C-01 was wrong** (305 catalog rows is correct) |

The orchestrator's spot-check of every quote and external fact a reviewer relied on is at the end of each report. **What we did with all of it:** [disposition.md](disposition.md).

**After v3 — two additional audits.** Round 2 had shown that the orchestrator's own record could be partly untrue, so two further read-only audits were run on the committed v3: [04 — is the disposition true?](04-audit-disposition-truth.md) (7 defects, all real) and [05 — contradictions and loopholes in the live package](05-audit-contradiction-hunt.md) (10 findings, all real). They produced **v3.1** — see [disposition §12](disposition.md#12-post-v3-audit-v31).

The second round's third-party landscape research ([research/02](../../research/02-third-party-and-oss-landscape.md)) was delivered in parallel and is part of v3, not of the review.
