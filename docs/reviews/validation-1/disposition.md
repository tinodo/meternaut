# Disposition: independent validation of the design

An independent AI reviewer read the design (two reports, kept as received in [raw-validation-1](raw-validation-1.md)) and filed 26 findings, counting the closing recommendations. The reviewer said plainly that it was not the last word, so each finding was checked against the files before anything was changed.

**How it was checked.** Every quoted line and line number was located in the repository at commit `ad958b9`. The reviewer's snapshot predates that commit by about 45 minutes, so one finding was already fixed. Two statements misread the text (see B4 and B16). The reviewer's own facts about Azure were not needed: the one it checked on Learn (partner retail rates) matches [agreements and access](../../design/14-agreements-and-access.md). Cited files and tools were run, not just read: the cost model's self-test and its `--check` pass after the change.

| Verdict | Count | Findings |
|---|---|---|
| Confirmed: a defect, fixed | 10 | A3, A4, A5, B1, B2, B4, B5, B8, B10, B18 |
| Partly: the structure held, a gap was real and fixed | 6 | A1, A2, A6, B3, B12, B15 |
| Already covered, or stale | 5 | B6, B7, B9, B16, B17 |
| Not adopted | 2 | B11, B13 |
| Agreed: judgement or direction, reflected in the changes above | 3 | B14, B19, B20 |

## Report A: knowledge and learning, testing and evaluation

| # | Finding | Checked against the files | Verdict and change |
|---|---|---|---|
| A1 | A "small trial" is R1 by label, although scaling a production service down can hurt before a rollback | R1 is defined in security as *reversible, small, non-production*, so the production example is not R1. But the knowledge document said only "small and reversible", used an example that reads like production, and said nothing about guard latency or credentials | **Partly.** A trial is offered only where the change is R1 and the guard metric reports faster than the change could do harm; anything that would be R2 or R3 is not a trial; the example is a development resource; credentials never cover trials |
| A2 | `bill-observed` can mistake a fitted model for a correct explanation | The evidence table already requires a closed period, the profile's stated error bound and a blueprint stored before the bill lands (so every period is out-of-time); claims carry a scale range. Real gap: "trailing billed usage" makes the bill check itself | **Partly.** A meter whose quantity came from trailing billed usage cannot earn `bill-observed`; the usage must be measured, never taken from the bill; the paragraph names error bound, stored-before and scale range |
| A3 | Causality is acknowledged but not operational | Predictions, control meters and confounders are registered beforehand and outcomes normalised for load; no rule says when a look-alike is a valid control, what a coinciding discount does, or what an unusable outcome is | **Confirmed.** New paragraph: outcomes are settled in quantity at constant prices; a control must share service, SKU family, purpose and earlier load; otherwise the outcome is *undetermined*, shown as such and counted as unscored; it never counts as a hit, never narrows a range and may only widen one |
| A4 | One Case becomes an estate-wide Detector without a promotion threshold | Back-test, shadow and blind samples exist; no numbers or local-only rule | **Confirmed.** Promotion is judged against numbers written beforehand (scopes with different owners, a shadow precision floor, a decoy ceiling); the Detector shadows every scope and one that holds in a single scope becomes active there only |
| A5 | Cold start has no product behaviour or success criterion | Rhythm needs a full cycle and the Case says "not enough history"; no thresholds | **Confirmed.** New row in the limits table: no expected saving until thresholds written at onboarding are met (history, explained share, missing-data share); until then a labelled scenario |
| A6 | Evaluation shows memory improvement on known traps, not prospective discovery; "learning" could be better retrieval | The learning test freezes memory and changes nothing else: same models, tools, prompts, pinned sources, later-in-time sealed cases, margin and minimum number of services fixed beforehand, a leakage audit, and retrieval-only, Advisor-only and expert-Detector baselines. Base-model knowledge is in both arms and cancels; a better retrieval method is not an arm difference. Two gaps: nobody audited the gains, and P6's launch was only replayed | **Partly.** Added a gain audit (a person who did not build the arms follows each gain's source chain) and, when a real launch falls after the snapshot, predictions recorded before its first invoice. Not adopted: the reviewer's full prospective protocol as a gate for every release (cost); it applies when a real launch occurs |

## Report B: the rest of the design and the tools

