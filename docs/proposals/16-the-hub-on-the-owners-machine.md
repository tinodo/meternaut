# The Hub on the owner's machine — a decision record

**Status: ordered by the owner on 2026-11-08.** Every deploy runs from his machine, with his own `az` session, by [`tools/hub-local.py`](../../tools/hub-local.py), which runs the steps of the Hub workflow, still the one description of every deploy. No GitHub workflow changes Azure any more.

## Why

The owner's GitHub Actions quota was used up, and the Hub workflow was the only way a change reached Azure ([rule 18](../../AGENTS.md)).

## What runs where

| What | Where |
|---|---|
| The bash of the steps, the tools of `tools/`, `az` | The owner's machine, in Git's bash |
| `hub-local.env`, the run counter, the lock, the records | The git-ignored `local/` folder of the main working tree, shared by every worktree; `METERNAUT_LOCAL` overrides it |
| `deploy-hub.yml` | GitHub, unchanged, run by a click only |

The tool reads the workflow itself, decides each `if:` and runs each step's script.

## The guards

A guard refuses and does not warn. The `az` session is a person's, in the configured tenant. The action and every input are the workflow's own. An action that only reads needs no `--yes` (`what-if`, `aigateway-check`, `page-latency`, `loop-check`, `operator-probe`, `drift-check`, `agents-drift`, `agent365-check`, and `foundry-evals` with `probe` or `rule`); every other action, and any unknown one, needs it; without it only the plan is printed. `aigateway` also needs `--public-ai-gateway-requested`, and `teams` needs `--public-teams-bot-requested` and the line `TEAMS_BOT_ENABLED=True` in the configuration. A change of Azure needs a clean working tree (`--allow-dirty` overrides). **A run also needs a person's word that the code was read** (added on 2026-11-10, when the repository was made public: the final review found that the control for a change from a stranger was only a rule of process, and two looks at the gate that answered it found it got round, first by a path in another case, by code outside four folders, by an action that only reads and by a record that a merge could write, then by a new file in the script's own folder that shadows a module of the standard library, by the rules of the agents counted as documents, by a file named like the recorded commit and by a link): the steps run the tools of this checkout with the owner's own sign-in, so when any path but the folder `docs/` and a few plain files of the root (`README.md`, `CHANGELOG.md`, `SECURITY.md`, `LICENSE`, `NOTICE` and `.gitignore`) differs from the commit that a person last read (`local/hub-local.reviewed`), or none is recorded, the run is refused, an action that only reads included, and it lists the paths and names the `git diff` to read. It goes on only when started again with `--reviewed` and the first 12 characters of the commit. `AGENTS.md` and every other file that ends in `.md` count as code, because they are the rules that the owner's agents follow, and so do the files that an agent obeys (`CLAUDE.md`, `GEMINI.md`, `copilot-instructions.md`, `SKILL.md`, `*.agent.md`, `*.prompt.md`, `*.instructions.md`, `*.chatmode.md`) in any folder, `docs/` too (a name that is not listed is not known). The case of a path does not matter, the paths are read from git's own NUL-separated output, a path with a backslash is code, a commit that holds a symbolic link or a submodule is refused, a record that git tracks or does not ignore counts for nothing, and a change that is not committed is never recorded as read. The top of the tool closes three ways in that a pull request could use to run something before any gate: the folder of the script is taken off the path (a new `tools/argparse.py` does not run first), the search of the current folder for a program such as `git` is switched off on Windows (a `git.exe` in the root does not run first), and the compiled files of a run go to a folder that is made for it (a compiled file in `tools/__pycache__` is not run instead of a source). It is a tripwire for a change that nobody read, not a lock: `tools/hub-local.py` and `tools/hubguard.py`, which it loads, run before any gate can look at them, so their diff is the first thing to read; whoever gives the word may not have read anything; and a run of the tests or of a tool by hand runs the same code with the same session. One run at a time: a lock file, taken over when its run is gone. The configuration is git-ignored and untracked. Every expression resolves, or nothing runs: a step that needs a GitHub token or calls `gh` stops the plan.

