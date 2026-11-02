"""Model clients for check C14.

Every model call of the demonstration goes through the governance hub (the Citadel hub of the adopting
organisation). `HubClient` reads the route and the credentials of a development contract from the
environment and calls it with the standard library only. `ScriptedClient` stands in for a model in tests.
`GuardedClient` stops a run at the call limit or the spending cap of its stage.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Protocol


class ClientError(RuntimeError):
    pass


class StopRun(RuntimeError):
    """The call limit or the spending cap of the stage was reached; nothing more is asked of the model."""


@dataclass(frozen=True)
class Completion:
    text: str
    prompt_tokens: int
    completion_tokens: int


class ModelClient(Protocol):
    def complete(self, system: str, user: str) -> Completion: ...


class ScriptedClient:
    """A stand-in for a model: `handler(system, user)` returns the reply text or a Completion."""

    def __init__(self, handler: Callable[[str, str], "str | Completion"]):
        self.handler = handler
        self.calls = 0

    def complete(self, system: str, user: str) -> Completion:
        self.calls += 1
        reply = self.handler(system, user)
        if isinstance(reply, Completion):
            return reply
        return Completion(reply, max(1, (len(system) + len(user)) // 4), max(1, len(reply) // 4))


class HubClient:
    """Chat Completions through the hub. The environment names the route; no secret is read from a file.

    C14_HUB_CHAT_URL    the full URL of the chat completions route on the hub's development contract
    C14_HUB_MODEL       the model alias that the contract maps to a model (for example `reasoner`)
    C14_HUB_KEY         the contract's subscription key, sent in the header named by C14_HUB_KEY_HEADER (default api-key)
    C14_HUB_BEARER      or a bearer token, sent as Authorization (used instead of the key when set)
    C14_HUB_MAX_TOKENS  optional limit on the reply, sent as max_completion_tokens (a real run sets it from the pack's params.json)
    """

    def __init__(self, env: dict | None = None, *, timeout: float = 120.0, attempts: int = 3, sleep=time.sleep,
                 max_tokens: int | None = None):
        env = os.environ if env is None else env
        self.url = env.get("C14_HUB_CHAT_URL", "")
        self.model = env.get("C14_HUB_MODEL", "")
        self.key = env.get("C14_HUB_KEY", "")
        self.key_header = env.get("C14_HUB_KEY_HEADER", "api-key")
        self.bearer = env.get("C14_HUB_BEARER", "")
        self.max_tokens = max_tokens or (int(env["C14_HUB_MAX_TOKENS"]) if env.get("C14_HUB_MAX_TOKENS") else None)
        missing = [n for n, v in (("C14_HUB_CHAT_URL", self.url), ("C14_HUB_MODEL", self.model)) if not v]
        if missing or not (self.key or self.bearer):
            raise ClientError("set " + ", ".join(missing + ([] if self.key or self.bearer else ["C14_HUB_KEY or C14_HUB_BEARER"])))
        if not self.url.startswith("https://"):
            raise ClientError("C14_HUB_CHAT_URL must be an https URL")
        self.timeout, self.attempts, self.sleep = timeout, attempts, sleep
        self.requests = 0

    def complete(self, system: str, user: str) -> Completion:
        body = {"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.max_tokens:
            body["max_completion_tokens"] = self.max_tokens
        headers = {"Content-Type": "application/json"}
        if self.bearer:
            headers["Authorization"] = f"Bearer {self.bearer}"
        else:
            headers[self.key_header] = self.key
        data = json.dumps(body).encode("utf-8")
        for attempt in range(1, self.attempts + 1):
            self.requests += 1
            request = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < self.attempts:
                    wait = float(e.headers.get("Retry-After") or 2 ** attempt)
                    self.sleep(min(wait, 60.0))
                    continue
                raise ClientError(f"the hub answered {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < self.attempts:
                    self.sleep(2 ** attempt)
                    continue
                raise ClientError(f"the hub could not be reached: {e}")
        try:
            text = payload["choices"][0]["message"]["content"] or ""
            usage = payload.get("usage", {})
            return Completion(text, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))
        except (KeyError, IndexError, TypeError, ValueError):
            raise ClientError("the hub's reply is not a chat completion")


class GuardedClient:
    """Counts every call and its tokens, and refuses a call past the limit or the cap.

    `prices` is (EUR per million input tokens, EUR per million output tokens) or None. A cap needs prices and
    `max_completion_tokens` (the limit the hub is told to apply to a reply), because the guard refuses a call
    whose worst case would pass the cap: the cost so far, plus the call's prompt (estimated at one token per two
    characters, which is generous) and a full-length reply. Without prices only the call limit is enforced, and
    the cost is read from the hub's logs. `used` seeds the counters with calls already made for the same stage.
    """

    def __init__(self, inner: ModelClient, *, max_calls: int, prices: tuple[float, float] | None = None,
                 cap_eur: float | None = None, max_completion_tokens: int | None = None,
                 used: tuple[int, int, int] = (0, 0, 0)):
        if cap_eur is not None and (not prices or not max_completion_tokens):
            raise ValueError("a spending cap needs token prices and max_completion_tokens: without them it cannot be enforced")
        self.inner, self.max_calls, self.prices, self.cap_eur = inner, max_calls, prices, cap_eur
        self.max_completion_tokens = max_completion_tokens
        self.calls, self.prompt_tokens, self.completion_tokens = used

    @property
    def cost_eur(self) -> float | None:
        if not self.prices:
            return None
        return (self.prompt_tokens * self.prices[0] + self.completion_tokens * self.prices[1]) / 1_000_000

    def _worst_case_eur(self, system: str, user: str) -> float:
        prompt_estimate = (len(system) + len(user) + 1) // 2
        return (prompt_estimate * self.prices[0] + self.max_completion_tokens * self.prices[1]) / 1_000_000

    def complete(self, system: str, user: str) -> Completion:
        if self.calls >= self.max_calls:
            raise StopRun(f"the limit of {self.max_calls} model calls is reached")
        if self.cap_eur is not None and (self.cost_eur or 0.0) + self._worst_case_eur(system, user) > self.cap_eur:
            raise StopRun(f"the next call could pass the spending cap of {self.cap_eur} EUR")
        self.calls += 1
        completion = self.inner.complete(system, user)
        self.prompt_tokens += completion.prompt_tokens
        self.completion_tokens += completion.completion_tokens
        return completion
