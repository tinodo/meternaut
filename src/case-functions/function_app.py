"""Entry point of the function app (Python v2 programming model). Wiring only: the logic is in the cases package."""
import azure.functions as func

from cases import console, control, drift, harness, loop, run, study

app = func.FunctionApp()
harness.announce()  # one line of the telemetry when the app starts: which files run and which commit they were built from

# Every day at 05:30 UTC.
TIMER_SCHEDULE = "0 30 5 * * *"
# Every day at 05:10 UTC, twenty minutes before the Watch: the drift check reads what the agents are, and a failure that guards them holds the investigation of the Watch that follows.
DRIFT_SCHEDULE = "0 10 5 * * *"
# Every Monday at 04:30 UTC, before the drift check and the Watch of that day: the Study reads the documentation of the kinds of resource that the estate has and files what it says (it does
# nothing unless the setting STUDY is on, and nothing while the switch `all` or the switch `investigation` is pulled).
STUDY_SCHEDULE = "0 30 4 * * 1"
# Every minute: the plans whose time is over, the changes whose start time has come, the changes to check.
TICK_SCHEDULE = "0 * * * * *"
# The control queue is in the app's host storage account, so the trigger uses the host's own connection: the platform reads AzureWebJobsStorage__credential and
# AzureWebJobsStorage__queueServiceUri (the template sets them) and signs in as the app's system-assigned identity. There is no connection string and no key.
HOST_STORAGE_CONNECTION = "AzureWebJobsStorage"


@app.function_name(name="watch-daily")
@app.timer_trigger(arg_name="timer", schedule=TIMER_SCHEDULE, run_on_startup=False)
def watch_daily(timer: func.TimerRequest) -> None:
    run.run_watch("timer", None)


@app.function_name(name="drift-daily")
@app.timer_trigger(arg_name="timer", schedule=DRIFT_SCHEDULE, run_on_startup=False)
def drift_daily(timer: func.TimerRequest) -> None:
    drift.run_check("timer")


@app.function_name(name="study-weekly")
@app.timer_trigger(arg_name="timer", schedule=STUDY_SCHEDULE, run_on_startup=False)
def study_weekly(timer: func.TimerRequest) -> None:
    study.run_study("timer", None)


@app.function_name(name="cases-control")
@app.queue_trigger(arg_name="msg", queue_name="%CASES_CONTROL_QUEUE_NAME%", connection=HOST_STORAGE_CONNECTION)
def cases_control(msg: func.QueueMessage) -> None:
    control.handle_message(msg)


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
