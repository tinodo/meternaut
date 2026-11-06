"""The one place where the app makes an HTTPS call.

A call is made only to a fixed list of addresses with a fixed method, every one of them a read (two of the POSTs ask for a query result,
for the key of the gateway access product and for a completion): a call to anything else is refused before it leaves the app, so a
mistake in the code cannot become a write to Azure. Timeouts are set, and a failure that may pass is retried a bounded number of times.
The one exception is the Foundry project of the app: the app makes and reads its own agents there and makes and deletes its own conversations (foundry_calls).
"""
from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.client import HTTPException
from typing import Callable, Mapping
from urllib.parse import urlencode, urlsplit

ARM_HOST = "management.azure.com"
GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
# A subscription, a resource group of it, or one resource of it (a child resource has more name segments).
SCOPE = rf"/subscriptions/{GUID}(?:/resourceGroups/[A-Za-z0-9._()-]{{1,90}}(?:/providers/[A-Za-z0-9.]{{1,80}}(?:/[A-Za-z0-9._()~-]{{1,100}}){{2,16}})?)?"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
# The endpoint of one Microsoft Foundry project (the default project is called _project), the name of an agent in it and the id of a conversation of it.
FOUNDRY_ENDPOINT = re.compile(r"https://[a-z0-9][a-z0-9-]{0,62}[a-z0-9]\.services\.ai\.azure\.com/api/projects/[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}")
FOUNDRY_AGENT_NAME = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
FOUNDRY_CONVERSATION_ID = r"conv_[A-Za-z0-9_-]{1,100}"

Transport = Callable[[str, str, Mapping[str, str], "bytes | None", float], "tuple[int, Mapping[str, str], bytes]"]


