"""The environment of a run of the Hub, for the tests of the tools that only a run of the Hub may start (tools/hubguard.py).

Only the proof file of a run of tools/hub-local.py counts: a file in a local folder, a lock there whose process is alive and started when the lock says, and the two variables that name them. What a
GitHub runner sets (RUNNER, here only to be refused) is no proof. So a test that wants a tool to run takes its environment from inside(): a REAL proof, made once for this process in a local folder of
its own, of a run that is alive (this process). The guard is neither patched nor weakened. A test that wants a refusal takes its environment from outside(), or makes the proof that it needs with
make_proof() and proof_environment(): a stale one, one of another run, one in another folder."""
import atexit
import contextlib
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

_spec = importlib.util.spec_from_file_location("hubguard_of_the_test_helper", Path(__file__).resolve().parents[1] / "hubguard.py")
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

# What a GitHub runner sets, and what the guard used to take as the proof of one. It proves nothing now: a test that wants a refusal uses it.
RUNNER = {"GITHUB_ACTIONS": "true", "GITHUB_RUN_ID": "1234567890", "GITHUB_REPOSITORY": "someone/some-repository", "ACTIONS_ID_TOKEN_REQUEST_URL": "https://actions.example.invalid/token"}
NAMES = (*RUNNER, "METERNAUT_HUB_PROOF", "METERNAUT_LOCAL")
_OWN: dict = {}


def own_proof() -> dict:
    """The two variables of the proof of a run that is alive for as long as this process is (it is that run): made in a local folder of its own the first time it is asked for, deleted when the process ends."""
    if not _OWN:
        folder = Path(tempfile.mkdtemp(prefix="hubenv-"))
        atexit.register(shutil.rmtree, str(folder), ignore_errors=True)
        _OWN.update(proof_environment(folder))
    return dict(_OWN)


def inside(extra=None) -> dict:
    """A new environment of a run of the Hub: the real proof of this process's own run, and what the caller adds."""
    return {**own_proof(), **(extra or {})}


def outside(environ=None) -> dict:
    """The same environment without any of the variables that say 'a run of the Hub', and without those that a GitHub runner sets: for the tests of a refusal."""
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


def make_proof(folder, *, pid=None, run="1762000000", token="a-token-of-the-tests", lock=True, start=None) -> Path:
    """The proof file of a run of tools/hub-local.py and the lock that goes with it, as that tool makes them in <folder>, a local folder of the test's own: the path of the proof file.
    The run is alive (this process, with its real start time) unless a pid is given, and then its start time is unknown unless one is given."""
    folder = Path(folder)
    run_folder = folder / "rt" / run
    run_folder.mkdir(parents=True, exist_ok=True)
    proof = run_folder / "hub-proof"
    proof.write_text(token, encoding="utf-8", newline="")
    if lock:
        if start is None:
            start = guard.process_started(os.getpid()) if pid is None else guard.UNKNOWN
        held = {"pid": os.getpid() if pid is None else pid, "action": "what-if", "started": "2026-11-08T00:00:00Z", "processStart": start, "run": run,
                "proof": hashlib.sha256(token.encode("utf-8")).hexdigest()}
        (folder / "hub-local.lock").write_text(json.dumps(held), encoding="utf-8", newline="\n")
    return proof


def proof_environment(folder, **kwargs) -> dict:
    """What a step of a run of the local Hub has of the proof: the variable that names the file, and the one that names the repository's own local folder (a test has no repository of its own)."""
    return {"METERNAUT_HUB_PROOF": str(make_proof(folder, **kwargs)), "METERNAUT_LOCAL": str(folder)}
