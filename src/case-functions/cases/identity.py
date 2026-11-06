"""The token of the app's managed identity, from the platform's local endpoint (no key, no secret, no library)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Callable, Mapping
from urllib.parse import quote, urlsplit

API_VERSION = "2019-08-01"
REFRESH_SECONDS = 300
TRY_TIMEOUT_SECONDS = 15
PAUSES_SECONDS = (2, 5)  # before the second try and before the third
NETWORK_ERRORS = (OSError, TimeoutError, urllib.error.URLError)


class IdentityError(Exception):
    """The platform gave no token. The text says why, and never holds a token."""


def _failure(problem: str, tries: int) -> IdentityError:
    """The error of the last try. It says how many tries were made when there was more than one."""
    return IdentityError(f"the managed identity endpoint {problem}" + (f" after {tries} tries" if tries > 1 else ""))


def default_fetch(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (the platform's own endpoint)
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


class Identity:
    def __init__(self, env: Mapping[str, str], *, fetch: Callable[[str, Mapping[str, str], float], tuple[int, bytes]] = default_fetch,
                 clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep) -> None:
        self.endpoint = env.get("IDENTITY_ENDPOINT", "")
        self.header = env.get("IDENTITY_HEADER", "")
        self.client_id = env.get("AZURE_CLIENT_ID", "")
        self.fetch, self.clock, self.sleep = fetch, clock, sleep
        self._cache: dict[str, tuple[str, float]] = {}

    def token(self, resource: str) -> str:
        """The token for the resource, from the cache while it has more than REFRESH_SECONDS left.

        The platform's endpoint can answer slowly just after the host started, so a request that failed for a passing reason is made again: 3 tries in all,
        each with a timeout of 15 s, with a pause of 2 s before the second try and 5 s before the third. The worst case is about 15+2+15+5+15 = 52 s.
        Only a network failure (a timeout, a lost or refused connection), HTTP 429 and HTTP 5xx are tried again.
        Any other refusal, a missing endpoint and an answer without a token end it at once."""
        cached = self._cache.get(resource)
        if cached and cached[1] - self.clock() > REFRESH_SECONDS:
            return cached[0]
        if urlsplit(self.endpoint).scheme not in ("http", "https") or not self.header:
            raise IdentityError("the platform's managed identity endpoint is not available")
        url = f"{self.endpoint}?resource={quote(resource, safe='')}&api-version={API_VERSION}"
        if self.client_id:
            url += f"&client_id={quote(self.client_id, safe='')}"
        headers = {"X-IDENTITY-HEADER": self.header, "Accept": "application/json"}
        for tries, pause in enumerate((0, *PAUSES_SECONDS), start=1):  # the first try has no pause
            if tries > 1:
                self.sleep(pause)
            try:
                status, body = self.fetch(url, headers, TRY_TIMEOUT_SECONDS)
            except NETWORK_ERRORS as error:
                problem, cause = f"gave no answer ({type(error).__name__})", error
            else:
                if status == 200:
                    return self._accept(resource, body, tries)
                problem, cause = f"answered {status}", None
                if status != 429 and not (500 <= status <= 599):
                    break
        raise _failure(problem, tries) from cause

    def _accept(self, resource: str, body: bytes, tries: int) -> str:
        try:
            document = json.loads(body.decode("utf-8"))
            token, expires = document["access_token"], float(document["expires_on"])
        except (ValueError, KeyError, TypeError) as error:
            raise _failure("gave an answer without a token", tries) from error
        if not isinstance(token, str) or not token:
            raise _failure("gave an answer without a token", tries)
        self._cache[resource] = (token, expires)
        return token
