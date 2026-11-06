"""The settings of the app, read from the environment. environment/cases/main.bicep sets them; a test holds the two together."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Mapping

from .http import FOUNDRY_ENDPOINT

AZURE_CLIENT_ID = "AZURE_CLIENT_ID"
SCOPE_SUBSCRIPTIONS = "SCOPE_SUBSCRIPTIONS"
GATEWAY_URL = "GATEWAY_URL"
GATEWAY_PRODUCT_SUBSCRIPTION_ID = "GATEWAY_PRODUCT_SUBSCRIPTION_ID"
MODEL_DETECTIVE = "MODEL_DETECTIVE"
MODEL_SKEPTIC = "MODEL_SKEPTIC"
MAX_CASES_PER_RUN = "MAX_CASES_PER_RUN"
EVENTHUB_CASES_CONTROL_NAME = "EVENTHUB_CASES_CONTROL_NAME"

LIMIT_CASES = 3
LIMIT_TOKENS_PER_RUN = 40000
LIMIT_COMPLETION_TOKENS = 2000
LIMIT_DEADLINE_SECONDS = 900

# Settings with a default, which the template may leave out. The limits of the proposal are ceilings: a setting can lower them and never raise them.
MAX_TOKENS_PER_RUN = "MAX_TOKENS_PER_RUN"
MAX_COMPLETION_TOKENS = "MAX_COMPLETION_TOKENS"
RUN_DEADLINE_SECONDS = "RUN_DEADLINE_SECONDS"

# The investigation by agents in Microsoft Foundry. All of it is optional: without FOUNDRY_PROJECT_ENDPOINT the app does not investigate. Its limits are ceilings too.
FOUNDRY_PROJECT_ENDPOINT = "FOUNDRY_PROJECT_ENDPOINT"
FOUNDRY_MODEL_INVESTIGATOR = "FOUNDRY_MODEL_INVESTIGATOR"
FOUNDRY_MODEL_SKEPTIC = "FOUNDRY_MODEL_SKEPTIC"
INVESTIGATE = "INVESTIGATE"
INVESTIGATE_MAX_CALLS = "INVESTIGATE_MAX_CALLS"
INVESTIGATE_MAX_SECONDS = "INVESTIGATE_MAX_SECONDS"

DEFAULT_MODEL_INVESTIGATOR = "gpt-6.1-sol"
DEFAULT_MODEL_SKEPTIC = "gpt-6-luna"
DEFAULT_INVESTIGATE_CALLS = 24
LIMIT_INVESTIGATE_CALLS = 40
DEFAULT_INVESTIGATE_SECONDS = 420
LIMIT_INVESTIGATE_SECONDS = 600

REQUIRED = (AZURE_CLIENT_ID, SCOPE_SUBSCRIPTIONS, GATEWAY_URL, GATEWAY_PRODUCT_SUBSCRIPTION_ID, MODEL_DETECTIVE, MODEL_SKEPTIC, MAX_CASES_PER_RUN,
            EVENTHUB_CASES_CONTROL_NAME)
OPTIONAL = {MAX_TOKENS_PER_RUN: str(LIMIT_TOKENS_PER_RUN), MAX_COMPLETION_TOKENS: str(LIMIT_COMPLETION_TOKENS), RUN_DEADLINE_SECONDS: str(LIMIT_DEADLINE_SECONDS),
            FOUNDRY_MODEL_INVESTIGATOR: DEFAULT_MODEL_INVESTIGATOR, FOUNDRY_MODEL_SKEPTIC: DEFAULT_MODEL_SKEPTIC,
            INVESTIGATE_MAX_CALLS: str(DEFAULT_INVESTIGATE_CALLS), INVESTIGATE_MAX_SECONDS: str(DEFAULT_INVESTIGATE_SECONDS)}

GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
GATEWAY = re.compile(r"^https://([a-z0-9][a-z0-9-]{0,48}[a-z0-9])\.azure-api\.net/?$")
PRODUCT_SUBSCRIPTION = re.compile(
    r"^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9._()-]{1,90}/providers/Microsoft\.ApiManagement/service/[A-Za-z0-9-]{1,50}/subscriptions/[A-Za-z0-9_-]{1,80}$")
MODEL = re.compile(r"^[a-z0-9][a-z0-9.-]{1,63}$")
# The name of a model deployment in a Foundry project.
DEPLOYMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
SWITCH_ON = ("1", "true", "on", "yes")
SWITCH_OFF = ("0", "false", "off", "no")


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
    foundry_endpoint: str | None = None
    foundry_model_investigator: str = DEFAULT_MODEL_INVESTIGATOR
    foundry_model_skeptic: str = DEFAULT_MODEL_SKEPTIC
    investigate: bool = False
    investigate_max_calls: int = DEFAULT_INVESTIGATE_CALLS
    investigate_max_seconds: int = DEFAULT_INVESTIGATE_SECONDS


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


def _switch(env: Mapping[str, str], name: str, default: bool, problems: list[str]) -> bool:
    raw = (env.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in SWITCH_ON or raw in SWITCH_OFF:
        return raw in SWITCH_ON
    problems.append(f"{name} is on or off")
    return default


def _investigation(env: Mapping[str, str], problems: list[str]) -> dict:
    """The optional settings of the investigation, as the keyword arguments of Settings. A problem is added to `problems`, never raised."""
    raw = env.get(FOUNDRY_PROJECT_ENDPOINT) or ""
    endpoint = raw[:-1] if raw.endswith("/") else raw
    if endpoint and not FOUNDRY_ENDPOINT.fullmatch(endpoint):
        problems.append(f"{FOUNDRY_PROJECT_ENDPOINT} is https://<account>.services.ai.azure.com/api/projects/<project>")
        endpoint = ""
    investigator = env.get(FOUNDRY_MODEL_INVESTIGATOR) or OPTIONAL[FOUNDRY_MODEL_INVESTIGATOR]
    skeptic = env.get(FOUNDRY_MODEL_SKEPTIC) or OPTIONAL[FOUNDRY_MODEL_SKEPTIC]
    for name, value in ((FOUNDRY_MODEL_INVESTIGATOR, investigator), (FOUNDRY_MODEL_SKEPTIC, skeptic)):
        if not DEPLOYMENT.fullmatch(value):
            problems.append(f"{name} is a model name")
    if investigator.lower() == skeptic.lower():
        problems.append(f"{FOUNDRY_MODEL_INVESTIGATOR} and {FOUNDRY_MODEL_SKEPTIC} are the same model, and the Skeptic has to be another model than the Investigator")
    investigate = _switch(env, INVESTIGATE, bool(endpoint), problems)
    if investigate and not raw:
        problems.append(f"{INVESTIGATE} is on and {FOUNDRY_PROJECT_ENDPOINT} is not set")
    return {
        "foundry_endpoint": endpoint or None,
        "foundry_model_investigator": investigator,
        "foundry_model_skeptic": skeptic,
        "investigate": investigate,
        "investigate_max_calls": _integer(env, INVESTIGATE_MAX_CALLS, 1, LIMIT_INVESTIGATE_CALLS, OPTIONAL[INVESTIGATE_MAX_CALLS], problems),
        "investigate_max_seconds": _integer(env, INVESTIGATE_MAX_SECONDS, 30, LIMIT_INVESTIGATE_SECONDS, OPTIONAL[INVESTIGATE_MAX_SECONDS], problems),
    }


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
    if env.get(MODEL_DETECTIVE) and env.get(MODEL_DETECTIVE) == env.get(MODEL_SKEPTIC):
        problems.append(f"{MODEL_DETECTIVE} and {MODEL_SKEPTIC} are the same model, and the Skeptic has to be another model than the Detective")
    max_cases = _integer(env, MAX_CASES_PER_RUN, 1, LIMIT_CASES, str(LIMIT_CASES), problems)
    max_tokens = _integer(env, MAX_TOKENS_PER_RUN, 1000, LIMIT_TOKENS_PER_RUN, OPTIONAL[MAX_TOKENS_PER_RUN], problems)
    max_completion = _integer(env, MAX_COMPLETION_TOKENS, 100, LIMIT_COMPLETION_TOKENS, OPTIONAL[MAX_COMPLETION_TOKENS], problems)
    deadline = _integer(env, RUN_DEADLINE_SECONDS, 60, LIMIT_DEADLINE_SECONDS, OPTIONAL[RUN_DEADLINE_SECONDS], problems)
    investigation = _investigation(env, problems)
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
        **investigation,
    )
