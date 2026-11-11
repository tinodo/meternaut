"""The environment of a run of the Hub, for the tests of the tools that only a run of the Hub may start (tools/hubguard.py).

A tool of that kind refuses unless GitHub's own variables of a runner are all there. GITHUB_ACTIONS=true alone is refused, so a test that wants the tool to run takes its environment from here, and a
test that wants a refusal takes it from outside(): the machine that runs the tests may itself be a GitHub runner, which has the variables, so the refusal clears them all."""
import contextlib
import os
from unittest import mock

RUNNER = {"GITHUB_ACTIONS": "true", "GITHUB_RUN_ID": "1234567890", "GITHUB_REPOSITORY": "someone/some-repository", "ACTIONS_ID_TOKEN_REQUEST_URL": "https://actions.example.invalid/token"}
NAMES = tuple(RUNNER)


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
