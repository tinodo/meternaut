"""The router: who is signed in, what is allowed, and which page answers.

A request is answered in this order: the health probe (no sign-in), the person (from the platform's sign-in headers, never from a form or a link), the checks
that every request shares (size, kind of form, where a POST came from), the route, the role that the route needs, and then the page.
"""
from __future__ import annotations

import logging
import re
from typing import Callable

from ..models import StoreError
from . import approval, history, home, notebook, notes, ops, settings
from .core import FORM_TYPE, ID, Ctx, Request, Response, Services, utc
from .layout import TEXT, denied, message_page, respond, secured

LOG = logging.getLogger("meternaut.web")
PRINCIPAL_HEADER = "x-ms-client-principal-id"
BACK = ("/", "Back to the decisions")

Handler = Callable[..., Response]
# method, path, handler, the roles of which a person needs one (none: any listed person)
ROUTES: tuple[tuple[str, str, Handler, tuple[str, ...]], ...] = (
    ("GET", "/", home.home, ()),
    ("GET", rf"/ok/(?P<plan_id>{ID})", approval.approval_page, ()),
    ("POST", rf"/ok/(?P<plan_id>{ID})", approval.approval_decide, ()),
    ("POST", rf"/ok/(?P<plan_id>{ID})/ask", approval.approval_ask, ()),
    ("POST", rf"/ok/(?P<plan_id>{ID})/not-mine", approval.approval_not_mine, ()),
    ("GET", "/arm/return", approval.arm_return, ()),
    ("GET", rf"/why/(?P<case_id>{ID})", notebook.notebook, ()),
    ("GET", "/history", history.history, ()),
    ("GET", "/me/decisions", history.history, ()),
    ("GET", "/me/activity", history.history, ()),
    ("GET", "/me/settings", settings.settings_page, ()),
    ("POST", "/me/settings", settings.settings_save, ()),
    ("POST", "/me/settings/export", settings.settings_export, ()),
    ("POST", "/me/settings/delete", settings.settings_delete, ()),
    ("GET", "/me/notes", notes.notes_page, ()),
    ("POST", "/me/notes", notes.notes_add, ()),
    ("POST", rf"/me/notes/(?P<note_id>{ID})/delete", notes.notes_delete, ()),
    ("GET", "/ops", ops.hub, ("ops",)),
    ("GET", "/ops/runs", ops.runs_page, ("ops",)),
    ("GET", "/ops/permissions", ops.permissions, ("ops", "owner")),
    ("POST", "/ops/pause", ops.pause_save, ("ops",)),
    ("GET", "/ops/pause", ops.pause_page, ("ops",)),
)
COMPILED = tuple((method, re.compile(pattern), handler, roles) for method, pattern, handler, roles in ROUTES)
# The one page that a GET changes something through (the return of the sign-in to Azure): a HEAD request (a prefetch, a link check) must not use it up.
NO_HEAD = frozenset({approval.arm_return})


def _path(raw: str, base: str) -> str | None:
    """The path below the base path (such as /api), without a closing slash. None when the path is not below the base or has an empty segment."""
    path = raw or "/"
    base = base.rstrip("/")
    if base:
        if path != base and not path.startswith(base + "/"):
            return None
        path = path[len(base):] or "/"
    if "//" in path:
        return None
    return path.rstrip("/") or "/"


def handle(request: Request, services: Services) -> Response:
    """Answers one request. It never raises: a fault is a plain page, and every response carries the security headers."""
    try:
        return secured(_handle(request, services))
    except StoreError as error:
        LOG.warning("console: the store failed (status %s)", error.status)
        return secured(_fault(request, services, 503, "I cannot reach my records", "Try again in a few minutes."))
    except Exception as error:  # noqa: BLE001 (a page must never show a trace)
        LOG.warning("console: %s", type(error).__name__)
        return secured(_fault(request, services, 500, "Something went wrong on my side", "Try again in a few minutes."))


def _fault(request: Request, services: Services, status: int, title: str, advice: str) -> Response:
    try:
        principal = services.people.principal(request.headers.get(PRINCIPAL_HEADER, "").strip())
        if principal is None:
            return denied()
        ctx = Ctx(request, services, principal, utc(services.now()))
        said = "Nothing has changed." if request.method in ("GET", "HEAD") else "Open the page again to see what was stored."
        return message_page(ctx, status, title, said, advice, back=BACK)
    except Exception:  # noqa: BLE001 (the last resort: a bare page)
        return respond(status, "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>Error</title></head><body><main><h1>Error</h1></main></body></html>")


def _handle(request: Request, services: Services) -> Response:
    method = request.method.upper()
    headers = {str(name).lower(): str(value) for name, value in request.headers.items()}
    path = _path(request.path, services.base)
    if path == "/healthz" and method in ("GET", "HEAD"):
        return respond(200, "" if method == "HEAD" else "ok", content_type=TEXT)
    principal = services.people.principal(headers.get(PRINCIPAL_HEADER, "").strip())
    if principal is None:
        return denied()
    ctx = Ctx(request, services, principal, utc(services.now()))
    if request.problem == "too_large":
        return message_page(ctx, 413, "The form is too large", "A form may hold at most 16 KB. Nothing was sent.", back=BACK)
    if request.problem:
        return message_page(ctx, 400, "The form cannot be read", "Nothing was sent.", back=BACK)
    if method not in ("GET", "HEAD", "POST"):
        refusal = message_page(ctx, 405, "This kind of request is not accepted", "Pages are opened with GET and answered with POST.", back=BACK)
        return Response(405, {**refusal.headers, "Allow": "GET, HEAD, POST"}, refusal.body)
    if method == "POST":
        if headers.get("sec-fetch-site", "same-origin") != "same-origin":
            return message_page(ctx, 403, "This form was not sent from this page", "Nothing was changed.", back=BACK)
        if headers.get("content-type", "").split(";")[0].strip().lower() != FORM_TYPE:
            return message_page(ctx, 415, "This form cannot be read", "Nothing was changed.", back=BACK)
    found = path is not None and [(m, rx.fullmatch(path), h, r) for m, rx, h, r in COMPILED if rx.fullmatch(path)]
    if not found:
        return message_page(ctx, 404, "I cannot find this page", "No page has this address. Nothing has changed.", back=BACK)
    wanted = "GET" if method == "HEAD" else method
    route = next(((match, handler, roles) for m, match, handler, roles in found if m == wanted and not (method == "HEAD" and handler in NO_HEAD)), None)
    if route is None:
        refusal = message_page(ctx, 405, "This page does not take that kind of request", "Nothing has changed.", back=BACK)
        head_ok = any(m == "GET" and handler not in NO_HEAD for m, _, handler, _ in found)
        allowed = sorted({m for m, *_ in found} | ({"HEAD"} if head_ok else set()))
        return Response(405, {**refusal.headers, "Allow": ", ".join(allowed)}, b"" if method == "HEAD" else refusal.body)
    match, handler, roles = route
    if roles and not any(principal.has(role) for role in roles):
        return message_page(ctx, 403, "You do not have the role that this page needs", f"This page is for people with the role {' or '.join(roles)}. Nothing has changed.",
                            back=BACK)
    response = handler(ctx, **match.groupdict())
    return Response(response.status, response.headers, b"") if method == "HEAD" else response
