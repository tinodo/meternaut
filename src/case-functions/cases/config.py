"""The settings of the app, read from the environment. environment/cases/main.bicep sets them; a test holds the two together."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Mapping

AZURE_CLIENT_ID = "AZURE_CLIENT_ID"
SCOPE_SUBSCRIPTIONS = "SCOPE_SUBSCRIPTIONS"
GATEWAY_URL = "GATEWAY_URL"
GATEWAY_PRODUCT_SUBSCRIPTION_ID = "GATEWAY_PRODUCT_SUBSCRIPTION_ID"
MODEL_DETECTIVE = "MODEL_DETECTIVE"
MODEL_SKEPTIC = "MODEL_SKEPTIC"
MAX_CASES_PER_RUN = "MAX_CASES_PER_RUN"
EVENTHUB_CASES_CONTROL_NAME = "EVENTHUB_CASES_CONTROL_NAME"

# Settings with a default, which the template may leave out.
MAX_TOKENS_PER_RUN = "MAX_TOKENS_PER_RUN"
MAX_COMPLETION_TOKENS = "MAX_COMPLETION_TOKENS"
RUN_DEADLINE_SECONDS = "RUN_DEADLINE_SECONDS"

REQUIRED = (AZURE_CLIENT_ID, SCOPE_SUBSCRIPTIONS, GATEWAY_URL, GATEWAY_PRODUCT_SUBSCRIPTION_ID, MODEL_DETECTIVE, MODEL_SKEPTIC, MAX_CASES_PER_RUN,
            EVENTHUB_CASES_CONTROL_NAME)
OPTIONAL = {MAX_TOKENS_PER_RUN: "40000", MAX_COMPLETION_TOKENS: "2000", RUN_DEADLINE_SECONDS: "900"}

GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
GATEWAY = re.compile(r"^https://([a-z0-9][a-z0-9-]{0,48}[a-z0-9])\.azure-api\.net/?$")
PRODUCT_SUBSCRIPTION = re.compile(
    r"^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9._()-]{1,90}/providers/Microsoft\.ApiManagement/service/[A-Za-z0-9-]{1,50}/subscriptions/[A-Za-z0-9_-]{1,80}$")
MODEL = re.compile(r"^[a-z0-9][a-z0-9.-]{1,63}$")


class ConfigError(Exception):
    """One or more settings are missing or wrong; the text lists every one, never a value of a secret (there is none)."""


@dataclass(frozen=True)
class Settings:
    client_id: str
    subscriptions: tuple[str, ...]
    gateway_url: str
    gateway_host: str
    product_subscription_id: str
    model_detective: str
    model_skeptic: str
    max_cases: int
    max_tokens_per_run: int
    max_completion_tokens: int
    deadline_seconds: int


def _integer(env: Mapping[str, str], name: str, low: int, high: int, default: str, problems: list[str]) -> int:
    raw = env.get(name) or default
    try:
        value = int(raw)
    except ValueError:
        problems.append(f"{name} is not a whole number")
        return low
    if not low <= value <= high:
        problems.append(f"{name} is not between {low} and {high}")
    return value


def load(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    problems = [f"{name} is not set" for name in REQUIRED if not env.get(name)]
    subscriptions = tuple(part.strip().lower() for part in env.get(SCOPE_SUBSCRIPTIONS, "").split(",") if part.strip())
    if env.get(SCOPE_SUBSCRIPTIONS) and not all(GUID.match(s) for s in subscriptions):
        problems.append(f"{SCOPE_SUBSCRIPTIONS} is a comma separated list of subscription ids")
    if env.get(AZURE_CLIENT_ID) and not GUID.match(env[AZURE_CLIENT_ID]):
        problems.append(f"{AZURE_CLIENT_ID} is a client id")
    gateway = GATEWAY.match(env.get(GATEWAY_URL, ""))
    if env.get(GATEWAY_URL) and not gateway:
        problems.append(f"{GATEWAY_URL} is https://<name>.azure-api.net")
    if env.get(GATEWAY_PRODUCT_SUBSCRIPTION_ID) and not PRODUCT_SUBSCRIPTION.match(env[GATEWAY_PRODUCT_SUBSCRIPTION_ID]):
        problems.append(f"{GATEWAY_PRODUCT_SUBSCRIPTION_ID} is the resource id of one subscription of the gateway")
    for name in (MODEL_DETECTIVE, MODEL_SKEPTIC):
        if env.get(name) and not MODEL.match(env[name]):
            problems.append(f"{name} is a model name")
    max_cases = _integer(env, MAX_CASES_PER_RUN, 1, 10, "3", problems)
    max_tokens = _integer(env, MAX_TOKENS_PER_RUN, 1000, 200000, OPTIONAL[MAX_TOKENS_PER_RUN], problems)
    max_completion = _integer(env, MAX_COMPLETION_TOKENS, 100, 8000, OPTIONAL[MAX_COMPLETION_TOKENS], problems)
    deadline = _integer(env, RUN_DEADLINE_SECONDS, 60, 3600, OPTIONAL[RUN_DEADLINE_SECONDS], problems)
    if problems or gateway is None:
        raise ConfigError("; ".join(problems))
    host = gateway.group(1)
    return Settings(
        client_id=env[AZURE_CLIENT_ID],
        subscriptions=subscriptions,
        gateway_url=f"https://{host}.azure-api.net",
        gateway_host=f"{host}.azure-api.net",
        product_subscription_id=env[GATEWAY_PRODUCT_SUBSCRIPTION_ID],
        model_detective=env[MODEL_DETECTIVE],
        model_skeptic=env[MODEL_SKEPTIC],
        max_cases=max_cases,
        max_tokens_per_run=max_tokens,
        max_completion_tokens=max_completion,
        deadline_seconds=deadline,
    )
