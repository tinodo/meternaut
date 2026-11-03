# Hub review 2, first-run fixes: disposition

The same reviewer (gpt-6.1-sol) read the fixes that followed the first runs of the workflow against the real services (commit `b7be2d1`). The report is [hub-firstruns-1.md](hub-firstruns-1.md). The verdict: no Blocker or Major, no reason to hold the deploy; one Minor in the removal. It is accepted and fixed. The deploy was not held, as the reviewer said, and it went through.

| # | Finding (severity) | Verdict | What was done (where) |
|---|---|---|---|
| H2-18 | In the removal, a budget list that could not be read was swallowed inside an `if` condition and taken for "the budget exists" (Minor) | Accepted | The count of the budget in the list is read by a plain assignment, so a failure stops the step; the count must be `0` (nothing to delete) or `1` (delete that budget), and anything else stops the step with a message. The one budget that could ever have been reached is the one the template makes, so nothing wrong could have been deleted. Two scenarios in the shell simulation (a list that cannot be read, and a count of 2) show that no budget is deleted, and the test of the workflow refuses a command substitution inside a `[` condition, which is the pattern that swallowed the failure (`.github/workflows/deploy-hub.yml`, `tools/tests/test_workflow_lint.py`) |

## What the reviewer asked the next real run to prove

- **That the authenticated PUT, then HEAD, on the link between a product and an API works on the instance.** Seen: the `deploy` that added the objects created the link, the check by HEAD found it, and the next plan read it as unchanged.
- **That the budget collection's real answers give the intended date.** Seen for a missing budget (the list is empty, so the date is the first of the current month). The answer for an existing budget has not been checked against its start date yet.
- **That a real DELETE of an API that answers 202 completes, and the product follows.** Not yet seen: both `pause` runs found no objects in the instance. While looking at them, a different thing showed: a DELETE of an object that is not there answers `204`, which the tool had reported as "deleted"; each object is read first now and what was not there is "absent" (see [the changelog](../../../CHANGELOG.md)).

## What was kept

The reviewer's own checks passed: 184 of 184 tests, both Bicep templates, the handling of HEAD with `urllib` (a 204 without a body, retries, no redirect), the fences of the tool (the allow-list, the address read-back, the prefix rule, the token only to the management host), the order and the waiting of the removal, and the changed `present()` matching.
