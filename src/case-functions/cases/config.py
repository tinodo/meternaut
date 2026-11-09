"""The settings of the app, read from the environment. environment/cases/main.bicep sets them; a test holds the two together."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Mapping

from .http import AI_GATEWAY_HOST, FOUNDRY_ENDPOINT

# The client id of a user-assigned managed identity that the app runs as. Not set or empty: the app runs as its own system-assigned identity, which is what
# the platform's token endpoint answers for when no client id is asked for.
AZURE_CLIENT_ID = "AZURE_CLIENT_ID"
# The subscriptions that the Watch reads, as a comma separated list of ids.
SCOPE_SUBSCRIPTIONS = "SCOPE_SUBSCRIPTIONS"
# On: the Watch reads every subscription that its own identity can read (the list that Azure Resource Manager gives it, made once at the start of a run), so a person widens or
# narrows what it watches by the roles that they give the identity, at a subscription or at a management group above it (scope.py). SCOPE_SUBSCRIPTIONS is then optional, and when it is
# given it is what the Watch reads if that list cannot be had. Off or not set: only SCOPE_SUBSCRIPTIONS.
SCOPE_ALL_SUBSCRIPTIONS = "SCOPE_ALL_SUBSCRIPTIONS"
MODEL_DETECTIVE = "MODEL_DETECTIVE"
MODEL_SKEPTIC = "MODEL_SKEPTIC"
# The host of the AI Gateway (the service reports it as properties.frontend.defaultHostname; the workflow reads it from the service and environment/cases/main.bicep sets it). Every model call of
# the Detective and the Skeptic goes to it, and to no other address (AGENTS.md rule 15 (c)), so the Watch does not start without it. MODEL_DETECTIVE and MODEL_SKEPTIC name aliases of the gateway,
# which have the names of the deployments (environment/aigateway/main.bicep).
AIGATEWAY_HOST = "AIGATEWAY_HOST"
MAX_CASES_PER_RUN = "MAX_CASES_PER_RUN"
# The name of the Storage queue in the host storage account that carries the control message (one message starts one Watch now). The queue trigger reads it as %CASES_CONTROL_QUEUE_NAME%
# (function_app.py), so the Watch does not start without it.
CASES_CONTROL_QUEUE_NAME = "CASES_CONTROL_QUEUE_NAME"

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
# How many days the daily timer waits after an investigation that ran before it investigates again. A run costs about two US dollars of model calls, and the standing limit of the AI Gateway
# is 5 a day and 25 a month for each caller (rule 15 (g)): investigating every day would use the month's allowance in about twelve days. A run that a person starts always investigates; the
# leads of the fixed detectors are judged by the Detective and the Skeptic every day anyway, which costs cents.
INVESTIGATE_EVERY_DAYS = "INVESTIGATE_EVERY_DAYS"
DEFAULT_INVESTIGATE_EVERY_DAYS = 7
LIMIT_INVESTIGATE_EVERY_DAYS = 30
# The tokens that one agent run may use before the harness stops it (cases/harness.py): a brake against a loop in a model, not a limit of normal work. The fourth real run of the agents
# (2026-11-08) used about 169,000 tokens in all; this is about three and a half times that, written here before it was measured again. A setting can lower it and never raise it.
INVESTIGATE_MAX_TOKENS = "INVESTIGATE_MAX_TOKENS"

# The Investigator is gpt-5.5 (no effort sent: see INVESTIGATOR_REASONING_EFFORT in agents.py) and the Skeptic gpt-6.1-sol: see AGENT_MODELS in tools/environment-params.py for why, and a test holds the files together.
DEFAULT_MODEL_INVESTIGATOR = "gpt-5.5"
DEFAULT_MODEL_SKEPTIC = "gpt-6.1-sol"
DEFAULT_INVESTIGATE_CALLS = 40
LIMIT_INVESTIGATE_CALLS = 40
DEFAULT_INVESTIGATE_SECONDS = 600
LIMIT_INVESTIGATE_SECONDS = 600
LIMIT_INVESTIGATE_TOKENS = 600_000

# SCOPE_SUBSCRIPTIONS is required unless SCOPE_ALL_SUBSCRIPTIONS is on (load below): the template always sets it, as the fallback.
REQUIRED = (SCOPE_SUBSCRIPTIONS, MODEL_DETECTIVE, MODEL_SKEPTIC, AIGATEWAY_HOST, MAX_CASES_PER_RUN, CASES_CONTROL_QUEUE_NAME)

# The Study (cases/study.py): the Scholar reads Microsoft's documentation about the kinds of resource that the estate has, once a week. It is off until STUDY is on, it needs the Foundry project
# like the investigation, and it stops when the switch `all` or the switch `investigation` is pulled. Its limits are ceilings too: a setting can lower them and never raise them.
STUDY = "STUDY"
STUDY_MAX_TYPES = "STUDY_MAX_TYPES"
STUDY_MAX_PAGES = "STUDY_MAX_PAGES"
STUDY_MAX_SECONDS = "STUDY_MAX_SECONDS"
STUDY_MAX_TOKENS = "STUDY_MAX_TOKENS"
DEFAULT_STUDY_TYPES = 4
LIMIT_STUDY_TYPES = 8
DEFAULT_STUDY_PAGES = 8
LIMIT_STUDY_PAGES = 16
DEFAULT_STUDY_SECONDS = 300
LIMIT_STUDY_SECONDS = 600
# The tokens that the Scholar may use in one run before the harness stops it: a brake against a loop in a model. A run of 24 tool calls that reads pages of about 3,500 characters uses about 300,000
# tokens (a model reads everything said so far again at every step, so the use grows with the square of the calls); the brake is a third more, written before a real run measured it.
DEFAULT_STUDY_TOKENS = 400_000
LIMIT_STUDY_TOKENS = 800_000

# The hold of the learning (cases/learning.py, hold): a proposal that past requests like it rarely saw approved goes to a person as a finding that needs one. It is off until LEARNING_HOLD is on,
# because the first run of tools/learning-check.py missed its thresholds (docs/proposals/15-learning.md): what is not shown to help is not switched on. The lessons, the line of the decision
# brief and the tools that recall are not behind it: they count and they decide nothing.
LEARNING_HOLD = "LEARNING_HOLD"

OPTIONAL = {MAX_TOKENS_PER_RUN: str(LIMIT_TOKENS_PER_RUN), MAX_COMPLETION_TOKENS: str(LIMIT_COMPLETION_TOKENS), RUN_DEADLINE_SECONDS: str(LIMIT_DEADLINE_SECONDS),
            FOUNDRY_MODEL_INVESTIGATOR: DEFAULT_MODEL_INVESTIGATOR, FOUNDRY_MODEL_SKEPTIC: DEFAULT_MODEL_SKEPTIC,
            INVESTIGATE_MAX_CALLS: str(DEFAULT_INVESTIGATE_CALLS), INVESTIGATE_MAX_SECONDS: str(DEFAULT_INVESTIGATE_SECONDS), INVESTIGATE_MAX_TOKENS: str(LIMIT_INVESTIGATE_TOKENS),
            INVESTIGATE_EVERY_DAYS: str(DEFAULT_INVESTIGATE_EVERY_DAYS),
            STUDY_MAX_TYPES: str(DEFAULT_STUDY_TYPES), STUDY_MAX_PAGES: str(DEFAULT_STUDY_PAGES), STUDY_MAX_SECONDS: str(DEFAULT_STUDY_SECONDS), STUDY_MAX_TOKENS: str(DEFAULT_STUDY_TOKENS)}

GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
# The name of a model of the Detective and the Skeptic: an alias of the AI Gateway, which has the name of the model deployment of the agents' own Foundry resource, and so do the agents.
MODEL = re.compile(r"^[a-z0-9][a-z0-9.-]{1,63}$")
# The name of a model deployment in a Foundry project.
DEPLOYMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
# What an agent names as its model: a deployment of the project, or `<connection>/<model>` for a model behind a connection of the project, which is how the agents reach the AI Gateway
# (docs/proposals/08-ai-gateway.md, step 2). Each part is a DEPLOYMENT, and nothing else is allowed: one slash at most, and no empty part.
AGENT_MODEL = re.compile(rf"{DEPLOYMENT.pattern}(?:/{DEPLOYMENT.pattern})?")
SWITCH_ON = ("1", "true", "on", "yes")
SWITCH_OFF = ("0", "false", "off", "no")


class ConfigError(Exception):
    """One or more settings are missing or wrong; the text lists every one, never a value of a secret (there is none)."""


@dataclass(frozen=True)
class Settings:
    client_id: str  # empty: the system-assigned identity of the app
    subscriptions: tuple[str, ...]
    model_detective: str
    model_skeptic: str
    max_cases: int
    max_tokens_per_run: int
    max_completion_tokens: int
    deadline_seconds: int
    # The host of the AI Gateway: the only address of a model call. Empty only in a Settings that a test builds by hand (a chat then refuses to start); load() never gives an empty one.
    ai_gateway_host: str = ""
    foundry_endpoint: str | None = None
    foundry_model_investigator: str = DEFAULT_MODEL_INVESTIGATOR
    foundry_model_skeptic: str = DEFAULT_MODEL_SKEPTIC
    investigate: bool = False
    investigate_max_calls: int = DEFAULT_INVESTIGATE_CALLS
    investigate_max_seconds: int = DEFAULT_INVESTIGATE_SECONDS
    investigate_max_tokens: int = LIMIT_INVESTIGATE_TOKENS
    investigate_every_days: int = DEFAULT_INVESTIGATE_EVERY_DAYS
    # True: `subscriptions` is only the fallback, and the list that a run reads is made at its start (scope.py). The run then works with a copy whose `subscriptions` is that list.
    all_subscriptions: bool = False
    # The quota ids of the subscriptions of the run, as the one list of subscriptions of the run gave them (scope.py): not a setting of the environment, the run fills them in its copy.
    quota_ids: tuple[str, ...] = ()
    # The Study (cases/study.py). Off unless STUDY is on; the limits are the ceilings of the Scholar's run.
    study: bool = False
    study_max_types: int = DEFAULT_STUDY_TYPES
    study_max_pages: int = DEFAULT_STUDY_PAGES
    study_max_seconds: int = DEFAULT_STUDY_SECONDS
    study_max_tokens: int = DEFAULT_STUDY_TOKENS
    # The hold of the learning (cases/learning.py, hold). Off unless LEARNING_HOLD is on.
    learning_hold: bool = False


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
        if not AGENT_MODEL.fullmatch(value):
            problems.append(f"{name} is a model name or <connection>/<model>")
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
        "investigate_max_tokens": _integer(env, INVESTIGATE_MAX_TOKENS, 10_000, LIMIT_INVESTIGATE_TOKENS, OPTIONAL[INVESTIGATE_MAX_TOKENS], problems),
        "investigate_every_days": _integer(env, INVESTIGATE_EVERY_DAYS, 1, LIMIT_INVESTIGATE_EVERY_DAYS, OPTIONAL[INVESTIGATE_EVERY_DAYS], problems),
    }


def _study(env: Mapping[str, str], endpoint: object, problems: list[str]) -> dict:
    """The optional settings of the Study, as the keyword arguments of Settings. It is off unless STUDY is on, and on needs the Foundry project like the investigation."""
    study = _switch(env, STUDY, False, problems)
    if study and not endpoint:
        problems.append(f"{STUDY} is on and {FOUNDRY_PROJECT_ENDPOINT} is not set")
    return {
        "study": study,
        "study_max_types": _integer(env, STUDY_MAX_TYPES, 1, LIMIT_STUDY_TYPES, OPTIONAL[STUDY_MAX_TYPES], problems),
        "study_max_pages": _integer(env, STUDY_MAX_PAGES, 1, LIMIT_STUDY_PAGES, OPTIONAL[STUDY_MAX_PAGES], problems),
        "study_max_seconds": _integer(env, STUDY_MAX_SECONDS, 30, LIMIT_STUDY_SECONDS, OPTIONAL[STUDY_MAX_SECONDS], problems),
        "study_max_tokens": _integer(env, STUDY_MAX_TOKENS, 10_000, LIMIT_STUDY_TOKENS, OPTIONAL[STUDY_MAX_TOKENS], problems),
    }


def load(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    problems: list[str] = []
    all_subscriptions = _switch(env, SCOPE_ALL_SUBSCRIPTIONS, False, problems)
    problems += [f"{name} is not set" for name in REQUIRED if not env.get(name) and not (name == SCOPE_SUBSCRIPTIONS and all_subscriptions)]
    subscriptions = tuple(part.strip().lower() for part in env.get(SCOPE_SUBSCRIPTIONS, "").split(",") if part.strip())
    if env.get(SCOPE_SUBSCRIPTIONS) and not all(GUID.match(s) for s in subscriptions):
        problems.append(f"{SCOPE_SUBSCRIPTIONS} is a comma separated list of subscription ids")
    client_id = (env.get(AZURE_CLIENT_ID) or "").strip()
    if client_id and not GUID.match(client_id):
        problems.append(f"{AZURE_CLIENT_ID} is a client id")
    for name in (MODEL_DETECTIVE, MODEL_SKEPTIC):
        if env.get(name) and not MODEL.match(env[name]):
            problems.append(f"{name} is a model name")
    if env.get(MODEL_DETECTIVE) and env.get(MODEL_DETECTIVE) == env.get(MODEL_SKEPTIC):
        problems.append(f"{MODEL_DETECTIVE} and {MODEL_SKEPTIC} are the same model, and the Skeptic has to be another model than the Detective")
    raw_host = env.get(AIGATEWAY_HOST) or ""
    gateway_host = raw_host.strip().lower()
    if raw_host and (not AI_GATEWAY_HOST.fullmatch(gateway_host) or len(gateway_host) > 253):
        problems.append(f"{AIGATEWAY_HOST} is the host name of the AI Gateway, under .ai.gateway.azure.com, without a scheme, a port or a path")
        gateway_host = ""
    max_cases = _integer(env, MAX_CASES_PER_RUN, 1, LIMIT_CASES, str(LIMIT_CASES), problems)
    max_tokens = _integer(env, MAX_TOKENS_PER_RUN, 1000, LIMIT_TOKENS_PER_RUN, OPTIONAL[MAX_TOKENS_PER_RUN], problems)
    max_completion = _integer(env, MAX_COMPLETION_TOKENS, 100, LIMIT_COMPLETION_TOKENS, OPTIONAL[MAX_COMPLETION_TOKENS], problems)
    deadline = _integer(env, RUN_DEADLINE_SECONDS, 60, LIMIT_DEADLINE_SECONDS, OPTIONAL[RUN_DEADLINE_SECONDS], problems)
    investigation = _investigation(env, problems)
    study = _study(env, investigation["foundry_endpoint"], problems)
    learning_hold = _switch(env, LEARNING_HOLD, False, problems)
    if problems:
        raise ConfigError("; ".join(problems))
    return Settings(
        client_id=client_id,
        subscriptions=subscriptions,
        model_detective=env[MODEL_DETECTIVE],
        model_skeptic=env[MODEL_SKEPTIC],
        max_cases=max_cases,
        max_tokens_per_run=max_tokens,
        max_completion_tokens=max_completion,
        deadline_seconds=deadline,
        ai_gateway_host=gateway_host,
        all_subscriptions=all_subscriptions,
        **investigation,
        **study,
        learning_hold=learning_hold,
    )
