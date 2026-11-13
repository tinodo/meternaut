"""The console: the HTTP front of the pages. It builds what the pages need from the settings, refuses unless the platform's sign-in is on, and hands the request on.

The platform's built-in sign-in (Microsoft Entra, with a federated credential and no secret) stands in front of every route but /healthz, and it adds the
headers that say who the person is. If it is not on, those headers could be made up by anybody, so the app refuses every request (503) and serves nothing
but /healthz. The pages themselves are in the web package; nothing here makes a page. A change is made with the approving person's own token (delegated.py):
this module wires the client that goes with it, and the reader that looks at a resource before a page offers Approve (precheck.py: the app's own identity and a list of calls that holds reads
only). The app holds no right of its own to change Azure.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Callable, Mapping

from . import config as cfg
from . import delegated, drift, learning, loop_config, offers, people as people_mod, precheck, runner, web, wiring
from .approvals import Approvals
from .events import History
from .families import registry
from .families.azure import Azure
from .http import Client, default_transport
from .identity import Identity
from .memory_store import utc_now
from .redact import Redactor
from .runner import RunnerServices

LOG = logging.getLogger("meternaut.console")
AUTH_FLAG = "WEBSITE_AUTH_ENABLED"
_RUNTIME: dict[str, object] = {}


def sign_in_is_on(env: Mapping[str, str]) -> bool:
    return (env.get(AUTH_FLAG) or "").strip().lower() == "true"


def build_services(env: Mapping[str, str], *, transport=default_transport, sleep=time.sleep, monotonic=time.monotonic, clock=utc_now, fetch=None) -> "web.Services":
    """The pages' services from the settings. Raises when the loop or the people are not set up: a console without them serves nothing."""
    settings = loop_config.load(env)
    if settings is None:
        raise loop_config.LoopConfigError("the loop is not configured")
    people = people_mod.load(env)
    redact = Redactor()
    options = {"sleep": sleep, **({"fetch": fetch} if fetch else {})}
    identity = Identity(env, **options)
    store = wiring.build_store(settings, identity.token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
    approval = wiring.approval_settings(settings)
    approvals = Approvals(store, approval, clock)
    watch = cfg.load(env)
    acts_on = registry.acts_on(settings.planted_tag, settings.change_scopes)
    history = History(uuid.uuid4().hex, None, clock, redact)
    signin = delegated.settings_of(settings)
    change_client = Client(runner.change_calls(settings.change_scopes), redact, transport=transport, sleep=sleep, monotonic=monotonic)

    def run(token: str) -> RunnerServices:
        # The person's own token, for the one request that makes the change: nothing keeps it.
        return RunnerServices(store, change_client, lambda resource: token, approval, clock=clock, sleep=sleep, emit=history.emit)

    if signin is None:
        def redeem(code: str, verifier: str) -> delegated.Tokens:
            raise delegated.SigninError("Signing in to Azure is not set up here. Nothing is approved.")
    else:
        redeem = delegated.TokenClient(signin, Identity({**env, "AZURE_CLIENT_ID": signin.assertion_client_id}, **options).token,
                                       Client(delegated.token_calls(signin), redact, transport=transport, sleep=sleep, monotonic=monotonic)).redeem
    delegate = delegated.Delegation(store, approvals, signin, redeem, run, emit=history.emit)
    reader_calls = runner.read_calls(settings.change_scopes)

    def look() -> Azure:
        # The reader of one look at a resource before a page offers Approve (cases/precheck.py): the app's own identity, and a list of calls that holds reads only, in the resource groups of the
        # change scopes. Each look has a client of its own, with a deadline, because a page waits for it. The page gains no right to change anything.
        reader = Client(reader_calls, redact, transport=transport, sleep=sleep, monotonic=monotonic)
        reader.deadline = monotonic() + precheck.LOOK_SECONDS
        return Azure(reader, identity.token)

    checker = precheck.Precheck(store, approval, look, clock)
    # The models that wrote anything on a page: the older roles, and the agents of the investigation when it is on (each name once).
    written_by = (watch.model_detective, watch.model_skeptic) + ((watch.foundry_model_investigator, watch.foundry_model_skeptic) if watch.investigate else ())

    def drift_now(by: str, started_at: str) -> object:
        # The timer's check, started by a person: the same reads, rules and lines (cases/drift.py), with the time that the console claimed for it.
        return drift.run_check("console", env, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock, fetch=fetch, by=by, started_at=started_at)

    return web.Services(store=store, decider=approvals, delegate=delegate, people=people, now=clock, host=settings.console_host, acts_on=acts_on,
                        models=tuple(dict.fromkeys(written_by)), drift=drift_now, lessons=lambda: learning.replay_text(store), checker=checker,
                        teams=lambda: offers.teams_status(settings, store, people, clock()))


def services(env: Mapping[str, str], **options) -> "web.Services":
    """One set of services for the life of the process: the token of the identity and the open connections are worth keeping."""
    if "services" not in _RUNTIME:
        _RUNTIME["services"] = build_services(env, **options)
    return _RUNTIME["services"]  # type: ignore[return-value]


def _plain(response_cls: Callable, status: int, text: str):
    return response_cls(body=text.encode("utf-8"), status_code=status, headers={
        "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'"})


def handle(req, response_cls: Callable, env: Mapping[str, str] | None = None, **options):
    """One request. `req` is what the platform hands over (method, url, headers, get_body); `response_cls` is how an answer is made. It never raises."""
    env = os.environ if env is None else env
    try:
        path = req.url.split("?", 1)[0].split("//", 1)[-1]
        path = "/" + path.split("/", 1)[1] if "/" in path else "/"
        if path == "/healthz":
            return _plain(response_cls, 200, "ok")
        if not sign_in_is_on(env):
            return _plain(response_cls, 503, "The sign-in is not set up, so nothing is served.")
        headers = {str(k).lower(): str(v) for k, v in req.headers.items()}
        request = web.parse_request(req.method, req.url, headers, req.get_body() or b"")
        answer = web.handle(request, services(env, **options))
        return response_cls(body=answer.body, status_code=answer.status, headers=dict(answer.headers))
    except Exception as error:  # noqa: BLE001 (a page that fails says nothing about why)
        LOG.error(Redactor()(f"the console failed: {type(error).__name__}: {error}"))
        return _plain(response_cls, 500, "Something went wrong. Nothing was changed.")
