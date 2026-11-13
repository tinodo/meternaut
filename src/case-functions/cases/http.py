"""The one place where the app makes an HTTPS call.

A call is made only to a fixed list of addresses with a fixed method, every one of them a read (the POSTs of Azure ask for a query result): a call to
anything else is refused before it leaves the app, so a mistake in the code cannot become a write to Azure. Timeouts are set, and a failure that may pass is
retried a bounded number of times. Two exceptions: the Foundry project of the app, where the app makes and reads its own agents and makes and deletes its own conversations
(foundry_calls), and the AI Gateway, which every model call goes through and which has the one POST of a chat completion (ai_gateway_calls). No chat completion goes to the Foundry
resource or its project: there is no direct path to a model (AGENTS.md rule 15 (c)). The Study (cases/study.py) has one list more, of public documentation pages that it reads with no
token (docs_calls), on a client of its own.
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
# The resource group of a subscription, a Log Analytics workspace of it (4 to 63 letters, digits and hyphens, none at the ends) and an account of the AI services of it.
GROUP = rf"/subscriptions/{GUID}/resourceGroups/[A-Za-z0-9._()-]{{1,90}}"
WORKSPACE = rf"{GROUP}/providers/Microsoft\.OperationalInsights/workspaces/[A-Za-z0-9][A-Za-z0-9-]{{2,61}}[A-Za-z0-9]"
AI_ACCOUNT = rf"{GROUP}/providers/Microsoft\.CognitiveServices/accounts/[A-Za-z0-9][A-Za-z0-9._-]{{0,63}}"
# A private endpoint and a private DNS zone, whose own lists (the DNS zone groups of the endpoint, the address records of the zone) the impact check reads (cases/impact.py).
ENDPOINT = rf"{GROUP}/providers/Microsoft\.Network/privateEndpoints/[A-Za-z0-9._()~-]{{1,100}}"
DNS_ZONE = rf"{GROUP}/providers/Microsoft\.Network/privateDnsZones/[A-Za-z0-9._()~-]{{1,100}}"
# The query API of Azure Monitor Logs (Learn, "Request format for the Azure Monitor Logs query API"): the public endpoint, whose token is asked for the audience below. A workspace is named
# there by its id (a GUID, the customerId of the workspace), and the one POST of it asks a question.
LOG_ANALYTICS_HOST = "api.loganalytics.azure.com"
LOG_ANALYTICS_RESOURCE = "https://api.loganalytics.io"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_CHALLENGE = 1500
# The endpoint of one Microsoft Foundry project (the default project is called _project), the name of an agent in it and the id of a conversation of it.
FOUNDRY_ENDPOINT = re.compile(r"https://[a-z0-9][a-z0-9-]{0,62}[a-z0-9]\.services\.ai\.azure\.com/api/projects/[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}")
FOUNDRY_AGENT_NAME = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
FOUNDRY_CONVERSATION_ID = r"conv_[A-Za-z0-9_-]{1,100}"
# The host of the AI Gateway (the service reports it as properties.frontend.defaultHostname): lower-case labels under the service's own domain, which a token is never sent beyond.
AI_GATEWAY_HOST = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.ai\.gateway\.azure\.com")
# The one route of a chat completion that the app makes: the AI Gateway's route of its OpenAI-compatible models, which every model call of Meternaut goes through.
AI_GATEWAY_CHAT_PATH = "/default/models/openai/v1/chat/completions"

Transport = Callable[[str, str, Mapping[str, str], "bytes | None", float], "tuple[int, Mapping[str, str], bytes]"]


class HttpError(Exception):
    """A call that failed. `status` is 0 when no answer arrived. The text never holds a header or a secret.

    `challenge` is the `www-authenticate` header of a 401 or a 403, as it came and cut at MAX_CHALLENGE characters, for the one reader that may use it (the claims
    challenge of the runner). It is never part of the text of the error, so it reaches no log, no History line and no page."""

    def __init__(self, status: int, message: str, retry_after: float | None = None, challenge: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
        self.challenge = challenge


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
    """The calls to one Foundry project. They make and read Meternaut's own agents there and make, use and delete its own conversations, and nothing else: no other host, no other
    project, no other method, no DELETE of an agent, and no chat completion, because a model is never called direct: its calls go through the AI Gateway (ai_gateway_calls). The
    patterns are exact (no case folding) and nothing may follow the names."""
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


def ai_gateway_calls(host: str) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """The one call to the AI Gateway: the POST of a chat completion, on the gateway's own host and on its one route. Every model call of Meternaut is this call (AGENTS.md rule 15 (c));
    the route reads no key and lists nothing, and nothing else of the gateway is called."""
    if not AI_GATEWAY_HOST.fullmatch(host) or len(host) > 253:
        raise ValueError("the host of the AI Gateway is a host name under .ai.gateway.azure.com, in lower case, without a scheme, a port or a path")
    return (("POST", re.compile(re.escape(f"https://{host}{AI_GATEWAY_CHAT_PATH}"))),)


# The public pages of Microsoft's documentation that the Study reads (cases/library.py), and nothing else of the internet: two hosts of pages, whose paths begin with the English folder
# (an address of another language or of no language is answered by a redirect, which the client does not follow), and the Azure Retail Prices API. GET only, no token of any kind, and a
# list of its own: the Watch's list (allowed_calls) holds none of them.
DOCS_PAGES = {"learn.microsoft.com": "/en-us/", "azure.microsoft.com": "/en-us/"}
PRICES_HOST = "prices.azure.com"
PRICES_PATH = "/api/retail/prices"
DOC_PATH = r"(?:(?!\.+(?:/|$))[A-Za-z0-9._~-]{1,100}/?){1,16}"


def docs_calls() -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """The calls of the Study to public documentation: a GET of a page under /en-us/ of the two hosts, and a GET of the price list. A path is plain words between slashes (no encoded
    character, no folder that is only dots), and the query is checked by cases/library.py, which makes the call: this list sees the address without its query."""
    pages = tuple(("GET", re.compile(re.escape(f"https://{host}{prefix}") + DOC_PATH)) for host, prefix in DOCS_PAGES.items())
    return pages + (("GET", re.compile(re.escape(f"https://{PRICES_HOST}{PRICES_PATH}"))),)


def allowed_calls(foundry_endpoint: str | None = None, ai_gateway_host: str | None = None) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """(method, address without its query) of every call that the app may make. `foundry_endpoint` adds the calls of foundry_calls for that one project and `ai_gateway_host` the one
    call of ai_gateway_calls; without them the app makes none, and every call of the Watch to Azure is a read (two POSTs of Azure Resource Manager and one of the Logs query API ask a
    question: a query). The one GET of /subscriptions lists the subscriptions that the app's own identity can read (scope.py): the Reader role covers it (R1 of
    environment/access-requirements.json), and the address has no part after it. The GET of one subscription (/subscriptions/<id>, nothing after the id) gives its display name, with the same role. The reads of the investigation's deeper tools name their own addresses (a workspace, its tables, its saved
    searches, the deployments of an account, the activity log, the diagnostic settings of a resource, the DNS zone groups of a private endpoint and the address records of a private DNS zone) and never a resource as such: a GET of one resource would read any of its properties."""
    arm = re.escape(f"https://{ARM_HOST}")
    calls = (
        ("POST", re.compile(arm + r"/providers/Microsoft\.ResourceGraph/resources", re.I)),
        ("POST", re.compile(arm + rf"/subscriptions/{GUID}/providers/Microsoft\.CostManagement/query", re.I)),
        ("GET", re.compile(arm + rf"/subscriptions/{GUID}/providers/Microsoft\.CostManagement/benefitRecommendations", re.I)),
        ("GET", re.compile(arm + rf"/subscriptions/{GUID}/providers/Microsoft\.Consumption/reservationRecommendations", re.I)),
        ("GET", re.compile(arm + rf"/subscriptions/{GUID}/providers/Microsoft\.Advisor/recommendations", re.I)),
        ("GET", re.compile(arm + rf"{SCOPE}/providers/Microsoft\.Authorization/locks", re.I)),
        ("GET", re.compile(arm + rf"{SCOPE}/providers/Microsoft\.Insights/metricDefinitions", re.I)),
        ("GET", re.compile(arm + rf"{SCOPE}/providers/Microsoft\.Insights/metrics", re.I)),
        ("GET", re.compile(arm + rf"{SCOPE}/providers/Microsoft\.Insights/diagnosticSettings", re.I)),
        ("GET", re.compile(arm + rf"/subscriptions/{GUID}/providers/Microsoft\.Insights/workbooks", re.I)),
        ("GET", re.compile(arm + rf"/subscriptions/{GUID}/providers/Microsoft\.Insights/eventtypes/management/values", re.I)),
        ("GET", re.compile(arm + rf"/subscriptions/{GUID}/providers/Microsoft\.Security/pricings", re.I)),
        ("GET", re.compile(arm + WORKSPACE, re.I)),
        ("GET", re.compile(arm + WORKSPACE + "/tables", re.I)),
        ("GET", re.compile(arm + WORKSPACE + "/savedSearches", re.I)),
        ("GET", re.compile(arm + WORKSPACE + r"/providers/Microsoft\.SecurityInsights/alertRules", re.I)),
        ("GET", re.compile(arm + AI_ACCOUNT + "/deployments", re.I)),
        ("GET", re.compile(arm + ENDPOINT + "/privateDnsZoneGroups", re.I)),
        ("GET", re.compile(arm + DNS_ZONE + "/A", re.I)),
        ("POST", re.compile(re.escape(f"https://{LOG_ANALYTICS_HOST}/v1/workspaces/") + GUID + "/query", re.I)),
        # What the capability profile reads (cases/capability.py): the first page of the lists of billing accounts, reservation orders and savings plan orders that the identity may see, and
        # one line of the price sheet of a subscription. Each address is the list itself, never one account or one order.
        ("GET", re.compile(arm + r"/providers/Microsoft\.Billing/billingAccounts", re.I)),
        ("GET", re.compile(arm + r"/providers/Microsoft\.Capacity/reservationOrders", re.I)),
        ("GET", re.compile(arm + r"/providers/Microsoft\.BillingBenefits/savingsPlanOrders", re.I)),
        ("GET", re.compile(arm + rf"/subscriptions/{GUID}/providers/Microsoft\.Consumption/pricesheets/default", re.I)),
        # The display name of one subscription (Learn, "Subscriptions - Get"): the address is the subscription itself and nothing after it, so no resource of it is read this way.
        ("GET", re.compile(arm + rf"/subscriptions/{GUID}", re.I)),
        ("GET", re.compile(arm + r"/subscriptions", re.I)),
    )
    if foundry_endpoint is not None:
        calls += foundry_calls(foundry_endpoint)
    if ai_gateway_host is not None:
        calls += ai_gateway_calls(ai_gateway_host)
    return calls


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A call goes to the address that was checked against the list. An answer that sends it somewhere else is not followed: urllib would send every header of the
    call, the authorization included, to the new address. The answer is the status of the redirect, like any other answer."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def default_transport(method: str, url: str, headers: Mapping[str, str], data: bytes | None, timeout: float, limit: int | None = None) -> tuple[int, Mapping[str, str], bytes]:
    """One call. `limit` caps the bytes of the answer that are read (a client that asks for a small answer sets it); without it the whole answer is read."""
    request = urllib.request.Request(url, data=data, headers=dict(headers), method=method)
    try:
        with _OPENER.open(request, timeout=timeout) as response:  # noqa: S310 (the address was checked against the list)
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read(limit)
    except urllib.error.HTTPError as error:
        return error.code, {k.lower(): v for k, v in error.headers.items()}, error.read(limit)


QUOTA_RESETS = re.compile(r"^(\d{1,3}):([0-5]?\d):([0-5]?\d(?:\.\d{1,7})?)$")


def retry_after(headers: Mapping[str, str]) -> float | None:
    """Seconds to wait, from Retry-After, from a service's own header that ends in -retry-after (Cost Management has several, for its entity, its client and its tenant) or from the
    time that Azure Resource Graph says its quota resets after (x-ms-user-quota-resets-after, hh:mm:ss, which it adds to every answer: Learn, "Guidance for throttled requests in
    Azure Resource Graph"). The longest of them is the one that binds. None when no header gives a number."""
    waits: list[float] = []
    for name, value in headers.items():
        text = str(value).strip()
        if name == "retry-after" or name.endswith("-retry-after"):
            try:
                waits.append(max(0.0, float(text)))
            except ValueError:
                continue
        elif name == "x-ms-user-quota-resets-after":
            found = QUOTA_RESETS.match(text)
            if found:
                # A second more than the quota says, so that the quota has reset when the call is made again.
                waits.append(int(found.group(1)) * 3600 + int(found.group(2)) * 60 + float(found.group(3)) + 1.0)
    return max(waits) if waits else None


def challenge_of(status: int, headers: Mapping[str, str]) -> str:
    """The `www-authenticate` header of a 401 or a 403 (the name is compared in lower case), cut at MAX_CHALLENGE characters. Empty for any other answer."""
    if status in (401, 403):
        for name, value in headers.items():
            if str(name).lower() == "www-authenticate":
                return str(value)[:MAX_CHALLENGE]
    return ""


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

    def request(self, method: str, url: str, *, headers: Mapping[str, str] | None = None, body: object = None, form: Mapping[str, str] | None = None, xml: str | None = None,
                timeout: float = 30, retries: int = 2, retry_after_max: float = 60, retry_statuses: frozenset[int] = RETRY_STATUSES,
                retry_network: bool = True, backoff: float = 1.0, backoff_max: float = 30.0) -> Response:
        """One call. A call that may already have been carried out (a model call whose answer did not arrive) is made with retry_network=False.

        `body` is sent as JSON, `form` as a form (the token endpoint of Microsoft Entra takes a form) and `xml` as XML text (the Queue service takes its messages so). A call has one of
        them or none.

        A call that is retried waits as long as the service says (Retry-After, up to `retry_after_max`). When the service says nothing the pause is `backoff` seconds
        (with jitter) before the first repeat, twice that before the second, and so on, up to `backoff_max`."""
        self.check(method, url)
        merged = {"Accept": "application/json", **(headers or {})}
        data = None
        if sum(item is not None for item in (body, form, xml)) > 1:
            raise ValueError("a call has a JSON body, a form or XML text, not more than one")
        if body is not None:
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
            merged["Content-Type"] = "application/json"
        elif form is not None:
            data = urlencode(dict(form)).encode("utf-8")
            merged["Content-Type"] = "application/x-www-form-urlencoded"
        elif xml is not None:
            data = xml.encode("utf-8")
            merged["Content-Type"] = "application/xml"
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
            raise HttpError(status, f"{method} {urlsplit(url).netloc}: {message}", wait, challenge_of(status, answer_headers))
