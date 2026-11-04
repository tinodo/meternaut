"""The gateway: the access product's key, read at the start of a run, and the chat route.

The gateway's rules always require the key of an access product, so this module reads that key with the app's own identity
(a role that allows that one read and nothing else), keeps it in memory, never logs it and registers it for redaction. If the
gateway answers 401 the key is read once more and the call is made once more. It is the one place that holds the key
(AGENTS.md rule 23 names it).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .config import Settings
from .http import ARM_HOST, Client, HttpError
from .redact import Redactor

LIST_SECRETS_API = "2024-05-01"
ARM_RESOURCE = f"https://{ARM_HOST}"
CHAT_TIMEOUT = 90
CHAT_RETRY_STATUSES = frozenset({429, 503})


class GatewayError(Exception):
    """The gateway or the model gave no usable answer. The text never holds the key."""


class GatewayRefused(GatewayError):
    """The gateway itself refused the call: the allowance is used up, or the key or the model is not allowed."""


@dataclass(frozen=True)
class Chat:
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class Gateway:
    def __init__(self, settings: Settings, client: Client, token: Callable[[str], str], redact: Redactor) -> None:
        self.settings, self.client, self.token, self.redact = settings, client, token, redact
        self._key: str | None = None

    @staticmethod
    def key_path(settings: Settings) -> str:
        """The path of the one call that asks for the key; http.allowed_calls lets exactly this call through."""
        return f"{settings.product_subscription_id}/listSecrets"

    def open(self) -> None:
        """Reads the key of the access product. It stays in this object and nowhere else."""
        url = f"{ARM_RESOURCE}{self.key_path(self.settings)}?api-version={LIST_SECRETS_API}"
        try:
            answer = self.client.request("POST", url, headers={"Authorization": f"Bearer {self.token(ARM_RESOURCE)}"}, retries=2).json()
        except HttpError as error:
            raise GatewayError(f"the key of the access product could not be read ({error})") from error
        key = answer.get("primaryKey") if isinstance(answer, dict) else None
        if not isinstance(key, str) or len(key) < 16:
            raise GatewayError("the key of the access product could not be read (the answer holds no key)")
        self._key = key
        self.redact.add(key)

    def chat(self, model: str, system: str, user: str, max_completion_tokens: int) -> Chat:
        body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_completion_tokens": max_completion_tokens}
        try:
            return self._post(body)
        except HttpError as error:
            if error.status != 401:
                raise self._failure(error) from error
        self.open()
        try:
            return self._post(body)
        except HttpError as error:
            raise self._failure(error) from error

    def _failure(self, error: HttpError) -> GatewayError:
        if error.status in (401, 403, 429):
            return GatewayRefused(f"the gateway refused the call ({error})")
        return GatewayError(f"the gateway gave no answer ({error})")

    def _post(self, body: dict) -> Chat:
        if not self._key:
            raise GatewayError("the key of the access product has not been read")
        # A call whose answer did not arrive may have been carried out and paid for, so only a refusal that says "not now" (429, 503) is repeated.
        response = self.client.request("POST", f"{self.settings.gateway_url}/models/chat/completions", headers={"api-key": self._key}, body=body,
                                       timeout=CHAT_TIMEOUT, retries=2, retry_after_max=60, retry_statuses=CHAT_RETRY_STATUSES, retry_network=False)
        return self._read(response.json())

    @staticmethod
    def _read(data: object) -> Chat:
        try:
            choice = data["choices"][0]  # type: ignore[index]
            text = choice["message"]["content"]
            usage = data.get("usage") or {}  # type: ignore[union-attr]
            prompt, completion, total = (int(usage.get(name, 0)) for name in ("prompt_tokens", "completion_tokens", "total_tokens"))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as error:
            raise GatewayError("the answer of the gateway is not a completion") from error
        if min(prompt, completion, total) < 0:
            raise GatewayError("the answer of the gateway reports a usage that is not valid")
        if not isinstance(text, str) or not text.strip():
            reason = choice.get("finish_reason") if isinstance(choice, dict) else None
            raise GatewayError("the model gave no text" + (" (it used its whole completion budget on its reasoning)" if reason == "length" else ""))
        return Chat(text, prompt, completion, max(total, prompt + completion))
