#!/usr/bin/env python3
"""Runs one script inside the virtual network, in a short-lived container group, and always deletes the group (standard library only).

    python tools/operator-run.py run --resource-group G --name N --subnet-id ID --identity-id ID --image IMAGE --script FILE
        [--secret-file NAME=PATH ...] [--env NAME=VALUE ...] [--secure-env NAME[=VALUE] ...] [--dns-server IP ...]
        [--cpu 1] [--memory 1.5] [--timeout-seconds 600] [--allow-tag] [--summary FILE] [--subscription S] [--poll-seconds 5]
    python tools/operator-run.py cleanup --resource-group G --prefix P [--older-than-minutes 30] [--subscription S]

This is the Operator of docs/proposals/07-private-by-default.md. Once the services of the project are private, the deployment workflow can no longer reach the
sites that publish code, the queue that starts a run, the telemetry or the function app from outside. What it still reaches is Azure Resource Manager. So it makes a
container group (Azure Container Instances) in the Operator's delegated subnet, with the Operator's user-assigned identity, lets one script run in it, reads the
log through Azure Resource Manager and deletes the group. The container group is made, and only a run of the Hub may make it (AGENTS.md rule 18; tools/hubguard.py says what
counts as one): the command refuses to run anywhere else. It also names the project's own subscription and resource group and no other (the settings ENV_SUBSCRIPTION_ID and ENV_RESOURCE_GROUP that the
workflow gives every step): --subscription is the project's when it is not given, and --subnet-id and --identity-id are resources of the project's group.

run      Creates the group (`az container create --file`, restart policy Never, Linux, the identity, the subnet, the DNS servers that are given), mounts the script
         and every --secret-file as one secret volume at /mnt/op, and starts `/bin/bash /mnt/op/<script>`. It polls the group every --poll-seconds seconds with
         `az container show` until the container has terminated or --timeout-seconds are over, and prints each line of the container's log once, as it comes
         (`az container logs`, while the container runs, and once more at the end). It prints the events of the group when the container never started (an image
         that cannot be pulled is the likely cause). Always, also after an error and after an interrupt, it reads the log a last time and then deletes the group.
         It exits with the container's exit code; 124 when the time was over (the group is deleted), 130 after an interrupt, 2 for a refused argument and 1 for
         everything else, a group that could not be made, read or deleted included.
cleanup  Deletes the container groups of the resource group whose name starts with the prefix, that carry the tag this tool puts on every group it makes, and are
         older than the given number of minutes (0: all of them). A group without that tag is not made by this tool and is left alone.

Facts that shaped it (Microsoft Learn; the Operator's record has the sources):
  - The log of a running container is kept up to 4 MB, the log of a stopped one only up to 16 KB or 1,000 lines. So the script must print little, the tool reads the
    log while the container runs, and says so when the last read is as long as that limit.
  - A container group in a virtual network has no public address, and it does not take the DNS servers of the network: --dns-server gives them (the landing zone's).
  - A secret volume is held in memory (tmpfs) and is read-only. The values travel in the body of the request, which the tool writes to a file that only its user can
    read and removes at the end. Nothing secret is ever on a command line of az, and the values of --secure-env are never printed: they are taken out of every line
    that the tool prints, including what az and the container say.
  - A request takes only a few hundred kilobytes of files: the tool refuses more than MAX_FILE_BYTES (480,000, with the evidence next to it: a request with 466,104 bytes of
    files was taken, and one with 632,656 was refused with an internal server error). What is bigger is fetched or built inside the container, from the sources and the
    scripts that do ride in the request.

The image is a reference that cannot change, registry/name@sha256:<64 hex characters>. A tag can move; --allow-tag accepts registry/name:tag for the probe only.
"""
from __future__ import annotations

import argparse
import base64
import datetime
import importlib.util
import ipaddress
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

