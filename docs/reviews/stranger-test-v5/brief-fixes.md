# Ideation v5: fixes brief (global decisions)

You own the file(s) named in your message and may edit no other. Cold-reader reviewers (the "stranger test") read the documents and reported findings, in `<repo>\docs\reviews\stranger-test-v5\raw-*.md`. Your message names the reports and the findings that concern your file. Read the findings, decide for each: **fix**, **reject** (say why) or **partly**. The reviewers may be wrong: before you change a statement about a Microsoft product, read the vendor's page (learn.microsoft.com) yourself.

`docs\01-north-star.md` was just rewritten and already applies every decision below. Read it first; your file must agree with it.

## Global decisions (apply to your whole file)

**D1. Agreement, not contract.** A customer's commercial arrangement is an **agreement** (Enterprise Agreement, Microsoft Customer Agreement, sold through a partner (CSP), pay-as-you-go). Never call it a "contract". Rename "every contract, every level of access" to "every agreement, every level of access". The north star section is now `01-north-star.md#5-every-agreement-every-level-of-access`. The word "contract" survives only in the document title "the learning contract" and in "contracted rates" (the contracted price). The partner list everywhere is: EA · MCA bought directly · sold through a partner (CSP) · pay-as-you-go.

**D2. Fact grades are not evidence levels.** The four **evidence levels** (documented → price-confirmed → bill-observed → outcome-confirmed) describe a *claim*. Any other scale (for example how a fact inside a Case was obtained: measured, observed, reported, inferred, assumed) must not be called evidence levels: call it "how the fact was obtained" and add one line saying that Atlas claims use the four levels.

**D3. Without a bill, a figure is a scenario.** Where the system cannot read the bill (no cost access), a figure is a labelled **scenario priced at list prices**; the Recommendation may still be made, and says what the figure rests on. A figure is called an expected *saving* only when a bill line confirms the meter (bill-observed for that estate). Make every document agree (gates, Recommendation card, no-cost-access reach).

**D4. Trial is not free.** Five routes (Ask, Look, Replay, Follow, Pool) cost AI and attention and nothing in Azure. **Trial** is different: one small reversible change to something an owner already runs; the owner approves after seeing a cost ceiling; it can move the bill; automatic rollback. Never write that learning "costs no Azure resources" or "spends no Azure resources". The correct statement: "learning never provisions anything just to measure it".

**D5. The route formerly called Watch is now Follow.** Routes: **Ask, Look, Replay, Follow, Pool, Trial**. (The *Watch clock* and the Watch workflow keep their name.) Replace the route everywhere in your file; keep sentences natural ("follow the outcome of changes people were making anyway").

**D6. Ledger.** **Ledger** = the system's record of predictions, decisions and measured outcomes. The list of bill lines the system cannot yet explain is now the **Unexplained Spend list** (not "Unexplained Spend Ledger"). Never use bare "ledger" for the second.

**D7. The Atlas is public.** `documented` and `price-confirmed` live in the open Atlas (price-confirmed means confirmed against *published* price lists). A customer's own price sheet, `bill-observed` and `outcome-confirmed` live in that estate and never enter the Atlas. **Pool**: only a scope and an aggregate leave an estate, privacy-reviewed, published only when several organisations contribute the same observation; never a bill line, name or identifier. Remove absolutes such as "never a byte of customer data" unless the mechanism is stated beside them.

**D8. Label invented examples.** Any example with named people, invented figures or a made-up service says "(an invented example)" in its heading or first line. Prefer roles over personal names.

**D9. No what-if in the ideation.** Do not name Azure's what-if preview as the safety check for Actions. Say: "check against synthetic data and, where the platform offers one, a change preview".

**D10. Sealed versus published cases.** The Commons shares regression cases; the sealed evaluation cases and their answers are never shared with the system under test.

**D11. Probe cadence.** The capability profile is probed at onboarding, weekly, and at once after a refusal (a 401 or 403). Never write that a new role is "noticed tomorrow".

**D12. "Verified" needs a subject.** The cost-trap bank's status `Verified` means *source-verified*: the claim was found on the cited Microsoft page; no bill has confirmed it (evidence level documented). Never write "verified" about those rows without saying so; never call them bill-confirmed.

**D13. No residue.** Delete sentences that answer an objection nobody made or defend a choice against an unnamed critic: "not a rulebook / chatbot / dashboard" (one positive statement in the north star and README is enough), "there is no first", "the other road", "by design" defences, "no customer-specific model training is needed", "unlike earlier versions", slogans that add no information ("the scientific method is not a metaphor"). Replace with the mechanism or delete.

**D14. Unbuilt.** Nothing is built. Describe the idea in the present tense if you like, but never write or imply measured results, "we found", "tested on", or "would be a first". Figures in examples are invented and labelled (D8).

**D15. Hedges and slogans.** Replace vague claims ("almost no cost", "thousands of accidental experiments a month") with a mechanism, a range tied to a stated assumption, or delete.

**D16. Links.** Link to other documents by file name only (no `#anchor`) unless you have checked the anchor exists in the target now. Do not link into design documents except by file (`design/14-agreements-and-access.md`, `design/06-security-and-governance.md`, `design/README.md`).

## Rules

- Use only the `edit` tool for changes (no scripts that rewrite files, no `create` on an existing file). Many small edits are fine.
- Keep your file about as long as it is now (within about 3 %): when you add, cut something weaker.
- Plain writing for strangers; no first person; no history ("earlier version", "we changed"); no conversation.
- Run `cd <repo> ; $env:PYTHONIOENCODING='utf-8'; python tools\check-docs.py --strict` and fix every message about your file. The lint bans: lab, Terrarium, wind tunnel, time machine, exam, Examiner, learner, Brief, Move (as a noun), "the brief", "project owner", "design-v", "judged on merit", "review round".
- Do not edit any other file. Do not post anywhere; the repository is private.

## Your final message

A table with one row per finding of yours: report and finding number, **fixed / rejected / partly**, one line on what you did or why you did not, and the Learn URL if you checked a fact. Then list anything you noticed in *another* document that contradicts the decisions above (file and line), without editing it.
