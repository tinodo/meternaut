# The Hub on the owner's machine — a decision record

**Status: ordered by the owner on 2026-11-08; built the same day.** Every deploy runs from the owner's machine, with his own `az` session, by [`tools/hub-local.py`](../../tools/hub-local.py), which runs the steps of the Hub workflow; the workflow stays the one description of every deploy. No GitHub workflow changes Azure any more.

## Why

The owner's GitHub Actions quota was used up, and the Hub workflow was the only way that a change reached Azure ([rule 18](../../AGENTS.md)). He chose to run deploys from his machine rather than wait for the quota.

## What runs where

| What | Where |
|---|---|
| The bash of the steps, the tools of `tools/`, `az` | The owner's machine, in Git's bash |
| `hub-local.env`, the run counter, the lock, the records | The git-ignored `local/` folder of the main working tree (the parent of `git rev-parse --git-common-dir`), so every worktree finds the same files; `METERNAUT_LOCAL` overrides it |
| `deploy-hub.yml` | GitHub, unchanged, run by a click only |

The tool reads the workflow with a reader written for its layout, decides each `if:` with a small evaluator (workflow text never reaches the interpreter) and runs each step's script. The tools of `tools/` accept only a run of the Hub, so the steps get `GITHUB_ACTIONS=true` and `METERNAUT_HUB_LOCAL=1`: the local Hub is the Hub.

## The guards

The tool refuses; it does not warn. Git's bash is found (not the WSL launcher). The `az` session is a person's, in the configured tenant. The action is one of the workflow's options. Every action except `what-if`, `aigateway-check`, `page-latency`, `loop-check` and `operator-probe` needs `--yes`; without it the plan is printed and nothing runs. `aigateway` also needs `--public-ai-gateway-requested`. An action that changes Azure needs a clean working tree (`--allow-dirty` overrides). One run at a time: a lock file, taken over when its run is gone. The configuration is ignored by git and not tracked. Every expression of the plan resolves, or nothing runs.

## What a person sees

`--dry-run` prints the plan (each step that would run, what its condition said, what is replaced) and needs no `az` session. A run prints the steps live, writes `local/records/hub-local-<action>-<time>.md` (commit, clean or not, each step's outcome and seconds, the summary, what was restored) and a `.log`, and ends with `Hub (local) <action>: PASSED in N minutes` or `FAILED`.

## What changed from a run on GitHub

- **No unit tests in the run.** The person who starts it has run them here; the commit and the tree's state are recorded.
- **The identity is the owner's own session, with his rights.** Azure no longer limits a run to the deploy identity's roles; the steps (every command names the project's resource group; a test pins that) and the guards above do. A step that reads the deploy identity's role assignments reads the signed-in person's: the `aigateway` check wants Role Based Access Control Administrator on the group itself, which Owner is not, so it stops there.
- **The CLI's default subscription** is set to the pilot's for the run and put back at the end, after a failure or Ctrl+C too, and by the next run if this one was killed ([rule 15 (b)](../../AGENTS.md)). Another `az` session on the machine sees the pilot's meanwhile.
- **The cases code is built here and published from this machine** through the app's public deployment site (`az functionapp deployment source config-zip`). It needs the app's public network access to be Enabled; the tool reads that first and stops when it is Disabled.
- **The run number** is a counter in `hub-local.state.json`; only an action that changes Azure uses up a number (planted waste is named with it).

## What the Operator steps need

The checks in the Operator (`cases-run`, `page-latency`, `loop-check`, `aigateway-check`, the health wait of `cases`) create a container group with the owner's own rights: Container Instances registered in the subscription, and the right to create the group, join the Operator's subnet and use its identity. Azure refuses otherwise, and the step says so.

## Not supported

Anything that needs a GitHub OpenID Connect token: the publish of the cases through the Operator, which is why the tool publishes from the machine, and the probe's check that the deploy identity signs in inside the Operator (`operator-probe` goes on without it and says so). A step of another kind than `run`, `actions/checkout`, `actions/setup-python` and `azure/login` stops the plan. It is tested on Windows with Git's bash.

## What Git's bash on Windows breaks

| What breaks | What the tool does |
|---|---|
| CRLF line ends in the checkout, which bash cannot run | The workflow is read as LF and every script is written with LF |
| Bash rewrites an argument that looks like a path (`/subscriptions/...` becomes a path under Git's folder) | `MSYS_NO_PATHCONV=1` and `MSYS2_ARG_CONV_EXCL=*`; the build of the function app, the one script that needs the conversion, gets it back |
| `python3` is the Store alias, and a native Python cannot start a bare `az` | A `python3` shim runs the tool's Python; the CLI runs through its own `python.exe`, by a shim in bash and a `sitecustomize` hook for the tools |
| `az.cmd` goes through cmd.exe, which takes an `&` or a quote inside an argument for its own | The same shim: no step goes through cmd.exe. It refuses `az login`, `logout`, `account set` and `config set` |
| `taskkill /T` cannot find what Git's bash started, so a `sleep` or an `az` outlived a timeout | Every step runs in a Windows job object that ends all of it |
| The system's text encoding, and block-buffered pipes | UTF-8 and unbuffered output |

## The way back

A click on the workflow is the same deploy as before, once the quota is there. The tool stays for a person who wants a plan first.