guard = sys.modules.get("hubguard")
if guard is None:  # a test has loaded it already; a tool run on its own loads it from its own folder
    _spec = importlib.util.spec_from_file_location("hubguard", Path(__file__).with_name("hubguard.py"))
    guard = importlib.util.module_from_spec(_spec)
    sys.modules["hubguard"] = guard
    _spec.loader.exec_module(guard)

API_VERSION = "2023-05-01"
CONTAINER = "operator"
MOUNT = "/mnt/op"
STARTED_TAG = "meternaut-operator"
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
NAME = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
PREFIX = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*-?$")
GROUP = re.compile(r"^[A-Za-z0-9._()-]{1,90}$")
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
REGISTRY = r"[a-z0-9][a-z0-9.-]*(?::[0-9]{1,5})?/[a-z0-9][a-z0-9._/-]*"
IMAGE_BY_DIGEST = re.compile(rf"^{REGISTRY}@sha256:[0-9a-f]{{64}}$")
IMAGE_BY_TAG = re.compile(rf"^{REGISTRY}:[A-Za-z0-9_][A-Za-z0-9_.-]{{0,127}}$")
SUBNET_ID = re.compile(r"^/subscriptions/[0-9a-f-]{36}/resourceGroups/[A-Za-z0-9._()-]{1,90}/providers/Microsoft\.Network/virtualNetworks/[A-Za-z0-9._-]{1,64}/subnets/[A-Za-z0-9._-]{1,80}$", re.I)
IDENTITY_ID = re.compile(r"^/subscriptions/[0-9a-f-]{36}/resourceGroups/[A-Za-z0-9._()-]{1,90}/providers/Microsoft\.ManagedIdentity/userAssignedIdentities/[A-Za-z0-9_-]{1,128}$", re.I)
NOT_FOUND = re.compile(r"ResourceNotFound|ContainerGroupNotFound|NotFound|\b404\b", re.I)
MIN_SECRET_LENGTH = 8
# The most bytes of files (the script and every --secret-file, before base64) that one container group's request may carry. It is a measured limit and not a documented one: Learn names no limit for a
# secret volume or for the request, and an assumption of 3,000,000 bytes, which this constant held first, was wrong. What was seen, on 2026-11-06 (UTC, from the Hub runs):
#   FILES_TAKEN_BYTES    466,104 bytes of files were taken: the probe of the Operator (a file of 400,000 bytes, a lock file of 44,967 and the probe's own script of 21,137)
#   FILES_REFUSED_BYTES  632,656 bytes of files were refused, twice, with "(InternalServerError) Encountered an internal server error" when the group was made: the finished package of the cases app (614,068
#                        bytes zipped) and the script of the container (18,588)
# The real limit lies between the two and is not known. The cap is a round number just above the largest total that is known to work, so that the probe still runs, and no request is ever sent that
# is not at most about that size. Anything bigger is built in the container from the sources and the scripts that do ride in the request (operator/publish.sh).
FILES_TAKEN_BYTES = 466_104
FILES_REFUSED_BYTES = 632_656
MAX_FILE_BYTES = 480_000
MIN_NAME, MAX_NAME = 3, 63
MIN_PREFIX = 4
LOG_LINES_IN_SUMMARY = 300
STOPPED_LOG_BYTES, STOPPED_LOG_LINES = 16 * 1024, 1000
READ_FAILURES_ALLOWED = 6
NOT_VISIBLE_YET_SECONDS = 120
DELETE_TRIES, DELETE_PAUSE = 4, 10
TIMED_OUT, INTERRUPTED = 124, 130


