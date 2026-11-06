import base64
import contextlib
import datetime
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
# The tool is not named operator.py: tools/ is the first place a tool looks for a module, and a file of that name there would be taken for the standard library's.
spec = importlib.util.spec_from_file_location("operator_run", ROOT / "tools" / "operator-run.py")
op = importlib.util.module_from_spec(spec)
spec.loader.exec_module(op)

SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
GROUP = "rg-example"
NAME = "op-probe-1"
SUBNET = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.Network/virtualNetworks/vnet-example/subnets/snet-ops"
IDENTITY = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-example-operator"
DIGEST = "sha256:" + "ab" * 32
IMAGE = f"mcr.microsoft.com/azure-cli@{DIGEST}"
SECRET = "Zx9-hunter2-QWERTY-42"
TOKEN_OF_THE_RUN = "ghs_Tok3nOfTheRun_0123456789"


def text(path):
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


def shown(provisioning="Succeeded", group="Running", container="Running", exit_code=None, detail=None, events=None, started=True, group_events=None):
    """What `az container show` prints for a group with one container."""
    current = {"state": container}
    if started:
        current["startTime"] = "2026-11-06T07:00:00+00:00"
    if exit_code is not None:
        current["exitCode"] = exit_code
    if detail:
        current["detailStatus"] = detail
    view = {"state": group}
    if group_events is not None:
        view["events"] = group_events
    return (0, json.dumps({"provisioningState": provisioning, "instanceView": view, "containers": [{"name": "operator", "instanceView": {"currentState": current, "events": events or []}}]}), "")


def warning(name, message, count=1):
    return {"count": count, "name": name, "message": message, "type": "Warning"}


class Clock:
    """A clock that only the pauses move, so that a run of minutes takes no time."""

    def __init__(self):
        self.now = 0.0
        self.pauses = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.pauses.append(seconds)
        self.now += max(seconds, 1)


class FakeAz:
    """A stand-in for `az` that plays a container group. It answers create, show, logs, delete and list, remembers every call and the document that create was given.

    `shows` and `logs` are the successive answers (the last one stays); an answer is a (code, output, error) triple, or an exception to raise."""

    def __init__(self, shows=None, logs=None, create=(0, "", ""), deletes=None, listing=None):
        self.calls = []
        self.shows = list(shows or [shown()])
        self.logs = list(logs or [(0, "", "")])
        self.create_answer = create
        self.deletes = list(deletes or [(0, "", "")])
        self.listing = listing
        self.document = None
        self.work_dir = None
        self.file_mode = None

    def verbs(self):
        return [call[1] for call in self.calls]

    @staticmethod
    def next_of(answers):
        answer = answers[0] if len(answers) == 1 else answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def __call__(self, arguments):
        self.calls.append(list(arguments))
        verb = arguments[1]
        if verb == "create":
            path = Path(arguments[arguments.index("--file") + 1])
            self.document = json.loads(path.read_text(encoding="utf-8"))
            self.work_dir = path.parent
            self.file_mode = path.stat().st_mode & 0o777
            return self.create_answer
        if verb == "show":
            return self.next_of(self.shows)
        if verb == "logs":
            return self.next_of(self.logs)
        if verb == "delete":
            return self.next_of(self.deletes)
        if verb == "list":
            return self.listing
        raise AssertionError(f"an az call that nobody expects: {arguments}")


def run_tool(*extra, az, clock=None, env=None, script_text="echo hi\n", files=None, actions=True, name=NAME):
    """`operator-run.py run` with the standard arguments; returns the exit code, what it printed on standard output and on standard error, and the folder it used."""
    clock = clock or Clock()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        script = tmp / "probe.sh"
        script.write_text(script_text, encoding="utf-8", newline="\n")
        argv = ["run", "--resource-group", GROUP, f"--name={name}", "--subnet-id", SUBNET, "--identity-id", IDENTITY, "--image", IMAGE, "--script", str(script), "--poll-seconds", "5", *extra]
        for file_name, content in (files or {}).items():
            path = tmp / file_name
            path.write_bytes(content)
            argv += ["--secret-file", f"{file_name}={path}"]
        out, err = io.StringIO(), io.StringIO()
        environment = {"RUNNER_TEMP": str(tmp), **({"GITHUB_ACTIONS": "true"} if actions else {}), **(env or {})}
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), mock.patch.dict(os.environ, environment, clear=False):
            if not actions:
                os.environ.pop("GITHUB_ACTIONS", None)
            code = op.main(argv, az=az, sleep=clock.sleep, clock=clock)
        return code, out.getvalue(), err.getvalue(), tmp


def clean_run(az, *extra, **kwargs):
    code, out, err, _ = run_tool(*extra, az=az, **kwargs)
    return code, out, err