| # | Finding | Checked against the files | Verdict and change |
|---|---|---|---|
| B1 | The first real-value test has no profile: phase 1 needs a real estate and a digest, but the Evaluate profile has no production roles and Operate, the Diplomat and e-mail arrive in phase 2; the phase 1 exit is a research protocol | All true as quoted. Replays also run in the Operate profile | **Confirmed.** Phase 1 is split. 1a "first value on one estate": Operate profile with read roles only, the prod contracts, the Diplomat's Monday digest by e-mail, the FinOps lead confirms findings. 1b "show that it learns": P5, P6, P10 and the baselines. Phase 2 is the owner channels. 1b may overlap 2; 3 waits for 1b |
| B2 | A failed P6 falls back to "more Detectors", which is the rule-book outcome the roadmap says it avoids | The fallback read "Narrower scope; more Detectors; better prompts" | **Confirmed.** P6 is named the exception; failing it withdraws the learning claim and reopens the goals |
| B3 | A large component stack stands before first value; no thin slice or time to first value | The counts match the documents (five agents, eleven private endpoints, six contracts in two environments). Not everything is on the critical path: phase 1 has no approval service, runner, bot or purchase identity. The missing slice and metric are real | **Partly.** 1a is the slice; a hosted agent, its contract and tools ship in the phase that first needs them; time to value is a measure |
| B4 | Onboarding and operating effort are not modelled; no goal for them | The cost model counts owner minutes and Atlas-review minutes only; the goals table has no effort row. The reviewer reads "five out-of-hours pagers": the design says five alert types page out of hours, on a rota the organisation sets | **Confirmed.** New goal "Be adoptable" and a report-card measure (platform, FinOps and security hours; days to the first confirmed finding); the cost document says that time is not modelled and can exceed the Pilot cloud bill. Not adopted: hour estimates, because nothing could seed them; the report card measures them |
| B5 | The Pilot break-even covers cloud cost only | True | **Confirmed.** The generated headline and row say "on its cloud cost alone"; the text says people's time comes on top |
| B6 | Meaning of prices under subscription-only access and partner retail rates; reconciliation proves the lake matches the bill, not that the bill is right | Both are stated in the documents (14 section 8; data and integrations) | **Already covered.** No change |
| B7 | The Strategy workflow needs reservation data that requires tenant-level roles | Stated in data and integrations; the capability profile records "commitments visible" | **Already covered**, one clause added: phase 4 names the flag |
| B8 | F11 says "every Azure agreement"; document 14 excludes classic CSP and sponsorship | True | **Confirmed.** F11 states the exception: where Cost Management has no data, the path is reading resources |
| B9 | The probe shows what the identity can do, not what the agreement allows | Stated in document 14 section 8 | **Already covered.** No change |
| B10 | The cost model has no funnel: investigations that die or park are not priced | Right: only cases that reach an owner were priced; the only stress was "investigations twice as long" | **Confirmed.** `tools/cost-model.py` adds a seed of one dead-end investigation per case (Detective and Skeptic in full, half the hosted time and tool work), a line in the monthly table and a sensitivity of three. Totals moved: Pilot 311 to 332, Team 795 to 1,002, Enterprise 4,760 to 6,831 EUR a month. P10 now measures dead ends |
| B11 | Break-even is a free parameter divided by a cost total and says nothing about yield | It is a threshold to beat, not a forecast, and the cost document already says most of the spend cannot be saved and that the system is judged on verified net savings | **Not adopted.** A yield threshold would need a yield nobody has measured. Wording only: "a threshold to beat, not a forecast" |
| B12 | The register says Terra is the default and Sol escalates; the headline prices Sol throughout | Both true; the headline is the declared high estimate and the Terra sensitivity is shown | **Partly.** The register notes that the cost model prices Sol throughout |
| B13 | Four fixed amounts are manual estimates; the PII price is UNVERIFIED | Disclosed with sources in the meters appendix and marked in the cost document | **Not adopted.** Nothing is hidden |
| B14 | Cloud cost is not the project risk; yield, attrition and hours are | A judgement | **Agreed.** Reflected in B4, B5 and B10 |
| B15 | The next demonstration should be one vertical slice at one reference access level, preferably EA or MCA with a billing reader | The slice is right; the reference level is not: the first estate is the adopter's own, and P4 already requires the probes to agree with the portal for every agreement type and level of access the pilot estates cover | **Partly.** 1a is the slice; no reference level is fixed |
| B16 | The P6 gold counts disagree: 79 in testing and evaluation, 78 in the bank | Already fixed in `ad958b9`: 83 Verified in the bank, document 08 and the ideation, and a lint check keeps them equal | **Stale.** No change |
| B17 | P6 measures rediscovery of documented mechanisms, not proven savings | Stated: Verified means source-verified, never bill-confirmed | **Already covered.** No change |
| B18 | First verified savings come only after the whole action stack; measure earlier | Phase 3 was the first place the Auditor settled anything | **Confirmed.** Phase 2 adds the Auditor settling changes owners make themselves, with "first owner-made saving verified in the bill" as an exit |
| B19 | What can wait, and what must not be given up | Matches the phase order; "begin with two or three contracts" is the same idea as shipping a contract with the phase that needs it | **Agreed.** Nothing to give up was touched |
| B20 | Keep direction; adjust four things | | **Agreed.** Phase 1a and the read profile (B1); the P6 rule (B2); goals and measures (B4); cost-model honesty (B5, B8, B10, B12). Break-even is kept (B11) |

