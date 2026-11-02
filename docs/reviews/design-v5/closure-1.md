# Design v5 closure check 1

## Findings

| ID | Verdict | File:line | Closure |
|---|---|---|---|
| A1 | CLOSED | `docs/design/05-data-and-integrations.md:213` | Undo, “I did not approve this” and “Talk to a person” are exceptions in the design, experience contract and manifest. |
| A2 | PARTLY | `docs/design/05-data-and-integrations.md:201,211`; `docs/experience/cards/manifest.json:12` | The owner holders, 24-hour starting window and separate consumption item landed, but the manifest still authorises Undo by approver/delegate rather than by the rollback-grant holder. |
| A3 | CLOSED | `docs/design/09-delivery-and-operations.md:26` | The code-owner, last-pusher, stale-approval, bypass, trusted-check and fork-event rules are present; `pr-draft` points here. |
| A4 | CLOSED | `docs/design/05-data-and-integrations.md:170` | Counted pushes and exempt Hello, desk, replies and safety notices are listed. |
| A5 | CLOSED | `docs/design/05-data-and-integrations.md:58` | Bound fields are immutable; only decisions, status and revocation are added by the Approval service under etag. |
| A6 | PARTLY | `docs/design/06-security-and-governance.md:129` | `05` and `08` now use manifest-declared fields, but `06` still says the request id is the only identifier a card, button or bot may carry. |
| A7 | CLOSED | `docs/design/05-data-and-integrations.md:178` | Every purchase approval, and affected one-person page approval, gets the paired e-mail with matching id, code and expiry. |
| A8 | PARTLY | `docs/design/05-data-and-integrations.md:70,89` | Section 2 now bridges excluded charges and keeps explained differences, but its freshness paragraph still says the final export “matches the invoice.” |
| A9 | CLOSED | `docs/design/01-goals-and-scope.md:72` | F5 now limits Challenge and Teach to spend claims or decisions and keeps Explain/help elsewhere. |
| A10 | CLOSED | `docs/design/13-roadmap.md:23-27` | Phase 1a has fixed notification/introductory handling; R2 readiness is phase 3 and R3 readiness phase 4. |
| A11 | CLOSED | `docs/design/04-knowledge-and-learning.md:307-309` | The sample now says “Notes” and “routine check,” not internal names. |
| B1 | CLOSED | `docs/design/05-data-and-integrations.md:234`; `docs/design/06-security-and-governance.md:275` | Delegates require Settings plus R2 sign-in and a notice; card mutes/pause and their residual risk are stated. |
| B2 | PARTLY | `docs/design/05-data-and-integrations.md:211`; `docs/experience/cards/manifest.json:12` | The one-tap choice and stolen-session risk are explicit, and consumption is separate; the manifest still contradicts the Credential holder rule. |
| B3 | CLOSED | `docs/design/05-data-and-integrations.md:160` | Submit requires the designated approver/delegate object id and the class authentication-context claim; forwarding grants nothing. |
| B4 | CLOSED | `docs/design/06-security-and-governance.md:274`; `docs/design/05-data-and-integrations.md:239` | The unadopted structural split and the Approval service trust-anchor risk are explicit. |
| B5 | CLOSED | `docs/design/05-data-and-integrations.md:128`; `docs/design/09-delivery-and-operations.md:26` | The stolen App can forge a check but cannot merge; human review and safe fork workflow rules are enforced. |
| B6 | CLOSED | `docs/design/05-data-and-integrations.md:186`; `docs/design/09-delivery-and-operations.md:205` | Organisation-wide admin consent precedes first contact, so a later consent screen is a fake. |
| B7 | PARTLY | `docs/design/14-agreements-and-access.md:123`; `docs/experience/05-letters-and-requests.md:84-99` | The technical rule is fixed, but the experience sample still sends a saving and scope names despite saying those are excluded. |
| B8 | CLOSED | `docs/design/14-agreements-and-access.md:149` | The current sentence matches Learn: enabled customer visibility shows purchases at pay-as-you-go rates and reservation usage at zero. |

