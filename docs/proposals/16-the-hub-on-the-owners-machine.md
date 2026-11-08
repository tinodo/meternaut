# The Hub on the owner's machine — a decision record

**Status: ordered by the owner on 2026-11-08.** Every deploy runs from the owner's machine, with his own `az` session, by [`tools/hub-local.py`](../../tools/hub-local.py), which runs the steps of the Hub workflow; the workflow stays the one description of every deploy. No GitHub workflow changes Azure any more.

## Why

The owner's GitHub Actions quota was used up, and the Hub workflow was the only way a change reached Azure ([rule 18](../../AGENTS.md)). He chose to deploy from his machine rather than wait.

## What runs where

| What | Where |
|---|---|
| The bash of the steps, the tools of `tools/`, `az` | The owner's machine, in Git's bash |
| `hub-local.env`, the run counter, the lock, the records | The git-ignored `local/` folder of the main working tree (the parent of `git rev-parse --git-common-dir`), shared by every worktree; `METERNAUT_LOCAL` overrides it |
| `deploy-hub.yml` | GitHub, unchanged, run by a click only |

The tool reads the workflow with its own reader, decides each `if:` itself and runs each step's script.

## The guards

A guard refuses and does not warn. The `az` session is a person's, in the configured tenant. The action and every input are options of the workflow. An action that only reads needs no `--yes` (`what-if`, `aigateway-check`, `page-latency`, `loop-check`, `operator-probe`, `drift-check`, `agents-drift`, `agent365-check`, and `foundry-evals` with `probe` or `rule`); every other action, and any that the tool does not know, needs it, and without it only the plan is printed. `aigateway` also needs `--public-ai-gateway-requested`, and `teams` needs `--public-teams-bot-requested` and the line `TEAMS_BOT_ENABLED=True` in the configuration. A change of Azure needs a clean working tree (`--allow-dirty` overrides). One run at a time: a lock file, taken over when its run is gone. The configuration is git-ignored and untracked. Every expression resolves, or nothing runs: a step that needs a GitHub token or calls `gh` stops the plan.

The tools that change Azure from the runner (`az-deploy.py create`, `retire-old.py`, `cases-move.py`, `aigateway-prep.py`, `operator-run.py`) used to trust `GITHUB_ACTIONS=true`, which any process on the machine can set. They now ask `tools/hubguard.py`: a real GitHub runner, or `METERNAUT_HUB_PROOF`, a file with a random token that a run makes under `local/rt/` before its first step, names in its lock by digest and deletes when it ends, after a failure or Ctrl+C too. `az-deploy.py` and `retire-old.py` also name only the project's subscription and group. This stops accidents and stray calls, not a process that holds the owner's `az` session: it can call `az` itself. The Operator's container has no lock, so its tools keep the old test.

## What a person sees

`--dry-run` prints the plan and needs no `az` session. The inputs are flags (`--help` lists them); the workflow's default is used and printed when one is missing. A run prints the steps live, writes a record and a log to `local/records/` (commit, tree state, each step's outcome, what was restored) and ends with `Hub (local) <action>: PASSED in N minutes` or `FAILED`.

## What changed from a run on GitHub

- **No unit tests and no look at CI:** no GitHub call is made and no token exists here. The person ran the checks on this machine; the record names the commit and the tree's state.
- **The identity is the owner's own session, with his rights.** The steps (each command names the project's group; a test pins that) and the guards limit a run, not roles. The role checks of `aigateway` and `governance` count Owner and User Access Administrator on the group or above it.
- **The CLI's default subscription** is set to the pilot's for the run and put back at the end, after a failure or Ctrl+C too, and by the next run if this one was killed ([rule 15 (b)](../../AGENTS.md)).
- **The cases code is built here and published from this machine** through the app's public deployment site (`az functionapp deployment source config-zip`), which needs the app's public network access Enabled. The files in the zip are first held against the digest that the deploy wrote as `PACKAGE_SHA256` (`tools/package-digest.py`; CRLF is read as LF); a package that differs is not published.
- **`DRIFT_ACCEPTED_EXEMPTIONS` and `DRIFT_ACCEPTED_DENY` are optional:** absent is empty, as on GitHub. Every other name has to be in the file.
- **The run number** is a counter in `hub-local.state.json`; only a change of Azure uses up a number.

## What the Operator steps need

The checks that run in the Operator (the health wait, `cases-run`, `page-latency`, `loop-check`, the gateway and agent checks) make a container group with the owner's own rights: Container Instances registered, and the right to create it, join the Operator's subnet and use its identity.

## Not supported

Anything that needs a GitHub OpenID Connect token: the publish of the cases through the Operator, and the probe's check that the deploy identity signs in (`operator-probe` goes on without it and says so). A step that is not `run`, `actions/checkout`, `actions/setup-python` or `azure/login` stops the plan. Tested on Windows with Git's bash.

## What Git's bash on Windows breaks

| What breaks | What the tool does |
|---|---|
| CRLF line ends of the checkout | The workflow is read as LF and every script is written with LF |
| Bash rewrites an argument that looks like a path (`/subscriptions/...`) | `MSYS_NO_PATHCONV=1`, `MSYS2_ARG_CONV_EXCL=*`; the package build gets the conversion back: its script wants a leading slash |
| `python3` is the Store alias; a native Python cannot start `az`; `az.cmd` mangles `&` and quotes | A `python3` shim; the CLI runs through its own `python.exe`, and `az login`, `logout`, `account set` and `config set` are refused |
| `taskkill /T` misses what Git's bash started | Every step runs in a Windows job object that ends all of it |
| The system's text encoding, block-buffered pipes | UTF-8 and unbuffered output |

## The way back

A click on the workflow deploys as before, once the quota is there.
