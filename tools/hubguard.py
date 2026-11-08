#!/usr/bin/env python3
"""Whether a run of the Hub started this process: the one test that the tools which change Azure from the runner share (standard library only).

    python tools/hubguard.py        prints yes, or what is missing; the exit code is 0 for yes and 2 for no

Since 2026-11-08 the Hub is run by tools/hub-local.py on the owner's machine. Its tools (az-deploy.py create, retire-old.py, cases-move.py, aigateway-prep.py and operator-run.py) used to take
GITHUB_ACTIONS=true as the proof that the Hub started them, and any process on the machine can set that variable: a stray call would have skipped every guard that only the local Hub has
(--yes, a clean working tree, one run at a time, the record). A process was started by the Hub when one of these holds:

  1. It is on a real GitHub runner: GITHUB_ACTIONS is true, and the run id (GITHUB_RUN_ID), the repository (GITHUB_REPOSITORY) and the address of an OpenID Connect token request
     (ACTIONS_ID_TOKEN_REQUEST_URL) are set. The Hub's job has the permission id-token: write, so every one of its steps has the address.
  2. METERNAUT_HUB_PROOF names the proof file of a run of tools/hub-local.py that is alive. The run makes <local>/rt/<run>/hub-proof before its first step, with a random token in it, and
     writes its number and the SHA-256 of the token into its lock, <local>/hub-local.lock. It deletes the file when it ends, after a failure and after Ctrl+C too. The proof counts while the
     process that holds the lock is alive, the number in the lock is the number of the proof's folder, and the file holds the token.

What this stops: an accident, and a stray call (a script, a copied command line, a coding agent) that sets GITHUB_ACTIONS=true and nothing more. What it does not stop: a process that holds the
owner's az session, which can call az itself, or a process that reads the proof file of a run that is alive and uses it. The tools that run inside the Operator's container group do not use this
file: the container has no run lock to compare with, and the services that they reach are private.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

PROOF_VARIABLE = "METERNAUT_HUB_PROOF"
PROOF_NAME = "hub-proof"
LOCK_NAME = "hub-local.lock"
TEMP_NAME = "rt"
RUNNER_VARIABLES = ("GITHUB_RUN_ID", "GITHUB_REPOSITORY", "ACTIONS_ID_TOKEN_REQUEST_URL")
SCOPE_VARIABLES = ("ENV_SUBSCRIPTION_ID", "ENV_RESOURCE_GROUP")


def process_alive(pid) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return kernel32.GetLastError() == 5
        try:
            code = ctypes.c_ulong()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def digest_of(token: str) -> str:
    """What the lock of a run holds of its token: the lock is read in the open, so the token itself is not in it."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def proof_problem(proof: str, alive=process_alive) -> str:
    """'' when the path is the proof file of a run that is alive; else what is wrong with it."""
    try:
        path = Path(proof).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return f"{PROOF_VARIABLE} names no file that is there (a run of the Hub deletes its proof when it ends)"
    folder = path.parent
    if path.name != PROOF_NAME or folder.parent.name != TEMP_NAME or not path.is_file():
        return f"{PROOF_VARIABLE} does not name the proof file of a run of tools/hub-local.py (<local>/{TEMP_NAME}/<run>/{PROOF_NAME})"
    try:
        held = json.loads((folder.parent.parent / LOCK_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        held = None
    if not isinstance(held, dict):
        return f"no run lock {LOCK_NAME} is next to the folder {TEMP_NAME}: no run of the Hub is going on there"
    if not alive(held.get("pid")):
        return f"the run that holds the lock {LOCK_NAME} (process {held.get('pid')}) is not alive: this proof is stale"
    if str(held.get("run")) != folder.name:
        return "the proof is not the proof of the run that holds the lock"
    try:
        token = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "the proof file cannot be read"
    if not token or not hmac.compare_digest(digest_of(token).encode("ascii"), str(held.get("proof") or "").encode("utf-8", "replace")):
        return "the proof file does not hold the token of the run that holds the lock"
    return ""


def what_is_missing(environ=None, alive=process_alive) -> str:
    """'' when a run of the Hub started this process; else a sentence that says what is missing."""
    env = os.environ if environ is None else environ
    unset = [name for name in RUNNER_VARIABLES if not env.get(name)]
    on_actions = env.get("GITHUB_ACTIONS") == "true"
    if on_actions and not unset:
        return ""
    proof = env.get(PROOF_VARIABLE) or ""
    if proof:
        return proof_problem(proof, alive)
    if on_actions:
        return (f"GITHUB_ACTIONS=true alone is no proof: this is no GitHub runner ({', '.join(unset)} not set), and {PROOF_VARIABLE} is not set, "
                "so no run of tools/hub-local.py started it")
    return f"GITHUB_ACTIONS is not true and {PROOF_VARIABLE} is not set: neither a GitHub runner nor a run of tools/hub-local.py started this"


def started_by_the_hub(environ=None, alive=process_alive) -> bool:
    return not what_is_missing(environ, alive)


def other_scope(subscription: str, resource_group: str, environ=None) -> str:
    """'' when the subscription and the resource group are the project's own, the settings that the workflow gives every step; else why not. Nothing is printed of them."""
    env = os.environ if environ is None else environ
    wanted_subscription, wanted_group = (env.get(name) or "" for name in SCOPE_VARIABLES)
    if not wanted_subscription or not wanted_group:
        return f"{' and '.join(SCOPE_VARIABLES)}, the project's own settings that the workflow gives every step, are not both set"
    if (subscription or "").lower() != wanted_subscription.lower() or (resource_group or "") != wanted_group:
        return f"the subscription or the resource group is not the project's own ({' and '.join(SCOPE_VARIABLES)}): this command names no other group"
    return ""


def main(argv=None, environ=None, out=None) -> int:
    why = what_is_missing(environ)
    print("yes: a run of the Hub started this process" if not why else f"no: {why}", file=out or sys.stdout)
    return 2 if why else 0


if __name__ == "__main__":
    sys.exit(main())
