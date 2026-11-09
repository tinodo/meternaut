#!/usr/bin/env python3
"""Runs the Hub workflow's own steps for one action on the owner's machine, with the owner's own az session (standard library only).

    python tools/hub-local.py <action> [--minutes N] [--public-ai-gateway-requested] [--public-teams-bot-requested] [--plant-public-ip] [--plant-vm] [--evals-command C] [--evals-judge J]
                                       [--redteam-mode M]
                                       [--yes] [--allow-dirty] [--dry-run] [--workflow PATH]
    python tools/hub-local.py --init [--from-github]

Why this exists: since 2026-11-08 every change to Azure is made from the owner's machine, with his own az session, by a tool of this repository, after a what-if and with a record (AGENTS.md
rule 18). No GitHub workflow changes Azure any more. The logic of every deploy is still the bash of .github/workflows/deploy-hub.yml: this tool reads that file, picks the steps of the action,
and runs them here, one after the other, with the values that GitHub held as variables and secrets (the git-ignored local/hub-local.env). The workflow is not copied or translated: when it
changes, the next run follows it, as long as its layout stays the one that tools/workflow-lint.py enforces.

THE HUB IS THIS TOOL NOW. The tools that the steps call and that change Azure (tools/az-deploy.py create, retire-old.py, cases-move.py, aigateway-prep.py, operator-run.py) accept only a run
of the Hub (tools/hubguard.py): a process that holds the proof of a run of this tool, and nothing else. GITHUB_ACTIONS=true is not enough, and neither is anything else that a GitHub runner sets:
any process on this machine can set them, and since 2026-11-08 no GitHub run changes Azure (AGENTS.md rule 18). A stray call would skip every guard that only this tool has. So each run makes a
proof: a random token in local/rt/<run>/hub-proof, the run's number, the SHA-256 of the token and the start time of its process in the lock, and METERNAUT_HUB_PROOF in the environment of every
step. The tools look for the proof in this repository's own local folder only (the one found below), and they refuse a file anywhere else and a lock whose process was not started when the lock
says. The file is deleted when the run ends, after a failure and after Ctrl+C too, and the token is never printed or written to the log or the record. This stops an accident and a stray call,
like a tripwire; it is not a lock. It does not stop a process that holds the owner's az session: that can call az itself, or make a proof of its own.
The steps still get GITHUB_ACTIONS=true and METERNAUT_HUB_LOCAL=1: the workflow passes the first on to the Operator's container, whose tools (aigateway-check.py, check-helpers.py,
aisec-helpers.py) have no run lock to compare with and keep the old test. The guards that matter here are this tool's own: the owner's az session, the action's options, --yes for an action that
changes Azure, a clean working tree, one run at a time, and a configuration file that git ignores.

Where it keeps its files: the git-ignored local/ folder of the repository's MAIN working tree (the parent of `git rev-parse --git-common-dir`), so that every worktree finds the same
configuration, run counter, lock and records; the environment variable METERNAUT_LOCAL names another folder.

What it replaces, and never fakes:
  * actions/checkout and actions/setup-python: skipped with a note (setup-python checks the Python version);
  * azure/login: the owner's own az session is checked instead. The CLI's default subscription is set to the pilot's for the run and always put back at the end (AGENTS.md rule 15 (b));
  * the step that asks GitHub whether the checks of CI passed for this commit: not asked (no GitHub call is made from this machine, and no GitHub token is ever given to a step). The person who
    starts the run ran the checks on this machine (AGENTS.md rule 35); the record names the commit and says whether the working tree is clean. An action that changes Azure needs a clean tree;
  * the unit tests of a first step that still runs them: not repeated, with the same note;
  * for the action cases, the publish through the Operator (it needs a GitHub OpenID Connect token): the package is built here by tools/build-function-app.sh and published from this machine
    through the app's public deployment site, which needs the app's public network access to be Enabled. Before it is published, the files in the zip file are held against the digest of the
    app's own files that the deploy wrote as the app's setting PACKAGE_SHA256 (tools/package-digest.py, which runs the app's own cases/release.py), so that the app's check of its release
    finds the same; a package whose files differ is never published.
A step that needs a GitHub OpenID Connect token or a GitHub token, or calls GitHub with gh, and has no replacement stops the run before anything is changed. Not supported: that token, so the check
of the deploy identity inside the Operator (the probe goes on without it, and says so).

The configuration names every variable and secret that the workflow reads. Two repository variables are optional, DRIFT_ACCEPTED_EXEMPTIONS and DRIFT_ACCEPTED_DENY (what the owner accepted of the
policy state): GitHub reads one that is not set as empty, and so does this tool. A run says so in its plan. Any other name that is missing from the file stops the plan.

The inputs of the workflow are flags: --minutes (page-latency), --plant-public-ip and --plant-vm (plant), --public-ai-gateway-requested (aigateway), --public-teams-bot-requested (teams),
--evals-command and --evals-judge (foundry-evals) and --redteam-mode (foundry-redteam). A flag that is not given has the workflow's own default, and the plan prints the value that each input has.
The action teams also reads one repository variable that no other action reads, TEAMS_BOT_ENABLED: the owner adds the line TEAMS_BOT_ENABLED=True to the configuration file, after his written
request for the Teams bot; the other actions never read it, so they need no such line. An action that only reads needs no --yes:
what-if, aigateway-check, page-latency, loop-check, operator-probe, drift-check, agents-drift, agent365-check, and foundry-evals with the command probe or rule. Every other action changes
Azure, and so does an action that this tool does not know.

On Windows the steps run in Git's bash. What that breaks, and what this tool does about it, is listed in docs/proposals/16-the-hub-on-the-owners-machine.md. In short: CRLF line ends of the workflow
are made LF; the path conversion of Git's bash is switched off, so that `az ... /subscriptions/...` is not rewritten; python3 is a shim (the Windows Store alias of that name opens the Store); the
Azure CLI is run through its own python.exe and not through az.cmd, because cmd.exe mangles quotes and ampersands in arguments; Python's text encoding is UTF-8; and a timeout kills the whole process tree.

The exit code: 0 passed (or a dry run), 1 a step failed, 2 refused or the workflow could not be planned: nothing was run.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-hub.yml"

# What the tools that change Azure ask before they run (tools/hubguard.py): this tool makes the proof that a run of the Hub holds, and the same file says how a tool reads it.
guard = sys.modules.get("hubguard")
if guard is None:  # a test has loaded it already; the tool run on its own loads it from its own folder
    _spec = importlib.util.spec_from_file_location("hubguard", Path(__file__).with_name("hubguard.py"))
    guard = importlib.util.module_from_spec(_spec)
    sys.modules["hubguard"] = guard
    _spec.loader.exec_module(guard)

# The actions that only read and preview (or make a short-lived container group that they delete again): they need no --yes. Every other action changes Azure, and so does an action that
# this list does not know: a new action is a change until somebody says that it only reads.
READ_ONLY_ACTIONS = ("what-if", "aigateway-check", "page-latency", "loop-check", "operator-probe", "drift-check", "agents-drift", "agent365-check")
# An action that reads for some values of an input and changes Azure for the others: foundry-evals reads with probe and rule, and makes evaluation runs and the rule with run and rule-apply.
READ_ONLY_INPUT_VALUES = {"foundry-evals": ("evals_command", ("probe", "rule"))}
# The inputs that only some actions read (the workflow says "Every other action ignores it"): a flag for another action is said in the plan, and never guessed.
INPUT_ACTIONS = {"minutes": ("page-latency",), "plant_public_ip": ("plant",), "plant_vm": ("plant",), "public_ai_gateway_requested": ("aigateway",), "public_teams_bot_requested": ("teams",),
                 "evals_command": ("foundry-evals",), "evals_judge": ("foundry-evals",), "redteam_mode": ("foundry-redteam",)}
INPUT_FLAGS = {"minutes": "--minutes", "plant_public_ip": "--plant-public-ip", "plant_vm": "--plant-vm", "public_ai_gateway_requested": "--public-ai-gateway-requested",
               "public_teams_bot_requested": "--public-teams-bot-requested", "evals_command": "--evals-command", "evals_judge": "--evals-judge", "redteam_mode": "--redteam-mode"}
PUBLIC_GATEWAY_ACTION = "aigateway"
TEAMS_ACTION = "teams"
# The workflow's job guard is `github.actor == 'tinodo' && github.ref == 'refs/heads/main'` (tools/workflow-lint.py enforces it). A local run is the owner's, on the code of this checkout.
LOCAL_ACTOR = "tinodo"
LOCAL_REF = "refs/heads/main"

CONFIG_NAME = "hub-local.env"
STATE_NAME = "hub-local.state.json"
LOCK_NAME = guard.LOCK_NAME
RECORDS_NAME = "records"
TEMP_NAME = guard.TEMP_NAME
LOCAL_OVERRIDE = guard.LOCAL_VARIABLE

# What GitHub held as variables and secrets for this workflow. The workflow's own references are checked against the file too, so a new name is found before a run starts.
VARIABLE_NAMES = ("ENV_RESOURCE_GROUP", "ENV_LOCATION", "ENV_VNET_PREFIX", "ENV_PE_SUBNET_PREFIX", "ENV_DNS_SERVERS", "ENV_OWNER", "ENV_BUDGET_AMOUNT", "ENV_ALERT_EMAILS",
                  "CONSOLE_APP_CLIENT_ID", "CONSOLE_PEOPLE", "CONSOLE_HOST_NAME", "MAIL_SENDER")
SECRET_NAMES = ("AZURE_SUBSCRIPTION_ID", "AZURE_TENANT_ID", "AZURE_CLIENT_ID")
# Repository variables that the workflow reads and that may be left out: what the owner has accepted of the policy state (tools/drift-check.py). Unset, GitHub reads them as empty, and the controls
# that they feed say UNKNOWN and print what they found. Absent or empty is empty here too, and a run says which of them it read as empty. Every other name has to be in the file: write NAME= for
# an empty value, so that a name that is missing (a new variable of the workflow, a typo) is found before a run starts.
OPTIONAL_NAMES = ("DRIFT_ACCEPTED_EXEMPTIONS", "DRIFT_ACCEPTED_DENY")
# A variable that one action alone reads, and that the owner adds to the file when he wants that action: not in the file that --init makes, and what a run says when it is missing.
SINGLE_ACTION_NAMES = {"TEAMS_BOT_ENABLED": f"only the action {TEAMS_ACTION} reads it: add the line TEAMS_BOT_ENABLED=True when the owner has asked for the Teams bot in writing"}
TEMPLATE_NAMES = ("ENV_SUBSCRIPTION_ID",) + VARIABLE_NAMES + SECRET_NAMES + OPTIONAL_NAMES
REQUIRED_NAMES = ("ENV_SUBSCRIPTION_ID", "AZURE_SUBSCRIPTION_ID", "AZURE_TENANT_ID", "ENV_RESOURCE_GROUP", "ENV_LOCATION")
FIRST_RUN_NUMBER = 1000
MIN_MASK_LENGTH = 3

# What a step does not inherit from the person's own environment: the tokens of GitHub, and the variables that only a real GitHub runner has (nothing that a step runs here looks like one).
STEP_ENV_DROPPED = ("GH_TOKEN", "GITHUB_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_URL", "ACTIONS_ID_TOKEN_REQUEST_TOKEN", "GITHUB_REPOSITORY")
STATUS_FUNCTIONS = ("always", "success", "failure", "cancelled")
SESSION_COMMANDS = (("login",), ("logout",), ("account", "set"), ("account", "clear"), ("configure",), ("config", "set"), ("config", "unset"))


class HubLocalError(Exception):
    """A refusal with a plain message: nothing was run, or nothing more was run."""


class WorkflowFormatError(HubLocalError):
    """The workflow has a layout that this tool does not read."""


class ExprError(HubLocalError):
    """An expression that this tool does not read, or that names something that is not there."""


# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# A reader for the part of YAML that the workflow uses: block mappings and sequences, plain and quoted one-line scalars, literal blocks. Everything else is an error, so that a layout that
# this tool does not understand is reported and never half read. All scalars are strings.
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
KEY = re.compile(r"([A-Za-z_][A-Za-z0-9_.-]*):(?: +|$)")
BLOCK_HEADER = re.compile(r"([|>])([+-]?)(?:\s+#.*)?")
ESCAPES = {'"': '"', "\\": "\\", "/": "/", "n": "\n", "t": "\t", "r": "\r", "0": "\0", " ": " "}


class Node(dict):
    """A mapping of the workflow, with the number of its first line."""

    line = 0


class _Reader:
    def __init__(self, text: str):
        self.lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.i = 0

    def fail(self, message: str, at: Optional[int] = None):
        raise WorkflowFormatError(f"line {(self.i if at is None else at) + 1}: {message}")

    def significant(self) -> bool:
        """Moves to the next line that holds more than blanks and a comment; False at the end of the text."""
        while self.i < len(self.lines):
            stripped = self.lines[self.i].strip()
            if stripped and not stripped.startswith("#"):
                return True
            self.i += 1
        return False

    def indent(self) -> int:
        line = self.lines[self.i]
        rest = line.lstrip(" ")
        if rest.startswith("\t"):
            self.fail("a tab in the indentation")
        return len(line) - len(rest)

    def document(self):
        if not self.significant():
            return None
        value = self.block(self.indent())
        if self.significant():
            self.fail("a line that does not belong to the structure above it")
        return value

    def block(self, indent: int):
        text = self.lines[self.i][indent:]
        if text == "-" or text.startswith("- "):
            return self.sequence(indent)
        return self.mapping(indent)

    def sequence(self, indent: int) -> list:
        items: list = []
        while self.significant():
            here = self.indent()
            if here < indent:
                break
            if here > indent:
                self.fail("unexpected indentation")
            text = self.lines[self.i][here:]
            if not (text == "-" or text.startswith("- ")):
                break
            rest = text[1:]
            body = rest.lstrip(" ")
            column = here + 1 + (len(rest) - len(body))
            if body == "" or body.startswith("#"):
                self.i += 1
                if self.significant() and self.indent() > indent:
                    items.append(self.block(self.indent()))
                else:
                    items.append(None)
            elif KEY.match(body):
                self.lines[self.i] = " " * column + body
                items.append(self.mapping(column))
            else:
                items.append(self.scalar(body))
                self.i += 1
        return items

    def mapping(self, indent: int) -> Node:
        result = Node()
        result.line = self.i + 1
        while self.significant():
            here = self.indent()
            if here < indent:
                break
            if here > indent:
                self.fail("unexpected indentation")
            text = self.lines[self.i][here:]
            if text == "-" or text.startswith("- "):
                break
            match = KEY.match(text)
            if not match:
                self.fail("expected a 'key: value' line")
            key = match.group(1)
            if key in result:
                self.fail(f"the key {key!r} is there twice")
            result[key] = self.value(text[match.end():], indent)
        return result

    def value(self, rest: str, indent: int):
        body = rest.strip()
        if body == "" or body.startswith("#"):
            self.i += 1
            if self.significant() and self.indent() > indent:
                return self.block(self.indent())
            return None
        header = BLOCK_HEADER.fullmatch(body)
        if header:
            if header.group(1) == ">":
                self.fail("a folded block scalar (>) is not read")
            return self.literal(indent, header.group(2))
        result = self.scalar(body)
        self.i += 1
        return result

    def literal(self, indent: int, chomp: str) -> str:
        self.i += 1
        block: list[str] = []
        block_indent: Optional[int] = None
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if line.strip() == "":
                block.append(line[block_indent:] if block_indent is not None and len(line) > block_indent else "")
                self.i += 1
                continue
            here = len(line) - len(line.lstrip(" "))
            if here <= indent:
                break
            if block_indent is None:
                block_indent = here
            elif here < block_indent:
                self.fail("a line of a block is indented less than the first line of the block")
            block.append(line[block_indent:])
            self.i += 1
        trailing = 0
        while block and block[-1] == "":
            block.pop()
            trailing += 1
        text = "\n".join(block)
        if chomp == "-":
            return text
        if chomp == "+":
            return text + "\n" * (trailing + 1) if block else "\n" * trailing
        return text + "\n" if block else ""

    def scalar(self, body: str) -> str:
        first = body[0]
        if first == '"':
            return self.double_quoted(body)
        if first == "'":
            return self.single_quoted(body)
        if first in "[{&*!>%@`|":
            self.fail(f"a value that starts with {first!r} is not read")
        return re.split(r"\s#", body, maxsplit=1)[0].rstrip()

    def after_quote(self, rest: str):
        rest = rest.strip()
        if rest and not rest.startswith("#"):
            self.fail("something follows the closing quote of a value")

    def double_quoted(self, body: str) -> str:
        out: list[str] = []
        i = 1
        while i < len(body):
            char = body[i]
            if char == '"':
                self.after_quote(body[i + 1:])
                return "".join(out)
            if char == "\\":
                if i + 1 >= len(body):
                    break
                escape = body[i + 1]
                if escape == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", body[i + 2:i + 6]):
                    out.append(chr(int(body[i + 2:i + 6], 16)))
                    i += 6
                    continue
                if escape not in ESCAPES:
                    self.fail(f"the escape \\{escape} in a quoted value is not read")
                out.append(ESCAPES[escape])
                i += 2
                continue
            out.append(char)
            i += 1
        self.fail("a quoted value has no closing quote on its line")

    def single_quoted(self, body: str) -> str:
        out: list[str] = []
        i = 1
        while i < len(body):
            char = body[i]
            if char == "'":
                if body[i + 1:i + 2] == "'":
                    out.append("'")
                    i += 2
                    continue
                self.after_quote(body[i + 1:])
                return "".join(out)
            out.append(char)
            i += 1
        self.fail("a quoted value has no closing quote on its line")


def parse_yaml(text: str):
    return _Reader(text).document()


# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# The workflow
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
STEP_KEYS = ("name", "id", "if", "uses", "with", "env", "run", "timeout-minutes")
ID_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


@dataclasses.dataclass
class InputSpec:
    name: str
    kind: str
    default: Any
    options: tuple


@dataclasses.dataclass
class Step:
    index: int
    line: int
    name: str
    id: str
    condition: Optional[str]
    uses: Optional[str]
    with_: dict
    env: dict
    run: Optional[str]
    timeout_minutes: Optional[float]
    unknown_keys: tuple


@dataclasses.dataclass
class Workflow:
    path: Path
    name: str
    inputs: dict
    job_name: str
    job_condition: Optional[str]
    job_env: dict
    job_timeout_minutes: float
    steps: list

    @property
    def actions(self) -> tuple:
        return self.inputs["action"].options


def _strings(node, what: str, line: int) -> dict:
    if node is None:
        return {}
    if not isinstance(node, dict):
        raise WorkflowFormatError(f"line {line}: {what} is not a mapping")
    result = {}
    for key, value in node.items():
        if isinstance(value, (dict, list)):
            raise WorkflowFormatError(f"line {line}: {what} {key!r} is not a plain value")
        result[key] = "" if value is None else value
    return result


def parse_workflow(text: str, path: Path = DEFAULT_WORKFLOW) -> Workflow:
    tree = parse_yaml(text)
    if not isinstance(tree, Node):
        raise WorkflowFormatError("the workflow is not a mapping")
    try:
        specs = tree["on"]["workflow_dispatch"]["inputs"]
    except (KeyError, TypeError):
        raise WorkflowFormatError("the workflow has no on.workflow_dispatch.inputs") from None
    inputs: dict = {}
    for name, spec in specs.items():
        if not isinstance(spec, Node):
            raise WorkflowFormatError(f"the input {name!r} is not a mapping")
        kind = spec.get("type") or "string"
        options = tuple(spec.get("options") or ())
        default = spec.get("default")
        if kind == "boolean":
            default = str(default).strip().lower() == "true"
        elif default is None:
            default = ""
        inputs[name] = InputSpec(name, kind, default, options)
    if "action" not in inputs or not inputs["action"].options:
        raise WorkflowFormatError("the workflow has no input 'action' with options")
    shell = (((tree.get("defaults") or {}).get("run") or {}).get("shell"))
    if shell not in (None, "bash"):
        raise WorkflowFormatError(f"the default shell of the workflow is {shell!r}: only bash is run here")
    jobs = tree.get("jobs")
    if not isinstance(jobs, Node) or len(jobs) != 1:
        raise WorkflowFormatError("the workflow has to have exactly one job")
    job_id, job = next(iter(jobs.items()))
    if not isinstance(job, Node) or not isinstance(job.get("steps"), list) or not job["steps"]:
        raise WorkflowFormatError(f"the job {job_id!r} has no steps")
    steps: list = []
    seen: set = set()
    for index, node in enumerate(job["steps"]):
        if not isinstance(node, Node):
            raise WorkflowFormatError(f"step {index + 1} is not a mapping")
        for key in ("run", "uses"):
            if key in node and isinstance(node[key], (dict, list)):
                raise WorkflowFormatError(f"line {node.line}: {key} is not a plain value")
        if ("run" in node) == ("uses" in node):
            raise WorkflowFormatError(f"line {node.line}: a step has either run or uses")
        step_id = node.get("id") or ""
        if step_id:
            if not ID_PATTERN.fullmatch(step_id) or step_id in seen:
                raise WorkflowFormatError(f"line {node.line}: the step id {step_id!r} is not valid or is used twice")
            seen.add(step_id)
        timeout = node.get("timeout-minutes")
        try:
            timeout_minutes = float(timeout) if timeout is not None else None
        except ValueError:
            raise WorkflowFormatError(f"line {node.line}: timeout-minutes {timeout!r} is not a number") from None
        steps.append(Step(index=index, line=node.line, name=node.get("name") or node.get("uses") or f"step {index + 1}", id=step_id, condition=node.get("if"),
                          uses=node.get("uses"), with_=_strings(node.get("with"), "with", node.line), env=_strings(node.get("env"), "env", node.line), run=node.get("run"),
                          timeout_minutes=timeout_minutes, unknown_keys=tuple(sorted(set(node) - set(STEP_KEYS)))))
    try:
        job_timeout = float(job.get("timeout-minutes") or 360)
    except ValueError:
        raise WorkflowFormatError("the timeout-minutes of the job is not a number") from None
    return Workflow(path=path, name=str(tree.get("name") or path.name), inputs=inputs, job_name=str(job.get("name") or job_id), job_condition=job.get("if"),
                    job_env=_strings(job.get("env"), "env", job.line), job_timeout_minutes=job_timeout, steps=steps)


def load_workflow(path: Path) -> Workflow:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise HubLocalError(f"the workflow {path} could not be read: {error}") from None
    return parse_workflow(text, Path(path))


# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# The expressions of the workflow: a small evaluator over a token list. Nothing here hands text to the interpreter. What it does not read is an error, and an error stops the run before any
# step starts.
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
class _Unknown:
    """The value of something that a dry run cannot know yet (the output of a step that has not run)."""

    def __repr__(self) -> str:
        return "UNKNOWN"


UNKNOWN = _Unknown()
NO_GITHUB_TOKEN = ("{0}: no GitHub token exists on this machine, and none is ever given to a step: a step that needs GitHub cannot run here, "
                   "and only a step that this tool replaces may name it")
MAX_EXPRESSION_LENGTH = 2000
MAX_DEPTH = 40
TOKEN = re.compile(r"(?P<string>'(?:[^']|'')*')|(?P<number>\d+(?:\.\d+)?)|(?P<op>&&|\|\||==|!=|!|\(|\)|,)|(?P<name>[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)*)")
INTERPOLATION = re.compile(r"\$\{\{(.*?)\}\}", re.S)
NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")


def tokenize(text: str) -> list:
    if len(text) > MAX_EXPRESSION_LENGTH:
        raise ExprError("an expression is longer than this tool reads")
    tokens: list = []
    pos = 0
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            return tokens
        match = TOKEN.match(text, pos)
        if not match:
            raise ExprError(f"the character {text[pos]!r} in {text!r} is not part of an expression that this tool reads")
        kind = match.lastgroup
        value = match.group(kind)
        if kind == "string":
            tokens.append(("string", value[1:-1].replace("''", "'")))
        elif kind == "number":
            tokens.append(("number", float(value) if "." in value else int(value)))
        elif kind == "op":
            tokens.append(("op", value))
        else:
            tokens.append(("name", value))
        pos = match.end()


class _ExprParser:
    def __init__(self, text: str):
        self.text = text
        self.tokens = tokenize(text)
        self.pos = 0
        self.depth = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else ("end", "")

    def take(self):
        token = self.peek()
        self.pos += 1
        return token

    def parse(self):
        if not self.tokens:
            raise ExprError("an expression is empty")
        node = self.or_()
        if self.pos != len(self.tokens):
            raise ExprError(f"unexpected {self.peek()[1]!r} in {self.text!r}")
        return node

    def or_(self):
        node = self.and_()
        while self.peek() == ("op", "||"):
            self.take()
            node = ("or", node, self.and_())
        return node

    def and_(self):
        node = self.equality()
        while self.peek() == ("op", "&&"):
            self.take()
            node = ("and", node, self.equality())
        return node

    def equality(self):
        node = self.unary()
        while self.peek() in (("op", "=="), ("op", "!=")):
            op = self.take()[1]
            node = ("eq" if op == "==" else "ne", node, self.unary())
        return node

    def unary(self):
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise ExprError("an expression is nested deeper than this tool reads")
        try:
            if self.peek() == ("op", "!"):
                self.take()
                return ("not", self.unary())
            return self.primary()
        finally:
            self.depth -= 1

    def primary(self):
        kind, value = self.take()
        if kind in ("string", "number"):
            return ("lit", value)
        if kind == "op" and value == "(":
            self.depth += 1
            if self.depth > MAX_DEPTH:
                raise ExprError("an expression is nested deeper than this tool reads")
            node = self.or_()
            self.depth -= 1
            if self.take() != ("op", ")"):
                raise ExprError(f"a parenthesis is not closed in {self.text!r}")
            return node
        if kind == "name":
            if self.peek() == ("op", "("):
                if "." in value:
                    raise ExprError(f"{value}(...) is not a function that this tool reads")
                self.take()
                args = []
                if self.peek() != ("op", ")"):
                    args.append(self.or_())
                    while self.peek() == ("op", ","):
                        self.take()
                        args.append(self.or_())
                if self.take() != ("op", ")"):
                    raise ExprError(f"a parenthesis is not closed in {self.text!r}")
                return ("call", value, args)
            literal = {"true": True, "false": False, "null": None}
            if value in literal:
                return ("lit", literal[value])
            return ("ref", tuple(value.split(".")))
        raise ExprError(f"unexpected {value!r} in {self.text!r}")


def parse_expression(text: str):
    return _ExprParser(text).parse()


def truthy(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0 and value == value
    return value != ""


def as_number(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text == "":
        return 0.0
    return float(text) if NUMBER.fullmatch(text) else math.nan


def loose_equals(left, right) -> bool:
    """GitHub's == : strings are compared without regard to case, and values of different types as numbers."""
    if isinstance(left, str) and isinstance(right, str):
        return left.casefold() == right.casefold()
    if left is None and right is None:
        return True
    if isinstance(left, bool) and isinstance(right, bool):
        return left == right
    return as_number(left) == as_number(right)


