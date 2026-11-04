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


class IdentityError(Exception):
    """The platform gave no token. The text says why, and never holds a token."""


def default_fetch(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (the platform's own endpoint)
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


class Identity:
    def __init__(self, env: Mapping[str, str], *, fetch: Callable[[str, Mapping[str, str], float], tuple[int, bytes]] = default_fetch,
                 clock: Callable[[], float] = time.time) -> None:
        self.endpoint = env.get("IDENTITY_ENDPOINT", "")
        self.header = env.get("IDENTITY_HEADER", "")
        self.client_id = env.get("AZURE_CLIENT_ID", "")
        self.fetch, self.clock = fetch, clock
        self._cache: dict[str, tuple[str, float]] = {}

    def token(self, resource: str) -> str:
        cached = self._cache.get(resource)
        if cached and cached[1] - self.clock() > REFRESH_SECONDS:
            return cached[0]
        if urlsplit(self.endpoint).scheme not in ("http", "https") or not self.header:
            raise IdentityError("the platform's managed identity endpoint is not available")
        url = f"{self.endpoint}?resource={quote(resource, safe='')}&api-version={API_VERSION}"
        if self.client_id:
            url += f"&client_id={quote(self.client_id, safe='')}"
        try:
            status, body = self.fetch(url, {"X-IDENTITY-HEADER": self.header, "Accept": "application/json"}, 30)
        except (OSError, TimeoutError, urllib.error.URLError) as error:
            raise IdentityError(f"the managed identity endpoint gave no answer ({type(error).__name__})") from error
        if status != 200:
            raise IdentityError(f"the managed identity endpoint answered {status}")
        try:
            document = json.loads(body.decode("utf-8"))
            token, expires = document["access_token"], float(document["expires_on"])
        except (ValueError, KeyError, TypeError) as error:
            raise IdentityError("the managed identity endpoint gave an answer without a token") from error
        if not isinstance(token, str) or not token:
            raise IdentityError("the managed identity endpoint gave an answer without a token")
        self._cache[resource] = (token, expires)
        return token
