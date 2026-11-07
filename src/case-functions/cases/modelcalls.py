"""The model calls of the Detective and the Skeptic: a chat completion of a model deployment of the agents' own Foundry resource.

Every model call of Meternaut goes direct, privately and with no key, to a deployment of its own Foundry resource, the way the agents' calls do (AGENTS.md rule 15 (c)): a POST of
`/openai/v1/chat/completions` with the app's own managed identity's token for the resource https://ai.azure.com. The first route is the project's, on the project endpoint that the
agents use. Nothing here reads a key, and the token is registered for redaction so that no error text can hold it.

Read on Microsoft Learn on 2026-11-07 and NOT TRIED ON THE SERVICE until the first `cases-run`. The project's route is the documented one: "Use reasoning models with Microsoft Foundry Models"
(https://learn.microsoft.com/azure/foundry/foundry-models/how-to/use-chat-reasoning) calls an OpenAI client whose base is the PROJECT endpoint plus `/openai/v1`
(https://<resource>.services.ai.azure.com/api/projects/<project>/openai/v1/chat/completions), with the token scope https://ai.azure.com/.default, and `model` is the deployment's name. The
resource's own route (https://<resource>.services.ai.azure.com/openai/v1/chat/completions, which the pages of the single models show) stays only as the fallback: a 404 or a 405 from the
project's route sends the call, once, to it (the same host, the same token), and the route that answers is the one used for the rest of the run. The first `cases-run` shows which one the
service takes. A failure says which routes were asked and what each answered, in plain words, and never holds the token.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .config import Settings
from .foundry import RESOURCE
from .http import CHAT_PATH, Client, HttpError, resource_of
from .identity import IdentityError
from .redact import Redactor

CHAT_TIMEOUT = 90
CHAT_RETRY_STATUSES = frozenset({429, 503})
# What a route that the service does not serve answers: the call was not carried out, so the other route may be asked.
ROUTE_NOT_SERVED = frozenset({404, 405})
NO_ENDPOINT = "the Foundry project's address is not set"


class ModelError(Exception):
    """The Foundry project or the model gave no usable answer. The text never holds the token."""


class ModelRefused(ModelError):
    """The Foundry resource itself refused the call: the allowance is used up, or the identity or the model is not allowed."""


@dataclass(frozen=True)
class Chat:
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class Models:
    def __init__(self, settings: Settings, client: Client, token: Callable[[str], str], redact: Redactor) -> None:
        self.settings, self.client, self.token, self.redact = settings, client, token, redact
        self._first = 0  # the route that answered last: the call starts there

    def open(self) -> None:
        """Nothing to read first: the app's identity is the credential, and there is no key. It stays so that a run starts the way it always did."""

    def routes(self) -> list[tuple[str, str]]:
        """(what it is called in an error text, its address): the project's route, then the resource's. Empty when the project's address is not set."""
        endpoint = self.settings.foundry_endpoint
        if not endpoint:
            return []
        return [("the project's route", f"{endpoint}{CHAT_PATH}"), ("the resource's route", f"{resource_of(endpoint)}{CHAT_PATH}")]

    def chat(self, model: str, system: str, user: str, max_completion_tokens: int) -> Chat:
        routes = self.routes()
        if not routes:
            raise ModelError(NO_ENDPOINT)
        body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_completion_tokens": max_completion_tokens}
        try:
            token = self.token(RESOURCE)
        except IdentityError as error:
            raise ModelError(f"no token could be had for the model service ({self.redact(error)})") from None
        self.redact.add(token)
        missed: list[tuple[str, HttpError]] = []
        for index in list(range(self._first, len(routes))) + list(range(self._first)):
            name, url = routes[index]
            try:
                # A call whose answer did not arrive may have been carried out and paid for, so only a refusal that says "not now" (429, 503) is repeated.
                response = self.client.request("POST", url, headers={"Authorization": f"Bearer {token}"}, body=body, timeout=CHAT_TIMEOUT, retries=2, retry_after_max=60,
                                               retry_statuses=CHAT_RETRY_STATUSES, retry_network=False)
            except HttpError as error:
                if error.status in ROUTE_NOT_SERVED:
                    missed.append((name, error))
                    continue
                raise self._failure(model, name, error) from error
            self._first = index
            return self._read(response.json())
        raise self._not_served(model, missed) from missed[-1][1]

    @staticmethod
    def _failure(model: str, route: str, error: HttpError) -> ModelError:
        """What a failed call says, in plain words: which route was asked, and what the service answered (already redacted by the client)."""
        if error.status in (401, 403, 429):
            return ModelRefused(f"the Foundry resource refused the model call on {route} ({error})")
        if error.status == 400:
            return ModelError(f"{route} (POST {CHAT_PATH}) did not accept the call: check that {model} is a deployment of the resource and that it takes chat completions ({error})")
        return ModelError(f"the Foundry resource gave no answer to the model call on {route} ({error})")

    @staticmethod
    def _not_served(model: str, missed: list[tuple[str, HttpError]]) -> ModelError:
        said = " and ".join(f"{name} answered {error.status}" for name, error in missed)
        return ModelError(f"no chat completions route took the call: POST {CHAT_PATH}, {said}. Check that {model} is a deployment of the resource ({missed[-1][1]})")

    @staticmethod
    def _read(data: object) -> Chat:
        try:
            choice = data["choices"][0]  # type: ignore[index]
            text = choice["message"]["content"]
            usage = data.get("usage") or {}  # type: ignore[union-attr]
            prompt, completion, total = (int(usage.get(name, 0)) for name in ("prompt_tokens", "completion_tokens", "total_tokens"))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as error:
            raise ModelError("the answer of the Foundry resource is not a completion") from error
        if min(prompt, completion, total) < 0:
            raise ModelError("the answer of the Foundry resource reports a usage that is not valid")
        if not isinstance(text, str) or not text.strip():
            reason = choice.get("finish_reason") if isinstance(choice, dict) else None
            raise ModelError("the model gave no text" + (" (it used its whole completion budget on its reasoning)" if reason == "length" else ""))
        return Chat(text, prompt, completion, max(total, prompt + completion))