class Problem(Exception):
    """Something the owner can fix or must know; printed without a trace. `code` is the exit code that follows."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


class TimedOut(Problem):
    """The container did not finish in time."""

    def __init__(self, seconds: int):
        super().__init__(f"the container did not finish within {seconds} seconds; its group is deleted below", TIMED_OUT)


class Progress:
    """What has been seen of the group so far, kept outside the polling loop so that the end of the run (a timeout, an error, an interrupt) still has it."""

    def __init__(self):
        self.state: State | None = None


class Az:
    """Runs the Azure CLI. A test replaces it with a stand-in of the same call: az(arguments) -> (exit code, standard output, standard error)."""

    def __init__(self, timeout: int = 600):
        self.timeout = timeout

    def __call__(self, arguments: list[str]) -> tuple[int, str, str]:
        try:
            done = subprocess.run([os.environ.get("AZ", "az"), *arguments], capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return 124, "", f"az did not answer within {self.timeout} seconds"
        return done.returncode, done.stdout, done.stderr


class Printer:
    """Everything the tool says goes through here, and the values of --secure-env never come out of it, in the form given or in the forms a message could hold them."""

    def __init__(self, secrets: list[str] | None = None, out=None, err=None):
        self.out = out if out is not None else sys.stdout
        self.err = err if err is not None else sys.stderr
        self.log_lines: list[str] = []
        self.forms: list[str] = []
        for secret in secrets or []:
            for form in (secret, base64.b64encode(secret.encode("utf-8")).decode("ascii"), json.dumps(secret)[1:-1]):
                if form and form not in self.forms:
                    self.forms.append(form)
        self.forms.sort(key=len, reverse=True)

    def redact(self, text: str) -> str:
        for form in self.forms:
            text = text.replace(form, "***")
        return text

    def say(self, text: str) -> None:
        print(self.redact(text), file=self.out, flush=True)

    def complain(self, text: str) -> None:
        print(self.redact(text), file=self.err, flush=True)

    def log(self, line: str) -> None:
        clean = self.redact(line)
        self.log_lines.append(clean)
        print(f"| {clean}", file=self.out, flush=True)


class LogStream:
    """Gives every line of a log once, however often the log is read. A log that is read again starts with the lines that were read before, unless it was cut at the start
    (a stopped container keeps only its last lines): the lines that follow the last overlap are the new ones."""

    def __init__(self):
        self.seen: list[str] = []

    def new_lines(self, text: str) -> list[str]:
        lines = [line.rstrip("\r") for line in text.split("\n")]
        while lines and lines[-1] == "":
            lines.pop()
        if lines[: len(self.seen)] == self.seen:
            fresh = lines[len(self.seen):]
        else:
            fresh = lines
            for overlap in range(min(len(self.seen), len(lines)), 0, -1):
                if self.seen[-overlap:] == lines[:overlap]:
                    fresh = lines[overlap:]
                    break
        self.seen = (self.seen + fresh)[-5000:]
        return fresh


class State:
    """What `az container show` says about the group and its one container, in the few words that decide what to do."""

    def __init__(self, document: dict):
        document = document or {}
        properties = document.get("properties") if isinstance(document.get("properties"), dict) else {}
        group_view = document.get("instanceView") or properties.get("instanceView") or {}
        containers = document.get("containers") or properties.get("containers") or []
        container = containers[0] if containers and isinstance(containers[0], dict) else {}
        container_properties = container.get("properties") if isinstance(container.get("properties"), dict) else {}
        view = container.get("instanceView") or container_properties.get("instanceView") or {}
        current = view.get("currentState") or {}
        self.provisioning = str(document.get("provisioningState") or properties.get("provisioningState") or "")
        self.group = str(group_view.get("state") or "")
        self.container = str(current.get("state") or "")
        self.detail = str(current.get("detailStatus") or "")
        exit_code = current.get("exitCode")
        self.exit_code = exit_code if isinstance(exit_code, int) and not isinstance(exit_code, bool) else None
        self.started = bool(current.get("startTime")) or self.container.lower() in ("running", "terminated")
        self.events = [event for event in (list(group_view.get("events") or []) + list(view.get("events") or [])) if isinstance(event, dict)]

    def describe(self) -> str:
        parts = [f"provisioning {self.provisioning or 'unknown'}", f"group {self.group or 'unknown'}", f"container {self.container or 'unknown'}"]
        if self.detail:
            parts[-1] += f" ({self.detail})"
        return ", ".join(parts)

    def is_(self, what: str) -> bool:
        return self.container.lower() == what


def describe_event(event: dict) -> str:
    count = event.get("count")
    times = f" (x{count})" if isinstance(count, int) and count > 1 else ""
    return f"[{event.get('type') or 'Event'}] {event.get('name') or ''}{times}: {str(event.get('message') or '')[:300]}".strip()


def first_line(text: str, limit: int = 300) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return (lines[0] if lines else "no message")[:limit]


def require_actions() -> None:
    not_the_hub = guard.refusal()
    if not_the_hub:
        raise Problem(f"this command makes and deletes resources in Azure, and only a run of the Hub may do that (AGENTS.md rule 18): {not_the_hub}", 2)


def only_in_the_project(args, *ids: tuple[str, str]) -> None:
    """The call names the project's own subscription and resource group and no other (tools/hubguard.py): the subscription is the project's when none is given, and the ids of the subnet and
    the identity are resources of the project's group."""
    if not args.subscription:
        args.subscription = os.environ.get("ENV_SUBSCRIPTION_ID") or ""
    other_scope = guard.other_scope(args.subscription, args.resource_group)
    if other_scope:
        raise Problem(other_scope, 2)
    for option, resource_id in ids:
        if not guard.in_the_project(resource_id):
            raise Problem(f"{option} is not a resource of the project's resource group", 2)