class HttpError(Exception):
    """A call that failed. `status` is 0 when no answer arrived. The text never holds a header or a secret."""

    def __init__(self, status: int, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


class Refused(Exception):
    """A call that the app does not make: it is not on the list."""


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes

    def json(self) -> object:
        try:
            return json.loads(self.body.decode("utf-8")) if self.body else None
        except ValueError as error:
            raise HttpError(self.status, "the answer is not JSON") from error
        except RecursionError as error:
            raise HttpError(self.status, "the answer is nested too deeply to be read") from error


def foundry_calls(endpoint: str) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """The calls to one Foundry project. They make and read Meternaut's own agents there and make, use and delete its own conversations, and nothing else: no
    other host, no other project, no other method, and no DELETE of an agent. The patterns are exact (no case folding) and nothing may follow the names."""
    if not FOUNDRY_ENDPOINT.fullmatch(endpoint):
        raise ValueError("the endpoint of the Foundry project is not https://<account>.services.ai.azure.com/api/projects/<project>")
    base = re.escape(endpoint)
    return (
        ("GET", re.compile(base + rf"/agents/{FOUNDRY_AGENT_NAME}")),
        ("POST", re.compile(base + "/agents")),
        ("POST", re.compile(base + rf"/agents/{FOUNDRY_AGENT_NAME}/versions")),
        ("POST", re.compile(base + "/openai/v1/conversations")),
        ("POST", re.compile(base + "/openai/v1/responses")),
        ("DELETE", re.compile(base + rf"/openai/v1/conversations/{FOUNDRY_CONVERSATION_ID}")),
    )


def allowed_calls(gateway_host: str, key_path: str, foundry_endpoint: str | None = None) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """(method, address without its query) of every call that the app may make. `key_path` is the path of the one call that asks for the key.
    `foundry_endpoint` adds the calls of foundry_calls for that one project; without it the app makes none."""
    arm = re.escape(f"https://{ARM_HOST}")
    calls = (
        ("POST", re.compile(arm + r"/providers/Microsoft\.ResourceGraph/resources", re.I)),
        ("POST", re.compile(arm + rf"/subscriptions/{GUID}/providers/Microsoft\.CostManagement/query", re.I)),
        ("GET", re.compile(arm + rf"/subscriptions/{GUID}/providers/Microsoft\.Advisor/recommendations", re.I)),
        ("GET", re.compile(arm + rf"{SCOPE}/providers/Microsoft\.Authorization/locks", re.I)),
        ("GET", re.compile(arm + rf"{SCOPE}/providers/Microsoft\.Insights/metricDefinitions", re.I)),
        ("GET", re.compile(arm + rf"{SCOPE}/providers/Microsoft\.Insights/metrics", re.I)),
        ("GET", re.compile(arm + rf"/subscriptions/{GUID}/providers/Microsoft\.Security/pricings", re.I)),
        ("POST", re.compile(re.escape(f"https://{ARM_HOST}{key_path}"), re.I)),
        ("POST", re.compile(re.escape(f"https://{gateway_host}/models/chat/completions"), re.I)),
    )
    return calls if foundry_endpoint is None else calls + foundry_calls(foundry_endpoint)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A call goes to the address that was checked against the list. An answer that sends it somewhere else is not followed: urllib would send every header of the
    call, the authorization included, to the new address. The answer is the status of the redirect, like any other answer."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def default_transport(method: str, url: str, headers: Mapping[str, str], data: bytes | None, timeout: float) -> tuple[int, Mapping[str, str], bytes]:
    request = urllib.request.Request(url, data=data, headers=dict(headers), method=method)
    try:
        with _OPENER.open(request, timeout=timeout) as response:  # noqa: S310 (the address was checked against the list)
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as error:
        return error.code, {k.lower(): v for k, v in error.headers.items()}, error.read()


def retry_after(headers: Mapping[str, str]) -> float | None:
    """Seconds to wait, from Retry-After or a service's own header that ends in -retry-after (Cost Management has one)."""
    for name, value in headers.items():
        if name == "retry-after" or name.endswith("-retry-after"):
            try:
                return max(0.0, float(value))
            except ValueError:
                return None
    return None


def error_text(status: int, body: bytes, redact: Callable[[str], str]) -> str:
    """The code and the first words of the message of an error body; nothing else of the answer. A body that is not JSON gives its first 120 characters, and a JSON
    body that is nested too deeply to be parsed gives a fixed text."""
    text = ""
    try:
        document = json.loads(body.decode("utf-8", "replace"))
        error = document.get("error") if isinstance(document, dict) else None
        if isinstance(error, dict):
            text = f"{error.get('code', '')}: {str(error.get('message', ''))[:200]}".strip(": ")
        elif isinstance(error, str):
            # An OAuth error of Microsoft Entra: the error and its AADSTS code, and not the description (it holds ids and a trace).
            codes = re.findall(r"AADSTS\d{3,7}", str(document.get("error_description", "")))
            text = f"{error[:60]} {codes[0] if codes else ''}".strip()
        elif isinstance(document, dict):
            text = str(document.get("message") or document.get("statusCode") or "")[:200]
    except RecursionError:
        text = "the body is nested too deeply to be read"
    except ValueError:
        text = body.decode("utf-8", "replace")[:120]
    return redact(f"{status} {' '.join(text.split())}".strip())


class Client:
    """Makes the calls of the list. `deadline` is an absolute time on the `monotonic` clock: no call starts after it, no timeout reaches past it and no
    pause is taken that would end after it."""

    def __init__(self, allowed: tuple[tuple[str, "re.Pattern[str]"], ...], redact: Callable[[str], str], *, transport: Transport = default_transport,
                 sleep: Callable[[float], None] = time.sleep, jitter: Callable[[], float] = random.random,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self.allowed, self.redact, self.transport, self.sleep, self.jitter, self.monotonic = allowed, redact, transport, sleep, jitter, monotonic
        self.deadline: float | None = None

    def check(self, method: str, url: str) -> None:
        parts = urlsplit(url)
        bare = f"{parts.scheme}://{parts.netloc}{parts.path}"
        if parts.scheme != "https" or not any(m == method and pattern.fullmatch(bare) for m, pattern in self.allowed):
            raise Refused(f"the app makes no {method} call to {parts.netloc}{parts.path[:80]}")

    def remaining(self) -> float | None:
        return None if self.deadline is None else self.deadline - self.monotonic()

    def request(self, method: str, url: str, *, headers: Mapping[str, str] | None = None, body: object = None, form: Mapping[str, str] | None = None,
                timeout: float = 30, retries: int = 2, retry_after_max: float = 60, retry_statuses: frozenset[int] = RETRY_STATUSES,
                retry_network: bool = True, backoff: float = 1.0, backoff_max: float = 30.0) -> Response:
        """One call. A call that may already have been carried out (a model call whose answer did not arrive) is made with retry_network=False.

        `body` is sent as JSON, `form` as a form (the token endpoint of Microsoft Entra takes a form). A call has one of them or none.

        A call that is retried waits as long as the service says (Retry-After, up to `retry_after_max`). When the service says nothing the pause is `backoff` seconds
        (with jitter) before the first repeat, twice that before the second, and so on, up to `backoff_max`."""
        self.check(method, url)
        merged = {"Accept": "application/json", **(headers or {})}
        data = None
        if body is not None and form is not None:
            raise ValueError("a call has a JSON body or a form, not both")
        if body is not None:
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
            merged["Content-Type"] = "application/json"
        elif form is not None:
            data = urlencode(dict(form)).encode("utf-8")
            merged["Content-Type"] = "application/x-www-form-urlencoded"
        attempt = 0
        while True:
            left = self.remaining()
            if left is not None and left <= 0:
                raise HttpError(0, f"{method} {urlsplit(url).netloc}: the deadline of the run was reached")
            try:
                status, answer_headers, answer = self.transport(method, url, merged, data, timeout if left is None else max(1.0, min(timeout, left)))
            except (OSError, TimeoutError, HTTPException, urllib.error.URLError) as error:
                status, answer_headers, answer = 0, {}, self.redact(f"network error: {type(error).__name__}").encode()
            if 200 <= status < 300:
                return Response(status, answer_headers, answer)
            wait = retry_after(answer_headers) if status == 429 else None
            retryable = retry_network if status == 0 else status in retry_statuses
            may_retry = retryable and not (wait is not None and wait > retry_after_max)
            if may_retry and attempt < retries:
                pause = wait if wait is not None else min(backoff_max, backoff * (2 ** attempt) * (1 + self.jitter()))
                left = self.remaining()
                if left is None or pause < left:
                    self.sleep(pause)
                    attempt += 1
                    continue
            message = answer.decode("utf-8", "replace") if status == 0 else error_text(status, answer, self.redact)
            raise HttpError(status, f"{method} {urlsplit(url).netloc}: {message}", wait)
