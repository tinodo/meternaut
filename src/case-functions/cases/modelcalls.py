"""The model calls of the Detective and the Skeptic: a chat completion through the AI Gateway.

Every model call of Meternaut goes through the AI Gateway, the governance hub of the Citadel design, and there is no direct path to a model (AGENTS.md rule 15 (c), docs/proposals/08-ai-gateway.md):
a POST of `/default/models/openai/v1/chat/completions` on the gateway's own host (the setting AIGATEWAY_HOST), with a token of the app's own managed identity for the audience
https://azure-api.net/aigateway, and the alias as `model`. The aliases have the names of the model deployments (environment/aigateway/main.bicep), so MODEL_DETECTIVE and MODEL_SKEPTIC name them.
The gateway accepts only a Microsoft Entra token, so nothing here reads or sends a key; the identity needs the role AI Gateway Models User on the gateway (environment/aigateway/main.bicep gives
it, and a new role takes up to ten minutes to apply). The gateway's own limits apply to the app as to every caller. The token is registered for redaction so that no error text can hold it.

Verified on the service on 2026-11-07, with the Operator's identity (tools/aigateway-check.py): the route answers 200 with usage numbers for both aliases, 401 for a request with no token and 404 for
an alias that does not exist. Not tried on the service: this app's own identity, which has the role only after the action aigateway has run with it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .config import Settings
from .http import AI_GATEWAY_CHAT_PATH, Client, HttpError
from .identity import IdentityError
from .redact import Redactor

# The audience of the gateway's tokens. A managed identity asks the platform for this resource (the scope of the same name with /.default is the same audience).
AUDIENCE = "https://azure-api.net/aigateway"
CHAT_TIMEOUT = 90
CHAT_RETRY_STATUSES = frozenset({429, 503})
NO_GATEWAY = "the AI Gateway's host name is not set"


class ModelError(Exception):
    """The AI Gateway or the model gave no usable answer. The text never holds the token."""


class ModelRefused(ModelError):
    """The AI Gateway itself refused the call: its token was not accepted, the identity has no role, or a limit is used up."""


@dataclass(frozen=True)
class Chat:
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class Models:
    def __init__(self, settings: Settings, client: Client, token: Callable[[str], str], redact: Redactor) -> None:
        self.settings, self.client, self.token, self.redact = settings, client, token, redact

    def open(self) -> None:
        """Nothing to read first: the app's identity is the credential, and there is no key. It stays so that a run starts the way it always did."""

    def chat(self, model: str, system: str, user: str, max_completion_tokens: int) -> Chat:
        host = self.settings.ai_gateway_host
        if not host:
            raise ModelError(NO_GATEWAY)
        body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_completion_tokens": max_completion_tokens}
        try:
            token = self.token(AUDIENCE)
        except IdentityError as error:
            raise ModelError(f"no token could be had for the AI Gateway ({self.redact(error)})") from None
        self.redact.add(token)
        try:
            # A call whose answer did not arrive may have been carried out and paid for, so only a refusal that says "not now" (429, 503) is repeated.
            response = self.client.request("POST", f"https://{host}{AI_GATEWAY_CHAT_PATH}", headers={"Authorization": f"Bearer {token}"}, body=body, timeout=CHAT_TIMEOUT, retries=2,
                                           retry_after_max=60, retry_statuses=CHAT_RETRY_STATUSES, retry_network=False)
        except HttpError as error:
            raise self._failure(model, error) from error
        return self._read(response.json())

    @staticmethod
    def _failure(model: str, error: HttpError) -> ModelError:
        """What a failed call says, in plain words: what the gateway answered and what usually causes it (the text of the error is already redacted by the client)."""
        if error.status == 401:
            return ModelRefused(f"the AI Gateway did not accept the app's token ({error}): the audience is {AUDIENCE}")
        if error.status == 403:
            return ModelRefused(f"the AI Gateway refused the app's identity ({error}): it needs the role AI Gateway Models User on the gateway, and a new role takes up to ten minutes to apply")
        if error.status == 429:
            return ModelRefused(f"the AI Gateway told the call to wait ({error}): a limit of the gateway or of the model deployment")
        if error.status == 404:
            return ModelError(f"the AI Gateway knows no alias named {model} ({error}): the aliases are the names of the model deployments")
        if error.status == 400:
            return ModelError(f"the AI Gateway did not accept the call ({error}): check that {model} is an alias that takes chat completions, and the content safety of the gateway")
        return ModelError(f"the AI Gateway gave no answer to the model call ({error})")

    @staticmethod
    def _read(data: object) -> Chat:
        try:
            choice = data["choices"][0]  # type: ignore[index]
            text = choice["message"]["content"]
            usage = data.get("usage") or {}  # type: ignore[union-attr]
            prompt, completion, total = (int(usage.get(name, 0)) for name in ("prompt_tokens", "completion_tokens", "total_tokens"))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as error:
            raise ModelError("the answer of the AI Gateway is not a completion") from error
        if min(prompt, completion, total) < 0:
            raise ModelError("the answer of the AI Gateway reports a usage that is not valid")
        if not isinstance(text, str) or not text.strip():
            reason = choice.get("finish_reason") if isinstance(choice, dict) else None
            raise ModelError("the model gave no text" + (" (it used its whole completion budget on its reasoning)" if reason == "length" else ""))
        return Chat(text, prompt, completion, max(total, prompt + completion))