## Closure check

Two further agents checked the fixes before release: one for contradictions across the design and the ideation, one for the cost-model change (it re-ran the model, rebuilt the new line by hand and mutation-tested the self-test). They found 18 points between them; a second pass over the fixes found eight more.

| Source | Finding | Done |
|---|---|---|
| Design | Undetermined outcomes "never move a range" (the first wording) contradicted "widens the range where no good comparison exists" | Fixed: an undetermined outcome never counts as a hit and never narrows a range; it may only widen one. A valid comparison is cost per unit of work or a look-alike |
| Design | The R1 table said a credential may cover R1; the limits table offered a trial unconditionally; the ideation defined a trial as any small change | Fixed: R1 cell "never a trial"; "where one qualifies"; the ideation documents and the decisions record say non-production |
| Design | The cold-start thresholds were not set anywhere | Fixed: onboarding step 1 records them. Not adopted: a change to the expected-saving glossary (an extra gate does not contradict "only when a bill backs it") |
| Design | Onboarding steps 4 and 6 assumed phase 2 channels | Fixed: sender mailbox first, Teams from phase 2 |
| Design | The phase 1a exit put people's time in a hub-log figure | Fixed: hours are recorded beside the cost |
| Design | P6 let a replay pass as prospective | Fixed: a replayed launch is reported as a replay |
| Design | The north star said a Detector watches "everywhere" | Fixed |
| Design | Several "phase 1" mentions were ambiguous | One sentence in the roadmap: "Phase 1" elsewhere means 1a and 1b together |
| Design | Precision floor and decoys were not defined where used | Fixed inline |
| Cost | The design index described the pilot as "mostly fixed" and the enterprise estate as "a few thousand" | Fixed: about half fixed; several thousand |
| Cost | "Merged" had no basis; "parked" was loose | Fixed: refuted, or parked before any message to an owner |
| Cost | The weekly shadow sample of unflagged resources is unpriced | Stated in "What the numbers leave out" |
| Cost | The added self-test assertions caught none of eleven seeded defects | Replaced by assertions that catch nine of them |
| Cost | "The largest fixed line is the search service" is false at Pilot size (private endpoints cost more) | Fixed |
| Cost | The seed's 50 % share was under-described | Fixed: orchestration steps, Cosmos request units and Content Safety records are named; logs, network, storage and Key Vault are scenario inputs |
| Cost | The "half stay on `triage`" sensitivity now includes dead-end Detective calls | Not adopted: those calls precede the Skeptic's objection that escalates them, so the sensitivity covers them |
| Cost | "Case" meant two things; P10's denominators were not all emitted | Partly: the line is "Cases that reach an owner: the agents' tokens" and the cost document says what a case and a dead end are. Not adopted: a per-investigation row |
| Cost | Durable state, sampled scoring and a Lesson call for dead ends were not scaled | Durable state switched to the dead-end work; the others are below 1 % of any total and left alone |

A second pass by the first reviewer, on the fixes, found these:

| Source | Finding | Done |
|---|---|---|
| Design | The "polite scream test" in the ideation let a trial run if what cannot be undone was merely stated | Fixed: anything that cannot be undone is never tried |
| Design | P6 asked for a prediction before the invoice but not for the snapshot's hash that the evaluation requires | Fixed |
| Design | A Detector that runs elsewhere only after passing a test that counts scopes it fired in is circular | Fixed: it shadows every scope and becomes active only where it passes; one that holds in a single scope becomes active there only |
| Design | The phase 2 row listed Lessons, but a surviving Case already ends as a Lesson in observe mode | Fixed: phase 2 says "Lessons taught by owners". The onboarding step that says a first Case "reaches Lesson" stays, because it is the observe-mode behaviour |
| Design | The north star's Detector label does not repeat the promotion conditions | Not adopted: a label need not carry the design's thresholds |
| Cost | The weekly shadow sample should be priced, not left out | Not adopted for now: its size is not set in the design; it is stated in "What the numbers leave out" and each sample costs about as much as a dead end. It is priced when P10 fixes the size |
| Cost | The "twice as long" sensitivity doubles tokens but not hosted time | Not adopted as a change to the model (it was always tokens only); the row now says so |
| Release notes | The changelog said "never moves a range" and the old Enterprise total | Fixed: "never narrows a range, may only widen one"; €6,831 |

## Numbers

The design size limit moved from 48,000 to 49,000 words ([why](../../../CHANGELOG.md)). The design grew by about 1,000 words: the roadmap (200), knowledge and learning (340), the cost document (240), testing and evaluation (100), goals (50), delivery (30).