class Arguments(unittest.TestCase):
    def refused(self, *extra, **kwargs):
        az = FakeAz()
        code, out, err = clean_run(az, *extra, **kwargs)
        self.assertEqual(code, 2, (out, err))
        self.assertEqual(az.calls, [], "a refused argument is refused before anything is asked of Azure")
        return err

    def test_the_name_of_the_group_is_a_safe_pattern(self):
        for name in ("Op-probe", "op_probe", "1probe", "-probe", "probe-", "op--probe", "ab", "a" * 64, "op probe", "op;rm", "op/../x", "op.probe"):
            with self.subTest(name=name):
                self.refused(name=name)

    def test_a_good_name_is_taken(self):
        for name in ("op-probe-1", "operator-probe-9876543210", "abc", "a" * 63):
            with self.subTest(name=name):
                az = FakeAz(shows=[shown(container="Terminated", exit_code=0)])
                code, _, _ = clean_run(az, name=name)
                self.assertEqual(code, 0)

    def test_the_image_is_a_digest_and_a_tag_only_when_it_is_allowed(self):
        az = FakeAz(shows=[shown(container="Terminated", exit_code=0)])
        self.assertEqual(clean_run(az)[0], 0)

    def test_an_image_that_is_not_pinned_is_refused_and_the_message_says_how_to_pin_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "probe.sh"
            script.write_text("echo hi\n", encoding="utf-8")
            base = ["run", "--resource-group", GROUP, "--name", NAME, "--subnet-id", SUBNET, "--identity-id", IDENTITY, "--script", str(script)]
            for image in ("mcr.microsoft.com/azure-cli:2.92.0", "mcr.microsoft.com/azure-cli", "azure-cli", "azure-cli:latest", f"mcr.microsoft.com/azure-cli@sha256:{'a' * 63}",
                          f"mcr.microsoft.com/azure-cli@sha256:{'G' * 64}", f"mcr.microsoft.com/azure-cli@md5:{'a' * 32}", "mcr.microsoft.com/azure-cli@sha256:" + "a" * 64 + " --x"):
                with self.subTest(image=image):
                    az, err = FakeAz(), io.StringIO()
                    with contextlib.redirect_stderr(err), mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
                        code = op.main([*base, "--image", image], az=az)
                    self.assertEqual(code, 2)
                    self.assertEqual(az.calls, [])
                    self.assertIn("sha256", err.getvalue())
            az, err = FakeAz(), io.StringIO()
            with contextlib.redirect_stderr(err), mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
                code = op.main([*base, "--image", "mcr.microsoft.com/azure-cli:2.92.0"], az=az)
            self.assertIn("is a tag, and a tag can move", err.getvalue())
            self.assertIn("--allow-tag", err.getvalue())
            az = FakeAz(shows=[shown(container="Terminated", exit_code=0)])
            out = io.StringIO()
            with contextlib.redirect_stdout(out), mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
                code = op.main([*base, "--image", "mcr.microsoft.com/azure-cli:2.92.0", "--allow-tag"], az=az, sleep=Clock().sleep)
            self.assertEqual(code, 0)
            self.assertIn("pinned by tag", out.getvalue())
            self.assertEqual(az.document["properties"]["containers"][0]["properties"]["image"], "mcr.microsoft.com/azure-cli:2.92.0")

    def test_the_ids_of_the_subnet_and_the_identity_are_resource_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "probe.sh"
            script.write_text("echo hi\n", encoding="utf-8")
            for subnet, identity in (("snet-ops", IDENTITY), (SUBNET, "id-example-operator"), (SUBNET.replace("/subnets/snet-ops", ""), IDENTITY), (SUBNET, IDENTITY.replace("userAssignedIdentities", "disks"))):
                az, err = FakeAz(), io.StringIO()
                with contextlib.redirect_stderr(err), mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
                    code = op.main(["run", "--resource-group", GROUP, "--name", NAME, "--subnet-id", subnet, "--identity-id", identity, "--image", IMAGE, "--script", str(script)], az=az)
                self.assertEqual((code, az.calls), (2, []), (subnet, identity))

    def test_environment_variables_are_checked(self):
        self.refused("--env", "NOVALUE")
        self.refused("--env", "1BAD=x")
        self.refused("--env", "A-B=x")
        self.refused("--env", "A=1", "--env", "A=2")
        self.refused("--env", "A=1", "--secure-env", f"A={SECRET}")
        self.refused("--env", "A=line\nbreak")

    def test_a_secure_value_that_is_too_short_to_be_kept_out_of_the_output_is_refused(self):
        err = self.refused("--secure-env", "TOKEN=xyz12")
        self.assertIn("use --env", err)
        self.assertNotIn("xyz12", err, "the value is not echoed")

    def test_a_secure_value_can_be_taken_from_the_environment_of_the_process_and_then_it_is_on_no_command_line(self):
        az = FakeAz(shows=[shown(container="Terminated", exit_code=0)])
        code, out, err = clean_run(az, "--secure-env", "OP_TOKEN", env={"OP_TOKEN": SECRET})
        self.assertEqual(code, 0, err)
        environment = az.document["properties"]["containers"][0]["properties"]["environmentVariables"]
        self.assertEqual(environment, [{"name": "OP_TOKEN", "secureValue": SECRET}])
        self.assertFalse(any(SECRET in part for call in az.calls for part in call))
        self.assertNotIn(SECRET, out + err)
        az = FakeAz()
        code, _, err = clean_run(az, "--secure-env", "OP_TOKEN_UNSET", env={"OP_TOKEN_UNSET": ""})
        self.assertEqual((code, az.calls), (2, []))
        self.assertIn("is not set", err)

    def test_dns_servers_are_private_ipv4_addresses_and_at_most_three(self):
        self.refused("--dns-server", "8.8.8.8")
        self.refused("--dns-server", "not-an-address")
        self.refused("--dns-server", "fd00::53")
        self.refused("--dns-server", "10.0.0.4", "--dns-server", "10.0.0.5", "--dns-server", "10.0.0.6", "--dns-server", "10.0.0.7")

    def test_size_and_time_limits(self):
        self.refused("--cpu", "0")
        self.refused("--cpu", "5")
        self.refused("--cpu", "0.25")
        self.refused("--memory", "17")
        self.refused("--memory", "1.55")
        self.refused("--timeout-seconds", "29")
        self.refused("--timeout-seconds", "3601")
        self.refused("--poll-seconds", "61")

    def test_nothing_is_made_outside_a_github_actions_run(self):
        az = FakeAz()
        code, _, err = clean_run(az, actions=False)
        self.assertEqual((code, az.calls), (2, []))
        self.assertIn("only a GitHub Actions run may do that", err)
        self.assertIn("rule 18", err)

    def test_files_of_the_secret_volume_are_checked(self):
        az = FakeAz()
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "x"
            good.write_bytes(b"abc")
            for pair in ("../escape=" + str(good), "a/b=" + str(good), "=" + str(good), "probe.sh=" + str(good), "missing=" + str(Path(tmp) / "nothing"), "noequals"):
                out, err = io.StringIO(), io.StringIO()
                script = Path(tmp) / "probe.sh"
                script.write_text("echo hi\n", encoding="utf-8")
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
                    code = op.main(["run", "--resource-group", GROUP, "--name", NAME, "--subnet-id", SUBNET, "--identity-id", IDENTITY, "--image", IMAGE, "--script", str(script),
                                    "--secret-file", pair], az=az)
                self.assertEqual(code, 2, pair)
        self.assertEqual(az.calls, [])

    def test_more_bytes_than_the_tool_allows_are_refused(self):
        az = FakeAz()
        with mock.patch.object(op, "MAX_FILE_BYTES", 1000):
            code, _, err = clean_run(az, files={"size-test": b"x" * 1001})
        self.assertEqual((code, az.calls), (2, []))
        self.assertIn("more than 1000 bytes", err)

    def test_the_script_that_cannot_be_read_is_refused(self):
        az = FakeAz()
        err = io.StringIO()
        with contextlib.redirect_stderr(err), mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            code = op.main(["run", "--resource-group", GROUP, "--name", NAME, "--subnet-id", SUBNET, "--identity-id", IDENTITY, "--image", IMAGE, "--script", "does-not-exist.sh"], az=az)
        self.assertEqual((code, az.calls), (2, []))


