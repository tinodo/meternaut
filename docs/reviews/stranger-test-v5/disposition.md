# Stranger test: disposition

What the stranger test found, what was done about it, and what was not done and why. The test and its reports are described in the [review record](../README.md); the briefs the readers received are [brief-cold-reader.md](brief-cold-reader.md), [brief-closure.md](brief-closure.md) for the closure checks and [brief-final-read.md](brief-final-read.md) for the final readers; the decisions that the fixes followed are in [brief-fixes.md](brief-fixes.md).

## 1. The test in numbers

| | |
|---|---|
| Cold readers | 13, on 11 models; each had only its assigned files |
| Findings | 221 (38 blockers, 110 majors, 73 minors) |
| Closure checks | 6, on other models; every finding was checked against the fixed text |
| Findings closed after the fixes | 186 closed with a quoted sentence, 15 closed by deleting the passage, 5 not applied and judged right to leave, 15 closed only in part (all 15 were finished afterwards), 0 open |
| New contradictions the fixes introduced, found by the closure checks | 31, all fixed |
| Final cold readers (a second, fresh set on the front door and the new documents) | 3, who filed 33 findings, all fixed or answered |

| Closure check (model) | Covers | Findings checked | Closed | Closed by deletion | Not applied, right | In part | Open | New defects |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| [closure 1](closure-1.md) (claude-sonnet-5.5) | design A, B, C | 50 | 41 | 6 | 1 | 2 | 0 | 8 |
| [closure 2](closure-2.md) (gpt-6.1-terra) | design D, E, F | 43 | 30 | 2 | 2 | 9 | 0 | 8 |
| [closure 3](closure-3.md) (gpt-6-sol) | idea A, B | 32 | 27 | 2 | 2 | 1 | 0 | 5 |
| [closure 4](closure-4.md) (grok-4.7) | idea C, novice | 28 | 24 | 1 | 0 | 3 | 0 | 3 |
| [closure 5](closure-5.md) (gpt-5.6-sol) | idea D, E | 30 | 28 | 2 | 0 | 0 | 0 | 4 |
| [closure 6](closure-6.md) (gpt-6.1-sol) | idea F (research) | 38 | 36 | 2 | 0 | 0 | 0 | 3 |

The closure reports are the finding-by-finding disposition: each row quotes the sentence that closes the finding, or says what was missing.

## 2. What changed because of the test

1. **The idea no longer carries the argument of an idea that was dropped.** The vocabulary of purpose-built test environments is gone from every document and from the pictures; [finding out without spending](../../04-finding-out-without-spending.md) says how the AI finds out instead (six routes, ordered by cost, with what each leaves unproven). The linter refuses the retired words.
2. **Agreements and access are part of the idea and the design.** One list everywhere (Enterprise Agreement, Microsoft Customer Agreement bought directly, sold through a partner, pay-as-you-go), "agreement" and never "contract", the capability probe (at onboarding, weekly and at once after a refusal), the data path, price source and purchase path per agreement, and the cases the facts on Microsoft Learn force: a pay-as-you-go account has no billing scope in Cost Management, a partner-sold subscription shows retail rates and zero cost for reservation usage, an Enterprise Agreement bought through a partner can show `IndirectCostDisabled`, a customer can buy a reservation under a partner agreement once the partner permits it.
3. **Evidence levels mean one thing.** Four levels (documented, price-confirmed, bill-observed, outcome-confirmed) describe a claim; a figure without a readable bill is a labelled scenario at list prices, an expected saving once a bill confirms the meter and a verified saving once the Auditor has measured it; the cost-trap bank's Verified rows are *source-verified*, never bill-confirmed.
4. **Nothing is promised without its mechanism.** What may leave an estate (a privacy-reviewed scope and aggregate, from several organisations, with receipts defined), consent before a meeting is captured, a trial can move the bill and shows a cost ceiling first, sealed cases are hidden while sealed, the first five routes change nothing in Azure but still cost model tokens.
5. **Examples are labelled invented and nothing is claimed as measured.** The learning is described in the intended tense, and the report-card figures, the press release and every named person are marked as invented.
6. **Contradictions were removed.** One name per thing: the six routes (Ask, Look, Replay, Follow, Pool, Trial), the autonomy ladder, the Unexplained Spend list against the Ledger, the Contract of the hub against an agreement, one definition of a credential.
7. **Facts were re-read on Microsoft Learn.** The cost-trap bank was re-read row by row (the status counts are now checked by the linter against the bank), Advisor's own limits are quoted from its page, the model-retirement call is named exactly, the partner purchase paths and the retail-rate caveat were corrected.