def split_pair(pair: str, what: str) -> tuple[str, str]:
    name, separator, value = pair.partition("=")
    if not separator:
        raise Problem(f"{what} is NAME=VALUE, not {name!r}", 2)
    return name, value


def check_name(name: str) -> None:
    if not MIN_NAME <= len(name) <= MAX_NAME or not NAME.match(name):
        raise Problem(f"the name of the container group is {MIN_NAME} to {MAX_NAME} lower-case letters, digits and single hyphens, starting with a letter: {name!r} is not", 2)


def check_image(image: str, allow_tag: bool) -> None:
    if IMAGE_BY_DIGEST.match(image):
        return
    if IMAGE_BY_TAG.match(image):
        if allow_tag:
            return
        raise Problem(f"the image {image!r} is a tag, and a tag can move. Pin it as registry/name@sha256:<64 hex characters>; --allow-tag accepts a tag for the probe", 2)
    raise Problem(f"the image is registry/name@sha256:<64 hex characters> (or registry/name:tag with --allow-tag), not {image!r}", 2)


def check_options(args) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[str]]:
    """The environment variables, the secure ones with their values read, and the DNS servers: each checked."""
    if not GROUP.match(args.resource_group):
        raise Problem("the resource group is letters, digits and . _ - ( )", 2)
    check_name(args.name)
    check_image(args.image, args.allow_tag)
    if not SUBNET_ID.match(args.subnet_id):
        raise Problem("--subnet-id is the resource id of a subnet", 2)
    if not IDENTITY_ID.match(args.identity_id):
        raise Problem("--identity-id is the resource id of a user-assigned identity", 2)
    if not 0.1 <= args.cpu <= 4 or round(args.cpu, 1) != args.cpu:
        raise Problem("--cpu is from 0.1 to 4, in steps of 0.1", 2)
    if not 0.1 <= args.memory <= 16 or round(args.memory, 1) != args.memory:
        raise Problem("--memory is from 0.1 to 16 (GB), in steps of 0.1", 2)
    if not 30 <= args.timeout_seconds <= 3600:
        raise Problem("--timeout-seconds is from 30 to 3600", 2)
    if not 0 <= args.poll_seconds <= 60:
        raise Problem("--poll-seconds is from 0 to 60", 2)
    plain = [split_pair(pair, "--env") for pair in args.env]
    secure = []
    for pair in args.secure_env:
        if "=" in pair:
            name, value = split_pair(pair, "--secure-env")
        else:
            name, value = pair, os.environ.get(pair, "")
            if not value:
                raise Problem(f"--secure-env {pair} names an environment variable of this process, and it is not set", 2)
        if len(value) < MIN_SECRET_LENGTH:
            raise Problem(f"the value of --secure-env {name} is shorter than {MIN_SECRET_LENGTH} characters, too short to be kept out of the output: use --env for it", 2)
        secure.append((name, value))
    names = [name for name, _ in plain + secure]
    for name in names:
        if not ENV_NAME.match(name):
            raise Problem(f"an environment variable is named with letters, digits and _, not {name!r}", 2)
    if len(set(names)) != len(names):
        raise Problem("an environment variable is given twice", 2)
    for name, value in plain:
        if any(ord(character) < 32 for character in value):
            raise Problem(f"the value of --env {name} holds a control character", 2)
    servers = []
    for server in args.dns_server:
        try:
            address = ipaddress.ip_address(server)
        except ValueError:
            raise Problem(f"--dns-server is an IP address, not {server!r}", 2)
        if address.version != 4 or not address.is_private:
            raise Problem("--dns-server is a private IPv4 address: the landing zone's resolver, not a public one", 2)
        servers.append(str(address))
    if len(servers) > 3:
        raise Problem("at most three --dns-server", 2)
    return plain, secure, servers


