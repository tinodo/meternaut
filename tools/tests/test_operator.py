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

    def test_it_declares_the_identity_the_group_s_network_pieces_the_three_roles_and_reads_the_namespace_and_its_two_hubs(self):
        types = sorted(self.declared().values())
        self.assertEqual(types, ["Microsoft.Authorization/roleAssignments"] * 3 + ["Microsoft.EventHub/namespaces", "Microsoft.EventHub/namespaces/eventhubs", "Microsoft.EventHub/namespaces/eventhubs",
                                                                                "Microsoft.ManagedIdentity/userAssignedIdentities", "Microsoft.Network/networkSecurityGroups",
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

    def test_the_roles_are_reader_on_the_group_and_data_sender_on_each_of_the_two_control_hubs_for_the_identity_only(self):
        self.assertIn("var readerRoleId = 'acdd72a7-3385-48ef-bd42-f606fba81ae7'", self.code)
        self.assertIn("var eventHubsDataSenderRoleId = '2b629674-e913-4c01-ae53-ef4638d8f975'", self.code)
        self.assertEqual(len(re.findall(r"RoleId = '", self.code)), 2, "two roles, Reader and Data Sender, and no third")
        self.assertEqual(len(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", self.code)), 2)
        blocks = dict(re.findall(r"(?ms)^resource (\w+) 'Microsoft\.Authorization/roleAssignments@[^']+' = \{\n(.*?)^\}", self.code))
        self.assertEqual(sorted(blocks), ["operatorReadsTheGroup", "operatorSendsCasesControl", "operatorSendsUsageControl"])
        expected = {"operatorReadsTheGroup": ("resourceGroup()", "guid(resourceGroup().id, operatorIdentity.id, readerRoleId)", "readerRoleId"),
                    "operatorSendsUsageControl": ("usageControlHub", "guid(usageControlHub.id, operatorIdentity.id, eventHubsDataSenderRoleId)", "eventHubsDataSenderRoleId"),
                    "operatorSendsCasesControl": ("casesControlHub", "guid(casesControlHub.id, operatorIdentity.id, eventHubsDataSenderRoleId)", "eventHubsDataSenderRoleId")}
        for name, (scope, assignment_name, role) in expected.items():
            block = blocks[name]
            self.assertIn(f"  scope: {scope}\n", block, name)
            self.assertIn(f"  name: {assignment_name}\n", block, name)
            self.assertIn(f"roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', {role})", block, name)
            self.assertIn("principalId: operatorIdentity.properties.principalId", block, name)
            self.assertIn("principalType: 'ServicePrincipal'", block, name)
        for wider in ("scope: eventHubs", "scope: subscription", "scope: tenant", "scope: managementGroup", "scope: usageHub", "scope: piiHub"):
            self.assertNotIn(wider, self.code, f"{wider}: the Operator may send to the two control hubs and nowhere else")

    def test_the_namespace_and_the_two_control_hubs_are_only_read_here_because_the_usage_recording_and_the_cases_make_them(self):
        self.assertEqual(len(re.findall(r"Microsoft\.EventHub", self.code)), 3)
        self.assertRegex(self.code, r"(?m)^resource eventHubs 'Microsoft\.EventHub/namespaces@[^']+' existing = \{\n  name: eventHubNamespaceName\n\}$")
        for symbol, name in (("usageControlHub", "usageControlHubName"), ("casesControlHub", "casesControlHubName")):
            self.assertRegex(self.code, rf"(?m)^resource {symbol} 'Microsoft\.EventHub/namespaces/eventhubs@[^']+' existing = \{{\n  parent: eventHubs\n  name: {name}\n\}}$")
        for word in ("consumergroups", "authorizationRules", "publicNetworkAccess", "disableLocalAuth", "eventHubs.properties", "ControlHub.properties"):
            self.assertNotIn(word, self.code, f"{word}: nothing of the namespace or the hubs is written or read here")

    def test_the_names_of_the_hubs_are_the_ones_that_the_usage_recording_and_the_first_cases_give_them(self):
        # A hub that is renamed in the template that makes it must be renamed here too: the role of the Operator is on the hub by its name, and a template that reads a hub that is not there fails.
        self.assertIn("var usageControlHubName = 'usage-control'", self.code)
        self.assertIn("var casesControlHubName = 'cases-control'", self.code)
        self.assertIn("var controlHubName = 'usage-control'", text("environment/recording/main.bicep"))
        self.assertIn("var controlHubName = 'cases-control'", text("environment/cases/main.bicep"))
        self.assertEqual(sorted(re.findall(r"CONTROL_HUB = \"([a-z-]+)\"", text("tools/recording-check.py") + text("tools/cases-check.py"))), ["cases-control", "usage-control"],
                         "and the tools send to the hubs of the same names")

    def test_it_outputs_the_ids_that_the_workflow_and_the_container_need_and_nothing_secret(self):
        outputs = re.findall(r"(?m)^output (\w+) string = (.+)$", self.code)
        self.assertEqual([name for name, _ in outputs], ["identityId", "identityPrincipalId", "identityClientId", "subnetId"])

    def test_every_parameter_says_what_it_is_and_the_text_ones_are_bounded(self):
        for match in re.finditer(r"(?m)^((?:@\w+\([^\n]*\)\n)+)param (\w+) (\w+)", self.code):
            self.assertIn("@description(", match.group(1), match.group(2))
        for name in ("owner", "opsSubnetPrefix", "eventHubNamespaceName"):
            self.assertRegex(self.code, rf"(?m)^@minLength\(\d+\)\n(?:@maxLength\(\d+\)\n)?param {name} string$")
        self.assertRegex(self.code, r"(?m)^@minLength\(9\)\n@maxLength\(18\)\nparam opsSubnetPrefix string$")
        self.assertRegex(self.code, r"(?m)^@minLength\(6\)\n@maxLength\(50\)\nparam eventHubNamespaceName string$", "the limits of an Event Hubs namespace's name, as in the usage recording's template")

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


CLIENT_ID = "11111111-2222-3333-4444-555555555555"
JWT_OF_A_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJvaWQiOiIxMTExMTExMS0yMjIyLTMzMzMtNDQ0NC01NTU1NTU1NTU1NTUifQ.c2lnbmF0dXJlLXNpZ25hdHVyZS1zaWduYXR1cmU"
BEARER_OF_A_TOKEN = "Bearer Zm9vYmFyYmF6cXV4MDEyMzQ1Njc4OWFiY2RlZg"

# Stand-ins for what operator/run-tool.sh calls. Every call of az, python3 and sleep is written to FAKE_LOG, so that a test sees what was called and in what order.
STUB_AZ_FOR_TOOLS = """#!/bin/bash
# stand-in for az: FAKE_AZ_LOGIN is ok, fail or twice (it fails twice and then works); FAKE_AZ_ACCOUNT is ok or fail
echo "az $*" >> "$FAKE_LOG"
if [ "$1" = login ]; then
  case "${FAKE_AZ_LOGIN:-ok}" in
    ok) exit 0 ;;
    twice) if [ "$(grep -c '^az login' "$FAKE_LOG")" -ge 3 ]; then exit 0; fi ;;
  esac
  echo "ERROR: Failed to connect to MSI 11111111-2222-3333-4444-555555555555 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa $GITHUB_TOKEN" >&2
  echo "second line that must not show" >&2
  exit 1
fi
if [ "$1" = account ] && [ "$2" = set ]; then
  if [ "${FAKE_AZ_ACCOUNT:-ok}" = ok ]; then exit 0; fi
  echo "ERROR: The subscription of '$4' doesn't exist." >&2
  exit 1
fi
echo "unexpected az call" >&2
exit 9
"""

STUB_PYTHON_FOR_TOOLS = """#!/bin/bash
# stand-in for python3: -c asks for the version (FAKE_PYTHON_VERSION, or fails when it is "broken"); anything else is the tool, which logs its arguments, prints FAKE_TOOL_OUTPUT
# (NOTHING means no line) and FAKE_TOOL_ERROR on standard error, and exits with FAKE_TOOL_EXIT
if [ "$1" = -c ]; then
  if [ "${FAKE_PYTHON_VERSION:-3.12.7}" = broken ]; then exit 1; fi
  echo "${FAKE_PYTHON_VERSION:-3.12.7}"
  exit 0
fi
{ printf 'tool-argv:'; for argument in "$@"; do printf ' [%s]' "$argument"; done; printf '\\n'; } >> "$FAKE_LOG"
output="${FAKE_TOOL_OUTPUT:-tool output\\n}"
if [ "$output" != NOTHING ]; then printf '%b' "$output"; fi
printf '%b' "${FAKE_TOOL_ERROR:-}" >&2
exit "${FAKE_TOOL_EXIT:-0}"
"""

STUB_SLEEP = """#!/bin/bash
echo "sleep $*" >> "$FAKE_LOG"
"""


class Ran:
    """What one run of operator/run-tool.sh did: the process, its lines, the calls that the stand-ins logged, and the volume that it was given."""

    def __init__(self, done, calls, volume, tmp):
        self.done, self.lines, self.calls, self.volume, self.tmp = done, done.stdout.splitlines(), calls, volume, tmp

    @property
    def tool_calls(self):
        return [call for call in self.calls if call.startswith("tool-argv:")]


class ScriptRunner:
    """Runs operator/run-tool.sh with bash, with the stand-ins first on the path of the script, and says what it did."""

    def run_tool(self, env=None, stubs=None, tool="recording-check", files=None, contents=None):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            for name, body in {"az": STUB_AZ_FOR_TOOLS, "python3": STUB_PYTHON_FOR_TOOLS, "timeout": STUB_TIMEOUT, "sleep": STUB_SLEEP, **(stubs or {})}.items():
                (bin_dir / name).write_text(body, encoding="utf-8", newline="\n")
                (bin_dir / name).chmod(0o755)  # on Linux a file that is not executable is skipped in the search of the path, and the real program would answer
            volume = tmp / "op"
            volume.mkdir()
            for name in ([f"{tool}.py"] if files is None else files):
                (volume / name).write_bytes((contents or {}).get(name, b"# the tool\n"))
            log = tmp / "log.txt"
            log.write_text("", encoding="utf-8")
            script = tmp / "run-tool.sh"
            script.write_text(text("operator/run-tool.sh"), encoding="utf-8", newline="\n")
            environment = {**os.environ, "STUBS": posix(bin_dir), "TOOL_VOLUME": posix(volume), "FAKE_LOG": posix(log), "OPERATOR_CLIENT_ID": CLIENT_ID, "TOOL_NAME": tool,
                           "TOOL_ARGS": "run --namespace evhns-example --job all --minutes 20", "GITHUB_TOKEN": TOKEN_OF_THE_RUN, **(env or {})}
            for name in [name for name, value in environment.items() if value is None]:
                del environment[name]
            done = subprocess.run([BASH, "-c", 'PATH="$STUBS:$PATH"; export PATH; exec bash "$0"', posix(script)], capture_output=True, text=True, env=environment, cwd=tmp)
            return Ran(done, log.read_text(encoding="utf-8").splitlines(), posix(volume), tmp)


@unittest.skipIf(BASH is None, "no bash on this machine")
class RunToolScript(ScriptRunner, unittest.TestCase):
    """operator/run-tool.sh against stand-ins for az, python3, timeout and sleep: what it refuses, what it runs, what it prints, and that the exit code is the tool's."""

    def test_a_good_run_signs_in_runs_the_tool_with_its_arguments_as_separate_words_and_ends_with_the_exit_code(self):
        ran = self.run_tool()
        self.assertEqual((ran.done.returncode, ran.done.stderr), (0, ""))
        self.assertEqual(ran.lines, ["ok: python3 3.12.7", "ok: az login --identity", "ok: running recording-check.py run", "tool output", "run-tool-done: exit code 0"])
        self.assertEqual(ran.calls, [f"az login --identity --client-id {CLIENT_ID} --allow-no-subscriptions --output none",
                                     f"tool-argv: [{ran.volume}/recording-check.py] [run] [--namespace] [evhns-example] [--job] [all] [--minutes] [20]",
                                     "sleep 20"], "the sign-in, the tool, and the hold that lets the log be read whole")

    def test_the_exit_code_of_the_tool_is_the_exit_code_of_the_container_and_the_log_is_still_held_open(self):
        for code in (1, 2, 7, 124):
            ran = self.run_tool({"FAKE_TOOL_EXIT": str(code), "FAKE_TOOL_OUTPUT": "the verdict\\n"})
            self.assertEqual(ran.done.returncode, code, code)
            self.assertEqual(ran.lines[-2:], ["the verdict", f"run-tool-done: exit code {code}"])
            self.assertEqual(ran.calls[-1], "sleep 20", "a failed tool's lines are read whole too")

    def test_the_lines_of_the_tool_come_in_the_order_it_wrote_them_standard_error_included(self):
        ran = self.run_tool({"FAKE_TOOL_OUTPUT": "first\\nsecond\\n", "FAKE_TOOL_ERROR": "error: third\\n", "FAKE_TOOL_EXIT": "1"})
        self.assertEqual(ran.lines[3:], ["first", "second", "error: third", "run-tool-done: exit code 1"])

    def test_the_hold_is_the_one_that_is_asked_for_after_the_tool_and_none_at_zero(self):
        ran = self.run_tool({"TOOL_HOLD_SECONDS": "7"})
        self.assertEqual(len(ran.calls), 3)
        self.assertEqual(ran.calls[-1], "sleep 7", "the hold comes after the tool")
        self.assertTrue(ran.calls[1].startswith("tool-argv:"))
        ran = self.run_tool({"TOOL_HOLD_SECONDS": "0"})
        self.assertEqual([call for call in ran.calls if call.startswith("sleep")], [])
        self.assertEqual(ran.done.returncode, 0)
        ran = self.run_tool({"TOOL_HOLD_SECONDS": "60"})
        self.assertIn("sleep 60", ran.calls)

    def test_a_string_that_looks_like_a_token_is_hidden_in_what_the_tool_prints_and_the_rest_is_not(self):
        output = f"The token was {JWT_OF_A_TOKEN} and the header Authorization: {BEARER_OF_A_TOKEN} stays out.\\nRequest 0123456789abcdef0123456789abcdef: /subscriptions/x/resourceGroups/rg-a/providers/Microsoft.Insights/components/appi-b\\n"
        ran = self.run_tool({"FAKE_TOOL_OUTPUT": output})
        self.assertEqual(ran.lines[3], "The token was <token hidden> and the header Authorization: Bearer <token hidden> stays out.")
        self.assertEqual(ran.lines[4], "Request 0123456789abcdef0123456789abcdef: /subscriptions/x/resourceGroups/rg-a/providers/Microsoft.Insights/components/appi-b", "ids and names are not hidden")
        for secret in (JWT_OF_A_TOKEN, BEARER_OF_A_TOKEN.split()[1], JWT_OF_A_TOKEN.split(".")[1], TOKEN_OF_THE_RUN):
            self.assertNotIn(secret, ran.done.stdout + ran.done.stderr)

    def test_a_tool_that_prints_nothing_gives_the_own_lines_only_and_a_long_line_passes_whole(self):
        ran = self.run_tool({"FAKE_TOOL_OUTPUT": "NOTHING"})
        self.assertEqual(ran.lines, ["ok: python3 3.12.7", "ok: az login --identity", "ok: running recording-check.py run", "run-tool-done: exit code 0"])
        long_line = "result " + "x" * 3000
        self.assertEqual(self.run_tool({"FAKE_TOOL_OUTPUT": long_line + "\\n"}).lines[3], long_line)

    def test_a_sign_in_that_fails_is_tried_three_times_ten_seconds_apart_and_then_stops_the_run_without_the_tool(self):
        ran = self.run_tool({"FAKE_AZ_LOGIN": "fail"})
        self.assertEqual(ran.done.returncode, 3)
        self.assertEqual(ran.lines, ["ok: python3 3.12.7", "FAIL: az login --identity: ERROR: Failed to connect to MSI <id> <hidden> <hidden>", "run-tool-done: exit code 3"])
        logins = [call for call in ran.calls if call.startswith("az login")]
        self.assertEqual(len(logins), 3)
        self.assertEqual([call for call in ran.calls if call.startswith("sleep")], ["sleep 10", "sleep 10"], "a pause between the tries and none after the last one")
        self.assertEqual(ran.tool_calls, [])
        self.assertNotIn("second line that must not show", ran.done.stdout)
        self.assertNotIn(TOKEN_OF_THE_RUN, ran.done.stdout + ran.done.stderr)

    def test_a_sign_in_that_works_at_the_third_try_goes_on_to_the_tool(self):
        ran = self.run_tool({"FAKE_AZ_LOGIN": "twice"})
        self.assertEqual(ran.done.returncode, 0)
        self.assertEqual(len([call for call in ran.calls if call.startswith("az login")]), 3)
        self.assertEqual(len(ran.tool_calls), 1)
        self.assertIn("ok: az login --identity", ran.lines)

    def test_the_tool_is_never_run_twice_whatever_it_says(self):
        for code in ("0", "1", "3"):
            self.assertEqual(len(self.run_tool({"FAKE_TOOL_EXIT": code}).tool_calls), 1, "a tool that sends an event is not tried again: the event may have arrived")

    def test_the_subscription_is_made_the_default_only_when_it_is_given(self):
        subscription = "22222222-3333-4444-5555-666666666666"
        ran = self.run_tool({"OPERATOR_SUBSCRIPTION": subscription})
        self.assertEqual(ran.done.returncode, 0)
        self.assertIn(f"az account set --subscription {subscription}", ran.calls)
        self.assertLess(ran.calls.index(f"az account set --subscription {subscription}"), ran.calls.index(ran.tool_calls[0]))
        self.assertIn("ok: az account set", ran.lines)
        self.assertEqual([call for call in self.run_tool().calls if call.startswith("az account")], [])
        ran = self.run_tool({"OPERATOR_SUBSCRIPTION": subscription, "FAKE_AZ_ACCOUNT": "fail"})
        self.assertEqual(ran.done.returncode, 3)
        self.assertIn("FAIL: az account set: ERROR: The subscription of '<id>' doesn't exist.", ran.lines)
        self.assertEqual(ran.tool_calls, [])

    def test_the_tool_that_is_named_is_the_tool_that_runs(self):
        for name in ("recording-check", "cases-check"):
            ran = self.run_tool(tool=name, files=["cases-check.py", "recording-check.py"], env={"TOOL_NAME": name})
            self.assertEqual(ran.tool_calls[0].split(" ")[1], f"[{ran.volume}/{name}.py]")
            self.assertIn(f"ok: running {name}.py run", ran.lines)

    def refused(self, env=None, **kwargs):
        ran = self.run_tool(env, **kwargs)
        self.assertEqual(ran.done.returncode, 2, (env, ran.lines))
        self.assertEqual(len(ran.lines), 2, ran.lines)
        self.assertRegex(ran.lines[0], r"^FAIL: ")
        self.assertEqual(ran.lines[1], "run-tool-done: exit code 2")
        self.assertEqual(ran.calls, [], "nothing runs after a refusal: no sign-in, no tool, no hold")
        self.assertFalse((ran.tmp / "canary").exists(), "nothing of the input was run as a command")
        return ran

    def test_an_identity_that_is_not_a_client_id_is_refused(self):
        for value in (None, "", "not-a-guid", "11111111-2222-3333-4444-55555555555", "11111111-2222-3333-4444-5555555555555", f"{CLIENT_ID}; touch canary", f"{CLIENT_ID}\n", f"x{CLIENT_ID}",
                      "$(touch canary)"):
            self.refused({"OPERATOR_CLIENT_ID": value})
        self.assertIn("OPERATOR_CLIENT_ID", self.refused({"OPERATOR_CLIENT_ID": "nope"}).lines[0])

    def test_a_subscription_that_is_not_an_id_is_refused_and_an_empty_one_is_none(self):
        for value in ("sub", "22222222-3333-4444-5555-66666666666", "22222222-3333-4444-5555-666666666666 --x", "$(touch canary)"):
            self.refused({"OPERATOR_SUBSCRIPTION": value})
        self.assertEqual(self.run_tool({"OPERATOR_SUBSCRIPTION": ""}).done.returncode, 0)

    def test_a_tool_name_that_is_not_a_plain_name_or_not_in_the_volume_is_refused(self):
        for value in (None, "", "../recording-check", "recording-check.py", "Recording-check", "recording check", "recording-check;touch canary", "recording_check", "1recording", "-recording",
                      "a" * 41, "recording-check\n", "$(touch canary)", "recording-check/x", "/etc/passwd"):
            self.refused({"TOOL_NAME": value}, files=["recording-check.py"])
        ran = self.refused({"TOOL_NAME": "cases-check"}, files=["recording-check.py"])
        self.assertIn("cases-check.py is not in the secret volume", ran.lines[0])
        self.refused({"TOOL_NAME": "recording-check"}, files=[])

    def test_arguments_that_are_empty_too_long_or_hold_anything_but_plain_characters_are_refused_without_being_printed_back(self):
        for value in (None, "", "   ", "r" * 601, "run " + "a" * 600):
            self.refused({"TOOL_ARGS": value})
        for character in ";&|$()`\"'<>*?!\\{}[]~#%,@+\n\t\r":
            ran = self.refused({"TOOL_ARGS": f"run --namespace a{character}b touch canary"})
            self.assertNotIn("touch", ran.done.stdout, repr(character))
        for value in ("run --namespace $(touch canary)", "run; touch canary", "run `touch canary`", "run --x=${HOME}", "run --x=a b\ntouch canary", "run --x=é", "run --x=*", "run --x=?"):
            ran = self.refused({"TOOL_ARGS": value})
            self.assertNotIn(value, ran.done.stdout)

    def test_arguments_must_start_with_the_command_of_the_tool(self):
        for value in ("--run", "Run", "1run", "-x run", "run1", "/run", "run" + "n" * 20 + " x", ".run"):
            self.refused({"TOOL_ARGS": value})
        self.assertEqual(self.run_tool({"TOOL_ARGS": "functions --site /a/b --minutes 5"}).done.returncode, 0)

    def test_a_hold_that_is_not_a_number_from_0_to_60_is_refused_and_an_empty_one_is_the_default(self):
        for value in ("abc", "-1", "61", "100", "1.5", "1 2", "$(touch canary)", "007x"):
            self.refused({"TOOL_HOLD_SECONDS": value})
        ran = self.run_tool({"TOOL_HOLD_SECONDS": ""})
        self.assertIn("sleep 20", ran.calls)
        self.assertEqual(self.run_tool({"TOOL_HOLD_SECONDS": "05"}).done.returncode, 0)

    def test_the_arguments_that_pass_reach_the_tool_as_the_words_they_are_and_nothing_is_expanded(self):
        value = "run --namespace evhns-example.servicebus.windows.net --insights /subscriptions/sub-id/resourceGroups/rg_a.b/providers/Microsoft.Insights/components/appi-x --job all --minutes=20 --a:b -- -"
        ran = self.run_tool({"TOOL_ARGS": value})
        self.assertEqual(ran.done.returncode, 0)
        words = " ".join(f"[{word}]" for word in value.split())
        self.assertEqual(ran.tool_calls, [f"tool-argv: [{ran.volume}/recording-check.py] {words}"])
        # extra spaces between words, and at the ends, are not words
        ran = self.run_tool({"TOOL_ARGS": "  run   --job  all "})
        self.assertEqual(ran.tool_calls, [f"tool-argv: [{ran.volume}/recording-check.py] [run] [--job] [all]"])

    def test_a_python_that_does_not_run_stops_the_run_with_3_and_the_tool_is_not_called(self):
        ran = self.run_tool({"FAKE_PYTHON_VERSION": "broken"})
        self.assertEqual(ran.done.returncode, 3)
        self.assertEqual(ran.lines, ["FAIL: python3 does not run", "run-tool-done: exit code 3"])
        self.assertEqual(ran.tool_calls, [])

    def test_every_line_of_its_own_is_short_and_starts_with_ok_or_fail(self):
        for ran in (self.run_tool(), self.run_tool({"FAKE_AZ_LOGIN": "fail"}), self.run_tool({"TOOL_ARGS": "x;"}), self.run_tool({"TOOL_NAME": "a" * 200})):
            for line in ran.lines:
                if line.startswith("run-tool-done: ") or line == "tool output":
                    continue
                self.assertRegex(line, r"^(ok|FAIL): ", line)
                self.assertLessEqual(len(line), 130, line)

    def test_it_runs_with_nothing_set_and_still_ends_well(self):
        ran = self.run_tool({"OPERATOR_CLIENT_ID": None, "TOOL_NAME": None, "TOOL_ARGS": None, "TOOL_VOLUME": None, "TOOL_HOLD_SECONDS": None})
        self.assertEqual(ran.done.returncode, 2)
        self.assertEqual(ran.done.stderr, "")
        self.assertEqual(ran.lines[-1], "run-tool-done: exit code 2")

    def test_the_script_names_only_what_it_may_read_from_the_environment(self):
        source = text("operator/run-tool.sh")
        used = set(re.findall(r"\$\{?(OPERATOR_\w+|TOOL_\w+|FAKE_\w+|GITHUB_\w+)", source))
        self.assertEqual(used, {"OPERATOR_CLIENT_ID", "OPERATOR_SUBSCRIPTION", "TOOL_NAME", "TOOL_ARGS", "TOOL_HOLD_SECONDS", "TOOL_VOLUME"})

    def test_the_script_evaluates_nothing_and_does_not_glob_and_uses_no_program_that_the_image_may_lack(self):
        source = re.sub(r"(?m)^\s*#.*$", "", text("operator/run-tool.sh"))
        for word in (r"\beval\b", r"\bsource\b", r"(?m)^\s*\. ", r"\bbash -c\b", r"\bsh -c\b", r"\bxargs\b", r"\bawk\b", r"\bjq\b", r"\bgawk\b", r"\bnslookup\b", r"\bdig\b", r"\bping\b", r"\bcurl\b",
                     r"\bpython3? -c .*\$", r"`"):
            self.assertNotRegex(source, word, word)
        self.assertIn("\nset -f\n", source, "no globbing")
        self.assertIn("\nset -u\n", source)
        self.assertEqual(source.count('"${words[@]}"'), 1, "the words are handed over as separate arguments, quoted")
        self.assertIn("IFS=' ' read -r -a words <<< \"$args\"", source)

    def test_the_script_is_valid_bash(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "run-tool.sh"
            script.write_text(text("operator/run-tool.sh"), encoding="utf-8", newline="\n")
            done = subprocess.run([BASH, "-n", posix(script)], capture_output=True, text=True)
        self.assertEqual((done.returncode, done.stderr), (0, ""))

    def test_the_script_has_no_key_and_prints_no_variable_of_its_environment(self):
        source = re.sub(r"(?m)^\s*#.*$", "", text("operator/run-tool.sh"))
        for word in ("listKeys", "listSecrets", "AccountKey", "SharedAccessKey", "primaryKey", "--password", "--secret", "get-access-token"):
            self.assertNotIn(word, source, word)
        for line in source.splitlines():
            if re.match(r"\s*(say|printf|echo)\b", line):
                self.assertNotRegex(line, r"\$\{?(OPERATOR_CLIENT_ID|OPERATOR_SUBSCRIPTION|TOOL_ARGS|args|GITHUB_\w+)\b", f"a value of the input is never printed: {line.strip()}")


def real_python():
    """The python3 of the image, here the Python that runs the tests. On Windows, Git's bash gets the script as a Windows path and no argument of the tool is converted."""
    return f"""#!/bin/bash
export MSYS_NO_PATHCONV=1
if [ "$1" = -c ]; then exec "{posix(sys.executable)}" "$@"; fi
script=$1
shift
if command -v cygpath > /dev/null 2>&1; then script=$(cygpath -w "$script"); fi
exec "{posix(sys.executable)}" "$script" "$@"
"""


@unittest.skipIf(BASH is None, "no bash on this machine")
class RunToolWithTheRealTools(ScriptRunner, unittest.TestCase):
    """operator/run-tool.sh with the real tools of tools/ in the volume and the real Python: the chain of a check, up to the exit code, as far as it goes without Azure. A tool that asked az for a
    token would call the program of AZ, which is a path that does not exist here: these tests stop before that, and nothing can reach a real Azure CLI."""

    SITE_ERROR = "error: --site is the resource id of the function app (a Microsoft.Web/sites resource)"

    def run_real(self, tool, args, files, **extra):
        contents = {name: (ROOT / "tools" / name).read_bytes() for name in files}
        return self.run_tool({"TOOL_NAME": tool, "TOOL_ARGS": args, "AZ": "/nonexistent/az-that-must-not-be-called", **extra}, stubs={"python3": real_python()}, tool=tool, files=files,
                             contents=contents)

    def test_the_real_tool_runs_from_the_volume_with_the_real_python_and_its_exit_code_and_error_line_come_out(self):
        ran = self.run_real("recording-check", "functions --site not-an-id", ["recording-check.py"])
        self.assertEqual(ran.done.returncode, 1, ran.done.stdout)
        version = "%d.%d.%d" % sys.version_info[:3]
        self.assertEqual(ran.lines, [f"ok: python3 {version}", "ok: az login --identity", "ok: running recording-check.py functions", self.SITE_ERROR, "run-tool-done: exit code 1"])
        self.assertEqual(ran.calls, [f"az login --identity --client-id {CLIENT_ID} --allow-no-subscriptions --output none", "sleep 20"], "the sign-in, nothing asked of Azure, and the hold")

    def test_the_cases_check_finds_the_recording_check_in_the_same_folder_and_needs_it(self):
        ran = self.run_real("cases-check", "functions --site not-an-id", ["cases-check.py", "recording-check.py"])
        self.assertEqual(ran.done.returncode, 1)
        self.assertEqual(ran.lines[3:], [self.SITE_ERROR, "run-tool-done: exit code 1"], "the cases check ran, loaded the recording check and refused the site")
        ran = self.run_real("cases-check", "functions --site not-an-id", ["cases-check.py"])
        self.assertEqual(ran.done.returncode, 1)
        self.assertIn("recording-check.py", "\n".join(ran.lines), "without the recording check beside it the cases check stops at its import, and the log says which file is missing")
        self.assertEqual(ran.lines[-1], "run-tool-done: exit code 1")
        self.assertNotIn(self.SITE_ERROR, ran.lines)

    def test_a_tool_that_would_start_a_job_refuses_until_the_container_is_told_that_it_is_in_a_github_actions_run(self):
        insights = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.Insights/components/appi-example"
        args = f"run --namespace evhns-example --insights {insights} --job all --minutes 1"
        for tool, files, arguments in (("recording-check", ["recording-check.py"], args), ("cases-check", ["cases-check.py", "recording-check.py"], args.replace(" --job all", ""))):
            ran = self.run_real(tool, arguments, files, GITHUB_ACTIONS=None)
            self.assertEqual(ran.done.returncode, 1, tool)
            self.assertIn("error: this command starts a job that writes to Azure, and only a GitHub Actions run may do that (AGENTS.md rule 18)", ran.lines, tool)
            self.assertEqual([call for call in ran.calls if call.startswith("az account")], [], "nothing was asked of Azure: the refusal comes first")


class TheToolsInTheContainer(unittest.TestCase):
    """The tools that the Operator runs are the very files of tools/, and they run in the image's Python 3.12 and from a folder that holds only the files that are sent."""

    TOOLS = ("recording-check.py", "cases-check.py")

    def test_both_parse_as_python_3_12_and_import_the_standard_library_only(self):
        # CI and the function app use Python 3.13, the image of the Operator has 3.12: a syntax of 3.13 would pass every test here and fail in the container.
        import ast
        for name in self.TOOLS:
            tree = ast.parse(text(f"tools/{name}"), feature_version=(3, 12))
            imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
            imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
            self.assertLessEqual(imported, set(sys.stdlib_module_names), f"{name}: {sorted(imported - set(sys.stdlib_module_names))}")

    def test_the_tools_run_from_a_folder_that_holds_only_them_like_the_secret_volume_and_the_cases_check_needs_the_recording_check_beside_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            volume = Path(tmp)
            for name in self.TOOLS:
                (volume / name).write_bytes((ROOT / "tools" / name).read_bytes())
            for name in self.TOOLS:
                done = subprocess.run([sys.executable, "-B", str(volume / name), "run", "--help"], capture_output=True, text=True, cwd=volume)
                self.assertEqual((done.returncode, done.stderr), (0, ""), name)
                self.assertIn("--namespace", done.stdout, name)
            self.assertEqual(sorted(path.name for path in volume.iterdir()), sorted(self.TOOLS), "nothing was written to the folder: no bytecode, no cache")
            (volume / "recording-check.py").unlink()
            done = subprocess.run([sys.executable, "-B", str(volume / "cases-check.py"), "run", "--help"], capture_output=True, text=True, cwd=volume)
            self.assertNotEqual(done.returncode, 0, "cases-check.py loads recording-check.py from its own folder, so both are sent")
            self.assertIn("recording-check.py", done.stderr)

    def test_the_tools_refuse_to_send_outside_a_github_actions_run_which_the_container_is_told_it_is_in(self):
        # The Operator's group is made only by a run of the Hub workflow (operator-run.py refuses anywhere else), so the workflow tells the container so with GITHUB_ACTIONS=true.
        with tempfile.TemporaryDirectory() as tmp:
            for name in self.TOOLS:
                (Path(tmp) / name).write_bytes((ROOT / "tools" / name).read_bytes())
            insights = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.Insights/components/appi-example"
            for name in self.TOOLS:
                environment = {key: value for key, value in os.environ.items() if key != "GITHUB_ACTIONS"}
                done = subprocess.run([sys.executable, "-B", str(Path(tmp) / name), "run", "--namespace", "evhns-example", "--insights", insights], capture_output=True, text=True, env=environment,
                                      cwd=tmp)
                self.assertEqual(done.returncode, 1, name)
                self.assertIn("only a GitHub Actions run may do that", done.stderr, name)


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

    def test_it_says_what_the_probe_proved_and_no_longer_says_that_nothing_has_run(self):
        self.assertIn("## What the probe proved on 2026-11-06", self.page)
        section = self.page.split("## What the probe proved on 2026-11-06")[1].split("\n## ")[0]
        for words in ("ran twice on the real estate and every check passed both times", "`az login --identity` and `az group show`", "resolve to private addresses", "`api.applicationinsights.io` and `api.loganalytics.io`",
                      "A file of 400,000 bytes arrived intact", "about one to two minutes", "neither of the two fallbacks", "What is still open: publishing code to the private deployment sites",
                      "the telemetry read once Application Insights is private", "the check of the console's front door"):
            self.assertIn(words, section, words)
        status = self.page.split("\n")[2]
        self.assertTrue(status.startswith("**Status: decided on 2026-11-06"), status[:80])
        self.assertNotIn("None of it has run on the real estate", self.page)
        self.assertNotIn("proposed on 2026-11-06", status)

    def test_it_says_how_the_checks_run_in_the_operator_what_reader_covers_and_that_the_data_plane_query_is_the_next_step_and_not_built(self):
        heading = "## The checks of the usage recording and the first cases run in the Operator"
        self.assertIn(heading, self.page)
        section = self.page.split(heading)[1].split("\n## ")[0]
        for words in ("[`operator/run-tool.sh`](../../operator/run-tool.sh)", "arguments made of letters, digits and `. / : _ = -` only", "nothing is evaluated or expanded", "three tries", "It never runs the tool twice",
                      "`GITHUB_ACTIONS=true`", "the two tools, about 33 KB", "`tools/cases-check.py` loads `tools/recording-check.py` from its own folder, so both files are sent for `cases-run`",
                      "The tools have no new option and no new behaviour", "parses both tools as 3.12",
                      "`Microsoft.Insights/Components/Query/Read`", "the built-in Reader role includes `*/read` for the control plane", "The Operator holds Reader on the project's resource group already, so the read needs no new role",
                      "That the endpoint is authorised by that operation is (inferred)",
                      "\"can't use Azure Monitor private links\"", "the query of the tools stops working", "`https://api.applicationinsights.io/v1/apps/<appId>/query`", "a Microsoft Entra token for that resource",
                      "That is the next step, and it is not built here.", "is still made from the runner through Azure Resource Manager",
                      "1,500 seconds for `recording-check`", "2,400 seconds for `cases-run`", "`op-check-<run id>`", "A stopped container keeps only the last 16 KB of its log", "the script stays 20 seconds"):
            self.assertIn(words, section, words)

    def test_it_lists_the_two_roles_of_the_checks_the_order_of_the_work_and_what_is_not_checked_yet(self):
        roles = self.page.split("| Role | Where | What the Operator does with it | Added with |")[1].split("\n\n")[0]
        self.assertIn("| Azure Event Hubs Data Sender | The two control hubs, `usage-control` and `cases-control`, one role on each hub |", roles)
        self.assertIn("| Reader | The project's resource group |", roles)
        self.assertIn("Azure Event Hubs Data Sender was in it already", self.page, "the role needs no hand step")
        self.assertIn("inside rule 29", self.page)
        order = self.page.split("## The order of the work")[1].split("\n## ")[0]
        for words in ("**The Operator and the probe** (done).", "**The checks run in the Operator** (built in the change before this one; not yet run when this page was written", "The order on an estate is `recording`, `cases`, `operator`",
                      "about ten minutes are waited for them to apply", "Step 4 is not run before both have passed.", "**Event Hubs private** (this change: built, not yet deployed).",
                      "it is a change of its own if it asks for one"):
            self.assertIn(words, order, words)
        not_checked = self.page.split("## Not checked")[1].split("\n## ")[0]
        for words in ("it did not make a connection to a private endpoint", "the token of the Operator's identity for `https://eventhubs.azure.net`", "Whether Python 3.12 of the image runs the two tools",
                      "has 3.13 only", "Whether the hold of 20 seconds"):
            self.assertIn(words, not_checked, words)
        for source in ("permissions/monitor#microsoftinsights", "azure-ad-authentication#query-application-insights-by-using-microsoft-entra-authentication", "built-in-roles/general#reader"):
            self.assertIn(source, self.page.split("## Sources")[1], source)


class EventHubsPrivateOnlyRecord(unittest.TestCase):
    """The decision record and the bootstrap page on the change that makes the Event Hubs namespace private-only and retires the deploy identity's right to send to the control hubs."""

    HEADING = "## Event Hubs private-only (built, not yet deployed)"

    def setUp(self):
        self.page = text("docs/proposals/07-private-by-default.md")
        self.section = self.page.split(self.HEADING)[1].split("\n## ")[0]
        self.bootstrap = text("environment/BOOTSTRAP.md")
        self.bootstrap_section = self.bootstrap.split("## Changed on 2026-11-06: the Event Hubs namespace is private")[1].split("\n## ")[0]

    def test_the_status_the_table_and_the_order_say_that_it_is_built_and_not_deployed_and_that_nothing_is_private_yet(self):
        status = self.page.split("\n")[2]
        self.assertIn("The Event Hubs namespace is private-only in the templates and the workflow, and the deploy identity's right to send to the two control hubs is retired by the actions that deploy them "
                      "([built, not yet deployed](#event-hubs-private-only-built-not-yet-deployed)). Nothing is private yet.", status)
        row = [line for line in self.page.split("\n") if line.startswith("| Event Hubs namespace |")][0]
        self.assertIn("**Enabled** on the real estate until the action `recording` is run with the template of this change, which sets it to **Disabled**", row)
        order = self.page.split("## The order of the work")[1].split("\n## ")[0]
        self.assertIn("4. **Event Hubs private** (this change: built, not yet deployed).", order)
        self.assertIn("Step 4 is not run before both have passed.", order)
        self.assertNotIn("(inferred from what the setting means)", self.page, "Learn says what the setting does, and the row cites it")
        self.assertIn("Disable public access to your Event Hubs namespace to allow access only via private endpoints", self.page)

    def test_it_says_what_changes_in_the_template_the_roles_the_workflow_and_the_read_back(self):
        for words in ("sets the namespace's public network access to Disabled and keeps local authentication off and TLS 1.2", "It adds no network rule set and no trusted-service exception: nothing needs one.",
                      "no longer give the deploy identity Azure Event Hubs Data Sender on the control hub, and the parameter that fed that role is gone from both templates and from the parameter builder",
                      "The roles of the gateway (on the two usage hubs), of the two apps (receive, on their hubs) and of the Operator (send, on the two control hubs) are as they were, and a test pins each.",
                      "A template never deletes an assignment that it stops declaring, so each of the two actions has one idempotent step, after its deploy, that retires the assignment that exists.",
                      "deletes the one that is Data Sender by its id, reads back that it is gone, and says what it did", "It does nothing on a new estate (no hub yet, or no assignment), and it touches no other assignment.",
                      "lists Data Sender for a delete as well as for a write, so no hand step is needed; if Azure refuses, the step stops with Azure's message and says that a person deletes that one assignment",
                      "The action `recording` reads the namespace back from Azure after its deploy and fails unless public network access is Disabled, local authentication is off and its private endpoint connection is Approved"):
            self.assertIn(words, self.section, words)

    def test_it_says_who_calls_the_namespace_afterwards_and_the_runner_is_not_one(self):
        table = self.section.split("**Who calls the namespace afterwards.**")[1].split("**The order**")[0]
        for words in ("| The usage app (three Event Hub triggers and the control hub's trigger) | Virtual network integration, private endpoint |", "| The cases app (the control hub's trigger) | The same | The same, and it runs on a Basic plan that is always on, so it has no wake from zero |",
                      "| The Operator's container groups | Inside the network, the private endpoint | The probe resolved the namespace's name to a private address and made no connection to it. The first check is the first send |",
                      "| The deployment workflow's runner | None | It sends nothing and reads nothing from the namespace; a test pins that no step of `recording-check` or `cases-run` does |",
                      "| The gateway (two loggers) | The private endpoint, over the peering | **Not known yet**:"):
            self.assertIn(words, table, words)

    def test_the_order_is_the_operator_the_checks_while_public_then_recording_then_cases_then_the_checks_again_and_the_way_back_is_a_revert(self):
        order = self.section.split("**The order**")[1].split("**The way back**")[0]
        positions = [order.index(words) for words in ("1. `operator`, if the Operator does not hold Data Sender on both control hubs yet, and about ten minutes of waiting.",
                                                      "2. `recording-check` and `cases-run`, through the Operator, **while the namespace is still public**.",
                                                      "3. `recording`: it deploys the template that makes the namespace private, reads the namespace back, and retires the deploy identity's right on `usage-control`. Then `cases`: it retires the right on `cases-control`.",
                                                      "4. `recording-check` and `cases-run` again, as the proof.", "5. The first call through the gateway that sends to the usage hubs, as the second proof")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("**The way back** is to revert this change and run `recording` and `cases`: the earlier templates set public access Enabled again and give the deploy identity its role again.", self.section)

    def test_the_gateway_question_is_not_known_yet_cites_learn_and_says_how_the_first_call_will_show_it(self):
        part = self.section.split("### Whether the gateway reaches the private namespace")[1].split("\n### ")[0]
        for words in ("**Not known yet.**", "\"Effective 15 March 2026, Azure API Management is retiring trusted service connectivity by the API Management gateway to supported Azure services\"",
                      "\"needs alternative ways to communicate and have network line-of-sight\"", "api-management/breaking-changes/trusted-service-connectivity-retirement-march-2026", "dated 2026-01-15, updated 2026-06-25, read on 2026-11-06",
                      "the gateway can reach it only through the private endpoint, over the peering and the hub", "was not read in the landing zone and has not been tried",
                      "no API policy includes the `ai-usage` fragment, and nothing has sent to the `ai-usage` and `pii-usage` hubs (a measurement of 2026-11-06 found no message in 14 hours)",
                      "**How the first gateway call will show it.**", "The namespace's metric `IncomingMessages` (Total, one-minute grain), split by the dimension `EntityName`, has a count for `ai-usage`",
                      "`EventHubSuccessfulEvents` rises when it works, and `EventHubTimedoutEvents`, `EventHubTotalFailedEvents`, `EventHubRejectedEvents` (wrong configuration or unauthorized) or `EventHubDroppedEvents` rise when it does not",
                      "**If there is no path**, a public endpoint is not an option under the rule", "the answer is read from the first call and not guessed"):
            self.assertIn(words, part, words)
        self.assertIn("**The gateway's path to the namespace**, only if the first call through the gateway shows that there is none", self.page.split("## Decisions for the owner")[1].split("\n## ")[0])

    def test_the_flex_question_quotes_learn_says_what_could_not_be_verified_and_names_the_proof(self):
        part = self.section.split("### Whether the usage app wakes from zero on a private namespace")[1]
        for words in ("\"The Flex Consumption plan natively supports virtual network triggers. Your function app can be triggered from event sources protected by a virtual network without requiring extra configuration for runtime scale monitoring\"",
                      "azure-functions/functions-networking-options", "dated 2026-09-15, updated 2026-10-16, read on 2026-11-06", "\"can connect to other Azure services secured inside a virtual network\"",
                      "azure-functions/flex-consumption-plan", "\"Private Event Hubs triggered function app\"", "**What could not be verified.**",
                      "wakes from zero on an event hub whose public network access is Disabled, through an identity-based connection (`EventHubConnection__fullyQualifiedNamespace`), which is this app. Nothing has run.",
                      "**The first `recording-check` after the flip is the proof**", "the check waits 20 minutes for the result", "If no result arrives while `IncomingMessages` of `usage-control` rises, the app did not wake.",
                      "an instance that is always ready for the control function (a standing price, to be taken from the Retail Prices API), or a plan that does not scale to zero"):
            self.assertIn(words, part, words)

    def test_the_not_checked_list_and_the_sources_say_what_was_read_and_what_was_not(self):
        not_checked = self.page.split("## Not checked")[1].split("\n## ")[0]
        for words in ("Whether the namespace comes out of the deploy as the template wrote it.", "Whether the deploy identity may delete its own old assignment.", "the principal type ServicePrincipal",
                      "ran with Git's bash 5.3 against a stand-in for `az` that keeps a list of assignments", "the source of the Azure CLI 2.92.0 (the scope is matched exactly unless inherited assignments are asked for, `--ids` deletes exactly the ids named), not tried",
                      "Whether the usage app wakes from zero on an event that arrives only through the private endpoint, and whether the gateway's two loggers reach the namespace",
                      "Whether the Operator's send reaches the namespace through the private endpoint"):
            self.assertIn(words, not_checked, words)
        sources = self.page.split("## Sources")[1]
        for words in ("[Restrict Event Hubs namespace to private endpoints](https://learn.microsoft.com/azure/event-hubs/private-link-service)", "microsoft-eventhub-namespaces-metrics", "microsoft-apimanagement-service-metrics",
                      "[az role assignment](https://learn.microsoft.com/cli/azure/role/assignment)", "the generated Bicep types of `Microsoft.EventHub/namespaces` at 2024-01-01",
                      "the source of the Azure CLI 2.92.0 for `az role assignment list` and `delete`"):
            self.assertIn(words, sources, words)

    def test_the_bootstrap_page_says_no_hand_step_what_a_refusal_means_the_order_the_way_back_and_how_to_delete_by_id(self):
        section = self.bootstrap_section
        for words in ("**No hand step is needed.** It is built and not yet deployed.", "sets `publicNetworkAccess: 'Disabled'` on the namespace (local authentication stays off and TLS 1.2 stays). It adds no network rule set and no trusted-service exception",
                      "no longer give the deploy identity *Azure Event Hubs Data Sender* on the control hub (`workflowSendsControl`), and the parameter `workflowPrincipalId` that fed it is gone from both templates and from the parameter builder",
                      "so one step in each of the two actions retires the assignment that exists", "deletes only the one that is *Azure Event Hubs Data Sender*, by its id, reads back that it is gone, and prints what it did",
                      "it never touches another assignment: the gateway's, the function apps' and the Operator's roles on the hubs stay", "reads the namespace back from Azure after the deploy and fails unless public network access is Disabled",
                      "**Why no hand step.**", "if Azure refuses the delete, the step stops with Azure's message and says what to do, and nothing else has changed", "A person then deletes that one assignment with their own sign-in, on the owner's written word",
                      "delete it by its id and never by a filter", "az role assignment delete --ids <id of the assignment>", "**The order**, on an estate where the namespace is still public:", "**while the namespace is still public**",
                      "**Going back.** Revert this change and run `recording` and `cases`"):
            self.assertIn(words, section, words)
        self.assertEqual(section.count("```powershell"), 1)
        self.assertEqual(sorted(set(re.findall(r"az role assignment (\w+)", section.split("```powershell")[1]))), ["delete", "list"])
        for anchor in ("#changed-on-2026-11-06-the-event-hubs-namespace-is-private",):
            self.assertIn(anchor, self.bootstrap)
        self.assertLess(self.bootstrap.index("## Changed on 2026-11-06: the Operator"), self.bootstrap.index("## Changed on 2026-11-06: the Event Hubs namespace is private"))
        self.assertLess(self.bootstrap.index("## Changed on 2026-11-06: the Event Hubs namespace is private"), self.bootstrap.index("\n## After it"))
        self.assertIn("holds none since [the namespace was made private](#changed-on-2026-11-06-the-event-hubs-namespace-is-private)", self.bootstrap.split("\n## ")[1])
        self.assertIn("The order of those four is `recording`, `cases`, `operator`, and then, about ten minutes after `operator` (a new role takes that long to apply), `recording-check` and `cases-run`. Once both checks have passed through the Operator while the namespace is still public, `recording` makes the Event Hubs namespace private",
                      self.bootstrap.split("\n## After it")[1])

    def test_the_pages_that_said_that_the_workflow_sends_or_that_the_namespace_is_public_say_the_new_state(self):
        cases = text("docs/proposals/02-first-cases.md")
        self.assertIn("the deployment workflow starts it, through the Operator, which sends the event from inside the network and reads the result from the telemetry", cases)
        self.assertIn("The Operator may send to that hub (the deployment workflow's identity held that right until the action `cases` retired it); the function reads it", cases)
        self.assertIn("the namespace takes no public traffic once the action `recording` has deployed its template, so the runner cannot send to it at all", cases)
        self.assertNotIn("The workflow may send to that hub", cases)
        readme = text("README.md")
        self.assertIn("the Event Hubs namespace is private-only in the code, not yet deployed; nothing is private yet", readme)
        self.assertIn("the template sets public network access to Disabled, the deploy identity no longer holds a role on the control hubs and the two deploy actions retire the one that it held", readme)
        self.assertIn("The Operator and its probe are built, and so is the switch that makes the Event Hubs namespace private-only (not yet deployed); nothing is private yet", readme)
        bootstrap_first = self.bootstrap.split("\n## ")[1]
        self.assertNotIn("the gateway's identity and the workflow's identity may send to event hubs", bootstrap_first)
        self.assertNotIn("the workflow's identity gets", self.bootstrap)
        self.assertNotIn("gives the gateway's identity and the workflow's identity *Azure Event Hubs Data Sender*", self.bootstrap)


class BootstrapOperatorSection(unittest.TestCase):
    """environment/BOOTSTRAP.md: the order of the actions, the two new roles, and what a person does after this change."""

    def setUp(self):
        self.page = text("environment/BOOTSTRAP.md")
        self.section = self.page.split("## Changed on 2026-11-06: the Operator")[1].split("\n## ")[0]

    def test_it_says_which_actions_use_the_operator_now_and_names_the_generic_script(self):
        for words in ("Two existing actions now use it: `recording-check` and `cases-run`", "[`operator/run-tool.sh`](../operator/run-tool.sh)", "[`tools/recording-check.py`](../tools/recording-check.py)",
                      "[`tools/cases-check.py`](../tools/cases-check.py)", "so that the control event is sent, and the telemetry is read, from inside the network"):
            self.assertIn(words, self.section, words)

    def test_it_names_the_three_roles_and_says_that_the_two_new_ones_need_no_hand_step(self):
        for words in ("**Three roles**, all for that identity.", "*Reader* on the project's resource group", "`Microsoft.Insights/Components/Query/Read`", "*Reader* includes `*/read`",
                      "*Azure Event Hubs Data Sender* on the control hub `usage-control` (made by the action `recording`) and on `cases-control` (made by the action `cases`), one role on each hub and none on the namespace",
                      "is in the condition of the deploy identity's role-assignment right already", "so the two new roles need no hand step"):
            self.assertIn(words, self.section, words)
        self.assertNotIn("**One role:**", self.section)
        self.assertNotIn("each needs the same hand step as below", self.section, "Data Sender needs none")

    def test_it_says_the_order_run_operator_again_wait_about_ten_minutes_and_then_run_the_two_checks(self):
        for words in ("The order of the actions on an estate is `recording`, `cases`, `operator`", "the action `operator` stops before it changes anything when a hub is not there",
                      "1. Run `operator` again.", "the two *Azure Event Hubs Data Sender* roles are made", "2. Wait about ten minutes: a new role takes up to that long to apply",
                      "3. Run `recording-check` and `cases-run`.", "that stops working when Application Insights gets private-only query access", "(that switch is not changed by this step)",
                      "it stops with the reason, and says to run `operator` first, when the identity or the subnet is missing"):
            self.assertIn(words, self.section, words)
        self.assertLess(self.section.index("1. Run `operator` again."), self.section.index("2. Wait about ten minutes"))
        self.assertLess(self.section.index("2. Wait about ten minutes"), self.section.index("3. Run `recording-check` and `cases-run`."))
        after = self.page.split("\n## After it")[1].split("\n## ")[0]
        self.assertIn("The order of those four is `recording`, `cases`, `operator`, and then, about ten minutes after `operator`", after)
        self.assertIn("both from inside the network by the Operator, so it comes after `operator`", after)
        self.assertIn("both by the Operator, so it comes after `operator` too", after)

    def test_it_says_what_a_check_costs_and_that_the_probe_passed_without_a_fallback(self):
        for words in ("at most 25 minutes for `recording-check` (about 2.3 US cents) and 40 for `cases-run` (about 3.6)", "20 seconds at the end", "it did not", "No new right is given to the deploy identity.",
                      "it passed on 2026-11-06, twice"):
            self.assertIn(words, self.section, words)


if __name__ == "__main__":
    unittest.main()
