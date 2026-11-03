# Hub review 2, first-run fixes: raw report

The same reviewer (gpt-6.1-sol) read, narrowly and read-only, the fixes that followed the first runs of the workflow against the real services: commit `b7be2d1` of the branch `fix-first-runs` (the tool's handling of the link between a product and an API, the waiting for an API's removal, the budget steps of the workflow, and the stand-ins and tests for them). The review changed nothing in Azure or GitHub. The report is as delivered, except that the file paths were absolute and are shortened here to paths relative to the repository.

## Verdict

**No Blocker or Major was found in `b7be2d1`; this review found no reason to hold the deploy.** One Minor, removal-only error-handling defect remains, and all **184 tests** plus both Bicep builds/lints passed.

## New defect

| ID | Severity | file:line | What is wrong | Why it matters | Suggested fix |
|---|---|---|---|---|---|
| **H2-18** | **Minor** | `.github\workflows\deploy-hub.yml:275–278` | A failed budget-list command is swallowed inside `if [ "$(az rest …)" != "0" ]`. Under the runner’s Bash flags, my failing-list probe produced an empty result, executed DELETE and returned success. The new budget test checks source strings, not this behaviour. | A transient failure during this later cleanup lookup is treated as evidence that the budget exists. **It cannot select another budget:** DELETE still names the fixed, approved budget. The deploy path is unaffected. | Capture the count in a standalone assignment so command failure propagates, then validate it as `0` or `1` before branching. Add a shell test asserting that list failure prevents DELETE and leaves the step unsuccessful. |

## Checks performed

- **184/184 tests passed**, with zero failures, errors or skips. Sources and tests were pinned to `b7be2d1`; fixture writes were virtualized in memory.
- **Bicep 0.46.1:** both hub and resource-group budget templates built and linted successfully, using stdout capture and `--no-restore`.
- **HEAD handling:** an actual Python HTTP-response parser handled bodyless HEAD 204 without `Content-Length`. Independent urllib-handler probes confirmed HEAD retries after 429 and refuses redirects without making another request.
- **Link handling:** plan/checks use HEAD, link deletion omits `If-Match`, and other deletions retain it. Unexpected error statuses fail rather than becoming absence. The implementation also tolerates HEAD 200 as existence.
- **Ownership fences remain intact:** `LINK` matches some foreign or malformed paths, but it is a classifier—not the allow-list. Fifteen CLI probes of such paths were rejected before any GET/HEAD/DELETE. The prefix check, URL read-back and management-host token restriction remain unchanged.
- **Async removal:** tests verify that API deletion waits through 202 until absence before deleting the product, retains `deleteRevisions=true`, and stops without deleting the product on timeout. An independent probe also completed an asynchronous link deletion using HEAD 204 → 204 → 404.
- **Budget lookup:** existing dates are preserved; empty/`None` results choose the current UTC month. A failed initial list command stops immediately, unlike H2-18’s later cleanup check. Invalid date prefixes remain rejected by the parameter helper.

No additional confirmed defect was found in the changed `present()` matching or removal order. No Azure or GitHub changes were performed.

## What the next real run must prove

- The authenticated **PUT → HEAD** association check works end to end on this instance.
- The budget collection’s real existing/missing results produce the intended parameter date.
- On a subsequent pause/remove, real **DELETE 202 → disappearance → product deletion** completes within the polling allowance; read errors or timeouts must leave the run failed rather than claiming cleanup succeeded.
