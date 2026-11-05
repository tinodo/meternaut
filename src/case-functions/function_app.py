"""Entry point of the function app (Python v2 programming model). Wiring only: the logic is in the cases package."""
import azure.functions as func

from cases import console, control, loop, run

app = func.FunctionApp()

# Every day at 05:30 UTC.
TIMER_SCHEDULE = "0 30 5 * * *"
# Every minute: the plans whose time is over, the changes whose start time has come, the changes to check.
TICK_SCHEDULE = "0 * * * * *"
# Identity-based connection. The platform reads EventHubConnection__fullyQualifiedNamespace, __credential and __clientId.
EVENT_HUB_CONNECTION = "EventHubConnection"


@app.function_name(name="watch-daily")
@app.timer_trigger(arg_name="timer", schedule=TIMER_SCHEDULE, run_on_startup=False)
def watch_daily(timer: func.TimerRequest) -> None:
    run.run_watch("timer", None)


@app.function_name(name="cases-control")
@app.event_hub_message_trigger(
    arg_name="event",
    event_hub_name="%EVENTHUB_CASES_CONTROL_NAME%",
    connection=EVENT_HUB_CONNECTION,
    consumer_group="casesControl",
    cardinality="one",
)
def cases_control(event: func.EventHubEvent) -> None:
    control.handle_event(event)


@app.function_name(name="runner-tick")
@app.timer_trigger(arg_name="timer", schedule=TICK_SCHEDULE, run_on_startup=False)
def runner_tick(timer: func.TimerRequest) -> None:
    loop.tick()


# Every page of the console. The platform's sign-in stands in front of it (anonymous here means "no function key": a key would be a secret), and the
# app refuses every request unless that sign-in is on.
@app.function_name(name="console")
@app.route(route="{*route}", methods=["GET", "POST"], auth_level=func.AuthLevel.ANONYMOUS)
def console_page(req: func.HttpRequest) -> func.HttpResponse:
    return console.handle(req, func.HttpResponse)
