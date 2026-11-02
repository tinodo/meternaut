# Build review 1, closure: disposition

The reviewer of the build ([build-closure-1.md](build-closure-1.md)) read all 13 findings again against the fixed files, ran both test suites and compiled and linted both Bicep templates. All 13 are closed, the reviewer agrees with the four parts that were not adopted (a minimum share of lines with a resource id, a bar on citations of the new claim, a check of every number in a case's facts, the case title), and the verdict is Release: YES. The reviewer found three new Minor defects. This record says what was done with each.

| # | Finding (severity) | Verdict | What was done (where) |
|---|---|---|---|
| N1 | After a run, `report` works out the verdict again from `review.json`, so a decision, a reviewer or a claim edited after the run could turn it into a pass (Minor) | Accepted | The run stores a hash of the decision, the reviewer and the claim; `report` refuses with exit code 2 when `review.json` no longer matches, and the arms must run again (`evaluation/c14/harness/runner.py`, `run.py`) |
| N2 | The check for the key's amount misses two-decimal forms and fractional amounts with a comma (Minor) | Accepted | An amount is caught as 1168, 1,168, 1168.00, 1,168.00 and 1,168.5 (`evaluation/c14/harness/cases.py`) |
| N3 | The scope check misses the older Enterprise Agreement scopes `/providers/Microsoft.Billing/departments/{id}` and `/enrollmentAccounts/{id}` (Minor) | Accepted | The scope list of the Cost Details Create Operation page on Microsoft Learn names both forms; both are accepted (`tools/pilot-feasibility.py`) |

The reviewer also found that the new Bicep step of the CI workflow should work on `ubuntu-latest` (the Azure CLI is installed there and fetches the Bicep binary from GitHub on first use), and noted that the new review files had to be linked from the index before the documentation lint could pass in CI; they are. The tests now number 145, 100 for the harness and 45 for the probe.