The five tools that change Azure (`az-deploy.py create`, `retire-old.py`, `cases-move.py`, `aigateway-prep.py`, `operator-run.py`) trusted `GITHUB_ACTIONS=true`, then what a GitHub runner sets. Any process can set both, and since a GitHub run changes nothing in Azure ([rule 18](../../AGENTS.md)) no runner needs them. So `tools/hubguard.py` accepts one thing: `METERNAUT_HUB_PROOF`, a file with a random token that a run makes under `local/rt/` and deletes when it ends, after a failure or Ctrl+C too. Its lock holds the token's digest and the process's start time; only the repository's own `local/` counts. All five name only the project's subscription and group. A refusal says nothing of why; `python tools/hubguard.py` tells a person. A tripwire, not a lock: it stops accidents and stray calls, not what holds the owner's machine and `az` session (it can call `az` or make a proof). The three tools in the Operator's container (`aigateway-check.py`, `check-helpers.py`, `aisec-helpers.py`) have no run lock to ask and keep the old test; only a private endpoint stops a stray call from that machine.

## What a person sees

`--dry-run` prints the plan and needs no `az` session. The inputs are flags (`--help` lists them); a missing one takes the workflow's default, printed. A run prints the steps live, writes a record and a log to `local/records/` and ends with `Hub (local) <action>: PASSED in N minutes` or `FAILED`.

## What changed from a run on GitHub

- **No unit tests and no look at CI:** no GitHub call and no token here. The person ran the checks on this machine; the record names the commit and the tree's state.
- **The identity is the owner's own session, with his rights.** The steps (each command names the project's group; a test pins that) and the guards limit a run, not roles. The role checks of `aigateway` and `governance` count Owner and User Access Administrator on the group or above it.
- **The CLI's default subscription** is set to the pilot's for the run and put back at the end, after a failure or Ctrl+C too, and by the next run if this one was killed ([rule 15 (b)](../../AGENTS.md)).
- **The cases code is built here and published from this machine** through the app's public deployment site, which needs the app's public network access Enabled. The files in the zip are first held against the digest that the deploy wrote as `PACKAGE_SHA256` (`tools/package-digest.py`; CRLF is read as LF); a package that differs is not published.
- **`DRIFT_ACCEPTED_EXEMPTIONS` and `DRIFT_ACCEPTED_DENY` are optional:** absent is empty, as on GitHub. Every other name has to be in the file.
- **The run number** is a counter in `hub-local.state.json`; only a change of Azure uses up a number.

## What the Operator steps need

The checks that run in the Operator (the health wait and the others) make a container group with the owner's own rights: Container Instances registered, and the right to create it, join the Operator's subnet and use its identity.

## Not supported

Anything that needs a GitHub OpenID Connect token: the publish of the cases through the Operator, and the probe's check that the deploy identity signs in (`operator-probe` goes on without it and says so). A step that is not `run`, `actions/checkout`, `actions/setup-python` or `azure/login` stops the plan.

## What Git's bash on Windows breaks

| What breaks | What the tool does |
|---|---|
| CRLF line ends of the checkout | The workflow is read as LF and every script is written with LF |
| Bash rewrites an argument that looks like a path (`/subscriptions/...`) | `MSYS_NO_PATHCONV=1`, `MSYS2_ARG_CONV_EXCL=*`; the package build gets the conversion back: its script wants a leading slash |
| `python3` is the Store alias; a native Python cannot start `az`; `az.cmd` mangles `&` and quotes | A `python3` shim; the CLI runs through its own `python.exe`, and `az login`, `logout`, `account set` and `config set` are refused |
| `taskkill /T` misses what Git's bash started | Every step runs in a Windows job object that ends all of it |
| The system's text encoding, block-buffered pipes | UTF-8 and unbuffered output |

## The way back

Deploying from GitHub again takes the owner's word: rule 18 and the test of `tools/hubguard.py` change together.