def to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def evaluate(node, ctx):
    kind = node[0]
    if kind == "lit":
        return node[1]
    if kind == "ref":
        return ctx.lookup(node[1])
    if kind == "call":
        return ctx.call(node[1], [evaluate(arg, ctx) for arg in node[2]])
    if kind == "not":
        value = evaluate(node[1], ctx)
        return UNKNOWN if value is UNKNOWN else not truthy(value)
    if kind == "and":
        left = evaluate(node[1], ctx)
        if left is UNKNOWN:
            right = evaluate(node[2], ctx)
            return right if right is not UNKNOWN and not truthy(right) else UNKNOWN
        return left if not truthy(left) else evaluate(node[2], ctx)
    if kind == "or":
        left = evaluate(node[1], ctx)
        if left is UNKNOWN:
            right = evaluate(node[2], ctx)
            return right if right is not UNKNOWN and truthy(right) else UNKNOWN
        return left if truthy(left) else evaluate(node[2], ctx)
    if kind in ("eq", "ne"):
        left = evaluate(node[1], ctx)
        right = evaluate(node[2], ctx)
        if left is UNKNOWN or right is UNKNOWN:
            return UNKNOWN
        same = loose_equals(left, right)
        return same if kind == "eq" else not same
    raise ExprError(f"an expression node of the kind {kind!r} is not known")


