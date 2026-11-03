# Hub review 2, final check: disposition

The same reviewer (gpt-6.1-sol) read the branch once more at commit `fe81e94`, narrowly: the three fixes of the closure round, the three findings that were closed in part, the new way of reading an object's state, and the workflow lint against other layouts of valid YAML. The report is [hub-final-1.md](hub-final-1.md). The verdict: the package is safe to hand to the owner as a pull request, with no blocking defect; one new Minor (H2-17), because of which two older findings stayed in part; and one question that only the first real run can answer. All of it is accepted. H2-17 was reproduced with a YAML parser before it was fixed.

| # | Finding (severity) | Verdict | What was done (where) |
|---|---|---|---|
| H2-17 | A guard that is only text inside a quoted value passes the lint (Minor) | Accepted, reproduced | With the real guard removed and the reviewer's quoted job name in its place, a YAML parser (PyYAML) reads the job as having no `if:` at all, and the lint reported zero findings; the same worked with the text hidden in `runs-on`. The lint reads one line at a time, so any value that goes on over several lines can hold a line that only looks like a setting. Fixed at the root: the lint now refuses a quoted value, and a list or map in brackets, that does not close on the line where it opens, in every workflow (block scripts written with `\|` or `>` are skipped, since their lines are text, and a quote opens a string only where YAML lets one start, so an apostrophe in a plain value such as `it's` or `== 'main'` is not flagged). Tests: the reviewer's decoy and four more places to hide it (`runs-on`, a single-quoted value, a map in braces, a list in brackets), the values that must stay accepted, and, where a YAML parser is installed, that the parser also reads each decoy as a job without `if:`. The new tests were run against the previous lint, and the ones that look for the hole fail there (`tools/workflow-lint.py`, `tools/tests/test_workflow_lint.py`) |
| H2-15, H2-12 | Closed in part, because of H2-17 | Closed by the fix of H2-17 | As above |
| H2-14, H2-05, H2-08, H2-16 | Closed | Nothing to do | The reviewer's probes of the states (`200`, `201` and `202` followed by a `404`, a working state, a final one; failed and cancelled; time-outs; read errors; policies, links and subscriptions, which have no state) found nothing wrong |

## The state words: a heuristic, hardened

The reviewer did not call this a defect, and it is not settled either. The fallback "a word that is on no list is a final state" is a guess: in the reviewer's probes `Queued`, `NotStarted` and `In Progress` were taken as final, a following write then started too early, failed with a `409` and stopped the run, and work was left half done. What the instance really says is known only from its first run. So:

- **Words are compared without case, spaces, underscores and hyphens**, so `In Progress`, `in_progress` and `InProgress` are one word.
- **More words are on the lists:** working (queued, not started, waiting, submitted, deploying, validating, migrating, scaling, restarting and deleting, besides the ones before) and failed (error, rejected, aborted and timed out, besides failed and cancelled).
- **A word on no list is printed** as a note, once, also when the run stops with an error, so that the first real run shows the real vocabulary. Every character of it that is not a letter, a digit, a space, a dot, an underscore or a hyphen is replaced, so that a state word cannot start a workflow command.
- **A write that starts too early** still fails and stops the run, and nothing wrong is left behind: the next run's plan sees the finished object as unchanged and goes on from there.

The reviewer also asked whether polling the object's own address, and not the address in the `Location` header, is a weakness. It is not, and it keeps the rule that the token goes only to addresses the tool built. If the first run shows that the instance's ordinary read does not report a current state, polling through an operation address, checked to lie inside the same resource, is the next step (`tools/apim-sync.py`, `tools/tests/test_apim_sync.py`, `hub/README.md`).

## Also changed: the same kind of hole, found while fixing H2-17

- **A list or map in brackets** that goes on over several lines can hide a line in the same way as a quote, and is refused with it.
- **A `run:` script written as a plain value over several lines** was read only on its first line, so a `${{ }}` expression on a later line escaped the rule that keeps expressions out of scripts. It is read to its end now; the same script inside a quote over several lines is refused.
- **Characters that readers do not agree about** (control characters, and the line breaks U+0085, U+2028 and U+2029, which Python splits on and a YAML reader may not) are refused, so that the lines the lint counts are the lines GitHub reads.
- **A second check in CI that does not read line by line.** Ruby's YAML parser, which the runner has, reads `deploy-hub.yml` and checks from the parsed structure that there is exactly one job, that its `if:` is the owner-and-main guard, that it has no `continue-on-error`, that it starts on `workflow_dispatch` alone and that it has a concurrency group. The line lint stays as the quick check; the parser is the one a decoy cannot fool. **Seen:** it passes on the real file, and on a throwaway branch with the guard removed (and the earlier steps made non-blocking, so that it was reached) it failed with `job hub: its if is not the owner-and-main guard`; the unit tests of the tools failed there too. The throwaway pull request was closed and its branch deleted. The same check is also a unit test with PyYAML, which runs where PyYAML is installed (it is not on the runner) (`.github/workflows/checks.yml`).
- The tools' tests went from 168 to 177. The README's list of what has not been seen carries the state words.

## What was kept

The reviewer's own checks passed: 168 of 168 tests, both Bicep templates, readiness failures that stop processing, and removal that deletes directly and never waits.

## What only the first run can prove

That the instance's ordinary read reports a current state after each write, and which words it uses (they are printed now). The other open points are unchanged and are listed in [the README](../../../hub/README.md#what-has-been-checked-and-what-has-not).
