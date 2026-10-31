# Round 2 · Reviewer C — disposition truth and consistency audit (raw report)

> **Status: RAW — verbatim as returned.** Agent type `general-purpose`, read-only, 2026-10-31. Brief: check whether the round-1 disposition is true row by row, whether the revised documents are consistent with each other (counts, vocabulary, links, wording), and whether the lint can be defeated (v4 revision, commit `cbd6756`). The orchestrator's spot-checks are appended; the disposition is in [disposition.md](disposition.md).

---

# R2-C report: disposition truth and consistency (commit cbd6756)

**Verdict**
1. **Is the disposition honest?** Mostly, not fully. I opened every "Where" target of the 48 rows. 33 are literally true, 15 are false or overstated (table below), and two header claims are false.
2. **Worst misstatements:** "no gate, no kill criterion, no register" (10-what-next.md:38 is a stop rule), "Prove" removed (a `LabProven` state remains), "Kept inside the organisation" (02 and 12 still say public), "one item partly" (five ◐ rows).
3. **Is the package consistent?** Counts hold: 34 cases, 37 rim ideas, 145 traps, and 24 papers (all 27 arXiv IDs re-checked against the arXiv API). The 14 mechanism names are identical in 01 and 02, and the README map matches the files. The repo is PRIVATE per `gh`, LICENSE is MIT, `.gitignore` exists, no stray tracked files, no "public/published" claim (press release is flagged fictional). Semantics diverge: claim states, advice from provisional profiles, ledger/notebook, and two pictures that contradict their prose.
4. **Mermaid and lint:** two state diagrams put `;` inside transition labels and likely mis-render. `--strict` (0/0) and `--self-test` pass, but eight evasions exist (end of report).
5. **Counts:** Critical 0 · Major 10 · Minor 9. Fix first: C2-01, 02, 03, 06, 09.