def read_files(args) -> dict[str, bytes]:
    """The files of the secret volume: the script, with Unix line endings (bash does not run a script with Windows ones), and each --secret-file as it is."""
    files: dict[str, bytes] = {}
    script = Path(args.script)
    try:
        files[script.name] = script.read_bytes().replace(b"\r\n", b"\n")
    except OSError:
        raise Problem(f"the script {args.script} cannot be read", 2)
    for pair in args.secret_file:
        name, path = split_pair(pair, "--secret-file")
        try:
            content = Path(path).read_bytes()
        except OSError:
            raise Problem(f"--secret-file {name}: {path} cannot be read", 2)
        if name in files:
            raise Problem(f"the file {name} is in the secret volume twice", 2)
        files[name] = content
    for name in files:
        if not FILE_NAME.match(name):
            raise Problem(f"a file of the secret volume is named with letters, digits and . _ -, not {name!r}", 2)
    if sum(len(content) for content in files.values()) > MAX_FILE_BYTES:
        raise Problem(f"the files are more than {MAX_FILE_BYTES} bytes; this tool refuses that: a request with {FILES_TAKEN_BYTES} bytes of files was taken, and one with {FILES_REFUSED_BYTES} was refused "
                      "with an internal server error (2026-11-06), so what is bigger has to be built in the container from sources", 2)
    return files


def group_document(args, files: dict[str, bytes], plain, secure, servers, started: str) -> dict:
    """The body of the request, in the form that `az container create --file` sends as it is (Azure Resource Manager's own)."""
    properties: dict = {
        "osType": "Linux",
        "restartPolicy": "Never",
        "subnetIds": [{"id": args.subnet_id, "name": "default"}],
        "ipAddress": {"type": "Private", "ports": [{"protocol": "TCP", "port": 80}]},
        "containers": [{
            "name": CONTAINER,
            "properties": {
                "image": args.image,
                "command": ["/bin/bash", f"{MOUNT}/{Path(args.script).name}"],
                "ports": [{"port": 80, "protocol": "TCP"}],
                "resources": {"requests": {"cpu": args.cpu, "memoryInGB": args.memory}},
                "environmentVariables": [{"name": name, "value": value} for name, value in plain] + [{"name": name, "secureValue": value} for name, value in secure],
                "volumeMounts": [{"name": "op", "mountPath": MOUNT}],
            },
        }],
        "volumes": [{"name": "op", "secret": {name: base64.b64encode(content).decode("ascii") for name, content in files.items()}}],
    }
    if servers:
        properties["dnsConfig"] = {"nameServers": servers}
    return {
        "apiVersion": API_VERSION,
        "type": "Microsoft.ContainerInstance/containerGroups",
        "name": args.name,
        "tags": {"workload": "meternaut", "component": "operator", STARTED_TAG: started},
        "identity": {"type": "UserAssigned", "userAssignedIdentities": {args.identity_id: {}}},
        "properties": properties,
    }


