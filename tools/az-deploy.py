#!/usr/bin/env python3
"""Runs one `az deployment group` command of the first environment, and repeats it on the answers that a second try clears.

    python tools/az-deploy.py what-if --subscription S --resource-group G --template T --parameters P [--restore-param NAME]
    python tools/az-deploy.py create  --subscription S --resource-group G --template T --parameters P --name N [--output NAME] [--restore-param NAME]

Standard library only. `what-if` reads and changes nothing. `create` deploys, and only a GitHub Actions run may do that
(AGENTS.md rule 18). With --output, the value of that output of the deployment is printed alone on standard output, so a
step can read it; everything else goes to standard error.

Three answers of the service are not failures of the template:
  - FlagMustBeSetForRestore: a soft-deleted account of the name is left from an earlier removal. With --restore-param the
    command is made again with NAME=true, which restores it (it holds nothing).
  - IfMatchPreconditionFailed, and a stop of the Azure CLI itself on the runner ("deadlock detected by _ModuleLock", an
    import lock of its Python): the deployment is idempotent, so it is made again after a minute.
  - ServiceBusy, ServiceUnavailable, TooManyRequests, RequestTimeout, GatewayTimeout: the same, for an instance that is
    busy with an earlier write.
At most three tries. Anything else stops the run at once, with the service's own text.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time

RESTORE = "FlagMustBeSetForRestore"
TRANSIENT = re.compile(r"IfMatchPreconditionFailed|deadlock detected by _ModuleLock|ServiceBusy|ServiceUnavailable|TooManyRequests|RequestTimeout|GatewayTimeout")
TRIES = 3
PAUSE = 60


def command(mode: str, args, extra: list[str]) -> list[str]:
    parts = [os.environ.get("AZ", "az"), "deployment", "group", "what-if" if mode == "what-if" else "create", "--only-show-errors",
             "--subscription", args.subscription, "--resource-group", args.resource_group,
             "--template-file", args.template]
    if args.parameters:
        parts += ["--parameters", f"@{args.parameters}"]
    for pair in extra:
        parts += ["--parameters", pair]
    if mode == "what-if":
        parts += ["--result-format", "FullResourcePayloads"]
    else:
        parts += ["--name", args.name]
        parts += ["--query", f"properties.outputs.{args.output}.value", "--output", "tsv"] if args.output else ["--output", "none"]
    return parts


def run(parts: list[str]) -> tuple[int, str, str]:
    done = subprocess.run(parts, capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


def main(argv=None, runner=run, sleep=time.sleep) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["what-if", "create"])
    parser.add_argument("--subscription", required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--parameters", help="an ARM parameter file; a template without parameters needs none")
    parser.add_argument("--name", help="the deployment's name (create)")
    parser.add_argument("--output", help="print this output of the deployment (create)")
    parser.add_argument("--restore-param", help="the template parameter that restores a soft-deleted account")
    args = parser.parse_args(argv)
    if args.mode == "create":
        if os.environ.get("GITHUB_ACTIONS") != "true":
            print("error: this command deploys, and only a GitHub Actions run may do that (AGENTS.md rule 18)", file=sys.stderr)
            return 2
        if not args.name:
            print("error: create needs --name", file=sys.stderr)
            return 2
    extra: list[str] = []
    attempt = 1
    while True:
        code, out, err = runner(command(args.mode, args, extra))
        if code == 0:
            if err.strip():
                print(err.rstrip(), file=sys.stderr)
            print(out.rstrip() if args.mode == "what-if" or args.output else "", end="\n" if out.strip() or args.mode == "what-if" else "")
            return 0
        if args.restore_param and RESTORE in err and not extra:
            print(f"A soft-deleted account of this name is left from an earlier removal; {'the preview, like the deploy, restores' if args.mode == 'what-if' else 'it is restored'} it (it holds nothing).", file=sys.stderr)
            extra = [f"{args.restore_param}=true"]
            continue
        if attempt < TRIES and TRANSIENT.search(err):
            print(f"The service answered with something that a second try usually clears (attempt {attempt} of {TRIES}). Trying again in a minute.", file=sys.stderr)
            attempt += 1
            sleep(PAUSE)
            continue
        print(err.rstrip(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