class TheRun(unittest.TestCase):
    """A good run: the group is made, polled, its log is printed line by line once, and the group is deleted last."""

    def good(self):
        return FakeAz(
            shows=[shown("Creating", "Pending", "Waiting", started=False, detail="ContainerCreating"), shown("Succeeded", "Running", "Waiting", started=False), shown(), shown(),
                   shown(group="Succeeded", container="Terminated", exit_code=0, detail="Completed")],
            logs=[(0, "ok: one\n", ""), (0, "ok: one\nok: two\n", ""), (0, "ok: one\nok: two\nprobe-done\n", "")])

    def test_exit_zero_the_log_once_and_the_group_deleted_after_the_last_read(self):
        az = self.good()
        summary = None
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            summary.write_text("earlier text\n", encoding="utf-8")
            code, out, err = clean_run(az, "--summary", str(summary))
            written = summary.read_text(encoding="utf-8")
        self.assertEqual((code, err), (0, ""))
        for line in ("ok: one", "ok: two", "probe-done"):
            self.assertEqual(out.count(f"| {line}\n"), 1, line)
        self.assertIn("State after 0 seconds: provisioning Creating, group Pending, container Waiting (ContainerCreating)", out)
        self.assertIn("The container finished with exit code 0", out)
        self.assertIn(f"The container group {NAME} is deleted.", out)
        verbs = az.verbs()
        self.assertEqual(verbs[0], "create")
        self.assertEqual(verbs[-1], "delete")
        self.assertEqual(verbs.count("create"), 1)
        self.assertEqual(verbs.count("delete"), 1)
        self.assertGreater(len(verbs) - 1 - verbs[::-1].index("logs"), 0)
        self.assertLess(max(i for i, v in enumerate(verbs) if v == "logs"), verbs.index("delete"), "the log is read before the group goes")
        self.assertTrue(written.startswith("earlier text\n"), "the summary is appended to")
        self.assertIn("### The Operator ran `op-probe-1`", written)
        self.assertIn("ok: one\nok: two\nprobe-done\n", written)
        self.assertIn("Exit code 0 after", written)

    def test_the_log_is_not_read_while_the_container_waits(self):
        az = self.good()
        clean_run(az)
        first_log = az.verbs().index("logs")
        shows_before = az.verbs()[:first_log].count("show")
        self.assertEqual(shows_before, 3, "two polls while it waits, and the third finds it running")

    def test_the_group_is_made_with_the_documented_body_and_no_wait(self):
        az = self.good()
        code, _, _, tmp = run_tool("--env", "OPERATOR_GROUP=rg-example", "--dns-server", "10.53.0.4", "--dns-server", "10.53.0.5", "--cpu", "0.5", "--memory", "2", az=az,
                                   files={"size-test": b"\x00\x01\x02" * 100})
        self.assertEqual(code, 0)
        create = az.calls[0]
        self.assertEqual(create[:2], ["container", "create"])
        for pair in (("--resource-group", GROUP), ("--name", NAME)):
            self.assertEqual(create[create.index(pair[0]) + 1], pair[1])
        for flag in ("--no-wait", "--only-show-errors", "--file"):
            self.assertIn(flag, create)
        self.assertEqual(create[create.index("--output") + 1], "none")
        document = az.document
        self.assertEqual(document["type"], "Microsoft.ContainerInstance/containerGroups")
        self.assertEqual(document["name"], NAME)
        self.assertEqual(document["identity"], {"type": "UserAssigned", "userAssignedIdentities": {IDENTITY: {}}})
        self.assertRegex(document["tags"][op.STARTED_TAG], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        properties = document["properties"]
        self.assertEqual((properties["osType"], properties["restartPolicy"]), ("Linux", "Never"))
        self.assertEqual(properties["subnetIds"], [{"id": SUBNET, "name": "default"}])
        self.assertEqual(properties["ipAddress"]["type"], "Private", "a group in a virtual network has no public address")
        self.assertEqual(properties["dnsConfig"], {"nameServers": ["10.53.0.4", "10.53.0.5"]})
        (container,) = properties["containers"]
        self.assertEqual(container["name"], "operator")
        self.assertEqual(container["properties"]["image"], IMAGE)
        self.assertEqual(container["properties"]["command"], ["/bin/bash", "/mnt/op/probe.sh"])
        self.assertEqual(container["properties"]["resources"], {"requests": {"cpu": 0.5, "memoryInGB": 2.0}})
        self.assertEqual(container["properties"]["environmentVariables"], [{"name": "OPERATOR_GROUP", "value": "rg-example"}])
        self.assertEqual(container["properties"]["volumeMounts"], [{"name": "op", "mountPath": "/mnt/op"}])
        (volume,) = properties["volumes"]
        self.assertEqual(sorted(volume["secret"]), ["probe.sh", "size-test"])
        self.assertEqual(base64.b64decode(volume["secret"]["probe.sh"]), b"echo hi\n")
        self.assertEqual(base64.b64decode(volume["secret"]["size-test"]), b"\x00\x01\x02" * 100)

    def test_no_dns_server_means_no_dns_setting(self):
        az = self.good()
        clean_run(az)
        self.assertNotIn("dnsConfig", az.document["properties"])

    def test_a_script_with_windows_line_endings_is_sent_with_unix_ones_and_a_secret_file_is_sent_as_it_is(self):
        az = self.good()
        clean_run(az, script_text="echo one\r\necho two\r\n", files={"data.bin": b"a\r\nb"})
        secret = az.document["properties"]["volumes"][0]["secret"]
        self.assertEqual(base64.b64decode(secret["probe.sh"]), b"echo one\necho two\n")
        self.assertEqual(base64.b64decode(secret["data.bin"]), b"a\r\nb")

    def test_the_request_is_written_to_a_private_file_that_is_gone_afterwards(self):
        az = self.good()
        code, _, _, tmp = run_tool(az=az)
        self.assertEqual(code, 0)
        self.assertIsNotNone(az.work_dir)
        self.assertFalse(az.work_dir.exists(), "the folder that held the request is removed")
        if os.name != "nt":
            self.assertEqual(az.file_mode, 0o600)

    def test_every_call_names_the_subscription_when_one_is_given(self):
        az = self.good()
        clean_run(az, "--subscription", SUBSCRIPTION)
        for call in az.calls:
            self.assertEqual(call[call.index("--subscription") + 1], SUBSCRIPTION, call)
        az = self.good()
        clean_run(az)
        self.assertFalse(any("--subscription" in call for call in az.calls))

    def test_a_group_that_is_not_visible_yet_is_waited_for_and_a_group_that_stays_unreadable_stops_the_run(self):
        not_found = (1, "", "ERROR: (ResourceNotFound) The Resource 'Microsoft.ContainerInstance/containerGroups/x' was not found.")
        az = FakeAz(shows=[not_found, not_found, shown(container="Terminated", exit_code=0)])
        code, _, _ = clean_run(az)
        self.assertEqual(code, 0)
        broken = (1, "", "ERROR: the service is unavailable")
        az = FakeAz(shows=[broken])
        code, out, err = clean_run(az)
        self.assertEqual(code, 1)
        self.assertIn("could not be read 6 times in a row", err)
        self.assertEqual(az.verbs().count("show"), 6)
        self.assertEqual(az.verbs()[-1], "delete", "also then the group is deleted")
        az = FakeAz(shows=[(0, "this is not json", "")])
        code, _, err = clean_run(az)
        self.assertEqual(code, 1)
        self.assertIn("the answer is not JSON", err)


class TheExitCode(unittest.TestCase):
    def test_the_exit_code_of_the_container_is_the_exit_code_of_the_run_and_the_log_and_the_delete_still_come(self):
        az = FakeAz(shows=[shown(), shown(container="Terminated", exit_code=3, detail="Error")], logs=[(0, "line before\n", ""), (0, "line before\nwhy it failed\n", "")])
        code, out, err = clean_run(az)
        self.assertEqual(code, 3)
        self.assertIn("The container finished with exit code 3", out)
        self.assertIn("| why it failed", out)
        self.assertEqual(az.verbs()[-1], "delete")

    def test_a_terminated_container_that_reports_no_exit_code_is_a_failure(self):
        az = FakeAz(shows=[shown(container="Terminated")])
        self.assertEqual(clean_run(az)[0], 1)

    def test_a_container_that_stopped_between_two_polls_still_gives_its_last_lines_from_the_stopped_log(self):
        az = FakeAz(shows=[shown(), shown(container="Terminated", exit_code=0)], logs=[(0, "a\nb\n", ""), (0, "b\nc\n", "")])
        code, out, _ = clean_run(az)
        self.assertEqual(code, 0)
        self.assertEqual([line for line in out.splitlines() if line.startswith("| ")], ["| a", "| b", "| c"])

    def test_a_stopped_log_as_long_as_the_limit_is_said_to_be_possibly_cut(self):
        long_log = "".join(f"line {i}\n" for i in range(1000))
        az = FakeAz(shows=[shown(container="Terminated", exit_code=0)], logs=[(0, long_log, "")])
        code, out, _ = clean_run(az)
        self.assertEqual(code, 0)
        self.assertIn("the log of a stopped container is cut at 16 KB or 1,000 lines", out)
        az = FakeAz(shows=[shown(container="Terminated", exit_code=0)], logs=[(0, "short\n", "")])
        self.assertNotIn("is cut at 16 KB", clean_run(az)[1])


class ImagePullFailure(unittest.TestCase):
    def test_the_events_are_printed_when_the_container_never_started_and_the_group_is_deleted(self):
        pull = warning("Failed", "Failed to pull image \"mcr.microsoft.com/azure-cli@sha256:abc\": context deadline exceeded", 3)
        az = FakeAz(shows=[shown("Creating", "Pending", "Waiting", started=False, events=[warning("Pulling", "pulling image")]),
                           shown("Creating", "Pending", "Waiting", started=False, detail="ImagePullBackOff", events=[pull]),
                           shown("Failed", "Pending", "Waiting", started=False, detail="ImagePullBackOff", events=[pull])])
        code, out, err = clean_run(az)
        self.assertEqual(code, 1)
        self.assertIn("could not be started: its provisioning failed", err)
        self.assertEqual(out.count("Event: [Warning] Failed (x3): Failed to pull image"), 2, "once as it came, once in the list at the end")
        self.assertIn("Event: [Warning] Pulling: pulling image", out)
        self.assertIn("The container never started.", out)
        self.assertNotIn("logs", az.verbs(), "a container that never ran has no log to ask for")
        self.assertEqual(az.verbs()[-1], "delete")

    def test_a_warning_that_comes_again_is_said_once_however_its_count_grows(self):
        shows = [shown("Creating", "Pending", "Waiting", started=False, events=[warning("Failed", "no route", n)]) for n in (1, 2, 3)]
        shows.append(shown(container="Terminated", exit_code=0))
        az = FakeAz(shows=shows)
        _, out, _ = clean_run(az)
        self.assertEqual(out.count("Event: [Warning] Failed"), 1)

    def test_group_events_are_read_too(self):
        az = FakeAz(shows=[shown("Failed", "Pending", "Waiting", started=False, group_events=[warning("FailedSubnet", "subnet is full")])])
        code, out, _ = clean_run(az)
        self.assertEqual(code, 1)
        self.assertIn("subnet is full", out)


class TheTimeout(unittest.TestCase):
    def test_a_container_that_does_not_finish_gives_exit_124_a_last_read_and_a_deleted_group(self):
        az = FakeAz(shows=[shown()], logs=[(0, "still working\n", "")])
        clock = Clock()
        code, out, err = clean_run(az, "--timeout-seconds", "30", clock=clock)
        self.assertEqual(code, 124)
        self.assertIn("did not finish within 30 seconds", err)
        self.assertIn("| still working", out)
        self.assertEqual(az.verbs()[-1], "delete")
        self.assertGreaterEqual(az.verbs().count("logs"), 2, "while it ran, and once more at the end")
        self.assertEqual(out.count("| still working"), 1)
        self.assertLessEqual(clock.now, 40)

    def test_a_container_that_never_left_waiting_says_so_and_shows_its_events(self):
        az = FakeAz(shows=[shown("Creating", "Pending", "Waiting", started=False, events=[warning("Failed", "cannot pull")])])
        code, out, err = clean_run(az, "--timeout-seconds", "30")
        self.assertEqual(code, 124)
        self.assertIn("The container never started.", out)
        self.assertIn("cannot pull", out)
        self.assertNotIn("logs", az.verbs())
        self.assertEqual(az.verbs()[-1], "delete")


class TheGroupIsAlwaysDeleted(unittest.TestCase):
    def test_a_group_that_could_not_be_made_is_still_deleted_in_case_azure_made_part_of_it(self):
        az = FakeAz(create=(1, "", "ERROR: (AuthorizationFailed) The client does not have authorization to perform action"), deletes=[(1, "", "ERROR: (ResourceNotFound) not found")])
        code, out, err = clean_run(az)
        self.assertEqual(code, 1)
        self.assertIn("the container group could not be made: ERROR: (AuthorizationFailed)", err)
        self.assertEqual(az.verbs(), ["create", "delete"])
        self.assertIn(f"The container group {NAME} is deleted.", out, "a group that is not there counts as deleted")

    def test_an_interrupt_deletes_the_group_and_gives_130(self):
        az = FakeAz(shows=[shown(), KeyboardInterrupt()], logs=[(0, "first line\n", "")])
        code, out, err = clean_run(az)
        self.assertEqual(code, 130)
        self.assertIn("interrupted", err)
        self.assertEqual(az.verbs()[-1], "delete")
        self.assertIn("| first line", out)

    def test_a_delete_that_fails_is_tried_again_and_the_exit_code_stays_the_containers(self):
        clock = Clock()
        az = FakeAz(shows=[shown(container="Terminated", exit_code=0)], deletes=[(1, "", "ERROR: busy"), (1, "", "ERROR: busy"), (0, "", "")])
        code, out, _ = clean_run(az, clock=clock)
        self.assertEqual(code, 0)
        self.assertEqual(az.verbs().count("delete"), 3)
        self.assertIn("could not be deleted yet (try 1 of 4): ERROR: busy", out)
        self.assertIn(f"The container group {NAME} is deleted.", out)
        self.assertIn(10, clock.pauses)

    def test_a_group_that_cannot_be_deleted_fails_a_run_that_was_good_and_says_how_to_remove_it(self):
        az = FakeAz(shows=[shown(container="Terminated", exit_code=0)], deletes=[(1, "", "ERROR: busy")])
        code, _, err = clean_run(az)
        self.assertEqual(code, 1)
        self.assertEqual(az.verbs().count("delete"), 4)
        self.assertIn("is still there", err)
        self.assertIn("cleanup", err)

    def test_a_group_that_cannot_be_deleted_does_not_change_the_code_of_a_run_that_failed(self):
        az = FakeAz(shows=[shown(container="Terminated", exit_code=3)], deletes=[(1, "", "ERROR: busy")])
        self.assertEqual(clean_run(az)[0], 3)

    def test_an_error_in_the_last_read_of_the_log_does_not_keep_the_group_from_being_deleted(self):
        az = FakeAz(shows=[shown(), shown(container="Terminated", exit_code=0)], logs=[(0, "a\n", ""), RuntimeError("boom")])
        code, out, err = clean_run(az)
        self.assertEqual(code, 0)
        self.assertEqual(az.verbs()[-1], "delete")
        self.assertIn("the last read of the log failed: RuntimeError", err)

    def test_a_log_that_cannot_be_read_while_the_container_runs_is_tried_again_at_the_next_poll(self):
        az = FakeAz(shows=[shown(), shown(), shown(container="Terminated", exit_code=0)], logs=[(1, "", "ERROR: not ready"), (0, "late line\n", "")])
        code, out, _ = clean_run(az)
        self.assertEqual(code, 0)
        self.assertEqual(out.count("| late line"), 1)


class NothingSecretIsPrinted(unittest.TestCase):
    """A secure value is passed in the body of the request and is in no line that the tool prints, whoever says it: az, the container or the tool."""

    def everything(self, az, *extra, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            code, out, err = clean_run(az, "--secure-env", f"GITHUB_TOKEN={SECRET}", "--summary", str(summary), *extra, **kwargs)
            written = summary.read_text(encoding="utf-8") if summary.exists() else ""
        return code, out, err, written

    def assertNoSecret(self, *streams):
        forms = (SECRET, base64.b64encode(SECRET.encode()).decode(), json.dumps(SECRET)[1:-1])
        for stream in streams:
            for form in forms:
                self.assertNotIn(form, stream)

    def test_a_good_run_whose_container_prints_the_secret_and_whose_az_repeats_it(self):
        echoing = (1, "", f"ERROR: the token {SECRET} was refused")
        az = FakeAz(shows=[echoing, shown(events=[warning("Failed", f"bad value {SECRET}")]), shown(), shown(container="Terminated", exit_code=0)],
                    logs=[(0, f"token is {SECRET}\n", ""), (0, f"token is {SECRET}\nsecond line\n", "")], deletes=[(1, "", f"ERROR: {SECRET}"), (0, "", "")])
        code, out, err, written = self.everything(az)
        self.assertEqual(code, 0, err)
        self.assertNoSecret(out, err, written)
        self.assertIn("| token is ***", out)
        self.assertIn("token is ***\nsecond line\n", written)
        self.assertIn("1 secure value(s) that are not shown", out)
        sent = az.document["properties"]["containers"][0]["properties"]["environmentVariables"]
        self.assertEqual(sent, [{"name": "GITHUB_TOKEN", "secureValue": SECRET}], "the value was sent, as a secure value and not as a plain one")
        self.assertFalse(any(SECRET in part for call in az.calls for part in call), "it is on no command line of az")

    def test_a_group_that_could_not_be_made_and_whose_az_repeats_the_secret(self):
        az = FakeAz(create=(1, "", f"ERROR: invalid secureValue {SECRET}"), deletes=[(1, "", f"ERROR: {SECRET}")])
        code, out, err, written = self.everything(az)
        self.assertEqual(code, 1)
        self.assertNoSecret(out, err, written)
        self.assertIn("***", err)

    def test_a_timeout_and_an_interrupt_with_the_secret_in_the_log_and_the_events(self):
        az = FakeAz(shows=[shown(events=[warning("Failed", f"{SECRET}")])], logs=[(0, f"{SECRET}\n", "")])
        code, out, err, written = self.everything(az, "--timeout-seconds", "30")
        self.assertEqual(code, 124)
        self.assertNoSecret(out, err, written)
        az = FakeAz(shows=[shown(), KeyboardInterrupt()], logs=[(0, f"{SECRET}\n", "")])
        code, out, err, written = self.everything(az)
        self.assertEqual(code, 130)
        self.assertNoSecret(out, err, written)

    def test_the_secret_is_not_in_the_request_file_after_the_run(self):
        az = FakeAz(shows=[shown(container="Terminated", exit_code=0)])
        with tempfile.TemporaryDirectory() as tmp:
            code, _, _, work = run_tool("--secure-env", f"GITHUB_TOKEN={SECRET}", az=az)
            self.assertEqual(code, 0)
            self.assertFalse(az.work_dir.exists())
            leftovers = [p for p in Path(work).rglob("*") if p.is_file() and SECRET.encode() in p.read_bytes()]
            self.assertEqual(leftovers, [])

    def test_the_secure_value_of_one_variable_is_taken_out_of_a_line_that_holds_it_inside_other_text(self):
        printer = op.Printer([SECRET])
        self.assertEqual(printer.redact(f"a{SECRET}b {SECRET}"), "a***b ***")
        self.assertEqual(op.Printer([]).redact("nothing to hide"), "nothing to hide")


class TheLogStream(unittest.TestCase):
    def test_a_log_that_grows_gives_only_its_new_lines(self):
        stream = op.LogStream()
        self.assertEqual(stream.new_lines("a\n"), ["a"])
        self.assertEqual(stream.new_lines("a\nb\n"), ["b"])
        self.assertEqual(stream.new_lines("a\nb\n"), [])
        self.assertEqual(stream.new_lines("a\nb\nc"), ["c"])

    def test_a_log_that_is_cut_at_its_start_continues_where_the_overlap_ends(self):
        stream = op.LogStream()
        stream.new_lines("a\nb\nc\nd\n")
        self.assertEqual(stream.new_lines("c\nd\ne\n"), ["e"])
        self.assertEqual(stream.new_lines("d\ne\n"), [])

    def test_a_log_with_nothing_in_common_is_new(self):
        stream = op.LogStream()
        stream.new_lines("a\nb\n")
        self.assertEqual(stream.new_lines("x\ny\n"), ["x", "y"])

    def test_blank_lines_inside_stay_and_windows_line_ends_go(self):
        stream = op.LogStream()
        self.assertEqual(stream.new_lines("a\r\n\r\nb\r\n\r\n"), ["a", "", "b"])
        self.assertEqual(stream.new_lines(""), [])

    def test_the_same_line_twice_in_a_row_is_two_lines(self):
        stream = op.LogStream()
        self.assertEqual(stream.new_lines("x\nx\n"), ["x", "x"])
        self.assertEqual(stream.new_lines("x\nx\nx\n"), ["x"])


NOW = datetime.datetime(2026, 11, 6, 12, 0, 0, tzinfo=datetime.timezone.utc)


def stamp(minutes_ago):
    return (NOW - datetime.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def group_listing():
    return [
        {"name": "op-probe-1", "tags": {op.STARTED_TAG: stamp(90)}},
        {"name": "op-probe-2", "tags": {op.STARTED_TAG: stamp(5)}},
        {"name": "op-probe-3", "tags": {}},
        {"name": "op-probe-4", "tags": {op.STARTED_TAG: "yesterday"}},
        {"name": "other-1", "tags": {op.STARTED_TAG: stamp(500)}},
        {"name": "op-probe-5"},
    ]


class Cleanup(unittest.TestCase):
    def cleanup(self, *extra, az=None, actions=True):
        az = az or FakeAz(listing=(0, json.dumps(group_listing()), ""))
        out, err = io.StringIO(), io.StringIO()
        arguments = ["cleanup", "--resource-group", GROUP, "--prefix", "op-probe-", *extra]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"} if actions else {}, clear=False):
            if not actions:
                os.environ.pop("GITHUB_ACTIONS", None)
            parser = op.build_parser()
            args = parser.parse_args(arguments)
            try:
                code = op.cleanup_command(args, az, now=NOW, sleep=Clock().sleep)
            except op.Problem as problem:
                print(f"error: {problem}", file=sys.stderr)
                code = problem.code
        return code, out.getvalue(), err.getvalue(), az

    def deleted(self, az):
        return [call[call.index("--name") + 1] for call in az.calls if call[1] == "delete"]

    def test_only_the_groups_of_the_prefix_that_carry_the_tag_and_are_old_enough_go(self):
        code, out, err, az = self.cleanup()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self.deleted(az), ["op-probe-1", "op-probe-4"], "an hour and a half old; and one whose tag cannot be read counts as old")
        self.assertIn("op-probe-2: 5 minutes old, younger than 30: left.", out)
        self.assertIn("op-probe-3: not made by this tool", out)
        self.assertIn("op-probe-5: not made by this tool", out)
        self.assertNotIn("other-1", out + str(az.calls), "a group of another prefix is not even looked at")
        self.assertIn("2 container group(s) deleted, 0 that could not be.", out)

    def test_zero_minutes_takes_every_group_of_this_tool_with_the_prefix(self):
        _, _, _, az = self.cleanup("--older-than-minutes", "0")
        self.assertEqual(self.deleted(az), ["op-probe-1", "op-probe-2", "op-probe-4"])

    def test_a_delete_that_fails_fails_the_command(self):
        az = FakeAz(listing=(0, json.dumps(group_listing()), ""), deletes=[(0, "", ""), (1, "", "ERROR: busy")])
        code, out, err, az = self.cleanup(az=az)
        self.assertEqual(code, 1)
        self.assertIn("1 that could not be", out)

    def test_a_prefix_that_is_too_short_or_not_a_name_is_refused_before_anything_is_listed(self):
        for prefix in ("op", "OP-", "op probe", "-op-", "op/../"):
            az = FakeAz(listing=(0, "[]", ""))
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
                code = op.main(["cleanup", "--resource-group", GROUP, f"--prefix={prefix}"], az=az)
            self.assertEqual((code, az.calls), (2, []), prefix)

    def test_a_list_that_fails_is_an_error_and_nothing_is_deleted(self):
        az = FakeAz(listing=(1, "", "ERROR: no"))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            code = op.main(["cleanup", "--resource-group", GROUP, "--prefix", "op-probe-"], az=az)
        self.assertEqual(code, 1)
        self.assertNotIn("delete", az.verbs())

    def test_it_refuses_to_run_outside_a_github_actions_run(self):
        code, out, err, az = self.cleanup(actions=False)
        self.assertEqual(code, 2)
        self.assertEqual(az.calls, [])


class TheFolder(unittest.TestCase):
    def test_no_tool_is_named_like_a_module_of_the_standard_library(self):
        # A tool runs with tools/ first on the module path. A file there with the name of a standard module (operator.py) is imported by the standard library itself
        # (collections does `from operator import ...`) and breaks every tool at its first import.
        names = {path.stem for path in (ROOT / "tools").glob("*.py")}
        self.assertEqual(sorted(names & set(sys.stdlib_module_names)), [])

    def test_the_tool_is_run_from_its_own_folder_without_trouble(self):
        done = subprocess.run([sys.executable, str(ROOT / "tools" / "operator-run.py"), "--help"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("always deletes the group", done.stdout)


class OperatorTemplate(unittest.TestCase):
    """environment/operator/main.bicep: the identity, the subnet that is made once, the one role."""

    def setUp(self):
        self.source = text("environment/operator/main.bicep")
        self.code = re.sub(r"(?m)//.*$", "", self.source)

    def declared(self):
        return {match.group(1): match.group(2) for match in re.finditer(r"(?m)^resource (\w+) '([^'@]+)@[^']+'", self.code)}

    def test_it_declares_the_identity_the_group_s_network_pieces_and_the_one_role_and_nothing_else(self):
        types = sorted(self.declared().values())
        self.assertEqual(types, ["Microsoft.Authorization/roleAssignments", "Microsoft.ManagedIdentity/userAssignedIdentities", "Microsoft.Network/networkSecurityGroups",
                                 "Microsoft.Network/virtualNetworks", "Microsoft.Network/virtualNetworks/subnets"])

    def test_the_virtual_network_is_never_declared_again_and_the_subnet_is_made_only_while_it_is_not_there(self):
        # AGENTS.md rule 27: a template that makes the subnet again takes away the route table that the landing zone's network manager put on it.
        self.assertRegex(self.code, r"(?m)^resource vnet 'Microsoft\.Network/virtualNetworks@[^']+' existing = \{$")
        self.assertRegex(self.code, r"(?m)^param opsSubnetExists bool = false$")
        self.assertRegex(self.code, r"(?m)^resource opsSubnet 'Microsoft\.Network/virtualNetworks/subnets@[^']+' = if \(!opsSubnetExists\) \{$")
        self.assertIn("parent: vnet", self.code)
        self.assertNotRegex(self.code, r"\bvnet\.", "nothing reads a property of the network")
        self.assertIn("output subnetId string = resourceId('Microsoft.Network/virtualNetworks/subnets', virtualNetworkName, opsSubnetName)", self.code, "the subnet is named by its id afterwards")

    def test_the_landing_zone_s_pieces_are_not_made_here(self):
        for word in ("routeTable", "routeTables", "privateDnsZones", "privateDnsZoneGroups", "virtualNetworkLinks", "virtualNetworkPeerings", "privateEndpoints", "publicIPAddresses",
                     "natGateways", "Microsoft.ContainerInstance/containerGroups@", "Microsoft.ApiManagement"):
            self.assertNotIn(word, self.code, word)

    def test_the_subnet_is_delegated_to_container_groups_private_and_behind_its_own_network_security_group(self):
        self.assertIn("var opsSubnetName = 'snet-ops'", self.code)
        self.assertIn("serviceName: 'Microsoft.ContainerInstance/containerGroups'", self.code)
        self.assertEqual(self.code.count("delegations: ["), 1)
        self.assertIn("defaultOutboundAccess: false", self.code)
        self.assertIn("name: 'nsg-${workload}-ops'", self.code)
        self.assertIn("securityRules: []", self.code, "no rule of its own: the landing zone's firewall decides")
        self.assertRegex(self.code, r"networkSecurityGroup: \{\n\s+id: opsNsg\.id\n\s+\}")

    def test_the_identity_is_user_assigned_and_named_for_the_operator(self):
        self.assertRegex(self.code, r"resource operatorIdentity 'Microsoft\.ManagedIdentity/userAssignedIdentities@[^']+' = \{\n  name: 'id-\$\{workload\}-operator'")

    def test_the_one_role_is_reader_on_the_resource_group_for_the_identity_only(self):
        self.assertIn("var readerRoleId = 'acdd72a7-3385-48ef-bd42-f606fba81ae7'", self.code)
        (block,) = re.findall(r"(?ms)^resource \w+ 'Microsoft\.Authorization/roleAssignments@[^']+' = \{\n(.*?)^\}", self.code)
        self.assertIn("scope: resourceGroup()", block)
        self.assertIn("name: guid(resourceGroup().id, operatorIdentity.id, readerRoleId)", block)
        self.assertIn("roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', readerRoleId)", block)
        self.assertIn("principalId: operatorIdentity.properties.principalId", block)
        self.assertIn("principalType: 'ServicePrincipal'", block)
        self.assertEqual(len(re.findall(r"RoleId = '", self.code)), 1)

    def test_it_outputs_the_ids_that_the_workflow_and_the_container_need_and_nothing_secret(self):
        outputs = re.findall(r"(?m)^output (\w+) string = (.+)$", self.code)
        self.assertEqual([name for name, _ in outputs], ["identityId", "identityPrincipalId", "identityClientId", "subnetId"])

    def test_every_parameter_says_what_it_is_and_the_text_ones_are_bounded(self):
        for match in re.finditer(r"(?m)^((?:@\w+\([^\n]*\)\n)+)param (\w+) (\w+)", self.code):
            self.assertIn("@description(", match.group(1), match.group(2))
        for name in ("owner", "opsSubnetPrefix"):
            self.assertRegex(self.code, rf"(?m)^@minLength\(\d+\)\n(?:@maxLength\(\d+\)\n)?param {name} string$")
        self.assertRegex(self.code, r"(?m)^@minLength\(9\)\n@maxLength\(18\)\nparam opsSubnetPrefix string$")

    def test_there_is_no_key_in_it(self):
        for word in ("listKeys", "listSecrets", "AccountKey", "SharedAccessKey", "primaryKey", "instrumentationKey", "allowSharedKeyAccess: true", "disableLocalAuth: false"):
            self.assertNotIn(word, self.code, word)

    def test_the_names_that_the_workflow_will_read_are_in_the_template(self):
        self.assertIn("var virtualNetworkName = 'vnet-${workload}'", self.code)
        self.assertIn("name: 'id-${workload}-operator'", self.code)


def find_bash():
    found = shutil.which("bash")
    for candidate in (found, r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
        if candidate and Path(candidate).exists():
            probe = subprocess.run([candidate, "-c", "echo ok"], capture_output=True, text=True)
            if probe.returncode == 0 and probe.stdout.strip() == "ok":
                return candidate
    return None


BASH = find_bash()


def posix(path):
    result = Path(path).resolve().as_posix()
    if os.name == "nt" and len(result) > 1 and result[1] == ":":
        return "/" + result[0].lower() + result[2:]
    return result


STUB_AZ = """#!/bin/bash
# stand-in for az: FAKE_AZ_LOGIN and FAKE_AZ_GROUP are ok or fail
if [ "$1" = login ]; then
  if [ "${FAKE_AZ_LOGIN:-ok}" = ok ]; then exit 0; fi
  echo "ERROR: Failed to connect to MSI 11111111-2222-3333-4444-555555555555 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa $GITHUB_TOKEN" >&2
  echo "second line that must not show" >&2
  exit 1
fi
if [ "$1" = group ]; then
  if [ "${FAKE_AZ_GROUP:-ok}" = ok ]; then echo Succeeded; exit 0; fi
  echo "ERROR: (AuthorizationFailed) The client does not have authorization" >&2
  exit 1
fi
echo "unexpected az call" >&2
exit 9
"""

STUB_GETENT = """#!/bin/bash
# stand-in for getent: FAKE_DNS is "name=ip name=ip"; a name that is not in it does not resolve
if [ "$1" != ahostsv4 ]; then exit 2; fi
for pair in ${FAKE_DNS:-}; do
  if [ "${pair%%=*}" = "$2" ]; then
    ip=${pair#*=}
    printf '%s      STREAM %s\\n%s      DGRAM\\n%s      RAW\\n' "$ip" "$2" "$ip" "$ip"
    exit 0
  fi
done
exit 2
"""

STUB_CURL = """#!/bin/bash
# stand-in for curl: FAKE_CURL is "host=code:exit:finalhost host=..."; a host that is not in it is unreachable (exit 28)
url=""
for argument in "$@"; do url=$argument; done
host=${url#https://}
host=${host%%/*}
for entry in ${FAKE_CURL:-}; do
  if [ "${entry%%=*}" = "$host" ]; then
    rest=${entry#*=}
    code=${rest%%:*}
    rest=${rest#*:}
    status=${rest%%:*}
    final=""
    if [ "$rest" != "$status" ]; then final=${rest#*:}; fi
    printf '%s https://%s/x' "$code" "${final:-$host}"
    exit "$status"
  fi
done
printf '000 %s' "$url"
exit 28
"""

STUB_TIMEOUT = """#!/bin/bash
shift
exec "$@"
"""

STUB_PYTHON = """#!/bin/bash
echo 3.12.7
"""


@unittest.skipIf(BASH is None, "no bash on this machine")
class ProbeScript(unittest.TestCase):
    """operator/probe.sh against stand-ins for az, curl, getent, timeout and python3: what it says for each check, that it says little, and that it never fails."""

    def run_probe(self, env=None, stubs=None, resolv="nameserver 10.53.0.4\nnameserver 168.63.129.16\n", size=None):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            for name, body in {"az": STUB_AZ, "getent": STUB_GETENT, "curl": STUB_CURL, "timeout": STUB_TIMEOUT, "python3": STUB_PYTHON, **(stubs or {})}.items():
                (bin_dir / name).write_text(body, encoding="utf-8", newline="\n")
                (bin_dir / name).chmod(0o755)  # on Linux a file that is not executable is skipped in the search of the path, and the real program would answer
            volume = tmp / "op"
            volume.mkdir()
            if size is not None:
                (volume / "size-test").write_bytes(b"x" * size)
            resolv_conf = tmp / "resolv.conf"
            resolv_conf.write_text(resolv, encoding="utf-8", newline="\n")
            script = tmp / "probe.sh"
            script.write_text(text("operator/probe.sh"), encoding="utf-8", newline="\n")
            environment = {**os.environ, "STUBS": posix(bin_dir), "PROBE_VOLUME": posix(volume), "PROBE_RESOLV_CONF": posix(resolv_conf), "OPERATOR_CLIENT_ID": "11111111-2222-3333-4444-555555555555",
                           "OPERATOR_GROUP": "rg-example", "GITHUB_TOKEN": TOKEN_OF_THE_RUN, **(env or {})}
            done = subprocess.run([BASH, "-c", 'PATH="$STUBS:$PATH"; export PATH; exec bash "$0"', posix(script)], capture_output=True, text=True, env=environment)
        return done, done.stdout.splitlines()

    def good_env(self):
        return {"PROBE_NAMES": "evhns-example.servicebus.windows.net github.com", "PROBE_PRIVATE_NAMES": "evhns-example.servicebus.windows.net",
                "FAKE_DNS": "evhns-example.servicebus.windows.net=10.53.0.20 github.com=140.82.121.4",
                "PROBE_URLS": "https://mcr.microsoft.com/v2/ https://api.github.com/ https://github.com/x/y https://slow.example.net/",
                "FAKE_CURL": "mcr.microsoft.com=200:0 api.github.com=200:0 github.com=302:0:release-assets.githubusercontent.com slow.example.net=302:47",
                "PROBE_SIZE_BYTES": "4000"}

    def test_a_good_environment_gives_one_ok_line_for_each_check_and_ends_with_probe_done(self):
        done, lines = self.run_probe(self.good_env(), size=4000)
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertEqual(lines, [
            "ok: az, curl, getent and python3 are in the image",
            "ok: python3 3.12.7",
            "ok: az login --identity",
            "ok: az group show of the project group: the Reader role works",
            "ok: resolver 1 is private",
            "ok: resolver 2 is the Azure-provided DNS",
            "ok: dns evhns-example.servicebus.windows.net is private",
            "ok: dns github.com is public",
            "ok: https mcr.microsoft.com 200",
            "ok: https api.github.com 200",
            "ok: https github.com 302 -> release-assets.githubusercontent.com",
            "ok: https slow.example.net answers, with more than 2 redirects",
            "ok: secret volume file is 4000 bytes, as sent",
            "probe-done",
        ])

    def test_each_failed_check_is_one_FAIL_line_with_a_few_words_and_the_exit_code_is_still_0(self):
        env = {**self.good_env(), "FAKE_AZ_LOGIN": "fail", "PROBE_PRIVATE_NAMES": "evhns-example.servicebus.windows.net github.com missing.example.net",
               "PROBE_NAMES": "evhns-example.servicebus.windows.net github.com missing.example.net bad*name",
               "PROBE_URLS": "https://mcr.microsoft.com/v2/ https://down.example.net/ https://tls.example.net/ https://gone.example.net/ http://insecure.example.net/ https://bad_host.example.net/",
               "FAKE_CURL": "mcr.microsoft.com=200:0 tls.example.net=000:60 gone.example.net=000:6", "PROBE_SIZE_BYTES": "5000"}
        done, lines = self.run_probe(env, size=4000)
        self.assertEqual(done.returncode, 0)
        self.assertIn("FAIL: az login --identity: ERROR: Failed to connect to MSI <id> <hidden> <hidden>", lines)
        self.assertNotIn("ok: az group show of the project group: the Reader role works", lines, "no group is read without a login")
        self.assertIn("FAIL: dns github.com is public, a private address was expected", lines)
        self.assertIn("FAIL: dns missing.example.net does not resolve", lines)
        self.assertIn("FAIL: dns: not a host name, skipped", lines)
        self.assertIn("FAIL: https down.example.net timed out (curl 28)", lines)
        self.assertIn("FAIL: https tls.example.net certificate not trusted (curl 60)", lines)
        self.assertIn("FAIL: https gone.example.net name not resolved (curl 6)", lines)
        self.assertIn("FAIL: url is not an https address, skipped", lines)
        self.assertIn("FAIL: url has an odd host name, skipped", lines)
        self.assertIn("FAIL: secret volume file is 4000 bytes, 5000 were sent", lines)
        self.assertEqual(lines[-1], "probe-done")

    def test_a_group_that_the_identity_cannot_read_says_so_in_a_few_words(self):
        done, lines = self.run_probe({**self.good_env(), "FAKE_AZ_GROUP": "fail"}, size=4000)
        self.assertIn("ok: az login --identity", lines)
        self.assertIn("FAIL: az group show: ERROR: (AuthorizationFailed) The client does not have authorization", lines)

    def test_a_secret_volume_without_the_file_that_was_to_be_sent_is_a_failure_and_without_a_size_it_is_only_said(self):
        _, lines = self.run_probe({"PROBE_SIZE_BYTES": "4000"}, size=None)
        self.assertIn("FAIL: no size-test file in the secret volume", lines)
        _, lines = self.run_probe({}, size=1234)
        self.assertIn("ok: secret volume file is 1234 bytes", lines)
        _, lines = self.run_probe({}, size=None)
        self.assertFalse([line for line in lines if "secret volume" in line or "size-test" in line])

    def test_a_resolver_that_is_public_or_missing_is_said(self):
        _, lines = self.run_probe({}, resolv="nameserver 8.8.8.8\nnameserver 2001:4860:4860::8888\n")
        self.assertIn("ok: resolver 1 is public", lines)
        self.assertIn("ok: resolver 2 is an IPv6 address", lines)
        _, lines = self.run_probe({}, resolv="search example\n")
        self.assertIn("FAIL: no resolver in /etc/resolv.conf", lines)

    def test_a_private_range_is_ten_172_16_to_31_and_192_168_and_nothing_else(self):
        names = {"a.example": "10.1.2.3", "b.example": "172.16.0.1", "c.example": "172.31.255.1", "d.example": "172.32.0.1", "e.example": "172.15.0.1", "f.example": "192.168.1.1", "g.example": "192.169.0.1",
                 "h.example": "100.64.0.1", "i.example": "169.254.169.254"}
        env = {"PROBE_NAMES": " ".join(names), "FAKE_DNS": " ".join(f"{name}={ip}" for name, ip in names.items())}
        _, lines = self.run_probe(env)
        got = {line.split()[2]: line.split()[-1] for line in lines if line.startswith("ok: dns ")}
        self.assertEqual(got, {"a.example": "private", "b.example": "private", "c.example": "private", "d.example": "public", "e.example": "public", "f.example": "private",
                               "g.example": "public", "h.example": "public", "i.example": "public"})

    def test_it_never_prints_more_than_120_lines_whatever_it_is_asked_and_still_ends_with_probe_done(self):
        # addresses that are refused before any program runs: the cap is the same, and the test does not start two hundred processes
        env = {**self.good_env(), "PROBE_URLS": " ".join(f"ftp://host{i}.example.net/" for i in range(200)), "FAKE_CURL": ""}
        done, lines = self.run_probe(env, size=4000)
        self.assertEqual(done.returncode, 0)
        self.assertEqual(len(lines), 120)
        self.assertEqual(lines[-1], "probe-done")
        self.assertEqual(lines[-2], "FAIL: more checks than 120 lines hold; the rest was left out")
        self.assertLess(len(done.stdout.encode("utf-8")), 12 * 1024, "far below the 16 KB that the log of a stopped container keeps")

    def test_every_line_is_short_and_starts_with_ok_or_FAIL_or_is_the_last_one(self):
        env = {**self.good_env(), "PROBE_NAMES": "a" * 200 + ".example.net", "FAKE_DNS": "", "PROBE_URLS": "https://" + "b" * 300 + ".example.net/x"}
        done, lines = self.run_probe(env, size=4000)
        for line in lines[:-1]:
            self.assertRegex(line, r"^(ok|FAIL): ", line)
            self.assertLessEqual(len(line), 100, line)
        self.assertEqual(lines[-1], "probe-done")

    def test_no_secret_of_the_environment_and_no_token_of_a_command_ever_reaches_the_output(self):
        for scenario in (self.good_env(), {**self.good_env(), "FAKE_AZ_LOGIN": "fail"}):
            done, lines = self.run_probe(scenario, size=4000)
            self.assertNotIn(TOKEN_OF_THE_RUN, done.stdout + done.stderr)
            for line in lines:
                if line.startswith("FAIL: az "):
                    self.assertNotRegex(line, r"[A-Za-z0-9_.~+/=-]{20,}", "what a command said holds no string that could be a token")
                self.assertNotRegex(line, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "an id is hidden")

    def test_it_runs_with_nothing_set_and_still_ends_well(self):
        done, lines = self.run_probe({"OPERATOR_CLIENT_ID": "", "OPERATOR_GROUP": ""})
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertIn("FAIL: az login: OPERATOR_CLIENT_ID is not set", lines)
        self.assertEqual(lines[-1], "probe-done")

    def test_a_subscription_is_passed_to_the_group_read_when_it_is_given_and_only_then(self):
        subscription = "22222222-3333-4444-5555-666666666666"
        strict = STUB_AZ.replace('if [ "$1" = group ]; then\n', 'if [ "$1" = group ]; then\n  case " $* " in *" --subscription ' + subscription + ' "*) ;; *) echo "ERROR: no subscription" >&2; exit 1 ;; esac\n')
        _, lines = self.run_probe({"OPERATOR_SUBSCRIPTION": subscription}, stubs={"az": strict})
        self.assertIn("ok: az group show of the project group: the Reader role works", lines)
        _, lines = self.run_probe({}, stubs={"az": strict})
        self.assertIn("FAIL: az group show: ERROR: no subscription", lines, "without the setting the read is the plain one")

    def test_the_script_has_no_awk_and_no_jq_because_the_image_has_neither_to_rely_on(self):
        source = re.sub(r"(?m)^\s*#.*$", "", text("operator/probe.sh"))
        for word in (r"\bawk\b", r"\bjq\b", r"\bgawk\b", r"\bnslookup\b", r"\bdig\b", r"\bping\b"):
            self.assertNotRegex(source, word, word)

    def test_the_script_names_only_what_it_may_read_from_the_environment(self):
        source = text("operator/probe.sh")
        used = set(re.findall(r"\$\{?(OPERATOR_\w+|PROBE_\w+|FAKE_\w+|GITHUB_\w+)", source))
        self.assertEqual(used, {"OPERATOR_CLIENT_ID", "OPERATOR_GROUP", "OPERATOR_SUBSCRIPTION", "PROBE_NAMES", "PROBE_PRIVATE_NAMES", "PROBE_URLS", "PROBE_SIZE_BYTES", "PROBE_VOLUME",
                                "PROBE_RESOLV_CONF"})

    def test_the_script_is_valid_bash(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "probe.sh"
            script.write_text(text("operator/probe.sh"), encoding="utf-8", newline="\n")
            done = subprocess.run([BASH, "-n", posix(script)], capture_output=True, text=True)
        self.assertEqual((done.returncode, done.stderr), (0, ""))


class Record(unittest.TestCase):
    """docs/proposals/07-private-by-default.md: the points that the design rests on are written down."""

    def setUp(self):
        self.page = text("docs/proposals/07-private-by-default.md")

    def test_it_names_the_options_the_operator_the_probe_and_the_decisions_that_are_the_owner_s(self):
        for heading in ("## The rule and the state", "## What private access breaks", "## The options", "## The Operator", "## What the probe checks", "## Decisions for the owner",
                        "## The order of the work", "## Sources"):
            self.assertIn(heading, self.page, heading)

    def test_it_says_which_statements_are_inferred(self):
        self.assertGreaterEqual(self.page.count("(inferred)"), 3)

    def test_it_names_no_real_identifier(self):
        # the one id that the page may carry is the id of a built-in policy definition, which is the same in every tenant
        public = self.page.replace("437914ee-c176-4fff-8986-7e05eb971365", "")
        self.assertNotRegex(public, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "no id")
        self.assertIn("437914ee-c176-4fff-8986-7e05eb971365", self.page, "the policy that has to be assigned in the landing zone is named by its id")
        self.assertNotRegex(self.page, r"aif-meternaut-[0-9a-f]{8}|func-meternaut-(usage|cases)-[0-9a-f]{8}|evhns-meternaut-[0-9a-f]{8}", "no real resource name")


if __name__ == "__main__":
    unittest.main()
