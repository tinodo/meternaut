"""Entry point of the function app (Python v2 programming model). Wiring only: the logic is in the usage package."""
from typing import List

import azure.functions as func

from usage import control, events, jobs

app = func.FunctionApp()

# Hours 3, 6, 9, 12, 15, 18, 21 and 23, UTC.
TIMER_SCHEDULE = "0 0 3,6,9,12,15,18,21,23 * * *"
# Identity-based connection. The platform reads EventHubConnection__fullyQualifiedNamespace and __credential; __clientId names a user-assigned identity, and
# without it the connection uses the app's system-assigned identity.
EVENT_HUB_CONNECTION = "EventHubConnection"


@app.function_name(name="llm-usage-ingestion")
@app.timer_trigger(arg_name="timer", schedule=TIMER_SCHEDULE, run_on_startup=False)
def llm_usage_ingestion(timer: func.TimerRequest) -> None:
    jobs.run_scheduled(jobs.LLM_JOB.name)


@app.function_name(name="mcp-usage-ingestion")
@app.timer_trigger(arg_name="timer", schedule=TIMER_SCHEDULE, run_on_startup=False)
def mcp_usage_ingestion(timer: func.TimerRequest) -> None:
    jobs.run_scheduled(jobs.MCP_JOB.name)


@app.function_name(name="agent-usage-ingestion")
@app.timer_trigger(arg_name="timer", schedule=TIMER_SCHEDULE, run_on_startup=False)
def agent_usage_ingestion(timer: func.TimerRequest) -> None:
    jobs.run_scheduled(jobs.AGENT_JOB.name)


# The batch type is typing.List, as in the Microsoft Learn samples of the Event Hubs trigger.
@app.function_name(name="ai-usage-ingestion")
@app.event_hub_message_trigger(
    arg_name="batch",
    event_hub_name="%EVENTHUB_USAGE_NAME%",
    connection=EVENT_HUB_CONNECTION,
    consumer_group="aiUsageIngestion",
    cardinality="many",
)
def ai_usage_ingestion(batch: List[func.EventHubEvent]) -> None:
    events.ingest_ai(batch)


@app.function_name(name="pii-usage-ingestion")
@app.event_hub_message_trigger(
    arg_name="batch",
    event_hub_name="%EVENTHUB_PII_NAME%",
    connection=EVENT_HUB_CONNECTION,
    consumer_group="piiUsageIngestion",
    cardinality="many",
)
def pii_usage_ingestion(batch: List[func.EventHubEvent]) -> None:
    events.ingest_pii(batch)


@app.function_name(name="usage-control")
@app.event_hub_message_trigger(
    arg_name="batch",
    event_hub_name="%EVENTHUB_CONTROL_NAME%",
    connection=EVENT_HUB_CONNECTION,
    consumer_group="usageControl",
    cardinality="many",
)
def usage_control(batch: List[func.EventHubEvent]) -> None:
    control.handle_events(batch)
