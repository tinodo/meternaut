# Design v5, closure check: disposition

One closure checker (gpt-5.6-sol, [closure-1.md](closure-1.md)) checked every finding of the two design v5 reviewers against the fixed text, and read the fixes for what they broke. An earlier attempt on another model returned nothing and was repeated. The result: 14 of the 19 findings closed, 5 closed only in part, and 12 new defects (11 Majors, 1 Minor). Its verdict was "Release: NO". Its last lint run failed only because the build plan's files were being edited at the same moment. Every item below was checked against the files before anything changed, and all are fixed. [The first disposition](disposition.md) holds the record of the two reviewers.

## Findings closed only in part

| Finding | What was left | What was done |
|---|---|---|
| A2, B2 | The card manifest still let the approver or a delegate undo a change, not the holder of the rollback grant | The manifest authorises Undo by the recorded grant holder only; for a change under a Credential that is each owner of record |
| A6 | Section 6 of the security design still said the request id is the only identifier a card, button or bot may carry | It says the request id is the only identifier, beside the verb, the plan code where the card decides and the inputs the card manifest lists |
| A8 | The freshness paragraph in the data design said the final export "matches the invoice" | It says the final file is the closing Cost Management input to reconciliation, which leaves out credits, taxes and support |
| B7 | The experience sample for a purchase request still named a saving and scopes while the text said both are left out | The saving, the evidence and the names are out of the sample; it keeps the product, the term, the stored amount, the scope identifiers and the deadline |

## New defects

| Defect | What was done |
|---|---|
| A page action other than a decision, an Undo or a preference reached Respond, which also caught the kill switch and Credential forms | The routing sentence names the Approval service as the handler for a decision, an Undo, a preference, a switch or a Credential; only conversational actions reach Respond |
| Undo "stays open whatever the record shows" conflicted with a pulled switch, which stops every new runner step | Undo is checked against its own grant and window; a pulled switch holds the run until it is released, and the person is told |
| "Any push due in quiet hours waits" delayed the report of a run under a standing permission, which the design promises within minutes | The promise is qualified in the agents design: the report of such a run waits only for quiet hours to end |
| Two approval records for a purchase against one request record with two approvals | One approval record with two approvals, in the security design |
| The roadmap named one allowed reader for the Monday letter and never said when the platform owner joins | Phase 1a has the FinOps lead alone; the platform owner joins in phase 2 |
| The Delegates row of the settings page left out the sign-in and the notice the design requires | The row says a delegate is named only after the sign-in that R2 needs, and the person is sent a notice |
| "The bill is at retail rates" for a partner-sold subscription | The sentence says the customer-tenant Cost Management lines show retail rates; the partner owns the invoice and its price |
| The runbook gave a human no way to write a switch when the page is down | The runbook runs the same commands under a time-boxed data role on the switch store, which is alerted and reviewed the next day |

## What was not adopted

Nothing in this round. The structural split of the purchase switch and the move of R2 Undo to the page, which the reviewers asked for earlier, stay as decided in [the first disposition](disposition.md): the risks are stated in the design.
