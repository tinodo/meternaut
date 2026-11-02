# Design v5: disposition

Two reviewers on different model families read the technical design after the experience design's 29 asks had been written into it ([brief.md](brief.md), [writer-sheet.md](writer-sheet.md)): A on landing, contradictions and the repository's rules (gpt-6.1-sol, [raw-a-landing.md](raw-a-landing.md)), B as adversary on security, cost and Microsoft facts (grok-4.7, [raw-b-adversary.md](raw-b-adversary.md)). A found 23 of the 29 asks landed, 1 partly, 5 contradicted by an older passage, and 11 Majors; B found 2 Blockers and 5 Majors. Both said not to release as it stood. Every finding below was checked against the files, and every claim about a Microsoft product was read again on Microsoft Learn on 2026-11-02, before anything changed.

## Reviewer A

| # | Finding | Verdict | What was done |
|---|---|---|---|
| A1 | A blanket "a verb is refused when answered or paused" also covers Undo, disowning an approval and help (05 §7) | Accepted | The three that stay open are named in 05 §7, in experience 04 and in the card manifest's contract |
| A2 | The rollback grant has no holder for a Credential run and no default window (05 §7) | Accepted | Holder: the approver, or each owner of record for a change under a Credential; the window is a starting value of 24 hours per recipe; the use is its own item in `consumption` |
| A3 | The fork rewrite dropped the ruleset conditions that make a human merge a review gate (05, 09) | Accepted | One paragraph in 09 §1 lists them (a code owner other than the last pusher, stale approvals dismissed, no App on a bypass list, the review check only from its App, `pull_request` and never `pull_request_target` on forks); the `pr-draft` row points at it |
| A4 | The notification policy counted the weekly desk and safety notices, which the experience exempts (05 §6) | Accepted | The counted and the exempt messages are listed |
| A5 | "An approval record is never changed" contradicts decisions and revocations written to the same record (05 §1, §7) | Accepted | The bound fields never change; only decisions, status and revocation are added, by the Approval service alone under an etag check |
| A6 | Three older passages still say a card may carry only the opaque id (05 §7, 06 §5, 08 §7) | Accepted | All three say what the card manifest lists for the verb; embedding a plan or an undeclared field is what the test rejects |
| A7 | No technical rule sends the approval-waiting e-mail the experience requires for purchases (05 §6) | Accepted | Every purchase request, and any one-person page request where the client matrix shows an embedded view, also goes by e-mail with the same request id, code and expiry |
| A8 | Reconciliation compared the bill with the invoice raw although Cost Management leaves out support, credits and taxes (05 §2) | Accepted | The excluded charges are accounted for first; an explained difference is kept and shown |
| A9 | Requirement F5 still said every message offers three buttons (01) | Accepted | F5 states the narrowed rule |
| A10 | The roadmap places approver readiness in phase 4 although R2 starts in phase 3, and the notification policy and first contact in phase 2 although the first digest is sent in 1a (13) | Accepted | Readiness is split (R2 in phase 3, R3 in phase 4); phase 1a has a fixed-settings policy for one allow-listed reader introduced by an agreed message |
| A11 | The Monday digest sample in 04 uses internal words (Lessons, Detector) as screen text | Accepted | The sample uses the words people see |

## Reviewer B

| # | Finding | Verdict | What was done |
|---|---|---|---|
| B1 (Blocker) | A card tap can name a delegate, who then decides R1 and R2 after the stolen session is gone (05 §8) | Accepted | A delegate is named only on the Settings page after the R2 sign-in, and the person is sent a notice; a mute or a pause may still be set on a card; section 12 admits what a compromised bot can and cannot do |
| B2 (Blocker) | Undo of an R2 change is a card tap with no step-up; the holder for a Credential run is unnamed; one consumption id cannot mark both the run and its undo (05 §7) | Accepted in part | The holder is named and the grant has its own consumption item (as A2). **Not adopted:** moving R2 Undo to the page. Undo restores the approved earlier state once, inside a short window, and is the person's quickest way to repair a regret; the residual risk (a stolen Teams session can undo a recent change) is stated in 05 §7, 06 §5 and 06 §12 |
| B3 | A page submit is authorised by scope, not by the designated approver; a forwarded link could decide (05 §6) | Accepted | The page refuses a decision unless the token's object id is the designated approver or a named delegate and carries the class's authentication-context claim |
| B4 | The two-person rule for resuming purchases is code in an app that can write `switches` (06 §5) | Accepted in part | Admitted in 06 §12 and 05 §8: the Approval service identity can release any switch alone and is the trust anchor. **Not adopted:** a structural split of the purchase switch, which would need a second identity for each role |
| B5 | Fork-based proposals: a stolen App key can post a passing check; fork workflows could use `pull_request_target` (05 §4) | Accepted | The `pr-draft` row says a stolen key cannot merge and why; 09 §1 forbids `pull_request_target` on forks and fixes the merge rules |
| B6 | The first-contact warning calls a consent screen fraud, but the tap path may show one (05 §6) | Accepted | An administrator consents to the delegated permissions for the organisation before first contact (05 §6, 09 §9 step 4), so any consent screen is a fake |
| B7 | A partner request is a "complete request" in a table and "scope identifiers only" in the paragraph; "outside the organisation" is false for an internal billing owner (14 §6, 05 §6, experience 05) | Accepted | One rule: stored quote (product, term, amount), scope identifiers and the deadline; no saving, evidence or other spend; any address off the list is refused whoever named it; the page shows the address, not a claim about where it is |
| B8 | The statement that Learn's pages disagree about whether a partner purchase shows is stale (14 §8) | Accepted | The Cost Management page says purchases show at pay-as-you-go rates when the cost visibility policy is on and reservation usage shows zero; the Partner Center page says nothing of the kind. The sentence now says that, and the Verifier still confirms the partner's price and discount with the partner |

Reviewer B's other checks: the new cost paragraph (10 §"What the numbers say") names existing lines and types no figure; `python tools\cost-model.py --check docs\design\10-cost-and-finops.md` passes; twenty Microsoft statements were right, one stale (B8). Reviewer B's rows for the send step, the AI marks and approver readiness: sound.

## Decided during integration, before the reviews

- **Approver readiness is a test sign-in**, not a read of registered methods: the registration report needs `AuditLog.Read.All`, which also reads sign-in and audit logs, so no app or pipeline holds it ([Learn](https://learn.microsoft.com/graph/api/authenticationmethodsroot-list-userregistrationdetails)); each approver signs in once on the approval page at the strength their class needs (06 §5, 09 §9).
- **A role is not delegable** (06 §5): a delegate decides R1 and R2 for the owner who named them, and fills a purchase seat only if they hold the approver role.
- **The kill switch page** is for the platform owner, the FinOps lead and security reviewers; `/ops/permissions` for the platform owner and the FinOps lead.
- **Corrections of statements the writers or the older text made:** playground evaluations are on by default in Foundry and switched off here (10 and 08); the Grafana dashboards row states what the vendor and Learn say; a failed check pauses a Credential and steps the domain down to Assist until a person has reviewed it (03 §7); the Verifier confirms a purchase on the bill where the bill shows it and with the partner where the partner holds it (06 §5).
- **Size.** The design budget moved from 49,000 to 52,500 words when the asks were placed, and the cuts that followed the reviews kept it there ([CHANGELOG](../../../CHANGELOG.md)).