def walk(node):
    yield node
    for child in node[1:] if node[0] in ("not", "and", "or", "eq", "ne") else (node[2] if node[0] == "call" else ()):
        if isinstance(child, tuple):
            yield from walk(child)
        elif isinstance(child, list):
            for item in child:
                yield from walk(item)


def validate(node, ctx) -> None:
    """Looks up every reference and call of an expression, so that one that a short-circuit would skip is still found."""
    for part in walk(node):
        if part[0] == "ref":
            ctx.lookup(part[1])
        elif part[0] == "call":
            ctx.check_call(part[1], part[2])


def contains_status_function(node) -> bool:
    return any(part[0] == "call" and part[1] in STATUS_FUNCTIONS for part in walk(node))


class StepState:
    """What a later step may read of an earlier one."""

    def __init__(self, outcome, outputs):
        self.outcome = outcome
        self.outputs = outputs


class Context:
    """The values that an expression of the workflow may read. `planning` is a dry run: the outputs of steps are not known yet."""

    GITHUB_NAMES = ("run_number", "run_id", "actor", "ref", "ref_name", "sha", "event_name", "run_attempt", "workspace")

    def __init__(self, *, inputs: dict, variables: dict, secrets: dict, github: dict, runner_temp: str, step_ids: dict, planning: bool):
        self.inputs = inputs
        self.variables = variables
        self.secrets = secrets
        self.github = github
        self.runner_temp = runner_temp
        self.step_ids = step_ids
        self.planning = planning
        self.env: dict = {}
        self.steps: dict = {}
        self.job_status = "success"
        self.cancelled = False
        self.current_index = 0
        self.secret_names: set = set()
        self.variable_names: set = set()
        self.optional_unset: set = set()

    def check_call(self, name: str, args) -> None:
        if name not in STATUS_FUNCTIONS:
            raise ExprError(f"the function {name}() is not one that this tool reads (it reads {', '.join(n + '()' for n in STATUS_FUNCTIONS)})")
        if args:
            raise ExprError(f"{name}() takes no arguments")

    def call(self, name: str, args):
        self.check_call(name, args)
        if name == "always":
            return True
        if name == "success":
            return self.job_status == "success"
        if name == "failure":
            return self.job_status == "failure"
        return self.cancelled

    def lookup(self, parts: tuple):
        root, rest = parts[0], parts[1:]
        dotted = ".".join(parts)
        if root == "inputs" and len(rest) == 1:
            if rest[0] not in self.inputs:
                raise ExprError(f"{dotted}: the workflow has no such input")
            return self.inputs[rest[0]]
        if root in ("vars", "secrets") and len(rest) == 1:
            if root == "secrets" and rest[0].upper() == "GITHUB_TOKEN":
                raise ExprError(NO_GITHUB_TOKEN.format(dotted))
            table = self.variables if root == "vars" else self.secrets
            if rest[0] not in table:
                if root == "vars" and rest[0] in OPTIONAL_NAMES:
                    self.optional_unset.add(rest[0])
                    return ""
                hint = SINGLE_ACTION_NAMES.get(rest[0]) if root == "vars" else None
                raise ExprError(f"{dotted} is not defined in {CONFIG_NAME} ({hint or 'write the name with an empty value if empty is right'})")
            (self.variable_names if root == "vars" else self.secret_names).add(rest[0])
            return table[rest[0]]
        if root == "github" and rest == ("token",):
            raise ExprError(NO_GITHUB_TOKEN.format(dotted))
        if root == "github" and len(rest) == 1 and rest[0] in self.GITHUB_NAMES:
            if rest[0] not in self.github:
                raise ExprError(f"{dotted} has no value on this machine")
            return self.github[rest[0]]
        if root == "env" and len(rest) == 1:
            return self.env.get(rest[0], "")
        if root == "runner" and rest == ("temp",):
            return self.runner_temp
        if root == "job" and rest == ("status",):
            return self.job_status
        if root == "steps" and len(rest) >= 2:
            return self.lookup_step(dotted, rest)
        raise ExprError(f"{dotted}: this tool does not read that part of the workflow context")

    def lookup_step(self, dotted: str, rest: tuple):
        step_id, kind = rest[0], rest[1]
        if step_id not in self.step_ids:
            raise ExprError(f"{dotted}: no step has the id {step_id!r}")
        if self.step_ids[step_id] >= self.current_index:
            raise ExprError(f"{dotted}: the step {step_id!r} does not come before the step that reads it")
        state = self.steps.get(step_id)
        if kind == "outputs" and len(rest) == 3:
            if state is None:
                return UNKNOWN if self.planning else ""
            return UNKNOWN if state.outputs is UNKNOWN else state.outputs.get(rest[2], "")
        if kind in ("outcome", "conclusion") and len(rest) == 2:
            if state is None:
                return UNKNOWN if self.planning else ""
            return state.outcome
        raise ExprError(f"{dotted}: only steps.<id>.outputs.<name> and steps.<id>.outcome are read")


