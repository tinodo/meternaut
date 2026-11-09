#!/usr/bin/env python3
"""Whether a run of the Hub started this process: the one test that the tools which change Azure from the runner share (standard library only).

    python tools/hubguard.py        says yes or no; at a terminal it also says what is missing (the exit code is 0 for yes and 2 for no)

Since 2026-11-08 the Hub is run by tools/hub-local.py on the owner's machine. Its tools (az-deploy.py create, retire-old.py, cases-move.py, aigateway-prep.py and operator-run.py) used to take
GITHUB_ACTIONS=true as the proof that the Hub started them, and any process on the machine can set that variable: a stray call would have skipped every guard that only the local Hub has
(--yes, a clean working tree, one run at a time, the record). A process was started by the Hub when one of these holds:

  1. It is on a real GitHub runner: GITHUB_ACTIONS is true, and the run id (GITHUB_RUN_ID), the repository (GITHUB_REPOSITORY) and the address of an OpenID Connect token request
     (ACTIONS_ID_TOKEN_REQUEST_URL) are set. The Hub's job has the permission id-token: write, so every one of its steps has the address.
  2. METERNAUT_HUB_PROOF names the proof file of a run of tools/hub-local.py that is alive. The run makes <local>/rt/<run>/hub-proof before its first step, with a random token in it, and
     writes into its lock, <local>/hub-local.lock, its number, the SHA-256 of the token and the start time of its process. It deletes the file when it ends, after a failure and after Ctrl+C
     too. <local> is the repository's own local/ folder, found the way that tools/hub-local.py finds it (the main working tree's local/, or the folder that METERNAUT_LOCAL names), and never
     from the path that the caller gives: a file anywhere else is refused, whatever sits next to it. The proof counts while the process that holds the lock is alive and started when the lock
     says (so a process number that was used again does not pass), the number in the lock is the number of the proof's folder, and the file holds the token.

A refusal says only that the call was not started by a run of the Hub, so that a process that reads it learns nothing to copy. This command says more to a person at a terminal.

What this stops: an accident, and a stray call (a script, a copied command line, a coding agent) that sets GITHUB_ACTIONS=true and nothing more. It is a tripwire and not a lock. What it does not
stop: a process that holds the owner's az session, which can call az itself, or a process that reads this file and the proof file of a run that is alive and uses them. The tools that run inside
the Operator's container group do not use it: the container has no run lock to compare with, and the services that they reach are private.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path

PROOF_VARIABLE = "METERNAUT_HUB_PROOF"
LOCAL_VARIABLE = "METERNAUT_LOCAL"
PROOF_NAME = "hub-proof"
LOCK_NAME = "hub-local.lock"
TEMP_NAME = "rt"
RUNNER_VARIABLES = ("GITHUB_RUN_ID", "GITHUB_REPOSITORY", "ACTIONS_ID_TOKEN_REQUEST_URL")
SCOPE_VARIABLES = ("ENV_SUBSCRIPTION_ID", "ENV_RESOURCE_GROUP")
UNKNOWN = "unknown"
# What a tool says when it refuses: nothing of what counts as a run of the Hub.
REFUSAL = "this call was not started by a run of the Hub"


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


def linux_start(stat_text: str, boot_id: str) -> str:
    """What /proc/<pid>/stat says of the start of a process (its 22nd field, in ticks since the machine booted), with the machine's boot id, so that the same number after a reboot is another start."""
    after = stat_text[stat_text.rindex(")") + 2:].split()
    return f"{boot_id.strip()}:{int(after[19])}"


def started_on_windows(pid: int) -> str:
    import ctypes
    from ctypes import wintypes
    pointer = ctypes.POINTER(wintypes.FILETIME)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = (wintypes.HANDLE, pointer, pointer, pointer, pointer)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return UNKNOWN
    try:
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        if not kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
            return UNKNOWN
        return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
    finally:
        kernel32.CloseHandle(handle)


def started_by_ps(pid: int) -> str:
    done = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL, env={**os.environ, "LC_ALL": "C", "LANG": "C"})
    text = " ".join(done.stdout.split())
    return text if done.returncode == 0 and text else UNKNOWN