def write_private(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def az_arguments(args, *words: str) -> list[str]:
    arguments = ["container", *words, "--only-show-errors"]
    if args.subscription:
        arguments += ["--subscription", args.subscription]
    return arguments


def read_log(az, args, printer: Printer, stream: LogStream) -> str | None:
    """Prints the lines of the container's log that were not printed yet. None when the log could not be read."""
    code, out, _ = az(az_arguments(args, "logs", "--resource-group", args.resource_group, "--name", args.name, "--container-name", CONTAINER))
    if code != 0:
        return None
    for line in stream.new_lines(out):
        printer.log(line)
    return out


def watch(az, args, printer: Printer, stream: LogStream, progress: Progress, sleep, clock, begun: float) -> int:
    """Polls the group until the container has terminated, and returns the container's exit code. A time that is over, and a group that failed or cannot be read, are a Problem."""
    last_line = None
    said_events: set[tuple] = set()
    failures = 0
    while True:
        elapsed = clock() - begun
        if elapsed >= args.timeout_seconds:
            raise TimedOut(args.timeout_seconds)
        code, out, err = az(az_arguments(args, "show", "--resource-group", args.resource_group, "--name", args.name, "--output", "json"))
        document = None
        if code == 0:
            try:
                document = json.loads(out)
            except ValueError:
                document = None
        if document is None:
            if code != 0 and NOT_FOUND.search(err or "") and elapsed < NOT_VISIBLE_YET_SECONDS:
                sleep(args.poll_seconds)
                continue
            failures += 1
            if failures >= READ_FAILURES_ALLOWED:
                raise Problem(f"the container group could not be read {failures} times in a row: {first_line(err) if code != 0 else 'the answer is not JSON'}")
            sleep(args.poll_seconds)
            continue
        failures = 0
        state = State(document)
        progress.state = state
        line = state.describe()
        if line != last_line:
            printer.say(f"State after {int(elapsed)} seconds: {line}")
            last_line = line
        for event in state.events:
            key = (event.get("type"), event.get("name"), event.get("message"))
            if event.get("type") == "Warning" and key not in said_events:
                said_events.add(key)
                printer.say(f"Event: {describe_event(event)}")
        if state.provisioning.lower() == "failed":
            raise Problem("the container group could not be started: its provisioning failed (the events say why; an image that cannot be pulled is the likely cause)")
        if state.is_("terminated"):
            return state.exit_code if state.exit_code is not None else 1
        if state.is_("running"):
            read_log(az, args, printer, stream)
        sleep(args.poll_seconds)


def delete_group(az, args, printer: Printer, sleep) -> bool:
    for attempt in range(1, DELETE_TRIES + 1):
        code, _, err = az(az_arguments(args, "delete", "--resource-group", args.resource_group, "--name", args.name, "--yes", "--output", "none"))
        if code == 0 or NOT_FOUND.search(err or ""):
            printer.say(f"The container group {args.name} is deleted.")
            return True
        printer.say(f"The container group {args.name} could not be deleted yet (try {attempt} of {DELETE_TRIES}): {first_line(err)}")
        if attempt < DELETE_TRIES:
            sleep(DELETE_PAUSE)
    printer.complain(f"error: the container group {args.name} is still there. Run `cleanup` (it deletes the groups that this tool made), or delete it by hand")
    return False


def write_summary(path: str, args, printer: Printer, code: int, seconds: int) -> None:
    lines = [line.replace("```", "'''") for line in printer.log_lines[:LOG_LINES_IN_SUMMARY]]
    cut = len(printer.log_lines) - len(lines)
    body = ["", f"### The Operator ran `{args.name}`", "", "```", *lines, *([f"... {cut} more lines are in the log of the step"] if cut > 0 else []), "```", "",
            f"Exit code {code} after {seconds} seconds. The container group is deleted at the end of every run."]
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(printer.redact("\n".join(body)) + "\n")
    except OSError:
        printer.complain(f"warning: the summary {path} could not be written")


def run_command(args, az, sleep=time.sleep, clock=time.monotonic) -> int:
    require_actions()
    only_in_the_project(args, ("--subnet-id", args.subnet_id), ("--identity-id", args.identity_id))
    plain, secure, servers = check_options(args)
    files = read_files(args)
    printer = Printer([value for _, value in secure])
    started_at = datetime.datetime.now(datetime.timezone.utc).strftime(TIME_FORMAT)
    document = group_document(args, files, plain, secure, servers, started_at)
    work = Path(tempfile.mkdtemp(prefix="operator-", dir=os.environ.get("RUNNER_TEMP") or None))
    stream = LogStream()
    progress = Progress()
    begun = clock()
    code = 1
    touched = False
    try:
        body = write_private(work, "group.json", json.dumps(document))
        printer.say(f"Making the container group {args.name}: {args.image.split('@')[0]} pinned by {'digest' if '@sha256:' in args.image else 'tag'}, {args.cpu:g} CPU, {args.memory:g} GB, "
                    f"restart never, {len(files)} file(s) in the secret volume, {len(secure)} secure value(s) that are not shown, {len(servers)} DNS server(s).")
        touched = True
        created, _, err = az(az_arguments(args, "create", "--resource-group", args.resource_group, "--name", args.name, "--file", str(body), "--no-wait", "--output", "none"))
        if created != 0:
            raise Problem(f"the container group could not be made: {first_line(err)}")
        printer.say(f"The request is accepted. Waiting for the container, at most {args.timeout_seconds} seconds.")
        code = watch(az, args, printer, stream, progress, sleep, clock, begun)
        printer.say(f"The container finished with exit code {code} after {int(clock() - begun)} seconds.")
    except KeyboardInterrupt:
        printer.complain("error: interrupted; the container group is deleted below")
        code = INTERRUPTED
    except Problem as problem:
        printer.complain(f"error: {problem}")
        code = problem.code
    finally:
        if touched:
            state = progress.state
            try:
                if state is not None and state.started:
                    last = read_log(az, args, printer, stream)
                    if last is not None and state.is_("terminated") and (len(last.encode("utf-8")) >= STOPPED_LOG_BYTES or len(last.splitlines()) >= STOPPED_LOG_LINES):
                        printer.say("Note: the log of a stopped container is cut at 16 KB or 1,000 lines, and this one is as long: lines may be missing. Make the script print less.")
                elif state is not None:
                    for event in state.events:
                        printer.say(f"Event: {describe_event(event)}")
                    printer.say("The container never started.")
            except Exception as error:  # the delete below must run whatever happened here
                printer.complain(f"warning: the last read of the log failed: {error.__class__.__name__}")
            if not delete_group(az, args, printer, sleep) and code == 0:
                code = 1
        shutil.rmtree(work, ignore_errors=True)
        if args.summary:
            write_summary(args.summary, args, printer, code, int(clock() - begun))
    return code


def age_in_minutes(started: str | None, now: datetime.datetime) -> float | None:
    try:
        then = datetime.datetime.strptime(started or "", TIME_FORMAT).replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None
    return (now - then).total_seconds() / 60


def cleanup_command(args, az, now: datetime.datetime | None = None, sleep=time.sleep) -> int:
    require_actions()
    only_in_the_project(args)
    if not GROUP.match(args.resource_group):
        raise Problem("the resource group is letters, digits and . _ - ( )", 2)
    if len(args.prefix) < MIN_PREFIX or not PREFIX.match(args.prefix):
        raise Problem(f"the prefix is at least {MIN_PREFIX} lower-case letters, digits and hyphens, starting with a letter", 2)
    if args.older_than_minutes < 0:
        raise Problem("--older-than-minutes is 0 or more", 2)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    code, out, err = az(az_arguments(args, "list", "--resource-group", args.resource_group, "--output", "json"))
    if code != 0:
        raise Problem(f"the container groups could not be listed: {first_line(err)}")
    try:
        groups = json.loads(out) or []
    except ValueError:
        raise Problem("the list of container groups is not JSON")
    printer = Printer()
    failed = 0
    deleted = 0
    for group in groups:
        name = str(group.get("name") or "") if isinstance(group, dict) else ""
        if not name.startswith(args.prefix):
            continue
        tags = group.get("tags") or {}
        if STARTED_TAG not in tags:
            printer.say(f"{name}: not made by this tool (no tag {STARTED_TAG}), left alone.")
            continue
        age = age_in_minutes(tags.get(STARTED_TAG), now)
        if age is not None and age < args.older_than_minutes:
            printer.say(f"{name}: {age:.0f} minutes old, younger than {args.older_than_minutes:g}: left.")
            continue
        target = argparse.Namespace(**{**vars(args), "name": name})
        if delete_group(az, target, printer, sleep):
            deleted += 1
        else:
            failed += 1
    printer.say(f"{deleted} container group(s) deleted, {failed} that could not be.")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="make a container group, run one script in it, read its log, delete it")
    run.add_argument("--resource-group", required=True)
    run.add_argument("--name", required=True, help="the name of the container group")
    run.add_argument("--subnet-id", required=True, help="the resource id of the Operator's subnet")
    run.add_argument("--identity-id", required=True, help="the resource id of the Operator's user-assigned identity")
    run.add_argument("--image", required=True, help="registry/name@sha256:<digest>")
    run.add_argument("--script", required=True, help="the script that the container runs with bash")
    run.add_argument("--secret-file", action="append", default=[], metavar="NAME=PATH", help="a file for the secret volume, at /mnt/op/NAME")
    run.add_argument("--env", action="append", default=[], metavar="NAME=VALUE", help="an environment variable")
    run.add_argument("--secure-env", action="append", default=[], metavar="NAME[=VALUE]", help="a secure environment variable; without a value it is taken from this process's environment")
    run.add_argument("--dns-server", action="append", default=[], metavar="IP", help="a DNS server of the container group (a container group does not take the network's)")
    run.add_argument("--cpu", type=float, default=1.0)
    run.add_argument("--memory", type=float, default=1.5, help="GB")
    run.add_argument("--timeout-seconds", type=int, default=600)
    run.add_argument("--poll-seconds", type=float, default=5.0)
    run.add_argument("--allow-tag", action="store_true", help="accept registry/name:tag instead of a digest (for the probe)")
    run.add_argument("--summary", help="append the log and the outcome to this file (the run's summary)")
    run.add_argument("--subscription")
    clean = commands.add_parser("cleanup", help="delete the container groups of this tool that are left, by prefix and age")
    clean.add_argument("--resource-group", required=True)
    clean.add_argument("--prefix", required=True)
    clean.add_argument("--older-than-minutes", type=float, default=30.0)
    clean.add_argument("--subscription")
    return parser


def terminate(_signal, _frame):
    raise KeyboardInterrupt()


def main(argv=None, az=None, sleep=time.sleep, clock=time.monotonic) -> int:
    args = build_parser().parse_args(argv)
    az = az if az is not None else Az()
    # A job that is cancelled gets SIGINT, then SIGTERM: both end the run the same way, with the container group deleted.
    try:
        previous = signal.signal(signal.SIGTERM, terminate)
    except (ValueError, OSError):
        previous = None
    try:
        return run_command(args, az, sleep, clock) if args.command == "run" else cleanup_command(args, az, sleep=sleep)
    except Problem as problem:
        print(f"error: {problem}", file=sys.stderr)
        return problem.code
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    sys.exit(main())
