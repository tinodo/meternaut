"""Long-running operations: what Azure answers to a write that it carries out later, and how a change follows it.

A stop, a resize and a change of a disk's tier are asynchronous in Azure Resource Manager (Learn, "Status of asynchronous operations"): the first answer is 200, 201 or 202, and
what says that the operation is not finished is the header `Azure-AsyncOperation` (the address that tells the status; used when it is there), else `Location`, or a
`provisioningState` that is not Succeeded, Failed or Canceled. The status address needs a right at the resource group, which the approver may not have: then the progress cannot be
read here, and that is not a failure.

So a change follows its operation for a short time, inside the request of the approver's sign-in and with the approver's token, which lives in memory for that request only (rule 29). When
the operation is not finished by then, the action is `running`, the approver is told so plainly, and the end is read later with the app's own reader, by looking at the resource itself
(runner.tick). Nothing here ever makes a second write.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from ..http import HttpError, Refused, Response
from .azure import Azure
from .calls import ARM_HOST

MAX_URL = 4096  # Learn: a REST client has to accept 4 KB for these two headers
MAX_TEXT = 200
WAIT_DEFAULT, WAIT_LEAST, WAIT_MOST = 3.0, 2.0, 5.0
DONE = ("succeeded",)
FAILED = ("failed", "canceled", "cancelled")
FINAL = DONE + FAILED
NOT_FINISHED = "accepted"  # what the status of an operation says that was accepted and has not begun, when it says nothing else


@dataclass(frozen=True)
class Initiated:
    """What the answer to the write says: the status, the address to follow, which header gave it, how long Azure asked to wait, and the provisioning state of the body (lower case)."""

    status: int
    url: str = ""
    via: str = ""
    wait: float | None = None
    provisioning: str = ""

    @property
    def asynchronous(self) -> bool:
        """The operation is not finished: there is an address to follow, or the answer is 201 or 202, or the provisioning state is not a final one."""
        return bool(self.url) or self.status in (201, 202) or self.provisioning not in ("",) + FINAL

    @property
    def failed(self) -> bool:
        return self.provisioning in FAILED


@dataclass(frozen=True)
class Progress:
    """One look at an operation: `succeeded`, `failed` or `running`. `text` is what Azure said about a failure (its code and the first words of its message), and `readable` is False when
    the progress cannot be read here at all (a right is missing, or the address is not one that the client may call), so that looking again is no use."""

    state: str
    text: str = ""
    readable: bool = True


def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if str(key).lower() == name:
            return str(value).strip()
    return ""


def _seconds(value: str) -> float | None:
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if 0 <= seconds < 86400 else None


def _body(response: Response) -> dict:
    try:
        body = response.json()
    except HttpError:
        return {}
    return body if isinstance(body, dict) else {}


def _provisioning(body: dict) -> str:
    properties = body.get("properties")
    state = properties.get("provisioningState") if isinstance(properties, dict) else body.get("provisioningState")
    return state.strip().lower()[:40] if isinstance(state, str) else ""


def initiated(response: Response) -> Initiated:
    """What the answer of a write says about the operation. An address that is not on Azure Resource Manager is not followed."""
    url, via = "", ""
    for name, header in (("azure-asyncoperation", "Azure-AsyncOperation"), ("location", "Location")):
        found = _header(response.headers, name)
        if found:
            url, via = found, header
            break
    if url and (len(url) > MAX_URL or not url.startswith(f"https://{ARM_HOST}/")):
        url, via = "", ""
    return Initiated(response.status, url, via, _seconds(_header(response.headers, "retry-after")), _provisioning(_body(response)))


def pause(started: Initiated) -> float:
    """How long to wait before looking: what Azure asked, kept between two and five seconds, else three."""
    return WAIT_DEFAULT if started.wait is None else min(WAIT_MOST, max(WAIT_LEAST, started.wait))


def _said(azure: Azure, error: object) -> str:
    """The code and the first words of the message of the error of an operation, as one short line."""
    if not isinstance(error, dict):
        return ""
    text = " ".join(f"{error.get('code', '')}: {error.get('message', '')}".strip(": ").split())
    return azure.client.redact(forget(text[:MAX_TEXT]))


def check(azure: Azure, started: Initiated) -> Progress:
    """One look at the operation with the token of the call. A status address that needs a right that the person has not got, or that is not on the client's list, is `running` and
    not readable; a throttled or failed look is `running` and may be repeated."""
    if not started.url:
        return Progress("running", "", readable=False)
    try:
        answer = azure.get(started.url)
    except Refused:
        return Progress("running", "", readable=False)
    except HttpError as error:
        return Progress("running", "", readable=error.status not in (401, 403, 404))
    body = _body(answer)
    if started.via == "Azure-AsyncOperation":
        status = str(body.get("status", "")).strip().lower()
        if status in DONE:
            return Progress("succeeded")
        if status in FAILED:
            return Progress("failed", _said(azure, body.get("error")) or f"the operation ended as {status}")
        return Progress("running")
    state = _provisioning(body)
    if answer.status == 202:
        return Progress("running")
    if state in FAILED:
        return Progress("failed", _said(azure, body.get("error")) or f"the resource shows the provisioning state {state}")
    return Progress("succeeded") if answer.status in (200, 204) and state in ("",) + DONE else Progress("running")


_ADDRESS = re.compile(r"https://management\.azure\.com/[^\s]*")


def forget(text: str) -> str:
    """A text without any address: what Azure says about an operation may hold one, and nothing here shows an address of Azure to a person."""
    return _ADDRESS.sub("(an address)", text)
