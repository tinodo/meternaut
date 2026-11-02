# Consistency audit (class 4 contradictions + class 8 buildability)

## 1) Verdict
Mostly. A stranger can follow the design intent, but several cross-file contradictions and buildability mismatches make implementation error-prone unless resolved first.

## 2) Findings

| # | Severity | File:line | Class | Quote | Why | Fix |
|---|---|---|---|---|---|---|
| 1 | Blocker | `docs/experience/04-messages-and-cards.md:103`; `docs/experience/cards/data/recommendation.json:6` + `docs/experience/cards/data/our-mistake.json:6` | 4, 8 (buildability) | Q1: “no two plans share a code.” Q2: `"planCode": "7F3K-92QD"` appears in unrelated examples (E1 recommendation and E2 incident). | The written invariant (“one code per plan”) is violated by sample data reused across different plans. Builders cannot validate uniqueness logic from provided artifacts. | Give each sample plan its own plan code; keep one code only across artifacts that represent the same plan lifecycle. |
| 2 | Major | `docs/experience/03-organisation-journeys.md:51`; `docs/img/experience-approval-page.svg:88` | 4 | Q1: “The price check expires on 10 June.” Q2: “Expires Wednesday 9 June, 14:00 CET.” | The same E4 example has two different expiry dates. This breaks trust and testability of expiry handling. | Choose one expiry timestamp for E4 and apply it everywhere (docs, card data, wireframe labels). |
| 3 | Major | `docs/experience/04-messages-and-cards.md:58`; `docs/experience/02-owner-journeys.md:184` | 4 | Q1: “Every card but Hello carries… ‘Why you are getting this’.” Q2: “Every card has a line ‘Why you are getting this’…” | Contradiction about Hello card behavior; one file excludes Hello, another says all cards. | Keep one rule: either “all cards” or “all except Hello,” then align both files and card templates. |
| 4 | Major | `docs/experience/04-messages-and-cards.md:48`; `docs/experience/04-messages-and-cards.md:50` | 4 | Q1: “utility cards … offer Explain only.” Q2: “Talk to a person … beside Explain on the utility cards.” | Internal contradiction in the same document: utility cards cannot both be “Explain only” and also expose “Talk to a person.” | Replace “offer Explain only” with wording that explicitly includes “Talk to a person” (and scope of other controls). |
| 5 | Minor | `docs/experience/04-messages-and-cards.md:127`; `docs/experience/cards/manifest.json:188-190` | 8 (buildability) | Q1: C11 buttons include “Widen … Keep it narrow … Show the resources.” Q2: manifest verbs list only `widen`, `keep-narrow`. | Manifest is presented as implementation inventory, but C11’s third visible action is not represented there, causing incomplete behavior contracts for tool-driven checks. | Add an explicit manifest field for non-verb actions (e.g., `openUrlActions: ["show-resources"]`) or include it in a normalized action list. |

## 3) Sentences I would delete
None. These issues are contradictions/mismatches; deletion is less safe than correction.

## 4) Fact checks
No external product fact-checks run in this assignment. Scope was restricted to internal consistency (class 4) and buildability mismatches (class 8).

## 5) Questions left unanswered
1. Is `cards/manifest.json` intended to be authoritative for all visible actions, or only state-changing verbs?
2. Should Hello include an explicit “Why you are getting this” line, or remain intro-only?
3. Which single canonical timestamp should govern E4 expiry across all assets?
