"""Entry point of the Teams bot's function app (Python v2 programming model). Wiring only: the logic is in cases/teams.py.

This file is not the entry of the cases app: the build of the bot's package (tools/build-teams-bot.sh) puts it in place of function_app.py,
so that the public app has exactly two functions, the messaging endpoint and the timer that offers cards, and none of the cases app's: no console route, no Watch, no loop's timer.
"""
import azure.functions as func

from cases import teams

app = func.FunctionApp()

# Every minute: the cards that are due (cases/offers.py). The same cadence as the letters of the loop.
OFFER_SCHEDULE = "0 * * * * *"


# The messaging endpoint of the bot. The host's route prefix is empty (host.json), so the whole address is the route. "Anonymous" means "no function key", because a key would be a secret: the
# JWT that the Bot Framework Connector sends is checked by the first lines of the handler (cases/botauth.py), and a call that fails gets an empty 401 or 403.
@app.function_name(name="teams-messages")
@app.route(route="api/messages", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def teams_messages(req: func.HttpRequest) -> func.HttpResponse:
    return teams.handle(req, func.HttpResponse)


@app.function_name(name="teams-offer")
@app.timer_trigger(arg_name="timer", schedule=OFFER_SCHEDULE, run_on_startup=False)
def teams_offer(timer: func.TimerRequest) -> None:
    teams.tick()
