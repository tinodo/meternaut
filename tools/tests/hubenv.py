"""The environment of a run of the Hub, for the tests of the tools that only a run of the Hub may start (tools/hubguard.py).

A tool of that kind refuses unless GitHub's own variables of a runner are all there, or a proof file of a run of tools/hub-local.py is. GITHUB_ACTIONS=true alone is refused, so a test that
wants the tool to run takes its environment from here, and a test that wants a refusal takes it from outside(): the machine that runs the tests may itself be a GitHub runner, which has the
variables, so the refusal clears them all."""
import contextlib
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

RUNNER = {"GITHUB_ACTIONS": "true", "GITHUB_RUN_ID": "1234567890", "GITHUB_REPOSITORY": "someone/some-repository", "ACTIONS_ID_TOKEN_REQUEST_URL": "https://actions.example.invalid/token"}
NAMES = (*RUNNER, "METERNAUT_HUB_PROOF")


def inside(extra=None) -> dict:
    """A new environment of a run of the Hub: what a real runner sets, and what the caller adds."""
    return {**RUNNER, **(extra or {})}


def outside(environ=None) -> dict:
    """The same environment without any of the variables that say 'a run of the Hub': for the tests of a refusal."""
    return {key: value for key, value in (environ or {}).items() if key not in NAMES}


@contextlib.contextmanager
def patched(is_the_hub=True, extra=None):
    """os.environ for the length of a block: a run of the Hub (the default) or not, and what the caller adds. Everything else in it stays; it is put back at the end."""
    with mock.patch.dict(os.environ, {}, clear=False):
        for name in NAMES:
            os.environ.pop(name, None)
        os.environ.update(inside() if is_the_hub else {})
        os.environ.update(extra or {})
        yield


def dead_pid() -> int:
    """The number of a process that has ended."""
    done = subprocess.Popen([sys.executable, "-c", "pass"])
    done.wait()
    return done.pid


def make_proof(folder, *, pid=None, run="1762000000", token="a-token-of-the-tests", lock=True) -> Path:
    """The proof file of a run of tools/hub-local.py and the lock that goes with it, as that tool makes them in <folder>, a local folder of the test's own: the path of the proof file.
    The run is alive (this process) unless a pid is given."""
    folder = Path(folder)
    run_folder = folder / "rt" / run
    run_folder.mkdir(parents=True, exist_ok=True)
    proof = run_folder / "hub-proof"
    proof.write_text(token, encoding="utf-8", newline="")
    if lock:
        held = {"pid": os.getpid() if pid is None else pid, "action": "what-if", "started": "2026-11-08T00:00:00Z", "run": run, "proof": hashlib.sha256(token.encode("utf-8")).hexdigest()}
        (folder / "hub-local.lock").write_text(json.dumps(held), encoding="utf-8", newline="\n")
    return proof
