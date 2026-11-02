# Build review 1: brief for the code reviewer

The project owner authorised building, to answer the remaining uncertainties: the repository foundations, the first checks that need code, spend and stop controls, pilot-data feasibility and the small learning demonstration, each with a named owner, a spending cap and a review date. [AGENTS.md](../../../AGENTS.md) rule 15 holds the limits of that authorisation. You review what was built so far. You edit no file except your report (see Output).

Repository: `<repo>` (the local folder keeps its old name; the product and the GitHub repository are called Meternaut). It is private. The system it describes is a team of AI agents that finds waste in Azure bills, tells the owners and acts only with a person's OK. Nothing in it is deployed, and nothing was run against an Azure subscription.

## What to review

| Path | What it is |
|---|---|
| `evaluation\c14\` | The harness of check C14, the small learning demonstration: `harness\*.py`, `run.py`, `pack-template\` (an invented template pack), `tests\`, `README.md` |
| `evaluation\README.md`, `evaluation\stages.json` | The folder's rules and the proposed owner, cap and review of each early stage |
| `tools\pilot-feasibility.py`, `tools\tests\test_pilot_feasibility.py` | The probe of check C13, stage 0: reads one closed month of bill lines per resource and reconciles it |
| `.github\workflows\checks.yml`, `.github\CODEOWNERS`, `.github\dependabot.yml` | The first CI, code ownership and update configuration |

Read them against the plan text they implement: `docs\build-plan\03-first-checks.md` (C13 and C14), `docs\build-plan\02-before-you-start.md` (what is recorded for each finding), `docs\build-plan\04-cost-effort-and-risks.md` (the stage spending cap), and the design they rest on: `docs\design\04-knowledge-and-learning.md` (the claim), `docs\design\08-testing-and-evaluation.md` (the learning test), `docs\design\14-agreements-and-access.md` (cost data paths).

## What to check

1. **C14 harness: does it do what the plan says, and can it pass without a gain?** Look for scoring bugs and off-by-one errors (found, priced, the median of three runs, the bars of two, five and four, the decoys); any way for the answer key or the cases to reach a prompt, including the prompt that proposes the claim; any difference between the three arms other than the claim (model alias, prompts, settings, order, length of the control); the check that the claim copies nothing from a case; the two-call stop test; the call limit and the spending cap (can a real run exceed either, or start without a cap?); how the hub client is configured and what it logs or stores (a key or token must never be written to a report); and whether the report keeps every answer and states its limits. Say what a careless or hurried person could do to make a pass meaningless.
2. **C13 probe: is it safe and is it right?** It must never use the default subscription of the command-line tool, never read an open month, never write inside the repository, never print, log or store a token or a download URL with its signature, and never send a bearer token to the storage blob. Check the request shapes against Microsoft Learn (the Cost Details report: `generateCostDetailsReport`, api-version `2022-05-01`, polling by the `Location` and `Retry-After` headers; the Query API, api-version `2023-11-01`, totals) and say what you read. Check the reconciliation (1 %, billing currency, unassigned lines), the `--file` route for pay-as-you-go, the price-basis evidence, how the token is obtained, and what an error message can leak.
3. **Tests: do they test behaviour?** Run `python -m unittest discover -s evaluation/c14/tests -t evaluation/c14` and `python -m unittest discover -s tools/tests` from the repository root (standard library only; nothing is installed). Name tests that cannot fail, mocks that hide the bug they should catch, and cases that are missing.
4. **CI: will it run?** It runs on `ubuntu-latest`, and the code was written on Windows: path separators, encodings, line endings, `python` against `python3`, the `$RUNNER_TEMP` use in the last step. Check that each action is pinned to the commit of its stated tag (you may use read-only `gh api` GET calls to github.com for that), that permissions are minimal, and that nothing in the workflow can leak a secret.
5. **The rules.** No secret, token, tenant or subscription id, mailbox or personal data in any new file; no package from a public registry and no network call that is not named in the code's header; nothing that deploys, spends or writes to Azure; none of the vocabulary the project dropped (lab, exam, Terrarium, wind tunnel, time machine, learner) in any file, code comments and strings included; no remark in a README that reads as the history of the project.

## Rules for you

This is a Microsoft-managed device. Use no public package registry (PyPI, npm, NuGet, PowerShell Gallery) and no workaround. Read nothing from any Azure subscription and run no command that reads or changes Azure resources. Start no OBS Studio (if one is ever started it must carry `--portable`), and post, comment or react on nothing on any GitHub repository. Publish nothing and run no release workflow.

## Output

One file, `docs\reviews\build-plan-v2\build-review-1.md`, and nothing else written: a table `| # | Severity | File:line | What is wrong | Fix |` (Blocker, Major or Minor; a Blocker means a pass could be meaningless, a secret could leak or something could spend or write to Azure), a list `## Checked and found right` and a last line `Release: YES` or `Release: NO`.