def process_started(pid) -> str:
    """A text that names the moment when the process with this number started: the same text each time it is asked while the process lives, and another one for a process that is given the number
    later. UNKNOWN when the platform does not say (the check that compares it is then no weaker than the one that asks only whether the number is alive)."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return UNKNOWN
    try:
        if os.name == "nt":
            return started_on_windows(pid)
        if sys.platform.startswith("linux"):
            try:
                return linux_start(Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace"), Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8"))
            except (OSError, ValueError, IndexError):
                pass
        return started_by_ps(pid)
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        return UNKNOWN


def run_git(args: list, cwd) -> tuple:
    """(exit code, standard output, standard error) of one git command. Only reads are asked of it here and in tools/hub-local.py."""
    try:
        done = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    except OSError as error:
        return 127, "", str(error)
    return done.returncode, done.stdout, done.stderr


class NoLocalFolder(Exception):
    """Git cannot say where the main working tree is, and METERNAUT_LOCAL names no folder."""


def local_folder(environ=None, cwd=None, git=None) -> Path:
    """The git-ignored local/ folder of the repository's MAIN working tree, or the folder that METERNAUT_LOCAL names (a blank value is no value).

    A worktree has no local/ of its own: it is the parent of the common git directory that holds it, and every worktree finds the same configuration, counter, lock and records there. tools/hub-local.py
    finds the folder with this function, and so do the tools that look for the proof of a run in it: from the repository that holds this file (cwd is the folder of this file when none is given)."""
    env = os.environ if environ is None else environ
    override = (env.get(LOCAL_VARIABLE) or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    cwd = Path(cwd) if cwd is not None else Path(__file__).resolve().parent
    git = git or run_git
    code, out, _ = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd)
    if code != 0:
        code, out, _ = git(["rev-parse", "--git-common-dir"], cwd)
    if code != 0 or not out.strip():
        raise NoLocalFolder(f"git could not say where the main working tree of this repository is. Set {LOCAL_VARIABLE} to the folder that holds hub-local.env")
    common = Path(out.strip())
    if not common.is_absolute():
        common = (cwd / common).resolve()
    if common.name != ".git":
        raise NoLocalFolder(f"the git directory {common} is not the .git folder of a working tree. Set {LOCAL_VARIABLE} to the folder that holds hub-local.env")
    return common.parent / "local"


def digest_of(token: str) -> str:
    """What the lock of a run holds of its token: the lock is read in the open, so the token itself is not in it."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def proof_problem(proof: str, local, alive=process_alive, started=process_started) -> str:
    """'' when the path is the proof file of a run that is alive, in the folder rt of the repository's own local folder; else what is wrong with it. Everything that is read is read from that folder:
    nothing of what sits next to the file that the caller names counts."""
    if local is None:
        return f"the repository's own local folder cannot be found (git does not say where the main working tree is, and {LOCAL_VARIABLE} names no folder)"
    try:
        path = Path(proof).resolve(strict=True)
        runs = (Path(local) / TEMP_NAME).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return f"{PROOF_VARIABLE} names no file that is there, or the folder {TEMP_NAME} of the repository's own local folder is not (a run of the Hub deletes its proof when it ends)"
    try:
        inside = path.name == PROOF_NAME and path.is_file() and path.parent.parent.samefile(runs)
    except OSError:
        inside = False
    if not inside:
        return f"{PROOF_VARIABLE} is not the proof file of a run in the repository's own local folder ({TEMP_NAME}/<run>/{PROOF_NAME})"
    try:
        held = json.loads((Path(local) / LOCK_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        held = None
    if not isinstance(held, dict):
        return f"no run lock {LOCK_NAME} is in the repository's own local folder: no run of the Hub is going on"
    pid = held.get("pid")
    if not alive(pid):
        return f"the run that holds the lock {LOCK_NAME} (process {pid}) is not alive: this proof is stale"
    since = held.get("processStart")
    if isinstance(since, str) and since and since != UNKNOWN:
        now = started(pid)
        if now != UNKNOWN and now != since:
            return f"the process {pid} did not start when the lock says: its number was used again, and this proof is stale"
    if str(held.get("run")) != path.parent.name:
        return "the proof is not the proof of the run that holds the lock"
    try:
        token = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "the proof file cannot be read"
    if not token or not hmac.compare_digest(digest_of(token).encode("ascii"), str(held.get("proof") or "").encode("utf-8", "replace")):
        return "the proof file does not hold the token of the run that holds the lock"
    return ""


def what_is_missing(environ=None, *, alive=process_alive, started=process_started, git=None) -> str:
    """'' when a run of the Hub started this process; else a sentence that says what is missing. Only a person who asks is told it (python tools/hubguard.py at a terminal): a tool refuses with REFUSAL."""
    env = os.environ if environ is None else environ
    unset = [name for name in RUNNER_VARIABLES if not env.get(name)]
    on_actions = env.get("GITHUB_ACTIONS") == "true"
    if on_actions and not unset:
        return ""
    proof = env.get(PROOF_VARIABLE) or ""
    if proof:
        try:
            local = local_folder(env, None, git)
        except NoLocalFolder:
            local = None
        return proof_problem(proof, local, alive, started)
    if on_actions:
        return (f"GITHUB_ACTIONS=true alone is no proof: this is no GitHub runner ({', '.join(unset)} not set), and {PROOF_VARIABLE} is not set, "
                "so no run of tools/hub-local.py started it")
    return f"GITHUB_ACTIONS is not true and {PROOF_VARIABLE} is not set: neither a GitHub runner nor a run of tools/hub-local.py started this"


def started_by_the_hub(environ=None, **injected) -> bool:
    return not what_is_missing(environ, **injected)


def refusal(environ=None, **injected) -> str:
    """'' when a run of the Hub started this process; else REFUSAL, which says nothing of what is missing, so that whoever reads it learns nothing to copy."""
    return "" if started_by_the_hub(environ, **injected) else REFUSAL


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
