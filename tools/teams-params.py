#!/usr/bin/env python3
"""Builds the parameter file of the Teams bot's template (environment/teams/main.bicep) from the file of the cases app (standard library only).

    python3 tools/teams-params.py --cases-params "$RUNNER_TEMP/cases.parameters.json" --out "$RUNNER_TEMP/teams.parameters.json" >> "$GITHUB_OUTPUT"

The workflow's step "Work out the settings" (tools/environment-params.py) writes the cases app's parameters; the bot shares what they hold: the region, the owner, the storage account of the
base, the people and the host name that the web page is opened at. This file takes those from it, so that the bot and the cases app cannot disagree, and makes the two names that are the bot's own
from the same eight-character digest as the cases app's name (func-meternaut-cases-<digest>): the function app (func-meternaut-teams-<digest>, a host name) and the Azure Bot resource
(bot-meternaut-teams-<digest>, a handle). It prints the names as lines for $GITHUB_OUTPUT, and it refuses, with one line, a cases file that does not hold what the bot needs: a bot without
people answers nobody, and one without a web page host has nothing to link its cards to.

The action `teams` of .github/workflows/deploy-hub.yml runs it, after the tools/environment-params.py check has passed the cases file. Nothing here reads Azure.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA = "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#"
CASES_APP = re.compile(r"^func-meternaut-cases-([0-9a-f]{8})$")
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ACCOUNT = re.compile(r"^[a-z0-9]{3,24}$")
HOST = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
LOCATION = re.compile(r"^[a-z0-9]{3,30}$")
OWN_DOMAIN = ".azurewebsites.net"
TAKEN = ("location", "owner", "storageAccountName", "consolePeople")
# What the template takes that the bot does not read from the cases file: left to the template's defaults (the most instances, the memory of an instance, no instance kept warm).
ALWAYS_READY_INSTANCES = 0


class Problem(Exception):
    """The cases file does not hold what the bot needs; the text says what."""


def names_of(cases_app: str) -> dict[str, str]:
    found = CASES_APP.match(cases_app or "")
    if not found:
        raise Problem(f"the cases app is not called func-meternaut-cases-<8 hex digits>, so the bot's names cannot follow it: {cases_app!r}")
    digest = found.group(1)
    return {"bot_app_name": f"func-meternaut-teams-{digest}", "bot_name": f"bot-meternaut-teams-{digest}"}


def values_of(cases: dict) -> dict[str, object]:
    """The parameters of the template, from the `parameters` of the cases file."""
    parameters = cases.get("parameters") if isinstance(cases, dict) else None
    if not isinstance(parameters, dict):
        raise Problem("the cases file is not a parameter file")

    def value(name: str, default: object = None) -> object:
        entry = parameters.get(name)
        return entry.get("value", default) if isinstance(entry, dict) else default

    missing = [name for name in (*TAKEN, "functionAppName") if not value(name)]
    if missing:
        raise Problem(f"the cases file lacks {', '.join(missing)}")
    location, account = str(value("location")), str(value("storageAccountName"))
    if not LOCATION.match(location):
        raise Problem("location is a region name such as swedencentral")
    if not ACCOUNT.match(account):
        raise Problem("storageAccountName is a storage account name")
    try:
        people = json.loads(str(value("consolePeople")))
    except ValueError as error:
        raise Problem("consolePeople is not JSON") from error
    if (not isinstance(people, list) or not people or not all(isinstance(p, dict) and GUID.match(str(p.get("oid", ""))) and p.get("name") and isinstance(p.get("roles"), list) for p in people)
            or not any("approver" in p["roles"] for p in people)):
        raise Problem("consolePeople is a list of people, each with an oid, a name and roles, and at least one is an approver: a bot without an approver answers nobody")
    cases_app = str(value("functionAppName"))
    names = names_of(cases_app)
    host = str(value("consoleHostName") or "") or f"{cases_app}{OWN_DOMAIN}"
    if not HOST.match(host):
        raise Problem(f"the host that the web page is opened at is not a host name: {host!r}")
    return {
        "location": location,
        "owner": str(value("owner")),
        "storageAccountName": account,
        "botAppName": names["bot_app_name"],
        "botName": names["bot_name"],
        "consoleHost": host,
        "consolePeople": str(value("consolePeople")),
        "alwaysReadyInstances": ALWAYS_READY_INSTANCES,
    }


def parameter_file(values: dict[str, object]) -> dict:
    return {"$schema": SCHEMA, "contentVersion": "1.0.0.0", "parameters": {name: {"value": value} for name, value in values.items()}}


def main(argv: list[str] | None = None, out=None) -> int:
    out = sys.stdout if out is None else out
    parser = argparse.ArgumentParser(description="Builds the parameter file of the Teams bot's template from the cases app's.")
    parser.add_argument("--cases-params", required=True, help="the cases app's parameter file (cases.parameters.json)")
    parser.add_argument("--out", required=True, help="the parameter file to write")
    args = parser.parse_args(argv)
    try:
        try:
            cases = json.loads(Path(args.cases_params).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise Problem(f"the cases file cannot be read: {type(error).__name__}") from error
        values = values_of(cases)
        Path(args.out).write_text(json.dumps(parameter_file(values), indent=2) + "\n", encoding="utf-8")
    except Problem as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    out.write(f"teams_bot_app_name={values['botAppName']}\nteams_bot_name={values['botName']}\nteams_console_host={values['consoleHost']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
