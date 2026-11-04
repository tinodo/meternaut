"""App settings. In Azure they are the app settings of the function app; the code reads them as environment variables.

The Event Hub names and the Event Hub connection are not read here: the platform resolves them from the trigger bindings.
"""
import os
from collections.abc import Mapping, Sequence

AZURE_CLIENT_ID = "AZURE_CLIENT_ID"
COSMOS_ENDPOINT = "COSMOS_ENDPOINT"
COSMOS_DATABASE = "COSMOS_DATABASE"
COSMOS_CONTAINER_CONFIG = "COSMOS_CONTAINER_CONFIG"
COSMOS_CONTAINER_AI_USAGE = "COSMOS_CONTAINER_AI_USAGE"
COSMOS_CONTAINER_PII_USAGE = "COSMOS_CONTAINER_PII_USAGE"
COSMOS_CONTAINER_LLM_USAGE = "COSMOS_CONTAINER_LLM_USAGE"
COSMOS_CONTAINER_MCP_USAGE = "COSMOS_CONTAINER_MCP_USAGE"
COSMOS_CONTAINER_AGENT_USAGE = "COSMOS_CONTAINER_AGENT_USAGE"
GATEWAY_APPINSIGHTS_ID = "GATEWAY_APPINSIGHTS_ID"


class ConfigError(RuntimeError):
    """A required app setting is missing or empty."""


def get_settings(names: Sequence[str], env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return the values of the named settings. The error names every setting that is missing."""
    source = os.environ if env is None else env
    values = {name: (source.get(name) or "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigError("Missing required app setting(s): " + ", ".join(missing))
    return values
