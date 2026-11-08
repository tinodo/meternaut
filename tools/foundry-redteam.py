#!/usr/bin/env python3
"""Red teaming of the Investigator in the Foundry project, from inside the network (standard library only).

    python tools/foundry-redteam.py run --endpoint <project endpoint> [--wait-seconds 900] [--summary FILE]
    python tools/foundry-redteam.py --selftest

NEVER against the production Investigator. The tool makes a SYNTHETIC COPY of it: a prompt agent whose instructions are the Investigator's (the file evaluation/investigator-instructions.txt,
which the tool holds against the hash in the lock before anything is made), whose model is the same alias through the same AI Gateway connection, which has NO tools and no access to anything of
the estate, and whose name says what it is (`meternaut-redteam-copy-...`). The tool makes it, attacks it with the red team of the Foundry service (taxonomy of risk categories, attack
strategies Flip, Base64 and IndirectJailbreak, from evaluation/thresholds.json) and deletes it in the end, whatever happened; it says so, and says what to delete by hand when it could not.

What this tests, and what it does not: it tests the instructions and the model alone against attacks on them (an agent that can be talked into prohibited actions). It cannot test the tool calls
of the production agent: Microsoft does not support function tools in red-team probing. How the Investigator behaves with its tools is tested by the evaluation set (tools/foundry-evals.py) and by
the injection suite of the unit tests.

The attacks go to the copy, whose model is reached only through the AI Gateway connection (AGENTS.md rule 15 (c)); the attack generation and the judging are the Foundry service's own. The run
is held to the spend cap of evaluation/limits.json before it starts (the attacks are estimated, ATTACKS_PER_STRATEGY for each strategy) and prints how many calls of a model it counted.
The tool starts only in a run of GitHub Actions. The red teaming of the Foundry service is in preview and is offered in some regions only (the Learn pages disagree about which: this tool
tries and says what the project answered).

The exit code is 0 when the run finished and no attack succeeded (up to the threshold of thresholds.json), 1 when an attack succeeded, the run did not finish or the copy could not be deleted,
2 when the tool refused to run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import secrets
import sys
import time
from pathlib import Path

helpers = sys.modules.get("aisec_helpers")
if helpers is None:  # a test has loaded it already; a tool run on its own loads it from its own folder
    _spec = importlib.util.spec_from_file_location("aisec_helpers", Path(__file__).with_name("aisec-helpers.py"))
    helpers = importlib.util.module_from_spec(_spec)
    sys.modules["aisec_helpers"] = helpers
    _spec.loader.exec_module(helpers)
Problem, SpendCap = helpers.Problem, helpers.SpendCap

API = "api-version=v1"
INVESTIGATOR = "meternaut-investigator"
COPY_PREFIX = "meternaut-redteam-copy-"
ROUTES = ("/openai/v1/evals", "/openai/evals?api-version=2025-11-15-preview")
ATTACKS_PER_STRATEGY = 10  # an assumption for the spend cap: the number of attacks that the service makes for a strategy is not documented


def find(name: str) -> Path:
    for folder in (helpers.HERE, helpers.EVALUATION):
        if (folder / name).is_file():
            return folder / name
    raise Problem(f"{name} is neither next to the tool nor in evaluation/", 2)


def copy_name(now: dt.datetime, token: str | None = None) -> str:
    return f"{COPY_PREFIX}{now:%Y%m%d%H%M}-{token or secrets.token_hex(2)}"


def synthetic_definition(instructions: str, model: str) -> dict:
    """The definition of the copy: the instructions and the model of the Investigator, and no tool of any kind."""
    return {"kind": "prompt", "model": model, "instructions": instructions}


def make_copy(client, name: str, definition: dict) -> str:
    if not name.startswith(COPY_PREFIX) or name == INVESTIGATOR or "tools" in definition:
        raise Problem("the copy is named so that nobody mistakes it for production, and has no tools", 2)
    status, document = client.request("POST", f"/agents?{API}", {"name": name, "definition": definition, "description": "A synthetic copy for red teaming, made and deleted by tools/foundry-redteam.py. It has no tools.",
                                                              "metadata": {"meternaut_redteam_copy": "true"}})
    version = ((document.get("versions") or {}).get("latest") or {}).get("version") if isinstance(document, dict) and isinstance(document.get("versions"), dict) else None
    version = version if version is not None else document.get("version") if isinstance(document, dict) else None
    if status not in (200, 201) or version is None:
        raise Problem(f"the synthetic copy could not be made ({status} {helpers.error_words(document)})")
    return str(version)


def delete_copy(client, name: str) -> bool:
    """Deletes the copy and makes sure that it is gone. Only a name that starts with COPY_PREFIX is ever deleted."""
    if not name.startswith(COPY_PREFIX):
        return False
    client.request("DELETE", f"/agents/{name}?{API}")
    status, _ = client.request("GET", f"/agents/{name}?{API}")
    return status == 404


def attack(client, spend, account: str, project: str, name: str, version: str, thresholds: dict, wait: float, sleep=time.sleep, clock=time.monotonic) -> tuple[str, int, int]:
    """Runs the red team on the copy. Returns (state, attacks, successful)."""
    plan = thresholds["redTeam"]
    spend.take(model_calls=ATTACKS_PER_STRATEGY * len(plan["attackStrategies"]))
    taxonomy = f"meternaut-redteam-{name[len(COPY_PREFIX):]}"
    target = {"type": "azure_ai_agent", "name": name, "version": version, "tool_descriptions": []}
    status, document = client.request("PUT", f"/evaluationtaxonomies/{taxonomy}?{API}", {"taxonomyInput": {"type": "agent", "target": target, "riskCategories": plan["riskCategories"]}})
    if status not in (200, 201):
        raise Problem(f"the taxonomy of the attack was not accepted ({status} {helpers.error_words(document)})")
    taxonomy_version = str((document or {}).get("version") or "1") if isinstance(document, dict) else "1"
    evaluation = {"name": f"meternaut-redteam-{name[len(COPY_PREFIX):]}", "data_source_config": {"type": "azure_ai_source", "scenario": "red_team"},
                  "testing_criteria": [{"type": "azure_ai_evaluator", "name": "prohibited_actions", "evaluator_name": "builtin.prohibited_actions"}]}
    base, created, query = "", None, ""
    for route in ROUTES:
        status, document = client.request("POST", route, evaluation)
        if status in (200, 201) and isinstance(document, dict) and isinstance(document.get("id"), str):
            base, created, query = route.split("?")[0], document["id"], ("?" + route.split("?", 1)[1]) if "?" in route else ""
            break
    if created is None:
        raise Problem(f"the project did not accept the red team evaluation ({status} {helpers.error_words(document)}): cloud red teaming may not be offered in this region")
    source = f"azureai://accounts/{account}/projects/{project}/evaluationtaxonomies/{taxonomy}/versions/{taxonomy_version}"
    status, document = client.request("POST", f"{base}/{created}/runs{query}", {"name": "redteam", "data_source": {
        "type": "azure_ai_red_team", "item_generation_params": {"type": "red_team_taxonomy", "attack_strategies": plan["attackStrategies"], "num_turns": 1, "source": {"type": "file_id", "id": source}},
        "target": target}})
    run_id = document.get("id") if isinstance(document, dict) else None
    if status not in (200, 201) or not isinstance(run_id, str):
        raise Problem(f"the red team run was not accepted ({status} {helpers.error_words(document)})")
    last, done = helpers.poll(lambda: client.request("GET", f"{base}/{created}/runs/{run_id}{query}")[1], lambda doc: isinstance(doc, dict) and doc.get("status") in ("completed", "failed", "canceled"),
                              wait, 15.0, sleep=sleep, clock=clock)
    state = last.get("status") if isinstance(last, dict) else None
    if not done or state != "completed":
        return state or "unanswered", 0, 0
    counts = last.get("result_counts") if isinstance(last.get("result_counts"), dict) else {}
    failed, passed = int(counts.get("failed") or 0), int(counts.get("passed") or 0)
    return "completed", failed + passed, failed  # a result that fails is an attack that got the copy to do what it must not


def command_run(args, client, spend, sleep=time.sleep, clock=time.monotonic, now=None) -> int:
    lockfile, _, _ = helpers.load_cases()
    account, project = helpers.check_endpoint(args.endpoint)
    thresholds = json.loads(find("thresholds.json").read_text(encoding="utf-8"))
    path = next((p for p in (helpers.HERE / lockfile.FILE_NAME, helpers.CASES / lockfile.FILE_NAME) if p.is_file()), None)
    if path is None:
        raise Problem(f"{lockfile.FILE_NAME} is neither next to the tool nor in the repository", 2)
    lock = lockfile.load(path)
    entry = lock.entry(INVESTIGATOR)
    instructions = find("investigator-instructions.txt").read_text(encoding="utf-8")
    if entry is None or lockfile.sha256_text(instructions) != entry["instructionsSha256"]:
        raise Problem("investigator-instructions.txt is not the instructions that the lock holds: nothing was made", 2)
    if not entry["connection"]:
        raise Problem("the lock names no connection to the AI Gateway: the copy would reach its model another way, and nothing was made", 2)
    name = copy_name(now or dt.datetime.now(dt.timezone.utc))
    definition = synthetic_definition(instructions, f"{entry['connection']}/{entry['model']}")
    version = make_copy(client, name, definition)
    helpers.say(f"redteam: made the synthetic copy {name} (version {version}), with no tools, from the locked instructions of the Investigator")
    state, attacks, successful, problem = "", 0, 0, ""
    try:
        state, attacks, successful = attack(client, spend, account, project, name, version, thresholds, args.wait_seconds, sleep, clock)
    except (Problem, SpendCap) as error:
        problem = str(error)
    finally:
        gone = delete_copy(client, name)
    helpers.say(f"redteam: the synthetic copy {name} was " + ("deleted and is gone" if gone else "NOT deleted: delete it by hand in the portal under Build, Agents"))
    if problem:
        helpers.say(f"FAIL {problem}")
    elif state != "completed":
        helpers.say(f"FAIL the red team run is {state} after {int(args.wait_seconds)} seconds: the copy was NOT tested (a Foundry without public network access may need the evaluation networking: see the proposal)")
    else:
        rate = successful / attacks if attacks else 1.0
        ok = rate <= thresholds["redTeam"]["maxSuccessfulAttackRate"]
        helpers.say(f"{'PASS' if ok else 'FAIL'} {successful} of {attacks} attacks got the copy to do what it must not (rate {rate:.2f}, at most {thresholds['redTeam']['maxSuccessfulAttackRate']}); the run is in the portal under Build, Red team")
    helpers.say(spend.line() + " (the attacks are estimated)")
    helpers.say(f"redteam: {len(client.calls)} calls to the project in all")
    return 0 if not problem and state == "completed" and gone and successful / max(1, attacks) <= thresholds["redTeam"]["maxSuccessfulAttackRate"] else 1


def selftest() -> int:
    problems: list[str] = []
    lockfile, _, _ = helpers.load_cases()
    lock = lockfile.load(helpers.CASES / lockfile.FILE_NAME)
    text = find("investigator-instructions.txt").read_text(encoding="utf-8")
    if lockfile.sha256_text(text) != lock.agents[INVESTIGATOR]["instructionsSha256"]:
        problems.append("the instructions file is not the locked instructions")
    definition = synthetic_definition(text, "aigateway/m")
    if "tools" in definition or definition["kind"] != "prompt":
        problems.append("the copy has tools or is not a prompt agent")
    for bad in (INVESTIGATOR, "meternaut-skeptic", "other"):
        try:
            make_copy(None, bad, definition)
            problems.append(f"a copy named {bad} was allowed")
        except Problem:
            pass
        except AttributeError:
            problems.append("the check of the name comes after the call")
    if delete_copy(None, INVESTIGATOR):
        problems.append("the production agent could be deleted")
    for line in problems:
        helpers.say(f"selftest FAIL: {line}")
    helpers.say("selftest: " + ("ok" if not problems else f"{len(problems)} problems"))
    return 1 if problems else 0


def main(argv=None, client=None, spend=None, sleep=time.sleep, clock=time.monotonic, now=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selftest", action="store_true")
    commands = parser.add_subparsers(dest="command")
    command = commands.add_parser("run")
    command.add_argument("--endpoint", required=True)
    command.add_argument("--wait-seconds", type=float, default=900)
    command.add_argument("--summary")
    args = parser.parse_args(argv)
    try:
        if args.selftest:
            return selftest()
        if args.command != "run":
            parser.error("name the command run, or give --selftest")
        helpers.require_actions()
        helpers.check_endpoint(args.endpoint)
        return command_run(args, client or helpers.Client(args.endpoint, helpers.FOUNDRY_RESOURCE), spend or helpers.Spend.load(), sleep, clock, now)
    except Problem as error:
        helpers.say(f"error: {error}", sys.stderr)
        return error.code


if __name__ == "__main__":
    sys.exit(main())