def unwrap(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("${{") and stripped.endswith("}}"):
        return stripped[3:-2]
    return stripped


def condition_result(text: Optional[str], ctx: Context):
    """True, False or UNKNOWN. A condition with no status function carries the implicit success() that GitHub adds."""
    node = parse_expression("success()" if text is None else unwrap(text))
    if ctx.planning:
        validate(node, ctx)
    value = evaluate(node, ctx)
    if not contains_status_function(node) and ctx.job_status != "success":
        return False
    return UNKNOWN if value is UNKNOWN else truthy(value)


def interpolate(text: str, ctx: Context, problems: Optional[list] = None, where: str = "") -> str:
    """Replaces every ${{ ... }} of a value. The replacement is never read again: a value that holds ${{ is text."""
    def replace(match):
        try:
            node = parse_expression(match.group(1).strip())
            if ctx.planning:
                validate(node, ctx)
            value = evaluate(node, ctx)
        except ExprError as error:
            if problems is None:
                raise
            problems.append(f"{where}: {error}")
            return match.group(0)
        return match.group(0) if value is UNKNOWN else to_text(value)
    return INTERPOLATION.sub(replace, text)


# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# The files that a step writes (GITHUB_OUTPUT, GITHUB_ENV) and the commands that it prints
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def parse_command_file(text: str) -> dict:
    """name=value lines and name<<DELIMITER blocks, as the runner of GitHub reads them."""
    lines = text.replace("\r\n", "\n").split("\n")
    result: dict = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if line == "":
            i += 1
            continue
        equals, heredoc = line.find("="), line.find("<<")
        if heredoc != -1 and (equals == -1 or heredoc < equals):
            name, delimiter = line[:heredoc], line[heredoc + 2:]
            if not name or not delimiter:
                raise HubLocalError(f"a line of a step's output file is not valid: {line[:60]!r}")
            body: list = []
            i += 1
            while i < len(lines) and lines[i] != delimiter:
                body.append(lines[i])
                i += 1
            if i >= len(lines):
                raise HubLocalError(f"a step's output file has no closing line {delimiter!r} for {name!r}")
            result[name] = "\n".join(body)
            i += 1
        elif equals > 0:
            result[line[:equals]] = line[equals + 1:]
            i += 1
        else:
            raise HubLocalError(f"a line of a step's output file is not valid: {line[:60]!r}")
    return result


COMMAND = re.compile(r"^::([A-Za-z-]+)(?: [^:]*)?::(.*)$")
LABELS = {"error": "ERROR", "warning": "WARNING", "notice": "NOTE"}


class Console:
    """Prints what a run says, masked, and keeps it in a log file as well."""

    def __init__(self, out=None, log_path: Optional[Path] = None):
        self.out = out if out is not None else sys.stdout
        self.masks: list = []
        self.log = open(log_path, "w", encoding="utf-8", newline="\n") if log_path else None
        self.errors = 0
        self.warnings = 0
        self.last_output = time.monotonic()

    def add_mask(self, value: str) -> None:
        if len(value) >= MIN_MASK_LENGTH and value not in self.masks:
            self.masks.append(value)
            self.masks.sort(key=len, reverse=True)

    def mask(self, text: str) -> str:
        for value in self.masks:
            if value in text:
                text = text.replace(value, "***")
        return text

    def emit(self, text: str) -> None:
        self.last_output = time.monotonic()
        text = self.mask(text)
        try:
            print(text, file=self.out, flush=True)
        except UnicodeEncodeError:
            print(text.encode("ascii", "replace").decode("ascii"), file=self.out, flush=True)
        if self.log:
            self.log.write(text + "\n")
            self.log.flush()

    def step_line(self, line: str) -> None:
        """One line of a step's output: workflow commands are translated, everything else is printed as it is."""
        match = COMMAND.match(line)
        if match:
            command, message = match.group(1).lower(), match.group(2)
            if command == "add-mask":
                self.add_mask(message)
                return
            if command in LABELS:
                if command == "error":
                    self.errors += 1
                elif command == "warning":
                    self.warnings += 1
                self.emit(f"{LABELS[command]}: {message}")
                return
            if command == "debug":
                return
            if command == "group":
                self.emit(f"-- {message}")
                return
            if command == "endgroup":
                return
        self.emit(line)

    def close(self) -> None:
        if self.log:
            self.log.close()
            self.log = None


# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# The machine: git, the local folder, the configuration, the run counter, the lock
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def posix(path) -> str:
    """The path with forward slashes: Git's bash and a native Python both open it."""
    return Path(path).as_posix()


def posix_absolute(path) -> str:
    """The form that Git's bash gives a Windows path (C:\\a\\b is /c/a/b): the build script of the function app tests for a leading slash."""
    text = Path(path).resolve().as_posix()
    if os.name == "nt" and len(text) > 2 and text[1] == ":":
        return "/" + text[0].lower() + text[2:]
    return text


run_git = guard.run_git


def resolve_local_dir(environ, cwd: Path, git: Callable = run_git) -> Path:
    """The git-ignored local/ folder of the repository's MAIN working tree, or the folder that METERNAUT_LOCAL names.

    A worktree has no local/ of its own: it is the parent of the common git directory that holds it, and every worktree finds the same configuration, counter, lock and records there. The tools that
    look for the proof of a run find the folder with the same function (tools/hubguard.py), so that the folder in which a run makes its proof is the folder in which they look for it."""
    try:
        return guard.local_folder(environ, cwd, git)
    except guard.NoLocalFolder as error:
        raise HubLocalError(str(error)) from None


def git_tracking(paths: list, git: Callable = run_git) -> str:
    """'outside' (no repository holds the paths), 'tracked', 'not-ignored' or 'ignored', for the paths together. Two git calls, whatever the number of paths."""
    names = [str(path) for path in paths]
    probe = Path(paths[0]).parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    code, listed, _ = git(["ls-files", "--", *names], probe)
    if code != 0:
        return "outside"
    if listed.strip():
        return "tracked"
    _, ignored, _ = git(["check-ignore", "--", *names], probe)
    return "ignored" if len([line for line in ignored.splitlines() if line.strip()]) == len(names) else "not-ignored"


def require_ignored(paths: list, git: Callable = run_git) -> None:
    where = git_tracking(paths, git)
    if where == "tracked":
        raise HubLocalError(f"{paths[0]} is tracked by git: it holds values that never go in a commit (AGENTS.md rule 17). Take it out of git first")
    if where == "not-ignored":
        raise HubLocalError(f"{paths[0]} (or the records folder next to it) is not ignored by git: it holds values that never go in a commit (AGENTS.md rule 17). "
                            "The repository's .gitignore has to list the local/ folder")


def parse_env_file(text: str) -> dict:
    """NAME=VALUE lines; a line that starts with # is a comment; a value may be wrapped in one pair of quotes. A name that is there twice is refused."""
    values: dict = {}
    for number, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise HubLocalError(f"{CONFIG_NAME} line {number}: expected NAME=VALUE")
        if name in values:
            raise HubLocalError(f"{CONFIG_NAME} line {number}: {name} is there twice")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" and value[0] not in value[1:-1]:
            value = value[1:-1]
        values[name] = value
    return values


GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def reconcile_config(values: dict) -> tuple:
    """(the values, notes, problems): the two names of the subscription are one value, and what a run cannot do without has to be there."""
    values = dict(values)
    notes: list = []
    problems: list = []
    env_id, secret_id = values.get("ENV_SUBSCRIPTION_ID", ""), values.get("AZURE_SUBSCRIPTION_ID", "")
    if env_id and secret_id and env_id.lower() != secret_id.lower():
        problems.append(f"{CONFIG_NAME}: ENV_SUBSCRIPTION_ID and AZURE_SUBSCRIPTION_ID are not the same subscription")
    elif env_id and not secret_id:
        values["AZURE_SUBSCRIPTION_ID"] = env_id
        notes.append("AZURE_SUBSCRIPTION_ID was not in the configuration: it is the same as ENV_SUBSCRIPTION_ID")
    elif secret_id and not env_id:
        values["ENV_SUBSCRIPTION_ID"] = secret_id
        notes.append("ENV_SUBSCRIPTION_ID was not in the configuration: it is the same as AZURE_SUBSCRIPTION_ID")
    for name in REQUIRED_NAMES:
        if not values.get(name):
            problems.append(f"{CONFIG_NAME}: {name} has no value")
    for name in ("ENV_SUBSCRIPTION_ID", "AZURE_TENANT_ID"):
        if values.get(name) and not GUID.fullmatch(values[name]):
            problems.append(f"{CONFIG_NAME}: {name} is not an id (8-4-4-4-12 hexadecimal digits)")
    return values, notes, problems


def load_config(local: Path, git: Callable = run_git) -> tuple:
    path = local / CONFIG_NAME
    if not path.is_file():
        raise HubLocalError(f"{path} does not exist. Run `python tools/hub-local.py --init` and fill it in")
    require_ignored([path, local / RECORDS_NAME / "hub-local-record.md"], git)
    try:
        values = parse_env_file(path.read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise HubLocalError(f"{path} could not be read: {error}") from None
    return reconcile_config(values)


def load_state(local: Path) -> dict:
    path = local / STATE_NAME
    if not path.is_file():
        raise HubLocalError(f"{path} does not exist. Run `python tools/hub-local.py --init`: the run counter starts above the highest number that the Hub reached on GitHub")
    try:
        state = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(state, dict) or not isinstance(state.get("lastRun"), int) or isinstance(state["lastRun"], bool) or state["lastRun"] < 0:
            raise ValueError("lastRun is not a whole number")
    except (OSError, ValueError) as error:
        raise HubLocalError(f"{path} is not a valid state file: {error}") from None
    return state


def save_state(local: Path, state: dict) -> None:
    path = local / STATE_NAME
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


process_alive = guard.process_alive


class Lock:
    """One run at a time: a file in the local folder, made with O_EXCL. It names the run that holds it and what that run changed on the machine."""

    def __init__(self, path: Path, info: dict, pid_alive: Callable = process_alive):
        self.path = path
        self.info = dict(info)
        self.pid_alive = pid_alive
        self.held = False

    def acquire(self) -> Optional[dict]:
        """Takes the lock. Returns what a dead run's lock said when one was found and removed, else None."""
        stale = None
        for _ in range(3):
            try:
                handle = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    held = json.loads(self.path.read_text(encoding="utf-8"))
                    if not isinstance(held, dict):
                        held = {}
                except (OSError, ValueError):
                    held = {}
                if self.pid_alive(held.get("pid")):
                    raise HubLocalError(f"another run holds the lock {self.path} (process {held.get('pid')}, action {held.get('action')}, started {held.get('started')}). "
                                        "Wait for it. If that run is gone, delete the file")
                stale = held
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                continue
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(self.info))
            self.held = True
            return stale
        raise HubLocalError(f"the lock {self.path} could not be taken")

    def update(self, **fields) -> None:
        self.info.update(fields)
        if self.held:
            self.path.write_text(json.dumps(self.info), encoding="utf-8", newline="\n")

    def release(self) -> None:
        if self.held:
            self.held = False
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


def drop_stale_proof(rt_base: Path, stale: dict) -> None:
    """The proof of a run that was killed: its file is left behind, and the lock that named it is taken over. Only a folder that is named like a run's is followed."""
    run = str(stale.get("run") or "")
    if re.fullmatch(r"[0-9]{1,12}", run):
        try:
            (rt_base / run / guard.PROOF_NAME).unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# The Azure CLI and Git's bash
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def refused_session_command(args) -> Optional[str]:
    """Why a command of the Azure CLI is not run for a step: it would change the owner's session. None when it is fine."""
    words = [str(word) for word in args]
    for command in SESSION_COMMANDS:
        if tuple(words[:len(command)]) == command:
            return f"az {' '.join(command)} is not run by a step of the Hub: the owner's own az session is used as it is (the run sets the subscription itself and puts the CLI's default back)"
    return None


class AzCli:
    """The Azure CLI of this machine. On Windows it is run through its own python.exe: az.cmd goes through cmd.exe, which takes an ampersand or a quote inside an argument for its own."""

    def __init__(self, argv: list):
        self.argv = [str(part) for part in argv]

    @classmethod
    def find(cls, environ=None) -> "AzCli":
        environ = os.environ if environ is None else environ
        if os.name == "nt":
            candidates = []
            exe = shutil.which("az")
            if exe:
                candidates.append(Path(exe).resolve().parent.parent / "python.exe")
            for variable in ("ProgramFiles", "ProgramFiles(x86)"):
                if environ.get(variable):
                    candidates.append(Path(environ[variable]) / "Microsoft SDKs" / "Azure" / "CLI2" / "python.exe")
            for python in candidates:
                if python.is_file():
                    # -I ignores PYTHONUTF8 and PYTHONIOENCODING, so the CLI would write the Windows code page into a pipe (an em dash is the byte 0x97): -X utf8 is a command line option and holds under -I.
                    return cls([str(python), "-X", "utf8", "-IBm", "azure.cli"])
            raise HubLocalError("the Azure CLI was not found. This tool needs the Windows (MSI) install: it runs the CLI's own python.exe, because az.cmd goes through cmd.exe, which mangles the arguments")
        exe = shutil.which("az")
        if not exe:
            raise HubLocalError("the Azure CLI (az) was not found on the PATH")
        return cls([exe])

    def environment(self) -> dict:
        env = dict(os.environ)
        if os.name == "nt":
            env["AZ_INSTALLER"] = "MSI"
        env["AZ_LAUNCHER"] = "bash"
        return env

    def run(self, args: list, timeout: float = 300) -> tuple:
        try:
            done = subprocess.run([*self.argv, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=timeout,
                                  env=self.environment())
        except subprocess.TimeoutExpired:
            return 124, "", f"az {' '.join(args[:3])} did not answer within {int(timeout)} seconds"
        except OSError as error:
            return 127, "", str(error)
        return done.returncode, done.stdout, done.stderr


def is_git_bash(path: str) -> bool:
    try:
        done = subprocess.run([path, "--noprofile", "--norc", "-c", "uname -s"], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0 and done.stdout.strip().upper().startswith(("MINGW", "MSYS", "CYGWIN"))


def find_bash(environ=None) -> str:
    """Git's bash. Not the bash.exe of System32 (the launcher of WSL, a different Linux): the one that Git for Windows installs, found by what it says about itself."""
    environ = os.environ if environ is None else environ
    if os.name != "nt":
        found = shutil.which("bash")
        if not found:
            raise HubLocalError("bash was not found on the PATH")
        return found
    candidates: list = []
    if environ.get("HUB_LOCAL_BASH"):
        candidates.append(Path(environ["HUB_LOCAL_BASH"]))
    for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = environ.get(variable)
        if base:
            root = Path(base) / "Programs" / "Git" if variable == "LOCALAPPDATA" else Path(base) / "Git"
            candidates += [root / "bin" / "bash.exe", root / "usr" / "bin" / "bash.exe"]
    git = shutil.which("git")
    if git:
        top = Path(git).resolve().parent.parent
        candidates += [top / "bin" / "bash.exe", top / "usr" / "bin" / "bash.exe"]
    for candidate in candidates:
        if candidate.is_file() and is_git_bash(str(candidate)):
            return str(candidate)
    raise HubLocalError("Git's bash was not found (looked for C:\\Program Files\\Git\\bin\\bash.exe and next to git.exe). Install Git for Windows, or set HUB_LOCAL_BASH to its bash.exe")


def python_shim(python: str) -> str:
    return f"#!/usr/bin/env bash\nexec {shlex.quote(posix(python))} \"$@\"\n"


def az_shim(argv: list) -> str:
    quoted = " ".join(shlex.quote(posix(part) if os.sep in part or "/" in part else part) for part in argv)
    install = "export AZ_INSTALLER=MSI AZ_LAUNCHER=bash\n" if os.name == "nt" else "export AZ_LAUNCHER=bash\n"
    return ("#!/usr/bin/env bash\n"
            "# Written by tools/hub-local.py: the Azure CLI of this machine, and never a command that changes the owner's session.\n"
            "case \"${1:-}\" in\n"
            "  login|logout|configure) echo \"ERROR: az $1 is not run by a step of the Hub: the owner's own az session is used as it is.\" >&2; exit 97 ;;\n"
            "  account) case \"${2:-}\" in set|clear) echo \"ERROR: az account $2 is not run by a step of the Hub: the run sets the subscription itself and puts the CLI's default back.\" >&2; exit 97 ;; esac ;;\n"
            "  config) case \"${2:-}\" in set|unset) echo \"ERROR: az config $2 is not run by a step of the Hub.\" >&2; exit 97 ;; esac ;;\n"
            "esac\n"
            f"{install}"
            f"exec {quoted} \"$@\"\n")


# The hook that a native Python gets on Windows (CreateProcess does not run a file called az, and az.cmd mangles arguments): `subprocess` is told to start the CLI's own python.exe.
SITECUSTOMIZE = '''# Written by tools/hub-local.py. Makes `az` in a subprocess of a tool the Azure CLI's own python.exe, and keeps it from changing the owner's session.
import json
import os
import subprocess
import sys

_argv = json.loads(os.environ.get("HUB_LOCAL_AZ") or "null")
_session = %(session)s
if _argv:
    _original = subprocess.Popen.__init__

    def _init(self, args, *rest, **options):
        if isinstance(args, (list, tuple)) and args and os.path.basename(str(args[0])).lower() in ("az", "az.cmd", "az.exe", "az.bat"):
            tail = [str(word) for word in args[1:]]
            refused = [command for command in _session if tail[:len(command)] == command]
            if refused:
                message = "ERROR: az " + " ".join(refused[0]) + " is not run by a tool of the Hub: the owner's own az session is used as it is."
                args = [sys.executable, "-c", "import sys; sys.stderr.write(sys.argv[1] + chr(10)); sys.exit(97)", message]
            else:
                args = list(_argv) + tail
        _original(self, args, *rest, **options)

    subprocess.Popen.__init__ = _init
'''


def sitecustomize_text() -> str:
    return SITECUSTOMIZE % {"session": json.dumps([list(command) for command in SESSION_COMMANDS])}


def windows_job():
    """(kernel32, a job object that ends every process in it when it is terminated or closed), or None. Git's bash (MSYS) starts programs in a way that loses the parent links that
    `taskkill /T` follows: a `sleep` or an `az` that a step started survives the kill of its bash. A job object holds every process that its members start, whatever their parents are."""
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class Counters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount",
                                                              "OtherTransferCount")]

    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", Counters), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = Extended()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: when this tool goes, so does everything that a step started
    if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        kernel32.CloseHandle(job)
        return None
    return kernel32, job


class ProcessGroup:
    """Everything that one command starts, so that all of it can be ended: a job object on Windows, a process group elsewhere."""

    def __init__(self, proc: subprocess.Popen):
        self.proc = proc
        self.job = None
        if os.name == "nt":
            try:
                made = windows_job()
                if made and made[0].AssignProcessToJobObject(made[1], int(proc._handle)):
                    self.job = made
                elif made:
                    made[0].CloseHandle(made[1])
            except (OSError, AttributeError, ValueError):
                self.job = None

    def kill(self) -> None:
        if self.job:
            self.job[0].TerminateJobObject(self.job[1], 1)
        elif os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True)
        else:
            import signal
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except OSError:
                pass
        try:
            self.proc.kill()
        except OSError:
            pass

    def interrupt(self) -> None:
        """Asks for a clean stop. On Windows the console has sent Ctrl+C to everything that shares it already; elsewhere the command is in a session of its own and is told."""
        if os.name != "nt":
            import signal
            try:
                os.killpg(self.proc.pid, signal.SIGINT)
            except OSError:
                pass

    def close(self) -> None:
        if self.job:
            self.job[0].CloseHandle(self.job[1])
            self.job = None


