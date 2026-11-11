#!/usr/bin/env python3
"""Whether a run of the Hub started this process: the one test that the tools which change Azure from the runner share (standard library only).

    python tools/hubguard.py        says yes or no; at a terminal it also says what is missing (the exit code is 0 for yes and 2 for no)

The Hub is the GitHub workflow .github/workflows/deploy-hub.yml (AGENTS.md rule 18). Its tools (az-deploy.py create, retire-old.py, cases-move.py, aigateway-prep.py and operator-run.py) used to take
GITHUB_ACTIONS=true as the proof that the Hub started them, and any process on a machine can set that variable: a stray call would have changed Azure outside the workflow. A process was started by the Hub
when it is on a real GitHub runner: GITHUB_ACTIONS is true, and the run id (GITHUB_RUN_ID), the repository (GITHUB_REPOSITORY) and the address of an OpenID Connect token request
(ACTIONS_ID_TOKEN_REQUEST_URL) are set. The Hub's job has the permission id-token: write, so every one of its steps has the address.

A refusal says only that the call was not started by a run of the Hub, so that a process that reads it learns nothing to copy. This command says more to a person at a terminal.

What this stops: an accident, and a stray call (a script, a copied command line, a coding agent) that sets GITHUB_ACTIONS=true and nothing more. It is a tripwire and not a lock: a process that sets all four
variables passes. The lock is the workflow's own: it starts only by hand, as the owner's account, on main (tools/workflow-lint.py fails a change that would make it start any other way). The tools that run
inside the Operator's container group do not use this test: the container is given GITHUB_ACTIONS=true and nothing else of the run, and the services that they reach are private.
"""
from __future__ import annotations

import os
import sys

RUNNER_VARIABLES = ("GITHUB_RUN_ID", "GITHUB_REPOSITORY", "ACTIONS_ID_TOKEN_REQUEST_URL")
SCOPE_VARIABLES = ("ENV_SUBSCRIPTION_ID", "ENV_RESOURCE_GROUP")
# What a tool says when it refuses: nothing of what counts as a run of the Hub.
REFUSAL = "this call was not started by a run of the Hub"


def what_is_missing(environ=None) -> str:
    """'' when a run of the Hub started this process; else a sentence that says what is missing. Only a person who asks is told it (python tools/hubguard.py at a terminal): a tool refuses with REFUSAL."""
    env = os.environ if environ is None else environ
    if env.get("GITHUB_ACTIONS") != "true":
        return "GITHUB_ACTIONS is not true: only a run of the Hub workflow on a GitHub runner started this"
    unset = [name for name in RUNNER_VARIABLES if not env.get(name)]
    if unset:
        return f"GITHUB_ACTIONS=true alone is no proof: this is no GitHub runner ({', '.join(unset)} not set)"
    return ""


def started_by_the_hub(environ=None) -> bool:
    return not what_is_missing(environ)


def refusal(environ=None) -> str:
    """'' when a run of the Hub started this process; else REFUSAL, which says nothing of what is missing, so that whoever reads it learns nothing to copy."""
    return "" if started_by_the_hub(environ) else REFUSAL


def other_scope(subscription: str, resource_group: str, environ=None) -> str:
    """'' when the subscription and the resource group are the project's own, the settings that the workflow gives every step; else why not. Nothing is printed of what was given or of the settings."""
    env = os.environ if environ is None else environ
    wanted_subscription, wanted_group = (env.get(name) or "" for name in SCOPE_VARIABLES)
    if not wanted_subscription or not wanted_group:
        return "the project's own subscription and resource group are not both set for this call: this command names no other group"
    if (subscription or "").lower() != wanted_subscription.lower() or (resource_group or "") != wanted_group:
        return "the subscription or the resource group is not the project's own: this command names no other group"
    return ""


def in_the_project(resource_id: str, environ=None) -> bool:
    """Whether the id of a resource names the project's own subscription and resource group (an id has no case)."""
    env = os.environ if environ is None else environ
    wanted_subscription, wanted_group = (env.get(name) or "" for name in SCOPE_VARIABLES)
    if not wanted_subscription or not wanted_group:
        return False
    return str(resource_id or "").lower().startswith(f"/subscriptions/{wanted_subscription}/resourcegroups/{wanted_group}/providers/".lower())


def main(argv=None, environ=None, out=None, person=None) -> int:
    """The answer, to a person at a terminal with what is missing, and to anything else with REFUSAL only."""
    why = what_is_missing(environ)
    if person is None:
        try:
            person = out is None and sys.stdout.isatty() and sys.stdin.isatty()
        except (AttributeError, ValueError):
            person = False
    print("yes: a run of the Hub started this process" if not why else f"no: {why if person else REFUSAL}", file=out if out is not None else sys.stdout)
    return 2 if why else 0


if __name__ == "__main__":
    sys.exit(main())
