"""The console: the HTTP front of the pages. It builds what the pages need from the settings, refuses unless the platform's sign-in is on, and hands the request on.

The platform's built-in sign-in (Microsoft Entra, with a federated credential and no secret) stands in front of every route but /healthz, and it adds the
headers that say who the person is. If it is not on, those headers could be made up by anybody, so the app refuses every request (503) and serves nothing
but /healthz. The pages themselves are in the web package; nothing here makes a page.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Callable, Mapping

from . import config as cfg
from . import loop_config, people as people_mod, web, wiring
from .approvals import Approvals
from .http import default_transport
from .identity import Identity
from .memory_store import utc_now
from .redact import Redactor

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
    identity = Identity(env, **({"fetch": fetch} if fetch else {}))
    store = wiring.build_store(settings, identity.token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
    approvals = Approvals(store, wiring.approval_settings(settings), clock)
    watch = cfg.load(env)
    writer = (f"delete an unattached managed disk or an unassigned public IP address that carries the tag {settings.planted_tag}, "
              f"in resource group {settings.writer_group} and nowhere else")
    return web.Services(store=store, decider=approvals, people=people, now=clock, host=settings.console_host, writer=writer,
                        models=(watch.model_detective, watch.model_skeptic))


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