## New defects

- Major · `docs/design/06-security-and-governance.md:129` · “The only identifier a card, button or bot may carry” · contradicts the verb, plan-code and declared-input contract · replace it with the exact manifest field rule.
- Major · `docs/experience/cards/manifest.json:12` · “undo … needs the designated approver or a named delegate” · excludes Credential owners and permits delegates who do not hold the rollback grant · authorise Undo only by the recorded grant holder.
- Major · `docs/experience/05-letters-and-requests.md:85` · “Saving: about EUR 4,700 a month … Scenario saving” · the external request violates `05:182` and `14:123`, and `84/99` also disclose scope names · remove saving/evidence/names; keep product, term, stored amount, scope identifiers and deadline.
- Major · `docs/design/05-data-and-integrations.md:70` · “its final file matches the invoice” · contradicts `89`, because Cost Management omits credits, taxes and support · say it is the closing Cost Management input to reconciliation.
- Major · `docs/design/05-data-and-integrations.md:170` · “any push due in quiet hours waits” · delays C8/C16/C17 although `03:194` and experience promise standing-permission runs are reported within minutes · exempt safety notices or qualify the promise consistently.
- Major · `docs/design/06-security-and-governance.md:244` · “Two approval records, the stored quote” · disagrees with `05:190,200`: one request record contains two approval entries · say “one approval record with two approvals.”
- Major · `docs/design/05-data-and-integrations.md:213` · “Undo … stay open whatever the record shows” · conflicts with switches stopping every new runner step (`06:174`, `07:48`) · define whether rollback bypasses a switch, queues, or is refused.
- Major · `docs/design/05-data-and-integrations.md:160` · “A page action other than a decision, an Undo or a preference reaches Respond” · also captures kill-switch and standing-permission forms · restrict this routing sentence to conversational actions and name operational handlers.
- Minor · `docs/design/13-roadmap.md:23` · “one allow-listed reader, the FinOps lead” · no later phase adds the platform owner, although experience says both receive every Monday letter · state the phase-1a exception and expansion phase.
- Major · `docs/experience/06-web-pages.md:112` · “Delegates | Who may answer for the person” · the experience omits the R2-strength sign-in and notice promised by `05:234` and `06:153` · add both to Settings.
- Major · `docs/design/14-agreements-and-access.md:57` · “the bill is at retail rates” · Learn says the customer Cost Management view is retail; the partner owns the invoice and its price · replace “bill” with “customer-tenant Cost Management lines.”
- Major · `docs/design/09-delivery-and-operations.md:155` · “One person runs the runbook's commands for the same switch” · the access matrix names no human/emergency switch writer, so the fallback cannot be implemented from the text · state that commands call the healthy Approval service or define the emergency identity and release checks.

## Verification and tool results

- [Microsoft Learn, Exchange RBAC for Applications](https://learn.microsoft.com/exchange/permissions-exo/application-rbac): **verified**. RBAC grants are independent of and additive to Microsoft Entra grants; effective permissions are their union, so organisation-wide `Mail.Send` must be removed.
- [Microsoft Learn, Cost Management for partners](https://learn.microsoft.com/azure/cost-management-billing/costs/get-started-partners): **verified**. With cost visibility enabled, customer usage and associated purchases appear at pay-as-you-go rates; reservation actual and amortised usage charges are zero.
- `python tools\check-docs.py --strict`: the requested pre-report run passed — 89 documents, 0 errors, 0 warnings. The final post-write run saw concurrent build-plan edits and failed — 95 documents, 6 orphan errors (five `build-plan-v1/cold-*.md` reports and this report) and 8 warnings, all in concurrent build-plan files.
- `python tools\cost-model.py --check docs\design\10-cost-and-finops.md`: exit 0.
- `python tools\cardlint.py`: exit 0 — 0 problems.

Release: NO.
