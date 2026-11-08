"""One client and one token: what a family reads with, and changes with.

For a change the token is the approver's own (delegated.py): it lives in memory for the one request and is never stored, logged or shown (AGENTS.md rule 29). For a read before a plan
and for the checks of the timer it is the reader's. The client's list of calls says which of the two it may do: a client made with `read_patterns` cannot even attempt a write.
"""
from __future__ import annotations

from typing import Callable

from ..http import Client, Response
from .calls import ARM_RESOURCE, WRITES, Call


class Azure:
    """The calls of one change, or of one run of checks. `correlation` is the id that goes on the write, so that Azure's own logs and ours can be joined."""

    def __init__(self, client: Client, token: Callable[[str], str], correlation: str = "") -> None:
        self.client, self.token, self.correlation = client, token, correlation

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token(ARM_RESOURCE)}"}

    def get(self, url: str, timeout: float = 30) -> Response:
        """A read. Raises HttpError when Azure refuses or fails, and Refused when the address is not on the client's list."""
        return self.client.request("GET", url, headers=self._headers(), timeout=timeout)

    def write(self, call: Call, url: str, body: object = None) -> Response:
        """The one write of a change: made once, never retried (a write that failed may have been carried out). `call` has to be one of WRITES."""
        if call not in WRITES:
            raise LookupError("this is not a call that Meternaut may make")
        headers = {**self._headers(), "x-ms-correlation-request-id": self.correlation or "none"}
        return self.client.request(call.method, url, headers=headers, body=body, timeout=60, retries=0, retry_network=False)
