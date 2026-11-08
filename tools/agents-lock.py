#!/usr/bin/env python3
"""Writes and checks the lock of the agents, `src/case-functions/cases/agents.lock.json` (standard library only).

    python tools/agents-lock.py write [--out FILE]
    python tools/agents-lock.py check [--lock FILE]

The lock holds, for each agent of the investigation, the model alias, the SHA-256 of its instructions and of the canonical schemas of its tools, and the options that are expected, and,
for each tool, the SHA-256 of its schema and of the source of the code that runs it, and of the module of the tools. It holds no id, name or address of an estate: it is made of what this
repository says (cases/agents.py, cases/toolbox.py, and the name of the AI Gateway connection and the models in tools/environment-params.py).

A changed definition is a release: the pull request that changes an instruction, a tool or a model changes the lock with it (`write`), and `check` fails, as a test in CI does, when
they differ. At run time the harness (cases/harness.py) refuses an agent whose code or stored definition differs from the lock, and the drift check reads the same lock.

write   Writes the lock from the code (to --out, by default the file that the app reads). The same code always makes the same file.
check   Reads the lock and says in which way the code differs from it, one line each. Exit 0 when it is current, 1 when it is not, 2 when it cannot be read.

Run it from anywhere: it finds the repository from its own place. It reads files, writes the one file that you name and never calls a service.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "case-functions"
LOCK = APP / "cases" / "agents.lock.json"
# The instructions of the Investigator as a file, for the red team: its synthetic copy is made from this text, which the tool holds against the hash in the lock before it makes the copy.
INSTRUCTIONS = ROOT / "evaluation" / "investigator-instructions.txt"


def load_app():
    """The modules of the app that the lock is made from. The app folder is put in front of the path so that `cases` is the package of this repository."""
    if str(APP) not in sys.path:
        sys.path.insert(0, str(APP))
    from cases import agents, foundry, lockfile, toolbox  # noqa: E402 (after the path is set)

    return agents, foundry, lockfile, toolbox


def load_params():
    """The constants of tools/environment-params.py that say how the agents reach their models: the switch of the route through the AI Gateway, the name of the connection and the models."""
    spec = importlib.util.spec_from_file_location("environment_params", ROOT / "tools" / "environment-params.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("environment_params", module)
    spec.loader.exec_module(module)
    return module


def from_code() -> tuple[dict, dict, str, str | None]:
    """The definitions that the code sends (by agent name), the digests of the code of the tools, the digest of the toolbox's module and the connection of the models (None for a direct route)."""
    agents, foundry, lockfile, toolbox = load_app()
    params = load_params()
    connection = params.AIGATEWAY_CONNECTION_NAME if params.AGENTS_VIA_AI_GATEWAY else None

    def named(model: str) -> str:
        return f"{connection}/{model}" if connection else model

    settings = SimpleNamespace(foundry_model_investigator=named(params.AGENT_MODELS["foundryModelInvestigator"]), foundry_model_skeptic=named(params.AGENT_MODELS["foundryModelSkeptic"]))
    specs = (agents.investigator(settings, toolbox.SPECS), agents.skeptic(settings))
    definitions = {spec.name: foundry.definition_of(spec) for spec in specs}
    implementations = lockfile.implementation_digests(toolbox.Toolbox, [tool.name for tool in toolbox.SPECS])
    module = lockfile.source_digest(Path(toolbox.__file__).read_text(encoding="utf-8"))
    return definitions, implementations, module, connection


def instructions_text() -> str:
    agents, _, _, _ = load_app()
    return agents.INVESTIGATOR_INSTRUCTIONS


def command_write(out: Path) -> int:
    _, _, lockfile, _ = load_app()
    definitions, implementations, module, connection = from_code()
    document = lockfile.build(definitions, implementations, module, connection)
    lockfile.validate(document)
    out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.name}: {len(document['agents'])} agents, {len(document['tools'])} tools")
    if out == LOCK:
        INSTRUCTIONS.write_text(instructions_text(), encoding="utf-8", newline="\n")
        print(f"wrote {INSTRUCTIONS.name}: the instructions of the Investigator, for the red team")
    return 0


def command_check(path: Path) -> int:
    _, _, lockfile, _ = load_app()
    try:
        lock = lockfile.load(path)
    except lockfile.LockError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    definitions, implementations, module, _ = from_code()
    problems = lockfile.stale(lock, definitions, implementations, module)
    if path == LOCK:
        try:
            if INSTRUCTIONS.read_text(encoding="utf-8") != instructions_text():
                problems.append(f"{INSTRUCTIONS.name} is not the instructions of the Investigator that the code holds")
        except OSError:
            problems.append(f"{INSTRUCTIONS.name} cannot be read")
    if not problems:
        print(f"the lock is current: {len(lock.agents)} agents, {len(lock.tools)} tools")
        return 0
    for line in problems:
        print(f"differs: {line}")
    print("run: python tools/agents-lock.py write   (a changed definition is a release: commit the code and the lock together)")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Writes and checks the lock of the agents.")
    commands = parser.add_subparsers(dest="command", required=True)
    write = commands.add_parser("write", help="write the lock from the code")
    write.add_argument("--out", type=Path, default=LOCK)
    check = commands.add_parser("check", help="say how the code differs from the lock")
    check.add_argument("--lock", type=Path, default=LOCK)
    args = parser.parse_args(argv)
    return command_write(args.out) if args.command == "write" else command_check(args.lock)


if __name__ == "__main__":
    sys.exit(main())