INTERRUPT_GRACE_SECONDS = 60
HEARTBEAT_SECONDS = 120


def run_process(argv: list, env: dict, cwd, console: Console, timeout_seconds: float) -> tuple:
    """Runs a command with its output streamed live through the console. Returns (exit code, timed out).

    Everything that the command starts is in one group (a job object on Windows), so that a timeout ends all of it, and so does the end of the command: a step does not leave an az or a
    container-group call running. A Ctrl+C reaches the command too, as it does when a person runs it by hand, and a tool that cleans up after itself (operator-run.py deletes its container
    group) gets up to a minute for that; a second Ctrl+C, or the minute, ends it. The output is read by a thread, because a blocking read of a pipe is not interrupted by Ctrl+C on
    Windows, while a wait with a timeout is. A command that is silent for two minutes is said to be still running."""
    options: dict = {}
    if os.name != "nt":
        options["start_new_session"] = True
    proc = subprocess.Popen(argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **options)
    group = ProcessGroup(proc)

    def pump() -> None:
        for raw in iter(proc.stdout.readline, b""):
            console.step_line(raw.decode("utf-8", errors="replace").rstrip("\r\n"))

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    began = time.monotonic()
    deadline = began + timeout_seconds
    timed_out = False
    try:
        while proc.poll() is None:
            reader.join(0.2)
            if not reader.is_alive():
                time.sleep(0.2)
            now = time.monotonic()
            if not timed_out and now > deadline:
                timed_out = True
                group.kill()
            if now - console.last_output > HEARTBEAT_SECONDS:
                console.emit(f"    ... still running after {(now - began) / 60:.0f} minutes")
        reader.join(2)
        group.kill()
        reader.join(5)
    except KeyboardInterrupt:
        group.interrupt()
        try:
            end = time.monotonic() + INTERRUPT_GRACE_SECONDS
            while proc.poll() is None and time.monotonic() < end:
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        group.kill()
        raise
    except BaseException:
        group.kill()
        raise
    finally:
        group.close()
        reader.join(2)
        if not reader.is_alive():
            try:
                proc.stdout.close()
            except OSError:
                pass
    return proc.returncode, timed_out


def remove_tree(path: Path) -> bool:
    """Deletes a folder. Read-only files (a build leaves some) are made writable first. False when something is still there."""
    def writable(function, target, *_):
        try:
            os.chmod(target, stat.S_IWRITE)
            function(target)
        except OSError:
            pass

    for _ in range(3):
        if not path.exists():
            return True
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=writable)
        else:
            shutil.rmtree(path, onerror=writable)
        if not path.exists():
            return True
        time.sleep(0.5)
    return not path.exists()


# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# What is replaced, and what cannot run here
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class Replacement:
    kind: str
    note: str
    # False: the step is not run and its env is not read (it names things that do not exist here, such as a GitHub token).
    env_used: bool = True
    # True: the step runs as written, but with Git's path conversion on and its temp folder as /c/... (see POSIX_PATH_NOTE).
    posix_paths: bool = False


POSIX_PATH_NOTE = ("runs as written, with Git's path conversion on and the temp folder as /c/...: the build script of the function app takes only a path that starts with a slash. "
                   "What it makes is not sent anywhere: the package is built by the publish step that follows")
USES_REPLACEMENTS = (
    ("actions/checkout@", Replacement("checkout", "the repository is this checkout")),
    ("actions/setup-python@", Replacement("python", "python3 is the Python that runs this tool; it has to be the version that the step asks for")),
    ("azure/login@", Replacement("az-session", "the owner's own az session is used: there is no sign-in with a federated credential here")),
)
# Found by what the script does and not by the name of the step, so that a step that is renamed is still found. A step that carries a token request and is not here stops the run.
RUN_REPLACEMENTS = (
    ("--script operator/publish.sh", Replacement("cases-publish", "built here and published from this machine through the app's public deployment site; the Operator's route needs a GitHub OpenID Connect token")),
    ("FUNCTION_APP_SOURCES_ONLY=1", Replacement("cases-pack", POSIX_PATH_NOTE, posix_paths=True)),
    ("--prefix op-publish-", Replacement("cases-publish-cleanup", "not needed: the publish made no container group")),
    ("PROBE_TOKEN_NOTE", Replacement("no-token", "no GitHub OpenID Connect token exists on this machine: the step goes on without the check of the deploy identity, and says so itself")),
    ("actions/workflows/checks.yml/runs", Replacement("ci-checks", "the checks of CI are not asked of GitHub: the person who starts the run ran them on this machine (no GitHub call is made from here)", env_used=False)),
)
OIDC_MARKERS = ("ACTIONS_ID_TOKEN_REQUEST_URL", "ACTIONS_ID_TOKEN_REQUEST_TOKEN")
# A call of the GitHub command line: the owner's own stored sign-in would answer it, and no GitHub call is made from here but the one read of `--init --from-github`.
GITHUB_CALL = re.compile(r"(?m)(?:^[ \t]*(?:(?:if|then|do|else|elif|while|until)\b[ \t]*)*|[;&|(`!{]|\$\()[ \t]*gh[ \t]+[a-z]")
UNIT_TEST_LINE = re.compile(r"(?m)^[ \t]*python3?[ \t]+-m[ \t]+unittest\b.*$")
APP_NAME = re.compile(r"[A-Za-z0-9-]{2,60}")


def classify(step: Step) -> tuple:
    """(the replacement of a step or None, why the step cannot run here or None)."""
    if step.unknown_keys:
        return None, f"it uses {', '.join(step.unknown_keys)}, which this tool does not read"
    if step.uses:
        for prefix, replacement in USES_REPLACEMENTS:
            if step.uses.startswith(prefix):
                return replacement, None
        return None, f"it uses the action {step.uses.split('@')[0]}, which cannot run on this machine"
    script = step.run or ""
    if "${{" in script:
        return None, "its script holds a ${{ expression (tools/workflow-lint.py forbids that: a value reaches a script through env)"
    for marker, replacement in RUN_REPLACEMENTS:
        if marker in script:
            return replacement, None
    if any(marker in script for marker in OIDC_MARKERS):
        return None, "it asks GitHub for an OpenID Connect token, which does not exist on this machine, and no replacement is known for it"
    if GITHUB_CALL.search(script):
        return None, "it calls GitHub with gh, and no GitHub call is made from this machine; no replacement is known for it"
    return None, None


@dataclasses.dataclass
class PlannedStep:
    step: Step
    verdict: Any
    replacement: Optional[Replacement] = None


@dataclasses.dataclass
class Plan:
    entries: list
    problems: list
    notes: list


def input_values(workflow: Workflow, args) -> dict:
    values = {name: spec.default for name, spec in workflow.inputs.items()}
    values["action"] = args.action
    if args.minutes is not None and "minutes" in values:
        values["minutes"] = str(args.minutes)
    if "public_ai_gateway_requested" in values:
        values["public_ai_gateway_requested"] = bool(args.public_ai_gateway_requested)
    if "public_teams_bot_requested" in values:
        values["public_teams_bot_requested"] = bool(args.public_teams_bot_requested)
    if "plant_public_ip" in values:
        values["plant_public_ip"] = bool(args.plant_public_ip)
    if "plant_vm" in values:
        values["plant_vm"] = bool(getattr(args, "plant_vm", False))
    for name in ("evals_command", "evals_judge", "redteam_mode"):
        given = getattr(args, name, None)
        if given is None:
            continue
        if name not in workflow.inputs:
            raise HubLocalError(f"{INPUT_FLAGS[name]} was given, and the workflow has no input {name}")
        options = workflow.inputs[name].options
        if options and given not in options:
            raise HubLocalError(f"{INPUT_FLAGS[name]} {given!r} is not one of the options of the input {name}: {', '.join(options)}")
        values[name] = given
    return values


def changes_azure(action: str, inputs: dict) -> bool:
    """False for an action that only reads (or makes a container group that it deletes): it needs no --yes and takes no run number. Every other action, and any that is not known, changes Azure."""
    if action in READ_ONLY_ACTIONS:
        return False
    rule = READ_ONLY_INPUT_VALUES.get(action)
    return not (rule and inputs.get(rule[0]) in rule[1])


def given_flags(args) -> dict:
    """Which input flags the person gave."""
    return {"minutes": args.minutes is not None, "plant_public_ip": bool(args.plant_public_ip), "plant_vm": bool(getattr(args, "plant_vm", False)),
            "public_ai_gateway_requested": bool(args.public_ai_gateway_requested), "public_teams_bot_requested": bool(args.public_teams_bot_requested),
            "evals_command": getattr(args, "evals_command", None) is not None, "evals_judge": getattr(args, "evals_judge", None) is not None,
            "redteam_mode": getattr(args, "redteam_mode", None) is not None}


def ignored_flags(args) -> list:
    """The flags that the person gave and that the action does not read: the workflow ignores such an input, and the plan says so."""
    return [f"{INPUT_FLAGS[name]} is only for {' and '.join(INPUT_ACTIONS[name])}: the action {args.action} ignores it" for name, was_given in given_flags(args).items()
            if was_given and args.action not in INPUT_ACTIONS[name]]


def inputs_line(workflow: Workflow, args) -> str:
    """The inputs that the action reads, with the value that each has: the plan never leaves one to be guessed."""
    values, given = input_values(workflow, args), given_flags(args)
    shown = []
    for name, actions in INPUT_ACTIONS.items():
        if args.action in actions and name in values:
            value = str(values[name]).lower() if isinstance(values[name], bool) else values[name]
            shown.append(f"{name}={value}" + ("" if given[name] else " (the workflow's default)"))
    return ", ".join(shown)


def job_environment(workflow: Workflow, ctx: Context, problems: Optional[list]) -> dict:
    env: dict = {}
    for name, text in workflow.job_env.items():
        env[name] = interpolate(text, ctx, problems, f"the job's env {name}")
        ctx.env[name] = env[name]
    return env


def build_plan(workflow: Workflow, ctx: Context, problems: list, notes: list) -> Plan:
    """Walks the steps of the action in order with the facts that are known before a run (inputs, configuration), and what a step's own condition says about later ones."""
    problems, notes = list(problems), list(notes)
    job_environment(workflow, ctx, problems)
    if workflow.job_condition is not None:
        try:
            if condition_result(workflow.job_condition, ctx) is not True:
                problems.append(f"the condition of the job is not true for a local run (actor {LOCAL_ACTOR}, ref {LOCAL_REF}): {workflow.job_condition}")
        except ExprError as error:
            problems.append(f"the condition of the job: {error}")
    entries: list = []
    for step in workflow.steps:
        ctx.current_index = step.index
        where = f"step {step.index + 1} ({step.name[:70]})"
        entry = PlannedStep(step, UNKNOWN)
        try:
            entry.verdict = condition_result(step.condition, ctx)
        except ExprError as error:
            problems.append(f"{where}: its condition: {error}")
        if entry.verdict is not False:
            entry.replacement, reason = classify(step)
            if reason:
                problems.append(f"{where}: {reason}")
            if entry.replacement is None or entry.replacement.env_used:
                for key, text in list(step.env.items()) + list(step.with_.items()):
                    interpolate(text, ctx, problems, f"{where}: {key}")
        if step.id:
            if entry.verdict is True:
                ctx.steps[step.id] = StepState("success", UNKNOWN)
            elif entry.verdict is False:
                ctx.steps[step.id] = StepState("skipped", {})
            else:
                ctx.steps[step.id] = StepState(UNKNOWN, UNKNOWN)
        entries.append(entry)
    return Plan(entries, problems, notes)


def format_plan(workflow: Workflow, plan: Plan) -> list:
    """The steps that would run (and those that might: their condition reads what an earlier step makes), with what replaces them."""
    total = len(workflow.steps)
    lines = []
    for entry in plan.entries:
        if entry.verdict is False:
            continue
        step = entry.step
        label = "RUN  " if entry.verdict is True else "MAYBE"
        line = f"  {step.index + 1:>3}/{total}  {label}  {step.name[:96]}"
        if entry.verdict is not True:
            line += f"\n                    decided when the run reaches it: if {step.condition}"
        if entry.replacement:
            line += f"\n                    replaced here: {entry.replacement.note}"
        lines.append(line)
    skipped = sum(1 for entry in plan.entries if entry.verdict is False)
    lines.append(f"  {skipped} of the {total} steps {'is' if skipped == 1 else 'are'} not for this action (their condition is false).")
    return lines