Paths below are relative to `<repo>\` (full path = this prefix + the shown path). Line numbers are 1-based.

## Findings

**C2-01 · Major — `docs\10-what-next.md`, "Step zero — the paper test" (l.38, l.74)**
Quote: "the idea needs rethinking before anything else is built. (It is an experiment, not a gate: its results shape everything after.)"
Why: This is a stop rule, i.e. a kill criterion/gate (AGENTS rule 2), and it falsifies disposition.md:83. L.74, "**What success looks like** — a description, not a gate:", is the old "done when" list renamed. The lint has no pattern for either.
Fix: End the sentence at "after the correction" and say what the result teaches. Fold the five bullets into one descriptive sentence.

**C2-02 · Major — `docs\02-learning-azure.md` "8. Knowing what it does not know" (l.274) vs `docs\11-the-learning-contract.md` "2." (l.35)**
Quote: "When advice rests on a provisional or doc-only profile, the Brief says so" vs "It **never produces savings advice** for an estate until it has been commercially verified there." Also 01:295 and 08:10: "firm advice follows once a bill confirms it" / "firm advice follows once a customer's own bill confirms it".
Why: The central A-04/C-01 rule is contradicted in 02, and "firm" implies softer advice earlier.
Fix: In 02 §8 write "a Brief never rests on such a profile; it asks or watches". Drop "firm" in 01 and 08.

**C2-03 · Major — `docs\02-learning-azure.md` §8 (l.272); `docs\12-press-release-from-the-future.md` "THE TOUGH QUESTIONS" (l.39)**
Quote: "The map is public on the report card." / "by being right, in public, on a report card that leads with what it is worst at". Compare 07:162: "plain, kept inside the organisation (the open benchmark is separate)". Also 04:305 "are published on the report card".
Why: D-15 is marked fixed. Public estate numbers are the leak D-15 was about.
Fix: Use "shown to the organisation". Keep the open benchmark as the only public artefact.

**C2-04 · Major — `docs\04-experiments-and-the-lab.md` §13 (l.262); `docs\05-recommend-act-verify.md` §4 (l.101)**
Quote: "BackTested --> LabProven: tried in the Lab, with failure injection for Moves"; "exactly where its proof *stops*".
Why: Contradicts disposition A-03 and C-02 (`"Prove" removed.`) and 11 §3 ("The word *prove* is not available to them").
Fix: Rename the state `LabTested`. Replace "proof boundary" with "assurance boundary".

**C2-05 · Major — `docs\01-north-star.md` "12. The outer rims" (l.306) and "9. The cast"**
Quote: "**The Forger.** An adversary that forges clever waste and plausible decoys to fool the Detectives, so the Exam stays hard." Compare 08:46 "Now part of the core Exam" and CHANGELOG:12 "a cast of 13 agents".
Why: A-08's "promoted … to the core" only half landed. The cast table has 13 rows and no Forger.
Fix: Delete the 01 §12 bullet. Add the Forger to the cast (14) or call it the Examiner's adversarial mode. Fix the CHANGELOG count.

**C2-06 · Major — `docs\04-experiments-and-the-lab.md` §13 (l.268); `docs\06-people-and-conversation.md` §5 "The alert" (l.179)**
Quote: "Reviewed --> Shadow: a Detector runs and tells nobody; a Move runs at assist level only"; "Asked --> Escalating: no answer, so the circle widens; an emergency uses text and voice".
Why: Mermaid's `stateDiagram.jison` (fetched) ends a description at `;`. The tails would parse as stray states (";", "a", "Move", … and ";", "an", "emergency", …). UNVERIFIED in a live renderer; derived from the grammar. The lint cannot see it.
Fix: Use "—" or "," instead of `;`. Add a lint rule for `;` in state-diagram labels.

**C2-07 · Major — `docs\05-recommend-act-verify.md` §9 diagram (l.262–275)**
Quote: "Declined --> Lesson: the reason is kept, with re-open conditions"; "Sustained --> [*]". Prose: `"No" is not an end state.` (l.280) and "**Everything ends in a Lesson**, not in a report." (l.281).
Why: The doc's "most important picture" ends "no" at `Lesson --> [*]` and lets success skip Lesson.
Fix: Add `Lesson --> Offered: a re-open condition is met` and `Sustained --> Lesson`.

**C2-08 · Major — `docs\07-getting-smarter.md` §3 flowchart (l.114) vs independence bullets (l.151)**
Quote: `SC -.->|"a miss becomes an Agenda question and a Lesson"| IN` vs "A miss on the credential exam is *not* fed back into training until the exam is retired."
Why: The picture shows one exam and one feedback loop. The A-05/C-03 fix (three exams kept apart) is invisible in it and contradicted by it.
Fix: Draw the three exams. Allow feedback only from the training Terrarium. Send the credential exam to the report card only.

**C2-09 · Major — claim and Detector states across `docs\02-learning-azure.md` §4, `docs\04-…` §13, `docs\07-…` §2 and §7, `docs\11-…` §7**
Quote: "MechanismVerified --> Replicated" (02:162) vs "*Draft* (proposed, with receipts) → *Reproduced* (re-run independently in a stated scope) → *Trusted*" (07:264). Also "CommerciallyVerified --> Compiled: general enough for a Detector or a Move" (02:165) vs "observation → lesson → pattern → Detector → Atlas claim" (inspirations.md:24) vs "candidate for a Detector or an Atlas claim" (11:100).
Why: A-08 promised one life cycle. Replicated/Reproduced, Compiled/Drafted, Watched/Shadow and Stale/Demoted name the same stages. A Detector precedes the Atlas claim on the 07 ladder and follows it in 02. 02:272's "verified, provisional, doc-only, unknown" is a fourth set.
Fix: Add one table "state → Commons tier → ladder rung" to 11 §7. Use "Replicated" everywhere. Pick one Detector origin.

**C2-10 · Major — `docs\11-the-learning-contract.md` "7. One vocabulary" vs `docs\04-experiments-and-the-lab.md` §3**
Quote: 11:105 "the page of one experiment (hypothesis, prediction, result, surprise)" vs 04:92 "The Lab Notebook is the hub: every bench reads *what is worth learning next* from it". Also "adapts the playbook" (06:244), "investigation playbooks" (11:15), `Detectors without evidence` (03:124, meaning a "tell"), "Findings become Atlas entries" (01:52), "a back-tested watcher" (07:72), "Technical steward" (03:67, 11:109), "Engineer / steward" (06:67).
Why: The crosswalk promises one word per thing, but 04 uses "Lab Notebook" for the role 11:104 gives the Experiment Ledger. "Playbook", "Atlas entry" and "watcher" are undefined, and "Lesson" (11:99) has two meanings.
Fix: Rename the 04 hub node "Experiment Ledger". Add playbook, ledger, refuted-shelf and tell rows. Use "tell" at 03:124.

**C2-11 · Minor — `docs\02-learning-azure.md` §6 (l.244); `docs\03-estate-and-investigation.md` §14 (l.281–291)**
Quote: "a **cap that bites**"; rows "**Network path**", "**Agreement**", "**Marketplace**", "**Governance**", "**Dev/test**", "**Region**", "**Retention**", "**Unit economics**", "**Spend more**" sit under a "Mechanism" header. Compare 01:118 "is one or a few of **fourteen mechanisms**".
Why: The closed set of 14 is broken in the docs' own tables. The gallery itself (34 cases, all 14 covered) is correct.
Fix: Rename the column "Where it shows up". Name "cap that bites" a proposed mechanism.

**C2-12 · Minor — strong claims: `docs\01-north-star.md`, `docs\07-getting-smarter.md`, `docs\12-…`, `docs\img\four-clocks.svg`**
Quote: "**Everything it learns compounds.**" and "the more it finds" (01:20); "*it gets better with every one of them*" (07:239); "with *no rule for any of them*, it is learning." (07:301); "The Atlas has hundreds of verified profiles" (01:295, also 01:349 and 07:180, scope unstated); "studies new Azure services within hours" (12:12, no "provisional"); "WATCH · minutes to hours" with "A deployment that just changed the bill." (SVG, not hedged like 01:96); "Overnight the system explores alternative architectures" (01:303).
Why: Absolutes and unscoped "verified" violate the revision's own rules (11 §2, "never interchangeable"). The bank's Status "Verified" is a third meaning (a Learn page was read).
Fix: Add hedges and scopes ("mechanism-verified", "aims to"). Redraw the Watch clock as "on fast signals".

**C2-13 · Minor — `docs\08-outer-rims.md` §A (l.12); `docs\research\inspirations.md` (l.15, l.74)**
Quote: anything short-lived pays a minimum; Expensive reasoning once, cheap detection forever. Compare 04:250 "Expensive reasoning once — cheap nominations after".
Why: The B-02 and A-07 corrections landed in 02 and 04 only. 08's "law" is the one reviewer B refuted. Inspirations §7 quotes a phrase that no longer exists at its link target.
Fix: Reword 08 with "usually". Change inspirations to "cheap nominations after".

**C2-14 · Minor — `docs\01-north-star.md` "15. The honest limits" (l.335)**
Quote: "Documents and bills disagree, and the Lab cannot reproduce everything" (link text "studying Azure, §8").
Why: 02 §8 holds only a coverage map, the frontier, humility and curiosity ("A learning system must have a map of its own ignorance."). Neither idea is there. It sits nearer 02 §9 and §11 and 11 §2.
Fix: Retarget the link to 11 §2 and 02 §11.

**C2-15 · Minor — history hygiene: `README.md` (l.55), `CHANGELOG.md` (l.5), archive**
Quote: "Earlier versions (v1 → v3.2.1) are preserved in" (the link goes to `docs\_archive\round-3-v3.2.1\` only); "(tag `ideation-v4`)".
Why: v1 and v2 live in `round-1-v1` and `round-2-v2`, v3–v3.2 only as tags. `git tag -l` has no `ideation-v4`. The v4 commit added `docs\_archive\round-3-v3.2.1\CHANGELOG-through-v3.2.1.md`, which opens with a stale v4 draft entry ("(~35 learning-centred moonshots)").
Fix: Name all three archive folders. Tag v4 or drop the claim.

**C2-16 · Minor — count and term slips**
Quote: "Three rules follow from the table:" (02:130, four bullets follow); `3 decisions, worth about €1,150 a month` (06:193, vs the EUR 215 letter at 06:200); "(measured / observed / reported / inferred)" (06:222) vs "**inferred** (the AI's reasoning) → **assumed**" (03:163); "a bank of 145+ is already collected" (07:139, bank says 145); "What it knows: three kinds of knowledge, one memory" then "And a fourth, quieter kind" (01:57); "the prediction is filed in the Ledger" (03:222, read as the Unexplained Spend Ledger); "carried forward unchanged except for this header and the framing noted below" (bank:7, rows were corrected).
Fix: Correct each in place.

**C2-17 · Minor — terms before definition**
Quote: "writes a Service Cost Profile with receipts" (README:13, Atlas, Cost Grammar, Moves, Terrarium undefined there); "Findings become Atlas entries, detectors and Moves" (01:52, defined at 01:61, glossary, 01:224); "The Brief offers three options" (01:191, defined at 01:218); the Time Machine (01:189, defined at 01:204).
Fix: Add one-line inline glosses at the first use.

**C2-18 · Minor — `AGENTS.md` rule 5**
Quote: "enforces rules 6–7 with pattern guards".
Why: The lint's own docstring says the bloat guard enforces rule 2. The purchase flow ("prepared by the AI … executed by the AI") is not in AGENTS.md at all (0 hits), so no rule or guard protects it, though your brief calls it standing.
Fix: Say "rules 2, 6, 7". Add the purchase rule to AGENTS.md.

**C2-19 · Minor — replacement anchor**
Quote: "moved the web tier to a second region" (01:188); "A web tier moved to a second region" (03:262); "the web tier of the booking app moved to a second region" (06:396).
Why: D-03 swapped the old anchors for one new story reused in three documents. A reader may see a new "fed example".
Fix: Keep it in 01 §5 only. Use other mechanisms in 03 and 06.

## Task 1 table: disposition rows not fully true

| Row (disposition.md line) | Disposition says | Actually there |
|---|---|---|
| Header (4) | "Everything was accepted, one item partly." | Five ◐ rows (23, 37, 51, 69, 77) and two 🔧 (15, 54). |
| Header (5) | "52 of 55 reviewer quotes exist verbatim" | Raw spot-checks give 8/8, 10/12, 14/14, 24/25 = 56 of 59 (raw-a:113, raw-b:161, raw-c:95, raw-d:111). |
| A-03 / C-02 (17, 47) | `"Prove" removed.` | `LabProven` (04:262), "its proof *stops*" (05:101). |
| A-08 (22) | "Forger and rehearsal estate promoted from moonshots to the core" | Forger still in 01 §12 (l.306). Cast of 13 excludes it. Three overlapping life cycles (02 §4, 04 §13, 07 §2) rather than one. |
| B-01 (29) | "The firewall per-GB meter (found only on Q&A) is not claimed." | Learn "Choose the right Azure Firewall SKU" (fetched): "a variable data processing charge billed per gigabyte of traffic processed". Bank NET-003 (bank:110) keeps it as Verified and "Delete dev/test firewalls". NAT "no stopped state" (02:99) is a negative claim (UNVERIFIED; bank ORPH-004 "inconclusive"). |
| B-02 (30) | "Reworded: granularity differs by meter" | 08:12 still has anything short-lived pays a minimum. |
| Claims to hedge (40) | "Watch clock runs on fast signals because the bill lags" | `four-clocks.svg` unchanged (embedded at 01:105). 12:12 "within hours" unhedged. |
| Contradictions (53) | "the expert seed is explicit and measured against" | 01:17 "So we do not write the advice." remains in "In one minute". |
| A-02 / Five-minute kill (16, 54, 83) | "no gate, no kill criterion, no register" | 10:38, see C2-01. |
| D-02 (61) | '"First/founding" language removed from 01' | 01:355 "### The founding exam". README:21, README:40 and 10:91 also carry it. |
| D-08 (67) | "replaced by a four-line pointer"; the "done when" gate "removed" | 01:335 is a six-link risk→answer paragraph under "The honest limits". 10:74 lists five success bullets. |
| D-09 (68) | "Old entries moved whole into the archive" | The archived copy starts with a stale v4 draft entry (C2-15). A file was added to the frozen archive. |
| D-13 (72) | "14 mechanisms in both tables" | 01:118 is prose. D-10 (l.69) says 01's grammar table was cut. |
| D-14 (73) | EUR 215 fix | 06:193 still `3 decisions, worth about €1,150 a month`. |
| D-15 (74) | "Kept inside the organisation" | 02:272, 12:39 (C2-03). |
| D-16 (75) | '"team agent" and "Atlas maintainer" replace the three meanings of "steward"' | "Technical steward" in 03:67 and 11:109, "Engineer / steward" in 06:67. |

## Raw-report items the disposition never mentions
- **B "Verified OK" nuance:** "(they add, not "multiply")". The docs still say "multiplying the stock silently" (02:62) and "multiplies its stock" (02:113).
- **B "Unverified" list:** "preview labels on the optimizer and memory; Databricks default auto-termination; Firewall/NAT per-GB meters in product docs; metric-definition completeness."
  - Bank:182 still says "Auto-termination is an opt-in setting on each cluster, not a workspace-wide default" as Verified. It is #2 in the "ten verified traps" list. The Learn WAF page recommends enforcing auto-termination but does not say it is opt-in (UNVERIFIED sub-claim).
  - 02:124 still says "every metric each resource type emits".
- **B gap 5:** "A spending limit doesn't prevent all charges" appears nowhere in the docs.
- **C-06 fix part:** "who bears responsibility for a materially harmful published claim". C-02 "stop rules" are covered only by 04:234.
- **D §1 lint notes:** "CHANGELOG and AGENTS are exempt", the missing "open questions" bloat pattern, "scan docs/**". All still true (below).
- **D §6:** the `living-system.svg` "ring" and `four-clocks.svg` "no coupling drawn" remarks, and "02 day-zero is borderline (69%)".
- **D §3 "still unclear":** how "analyse actual consumption" works beyond one-liners. How the Lab gets services needing quota or private preview was fixed at 02:306 but is not recorded.
- **D-16 sub-point:** Detectors originate from "confirmed findings (04 §13) or Pattern lessons (07 §2)". Still four origins (C2-09).

## Lint-defeat list (`tools\check-docs.py`, tested in memory only)
1. **Unscanned files (rules 2, 6).**
   - `check_guards` skips AGENTS.md, CHANGELOG.md, `docs\reviews\README.md`, the disposition and all new sub-folders (16 of 20 live files are guarded).
   - A new `docs\governance\decision-register.md` with one H1 passes: not guarded, not orphan-checked.
   - The disposition's own "no gate, no kill criterion" would fail the bloat pattern `kill criteri` if scanned.
   - SVG text is never scanned.
2. **Paraphrase and wrapping (rule 6).** These passed the anchoring patterns:
   - "produced and billed all day and no one has ever opened it"
   - "never reads"
   - "virtual hub … raised years ago"
   - "user VPN gateway scale units"
   - "Azure Monitor Logs … not queried by anyone"

   Matching is per line, so hard-wrapping "scaled up / long ago" evades even the exact pattern. 07 and the exam bank are allow-listed wholesale, so 07 §1–§7 could host the findings.
3. **Bloat vocabulary (rule 2).** These all pass: "Open questions for the operator", "Go / no-go gate", "Stop conditions … abandon the idea", "Risk log", "Decision log", "Threat model", "Assumptions we are making". Live example: 10:38.
4. **Pipeline detector (rule 7).**
   - `A -- go --> B` syntax: a 10-node chain reads as longest path 1 and passes.
   - A chain plus a decorative node with four dotted links passes.
   - A 7-chain with 3 leaves (73%) passes.
   - Chains of four or fewer nodes pass.
   - `stateDiagram` blocks and ASCII or SVG pictures are never tested for linearity.
5. **Mermaid syntax.** Semicolons in state labels pass (C2-06).
6. **Link checker.** `[x][ref]`, `<a href=…>`, `<autolinks>` are ignored, and `a_(b).md` is parsed as `a_(b`. A broken link in these forms passes.
7. **Rule 4 (history).** `docs\_archive\**` and `raw-*.md` are exempt from every check, so edits to them pass. The v4 commit itself added a file to the archive.
8. **Wording and rule 1.** Nothing guards "prove", "verified" without scope, "within hours", the purchase flow (not in AGENTS.md) or "published at …" claims.

**UNVERIFIED:** the Mermaid render (C2-06); the NAT "no stopped state" negative; the D-17 brief quote, which is only in the session record. I fetched Learn (SRE Agent billing, reservation-exchange policy, Firewall, NAT), arXiv and `gh repo view` with GET only. The SRE Agent figures match Learn, as does the exchange policy as 05:7 states it. No repo file was changed. The fetch tool saved two outputs under `%LOCALAPPDATA%\Temp`, outside the repo.

---

## Orchestrator spot-checks (2026-10-31)

- **Quotes:** every quoted passage checked exists verbatim at the cited line — C2-01, 02, 03, 04, 05, 06, 07, 08, 09, 10 (all quotes), 13, 15, 16 (`Three rules follow…`, `3 decisions…`, `measured / observed…`, `bank of 145+`, `And a fourth…`, `filed in the Ledger`, `carried forward unchanged…`), 18 and 19. The disposition-table rows the orchestrator re-opened (the Header, A-03/C-02, A-08, B-02, Contradictions, D-14, D-15, D-16 rows) are as described.
- **Mermaid (C2-06):** confirmed against the grammar. `packages/mermaid/src/diagrams/state/parser/stateDiagram.jison` line 160 defines the transition description token as `<INITIAL,struct>\s*":"(?:[^:\n;]|":"[^:\n;])+` — it cannot contain `;`. Treated as a real defect (not just "likely").
- **Quote tally (header row):** the round-1 raw reports record 8 of 8 (A), 14 of 14 (C), 24 of 25 (D) and 10 of 12 (B); the disposition's "52 of 55" was wrong (three misses was right; the totals were not). Corrected to 56 of 59.
- **Round-1 ◐ markers:** five ◐ rows and two 🔧 rows are present, so "one item partly" was wrong. Corrected.
- **Archive:** `docs\_archive` holds `round-1-v1`, `round-2-v2` and `round-3-v3.2.1`; `git tag -l` has `ideation-v1 … ideation-v3.2.1` and no `ideation-v4` yet (it will exist when this version is tagged). The archived changelog opens with an abandoned v4 draft written before the rebuild; the archive is left as found.
- **Lint-defeat list:** the orchestrator read `tools\check-docs.py` and agrees with items 1, 3, 4 and 5 (they are real gaps); item 2 (paraphrases) is inherent to a pattern guard and is stated as such in AGENTS rule 5; items 6 and 7 are accepted as known limits. The fixes taken are listed in the disposition.