## 3. Findings not applied as written

| Report · finding | The finding | Decision and reason |
|---|---|---|
| design A · 1 (blocker) | Hosted agents need a container registry | **Not applied.** Learn's page on deploying a hosted agent from code describes deployment from a source zip, without building or pushing an image. The text now says so in one clause; the container route stays optional. |
| design B · 9 | Drop the sentence that ten hosted agents would cost more and isolate no more | **Kept.** It answers the question "why five, not ten?" and now follows the positive rule. |
| design D · 7 | Five apps but a different number of identities | **Kept.** One app can hold several identities; the design says which. |
| design F · 4 | Rename Credential | **Kept.** The design glossary defines it and separates it from keys and secrets. |
| idea A · 15 | "The product is built on Microsoft's platforms" needs a source | **Kept.** It is the project's premise, not a claim about a product. |
| idea A · 17 | The day-zero story appears twice | **Kept.** A short version in the north star, the worked step-by-step version in the studying document, both marked invented. |
| idea A · 16 | Day-one owner questions | **Fixed where the sentence was** (the north star), not in the studying document that the reviewer's line number pointed at. |
| idea E · 4 | Call the bank's Verified rows "confirmed" | **Not used.** It would blur the four evidence levels; they are "source-verified". |
| novice · 13 | Rename the hub's "Contract" | **Kept and glossed.** It is Citadel's own term, and the glossary says it has nothing to do with an Azure agreement. |
| idea D · 5 | Live per-person translation | **In part.** The aspiration stays, stated as an experience: one agreed spoken language, a translated text view for each participant, disputed wording confirmed in writing. |
| idea C · 4 | A per-action and a Finance ledger | **In part.** They are views of the one Ledger, which the recommendation document now says. |
| final 1 · 1 (blocker) | Disable the approval path through which a compromised bot could approve a small reversible change | **Not applied.** The design says what a compromised bot could still approve and bounds it; the finding asks for a design change, not a correction. |
| final 2 · 8 | Rename Credential and Contract | **Kept**, as above. |
| final 3 · 4 | Advisor's limits are not on the page cited | **Not applied.** The reviewer read a different page; Advisor's cost-recommendations page lists both limits (retail rates; reservations and savings plans not considered). The link was added at the sentence. |
| final 2 · 1 (blocker) | A pay-as-you-go account has a billing account | **In part.** Both statements hold on Learn: the Billing blade shows an account, and Cost Management has no billing-account scope for these subscriptions. The text says both. |

## 4. Reviewer claims that were checked on Microsoft Learn

| Claim | Result |
|---|---|
| Hosted agents need a container registry (design A) | Wrong: deployment from a source zip is documented. |
| Advisor ships hand-written recommendations (idea E, about a sentence in the press release) | The reviewer was right and the sentence was wrong: Advisor's resize and shutdown recommendations use machine learning. Rewritten from the page. |
| Voice and text cannot use Teams (idea D, about a sentence in the people document) | The reviewer was right: Teams has calling and, in some countries, text. The sentence is gone and the idea is stated without a technology. |
| The partner's customer cannot buy a reservation (closure 2) | The reviewer was right: the customer can buy once the partner permits it. The two Learn pages name different roles, and the design says so. |
| Models can be listed with their lifecycle dates (closure 2) | Confirmed: the Models List operation returns `lifecycleStatus`, `deprecation.inference` and a date per SKU. |
| A hosted Infracost server is a commercial service; a text-to-SQL paper reports 44.5 % fewer bytes (idea F) | Both confirmed. |
| Fourteen changed bank rows (closure 6) | Twelve supported by the cited pages; two were not fully supported (backup soft delete, blob versioning with smart tier) and were corrected. |

## 5. What remains open

- Nothing is built. The proof points in the design's README are measurements that nobody has taken; the cost figures are model outputs.
- Residual risks are stated where they arise (for example what a compromised bot could still approve in the design's security document) rather than removed.
- Two readers asked for a mechanism the idea level does not give (the minimum number of organisations before an observation is published, who runs the privacy review). The ideation says a minimum cohort that the maintainers set and a review by someone other than the contributor; the numbers belong in the design phase of the Commons.