def run_gh(args: list, cwd) -> tuple:
    """The one call to GitHub that this tool can make, and only for `--init --from-github`: it reads the variables and the newest run number once."""
    try:
        done = subprocess.run(["gh", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as error:
        return 127, "", str(error)
    return done.returncode, done.stdout, done.stderr


@dataclasses.dataclass
class Deps:
    """What touches the machine, so that a test can put a fake in its place."""

    root: Path = ROOT
    git: Callable = run_git
    az: Callable = AzCli.find
    bash: Callable = find_bash
    gh: Callable = run_gh
    pid_alive: Callable = process_alive
    clock: Callable = lambda: dt.datetime.now(dt.timezone.utc)
    sleep: Callable = time.sleep


@dataclasses.dataclass
class StepRecord:
    number: int
    name: str
    outcome: str
    how: str
    seconds: float


def iso(moment: dt.datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def minutes_text(seconds: float) -> str:
    return f"{seconds / 60:.1f}"


class Hub:
    """One run (or one dry run) of an action."""

    def __init__(self, args, environ, deps: Deps, out):
        self.args = args
        self.environ = environ
        self.deps = deps
        self.out = out
        self.root = Path(deps.root)
        self.console: Optional[Console] = None
        self.ctx: Optional[Context] = None
        self.workflow: Optional[Workflow] = None
        self.values: dict = {}
        self.head = ""
        self.dirty: list = []
        self.steps_started = False
        self.records: list = []
        self.summary: list = []
        self.used: list = []
        self.github_env: dict = {}
        self.base_env: dict = {}
        self.job_env: dict = {}
        self.az: Any = None
        self.bash = ""
        self.rt: Optional[Path] = None
        self.proof: Optional[Path] = None
        self.lock: Optional[Lock] = None
        self.previous_default: Optional[dict] = None
        self.default_changed = False
        self.session_user = ""
        self.restore_note = "the CLI's default subscription was not changed"

    # ---- the facts of a run --------------------------------------------------------------------------------------------------------------------------------------------------------------
    def git_state(self) -> tuple:
        """(the head commit, the changed paths): one call, `git status --porcelain=v2 --branch`, which says both."""
        code, out, _ = self.deps.git(["status", "--porcelain=v2", "--branch"], self.root)
        head = ""
        dirty: list = []
        for line in out.splitlines():
            if line.startswith("# branch.oid "):
                head = line.split(" ", 2)[2].strip()
            elif line.strip() and not line.startswith("#"):
                dirty.append(line)
        if code != 0 or not re.fullmatch(r"[0-9a-f]{40,64}", head):
            raise HubLocalError("git could not read the head commit and the state of this checkout")
        return head, dirty

    def say(self, text: str) -> None:
        (self.console or Console(self.out)).emit(text)

    # ---- the plan and the guards ---------------------------------------------------------------------------------------------------------------------------------------------------------
    def go(self) -> int:
        args, deps = self.args, self.deps
        workflow = load_workflow(Path(args.workflow) if args.workflow else self.root / ".github" / "workflows" / "deploy-hub.yml")
        action = args.action
        if action not in workflow.actions:
            raise HubLocalError(f"{action!r} is not an action of the workflow. It has: {', '.join(workflow.actions)}")
        inputs = input_values(workflow, args)
        writes = changes_azure(action, inputs)
        local = resolve_local_dir(self.environ, self.root, deps.git)
        values, notes, problems = load_config(local, deps.git)
        state = load_state(local)
        run_number = state["lastRun"] + 1
        run_id = int(deps.clock().timestamp())
        head, dirty = self.git_state()
        rt = local / TEMP_NAME / str(run_id)
        ctx = Context(inputs=inputs, variables=values, secrets=values, runner_temp=posix(rt), planning=True,
                      step_ids={step.id: step.index for step in workflow.steps if step.id},
                      github={"run_number": run_number, "run_id": run_id, "actor": LOCAL_ACTOR, "ref": LOCAL_REF, "ref_name": "main", "sha": head, "event_name": "workflow_dispatch",
                              "run_attempt": 1, "workspace": posix(self.root)})
        plan = build_plan(workflow, ctx, problems, notes + ignored_flags(args))
        for name in sorted(ctx.optional_unset):
            plan.notes.append(f"{name} is not in {CONFIG_NAME}: it is optional, and it is read as empty, as GitHub reads a variable that is not set")
        refusals = []
        if writes and not args.yes:
            refusals.append(f"the action {action} changes Azure: it needs --yes")
        if action == PUBLIC_GATEWAY_ACTION and not args.public_ai_gateway_requested:
            refusals.append("the AI Gateway's front door is public and cannot be made private: the action aigateway needs --public-ai-gateway-requested, which only the owner's written request allows")
        if action == TEAMS_ACTION and not args.public_teams_bot_requested:
            refusals.append("the Teams bot's messaging endpoint is public by necessity: the action teams needs --public-teams-bot-requested, which only the owner's written request allows")
        if writes and dirty and not args.allow_dirty:
            refusals.append(f"the working tree is not clean ({len(dirty)} paths): commit or stash first, or pass --allow-dirty")
        console = Console(self.out)
        self.print_plan(console, workflow, plan, local, values, head, dirty, run_number, writes, state)
        if plan.problems:
            console.emit("")
            console.emit("These stop the run before anything is done:")
            for problem in plan.problems:
                console.emit(f"  - {problem}")
            return 2
        if args.dry_run:
            console.emit("")
            console.emit(f"Hub (local) {action}: dry run, nothing was run" + (f" (a real run would be refused: {'; '.join(refusals)})" if refusals else ""))
            return 0
        if refusals:
            console.emit("")
            console.emit("Refused, so this was a dry run:")
            for refusal in refusals:
                console.emit(f"  - {refusal}")
            return 2
        return self.run(workflow, plan, ctx, values, local, state, writes, head, dirty, run_number, run_id, rt)

    def print_plan(self, console: Console, workflow: Workflow, plan: Plan, local: Path, values: dict, head: str, dirty: list, run_number: int, writes: bool, state: dict) -> None:
        action = self.args.action
        empty = sorted(name + (" (optional)" if name in OPTIONAL_NAMES else "") for name, value in values.items() if value == "")
        console.emit(f"Hub (local) {action}: the plan" + (" (a dry run: nothing is run, nothing is changed, no az session is needed)" if self.args.dry_run else ""))
        console.emit(f"  workflow       {workflow.path.name}: {len(workflow.steps)} steps, {len(workflow.actions)} actions")
        console.emit(f"  action         {action} ({'changes Azure' if writes else 'reads only'})")
        inputs = inputs_line(workflow, self.args)
        if inputs:
            console.emit(f"  inputs         {inputs}")
        console.emit(f"  commit         {head[:12]}, working tree {'clean' if not dirty else f'NOT clean ({len(dirty)} paths)'}")
        console.emit(f"  local folder   {local}")
        console.emit(f"  configuration  {len(values)} names, {len(empty)} empty" + (f" ({', '.join(empty)})" if empty else ""))
        console.emit(f"  run number     {run_number}" + (" (taken by this run)" if writes else " (a read-only action does not use up a number)"))
        console.emit("The steps:")
        for line in format_plan(workflow, plan):
            console.emit(line)
        for note in plan.notes:
            console.emit(f"Note: {note}")

    # ---- the run -------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    def run(self, workflow: Workflow, plan: Plan, ctx: Context, values: dict, local: Path, state: dict, writes: bool, head: str, dirty: list, run_number: int, run_id: int, rt: Path) -> int:
        deps, action = self.deps, self.args.action
        self.workflow, self.values, self.head, self.dirty = workflow, values, head, dirty
        self.ctx = ctx
        self.bash = deps.bash()
        self.az = deps.az()
        started = deps.clock()
        stamp = started.strftime("%Y%m%dT%H%M%SZ")
        records = local / RECORDS_NAME
        records.mkdir(parents=True, exist_ok=True)
        log_path = records / f"hub-local-{action}-{stamp}.log"
        record_path = records / f"hub-local-{action}-{stamp}.md"
        self.lock = Lock(local / LOCK_NAME, {"pid": os.getpid(), "action": action, "started": iso(started), "processStart": guard.process_started(os.getpid())}, deps.pid_alive)
        stale = self.lock.acquire()
        clock_start = time.monotonic()
        passed = False
        interrupted = False
        refused = False
        try:
            self.console = Console(self.out, log_path)
            for name in SECRET_NAMES + ("ENV_SUBSCRIPTION_ID",):
                self.console.add_mask(values.get(name, ""))
            self.header(workflow, run_number, run_id, head, dirty, writes)
            run_ctx = Context(inputs=ctx.inputs, variables=values, secrets=values, github=ctx.github, runner_temp=posix(rt), step_ids=ctx.step_ids, planning=False)
            self.ctx = run_ctx
            if stale:
                drop_stale_proof(rt.parent, stale)
                self.recover_stale(stale)
            self.start_session()
            if writes:
                state = dict(state, lastRun=run_number)
                save_state(local, state)
            rt.mkdir(parents=True, exist_ok=True)
            self.rt = rt
            (rt / "steps").mkdir()
            (rt / "files").mkdir()
            self.make_proof(rt)
            self.make_shims()
            self.job_env = job_environment(workflow, run_ctx, None)
            passed = self.run_steps()
        except KeyboardInterrupt:
            interrupted = True
            self.say("ERROR: interrupted (Ctrl+C)")
        except HubLocalError as error:
            self.say(f"ERROR: {error}")
            refused = not self.steps_started
        except Exception as error:
            import traceback
            self.say(f"ERROR: the runner itself failed: {error!r}")
            self.say(traceback.format_exc())
        finally:
            seconds = time.monotonic() - clock_start
            self.finish(action, passed, interrupted, started, deps.clock(), seconds, run_number, run_id, rt, record_path, log_path, writes)
        return 0 if passed else (2 if refused else 1)

    def header(self, workflow: Workflow, run_number: int, run_id: int, head: str, dirty: list, writes: bool) -> None:
        self.say(f"Hub (local) {self.args.action}: the Hub workflow's own steps, run on this machine with the owner's own az session.")
        self.say(f"  commit {head[:12]}, working tree {'clean' if not dirty else f'NOT clean ({len(dirty)} paths; --allow-dirty was given)'}; run number {run_number}, run id {run_id}")
        self.say(f"  the log is {self.console.log.name if self.console and self.console.log else ''}".rstrip())

    def recover_stale(self, stale: dict) -> None:
        previous = stale.get("previousDefault")
        self.say(f"WARNING: an earlier run (process {stale.get('pid')}, action {stale.get('action')}, started {stale.get('started')}) did not finish.")
        if previous:
            code, _, err = self.az.run(["account", "set", "--subscription", str(previous)])
            if code == 0:
                self.say("NOTE: it had changed the CLI's default subscription; that default is put back before this run starts.")
            else:
                raise HubLocalError(f"an earlier run left the CLI's default subscription changed, and it could not be put back ({err.strip()[:200]}). Run `az account set --subscription {previous}`")

    def start_session(self) -> None:
        target = self.values["ENV_SUBSCRIPTION_ID"]
        code, out, err = self.az.run(["account", "show", "--query", "{id:id, tenant:tenantId, user:user.name, type:user.type}", "--output", "json"])
        if code != 0:
            raise HubLocalError(f"there is no az session on this machine ({(err.strip().splitlines() or [''])[0][:200]}). Sign in yourself with `az login`: this tool never signs in")
        try:
            info = json.loads(out)
        except ValueError:
            raise HubLocalError("az account show did not answer with json") from None
        if info.get("type") != "user":
            raise HubLocalError(f"the az session is a {info.get('type')}, not a person: a deploy runs with the owner's own session only")
        self.previous_default = {"id": info.get("id", "")}
        self.session_user = info.get("user", "")
        self.lock.update(previousDefault=self.previous_default["id"])
        self.default_changed = True
        code, _, err = self.az.run(["account", "set", "--subscription", target])
        if code != 0:
            raise HubLocalError(f"az account set --subscription failed for the pilot's subscription: {err.strip()[:300]}")
        self.verify_session(first=True)

    def verify_session(self, first: bool = False) -> dict:
        target = self.values["ENV_SUBSCRIPTION_ID"]
        code, out, err = self.az.run(["account", "show", "--query", "{id:id, tenant:tenantId, user:user.name, type:user.type}", "--output", "json"])
        if code != 0:
            raise HubLocalError(f"az account show failed: {err.strip()[:300]}")
        info = json.loads(out)
        if info.get("id", "").lower() != target.lower():
            raise HubLocalError("the CLI's default subscription is not the pilot's subscription any more (something changed it during the run)")
        tenant = self.values.get("AZURE_TENANT_ID", "")
        if tenant and info.get("tenant", "").lower() != tenant.lower():
            raise HubLocalError("the az session is in another tenant than AZURE_TENANT_ID of the configuration")
        if info.get("type") != "user":
            raise HubLocalError("the az session is not a person's any more")
        if first:
            self.say(f"  az session of {info.get('user')}; the pilot's subscription is the CLI's default for this run (it is put back at the end)")
        return info

    def make_proof(self, rt: Path) -> None:
        """Before the first step: the proof that a run of the Hub holds (tools/hubguard.py). A random token in a file of the run's own folder, and in the lock the number of the run and the SHA-256 of the token
        (the start time of this process is there since the lock was taken).
        The token is masked in everything that is printed or logged, and it is in no other file."""
        token = secrets.token_hex(32)
        self.proof = rt / guard.PROOF_NAME
        self.proof.write_text(token, encoding="utf-8", newline="")
        self.console.add_mask(token)
        self.lock.update(run=rt.name, proof=guard.digest_of(token))

    def drop_proof(self) -> None:
        """First at the end of a run, whatever the end was: the file goes, and the lock no longer holds the digest, so a process that outlives the run has nothing to show after it."""
        proof, self.proof = self.proof, None
        if proof is None:
            return
        try:
            proof.unlink()
        except FileNotFoundError:
            pass
        except OSError as error:
            self.say(f"WARNING: the proof file {proof} could not be deleted ({error}): delete it by hand")
        try:
            if self.lock:
                self.lock.update(proof=None)
        except OSError:
            pass

    def make_shims(self) -> None:
        shim = self.rt / "shim"
        shim.mkdir()
        for name, text in (("python3", python_shim(sys.executable)), ("az", az_shim(self.az.argv))):
            path = shim / name
            path.write_text(text, encoding="utf-8", newline="\n")
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        # The Azure CLI asks aka.ms for the latest Bicep release before every Bicep command, and that request has no time limit: on 2026-11-09 one hung for 14 minutes and held a deployment, so the check is off.
        env = {"GITHUB_ACTIONS": "true", "METERNAUT_HUB_LOCAL": "1", guard.PROOF_VARIABLE: posix(self.proof), "GITHUB_ACTOR": LOCAL_ACTOR, "GITHUB_REF": LOCAL_REF, "GITHUB_REF_NAME": "main",
               "GITHUB_SHA": self.head,
               "GITHUB_RUN_ID": str(self.ctx.github["run_id"]), "GITHUB_RUN_NUMBER": str(self.ctx.github["run_number"]), "GITHUB_RUN_ATTEMPT": "1",
               "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_WORKFLOW": self.workflow.name, "GITHUB_WORKSPACE": posix(self.root), "RUNNER_TEMP": posix(self.rt),
               "MSYS_NO_PATHCONV": "1", "MSYS2_ARG_CONV_EXCL": "*", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1", "AZ": "az", "AZURE_BICEP_CHECK_VERSION": "false",
               "PATH": posix(shim) + os.pathsep + self.environ.get("PATH", "")}
        if os.name == "nt":
            (shim / "sitecustomize.py").write_text(sitecustomize_text(), encoding="utf-8", newline="\n")
            env["HUB_LOCAL_AZ"] = json.dumps(self.az.argv)
            env["PYTHONPATH"] = posix(shim) + (os.pathsep + self.environ["PYTHONPATH"] if self.environ.get("PYTHONPATH") else "")
        self.base_env = env

    def step_environment(self, step_env: dict, files: dict) -> dict:
        env = {key: value for key, value in self.environ.items() if key.upper() not in STEP_ENV_DROPPED}
        env.update(self.base_env)
        env.update(self.job_env)
        env.update(self.github_env)
        env.update(step_env)
        env.update({"GITHUB_OUTPUT": posix(files["output"]), "GITHUB_ENV": posix(files["env"]), "GITHUB_STEP_SUMMARY": posix(files["summary"])})
        return env

    # ---- the steps -----------------------------------------------------------------------------------------------------------------------------------------------------------------------
    def run_steps(self) -> bool:
        ctx, total = self.ctx, len(self.workflow.steps)
        ctx.env = dict(self.job_env)
        self.steps_started = True
        for step in self.workflow.steps:
            ctx.current_index = step.index
            number = step.index + 1
            try:
                wanted = condition_result(step.condition, ctx)
            except ExprError as error:
                self.say(f"ERROR: step {number} ({step.name}): its condition could not be read: {error}")
                self.records.append(StepRecord(number, step.name, "failure", "its condition could not be read", 0.0))
                ctx.job_status = "failure"
                continue
            if wanted is not True:
                self.records.append(StepRecord(number, step.name, "skipped", "its condition is false", 0.0))
                if step.id:
                    ctx.steps[step.id] = StepState("skipped", {})
                continue
            self.say(f"[{number}/{total}] {step.name}")
            began = time.monotonic()
            outputs: dict = {}
            try:
                outcome, how, outputs = self.execute_step(step)
            except KeyboardInterrupt:
                if ctx.cancelled:
                    raise
                ctx.cancelled = True
                ctx.job_status = "cancelled"
                outcome, how = "cancelled", "interrupted (Ctrl+C); the steps that always run still follow"
                self.say("ERROR: interrupted (Ctrl+C): the steps that always run (the clean-up of container groups) still follow; Ctrl+C again ends the run at once")
            except HubLocalError as error:
                outcome, how = "failure", str(error)
                self.say(f"ERROR: {error}")
            except Exception as error:
                import traceback
                outcome, how = "failure", f"the runner failed: {error!r}"
                self.say(f"ERROR: the runner failed in this step: {error!r}")
                self.say(traceback.format_exc())
            seconds = time.monotonic() - began
            self.records.append(StepRecord(number, step.name, outcome, how, seconds))
            if step.id:
                ctx.steps[step.id] = StepState(outcome, outputs)
            if outcome == "failure" and ctx.job_status == "success":
                ctx.job_status = "failure"
            self.say(f"    {outcome} after {seconds:.0f} s" + (f" ({how})" if outcome != "success" and how != "ran" else ""))
        return ctx.job_status == "success"

    def step_limit_seconds(self, step: Step) -> float:
        minutes = step.timeout_minutes if step.timeout_minutes else 360.0
        return minutes * 60

    def execute_step(self, step: Step) -> tuple:
        """Returns (outcome, how, the step's outputs)."""
        replacement, reason = classify(step)
        if reason:
            raise HubLocalError(reason)
        if replacement and replacement.kind == "ci-checks":
            note = (f"the checks of CI are not asked of GitHub: the person who starts the run ran them on this machine, for commit {self.head[:12]}, "
                    f"with the working tree {'clean' if not self.dirty else 'NOT clean'}")
            self.say(f"    replaced: {note}")
            self.used.append(note)
            return "success", f"replaced: {replacement.note}", {}
        step_env = {key: interpolate(text, self.ctx) for key, text in step.env.items()}
        files = {name: self.rt / "files" / f"step-{step.index + 1:02d}.{name}" for name in ("output", "env", "summary")}
        for path in files.values():
            path.write_text("", encoding="utf-8")
        kind = replacement.kind if replacement else ""
        if kind in ("checkout", "cases-publish-cleanup"):
            self.say(f"    replaced: {replacement.note}")
            self.used.append(replacement.note)
            return ("success" if kind == "checkout" else "skipped"), f"replaced: {replacement.note}", {}
        if kind == "python":
            return self.check_python(step, replacement)
        if kind == "az-session":
            self.verify_session()
            self.say(f"    replaced: {replacement.note} ({self.session_user})")
            self.used.append(replacement.note)
            return "success", f"replaced: {replacement.note}", {}
        if kind == "cases-publish":
            self.used.append(replacement.note)
            ok = self.publish_cases(step_env, files)
            return ("success" if ok else "failure"), f"replaced: {replacement.note}", self.read_files(step, files)
        if kind == "no-token":
            self.say(f"    NOTE: {replacement.note}")
            self.used.append(replacement.note)
        if kind == "cases-pack":
            self.say(f"    NOTE: {replacement.note}")
            self.used.append("the archive of the app's sources is made here and is not sent to the Operator")
        script = self.script_text(step)
        path = self.rt / "steps" / f"step-{step.index + 1:02d}.sh"
        path.write_bytes(script.encode("utf-8"))
        env = self.step_environment(step_env, files)
        if replacement and replacement.posix_paths:
            env["RUNNER_TEMP"] = posix_absolute(self.rt)
            for name in ("MSYS_NO_PATHCONV", "MSYS2_ARG_CONV_EXCL"):
                env.pop(name, None)
        code, timed_out = run_process([self.bash, "--noprofile", "--norc", "-eo", "pipefail", posix(path)], env, self.root, self.console, self.step_limit_seconds(step))
        outputs = self.read_files(step, files)
        if timed_out:
            self.say(f"ERROR: the step was stopped after {self.step_limit_seconds(step) / 60:g} minutes (timeout-minutes), with everything that it had started")
            return "failure", "timed out", outputs
        if code != 0:
            return "failure", f"exit code {code}", outputs
        return "success", "ran", outputs

    def script_text(self, step: Step) -> str:
        script = (step.run or "").replace("\r\n", "\n")
        if not script.endswith("\n"):
            script += "\n"
        count = len(UNIT_TEST_LINE.findall(script))
        if count:
            note = f"the unit tests are not repeated: they were run on this machine (commit {self.head[:12]}, working tree {'clean' if not self.dirty else 'NOT clean'})"
            first = {"done": False}

            def replace(_):
                if first["done"]:
                    return ":"
                first["done"] = True
                return f"echo {shlex.quote(note)}"
            script = UNIT_TEST_LINE.sub(replace, script)
            self.used.append("the unit tests of the first step are not repeated")
        return script

    def read_files(self, step: Step, files: dict) -> dict:
        """The outputs of a step; its environment file and its summary are taken over. A file that cannot be read fails the step."""
        outputs: dict = {}
        try:
            outputs = parse_command_file(files["output"].read_text(encoding="utf-8", errors="replace"))
            self.github_env.update(parse_command_file(files["env"].read_text(encoding="utf-8", errors="replace")))
            self.ctx.env.update(self.github_env)
        except HubLocalError as error:
            self.say(f"ERROR: {error}")
            raise
        text = files["summary"].read_text(encoding="utf-8", errors="replace").strip()
        if text:
            self.summary.append(self.console.mask(text))
        return outputs

    def check_python(self, step: Step, replacement: Replacement) -> tuple:
        wanted = interpolate(step.with_.get("python-version", ""), self.ctx).strip()
        have = f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}"
        parts = wanted.split(".") if wanted else []
        if wanted and have.split(".")[:len(parts)] != parts:
            self.say(f"ERROR: the step asks for Python {wanted} (the function app's runtime), and this tool runs on Python {have}. Start it with a Python {wanted}")
            return "failure", f"Python {have}, not {wanted}", {}
        self.say(f"    replaced: {replacement.note} (Python {have})")
        self.used.append(replacement.note)
        return "success", f"replaced: {replacement.note}", {}

    def publish_cases(self, step_env: dict, files: dict) -> bool:
        """The package is built here and published through the app's public deployment site, with the owner's own session."""
        app = step_env.get("FUNCTION_APP", "")
        group, subscription = self.values["ENV_RESOURCE_GROUP"], self.values["ENV_SUBSCRIPTION_ID"]
        if not APP_NAME.fullmatch(app):
            self.say(f"ERROR: the name of the cases app is not a name: {app!r}. Nothing was published")
            return False
        site = f"https://management.azure.com/subscriptions/{subscription}/resourceGroups/{group}/providers/Microsoft.Web/sites/{app}?api-version=2024-04-01"
        code, out, err = self.az.run(["rest", "--method", "get", "--url", site, "--query", "properties.publicNetworkAccess", "--output", "tsv"])
        if code != 0:
            self.say(f"ERROR: the cases app could not be read: {err.strip()[:300]}. Nothing was published")
            return False
        access = out.strip()
        if access.lower() == "disabled":
            self.say("ERROR: the cases app takes no public traffic (its public network access is Disabled), so its deployment site cannot be reached from this machine. The route through the "
                     "Operator needs a GitHub OpenID Connect token, which does not exist here. Nothing was published")
            return False
        build, package = self.rt / "cases-build", self.rt / "cases.zip"
        script = self.rt / "steps" / "cases-build.sh"
        script.write_text(f"set -euo pipefail\nbash tools/build-function-app.sh case-functions cases {shlex.quote(posix_absolute(build))} {shlex.quote(posix_absolute(package))}\n",
                          encoding="utf-8", newline="\n")
        env = self.step_environment({}, files)
        for name in ("MSYS_NO_PATHCONV", "MSYS2_ARG_CONV_EXCL"):
            env.pop(name, None)
        self.say("    building the package here (pip reaches the managed package feed only; if it fails, nothing is published and no other index is tried)")
        code, timed_out = run_process([self.bash, "--noprofile", "--norc", "-eo", "pipefail", posix(script)], env, self.root, self.console, 20 * 60)
        if code != 0 or not package.is_file():
            self.say("ERROR: the package could not be built (see above). Nothing was published")
            return False
        expected = self.release_digest()
        if expected:
            if not self.package_has_digest(package, expected):
                return False
        else:
            self.say("    NOTE: no step of this workflow gave the digest of the app's own files (the output package_sha256), so the package is not held against one")
        package_sha256 = hashlib.sha256(package.read_bytes()).hexdigest()
        command = [*self.az.argv, "functionapp", "deployment", "source", "config-zip", "--subscription", subscription, "--resource-group", group, "--name", app, "--src", posix(package),
                   "--build-remote", "false", "--only-show-errors", "--output", "none"]
        for attempt in (1, 2, 3):
            code, timed_out = run_process(command, self.az.environment(), self.root, self.console, 10 * 60)
            if code == 0:
                self.say(f"    the package is published to {app} (attempt {attempt} of 3), from this machine, through the app's public deployment site")
                self.summary.append(f"The cases package was built on this machine and published to `{app}` through the app's public deployment site (attempt {attempt} of 3), with the owner's own session. "
                                    "Nothing went to the Operator in this run (its route needs a GitHub OpenID Connect token): a line below that says that the Operator received or published the code "
                                    "describes a run on GitHub, not this one.")
                self.summary.append(f"the cases package that is published has the SHA-256 {package_sha256}")
                if expected:
                    self.summary.append(f"Its own files (function_app.py and cases/) have the digest `{expected}`, which the deploy wrote as the app's setting PACKAGE_SHA256: they were held against it before "
                                        "the package was published, so the app's check of its release finds the same.")
                return True
            self.say(f"ERROR: the publish did not go through (attempt {attempt} of 3)" + (" (it timed out)" if timed_out else ""))
            if attempt < 3:
                self.deps.sleep(60)
        self.say(f"ERROR: the code could not be published to {app}")
        return False

    def release_digest(self) -> str:
        """The digest of the app's own files that an earlier step gave (the output package_sha256): what the deploy wrote as the app's setting PACKAGE_SHA256, and what the app's own check
        of its release holds its running files against."""
        for state in self.ctx.steps.values():
            outputs = state.outputs if isinstance(state.outputs, dict) else {}
            if re.fullmatch(r"[0-9a-f]{64}", outputs.get("package_sha256", "")):
                return outputs["package_sha256"]
        return ""

    def package_has_digest(self, package: Path, expected: str) -> bool:
        """The files in the zip file give the expected digest, by tools/package-digest.py, which loads the app's own cases/release.py: the check that the app will make of the files that it runs.
        Only the files that the digest covers are unpacked (function_app.py and cases/: the libraries are many, and it does not cover them). A Windows checkout has CRLF line ends, and the
        digest reads them as LF, so this holds for it too. When it does not, nothing is published."""
        folder = self.rt / "cases-verify"
        tool = self.root / "tools" / "package-digest.py"
        try:
            with zipfile.ZipFile(package) as archive:
                for member in archive.infolist():
                    if member.filename == "function_app.py" or member.filename.startswith("cases/"):
                        archive.extract(member, folder)
            done = subprocess.run([sys.executable, str(tool), str(folder), "--check", expected], capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  stdin=subprocess.DEVNULL, timeout=300)
        except (OSError, zipfile.BadZipFile, subprocess.TimeoutExpired) as error:
            self.say(f"ERROR: the files of the package could not be held against the digest of the app's own files: {error!r}. Nothing was published")
            return False
        if done.returncode != 0:
            said = (done.stdout.strip() or done.stderr.strip()).splitlines()
            self.say(f"ERROR: the files in the package are not the files whose digest the deploy wrote as PACKAGE_SHA256 ({said[0] if said else 'no answer'}): the app's check of its release would fail. "
                     "Did a file of src/case-functions change after the step that works out the release? Nothing was published")
            return False
        self.say("    the files of the package (function_app.py and cases/) have the digest that the deploy wrote as PACKAGE_SHA256: the app's check of its release will find the same")
        return True

    # ---- the end of a run ----------------------------------------------------------------------------------------------------------------------------------------------------------------
    def finish(self, action: str, passed: bool, interrupted: bool, started: dt.datetime, ended: dt.datetime, seconds: float, run_number: int, run_id: int, rt: Path,
               record_path: Path, log_path: Path, writes: bool) -> None:
        """Always: the proof goes first, then the CLI's default is put back, then clean up, release the lock, write the record, say how it went."""
        try:
            self.drop_proof()
        finally:
            try:
                self.restore_default()
            finally:
                try:
                    if rt.exists() and not remove_tree(rt):
                        self.say(f"WARNING: {rt} could not be deleted completely: delete it by hand")
                finally:
                    if self.lock:
                        self.lock.release()
        verdict = f"Hub (local) {action}: {'PASSED' if passed else 'FAILED'} in {minutes_text(seconds)} minutes"
        try:
            record_path.write_text(self.record_text(action, verdict, passed, interrupted, started, ended, run_number, run_id, log_path, writes), encoding="utf-8", newline="\n")
        except OSError as error:
            self.say(f"WARNING: the record could not be written: {error}")
        for line in self.report(record_path):
            self.say(line)
        self.say(verdict)
        if self.console:
            self.console.close()

    def restore_default(self) -> None:
        if not self.default_changed or not self.previous_default:
            return
        previous = self.previous_default
        code, _, err = self.az.run(["account", "set", "--subscription", previous["id"]])
        if code == 0:
            self.restore_note = "the CLI's default subscription was put back to the one that it was before the run"
        else:
            self.restore_note = f"THE CLI'S DEFAULT SUBSCRIPTION WAS NOT PUT BACK ({err.strip()[:200]}). Run: az account set --subscription {previous['id']}"
        self.default_changed = False
        if self.lock:
            self.lock.update(previousDefault=None)

    def report(self, record_path: Path) -> list:
        lines = ["", "Steps that ran:"]
        for record in self.records:
            if record.outcome == "skipped" and record.how == "its condition is false":
                continue
            lines.append(f"  {record.number:>3}  {record.outcome:<9} {record.seconds:6.0f} s  {record.name[:90]}" + ("" if record.how == "ran" else f"  [{record.how[:100]}]"))
        if self.summary:
            lines += ["", "What the steps wrote to their summary:", *self.summary]
        lines += ["", f"Restored: {self.restore_note}.", f"The record: {record_path}", ""]
        return lines

    def record_text(self, action: str, verdict: str, passed: bool, interrupted: bool, started: dt.datetime, ended: dt.datetime, run_number: int, run_id: int, log_path: Path,
                    writes: bool) -> str:
        def cell(text: str) -> str:
            return text.replace("|", "/").replace("\n", " ")
        every_input = ", ".join(f"{name} {to_text(value)}" for name, value in self.ctx.inputs.items() if name != "action")
        lines = [f"# Hub (local): {action}", "", f"**{verdict}**", "",
                 f"- action: {action} ({'changes Azure' if writes else 'reads only'}); inputs: {every_input}",
                 f"- head commit: {self.head}; working tree: {'clean' if not self.dirty else 'NOT clean (' + str(len(self.dirty)) + ' paths)'}",
                 f"- started {iso(started)}, ended {iso(ended)}" + ("; interrupted by Ctrl+C" if interrupted else ""),
                 f"- run number {run_number}{'' if writes else ' (not used up: a read-only action)'}, run id {run_id}",
                 f"- az session: {self.session_user or 'none'}",
                 f"- restored: {self.restore_note}",
                 f"- the log: {log_path.name}", "", "## Steps", "", "| # | outcome | seconds | step | how |", "|---|---|---|---|---|"]
        for record in self.records:
            lines.append(f"| {record.number} | {record.outcome} | {record.seconds:.0f} | {cell(record.name)} | {cell(record.how)} |")
        lines += ["", "## What differs from a run on GitHub", ""]
        for note in dict.fromkeys(self.used):
            lines.append(f"- {note}")
        if not self.used:
            lines.append("- nothing was replaced in the steps that ran")
        lines += ["", "## What the steps wrote to their summary", ""]
        lines += self.summary if self.summary else ["(nothing)"]
        return "\n".join(lines) + "\n"


TEMPLATE_HEAD = """# The values that GitHub held as variables and secrets for the Hub workflow (.github/workflows/deploy-hub.yml), for a run on this machine (tools/hub-local.py).
# This file stays on this machine: git ignores it (AGENTS.md rule 17). One NAME=VALUE per line; a line that starts with # is a comment. Never commit it.
# ENV_SUBSCRIPTION_ID and AZURE_SUBSCRIPTION_ID are the same subscription. AZURE_CLIENT_ID is the deploy identity's client id: a run here does not use it, and it may stay empty.
# GitHub shows the value of a variable but never of a secret, so the secrets are filled in by hand even with --from-github.
# DRIFT_ACCEPTED_EXEMPTIONS and DRIFT_ACCEPTED_DENY are optional: what the owner has accepted of the policy state (tools/drift-check.py). Empty, or no line, accepts nothing.
"""


def template_text(known: dict) -> str:
    lines = [TEMPLATE_HEAD.rstrip("\n")]
    for name in TEMPLATE_NAMES:
        lines.append(f"{name}={known.get(name, '')}")
    return "\n".join(lines) + "\n"


def do_init(args, environ, deps: Deps, out) -> int:
    """Makes the configuration file (names, and values only with --from-github) and the run counter when they are not there. Nothing that exists is changed."""
    def say(text: str) -> None:
        print(text, file=out, flush=True)

    local = resolve_local_dir(environ, Path(deps.root), deps.git)
    local.mkdir(parents=True, exist_ok=True)
    config, state = local / CONFIG_NAME, local / STATE_NAME
    known: dict = {}
    last_run = FIRST_RUN_NUMBER - 1
    if args.from_github and not (config.exists() and state.exists()):
        code, text, error = deps.gh(["variable", "list", "--json", "name,value"], deps.root)
        if code != 0:
            raise HubLocalError(f"gh variable list failed: {error.strip()[:300]}")
        try:
            known = {item["name"]: item["value"] for item in json.loads(text) if item.get("name") in TEMPLATE_NAMES}
        except (ValueError, KeyError, TypeError):
            raise HubLocalError("gh variable list did not answer with the list that was expected") from None
        code, text, error = deps.gh(["run", "list", "--workflow", DEFAULT_WORKFLOW.name, "--limit", "1", "--json", "number"], deps.root)
        if code != 0:
            raise HubLocalError(f"gh run list failed: {error.strip()[:300]}")
        try:
            runs = json.loads(text)
            if runs:
                last_run = int(runs[0]["number"])
        except (ValueError, KeyError, TypeError):
            raise HubLocalError("gh run list did not answer with the list that was expected") from None
    if config.exists():
        say(f"kept: {config} exists and is not changed")
    else:
        require_ignored([config, local / RECORDS_NAME / "hub-local-record.md"], deps.git)
        config.write_text(template_text(known), encoding="utf-8", newline="\n")
        empty = [name for name in TEMPLATE_NAMES if name not in OPTIONAL_NAMES and not known.get(name)]
        filled = len([name for name in TEMPLATE_NAMES if known.get(name)])
        say(f"made: {config} with {len(TEMPLATE_NAMES)} names" + (f", {filled} of them filled in from GitHub" if known else ", all empty"))
        say(f"fill in: {', '.join(empty)}")
    if state.exists():
        say(f"kept: {state} exists and is not changed")
    else:
        state.write_text(json.dumps({"lastRun": last_run}, indent=2) + "\n", encoding="utf-8", newline="\n")
        say(f"made: {state}: the next run number is {last_run + 1}" + (" (the newest run of the Hub on GitHub was number " + str(last_run) + ")" if args.from_github else
                                                                      " (above any number that the Hub reached on GitHub; --from-github reads the newest from there)"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hub-local.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", nargs="?", help="the action of the Hub workflow (its input 'action')")
    parser.add_argument("--minutes", help="only with page-latency: how many minutes (the workflow's input minutes; its default when not given)")
    parser.add_argument("--public-ai-gateway-requested", action="store_true", help="only with aigateway: the owner has asked in writing for a public AI Gateway")
    parser.add_argument("--public-teams-bot-requested", action="store_true", help="only with teams: the owner has asked in writing for a public Teams bot")
    parser.add_argument("--plant-public-ip", action="store_true", help="only with plant: also plant an unassigned public IP address")
    parser.add_argument("--plant-vm", action="store_true", help="only with plant: also plant a virtual machine that nothing uses, with its network interface and its OS disk (about 0.04 US dollars an hour while it runs)")
    parser.add_argument("--evals-command", help="only with foundry-evals: the workflow's input evals_command (probe, run, rule or rule-apply; the workflow's default when not given). "
                        "probe and rule only read; run and rule-apply need --yes")
    parser.add_argument("--evals-judge", help="only with foundry-evals and --evals-command run: the workflow's input evals_judge (none, connection or auto; the workflow's default when not given)")
    parser.add_argument("--redteam-mode", help="only with foundry-redteam: the workflow's input redteam_mode (auto, cloud or dataset; the workflow's default when not given)")
    parser.add_argument("--yes", action="store_true", help="run an action that changes Azure (without it the plan is printed and nothing runs)")
    parser.add_argument("--allow-dirty", action="store_true", help="run an action that changes Azure from a working tree that has uncommitted changes")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and run nothing: no az session is needed")
    parser.add_argument("--workflow", help="the workflow file (default: .github/workflows/deploy-hub.yml of this checkout)")
    parser.add_argument("--init", action="store_true", help=f"make {CONFIG_NAME} (names with empty values) and {STATE_NAME} in the local folder when they are not there")
    parser.add_argument("--from-github", action="store_true", help="with --init: read the variables and the newest run number from GitHub (one gh variable list and one gh run list)")
    return parser


def main(argv=None, *, environ=None, out=None, deps: Optional[Deps] = None) -> int:
    out = out if out is not None else sys.stdout
    environ = os.environ if environ is None else environ
    deps = deps or Deps()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.from_github and not args.init:
        parser.error("--from-github is only for --init")
    if not args.init and not args.action:
        parser.error("an action is needed (or --init)")
    if args.init and args.action:
        parser.error("--init takes no action")
    try:
        if args.init:
            return do_init(args, environ, deps, out)
        return Hub(args, environ, deps, out).go()
    except HubLocalError as error:
        print(f"hub-local: refused: {error}", file=out, flush=True)
        return 2


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
