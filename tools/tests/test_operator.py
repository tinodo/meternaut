import base64
import contextlib
import datetime
import importlib.util
import io
import json
import os
import re
import shlex
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
_hubenv_spec = importlib.util.spec_from_file_location("hubenv", Path(__file__).with_name("hubenv.py"))
hubenv = importlib.util.module_from_spec(_hubenv_spec)
_hubenv_spec.loader.exec_module(hubenv)

SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
GROUP = "rg-example"
NAME = "op-probe-1"
SUBNET = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.Network/virtualNetworks/vnet-example/subnets/snet-ops"
IDENTITY = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-example-operator"
DIGEST = "sha256:" + "ab" * 32
IMAGE = f"mcr.microsoft.com/azure-cli@{DIGEST}"
PROJECT = {"ENV_SUBSCRIPTION_ID": SUBSCRIPTION, "ENV_RESOURCE_GROUP": GROUP}
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
        environment = {**PROJECT, "RUNNER_TEMP": str(tmp), **(env or {})}
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), hubenv.patched(actions, environment):
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
                    with contextlib.redirect_stderr(err), hubenv.patched(extra=PROJECT):
                        code = op.main([*base, "--image", image], az=az)
                    self.assertEqual(code, 2)
                    self.assertEqual(az.calls, [])
                    self.assertIn("sha256", err.getvalue())
            az, err = FakeAz(), io.StringIO()
            with contextlib.redirect_stderr(err), hubenv.patched(extra=PROJECT):
                code = op.main([*base, "--image", "mcr.microsoft.com/azure-cli:2.92.0"], az=az)
            self.assertIn("is a tag, and a tag can move", err.getvalue())
            self.assertIn("--allow-tag", err.getvalue())
            az = FakeAz(shows=[shown(container="Terminated", exit_code=0)])
            out = io.StringIO()
            with contextlib.redirect_stdout(out), hubenv.patched(extra=PROJECT):
                code = op.main([*base, "--image", "mcr.microsoft.com/azure-cli:2.92.0", "--allow-tag"], az=az, sleep=Clock().sleep)
            self.assertEqual(code, 0)
            self.assertIn("pinned by tag", out.getvalue())
            self.assertEqual(az.document["properties"]["containers"][0]["properties"]["image"], "mcr.microsoft.com/azure-cli:2.92.0")

    def test_the_ids_of_the_subnet_and_the_identity_are_resource_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "probe.sh"
            script.write_text("echo hi\n", encoding="utf-8")
            for subnet, identity, why in (("snet-ops", IDENTITY, "--subnet-id is not a resource of the project's resource group"), (SUBNET, "id-example-operator", "--identity-id is not a resource of the project's resource group"),
                                          (SUBNET.replace("/subnets/snet-ops", ""), IDENTITY, "--subnet-id is the resource id of a subnet"),
                                          (SUBNET, IDENTITY.replace("userAssignedIdentities", "disks"), "--identity-id is the resource id of a user-assigned identity")):
                az, err = FakeAz(), io.StringIO()
                with contextlib.redirect_stderr(err), hubenv.patched(extra=PROJECT):
                    code = op.main(["run", "--resource-group", GROUP, "--name", NAME, "--subnet-id", subnet, "--identity-id", identity, "--image", IMAGE, "--script", str(script)], az=az)
                self.assertEqual((code, az.calls), (2, []), (subnet, identity))
                self.assertIn(why, err.getvalue(), "an id that is not even in the project's group is refused by that check; one that is, by the check of its form")

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

    def test_nothing_is_made_outside_a_run_of_the_hub(self):
        az = FakeAz()
        code, _, err = clean_run(az, actions=False)
        self.assertEqual((code, az.calls), (2, []))
        self.assertIn("error: this command makes and deletes resources in Azure, and only a run of the Hub may do that (AGENTS.md rule 18): this call was not started by a run of the Hub", err)

    def test_a_process_that_only_says_that_github_actions_is_true_makes_nothing_and_the_refusal_says_nothing_of_what_it_lacks(self):
        az = FakeAz()
        code, _, err = clean_run(az, actions=False, env={"GITHUB_ACTIONS": "true"})
        self.assertEqual((code, az.calls), (2, []))
        self.assertIn("this call was not started by a run of the Hub", err)
        self.assertNotRegex(err, r"GITHUB_|METERNAUT_|ACTIONS_ID|(?i:proof)|(?i:lock)", "a refusal says nothing to copy")

    def test_the_call_names_the_projects_own_subscription_and_group_and_no_other_and_asks_azure_nothing_otherwise(self):
        elsewhere = "99999999-8888-7777-6666-555555555555"
        for label, extra, env in (("another group", ["--resource-group", "rg-another"], {}), ("another subscription", ["--subscription", elsewhere], {}),
                                  ("the project's group, named by its case", ["--resource-group", GROUP.upper()], {}),
                                  ("a project without its own subscription", [], {"ENV_SUBSCRIPTION_ID": ""}), ("a project without its own group", [], {"ENV_RESOURCE_GROUP": ""})):
            az = FakeAz()
            code, _, err = clean_run(az, *extra, env=env)
            self.assertEqual((code, az.calls), (2, []), label)
            self.assertIn("no other group", err, label)
            self.assertNotRegex(err, r"ENV_|METERNAUT_|GITHUB_", label)

    def test_the_subnet_and_the_identity_are_resources_of_the_projects_own_group_and_of_no_other(self):
        elsewhere = SUBSCRIPTION.replace("1111", "9999", 1)
        other_group = "/resourceGroups/rg-another/"
        for label, subnet, identity in (("a subnet of another group", SUBNET.replace(f"/resourceGroups/{GROUP}/", other_group), IDENTITY),
                                        ("an identity of another group", SUBNET, IDENTITY.replace(f"/resourceGroups/{GROUP}/", other_group)),
                                        ("a subnet of another subscription", SUBNET.replace(SUBSCRIPTION, elsewhere), IDENTITY),
                                        ("an identity of another subscription", SUBNET, IDENTITY.replace(SUBSCRIPTION, elsewhere)),
                                        ("a group whose name only starts like the project's", SUBNET.replace(f"/resourceGroups/{GROUP}/", f"/resourceGroups/{GROUP}-2/"), IDENTITY)):
            with tempfile.TemporaryDirectory() as tmp:
                script = Path(tmp) / "probe.sh"
                script.write_text("echo hi\n", encoding="utf-8")
                az, err = FakeAz(), io.StringIO()
                with contextlib.redirect_stderr(err), hubenv.patched(extra=PROJECT):
                    code = op.main(["run", "--resource-group", GROUP, "--name", NAME, "--subnet-id", subnet, "--identity-id", identity, "--image", IMAGE, "--script", str(script)], az=az)
                self.assertEqual((code, az.calls), (2, []), label)
                self.assertRegex(err.getvalue(), r"--(subnet|identity)-id is not a resource of the project's resource group", label)
        az = FakeAz(shows=[shown(container="Terminated", exit_code=0)])
        code, _, _ = clean_run(az, "--subscription", SUBSCRIPTION.upper())
        self.assertEqual(code, 0, "an id has no case: the same subscription, written in capitals, is the project's own")

    def test_files_of_the_secret_volume_are_checked(self):
        az = FakeAz()
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "x"
            good.write_bytes(b"abc")
            for pair in ("../escape=" + str(good), "a/b=" + str(good), "=" + str(good), "probe.sh=" + str(good), "missing=" + str(Path(tmp) / "nothing"), "noequals"):
                out, err = io.StringIO(), io.StringIO()
                script = Path(tmp) / "probe.sh"
                script.write_text("echo hi\n", encoding="utf-8")
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), hubenv.patched(extra=PROJECT):
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

    def test_the_cap_is_the_measured_limit_with_its_evidence_and_the_message_says_what_was_seen(self):
        # A container group's request took 466,104 bytes of files (the probe of 2026-11-06) and refused 632,656 (the finished package of the cases app and the container script) with an internal server
        # error. The 3,000,000 bytes that this constant held first were an assumption: Learn names no limit, and the first cases publish through the Operator found a real one.
        self.assertEqual(op.MAX_FILE_BYTES, 480_000)
        self.assertEqual((op.FILES_TAKEN_BYTES, op.FILES_REFUSED_BYTES), (466_104, 632_656))
        self.assertEqual(op.FILES_TAKEN_BYTES, 400_000 + 44_967 + 21_137, "the file of the size test, a lock file and the probe's script")
        self.assertEqual(op.FILES_REFUSED_BYTES, 614_068 + 18_588, "the finished package of the cases app and the container script")
        self.assertLessEqual(op.FILES_TAKEN_BYTES, op.MAX_FILE_BYTES, "what is known to work is within the cap, so the probe is not refused")
        self.assertLess(op.MAX_FILE_BYTES, op.FILES_REFUSED_BYTES, "what was refused is above it")
        az = FakeAz()
        code, _, err = clean_run(az, files={"size-test": b"x" * (op.MAX_FILE_BYTES + 1)})
        self.assertEqual((code, az.calls), (2, []))
        for words in ("more than 480000 bytes", "a request with 466104 bytes of files was taken", "one with 632656 was refused with an internal server error (2026-11-06)",
                      "built in the container from sources"):
            self.assertIn(words, err, words)
        self.assertNotIn("3000000", err)

    def test_files_that_are_exactly_at_the_cap_are_taken(self):
        script_bytes = len(b"echo hi\n")
        with tempfile.TemporaryDirectory() as tmp:
            script, big = Path(tmp) / "probe.sh", Path(tmp) / "size-test"
            script.write_bytes(b"echo hi\n")
            big.write_bytes(b"x" * (op.MAX_FILE_BYTES - script_bytes))
            args = op.build_parser().parse_args(["run", "--resource-group", GROUP, "--name", NAME, "--subnet-id", SUBNET, "--identity-id", IDENTITY, "--image", IMAGE, "--script", str(script),
                                                 "--secret-file", f"size-test={big}"])
            files = op.read_files(args)
            self.assertEqual(sum(len(content) for content in files.values()), op.MAX_FILE_BYTES)
            big.write_bytes(b"x" * (op.MAX_FILE_BYTES - script_bytes + 1))
            with self.assertRaises(op.Problem):
                op.read_files(args)

    def test_the_script_that_cannot_be_read_is_refused(self):
        az = FakeAz()
        err = io.StringIO()
        with contextlib.redirect_stderr(err), hubenv.patched(extra=PROJECT):
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

    def test_every_call_names_the_subscription_when_one_is_given_and_the_projects_own_when_none_is(self):
        az = self.good()
        clean_run(az, "--subscription", SUBSCRIPTION)
        self.assertTrue(az.calls)
        for call in az.calls:
            self.assertEqual(call[call.index("--subscription") + 1], SUBSCRIPTION, call)
        az = self.good()
        clean_run(az)
        for call in az.calls:
            self.assertEqual(call[call.index("--subscription") + 1], SUBSCRIPTION, f"the subscription of the project when none is given: {call}")

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


class TheTokenOfTheDeployIdentity(unittest.TestCase):
    """The token that the probe signs in as the deploy identity with, in the size and the shape of the real one (a JWT of about a kilobyte), goes through the real tool: it is one secure value of
    the request and it is in nothing that the tool prints, in no file that is left behind and on no command line, even when the container says it."""

    TOKEN = ".".join(["eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9", "eyJzdWIiOiJyZXBvOm" + "dpdGh1Yi1leGFtcGxlLzEyMzQ1" * 30, "c2ln" + "bmF0dXJlLTEyMzQ1" * 20])

    def run_probe_in_the_tool(self, az):
        files = {"size-test": b"x" * 1000, "cases-requirements.txt": CASES_LOCK}
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            code, out, err, work = run_tool("--secure-env", "AZURE_FEDERATED_TOKEN", "--env", f"PROBE_DEPLOY_CLIENT_ID={DEPLOY_CLIENT}", "--env", f"PROBE_DEPLOY_TENANT_ID={DEPLOY_TENANT}",
                                            "--env", f"PROBE_LOCK_BYTES={len(CASES_LOCK)}", "--summary", str(summary), az=az, env={"AZURE_FEDERATED_TOKEN": self.TOKEN},
                                            script_text=text("operator/probe.sh"), files=files)
            written = summary.read_text(encoding="utf-8") if summary.exists() else ""
            leftovers = [path for path in Path(work).rglob("*") if path.is_file() and self.TOKEN.encode() in path.read_bytes()]
        return code, out, err, written, leftovers

    def test_it_is_one_secure_value_of_the_request_the_volume_holds_the_script_and_the_two_files_and_nothing_that_is_printed_or_left_behind_holds_it(self):
        az = FakeAz(shows=[shown(), shown(container="Terminated", exit_code=0)], logs=[(0, f"the container says {self.TOKEN}\nsecond line\n", ""), (0, f"the container says {self.TOKEN}\nsecond line\n", "")],
                    deletes=[(1, "", f"ERROR: {self.TOKEN}"), (0, "", "")])
        code, out, err, written, leftovers = self.run_probe_in_the_tool(az)
        self.assertEqual(code, 0, err)
        variables = az.document["properties"]["containers"][0]["properties"]["environmentVariables"]
        self.assertEqual([variable for variable in variables if self.TOKEN in json.dumps(variable)], [{"name": "AZURE_FEDERATED_TOKEN", "secureValue": self.TOKEN}])
        self.assertEqual(json.dumps(az.document).count(self.TOKEN), 1, "once in the request, and as a secure value, which Azure does not show again")
        self.assertEqual(sorted(az.document["properties"]["volumes"][0]["secret"]), ["cases-requirements.txt", "probe.sh", "size-test"])
        self.assertEqual(base64.b64decode(az.document["properties"]["volumes"][0]["secret"]["cases-requirements.txt"]), CASES_LOCK, "the lock file is sent whole")
        for stream in (out, err, written):
            for form in (self.TOKEN, base64.b64encode(self.TOKEN.encode()).decode(), json.dumps(self.TOKEN)[1:-1]):
                self.assertNotIn(form, stream)
        self.assertIn("| the container says ***", out)
        self.assertIn("1 secure value(s) that are not shown", out)
        self.assertFalse(any(self.TOKEN in part for call in az.calls for part in call), "on no command line of az")
        self.assertEqual(leftovers, [], "and in no file that is left behind")

    def test_a_token_that_is_not_in_the_environment_is_refused_before_anything_is_made(self):
        az = FakeAz()
        code, out, err, _ = run_tool("--secure-env", "AZURE_FEDERATED_TOKEN", az=az, env={"AZURE_FEDERATED_TOKEN": ""})
        self.assertEqual(code, 2)
        self.assertIn("--secure-env AZURE_FEDERATED_TOKEN names an environment variable of this process, and it is not set", err)
        self.assertEqual(az.calls, [], "no group is made without the token that the probe was told to get: the step leaves the argument out instead")


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
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), hubenv.patched(actions, PROJECT):
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
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), hubenv.patched(extra=PROJECT):
                code = op.main(["cleanup", "--resource-group", GROUP, f"--prefix={prefix}"], az=az)
            self.assertEqual((code, az.calls), (2, []), prefix)

    def test_a_list_that_fails_is_an_error_and_nothing_is_deleted(self):
        az = FakeAz(listing=(1, "", "ERROR: no"))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), hubenv.patched(extra=PROJECT):
            code = op.main(["cleanup", "--resource-group", GROUP, "--prefix", "op-probe-"], az=az)
        self.assertEqual(code, 1)
        self.assertNotIn("delete", az.verbs())

    def test_it_refuses_to_run_outside_a_run_of_the_hub(self):
        code, out, err, az = self.cleanup(actions=False)
        self.assertEqual(code, 2)
        self.assertEqual(az.calls, [])
        self.assertIn("this call was not started by a run of the Hub", err)

    def test_it_lists_and_deletes_in_the_projects_own_group_and_subscription_and_in_no_other(self):
        for label, group, extra in (("another group", "rg-another", []), ("the group in capitals", GROUP.upper(), []), ("another subscription", GROUP, ["--subscription", "99999999-8888-7777-6666-555555555555"])):
            az = FakeAz(listing=(0, json.dumps(group_listing()), ""))
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), hubenv.patched(extra=PROJECT):
                code = op.main(["cleanup", "--resource-group", group, "--prefix", "op-probe-", *extra], az=az)
            self.assertEqual((code, az.calls), (2, []), label)
            self.assertIn("this command names no other group", err.getvalue(), label)
        az = FakeAz(listing=(0, json.dumps(group_listing()), ""))
        code, _, _, az = self.cleanup(az=az)
        self.assertEqual(code, 0)
        self.assertTrue(az.calls)
        for call in az.calls:
            self.assertEqual(call[call.index("--subscription") + 1], SUBSCRIPTION, f"the subscription of the project when none is given: {call}")


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

    def test_it_declares_the_identity_the_group_s_network_pieces_the_two_roles_and_reads_the_storage_account_and_its_control_queue(self):
        types = sorted(self.declared().values())
        self.assertEqual(types, ["Microsoft.Authorization/roleAssignments"] * 2 + ["Microsoft.ManagedIdentity/userAssignedIdentities", "Microsoft.Network/networkSecurityGroups",
                                                                                 "Microsoft.Network/virtualNetworks", "Microsoft.Network/virtualNetworks/subnets",
                                                                                 "Microsoft.Storage/storageAccounts", "Microsoft.Storage/storageAccounts/queueServices",
                                                                                 "Microsoft.Storage/storageAccounts/queueServices/queues"])

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

    def test_the_roles_are_reader_on_the_group_and_queue_data_contributor_on_the_one_control_queue_for_the_identity_only(self):
        self.assertIn("var readerRoleId = 'acdd72a7-3385-48ef-bd42-f606fba81ae7'", self.code)
        self.assertIn("var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'", self.code)
        self.assertEqual(len(re.findall(r"RoleId = '", self.code)), 2, "two roles, Reader and Storage Queue Data Contributor, and no third")
        self.assertEqual(len(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", self.code)), 2)
        blocks = dict(re.findall(r"(?ms)^resource (\w+) 'Microsoft\.Authorization/roleAssignments@[^']+' = \{\n(.*?)^\}", self.code))
        self.assertEqual(sorted(blocks), ["operatorPutsCasesControl", "operatorReadsTheGroup"], "the Operator holds no role on a hub: the namespace is gone, and the usage recording's hub was removed on 2026-11-07")
        expected = {"operatorReadsTheGroup": ("resourceGroup()", "guid(resourceGroup().id, operatorIdentity.id, readerRoleId)", "readerRoleId"),
                    "operatorPutsCasesControl": ("casesControlQueue", "guid(casesControlQueue.id, operatorIdentity.id, storageQueueDataContributorRoleId)", "storageQueueDataContributorRoleId")}
        for name, (scope, assignment_name, role) in expected.items():
            block = blocks[name]
            self.assertIn(f"  scope: {scope}\n", block, name)
            self.assertIn(f"  name: {assignment_name}\n", block, name)
            self.assertIn(f"roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', {role})", block, name)
            self.assertIn("principalId: operatorIdentity.properties.principalId", block, name)
            self.assertIn("principalType: 'ServicePrincipal'", block, name)
        for wider in ("scope: storage\n", "scope: queueService", "scope: subscription", "scope: tenant", "scope: managementGroup", "scope: usageHub", "scope: piiHub", "usageControlHub"):
            self.assertNotIn(wider, self.code, f"{wider}: the Operator may put a message in the control queue of the cases and nowhere else")
        self.assertNotIn("c6a89b2d-59bc-44d0-9896-0f6e12d7b80a", self.code, "Storage Queue Data Message Sender is not in the condition of the deploy identity's right to assign roles")

    def test_the_storage_account_and_the_control_queue_are_only_read_here_because_the_base_and_the_cases_make_them(self):
        self.assertEqual(len(re.findall(r"Microsoft\.Storage", self.code)), 3)
        self.assertRegex(self.code, r"(?m)^resource storage 'Microsoft\.Storage/storageAccounts@[^']+' existing = \{\n  name: storageAccountName\n\}$")
        self.assertRegex(self.code, r"(?m)^resource queueService 'Microsoft\.Storage/storageAccounts/queueServices@[^']+' existing = \{\n  parent: storage\n  name: 'default'\n\}$")
        self.assertRegex(self.code, r"(?m)^resource casesControlQueue 'Microsoft\.Storage/storageAccounts/queueServices/queues@[^']+' existing = \{\n  parent: queueService\n  name: casesControlQueueName\n\}$")
        for word in ("Microsoft.EventHub", "eventHub", "blobServices", "tableServices", "publicNetworkAccess", "allowSharedKeyAccess", "storage.properties", "casesControlQueue.properties", "metadata"):
            self.assertNotIn(word, self.code, f"{word}: nothing of the storage account or the queue is written or read here")

    def test_the_name_of_the_queue_is_the_one_that_the_first_cases_give_it(self):
        # A queue that is renamed in the template that makes it must be renamed here too: the role of the Operator is on the queue by its name, and a template that reads a queue that is not there fails.
        self.assertIn("var casesControlQueueName = 'cases-control'", self.code)
        self.assertIn("var controlQueueName = 'cases-control'", text("environment/cases/main.bicep"))
        self.assertEqual(sorted(re.findall(r"CONTROL_QUEUE = \"([a-z-]+)\"", text("tools/cases-check.py"))), ["cases-control"], "and the tool puts its message in the queue of the same name")

    def test_it_outputs_the_ids_that_the_workflow_and_the_container_need_and_nothing_secret(self):
        outputs = re.findall(r"(?m)^output (\w+) string = (.+)$", self.code)
        self.assertEqual([name for name, _ in outputs], ["identityId", "identityPrincipalId", "identityClientId", "subnetId"])

    def test_every_parameter_says_what_it_is_and_the_text_ones_are_bounded(self):
        for match in re.finditer(r"(?m)^((?:@\w+\([^\n]*\)\n)+)param (\w+) (\w+)", self.code):
            self.assertIn("@description(", match.group(1), match.group(2))
        for name in ("owner", "opsSubnetPrefix", "storageAccountName"):
            self.assertRegex(self.code, rf"(?m)^@minLength\(\d+\)\n(?:@maxLength\(\d+\)\n)?param {name} string$")
        self.assertRegex(self.code, r"(?m)^@minLength\(9\)\n@maxLength\(18\)\nparam opsSubnetPrefix string$")
        self.assertRegex(self.code, r"(?m)^@minLength\(3\)\n@maxLength\(24\)\nparam storageAccountName string$", "the limits of a storage account's name, as in the base's template")

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
# stand-in for az: FAKE_AZ_LOGIN, FAKE_AZ_DEPLOY_LOGIN, FAKE_AZ_GROUP and FAKE_AZ_DEPLOY_GROUP are ok or fail; FAKE_TOKEN_IN_ERROR is a string that a failed sign-in of the deploy identity repeats.
# Every call is logged with the folder of the CLI's state (AZURE_CONFIG_DIR: the deploy identity has one of its own), and a call that finds the federated token in its environment says so:
# the probe takes it out of the environment before anything runs
if [ -n "${FAKE_LOG:-}" ]; then
  echo "az $* [config=${AZURE_CONFIG_DIR:-none}]" >> "$FAKE_LOG"
  if [ -n "${AZURE_FEDERATED_TOKEN:-}" ]; then echo "az SAW THE TOKEN IN ITS ENVIRONMENT" >> "$FAKE_LOG"; fi
fi
if [ "$1" = login ]; then
  case " $* " in
    *" --service-principal "*)
      if [ "${FAKE_AZ_DEPLOY_LOGIN:-ok}" = ok ]; then exit 0; fi
      echo "ERROR: AADSTS70021: the assertion ${FAKE_TOKEN_IN_ERROR:-} was refused, no matching federated identity record" >&2
      echo "second line that must not show" >&2
      exit 1 ;;
  esac
  if [ "${FAKE_AZ_LOGIN:-ok}" = ok ]; then exit 0; fi
  echo "ERROR: Failed to connect to MSI 11111111-2222-3333-4444-555555555555 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa $GITHUB_TOKEN" >&2
  echo "second line that must not show" >&2
  exit 1
fi
if [ "$1" = group ]; then
  if [ -n "${AZURE_CONFIG_DIR:-}" ]; then
    if [ "${FAKE_AZ_DEPLOY_GROUP:-ok}" = ok ]; then echo Succeeded; exit 0; fi
    echo "ERROR: (AuthorizationFailed) The deploy identity does not have authorization ${FAKE_TOKEN_IN_ERROR:-}" >&2
    exit 1
  fi
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
# stand-in for curl: FAKE_CURL is "host=code:exit:finalhost host=..."; a host that is not in it is unreachable (exit 28). What --write-out asks for is what comes out: the status code alone
# for '%{http_code}', the code and the final address for the probe's own format. The address of the request is the last argument.
url=""
format=""
previous=""
for argument in "$@"; do
  if [ "$previous" = --write-out ]; then format=$argument; fi
  previous=$argument
  url=$argument
done
host=${url#https://}
host=${host%%/*}
if [ -n "${FAKE_LOG:-}" ]; then echo "curl $*" >> "$FAKE_LOG"; fi
for entry in ${FAKE_CURL:-}; do
  if [ "${entry%%=*}" = "$host" ]; then
    rest=${entry#*=}
    code=${rest%%:*}
    rest=${rest#*:}
    status=${rest%%:*}
    final=""
    if [ "$rest" != "$status" ]; then final=${rest#*:}; fi
    if [ "$format" = '%{http_code}' ]; then printf '%s' "$code"; else printf '%s https://%s/x' "$code" "${final:-$host}"; fi
    exit "$status"
  fi
done
if [ "$format" = '%{http_code}' ]; then printf '000'; else printf '000 %s' "$url"; fi
exit 28
"""

STUB_TIMEOUT = """#!/bin/bash
shift
exec "$@"
"""

STUB_PYTHON = """#!/bin/bash
# stand-in for python3. -c with sys.version_info says the version; -c with os.walk is the real Python (REAL_PYTHON), which counts the files of a folder; -c with sysconfig says where ensurepip put pip;
# -c with import lzma or import bz2 works unless FAKE_PYTHON_MODULES_MISSING names the module (the names are separated by spaces).
# -m pip is FAKE_PIP: ok, missing (no pip, unless PYTHONPATH names the one that ensurepip made), strict-fails (the first attempt says Requires-Python and the one with --ignore-requires-python works),
# hash, network, timeout (the exit code of timeout) or other (an error that nobody planned for). -m ensurepip is FAKE_ENSUREPIP: ok or disabled. Every -m call is logged with its arguments and PYTHONPATH,
# and a call that finds the federated token in its environment says so.
if [ -n "${FAKE_LOG:-}" ]; then
  if [ "$1" = -m ]; then echo "python3 $* [PYTHONPATH=${PYTHONPATH:-none}]" >> "$FAKE_LOG"; fi
  if [ -n "${AZURE_FEDERATED_TOKEN:-}" ]; then echo "python3 SAW THE TOKEN IN ITS ENVIRONMENT" >> "$FAKE_LOG"; fi
fi
case "$1" in
  -c)
    case "$2" in
      *os.walk*)
        dir=$3
        if command -v cygpath > /dev/null 2>&1; then dir=$(cygpath -w "$3"); fi
        exec "$REAL_PYTHON" -c "$2" "$dir" ;;
      *sysconfig*) echo "$3/usr/lib/python3.12/site-packages"; exit 0 ;;
      "import lzma" | "import bz2")
        case " ${FAKE_PYTHON_MODULES_MISSING:-} " in
          *" ${2#import } "*) echo "ModuleNotFoundError: No module named '_${2#import }'" >&2; exit 1 ;;
        esac
        exit 0 ;;
      *) echo 3.12.7; exit 0 ;;
    esac ;;
  -m)
    case "$2" in
      ensurepip)
        if [ "${FAKE_ENSUREPIP:-ok}" != ok ]; then echo "ERROR: ensurepip is disabled in this Python: install the python3-pip package" >&2; exit 1; fi
        root=""
        previous=""
        for argument in "$@"; do
          if [ "$previous" = --root ]; then root=$argument; fi
          previous=$argument
        done
        mkdir -p "$root/usr/lib/python3.12/site-packages/pip"
        echo "# pip" > "$root/usr/lib/python3.12/site-packages/pip/__init__.py"
        exit 0 ;;
      pip)
        if [ "$3" = --version ]; then
          if [ "${FAKE_PIP:-ok}" = missing ] && [ -z "${PYTHONPATH:-}" ]; then echo "/usr/bin/python3: No module named pip" >&2; exit 1; fi
          echo "pip 24.0 from /usr/lib/python3.12/site-packages/pip (python 3.12)"
          exit 0
        fi
        target=""
        ignore=no
        previous=""
        for argument in "$@"; do
          if [ "$previous" = --target ]; then target=$argument; fi
          if [ "$argument" = --ignore-requires-python ]; then ignore=yes; fi
          previous=$argument
        done
        case "${FAKE_PIP:-ok}:$ignore" in
          strict-fails:no)
            echo "ERROR: Ignored the following versions that require a different python version: 2.3.0 Requires-Python >=3.13" >&2
            echo "ERROR: No matching distribution found for azure-functions==2.3.0" >&2
            exit 1 ;;
          hash:*) echo "ERROR: THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE. If you have updated the package versions, please update the hashes." >&2; exit 1 ;;
          network:*)
            echo "WARNING: Retrying (Retry(total=0)) after connection broken by 'NewConnectionError: Failed to establish a new connection: [Errno -3] Temporary failure in name resolution'" >&2
            echo "ERROR: Could not find a version that satisfies the requirement azure-core==1.41.0" >&2
            exit 1 ;;
          timeout:*) exit 124 ;;
          other:*) echo "ERROR: something that nobody planned for went wrong while a wheel was unpacked" >&2; exit 1 ;;
        esac
        mkdir -p "$target/azure/core" "$target/cryptography"
        head -c 1048576 /dev/zero > "$target/cryptography/big.so"
        head -c 524288 /dev/zero > "$target/azure/core/medium.bin"
        echo "# core" > "$target/azure/core/__init__.py"
        exit 0 ;;
    esac ;;
esac
echo "unexpected python3 call: $*" >&2
exit 9
"""

FEDERATED_TOKEN = "fake-oidc-token-Q9x7LmN2pR5tV8wY"
SHORT_FEDERATED_TOKEN = "fake-oidc-7Qz"
DEPLOY_CLIENT = "aaaaaaaa-1111-2222-3333-444444444444"
DEPLOY_TENANT = "bbbbbbbb-5555-6666-7777-888888888888"
SCM_CASES = "func-meternaut-cases-0a1b2c3d.scm.azurewebsites.net"
CASES_LOCK = b"azure-core==1.41.0 \\\n    --hash=sha256:" + b"ab" * 32 + b"\n"


@unittest.skipIf(BASH is None, "no bash on this machine")
class ProbeScript(unittest.TestCase):
    """operator/probe.sh against stand-ins for az, curl, getent, timeout and python3: what it says for each check, that it says little, and that it never fails."""

    def run_probe(self, env=None, stubs=None, resolv="nameserver 10.53.0.4\nnameserver 168.63.129.16\n", size=None, lock=None):
        """Runs the script. What the stand-ins logged is in self.calls, and what the probe left in its work folder in self.leftover."""
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
            if lock is not None:
                (volume / "cases-requirements.txt").write_bytes(lock)
            work_root = tmp / "work"
            work_root.mkdir()
            log = tmp / "log.txt"
            log.write_text("", encoding="utf-8")
            resolv_conf = tmp / "resolv.conf"
            resolv_conf.write_text(resolv, encoding="utf-8", newline="\n")
            script = tmp / "probe.sh"
            script.write_text(text("operator/probe.sh"), encoding="utf-8", newline="\n")
            environment = {**os.environ, "STUBS": posix(bin_dir), "PROBE_VOLUME": posix(volume), "PROBE_RESOLV_CONF": posix(resolv_conf), "PROBE_TMP": posix(work_root), "FAKE_LOG": posix(log),
                           "REAL_PYTHON": posix(sys.executable), "OPERATOR_CLIENT_ID": "11111111-2222-3333-4444-555555555555", "OPERATOR_GROUP": "rg-example", "GITHUB_TOKEN": TOKEN_OF_THE_RUN,
                           **(env or {})}
            for name in [name for name, value in environment.items() if value is None]:
                del environment[name]
            done = subprocess.run([BASH, "-c", 'PATH="$STUBS:$PATH"; export PATH; exec bash "$0"', posix(script)], capture_output=True, text=True, env=environment)
            self.calls = log.read_text(encoding="utf-8").splitlines()
            self.leftover = sorted(path.name for path in work_root.iterdir())
        return done, done.stdout.splitlines()

    def good_env(self):
        """Everything that the probe is given on the real estate, with stand-ins that answer well. The deploy identity has a token, the deployment site is private, and the lock file has arrived whole."""
        return {"PROBE_NAMES": "evhns-example.servicebus.windows.net github.com", "PROBE_PRIVATE_NAMES": f"evhns-example.servicebus.windows.net {SCM_CASES}",
                "FAKE_DNS": f"evhns-example.servicebus.windows.net=10.53.0.20 github.com=140.82.121.4 {SCM_CASES}=10.53.0.21",
                "PROBE_URLS": "https://mcr.microsoft.com/v2/ https://api.github.com/ https://github.com/x/y https://slow.example.net/",
                "FAKE_CURL": f"mcr.microsoft.com=200:0 api.github.com=200:0 github.com=302:0:release-assets.githubusercontent.com slow.example.net=302:47 {SCM_CASES}=401:0",
                "PROBE_SIZE_BYTES": "4000", "AZURE_FEDERATED_TOKEN": FEDERATED_TOKEN, "PROBE_DEPLOY_CLIENT_ID": DEPLOY_CLIENT, "PROBE_DEPLOY_TENANT_ID": DEPLOY_TENANT,
                "PROBE_SCM_HOSTS": SCM_CASES, "PROBE_LOCK_BYTES": str(len(CASES_LOCK))}

    def good_run(self, **changes):
        return self.run_probe({**self.good_env(), **changes}, size=4000, lock=CASES_LOCK)

    @staticmethod
    def without_seconds(lines):
        """The seconds that a build took are the clock's, not the test's."""
        return [re.sub(r", \d+ s, hashes ok$", ", N s, hashes ok", line) for line in lines]

    def test_a_good_environment_gives_one_ok_line_for_each_check_and_ends_with_probe_done(self):
        done, lines = self.good_run()
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertEqual(self.without_seconds(lines), [
            "ok: az, curl, getent and python3 are in the image",
            "ok: python3 3.12.7",
            "ok: python3 imports lzma and bz2",
            "ok: python3 -m pip 24.0",
            "ok: az login as the deploy identity with the OpenID Connect token",
            "ok: az group show of the project group as the deploy identity",
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
            "ok: scm func-meternaut-cases-0a1b2c3d: private address, GET / gives 401",
            f"ok: cases lock file is {len(CASES_LOCK)} bytes, as sent",
            "ok: cases build needs no --ignore-requires-python: 3 files, 1.5 MB, N s, hashes ok",
            "probe-done",
        ])
        self.assertEqual(self.leftover, [], "the work folder, with the CLI's state of the deploy identity and what was built, is gone")

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

    def test_a_python_that_cannot_import_lzma_or_bz2_is_one_FAIL_line_that_names_what_it_cannot_import_and_the_probe_goes_on(self):
        # The sources that the workflow sends are one LZMA entry (tools/build-function-app.sh), so the container needs lzma; bz2 is the other compression that a zip can use
        for missing, said in (("lzma", "FAIL: python3 cannot import: lzma"), ("bz2", "FAIL: python3 cannot import: bz2"), ("lzma bz2", "FAIL: python3 cannot import: lzma bz2")):
            done, lines = self.good_run(FAKE_PYTHON_MODULES_MISSING=missing)
            self.assertEqual((done.returncode, done.stderr), (0, ""), missing)
            self.assertEqual(lines[1:3], ["ok: python3 3.12.7", said], missing)
            self.assertNotIn("ok: python3 imports lzma and bz2", lines)
            self.assertNotIn("ModuleNotFoundError", done.stdout, "what Python said is not printed")
            self.assertIn("ok: python3 -m pip 24.0", lines, "the other checks go on")
            self.assertEqual(lines[-1], "probe-done")
        done, lines = self.good_run()
        self.assertEqual(lines[1:3], ["ok: python3 3.12.7", "ok: python3 imports lzma and bz2"])

    def test_a_python_that_does_not_run_is_said_once_and_its_modules_are_not_asked_about(self):
        broken = "#!/bin/bash\nexit 1\n"
        done, lines = self.run_probe({}, stubs={"python3": broken})
        self.assertIn("FAIL: python3 does not run", lines)
        self.assertEqual([line for line in lines if "lzma" in line or "bz2" in line], [])
        self.assertEqual(lines[-1], "probe-done")

    def test_a_secret_volume_without_the_file_that_was_to_be_sent_is_a_failure_and_without_a_size_it_is_only_said(self):
        _, lines = self.run_probe({"PROBE_SIZE_BYTES": "4000"}, size=None)
        self.assertIn("FAIL: no size-test file in the secret volume", lines)
        _, lines = self.run_probe({}, size=1234)
        self.assertIn("ok: secret volume file is 1234 bytes", lines)
        _, lines = self.run_probe({}, size=None)
        self.assertFalse([line for line in lines if "secret volume file" in line or "size-test" in line])

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
            done, lines = self.run_probe(scenario, size=4000, lock=CASES_LOCK)
            self.assertNotIn(TOKEN_OF_THE_RUN, done.stdout + done.stderr)
            self.assertNotIn(FEDERATED_TOKEN, done.stdout + done.stderr)
            for line in lines:
                if line.startswith("FAIL: az "):
                    self.assertNotRegex(line, r"[A-Za-z0-9_.~+/=-]{20,}", "what a command said holds no string that could be a token")
                self.assertNotRegex(line, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "an id is hidden")

    def test_it_runs_with_nothing_set_and_still_ends_well(self):
        done, lines = self.run_probe({"OPERATOR_CLIENT_ID": "", "OPERATOR_GROUP": ""})
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertIn("FAIL: az login: OPERATOR_CLIENT_ID is not set", lines)
        self.assertIn("FAIL: deploy identity sign-in: no token (the workflow sent none)", lines)
        self.assertIn("FAIL: no cases-requirements.txt in the secret volume", lines)
        self.assertFalse([line for line in lines if line.startswith(("ok: scm", "FAIL: scm"))], "no deployment site asked for, no line")
        self.assertEqual([call for call in self.calls if "scm.azurewebsites.net" in call], [])
        self.assertEqual(lines[-1], "probe-done")
        self.assertEqual(self.leftover, [])

    def test_a_subscription_is_passed_to_the_group_read_when_it_is_given_and_only_then(self):
        subscription = "22222222-3333-4444-5555-666666666666"
        strict = STUB_AZ.replace('if [ "$1" = group ]; then\n', 'if [ "$1" = group ]; then\n  case " $* " in *" --subscription ' + subscription + ' "*) ;; *) echo "ERROR: no subscription" >&2; exit 1 ;; esac\n')
        _, lines = self.run_probe({"OPERATOR_SUBSCRIPTION": subscription}, stubs={"az": strict})
        self.assertIn("ok: az group show of the project group: the Reader role works", lines)
        _, lines = self.run_probe({}, stubs={"az": strict})
        self.assertIn("FAIL: az group show: ERROR: no subscription", lines, "without the setting the read is the plain one")
        _, lines = self.run_probe({**self.good_env(), "OPERATOR_SUBSCRIPTION": subscription}, stubs={"az": strict})
        self.assertEqual(len([call for call in self.calls if call.startswith("az group show")]), 2, "the Operator's read and the deploy identity's")
        for call in self.calls:
            if call.startswith("az group show"):
                self.assertIn(f"--subscription {subscription}", call, "both reads name the subscription when it is given")
        self.assertIn("ok: az group show of the project group as the deploy identity", lines)

    # --- the deploy identity -------------------------------------------------------------------------------------------------------------------------------------------------------------

    def test_the_deploy_identity_signs_in_with_the_token_in_a_folder_of_its_own_before_the_operator_and_reads_the_group_there(self):
        done, lines = self.good_run()
        (login,) = [call for call in self.calls if call.startswith("az login --service-principal")]
        self.assertRegex(login, rf"^az login --service-principal --username {DEPLOY_CLIENT} --tenant {DEPLOY_TENANT} --federated-token {FEDERATED_TOKEN} --allow-no-subscriptions --output none "
                                r"\[config=/.+/azure-deploy\]$")
        folder = re.search(r"\[config=(.+)\]$", login).group(1)
        self.assertEqual([call for call in self.calls if f"[config={folder}]" in call],
                         [login, f"az group show --name rg-example --query properties.provisioningState --output tsv [config={folder}]"], "everything of the deploy identity is in its own folder")
        operator = [call for call in self.calls if call.startswith("az ") and "[config=none]" in call]
        self.assertEqual(operator, ["az login --identity --client-id 11111111-2222-3333-4444-555555555555 --allow-no-subscriptions --output none [config=none]",
                                    "az group show --name rg-example --query properties.provisioningState --output tsv [config=none]"], "the Operator's sign-in keeps the default folder")
        self.assertLess(self.calls.index(login), self.calls.index(operator[0]), "the token is valid for five minutes, so it is used before anything that can wait")
        self.assertTrue(folder.startswith(folder.rsplit("/probe-", 1)[0] + "/probe-"), "the folder is inside the work folder of the probe, which is removed at the end")
        self.assertEqual(self.leftover, [])

    def test_the_token_is_on_the_command_line_of_the_one_sign_in_and_in_the_environment_of_no_program(self):
        self.good_run(PROBE_SCM_HOSTS=SCM_CASES)
        self.assertEqual([call for call in self.calls if FEDERATED_TOKEN in call], [next(call for call in self.calls if "--service-principal" in call)])
        self.assertIn(f"--federated-token {FEDERATED_TOKEN} ", self.calls[[FEDERATED_TOKEN in call for call in self.calls].index(True)])
        self.assertEqual([call for call in self.calls if "SAW THE TOKEN" in call], [],
                         "the probe takes the token out of its environment before any program runs, so that az, python3 and pip do not inherit it")

    def test_the_token_never_reaches_the_output_even_when_az_repeats_it_and_even_when_it_is_too_short_to_look_like_one(self):
        for token, failing in ((FEDERATED_TOKEN, "FAKE_AZ_DEPLOY_LOGIN"), (SHORT_FEDERATED_TOKEN, "FAKE_AZ_DEPLOY_LOGIN"), (FEDERATED_TOKEN, "FAKE_AZ_DEPLOY_GROUP")):
            done, lines = self.good_run(AZURE_FEDERATED_TOKEN=token, FAKE_TOKEN_IN_ERROR=token, **{failing: "fail"})
            self.assertEqual(done.returncode, 0)
            self.assertNotIn(token, done.stdout + done.stderr, (token, failing))
            for word in ("second line that must not show", FEDERATED_TOKEN):
                self.assertNotIn(word, done.stdout + done.stderr)
            if failing == "FAKE_AZ_DEPLOY_LOGIN":
                self.assertRegex("\n".join(lines), r"(?m)^FAIL: deploy identity sign-in: ERROR: AADSTS70021: the assertion <(token|hidden)> was refused", (token, failing))
            else:
                self.assertRegex("\n".join(lines), r"(?m)^FAIL: az group show as the deploy identity: ERROR: \(AuthorizationFailed\) The deploy identity do", (token, failing))
            self.assertEqual(lines[-1], "probe-done")

    def test_without_a_token_the_sign_in_says_so_with_the_reason_of_the_workflow_and_the_rest_of_the_probe_runs(self):
        done, lines = self.good_run(AZURE_FEDERATED_TOKEN=None, PROBE_TOKEN_NOTE="the job has no OpenID Connect token request")
        self.assertEqual(done.returncode, 0)
        self.assertIn("FAIL: deploy identity sign-in: no token (the job has no OpenID Connect token request)", lines)
        self.assertEqual([call for call in self.calls if "--service-principal" in call], [], "nothing is tried without a token")
        self.assertEqual(len([line for line in lines if "deploy identity" in line]), 1, "no group is read with an identity that did not sign in")
        for expected in ("ok: az login --identity", "ok: az group show of the project group: the Reader role works", "ok: secret volume file is 4000 bytes, as sent",
                         "ok: scm func-meternaut-cases-0a1b2c3d: private address, GET / gives 401"):
            self.assertIn(expected, lines)
        self.assertEqual(self.without_seconds(lines)[-2], "ok: cases build needs no --ignore-requires-python: 3 files, 1.5 MB, N s, hashes ok")
        self.assertEqual(lines[-1], "probe-done")
        done, lines = self.good_run(AZURE_FEDERATED_TOKEN="", PROBE_TOKEN_NOTE=None)
        self.assertIn("FAIL: deploy identity sign-in: no token (the workflow sent none)", lines)
        self.assertEqual([call for call in self.calls if "--service-principal" in call], [])

    def test_a_sign_in_that_is_refused_says_why_in_a_few_words_and_nothing_is_read_with_that_identity(self):
        done, lines = self.good_run(FAKE_AZ_DEPLOY_LOGIN="fail")
        self.assertEqual(done.returncode, 0)
        self.assertTrue([line for line in lines if line.startswith("FAIL: deploy identity sign-in: ERROR: AADSTS70021")], lines)
        self.assertEqual([call for call in self.calls if call.startswith("az group show") and "[config=none]" not in call], [], "no read with an identity that is not signed in")
        self.assertIn("ok: az login --identity", lines)
        self.assertEqual(lines[-1], "probe-done")

    def test_an_identity_or_a_tenant_that_is_not_given_is_said_and_nothing_is_tried(self):
        for name in ("PROBE_DEPLOY_CLIENT_ID", "PROBE_DEPLOY_TENANT_ID"):
            done, lines = self.good_run(**{name: ""})
            self.assertIn("FAIL: deploy identity sign-in: PROBE_DEPLOY_CLIENT_ID or PROBE_DEPLOY_TENANT_ID is not set", lines, name)
            self.assertEqual([call for call in self.calls if "--service-principal" in call], [], name)

    def test_a_deploy_identity_that_cannot_read_the_group_says_so_in_a_few_words(self):
        done, lines = self.good_run(FAKE_AZ_DEPLOY_GROUP="fail")
        self.assertIn("ok: az login as the deploy identity with the OpenID Connect token", lines)
        self.assertIn("FAIL: az group show as the deploy identity: ERROR: (AuthorizationFailed) The deploy identity doe", lines, "what the CLI said, cut to a few words")
        self.assertIn("ok: az group show of the project group: the Reader role works", lines, "the Operator's read is another one and still works")

    # --- pip and the build of the cases app's libraries ---------------------------------------------------------------------------------------------------------------------------------

    def build_run(self, **changes):
        """A run with nothing but the build test to do: a lock that arrived and a pip that behaves as FAKE_PIP says."""
        done, lines = self.run_probe({"PROBE_LOCK_BYTES": str(len(CASES_LOCK)), **changes}, lock=CASES_LOCK)
        self.assertEqual(done.returncode, 0)
        self.assertEqual(lines[-1], "probe-done")
        self.assertEqual(self.leftover, [], "the folder of the build is deleted whatever came of it")
        return self.without_seconds(lines), [call for call in self.calls if call.startswith("python3 -m pip install")]

    def test_the_build_runs_the_pip_command_of_the_build_script_for_python_3_13_into_a_folder_of_the_work_folder_and_the_lock_of_the_volume(self):
        lines, installs = self.build_run()
        self.assertEqual(lines[-3:], [f"ok: cases lock file is {len(CASES_LOCK)} bytes, as sent", "ok: cases build needs no --ignore-requires-python: 3 files, 1.5 MB, N s, hashes ok", "probe-done"])
        (install,) = installs
        self.assertRegex(install, r"--target /.+/probe-[^/]+/cases/\.python_packages/lib/site-packages --requirement /.+/op/cases-requirements\.txt \[PYTHONPATH=none\]$")
        self.assertNotIn("--ignore-requires-python", install)
        self.assertIn("--python-version 3.13", install)

    @staticmethod
    def pip_words(source):
        """The words of the first `python3 -m pip install` command of a script, without the folder and the file that it is given (they differ) and without the optional flag."""
        flat = re.sub(r"\\\n\s*", " ", source)
        command = re.search(r"python3 -m pip install (.+?)(?: 2>&1\))?\n", flat).group(1)
        words = shlex.split(command)
        kept = []
        skip = False
        for word in words:
            if skip:
                skip = False
            elif word in ("--target", "--requirement"):
                skip = True
            elif word != "$1":
                kept.append(word)
        return kept

    def test_the_pip_command_of_the_probe_is_the_one_of_the_build_script_in_every_flag_and_in_the_same_order(self):
        script, probe = self.pip_words(text("tools/build-function-app.sh")), self.pip_words(text("operator/probe.sh"))
        self.assertEqual(probe, script, "what the probe tries is what the build does: a flag that one has and the other has not would make its answer worth nothing")
        for flag in ("--only-binary=:all:", "--require-hashes", "--implementation", "--python-version", "--no-compile", "--platform"):
            self.assertIn(flag, probe)
        self.assertIn("3.13", probe, "the libraries are built for the app's runtime, whatever the interpreter of the image is")
        self.assertNotIn("--ignore-requires-python", probe, "the strict form comes first: the flag is the probe's second attempt, given as the one argument of the function")

    def test_when_the_first_attempt_fails_because_of_requires_python_the_second_adds_the_flag_and_the_probe_says_which_one_worked(self):
        lines, installs = self.build_run(FAKE_PIP="strict-fails")
        self.assertEqual(lines[-3:], ["FAIL: cases build without --ignore-requires-python: Requires-Python does not fit the interpreter",
                                      "ok: cases build only with --ignore-requires-python: 3 files, 1.5 MB, N s, hashes ok", "probe-done"])
        self.assertEqual(len(installs), 2)
        first, second = installs
        self.assertNotIn("--ignore-requires-python", first)
        self.assertEqual(second.replace(" --ignore-requires-python", ""), first, "the second attempt is the first and that one flag")

    def test_a_hash_a_name_or_a_timeout_is_not_tried_again_because_the_flag_would_not_change_it(self):
        for mode, said in (("hash", "a hash does not match the lock"), ("network", "a name was not resolved"), ("timeout", "timed out after 240 s")):
            lines, installs = self.build_run(FAKE_PIP=mode)
            self.assertEqual(lines[-2:], [f"FAIL: cases build: {said}", "probe-done"], mode)
            self.assertEqual(len(installs), 1, mode)

    def test_an_error_nobody_planned_for_is_tried_again_with_the_flag_and_both_failures_are_said_in_a_few_words(self):
        lines, installs = self.build_run(FAKE_PIP="other")
        failures = [line for line in lines if line.startswith("FAIL: cases build")]
        self.assertEqual(len(failures), 2, failures)
        self.assertTrue(failures[0].startswith("FAIL: cases build without --ignore-requires-python: ERROR: something that nobody planned for"), failures[0])
        self.assertTrue(failures[1].startswith("FAIL: cases build with --ignore-requires-python too: ERROR: something that nobody planned for"), failures[1])
        self.assertEqual(len(installs), 2)

    def test_without_pip_ensurepip_is_tried_into_the_work_folder_and_the_build_goes_on_with_the_pip_that_it_made(self):
        lines, installs = self.build_run(FAKE_PIP="missing")
        self.assertIn("FAIL: python3 -m pip is not there: /usr/bin/python3: No module named pip", lines)
        self.assertIn("ok: python3 -m ensurepip makes pip 24.0 in the work folder", lines)
        self.assertEqual(lines[-2], "ok: cases build needs no --ignore-requires-python: 3 files, 1.5 MB, N s, hashes ok")
        (ensure,) = [call for call in self.calls if call.startswith("python3 -m ensurepip")]
        self.assertRegex(ensure, r"^python3 -m ensurepip --root /.+/probe-[^/]+/ensurepip \[PYTHONPATH=none\]$", "into the work folder, not into the system's Python")
        (install,) = installs
        self.assertRegex(install, r"\[PYTHONPATH=/.+/probe-[^/]+/ensurepip/usr/lib/python3\.12/site-packages\]$", "and the pip that it made is the one that builds")

    def test_without_pip_and_without_a_working_ensurepip_the_build_is_skipped_and_the_probe_says_both(self):
        lines, installs = self.build_run(FAKE_PIP="missing", FAKE_ENSUREPIP="disabled")
        self.assertIn("FAIL: python3 -m pip is not there: /usr/bin/python3: No module named pip", lines)
        self.assertIn("FAIL: python3 -m ensurepip: ERROR: ensurepip is disabled in this Python: install the python3-pip", lines)
        self.assertEqual(lines[-2], "FAIL: cases build skipped: there is no pip")
        self.assertEqual(installs, [])

    def test_a_lock_file_that_is_missing_or_not_the_size_that_was_sent_is_said_and_the_size_of_one_that_nobody_measured_is_only_reported(self):
        done, lines = self.run_probe({"PROBE_LOCK_BYTES": "99"}, lock=CASES_LOCK)
        self.assertIn(f"FAIL: cases lock file is {len(CASES_LOCK)} bytes, 99 were sent", lines)
        self.assertTrue([line for line in lines if line.startswith("ok: cases build")], "a lock that differs is said, and the build is tried all the same")
        done, lines = self.run_probe({}, lock=CASES_LOCK)
        self.assertIn(f"ok: cases lock file is {len(CASES_LOCK)} bytes", lines)
        done, lines = self.run_probe({"PROBE_LOCK_BYTES": "99"})
        self.assertIn("FAIL: no cases-requirements.txt in the secret volume", lines)
        self.assertEqual([call for call in self.calls if call.startswith("python3 -m pip install")], [], "nothing is built without a lock")

    def test_nothing_is_built_when_the_output_is_already_full(self):
        env = {**self.good_env(), "PROBE_URLS": " ".join(f"ftp://host{i}.example.net/" for i in range(200))}
        done, lines = self.run_probe(env, size=4000, lock=CASES_LOCK)
        self.assertEqual(lines[-2], "FAIL: more checks than 120 lines hold; the rest was left out")
        self.assertEqual([call for call in self.calls if call.startswith("python3 -m pip install")], [], "a build that nobody could be told about is not made")

    # --- the deployment sites of the function apps ---------------------------------------------------------------------------------------------------------------------------------------

    def test_each_deployment_site_is_said_private_or_public_with_the_status_of_a_get_and_what_was_expected_to_be_private_is_failed_when_it_is_not(self):
        hosts = {"func-a.scm.azurewebsites.net": ("10.53.0.21", "401:0"), "func-b.scm.azurewebsites.net": ("20.50.1.2", "403:0"), "func-c.scm.azurewebsites.net": ("20.50.1.3", "302:0:login.example.net"),
                 "func-d.scm.azurewebsites.net": ("10.53.0.22", "000:28"), "func-e.scm.azurewebsites.net": ("10.53.0.23", "000:60"), "func-f.scm.azurewebsites.net": ("20.50.1.4", "503:0")}
        env = {"PROBE_SCM_HOSTS": " ".join(hosts) + " func-g.scm.azurewebsites.net bad*host",
               "PROBE_PRIVATE_NAMES": "func-a.scm.azurewebsites.net func-b.scm.azurewebsites.net func-f.scm.azurewebsites.net",
               "FAKE_DNS": " ".join(f"{host}={ip}" for host, (ip, _) in hosts.items()), "FAKE_CURL": " ".join(f"{host}={answer}" for host, (_, answer) in hosts.items())}
        done, lines = self.run_probe(env)
        scm = [line for line in lines if line.startswith(("ok: scm", "FAIL: scm"))]
        self.assertEqual(scm, ["ok: scm func-a: private address, GET / gives 401",
                               "FAIL: scm func-b: public address, expected private; GET / gives 403",
                               "ok: scm func-c: public address, GET / gives 302",
                               "FAIL: scm func-d: private address, GET / timed out (curl 28)",
                               "FAIL: scm func-e: private address, GET / certificate not trusted (curl 60)",
                               "FAIL: scm func-f: public address, expected private; GET / gives 503",
                               "FAIL: scm func-g: the name does not resolve",
                               "FAIL: scm: not a host name, skipped"])
        asked = [call for call in self.calls if call.startswith("curl")]
        self.assertEqual(len(asked), 6, "a name that does not resolve and a name that is not one are not asked")
        for call in asked:
            for word in ("--silent", "--output /dev/null", "--max-time 20", "--write-out %{http_code}"):
                self.assertIn(word, call, "the status and nothing else")
            for word in ("--location", "--max-redirs", "-H", "--header", "--user", "--data", "--request", "Authorization"):
                self.assertNotIn(word, call, "an unauthenticated GET that follows no redirect: the status is the site's own, and no content is kept")
            self.assertRegex(call, r" https://func-[a-f]\.scm\.azurewebsites\.net/$")
        self.assertEqual(lines[-1], "probe-done")

    # -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    def test_the_script_has_no_awk_and_no_jq_because_the_image_has_neither_to_rely_on(self):
        source = re.sub(r"(?m)^\s*#.*$", "", text("operator/probe.sh"))
        for word in (r"\bawk\b", r"\bjq\b", r"\bgawk\b", r"\bnslookup\b", r"\bdig\b", r"\bping\b", r"\bfind\s+[\"$./-]", r"\bgrep\b"):
            self.assertNotRegex(source, word, word)

    def test_the_script_names_only_what_it_may_read_from_the_environment(self):
        source = text("operator/probe.sh")
        used = set(re.findall(r"\$\{?(AZURE_FEDERATED_\w+|OPERATOR_\w+|PROBE_\w+|FAKE_\w+|GITHUB_\w+)", source))
        self.assertEqual(used, {"AZURE_FEDERATED_TOKEN", "OPERATOR_CLIENT_ID", "OPERATOR_GROUP", "OPERATOR_SUBSCRIPTION", "PROBE_NAMES", "PROBE_PRIVATE_NAMES", "PROBE_URLS", "PROBE_SIZE_BYTES",
                                "PROBE_SCM_HOSTS", "PROBE_DEPLOY_CLIENT_ID", "PROBE_DEPLOY_TENANT_ID", "PROBE_TOKEN_NOTE", "PROBE_LOCK_BYTES", "PROBE_VOLUME", "PROBE_RESOLV_CONF", "PROBE_TMP"})

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

    def run_tool(self, env=None, stubs=None, tool="cases-check", files=None, contents=None):
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
                           "TOOL_ARGS": "run --storage-account stexample --job all --minutes 20", "GITHUB_TOKEN": TOKEN_OF_THE_RUN, **(env or {})}
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
        self.assertEqual(ran.lines, ["ok: python3 3.12.7", "ok: az login --identity", "ok: running cases-check.py run", "tool output", "run-tool-done: exit code 0"])
        self.assertEqual(ran.calls, [f"az login --identity --client-id {CLIENT_ID} --allow-no-subscriptions --output none",
                                     f"tool-argv: [{ran.volume}/cases-check.py] [run] [--storage-account] [stexample] [--job] [all] [--minutes] [20]",
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
        self.assertEqual(ran.lines, ["ok: python3 3.12.7", "ok: az login --identity", "ok: running cases-check.py run", "run-tool-done: exit code 0"])
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
        for name in ("cases-check", "some-other-tool"):
            ran = self.run_tool(tool=name, files=["cases-check.py", "some-other-tool.py"], env={"TOOL_NAME": name})
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
        for value in (None, "", "../cases-check", "cases-check.py", "Cases-check", "cases check", "cases-check;touch canary", "cases_check", "1cases", "-cases",
                      "a" * 41, "cases-check\n", "$(touch canary)", "cases-check/x", "/etc/passwd"):
            self.refused({"TOOL_NAME": value}, files=["cases-check.py"])
        ran = self.refused({"TOOL_NAME": "some-other-tool"}, files=["cases-check.py"])
        self.assertIn("some-other-tool.py is not in the secret volume", ran.lines[0])
        self.refused({"TOOL_NAME": "cases-check"}, files=[])

    def test_arguments_that_are_empty_too_long_or_hold_anything_but_plain_characters_are_refused_without_being_printed_back(self):
        for value in (None, "", "   ", "r" * 601, "run " + "a" * 600):
            self.refused({"TOOL_ARGS": value})
        for character in ";&|$()`\"'<>*?!\\{}[]~#%,@+\n\t\r":
            ran = self.refused({"TOOL_ARGS": f"run --storage-account a{character}b touch canary"})
            self.assertNotIn("touch", ran.done.stdout, repr(character))
        for value in ("run --storage-account $(touch canary)", "run; touch canary", "run `touch canary`", "run --x=${HOME}", "run --x=a b\ntouch canary", "run --x=é", "run --x=*", "run --x=?"):
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
        value = "run --storage-account stexample.queue.core.windows.net --insights /subscriptions/sub-id/resourceGroups/rg_a.b/providers/Microsoft.Insights/components/appi-x --job all --minutes=20 --a:b -- -"
        ran = self.run_tool({"TOOL_ARGS": value})
        self.assertEqual(ran.done.returncode, 0)
        words = " ".join(f"[{word}]" for word in value.split())
        self.assertEqual(ran.tool_calls, [f"tool-argv: [{ran.volume}/cases-check.py] {words}"])
        # extra spaces between words, and at the ends, are not words
        ran = self.run_tool({"TOOL_ARGS": "  run   --job  all "})
        self.assertEqual(ran.tool_calls, [f"tool-argv: [{ran.volume}/cases-check.py] [run] [--job] [all]"])

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
        ran = self.run_real("cases-check", "functions --site not-an-id", ["cases-check.py", "check-helpers.py"])
        self.assertEqual(ran.done.returncode, 1, ran.done.stdout)
        version = "%d.%d.%d" % sys.version_info[:3]
        self.assertEqual(ran.lines, [f"ok: python3 {version}", "ok: az login --identity", "ok: running cases-check.py functions", self.SITE_ERROR, "run-tool-done: exit code 1"])
        self.assertEqual(ran.calls, [f"az login --identity --client-id {CLIENT_ID} --allow-no-subscriptions --output none", "sleep 20"], "the sign-in, nothing asked of Azure, and the hold")

    def test_the_console_check_runs_from_the_volume_on_its_own_with_the_arguments_of_the_workflow_and_its_door_refuses_a_name_that_is_none_before_it_asks_anything(self):
        # The check of a closed app's front door runs in the Operator (docs/proposals/07-private-by-default.md, the web page on the private network): the tool is the only file in the volume.
        ran = self.run_real("console-check", "door --host not_a_host --expect signin --private", ["console-check.py"])
        self.assertEqual(ran.done.returncode, 2, ran.done.stdout)
        version = "%d.%d.%d" % sys.version_info[:3]
        self.assertEqual(ran.lines, [f"ok: python3 {version}", "ok: az login --identity", "ok: running console-check.py door", "console-check: --host is a host name", "run-tool-done: exit code 2"])
        self.assertEqual(ran.calls, [f"az login --identity --client-id {CLIENT_ID} --allow-no-subscriptions --output none", "sleep 20"], "the sign-in, nothing asked of Azure, and the hold")

    def test_the_cases_check_needs_the_shared_helpers_in_the_same_folder(self):
        ran = self.run_real("cases-check", "functions --site not-an-id", ["cases-check.py"])
        self.assertEqual(ran.done.returncode, 1)
        self.assertIn("check-helpers.py", "\n".join(ran.lines), "without the helpers beside it the cases check stops at its import, and the log says which file is missing")
        self.assertEqual(ran.lines[-1], "run-tool-done: exit code 1")
        self.assertNotIn(self.SITE_ERROR, ran.lines)

    def test_a_tool_that_would_start_a_job_refuses_until_the_container_is_told_that_it_is_in_a_github_actions_run(self):
        insights = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.Insights/components/appi-example"
        args = f"run --storage-account stexample --insights {insights} --minutes 1"
        for tool, files, arguments in (("cases-check", ["cases-check.py", "check-helpers.py"], args),):
            ran = self.run_real(tool, arguments, files, GITHUB_ACTIONS=None)
            self.assertEqual(ran.done.returncode, 1, tool)
            self.assertIn("error: this command starts a job that writes to Azure, and only a GitHub Actions run may do that (AGENTS.md rule 18)", ran.lines, tool)
            self.assertEqual([call for call in ran.calls if call.startswith("az account")], [], "nothing was asked of Azure: the refusal comes first")


class TheToolsInTheContainer(unittest.TestCase):
    """The tools that the Operator runs are the very files of tools/, and they run in the image's Python 3.12 and from a folder that holds only the files that are sent."""

    TOOLS = ("cases-check.py",)
    HELPERS = ("check-helpers.py",)
    # The check of the web page's front door runs in the Operator too (a closed app answers nobody outside the network): it sends no event and loads no other tool, so it needs none of the checks below that
    # belong to the tool that sends one, and tools/tests/test_console_check.py runs it from a folder of its own.
    ALL_TOOLS = TOOLS + HELPERS + ("console-check.py",)

    def test_all_parse_as_python_3_12_and_import_the_standard_library_only(self):
        # CI and the function app use Python 3.13, the image of the Operator has 3.12: a syntax of 3.13 would pass every test here and fail in the container.
        import ast
        for name in self.ALL_TOOLS:
            tree = ast.parse(text(f"tools/{name}"), feature_version=(3, 12))
            imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
            imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
            self.assertLessEqual(imported, set(sys.stdlib_module_names), f"{name}: {sorted(imported - set(sys.stdlib_module_names))}")

    def test_the_tool_runs_from_a_folder_that_holds_only_it_and_its_helpers_like_the_secret_volume_and_the_cases_check_needs_the_helpers_beside_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            volume = Path(tmp)
            for name in self.TOOLS + self.HELPERS:
                (volume / name).write_bytes((ROOT / "tools" / name).read_bytes())
            for name in self.TOOLS:
                done = subprocess.run([sys.executable, "-B", str(volume / name), "run", "--help"], capture_output=True, text=True, cwd=volume)
                self.assertEqual((done.returncode, done.stderr), (0, ""), name)
                self.assertIn("--storage-account", done.stdout, name)
            self.assertEqual(sorted(path.name for path in volume.iterdir()), sorted(self.TOOLS + self.HELPERS), "nothing was written to the folder: no bytecode, no cache")
            (volume / "check-helpers.py").unlink()
            done = subprocess.run([sys.executable, "-B", str(volume / "cases-check.py"), "run", "--help"], capture_output=True, text=True, cwd=volume)
            self.assertNotEqual(done.returncode, 0, "cases-check.py loads check-helpers.py from its own folder, so both are sent")
            self.assertIn("check-helpers.py", done.stderr)

    def test_the_tool_refuses_to_send_outside_a_github_actions_run_which_the_container_is_told_it_is_in(self):
        # The Operator's group is made only by a run of the Hub workflow (operator-run.py refuses anywhere else), so the workflow tells the container so with GITHUB_ACTIONS=true.
        with tempfile.TemporaryDirectory() as tmp:
            for name in self.TOOLS + self.HELPERS:
                (Path(tmp) / name).write_bytes((ROOT / "tools" / name).read_bytes())
            insights = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.Insights/components/appi-example"
            for name in self.TOOLS:
                environment = {key: value for key, value in os.environ.items() if key != "GITHUB_ACTIONS"}
                done = subprocess.run([sys.executable, "-B", str(Path(tmp) / name), "run", "--storage-account", "stexample", "--insights", insights], capture_output=True, text=True, env=environment,
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
                      "A file of 400,000 bytes arrived intact", "about one to two minutes", "neither of the two fallbacks", "What is still open: the telemetry read once Application Insights is private",
                      "Publishing code to the private deployment sites is done for both apps: the Operator did it on 2026-11-06",
                      "the check of the function app's front door"):
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
                      "That the endpoint is authorised by that operation was inferred, and the first `recording-check` in the Operator showed it on 2026-11-06",
                      "**It ran, and it passed.**", "All four runs passed, so the token for `https://eventhubs.azure.net`, the send to the control hub over the private endpoint with the new role, and the telemetry read through Azure Resource Manager with Reader all worked.",
                      "\"can't use Azure Monitor private links\"", "the query of the tools stops working", "`https://api.applicationinsights.io/v1/apps/<appId>/query`", "a Microsoft Entra token for that resource",
                      "That is the next step, and it is not built here.", "is still made from the runner through Azure Resource Manager",
                      "1,500 seconds for `recording-check`", "2,400 seconds for `cases-run`", "`op-check-<run id>`", "A stopped container keeps only the last 16 KB of its log", "the script stays 20 seconds"):
            self.assertIn(words, section, words)

    def test_it_lists_the_two_roles_of_the_checks_the_order_of_the_work_and_what_is_not_checked_yet(self):
        roles = self.page.split("| Role | Where | What the Operator does with it | Added with |")[1].split("\n\n")[0]
        self.assertIn("| Azure Event Hubs Data Sender | The two control hubs, `usage-control` and `cases-control`, one role on each hub |", roles)
        self.assertIn("| Reader | The project's resource group |", roles)
        self.assertIn("| The checks (the action `operator`, run on 2026-11-06 with no hand step) |", roles)
        self.assertIn("Ran on 2026-11-06 and passed, before and after the namespace was made private: [below](#the-checks-of-the-usage-recording-and-the-first-cases-run-in-the-operator)", self.page)
        self.assertNotIn("Built, not yet run", self.page)
        self.assertIn("Azure Event Hubs Data Sender was in it already", self.page, "the role needs no hand step")
        self.assertIn("inside rule 29", self.page)
        order = self.page.split("## The order of the work")[1].split("\n## ")[0]
        for words in ("**The Operator and the probe** (done).", "**The checks run in the Operator** (done: both passed through it on the real estate on 2026-11-06, before and after step 4)", "The order on an estate is `recording`, `cases`, `operator`",
                      "about ten minutes are waited for them to apply", "Step 4 is not run before both have passed.", "**Event Hubs private** (done on 2026-11-06).", "Nothing that was still public had been switched off at that point.",
                      "it is a change of its own if it asks for one"):
            self.assertIn(words, order, words)
        for stale in ("not yet run when this page was written", "built, not yet deployed", "Nothing is private yet"):
            self.assertNotIn(stale, order, stale)
        not_checked = self.page.split("## Not checked")[1].split("\n## ")[0]
        open_part, closed_part = not_checked.split("**Closed by the runs of 2026-11-06**")
        for words in ("it did not make a connection to a private endpoint", "the token of the Operator's identity for `https://eventhubs.azure.net`", "Whether Python 3.12 of the image runs the two tools",
                      "whose python3 is 3.12 (read from its layers), and both checks passed"):
            self.assertIn(words, closed_part, words)
        self.assertIn("Whether the hold of 20 seconds", open_part)
        for source in ("permissions/monitor#microsoftinsights", "azure-ad-authentication#query-application-insights-by-using-microsoft-entra-authentication", "built-in-roles/general#reader"):
            self.assertIn(source, self.page.split("## Sources")[1], source)


class EventHubsPrivateOnlyRecord(unittest.TestCase):
    """The decision record and the bootstrap page on the change that makes the Event Hubs namespace private-only and retires the deploy identity's right to send to the control hubs."""

    HEADING = "## Event Hubs private-only (deployed and proven on 2026-11-06)"

    def setUp(self):
        self.page = text("docs/proposals/07-private-by-default.md")
        self.section = self.page.split(self.HEADING)[1].split("\n## ")[0]
        self.bootstrap = text("environment/BOOTSTRAP.md")
        self.bootstrap_section = self.bootstrap.split("## Changed on 2026-11-06: the Event Hubs namespace is private")[1].split("\n## ")[0]

    def test_the_status_the_table_and_the_order_say_that_it_is_deployed_and_proven_and_what_is_still_public_and_unknown(self):
        status = self.page.split("\n")[2]
        self.assertIn("The Event Hubs namespace is the first of the services that were still public to be switched off on the real estate: its public network access is Disabled (read back from Azure), the deploy identity's right to send to the two control hubs is retired, "
                      "the usage app woke from zero on the private namespace, and the public address refuses an anonymous request ([deployed and proven](#event-hubs-private-only-deployed-and-proven-on-2026-11-06)). "
                      "The cases app, Application Insights and the workspace are still public, and whether the gateway's two loggers reach the private namespace is not known yet.", status)
        for stale in ("Nothing is private yet", "built, not yet deployed", "([built, not yet run](#the-checks-of-the-usage-recording-and-the-first-cases-run-in-the-operator))"):
            self.assertNotIn(stale, status, stale)
        self.assertIn("([phase 1 of publishing code to the private apps](#publishing-code-to-the-private-apps-phase-1): done; the apps stay public)", status, "the status keeps what phase 1 says of itself")
        row = [line for line in self.page.split("\n") if line.startswith("| Event Hubs namespace |")][0]
        self.assertIn("**Disabled** on the real estate since 2026-11-06: the action `recording` deployed the template that sets it and read it back from Azure", row)
        self.assertNotIn("**Enabled**", row)
        order = self.page.split("## The order of the work")[1].split("\n## ")[0]
        self.assertIn("4. **Event Hubs private** (done on 2026-11-06).", order)
        self.assertIn("Step 4 is not run before both have passed.", order)
        self.assertNotIn("(inferred from what the setting means)", self.page, "Learn says what the setting does, and the row cites it")
        self.assertIn("Disable public access to your Event Hubs namespace to allow access only via private endpoints", self.page)
        self.assertIn("and it did so through the private namespace on 2026-11-06 ([the runs](#what-the-runs-showed-on-2026-11-06))", self.page)

    def test_it_says_what_changed_in_the_template_the_roles_the_workflow_and_the_read_back(self):
        self.assertTrue(self.section.lstrip().startswith("**What changed.**"), "the section says what changed, in the past")
        for words in ("sets the namespace's public network access to Disabled and keeps local authentication off and TLS 1.2", "It adds no network rule set and no trusted-service exception: nothing needs one.",
                      "no longer give the deploy identity Azure Event Hubs Data Sender on the control hub, and the parameter that fed that role is gone from both templates and from the parameter builder",
                      "The roles of the gateway (on the two usage hubs), of the two apps (receive, on their hubs) and of the Operator (send, on the two control hubs) are as they were, and a test pins each.",
                      "A template never deletes an assignment that it stops declaring, so each of the two actions has one idempotent step, after its deploy, that retires the assignment that exists.",
                      "deletes the one that is Data Sender by its id, reads back that it is gone, and says what it did", "It does nothing on a new estate (no hub yet, or no assignment), and it touches no other assignment.",
                      "lists Data Sender for a delete as well as for a write, and the real runs showed that the identity may delete its own assignment: no hand step was needed. "
                      "If Azure ever refuses (the condition changed, say), the step stops with Azure's message and says that a person deletes that one assignment",
                      "The action `recording` reads the namespace back from Azure after its deploy and fails unless public network access is Disabled, local authentication is off and its private endpoint connection is Approved"):
            self.assertIn(words, self.section, words)

    def test_it_says_who_calls_the_namespace_afterwards_and_the_runner_is_not_one(self):
        table = self.section.split("**Who calls the namespace afterwards.**")[1].split("**The order that was run**")[0]
        for words in ("| The usage app (three Event Hub triggers and the control hub's trigger) | Virtual network integration, private endpoint | It woke from zero on the private namespace, from the control event, and ran the three copy jobs",
                      "| The cases app (the control hub's trigger) | The same | On 2026-11-06 it ran on a Basic plan that is always on, so it had no wake from zero, and the Watch of `cases-run` passed after the flip; on Flex Consumption (since 2026-11-07) the trigger wakes it from zero as the usage app's does",
                      "| The Operator's container groups | Inside the network, the private endpoint | The probe resolved the namespace's name to a private address and made no connection to it. "
                      "The checks sent over it, before the flip and after it: after the flip the namespace takes nothing else, so that send proves the path |",
                      "| The deployment workflow's runner | None | It sends nothing and reads nothing from the namespace; a test pins that no step of `recording-check` or `cases-run` does. The public address refuses a request from outside since the flip",
                      "| The gateway (two loggers) | The private endpoint, over the peering | **Not known yet**:"):
            self.assertIn(words, table, words)

    def test_the_order_is_the_operator_the_checks_while_public_then_recording_then_cases_then_the_checks_again_and_the_way_back_is_a_revert(self):
        order = self.section.split("**The order that was run**")[1].split("**The way back**")[0]
        positions = [order.index(words) for words in ("1. `operator`, because the Operator did not hold Data Sender on both control hubs yet: it made both assignments, with no hand step.",
                                                      "2. `recording-check` and `cases-run`, through the Operator, **while the namespace was still public**.",
                                                      "3. `recording`: it deployed the template that makes the namespace private, read the namespace back, and retired the deploy identity's right on `usage-control`. Then `cases`: it retired the right on `cases-control`.",
                                                      "4. `recording-check` and `cases-run` again, as the proof. Both passed.", "5. The first call through the gateway that sends to the usage hubs, as the second proof: **not done yet**")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("**The way back** is to revert this change and run `recording` and `cases`: the earlier templates set public access Enabled again and give the deploy identity its role again.", self.section)

    def test_the_gateway_question_is_not_known_yet_cites_learn_and_says_how_the_first_call_will_show_it(self):
        part = self.section.split("### Whether the gateway reaches the private namespace")[1].split("\n### ")[0]
        for words in ("**Not known yet.**", "\"Effective 15 March 2026, Azure API Management is retiring trusted service connectivity by the API Management gateway to supported Azure services\"",
                      "\"needs alternative ways to communicate and have network line-of-sight\"", "api-management/breaking-changes/trusted-service-connectivity-retirement-march-2026", "dated 2026-01-15, updated 2026-06-25, read on 2026-11-06",
                      "the gateway can reach it only through the private endpoint, over the peering and the hub", "was not read in the landing zone and has not been tried",
                      "no API policy includes the `ai-usage` fragment, and nothing has sent to the `ai-usage` and `pii-usage` hubs (a measurement of 2026-11-06 found no message in 14 hours)",
                      "The namespace has been private since 2026-11-06, so the first call that sends is the test, and this stays open until then.",
                      "**How the first gateway call will show it.**", "The namespace's metric `IncomingMessages` (Total, one-minute grain), split by the dimension `EntityName`, has a count for `ai-usage`",
                      "`EventHubSuccessfulEvents` rises when it works, and `EventHubTimedoutEvents`, `EventHubTotalFailedEvents`, `EventHubRejectedEvents` (wrong configuration or unauthorized) or `EventHubDroppedEvents` rise when it does not",
                      "**If there is no path**, a public endpoint is not an option under the rule", "the answer is read from the first call and not guessed"):
            self.assertIn(words, part, words)
        self.assertIn("**The gateway's path to the namespace**, only if the first call through the gateway shows that there is none", self.page.split("## Decisions for the owner")[1].split("\n## ")[0])

    def test_the_flex_question_is_answered_by_a_run_keeps_the_learn_quote_and_says_what_the_pages_did_not_say(self):
        part = self.section.split("### The usage app wakes from zero on a private namespace")[1].split("\n### ")[0]
        for words in ("**Yes, for this app, and a run proved it.**", "the control event of `recording-check` arrived on `usage-control` through the private endpoint, the app woke from zero on it and ran the three copy jobs",
                      "\"The Flex Consumption plan natively supports virtual network triggers. Your function app can be triggered from event sources protected by a virtual network without requiring extra configuration for runtime scale monitoring\"",
                      "azure-functions/functions-networking-options", "dated 2026-09-15, updated 2026-10-16, read on 2026-11-06", "\"can connect to other Azure services secured inside a virtual network\"",
                      "azure-functions/flex-consumption-plan", "\"Private Event Hubs triggered function app\"", "**What the pages did not say, and the run showed.**",
                      "wakes from zero on an event hub whose public network access is Disabled, through an identity-based connection (`EventHubConnection__fullyQualifiedNamespace`), which is this app, "
                      "so the first `recording-check` after the flip was named as the proof. It is one run of one app, and it is the proof for this app.",
                      "an instance that is always ready for the control function, a standing price to be taken from the Retail Prices API, or a plan that does not scale to zero) are not needed"):
            self.assertIn(words, part, words)
        for stale in ("**What could not be verified.**", "Nothing has run.", "If no result arrives while `IncomingMessages`", "has been idle"):
            self.assertNotIn(stale, part, stale)

    def test_the_not_checked_list_and_the_sources_say_what_is_open_what_the_runs_closed_and_what_was_read(self):
        not_checked = self.page.split("## Not checked")[1].split("\n## ")[0]
        open_part, closed_part = not_checked.split("**Closed by the runs of 2026-11-06**")
        for words in ("**Open:**", "Whether a /27 is large enough.", "Whether the hold of 20 seconds", "Whether the list of the cases app's functions, which `cases` and `cases-run` make from the runner, still answers when that app is private.",
                      "Whether the gateway's two loggers reach the namespace",
                      "Whether the tenant's policy compliance record for the namespace turns Compliant. It still showed NonCompliant at 15:32 UTC on 2026-11-06, and its evaluation is asynchronous, so a refreshed state is not yet seen.",
                      "Whether the step that retires the deploy identity's right does nothing, and says so, when the assignment is gone. The first run of each action found the assignment, so that branch ran only against a stand-in for `az`"):
            self.assertIn(words, open_part, words)
        for words in ("Whether the namespace comes out of the deploy as the template wrote it.", "The step that reads the namespace back ran, and it printed Disabled, no local authentication and an Approved private endpoint connection.",
                      "Whether the deploy identity may delete its own old assignment. It may:", "in the source of the Azure CLI 2.92.0 (the scope is matched exactly unless inherited assignments are asked for, `--ids` deletes exactly the ids named) worked on the runner too.",
                      "Whether the usage app wakes from zero on an event that arrives only through the private endpoint. It does", "Whether the Operator's send reaches the namespace through the private endpoint with the role that has applied"):
            self.assertIn(words, closed_part, words)
        for stale in ("and it has not run", "not tried", "nobody has seen"):
            self.assertNotIn(stale, not_checked, stale)
        sources = self.page.split("## Sources")[1]
        for words in ("[Restrict Event Hubs namespace to private endpoints](https://learn.microsoft.com/azure/event-hubs/private-link-service)", "microsoft-eventhub-namespaces-metrics", "microsoft-apimanagement-service-metrics",
                      "[az role assignment](https://learn.microsoft.com/cli/azure/role/assignment)", "the generated Bicep types of `Microsoft.EventHub/namespaces` at 2024-01-01",
                      "the source of the Azure CLI 2.92.0 for `az role assignment list` and `delete`"):
            self.assertIn(words, sources, words)

    def test_the_bootstrap_page_says_no_hand_step_what_a_refusal_means_the_order_the_way_back_and_how_to_delete_by_id(self):
        section = self.bootstrap_section
        for words in ("**No hand step was needed.** It was deployed through the Hub on 2026-11-06 and every run passed", "sets `publicNetworkAccess: 'Disabled'` on the namespace (local authentication stays off and TLS 1.2 stays). It adds no network rule set and no trusted-service exception",
                      "no longer give the deploy identity *Azure Event Hubs Data Sender* on the control hub (`workflowSendsControl`), and the parameter `workflowPrincipalId` that fed it is gone from both templates and from the parameter builder",
                      "so one step in each of the two actions retires the assignment that exists", "deletes only the one that is *Azure Event Hubs Data Sender*, by its id, reads back that it is gone, and prints what it did",
                      "it never touches another assignment: the gateway's, the function apps' and the Operator's roles on the hubs stay", "reads the namespace back from Azure after the deploy and fails unless public network access is Disabled",
                      "**Why no hand step.**", "the runs of 2026-11-06: `recording` and `cases` each deleted the one assignment by its id and read back that it was gone, and Azure refused neither.",
                      "if Azure refuses the delete, the step stops with Azure's message and says what to do, and nothing else has changed", "A person then deletes that one assignment with their own sign-in, on the owner's written word",
                      "delete it by its id and never by a filter", "az role assignment delete --ids <id of the assignment>", "**The order**, on an estate where the namespace is still public:", "**while the namespace is still public**",
                      "**Done on the real estate on 2026-11-06:** steps 1 to 4, and every run passed. Step 5 is still open, because no gateway policy includes the `ai-usage` fragment yet, so nothing sends to the usage hubs.",
                      "on the real estate it did ([the answer](../docs/proposals/07-private-by-default.md#the-usage-app-wakes-from-zero-on-a-private-namespace))",
                      "**Going back.** Revert this change and run `recording` and `cases`"):
            self.assertIn(words, section, words)
        self.assertNotIn("it has not run", section)
        self.assertEqual(section.count("```powershell"), 1)
        self.assertEqual(sorted(set(re.findall(r"az role assignment (\w+)", section.split("```powershell")[1]))), ["delete", "list"])
        for anchor in ("#changed-on-2026-11-06-the-event-hubs-namespace-is-private",):
            self.assertIn(anchor, self.bootstrap)
        self.assertLess(self.bootstrap.index("## Changed on 2026-11-06: the Operator"), self.bootstrap.index("## Changed on 2026-11-06: the Event Hubs namespace is private"))
        self.assertLess(self.bootstrap.index("## Changed on 2026-11-06: the Event Hubs namespace is private"), self.bootstrap.index("\n## After it"))
        self.assertIn("holds none since [the namespace was made private](#changed-on-2026-11-06-the-event-hubs-namespace-is-private)", self.bootstrap.split("\n## ")[1])
        self.assertIn("The order of those three is `base`, `cases`, `operator`, and then, about ten minutes after `operator` (a new role takes that long to apply), `cases-run`. On 2026-11-06 the list held one more action, `recording-check`, and `base` was called `recording`: once both checks had passed through the Operator while the namespace was still public, `recording` made the Event Hubs namespace private",
                      self.bootstrap.split("\n## After it")[1])
        self.assertIn("On the real estate the Event Hubs steps of this list ran on 2026-11-06 and every run of them passed.", self.bootstrap.split("\n## After it")[1])

    def test_the_pages_that_said_that_the_workflow_sends_or_that_the_namespace_is_public_say_the_new_state(self):
        cases = text("docs/proposals/02-first-cases.md")
        self.assertIn("the deployment workflow starts it, through the Operator, which puts the message in the queue from inside the network and reads the result from the telemetry", cases)
        self.assertIn("The Operator may put messages in that queue (*Storage Queue Data Contributor* on the queue alone); the function reads it with the role that its host holds on the account already", cases)
        self.assertIn("The storage account takes no public traffic, so the runner cannot reach the queue at all", cases)
        self.assertNotIn("The workflow may send to that hub", cases)
        readme = text("README.md")
        self.assertIn("the namespace has been private-only since 2026-11-06, deployed and proven; the code of both function apps is published from inside the network, and the usage app takes no public traffic, deployed and proven; "
                      "the cases app, Application Insights and the workspace are still public", readme)
        self.assertIn("the template sets public network access to Disabled, the deploy identity no longer holds a role on the control hubs and the two deploy actions retired the one that it held", readme)
        self.assertIn("The Operator and its probe are built and ran on the real estate, the Event Hubs namespace and the usage app were private-only there from 2026-11-06 (deployed and proven; the usage app was removed on 2026-11-07), and the code of the function apps is published "
                      "from inside the network; the cases app, Application Insights and the workspace are still public", readme)
        bootstrap_first = self.bootstrap.split("\n## ")[1]
        self.assertNotIn("the gateway's identity and the workflow's identity may send to event hubs", bootstrap_first)
        self.assertNotIn("the workflow's identity gets", self.bootstrap)
        self.assertNotIn("gives the gateway's identity and the workflow's identity *Azure Event Hubs Data Sender*", self.bootstrap)
        self.assertNotIn("gives it to the gateway's identity and the workflow's identity)", self.bootstrap, "the usage recording no longer gives the workflow's identity a role on a hub")

    def test_no_page_still_calls_the_namespace_built_and_not_deployed_and_no_link_points_at_an_old_anchor(self):
        names = ("README.md", "docs/proposals/02-first-cases.md", "docs/proposals/07-private-by-default.md", "environment/BOOTSTRAP.md")
        pages = {name: text(name) for name in names + ("CHANGELOG.md",)}
        for name, page in pages.items():
            for anchor in ("event-hubs-private-only-built-not-yet-deployed", "whether-the-usage-app-wakes-from-zero-on-a-private-namespace"):
                self.assertNotRegex(page, r"\]\([^)\s]*#" + anchor + r"\)", f"{name} links to an anchor that no longer exists")
        for name in names:
            for stale in ("this change: built, not yet deployed", "([built, not yet deployed](#event-hubs", "nothing is private yet", "Nothing is private yet", "Whether it wakes from zero on a private namespace",
                          "whether the usage app wakes from zero on one", "It is built and not yet deployed", "private-only in the code, not yet deployed", "private-only (not yet deployed)"):
                self.assertNotIn(stale, pages[name], f"{name}: {stale}")
            for line in pages[name].split("\n"):
                if "not yet deployed" in line:
                    self.assertNotRegex(line.lower(), r"namespace|event hubs", f"{name}: a line that says 'not yet deployed' names the Event Hubs namespace: {line[:120]}")
        self.assertIn("## Event Hubs private-only (deployed and proven on 2026-11-06)", pages["docs/proposals/07-private-by-default.md"])
        changelog = pages["CHANGELOG.md"]
        newest = "## The Event Hubs namespace is private-only on the real estate (deployed and proven) — 2026-11-06"
        built = "## The Event Hubs namespace is private-only, and the deploy identity stops sending (built, not yet deployed) — 2026-11-06"
        self.assertLess(changelog.index(newest), changelog.index(built), "the entry that records the runs is above the one that records the build")

    def test_what_the_runs_showed_is_written_down_with_the_proofs_and_without_a_run_number_or_a_policy_name(self):
        part = self.section.split("### What the runs showed on 2026-11-06")[1].split("\n### ")[0]
        for words in ("The run pages of the Hub are the record.", "Times are UTC.",
                      "| `operator` (13:31) | Both assignments of Azure Event Hubs Data Sender for the Operator's identity were made, on `usage-control` and on `cases-control`. No hand step |",
                      "the three copy jobs reported ok (`llm-usage-ingestion` read 1 row and wrote 1), and 18 documents were in the container",
                      "The Watch ran 297 seconds: 6 leads, 12 cases (all of them needs-a-person), 17 tool calls and 33,621 tokens through Foundry",
                      "Only `publicNetworkAccess: Enabled => Disabled` on the namespace, besides the usual noise of tags",
                      "The read-back step printed that public network access is Disabled, local authentication is off and the private endpoint connection is Approved.",
                      "deleted it by its id and read back that it was gone. **The deploy identity may delete its own Data Sender assignment**: no hand step was needed",
                      "The deployment site took the package (HTTP 200), `/healthz` answered 200, and the function app's pages loaded in a browser check afterwards ([rule 28](../../AGENTS.md))",
                      "**The usage app woke from zero on the private namespace**, from the control event, and ran the three copy jobs; 18 documents in the container",
                      "The Watch ran 277 seconds, with 23 tool calls, and made no new case, because of the \"judged lately\" guard",
                      "Before the flip (14:14): HTTP 200 with the service's \"Publicly Listed Services\" feed. After it (15:10): HTTP 401 with \"Ip has been prevented to connect to the endpoint\"",
                      "One, at 15:14: \"An exception occurred while receiving events for Event Hub: cases-control\", partition 0, a minute after its publish restarted the app. The next run, at 15:22, worked, so it is taken to be the restart (inferred)",
                      "Still NonCompliant at 15:32. Its evaluation is asynchronous, so a refreshed state is not yet seen"):
            self.assertIn(words, part, words)
        self.assertNotRegex(self.page, r"\b[Rr]un [0-9]{3}\b", "the run numbers are in the changelog only")
        self.assertNotIn("pna-audit", self.page, "the name of a policy of the tenant is not in a committed page")


class PublishingPhaseOneRecord(unittest.TestCase):
    """docs/proposals/07-private-by-default.md, environment/BOOTSTRAP.md and the changelog: phase 1 of publishing code to the private apps is written down, with what it checks, what it does not, and the order."""

    HEADING = "## Publishing code to the private apps: phase 1"

    def setUp(self):
        self.page = text("docs/proposals/07-private-by-default.md")
        self.assertIn(self.HEADING, self.page)
        self.section = self.page.split(self.HEADING)[1].split("\n## ")[0]

    def test_it_names_the_three_phases_and_says_that_the_apps_stay_public_in_the_first(self):
        for words in ("This is phase 1: it changes nothing about how the code is published and nothing about who can reach the apps.", "| 1 | One private endpoint for each app, and a second set of checks in the probe",
                      "The apps stay public | done on 2026-11-06: the endpoints exist and every check of the probe passed |", "| 2 | The two publish steps run in the Operator, as the deploy identity, while the apps are still public",
                      "| 3 | `usageAppPublicNetworkAccess` and `casesAppPublicNetworkAccess`", "one value for each app"):
            self.assertIn(words, self.section, words)
        phases = self.section.split("| Phase | What | State |")[1].split("\n\n")[0]
        for words in ("done on 2026-11-06 for both apps: the usage app at the first attempt, and the cases app at the first attempt after a fix for a request that was too big ([phase 2](#publishing-code-to-the-private-apps-phase-2))",
                      "the check of the function app's front door and the cases app's health check move inside (the list of the functions does not have to: it answered for the usage app with its public access Disabled)",
                      "the usage app: **done and proven on 2026-11-06** (Azure shows Disabled, anonymous requests got HTTP 403, the Operator published into the app that was already private, "
                      "the runner's list of its functions answered, and `recording-check` passed: [phase 3 for the usage app](#publishing-code-to-the-private-apps-phase-3-for-the-usage-app-deployed-and-proven-on-2026-11-06))",
                      "the cases app: when the people who approve have a network path to the function app, which is the owner's decision, and its front-door check and health check move inside then"):
            self.assertIn(words, phases, words)
        for stale in ("built on 2026-11-06 (it has no page for people", "has not run again", "| later |"):
            self.assertNotIn(stale, phases, stale)

    def test_it_says_as_whom_the_operator_publishes_and_that_the_token_goes_nowhere_but_into_one_secure_value(self):
        for words in ("As the deploy identity, which holds the right to write to the apps already, and not as the Operator's own identity", "gets no role that writes, so [rule 29](../../AGENTS.md) stays as it is",
                      "no key, publish profile or personal access token exists", "the audience `api://AzureADTokenExchange`, the one that `azure/login` asks for", "valid for five minutes",
                      "which is why it is asked for last", "`--secure-env AZURE_FEDERATED_TOKEN`", "on no command line, in no `--env` value, in no file and in no line that the tool, the probe or the summary prints",
                      "`az login --service-principal --username <client id> --tenant <tenant id> --federated-token <token>`", "with a state folder of its own",
                      "and the probe of 2026-11-06 showed that it does: no hand step was needed", "its first step, `azure/login`, signs in with a token of the same audience and subject",
                      "the probe says why in that one line and goes on with the others"):
            self.assertIn(words, self.section, words)

    def test_it_says_how_the_usage_package_is_built_which_flag_is_tried_second_and_why_that_is_safe(self):
        for words in ("Neither package rides in the request", "the usage app's package is 7.0 MB zipped, and the cases app's is 614,068 bytes zipped", "this record first said about 2 MB for it, which was an estimate and was wrong",
                      "So each is built inside the container from the hash-locked lock file of its app",
                      "The probe builds the usage app's libraries from the hash-locked `src/usage-functions/requirements.txt` (since 2026-11-07 the probe builds the cases app's libraries from `src/case-functions/requirements.txt`)", "[`tools/build-function-app.sh`](../../tools/build-function-app.sh)",
                      "`--only-binary=:all: --require-hashes`", "Only the lock file rides in the request of the probe", "the image has Python 3.12", "Whether the build works from 3.12 was the main unknown of this phase, and the probe of 2026-11-06 answered it: it works, and without the flag",
                      "(inferred from pip 25.0.1, and the probe confirmed it)",
                      "pip is told `--python-version 3.13`", "so the probe tries that first", "`--ignore-requires-python`", "The flag is safe only because every version is pinned and every file is checked against its hash",
                      "A failure of the network, of a certificate or of a hash is not tried again with the flag"):
            self.assertIn(words, self.section, words)

    def test_it_lists_what_the_probe_checks_now_and_keeps_the_promises_of_the_first_probe(self):
        for words in ("One `ok:` or `FAIL:` line each, still at most 120 lines, never a token, always ending in `probe-done`, and still always exiting 0", "`python3 -m pip --version`, and `python3 -m ensurepip` when pip is not there",
                      "`az login --service-principal` as the deploy identity with the run's token, then `az group show` of the project's group as that identity", "The lines print no id",
                      "The usage app's lock file", "whether `--ignore-requires-python` was needed (the strict form is tried first), the number of files, the size in MB, the seconds, and that the hashes matched",
                      "`<app>.scm.azurewebsites.net` of each app", "a status only: no content is read and no redirect is followed", "A public address says that the landing zone's policy has not registered the name (yet)",
                      "The group is given 1,200 seconds now and not 900"):
            self.assertIn(words, self.section, words)

    def test_it_says_what_a_private_endpoint_needs_with_the_pages_and_their_dates_and_what_could_not_be_verified(self):
        for words in ("(Learn, read on 2026-11-06)", "functions-networking-options", "updated 2026-10-16", "overview-private-endpoint", "updated 2026-09-17", "That page does not list Flex Consumption, so the Functions page is the source for it",
                      "`sites` (`sites-<slot>` for a slot)", "`<app>.scm`", "`privatelink.azurewebsites.net`", "Inbound only", "`snet-func` and `snet-cases`, and the endpoints are in `snet-pe`",
                      "`vnetRouteAllEnabled: false`", "`vnetContentShareEnabled` does not apply", "overview-access-restrictions", "public access is on unless a private endpoint exists, and then it is off",
                      "the templates always write the value now", "a change of the value on a Linux app restarts it", "no zone, link or zone group is made ([rule 19](../../AGENTS.md))",
                      "**What could not be verified, when this phase was done, and what the later runs showed.** The waits for the apps' endpoints were added after the runs above and had not run then.",
                      "Whether the zone group that the waits ask for is what the policy makes for the endpoint of an App Service app",
                      "The records of both apps were in the central zone, which is what a zone group makes, but the zone group itself was not read",
                      "**Answered:** the waits passed in the runs that followed. The usage recording's said that the landing zone's policy had registered every private endpoint of the usage recording, the function app's own included, "
                      "and the `cases` run passed its own wait before it published.",
                      "Whether the deployment site of the Flex Consumption app takes a package from inside the network", "and the answer was 401", "Microsoft Q&A posts say that it runs only while one does", "that is not an official source",
                      "**Answered:** `config-zip` from the container published the usage app's package through the private endpoint, twice (once with the app public, once into the app that was already private), "
                      "and the cases app's deployment site took its package with a Kudu zip deployment (HTTP 200).",
                      "Whether the build inside the container gives the same files as the build on the runner", "the probe counted 900 files and 22.9 MB but did not compare them with the runner's package",
                      "no build made on the runner has been compared with one made in the container. **Still open.**",
                      "Whether the function app still opens from the machines of the people who use it",
                      "The function app loaded in a browser after the `cases` run of 2026-11-06, with one click on Microsoft's account picker, because the redeploy had ended the earlier session; "
                      "the machines of the other people who approve were not tested. **Still open** for them."):
            self.assertIn(words, self.section, words)
        for answered in ("Nothing of this phase has run in Azure.", "Whether the image has pip or `ensurepip`", "Whether the subject of the run's token matches the federated credential", "the probe and `cases` have not run with this phase",
                         "The waits for the apps' endpoints were added after the runs above and have not run.", "The first `recording` and `cases` after this change show it", "Phase 2 shows what the site accepts."):
            self.assertNotIn(answered, self.section, answered)

    def test_it_says_what_the_first_deploy_found_and_that_the_endpoint_of_each_app_is_waited_for_before_its_code_is_published(self):
        paragraph = self.section.split("**What the first deploy found (2026-11-06).**")[1].split("\n\n")[0]
        for words in ("The first `recording` after this phase failed at the publish of the usage app, three times", "Reset all workers endpoint responded with Name or service not known",
                      "A Flex Consumption deployment ends with a call from the deployment site to the app's own host name",
                      "a CNAME of `<app>.privatelink.azurewebsites.net`, for which the central zone has no record yet: the policy adds it about ten minutes later",
                      "the last step of the deployment fails although the package was taken", "held the main and `.scm` records of 35 apps when it was read by hand on 2026-11-06",
                      "The timing fits: the endpoint was made at 16:01 UTC, the three attempts failed between 16:04 and 16:08, the records were in the zone by 16:14, and a second run of `recording` between 16:14 and 16:22 published the code",
                      "so the policy exists and registers both names", "The endpoint of each app is therefore in the list of the endpoints that its action waits for, by DNS zone group like the others",
                      "the usage app's in `recording`, which waited for the five endpoints of the services before, and the cases app's in a step of its own in `cases`",
                      "A test fails a template that makes the endpoint of an app without that wait",
                      "The cases publish went from the runner to the public deployment site when this was written, and did not depend on DNS; since phase 2 it goes from the Operator through the private endpoint, "
                      "and the container stops unless both names of the app resolve to private addresses, so the wait is needed for it too"):
            self.assertIn(words, paragraph, words)
        self.assertNotIn("The cases publish goes from the runner to the public deployment site and does not depend on DNS", paragraph, "that was true until phase 2")
        for gone in ("nothing that works today can stop because of an endpoint", "The actions do not wait for it in this phase", "because nothing depends on the names yet"):
            self.assertNotIn(gone, self.section, gone)

    def test_it_says_what_the_second_probe_showed_in_plain_facts_and_no_id(self):
        paragraph = self.section.split("**What the second probe showed (2026-11-06, 16:37 UTC).**")[1].split("\n\n")[0]
        for words in ("It ran after both apps' endpoints existed and their names were registered in the central zone", "the zone held the records of 35 other apps",
                      "the names of the usage app appeared about 12 minutes after its endpoint was made, and those of the cases app about 12 minutes after its endpoint", "and every check passed",
                      "pip is missing from the image, and `python3 -m ensurepip` makes pip 25.0.1",
                      "The deploy identity signed in with the run's OpenID Connect token inside the container and read the project's group",
                      "The main name and the deployment name of both apps resolve to private addresses", "a `GET /` of both deployment sites answers 401 without a sign-in",
                      "built in the image's Python 3.12 without `--ignore-requires-python`: 900 files, 22.9 MB, 7 seconds, and the hashes matched"):
            self.assertIn(words, paragraph, words)
        self.assertNotRegex(paragraph, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", "no id of the tenant, the subscription or an object")
        self.assertLess(self.section.index("**What the first deploy found (2026-11-06).**"), self.section.index("**What the second probe showed (2026-11-06, 16:37 UTC).**"))
        self.assertLess(self.section.index("**What the second probe showed (2026-11-06, 16:37 UTC).**"), self.section.index("**What a person runs, in order.**"))

    def test_it_says_what_changed_in_the_templates_the_order_a_person_runs_the_one_side_effect_and_the_cost(self):
        for words in ("`pe-<app name>`, for the sub-resource `sites`, in the endpoint subnet `snet-pe`", "It is written after every other write to the app", "(`Enabled` or `Disabled`, default `Enabled`)",
                      "Phase 3 is one changed constant for each app", "The endpoint subnet holds nine endpoints now", "(inferred: eleven are left)",
                      "1. `recording`, and then `cases`. Each makes its app's private endpoint, waits until the landing zone's policy has registered it in the central zone (about ten minutes, at most 40 checks a minute apart), "
                      "and only then publishes the code. The apps stay public.",
                      "2. `operator-probe`, and read its lines in this order of questions", "3. Phase 2 is built from the answers.",
                      "Steps 1 and 2 ran on 2026-11-06: the first `recording`, which did not wait for the app's names yet, failed at the publish and was run again once they were registered, and the probe passed (above). "
                      "Step 3 was phase 2, which is done ([below](#publishing-code-to-the-private-apps-phase-2)).",
                      "a client that resolves it through the landing zone's DNS gets the private address, with or without a route to it",
                      "After `cases`, which waits for the registration, resolve the function app's name and open the function app from the machine that is used for it",
                      "The way back is deleting the endpoint, which no workflow action does: by hand, break-glass ([rule 18](../../AGENTS.md))", "about 6.57 euros a month", "so the two cost about 13"):
            self.assertIn(words, self.section, words)
        self.assertLess(self.section.index("1. `recording`, and then `cases`."), self.section.index("2. `operator-probe`"))
        self.assertNotIn("Wait about ten minutes", self.section, "the actions wait, so a person does not")

    def test_the_state_table_the_order_of_the_work_the_decisions_and_the_sources_say_the_same(self):
        state = self.page.split("## The rule and the state")[1].split("\n## ")[0]
        self.assertIn("the parameter `usageAppPublicNetworkAccess` | one, for the app and its deployment site (made on 2026-11-06; both names are registered in the central zone)", state)
        self.assertIn("the parameter `casesAppPublicNetworkAccess` | one, for the app and its deployment site (made on 2026-11-06; both names are registered in the central zone)", state)
        order = self.page.split("## The order of the work")[1].split("\n## ")[0]
        self.assertIn("It is done in three phases ([above](#publishing-code-to-the-private-apps-phase-1))", order)
        self.assertIn("both records of each app were there about 12 minutes after its endpoint was made, on 2026-11-06", order)
        self.assertIn("The actions wait for the registration of each app's endpoint before they publish.", order)
        self.assertIn("the endpoints and a second set of checks in the probe, with the apps still public (done on 2026-11-06: both endpoints exist, and every check of the probe passed)", order)
        self.assertIn("the publish steps through the Operator, still with the apps public (done on 2026-11-06 for both apps: [phase 2](#publishing-code-to-the-private-apps-phase-2)); and then `Disabled` for each app, "
                      "with the cases app's health check moved inside and its access check made through the gateway's host name. The usage app is done and proven ([the section](#publishing-code-to-the-private-apps-phase-3-for-the-usage-app-deployed-and-proven-on-2026-11-06)); "
                      "the cases app is built for the gateway and waits for the gateway objects and the owner's yes ([phase 3 for the cases app](#publishing-code-to-the-private-apps-phase-3-for-the-cases-app-the-console-behind-the-platforms-application-gateway-built-not-deployed)).", order)
        self.assertNotIn("not read in the landing zone; a fact to check, which the probe reports", order)
        decisions = self.page.split("## Decisions for the owner")[1].split("\n## ")[0]
        self.assertIn("changes three of the decisions below", decisions)
        self.assertIn("no Website Contributor for the Operator (it publishes as the deploy identity, which holds the right already)", decisions)
        not_checked = self.page.split("## Not checked")[1].split("\n## ")[0]
        self.assertIn("Phase 1 of publishing code ([above](#publishing-code-to-the-private-apps-phase-1)): the endpoints and the probe ran on 2026-11-06 and every check passed (what the second probe showed, above). "
                      "The two waits and what a deployment site accepts from inside the network are in the closed list below. Open: whether the function app still opens from the machines of the people who use it", not_checked)
        self.assertNotIn("the probe has not run, and the first `recording` failed at the publish", not_checked)
        sources = self.page.split("## Sources")[1]
        for page in ("functions-networking-options", "functions-deployment-technologies", "overview-access-restrictions", "cli/azure/reference-index", "actions/reference/security/oidc"):
            self.assertIn(page, sources, page)
        status = self.page.split("\n")[2]
        self.assertTrue(status.startswith("**Status: decided on 2026-11-06"), status[:80])
        self.assertIn("[phase 1 of publishing code to the private apps](#publishing-code-to-the-private-apps-phase-1): done; the apps stay public", status)
        self.assertIn("The two function apps have a private endpoint each since the same day, and the second set of checks of the probe, which learns what publishing code from the Operator needs, ran on the real estate and passed every check", status)

    def test_the_bootstrap_page_says_that_no_hand_step_is_needed_and_in_what_order_to_run(self):
        page = text("environment/BOOTSTRAP.md")
        heading = "## Changed on 2026-11-06: publishing code from inside the network, phase 1"
        self.assertIn(heading, page)
        paragraph = page.split(heading)[1].split("\n## ")[0]
        for words in ("**No hand step is needed.**", "[The decision record](../docs/proposals/07-private-by-default.md#publishing-code-to-the-private-apps-phase-1)", "This is the first of three phases, and the apps stay public in it",
                      "about 6.57 euros a month each", "the sub-resource `sites`, in `snet-pe`",
                      "no DNS zone, link or zone group", "a parameter that stays `Enabled`, so the apps stay public", "audience `api://AzureADTokenExchange`", "the workflow's `id-token: write` permission is all it needs",
                      "as one secure value", "Nothing is added to the deploy identity and no credential changes", "the first step of the same job, `azure/login`, signs in with a token of the same audience and subject",
                      "a person decides, on the owner's word", "nothing is guessed here", "accepts it, and the probe of 2026-11-06 showed that it does.",
                      "The actions `recording` and `cases` also wait, after their deploy and before they publish, until the landing zone's policy has registered each app's endpoint in the central zone "
                      "(about ten minutes, at most 40 checks a minute apart; `cases` has a step of its own, `recording` waits for the app's endpoint with the five of the services)",
                      "the first `recording` without that wait failed at the publish, because the app's own name did not resolve yet", "The order is `recording`, `cases`, and then `operator-probe`."):
            self.assertIn(words, paragraph, words)
        self.assertNotIn("about ten minutes of waiting for the landing zone's policy", paragraph)
        after = page.split("\n## After it")[1].split("\n## ")[0]
        self.assertIn("Since phase 1 of publishing code from inside the network, the action `cases` also makes the cases app's private endpoint and waits until the landing zone's policy has registered it "
                      "(`recording` did the same for the usage app's until 2026-11-07); after that, "
                      "`operator-probe` is run once more and its lines are read ([the section](#changed-on-2026-11-06-publishing-code-from-inside-the-network-phase-1)). "
                      "On the real estate the endpoints were made and the probe ran on 2026-11-06, and every check of the probe passed.", after)
        self.assertNotIn("about ten minutes after those runs", after, "the actions wait for the names now, so a person does not")
        self.assertNotIn("The same runs of `recording` and `cases`", after, "'the same runs' was ambiguous next to the sentence about the Event Hubs runs")
        self.assertLess(after.index("On the real estate the Event Hubs steps of this list ran on 2026-11-06"), after.index("Since phase 1 of publishing code"))
        self.assertLess(after.index("Since phase 1 of publishing code"), after.index("One yes to the whole list"))

    def test_the_changelog_says_what_the_owner_said_what_changed_what_was_not_checked_and_what_a_person_runs_in_order(self):
        changelog = text("CHANGELOG.md")
        heading = "## Publishing code to the private apps, phase 1: a private endpoint for each function app and a second probe (built, not yet run) — 2026-11-06"
        self.assertIn(heading, changelog)
        entry = changelog.split(heading)[1].split("\n## ")[0]
        for words in ("**What the owner said.**", "no resource of the project has a public endpoint (private endpoints only), and no key exists anywhere", "**What changed.**", "`usageAppPublicNetworkAccess` and `casesAppPublicNetworkAccess`",
                      "no private DNS zone, no link and no zone group", "`--secure-env AZURE_FEDERATED_TOKEN`", "1,200 seconds and not 900", "**Cost.**", "about 6.57 euros a month", "about 13",
                      "**What was checked.**", "**Not checked, and why it matters.**", "Nothing ran in Azure", "**What a person has to do, in order.**", "`operator-probe`",
                      "(2) The actions wait for the landing zone's policy to register the names before they publish (the entry about the wait, above: the first run without that wait failed).",
                      "whether the landing zone registers the names of the `sites` sub-resource in its central zone (it does: see the entry about the wait, above)"):
            self.assertIn(words, entry, words)
        self.assertLess(entry.index("`recording`"), entry.index("`cases`"))
        self.assertLess(entry.index("(2) The actions wait"), entry.rindex("`operator-probe`"))
        self.assertNotIn("wait about ten minutes", entry, "the actions wait, so a person does not")

    def test_the_changelog_says_what_failed_why_what_changed_what_was_not_checked_and_what_a_person_runs_in_order_for_the_wait_for_the_apps_endpoints(self):
        changelog = text("CHANGELOG.md")
        heading = "## The private endpoints of the two function apps are waited for before their code is published (built, not yet run) — 2026-11-06"
        self.assertIn(heading, changelog)
        entry = changelog.split(heading)[1].split("\n## ")[0]
        for words in ("**What failed.**", "made the usage app's private endpoint at 16:01 and failed at the step \"Publish the usage functions to the function app\", three attempts (between 16:04 and 16:08)",
                      "Deployment was successful but Reset all workers endpoint responded with Name or service not known",
                      "had passed at once, because the app's own endpoint was not in its list", "The records of the app's names were in the central zone by 16:14, and a second run of `recording`, from 16:14 to 16:22, published the code",
                      "**Why.**", "A Flex Consumption deployment ends with a call from the deployment site to the app's own host name",
                      "the central zone `privatelink.azurewebsites.net` has no record of it yet: the landing zone's policy adds it about ten minutes later", "the last step fails although the package was taken",
                      "the second run fits it: the publish went through once the records existed",
                      "Two things in phase 1 were wrong", "nothing that works today can stop because of an endpoint", "held the main and `.scm` records of 35 apps when it was read by hand today",
                      "It registered the names of both apps, about 12 minutes after each endpoint was made",
                      "**What changed.**", "`recording_endpoints()` now lists the usage app's endpoint", "six in all", "`cases_endpoints`", "`APP_ENDPOINT_ZONE`",
                      "\"Wait until the landing zone has registered the cases app's private endpoint in the central zone\"", "40 checks a minute apart", "about 50 minutes, inside the job's 150",
                      "**What the probe of phase 1 showed (16:37).**", "pip is missing from the image, and `python3 -m ensurepip` makes pip 25.0.1", "without `--ignore-requires-python`: 900 files, 22.9 MB, 7 seconds, and the hashes matched",
                      "answers 401 without a sign-in", "are as the session that ran the Hub passed them on, and were not measured again here",
                      "**Not checked, and why it matters.**", "I called nothing in Azure", "The waits have not run", "**What a person has to do, in order.**"):
            self.assertIn(words, entry, words)
        self.assertNotRegex(entry, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", "no id of the tenant, the subscription or an object")
        self.assertNotIn("@@", entry, "no placeholder is left")
        self.assertLess(entry.index("**What changed.**"), entry.index("**What the probe of phase 1 showed (16:37).**"))
        self.assertLess(entry.index("**What the probe of phase 1 showed (16:37).**"), entry.index("**What was checked.**"))
        order = entry.split("**What a person has to do, in order.**")[1]
        self.assertLess(order.index("**`recording`**"), order.index("**`cases`**"))
        self.assertIn("Open the console once from the machine that is used for it", order)
        self.assertIn("Phase 2, the publish steps through the Operator while the apps are still public, is the next change", order)
        self.assertNotIn("**`operator-probe`**", order, "the probe has run: a person is not asked to run it for this change")
        self.assertLess(changelog.index("## The code of both function apps is published from inside the network, in the Operator"),
                        changelog.index("## The private endpoints of the two function apps are waited for before their code is published"),
                        "the entry of phase 2 is above the entry of the wait for the endpoints, which is the one below it")
        self.assertLess(changelog.index(heading), changelog.index("## The Event Hubs namespace is private-only on the real estate (deployed and proven)"))
        self.assertLess(changelog.index("## The Event Hubs namespace is private-only on the real estate (deployed and proven)"), changelog.index("## Publishing code to the private apps, phase 1"))


class PublishingPhaseTwoRecord(unittest.TestCase):
    """docs/proposals/07-private-by-default.md, environment/BOOTSTRAP.md and the changelog: phase 2 of publishing code to the private apps is written down, with what it relies on, what it does, what is
    not verified, and the order a person runs."""

    HEADING = "## Publishing code to the private apps: phase 2"
    CHANGELOG_HEADING = "## The code of both function apps is published from inside the network, in the Operator (built, not yet run) — 2026-11-06"

    def setUp(self):
        self.page = text("docs/proposals/07-private-by-default.md")
        self.assertIn(self.HEADING, self.page)
        self.section = self.page.split(self.HEADING)[1].split("\n## ")[0]

    def test_it_says_what_the_two_actions_do_that_the_runner_publishes_nothing_and_that_the_apps_stay_public(self):
        for words in ("The Hub actions `recording` and `cases` publish the code of their app from inside the network: in a short-lived container group of the Operator, through the app's private endpoint, "
                      "as the deploy identity, with the OpenID Connect token of the run", "The runner publishes nothing any more. There is one path, so that it is the one that is proven.",
                      "The Operator's own identity still holds no right that writes", "no key, publish profile or personal access token exists",
                      "The apps stay public in this phase (`usageAppPublicNetworkAccess` and `casesAppPublicNetworkAccess` stay `Enabled`)", "the point is to prove the private path before anything is closed. No resource of a template changed: only the comments of the two templates and the description of one parameter, which said that the runner publishes, now say how the code is published.",
                      "The usage app was closed afterwards, as a change of its own ([phase 3 for the usage app](#publishing-code-to-the-private-apps-phase-3-for-the-usage-app-deployed-and-proven-on-2026-11-06)).",
                      "Both apps were published this way on the real estate on 2026-11-06 (what the runs showed is below): the usage app at the first attempt, and the cases app at the first attempt after a fix, "
                      "because its finished package had been too big for the request. Both are built in the container from their sources."):
            self.assertIn(words, self.section, words)
        self.assertNotIn("The first runs on the real estate are below: the usage app was published this way at the first attempt, and the cases app was not", self.section)

    def test_it_lists_what_the_probe_of_phase_1_proved_and_that_the_two_other_facts_are_the_waits_and_the_five_minutes(self):
        paragraph = self.section.split("**What the probe of phase 1 proved, which this relies on**")[1].split("\n\n")[0]
        for words in ("The image's `python3` is 3.12.15 and has no pip, and `python3 -m ensurepip` makes pip 25.0.1 in a work folder", "The deploy identity signs in with the run's token inside the container and reads the project's group",
                      "`curl`, `getent` and `az` are in the image, and no `zip` or `unzip` is guaranteed, so Python's `zipfile` makes and opens the zip files",
                      "The main name and the deployment name of both apps resolve to private addresses, and a `GET /` of both deployment sites answers 401 without a sign-in",
                      "build in the image's Python 3.12 from the lock file with the pip command of the build script, without `--ignore-requires-python`",
                      "a Flex Consumption deployment ends with a call to the app's own host name through the landing zone's DNS (the reason for the waits)",
                      "the deploy identity's token lasts five minutes, so the container signs in first"):
            self.assertIn(words, paragraph, words)

    def test_it_says_what_the_runner_and_the_container_do_in_each_action_and_what_stays_on_the_runner(self):
        table = self.section.split("**The steps of the two actions**")[1].split("\n\n")[1]
        for words in ("| `recording` (usage app, Flex Consumption) |", "Packs the app's **sources**: `function_app.py`, `host.json`, the hash lock `requirements.txt` and the `usage` package, about 35 KB zipped, with no libraries, tests or caches",
                      "Checks the sources, the build script and the container script against the cap of the tool",
                      "makes the container group `op-publish-<run id>` with the sources, the build script and the container script in its secret volume",
                      "builds the libraries from the lock with the pip command of the build script (under the image's Python 3.12), zips the package, and runs `az functionapp deployment source config-zip --build-remote false`, three attempts a minute apart",
                      "| `cases` (cases app, Basic plan or Flex Consumption) |", "Packs the app's **sources**, as for the usage app: `function_app.py`, `host.json`, the hash lock `requirements.txt` and the `cases` package, 208,046 bytes zipped on the runner",
                      "Checks the sources, the build script and the container script against the cap of the tool. Finds the Operator",
                      "asks for an Azure Resource Manager token as the deploy identity, builds the libraries from the lock with the pip command of the build script (under the image's Python 3.12), "
                      "zips the package (614,068 bytes on the runner, more than a request takes), and posts the built package to the deployment site's `api/zipdeploy` with `curl` (the bearer on standard input), five attempts a minute apart, HTTP 200 or 202 accepted "
                      "(on a Basic plan; on Flex Consumption it publishes the built package with `az functionapp deployment source config-zip`, as for the usage app, three attempts a minute apart"):
            self.assertIn(words, table, words)
        self.assertNotIn("finished package** with its libraries", table, "the runner builds no libraries of either app any more")
        for words in ("Everything after the publish stays on the runner: the list of the functions, the health check of the cases app and the summaries.",
                      "Azure Resource Manager reads work from the runner for an app whose public access is Disabled: the list of the usage app's functions answered once that app was private",
                      "after it had been read on other apps of the landing zone (a read-only check on 2026-11-06, as the session that coordinates the work reported it)",
                      "The health check of the cases app moves inside when that app is closed.",
                      "so `recording` signs in once more before the list of its functions"):
            self.assertIn(words, self.section, words)
        self.assertNotIn("and the health check and the list move inside in phase 3", self.section, "the list of the functions did not have to move: it answered for the private usage app")

    def test_it_says_that_the_build_is_one_script_in_three_modes_with_one_pip_command_and_a_test_that_pins_it(self):
        paragraph = self.section.split("**One build, in two places.**")[1].split("\n\n")[0]
        for words in ("stays the one place that knows how a package is built", "`--only-binary=:all:`, `--require-hashes`, the three manylinux platform flags, `--implementation cp --python-version 3.13`",
                      "By default it is the runner's build, with the guard that the running interpreter is Python 3.13, as before.",
                      "`FUNCTION_APP_SOURCES_ONLY=1` copies the app's files and zips them and does nothing else", "`FUNCTION_APP_BUILD_IN_OPERATOR=1`, set only by the container script, replaces the guard by two checks "
                      "(pip runs, and the lock carries hashes), makes the zip with Python, and fails the build when pip left a compiled module for another Python than 3.13",
                      "The two switches cannot be set together, and any value but `1` is refused.", "pins that the pip words are identical and that the two zips hold the same files"):
            self.assertIn(words, paragraph, words)

    def test_it_says_what_the_container_script_checks_in_which_order_and_what_its_exit_codes_mean(self):
        paragraph = self.section.split("**The container script.**")[1].split("\n\n")[0]
        for words in ("takes everything from its environment, checks it before anything runs (nothing is evaluated and no value is printed back)", "ends with `publish-done: exit code N`",
                      "The container stays 20 seconds after the work", "the deploy identity signs in, which is the first `az` call (three tries)",
                      "the token that the publish needs is fetched at once, while the sign-in's assertion, which lives five minutes, is fresh",
                      "for the usage app a token for the App Service resource, because Flex Consumption's `config-zip` asks Microsoft Entra for one (read in the Azure CLI's development source, not in 2.92.0, and not run; "
                      "a failure is said and does not stop the run, and the first usage run had it and passed)",
                      "for the cases app a token for Azure Resource Manager, which is the bearer of the post (a failure stops the run)",
                      "**both names of the app must resolve to a private address** (three tries each)",
                      "a public path would prove nothing", "then the package is built from the sources, the same way for both apps (pip made by `ensurepip` in a work folder, the build script in the Operator's mode, two attempts)",
                      "then the publish of its kind", "A string that looks like a token is hidden in anything a command said", "the work folder, with the state of the Azure CLI, is deleted at the end",
                      "The exit code is 0 when the code was published, 1 when the publish failed after its attempts, 2 when the input was refused and nothing was run, and 3 when the container could not do it"):
            self.assertIn(words, paragraph, words)
        order = ("the size of the file in the volume is compared", "the deploy identity signs in", "the token that the publish needs is fetched at once", "**both names of the app must resolve",
                 "then the package is built from the sources", "then the publish of its kind")
        for earlier, later in zip(order, order[1:]):
            self.assertLess(paragraph.index(earlier), paragraph.index(later), f"{earlier} comes before {later}")

    def test_it_says_how_long_the_groups_are_given_and_why_and_what_the_first_run_on_an_estate_needs(self):
        time = self.section.split("**The time.**")[1].split("\n\n")[0]
        for words in ("The usage group is given 2,400 seconds and its step 45 minutes; the cases group 1,200 seconds and its step 25.", "A good run takes minutes", "The limits are for a run that is stuck.",
                      "a step of its own deletes any `op-publish-` group that a cancelled step left", "the step's limit is five minutes behind the group's",
                      "If every command used its whole limit, the attempts would take longer than the group is given; that is intended", "cut by the job's own limit of 150 minutes, and running the action again is safe"):
            self.assertIn(words, time, words)
        first = self.section.split("**The first run on an estate.**")[1].split("\n\n")[0]
        for words in ("Both actions need the Operator, which `operator` makes, and `operator` needs the control hubs that `recording` and `cases` make.",
                      "`recording` and `cases` deploy and then stop at the publish with a plain message that says to run `operator` first (the step changes nothing)",
                      "the order is `recording`, `cases`, `operator`, and then `recording` and `cases` again, the second round publishing. The Hub summaries say so."):
            self.assertIn(words, first, words)

    def test_it_says_what_the_runs_showed_the_defect_in_plain_words_and_the_cases_run_after_the_fix(self):
        paragraphs = self.section.split("**What the runs showed**")[1].split("\n\n")[:3]
        usage, defect, cases = paragraphs
        for words in ("(2026-11-06, UTC, as the session that ran the Hub reported them)", "`recording` (19:12 to 19:23) published the usage app from the Operator at the first attempt: the container ran 169 seconds",
                      "the sign-in as the deploy identity worked, the token for the App Service resource was fetched, both names of the app resolved to private addresses",
                      "the image's Azure CLI was 2.92.0, `ensurepip` made pip 25.0.1", "the sources were 15 files, the build gave 914 files and 7.0 MB zipped in 8 seconds with the hashes checked",
                      "`config-zip` published the package through the private endpoint, and the group was deleted",
                      "the path through the private endpoint, the sign-in as the deploy identity, and Flex Consumption's `config-zip` from the image's Azure CLI are verified for the usage app"):
            self.assertIn(words, usage, words)
        for words in ("**The defect, in plain words.**", "`cases` failed twice (19:25 and 19:31), at the step that makes the container group, with an Azure Resource Manager \"InternalServerError\" "
                      "(\"Encountered an internal server error\"), and no container ran.",
                      "The request held the finished package and the container script, 632,656 bytes of files, and a request takes less than that: the tool's limit of 3,000,000 bytes had been an assumption (the evidence is above).",
                      "Nothing was published, the template and the waits before the publish had done their work, and running the action again was safe.",
                      "The fix builds the cases app in the container from its sources, as the usage app is built, and caps the files of a request at 480,000 bytes."):
            self.assertIn(words, defect, words)
        for words in ("**The cases app, after the fix.**", "`cases` (20:33 to 20:39) published the app from the Operator at the first attempt: the container ran 92 seconds, the file of sources was 208,046 bytes, "
                      "the sources were 54 files, the build gave 208 files and 0.5 MB zipped in 3 seconds with the hashes checked",
                      "the deployment site took the package (HTTP 200, attempt 1 of 5), `/healthz` answered 200, the check of the function app's front door passed all its lines, and the function app loaded in a browser afterwards.",
                      "The redeploy had ended the earlier session, so Microsoft's account picker came up once and the sign-in completed with a click; the pages then showed.",
                      "In the container's log, megabytes (of 1,048,576 bytes) are cut to one decimal, so 0.5 MB agrees with the 614,068 bytes that the runner's build of the cases package had given.",
                      "So phase 2 is done for both apps: the Kudu zip deployment from the container is seen too."):
            self.assertIn(words, cases, words)
        for paragraph in paragraphs:
            self.assertNotRegex(paragraph, r"\b[0-9]{11}\b", "the ids of runs belong in the changelog, not in the decision record")
            self.assertNotIn("tracking", paragraph, "nor the ids that Azure gave to the failed requests")
        self.assertNotIn("**What the first runs showed**", self.section)
        self.assertNotIn("and has not run again", self.section)

    def test_it_says_what_the_size_of_a_request_is_how_it_was_measured_and_that_the_first_figure_was_an_assumption(self):
        paragraph = self.section.split("**The size of a request.**")[1].split("\n\n")[0]
        for words in ("takes only a few hundred kilobytes of files, and the tool refuses more than 480,000 bytes of them (`MAX_FILE_BYTES` in [`tools/operator-run.py`](../../tools/operator-run.py), with the evidence next to it)",
                      "That is a measured limit and not a documented one: Learn names none for a secret volume or for the request",
                      "the 3,000,000 bytes that the tool held first were an assumption, which was wrong",
                      "a request with **466,104 bytes** of files was taken (the probe of phase 1: the file of 400,000 bytes, the usage app's lock of 44,967 and the probe's script of 21,137)",
                      "a request with **632,656 bytes** (the cases app's finished package of 614,068 bytes and the container script of 18,588) was refused twice, at 19:25 and at 19:31 UTC, with "
                      "\"(InternalServerError) Encountered an internal server error\" when the group was made",
                      "The limit lies between the two, and where is not known.",
                      "The cap of 480,000 is a round number just above the largest total that is known to work, so that the probe is not refused.",
                      "The cases app's package had been taken for about 2 MB on an estimate, and the first build on the runner said 614,068 bytes: the figure was wrong wherever it was written.",
                      "So neither package rides in the request.", "about 235 KB of files for the cases app (the largest) and about 62 KB for the usage app at the time of writing",
                      "the runner counts them against the cap before it looks for the Operator, with the evidence in its message",
                      "The cases request of the run after the fix was the file of sources (208,046 bytes) and the two scripts, about 235 KB in all, and Azure took it."):
            self.assertIn(words, paragraph, words)

    def test_the_figures_of_the_record_are_the_ones_that_the_tool_holds(self):
        tool = text("tools/operator-run.py")
        held = {name: int(re.search(rf"^{name} = ([0-9_]+)", tool, re.M).group(1).replace("_", "")) for name in ("FILES_TAKEN_BYTES", "FILES_REFUSED_BYTES", "MAX_FILE_BYTES")}
        paragraph = self.section.split("**The size of a request.**")[1].split("\n\n")[0]
        self.assertEqual(held, {"FILES_TAKEN_BYTES": 466104, "FILES_REFUSED_BYTES": 632656, "MAX_FILE_BYTES": 480000})
        for name, figure in held.items():
            self.assertIn(f"{figure:,}", paragraph, f"{name} is written in the record")
        self.assertLess(held["FILES_TAKEN_BYTES"], held["MAX_FILE_BYTES"], "the cap lets the largest request that is known to work through")
        self.assertLess(held["MAX_FILE_BYTES"], held["FILES_REFUSED_BYTES"], "and stops what was refused")
        self.assertEqual(held["FILES_TAKEN_BYTES"], 400_000 + 44_967 + 21_137, "the figure that was taken is the probe of 2026-11-06 as it was sent: the size test, the usage lock and the probe's script")

    def test_it_says_what_is_not_verified_and_what_the_runs_closed(self):
        part = self.section.split("**What is not verified.**")[1].split("**What a person runs, in order.**")[0]
        for words in ("Both publishes have run in Azure (above), and what the runs closed is in [Not checked](#not-checked): the first `cases` publish through the Operator, the cases libraries built alone in the container, "
                      "the post of the built package to the deployment site from the container, how long the cases publish takes, and Flex Consumption's `config-zip` from the image's Azure CLI. What is still open:",
                      "The exact limit of a request, which lies between 466,104 and 632,656 bytes of files.", "a request of the size of the cap has not been made",
                      "The requests of the two apps are far below it (about 62 KB and about 235 KB), and the runs did not narrow the limit.",
                      "That the package that the container builds is the one that the runner would build", "the zips of two builds differ in file times, so the test compares the members and the pip words, not the bytes",
                      "No build made on the runner has been compared with one made in the container.",
                      "The container's log said 7.0 MB for the usage package and 0.5 MB for the cases package (megabytes cut to one decimal, which agrees with the 614,068 bytes that the runner's build of the cases package gave)."):
            self.assertIn(words, part, words)
        self.assertEqual(part.count("\n- "), 2, "two items are open: the exact limit and the equality of the packages")
        for answered in ("Nothing of this phase has run in Azure.", "The size of the request. The cases package of about 2 MB", "and the cases app's has not.", "How long the cases publish takes. The usage app's took 169 seconds in all",
                         "nothing has built it alone there", "and has not run from the container."):
            self.assertNotIn(answered, part, answered)

    def test_it_says_the_order_a_person_runs_for_the_real_estate_and_for_a_new_one_and_the_cost(self):
        order = self.section.split("**What a person runs, in order.**")[1].split("\n\n**Cost.**")[0]
        for words in ("Done on the real estate on 2026-11-06, with no hand step: `recording` and then `cases` (the second after its fix).",
                      "Each run shows the container's lines (both names private, the sign-in, the build with its numbers, the publish), and the `cases` run the health answer and the front-door check; the function app was opened once afterwards.",
                      "Nothing more is needed for phase 2. Run the two actions again whenever the code of an app changes: each publishes from inside the network.",
                      "On a new estate: `recording`, `cases`, `operator`, and then `recording` and `cases` again. Phase 3 for the usage app is done ([below](#publishing-code-to-the-private-apps-phase-3-for-the-usage-app-deployed-and-proven-on-2026-11-06)); "
                      "for the cases app it waits for the owner's decision about the function app."):
            self.assertIn(words, order, words)
        self.assertLess(order.index("Done on the real estate"), order.index("On a new estate"))
        for stale in ("On the real estate, where the Operator exists and the apps are public:", "`cases` is the one that has not published from the Operator yet.", "Phase 3 follows when both have passed."):
            self.assertNotIn(stale, order, stale)
        self.assertIn("**Cost.** One container group per publish, for a few minutes, at the rate of [what it costs](#what-it-costs): at its limit about 3.6 US cents for the usage group and 1.8 for the cases group, "
                      "and a normal run is a tenth of that. Nothing standing is added.", self.section)
        self.assertLess(self.section.index("**What is not verified.**"), self.section.index("**What a person runs, in order.**"))
        self.assertNotRegex(self.section, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", "no id of the tenant, the subscription or an object")
        self.assertNotIn("func-meternaut-", self.section, "no name of a real app")

    def test_the_status_the_table_of_the_phases_the_order_of_the_work_and_the_not_checked_say_the_same(self):
        status = self.page.split("\n")[2]
        self.assertIn("The two actions that deploy the apps, `recording` and `cases`, publish the code from inside the network, in the Operator, as the deploy identity, and both did so on the real estate on 2026-11-06 "
                      "([phase 2](#publishing-code-to-the-private-apps-phase-2): done; the usage app at the first attempt, and the cases app at the first attempt after a fix, because its first two attempts were refused "
                      "for a request that was too big). The usage app has taken no public traffic since the same day: its public access is Disabled (Azure shows it), anonymous requests to its public address are refused "
                      "with HTTP 403, the Operator published into it, and `recording-check` passed with it private "
                      "([phase 3 for the usage app](#publishing-code-to-the-private-apps-phase-3-for-the-usage-app-deployed-and-proven-on-2026-11-06)).", status)
        self.assertNotIn("has not run again", status)
        phase_1 = self.page.split("## Publishing code to the private apps: phase 1")[1].split("\n## ")[0]
        self.assertIn("so that the path through the private endpoint is proved with nothing to lose | done on 2026-11-06 for both apps: the usage app at the first attempt, and the cases app at the first attempt "
                      "after a fix for a request that was too big ([phase 2](#publishing-code-to-the-private-apps-phase-2)) |", phase_1)
        self.assertNotIn("proved with nothing to lose | later |", self.page)
        order = self.page.split("## The order of the work")[1].split("\n## ")[0]
        self.assertIn("the publish steps through the Operator, still with the apps public (done on 2026-11-06 for both apps: [phase 2](#publishing-code-to-the-private-apps-phase-2)); and then `Disabled` for each app", order)
        not_checked = self.page.split("## Not checked")[1].split("\n## ")[0]
        self.assertIn("Phase 2 of publishing code ([above](#publishing-code-to-the-private-apps-phase-2)): both apps were published through the Operator on 2026-11-06, the cases app after a fix for a request that was too big. "
                      "Open: the exact limit of a request (between 466,104 and 632,656 bytes of files; the runs did not narrow it), and whether the container's package equals the runner's", not_checked)
        self.assertNotIn("has not run for the cases app since its fix", self.page)
        self.assertIn("Read again on 2026-11-06 for phase 2 of publishing code:", self.page.split("## Sources")[1])
        self.assertLess(self.page.index(self.HEADING), self.page.index("## Reading telemetry when the component is private"))
        self.assertLess(self.page.index("## Publishing code to the private apps: phase 1"), self.page.index(self.HEADING))
        self.assertLess(self.page.index(self.HEADING), self.page.index("## Publishing code to the private apps: phase 3 for the usage app (deployed and proven on 2026-11-06)"))
        self.assertLess(self.page.index("## Publishing code to the private apps: phase 3 for the usage app (deployed and proven on 2026-11-06)"), self.page.index("## Reading telemetry when the component is private"))

    def test_the_bootstrap_page_says_that_no_hand_step_is_needed_and_the_order_on_a_new_estate(self):
        page = text("environment/BOOTSTRAP.md")
        heading = "## Changed on 2026-11-06: publishing code from inside the network, phase 2"
        self.assertIn(heading, page)
        paragraph = page.split(heading)[1].split("\n## ")[0]
        for words in ("**No hand step is needed.**", "[The decision record](../docs/proposals/07-private-by-default.md#publishing-code-to-the-private-apps-phase-2)",
                      "the actions `recording` and `cases` now publish the code of their function app from inside the network, in a short-lived container group of the Operator, through the app's private endpoint",
                      "The runner publishes nothing any more, and the apps stay public in this phase.", "audience `api://AzureADTokenExchange`", "the workflow's `id-token: write` permission is all it needs",
                      "Nothing is added to the deploy identity or to the Operator's identity, and no credential changes", "the probe of phase 1 showed that the federated credential `github-main`",
                      "a person decides, on the owner's word", "nothing is guessed here", "**The order changes on an estate that has no Operator.**",
                      "the order is `recording`, `cases`, `operator`, and then `recording` and `cases` again: the second round publishes.",
                      "On the estate that has the Operator, run `recording` and then `cases`, read the list of the functions and the health answer in their summaries, and open the function app once.", "**Going back**",
                      "The cases app is. The usage app is not since its phase 3 on 2026-11-06: for it, set `USAGE_APP_PUBLIC_NETWORK_ACCESS` in `tools/environment-params.py` back to `Enabled` and run `recording` first, "
                      "because the runner cannot reach the deployment site of a private app.",
                      "**It ran on the real estate on 2026-11-06, with no hand step.**", "`recording` published the usage app from the Operator at the first attempt.",
                      "`cases` failed twice at the step that makes the container group, because its request carried more bytes of files than a container group takes; the fix builds the cases app in the container from its sources, "
                      "and the run after it published the app at the first attempt",
                      "The usage app has taken no public traffic since the same day", "and nothing is added for a person to do.",
                      "One thing a person sees after `cases`: the redeploy ends a signed-in session of the function app, so the first page afterwards shows Microsoft's account picker once, and a click completes the sign-in."):
            self.assertIn(words, paragraph, words)
        after = page.split("\n## After it")[1].split("\n## ")[0]
        self.assertIn("On the real estate both ran on 2026-11-06 and published, and the usage app took no public traffic from then until the action `retire-old` deleted it. One yes to the whole list", after)
        self.assertIn("Since phase 2, `cases` publishes its code in the Operator, as the deploy identity, so it comes after `operator` on an estate that has none: it deploys and stops at the publish, "
                      "and the order is `base`, `cases`, `operator`, and then `cases` again", after)
        self.assertLess(after.index("Since phase 1 of publishing code"), after.index("Since phase 2, `cases` publishes"))
        self.assertLess(after.index("Since phase 2, `cases` publishes"), after.index("One yes to the whole list"))
        self.assertLess(page.index("## Changed on 2026-11-06: publishing code from inside the network, phase 1"), page.index(heading))
        self.assertLess(page.index(heading), page.index("\n## After it"))
        self.assertNotRegex(paragraph, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", "no id of the tenant, the subscription or an object")

    def test_the_changelog_says_what_the_owner_said_what_changed_what_was_checked_what_was_not_and_what_a_person_runs_in_order(self):
        changelog = text("CHANGELOG.md")
        self.assertIn(self.CHANGELOG_HEADING, changelog)
        entry = changelog.split(self.CHANGELOG_HEADING)[1].split("\n## ")[0]
        for words in ("**What the owner said.**", "no resource of the project has a public endpoint (private endpoints only), and no key exists anywhere", "the apps stay public",
                      "the publish steps of the runner are replaced, so that one path exists and it is the one that is proven",
                      "**What changed.**", "[`operator/publish.sh`](operator/publish.sh), new", "It signs in first, as the deploy identity, with the run's token (the first `az` call, three tries).",
                      "For the usage app it then fetches a token for the App Service resource at once, while the sign-in's assertion, which lives five minutes, is fresh",
                      "It then requires both names of the app to resolve to private addresses", "makes pip with `ensurepip` in a work folder (the image has none)",
                      "`az functionapp deployment source config-zip --build-remote false`, three attempts a minute apart", "five attempts, 200 or 202 accepted",
                      "One build script, three modes", "`FUNCTION_APP_SOURCES_ONLY=1` zips the app's files without libraries", "`FUNCTION_APP_BUILD_IN_OPERATOR=1`, set only by the container script",
                      "\"Pack the usage app's sources for the Operator\" replaces the build", "\"Publish the usage functions to the function app from inside the network, in the Operator\" replaces the publish",
                      "the build step now also checks that the package and the container script are within the 3,000,000 bytes that the tool takes",
                      "masked at once, kept in a shell variable, given to the tool only as `--secure-env AZURE_FEDERATED_TOKEN`, never in `--env`, a file or the summary; without a token the step fails with the reason and publishes nothing",
                      "The usage group is given 2,400 seconds (step limit 45 minutes) and the cases group 1,200 (25)", "A step after each deletes any `op-publish-` group that is left, and always runs.",
                      "`recording` signs in once more before the list of its functions", "The order is `recording`, `cases`, `operator`, and then `recording` and `cases` again; the second round publishes.",
                      "**What was checked.**", "No resource of a template changed; the Bicep build and lint of the two templates, whose comments and one description were brought up to date, are clean", "14 files, about 35 KB",
                      "**Not checked, and why it matters.**", "Nothing ran in Azure, so the first run decides.", "whether Flex Consumption's `config-zip` behaves from the image's Azure CLI (2.92.0 as the session that ran the Hub reported it) as it does from the runner's",
                      "about 2.7 MB after base64", "the largest one that is known to work is the probe's 400,000 bytes and Learn names no limit", "build the cases app in the container from its sources, as the usage app is, which is one switch",
                      "The script was run with Git's bash 5, not the image's", "**What a person has to do, in order.**", "No hand step."):
            self.assertIn(words, entry, words)
        self.assertNotIn("@@", entry, "no placeholder is left")
        self.assertNotRegex(entry, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", "no id of the tenant, the subscription or an object")
        order = entry.split("**What a person has to do, in order.**")[1]
        self.assertLess(order.index("**`recording`**"), order.index("**`cases`**"))
        self.assertIn("open the console once", order)
        self.assertIn("on a new estate the order is `recording`, `cases`, `operator`, and then `recording` and `cases` again", order)
        self.assertIn("Phase 3, which makes the apps private and moves the health check and the list of the functions inside, follows when both have passed.", order)
        self.assertLess(entry.index("**What changed.**"), entry.index("**What was checked.**"))
        self.assertLess(entry.index("**What was checked.**"), entry.index("**Not checked, and why it matters.**"))
        self.assertLess(entry.index("**Not checked, and why it matters.**"), entry.index("**What a person has to do, in order.**"))


class TheCasesAppIsBuiltInTheContainerRecord(unittest.TestCase):
    """CHANGELOG.md: the entry about the two failed `cases` runs says what failed, why, the measured limit, what changed, what was checked, what was not, and what a person runs; the older entries stay below it."""

    HEADING = "## The cases app is built in the container, and a request takes at most 480,000 bytes of files (built, not yet run) — 2026-11-06"

    def setUp(self):
        self.changelog = text("CHANGELOG.md")
        self.assertIn(self.HEADING, self.changelog)
        self.entry = self.changelog.split(self.HEADING)[1].split("\n## ")[0]

    def test_it_says_what_failed_with_the_runs_the_error_and_the_sizes_and_what_ran_well(self):
        part = self.entry.split("**What failed.**")[1].split("**Why.**")[0]
        for words in ("The Hub action `recording` published the usage app from the Operator at the first attempt (run 42277631207, 19:12 to 19:23 UTC", "in 169 seconds",
                      "the sign-in as the deploy identity worked, the token for the App Service resource was fetched, both names of the app were private", "the image's Azure CLI was 2.92.0, `ensurepip` made pip 25.0.1",
                      "the 15 files of sources became 914 files and 7.0 MB zipped in 8 seconds", "`config-zip` published the package, and the group was deleted",
                      "The Hub action `cases` failed twice (run 42279231858 at 19:25 and run 42279986261 at 19:31), at the step that makes the container group",
                      "`error: the container group could not be made: ERROR: (InternalServerError) Encountered an internal server error`",
                      "632,656 bytes of files: the finished package of 614,068 bytes and the container script of 18,588", "No container ran and nothing was published."):
            self.assertIn(words, part, words)

    def test_it_says_why_the_old_figure_was_wrong_and_what_range_was_measured(self):
        part = self.entry.split("**Why.**")[1].split("**What changed.**")[0]
        for words in ("The tool refused more than 3,000,000 bytes of files, and that figure was an assumption of the phase-2 build: Learn names no limit for a secret volume or for the request (read on 2026-11-06). It was wrong.",
                      "**466,104 bytes** of files (the probe of phase 1 at 16:37: the file of 400,000 bytes, the usage app's lock of 44,967 and the probe's script of 21,137",
                      "the \"about 475 KB\" that the session that coordinates the work gave is this total, added up exactly", "the **632,656 bytes** that were refused twice",
                      "Where it lies between the two is not known.", "The cases app's package had also been taken for about 2 MB, on an estimate",
                      "the first build on the runner said 614,068 bytes, so the figure was wrong wherever it was written",
                      "its request carries sources and scripts only (about 62 KB), and its package of 7.0 MB zipped could not ride in a request in any case"):
            self.assertIn(words, part, words)

    def test_the_figures_of_the_entry_are_the_ones_that_the_tool_holds(self):
        tool = text("tools/operator-run.py")
        for name in ("FILES_TAKEN_BYTES", "FILES_REFUSED_BYTES", "MAX_FILE_BYTES"):
            figure = int(re.search(rf"^{name} = ([0-9_]+)", tool, re.M).group(1).replace("_", ""))
            self.assertIn(f"{figure:,}", self.entry, f"{name} is written in the entry")
        self.assertIn("(13,896 bytes above it)", self.entry)
        self.assertEqual(480_000 - 466_104, 13_896)

    def test_it_says_what_changed_in_the_tool_the_container_script_the_hub_and_the_tests(self):
        part = self.entry.split("**What changed.**")[1].split("**What was checked.**")[0]
        for words in ("**The tool** ([`tools/operator-run.py`](tools/operator-run.py)).", "The cap on the total bytes of the secret files is 480,000, a named constant (`MAX_FILE_BYTES`) with the two measured figures "
                      "(`FILES_TAKEN_BYTES` and `FILES_REFUSED_BYTES`) and the date next to it", "the error message says what was seen", "so that what is bigger has to be built in the container from sources",
                      "**The cases app is built in the container, as the usage app is.**", "`FUNCTION_APP_SOURCES_ONLY=1` mode (52 files, 206,467 bytes zipped)", "about 234 KB of files",
                      "asks for the Azure Resource Manager token as the deploy identity right after the sign-in (the sign-in's assertion lives five minutes; a failure stops the run before the names and the build)",
                      "`FUNCTION_APP_BUILD_IN_OPERATOR=1`, the hash lock `src/case-functions/requirements.txt`, the same flags, no `--ignore-requires-python`",
                      "posts the built package from the work folder to the deployment site's `api/zipdeploy` with `curl`, as before", "The built file never rides in a request, so no request limit applies to it.",
                      "one pip command and one path exist; the parity tests cover both apps now",
                      "\"Build the cases app's package\" is now \"Pack the cases app's sources for the Operator\"",
                      "Both pack steps, the cases one and the usage one, add up the sources, the build script and the container script and stop when the total is above 480,000 bytes, before the Operator is looked for, "
                      "with a message that names the cap and the evidence", "The names of the other steps, their order, the limits of time, the first-run behaviour and the messages are unchanged.",
                      "a request of exactly 480,000 bytes is taken, one byte more is refused", "one pins that the lock of the cases app is a part of the usage lock",
                      "The phase-2 entry below keeps what it said when it was written, with two notes where a sentence of it is no longer true."):
            self.assertIn(words, part, words)

    def test_it_says_what_was_checked_and_which_flag_the_cases_lock_needs(self):
        part = self.entry.split("**What was checked.**")[1].split("**Not checked, and why it matters.**")[0]
        for words in ("The whole suite of the tools passes", "against 1,151 before this change", "the documents check (strict) and the workflow lint (0 findings)",
                      "Git's bash against stand-ins for `az`, `python3`, `pip`, `curl`, `getent`, `timeout` and `sleep`",
                      "the Azure Resource Manager token of `cases` is fetched right after the sign-in and a failure of it stops the run before the names",
                      "the built zip (and not the sources) is what `curl` and `config-zip` take",
                      "a total of exactly 480,000 bytes passes, one more stops with the message, and the figures of the incident (614,068 and 18,588) stop",
                      "its three libraries (`azure-functions` 2.3.0, `markupsafe` 3.0.4 and `werkzeug` 3.1.9) are in the usage lock at the same version and with the same hashes, and neither lock has an environment marker",
                      "with `--python-version 3.13` and without `--ignore-requires-python` (900 files in the probe, 914 in the publish), and no other flag is needed",
                      "No template changed, so no Bicep build was run."):
            self.assertIn(words, part, words)

    def test_it_says_what_is_not_checked_and_the_order_a_person_runs(self):
        part = self.entry.split("**Not checked, and why it matters.**")[1].split("**What a person has to do, in order.**")[0]
        for words in ("The first `cases` publish through the Operator is the open one.", "Nothing has built the cases libraries alone in the container",
                      "the same `curl` command got HTTP 200 from the runner at 15:13 on 2026-11-06, and from the container the deployment site answered 401 to a `GET` without a sign-in",
                      "The exact limit of a request, between 466,104 and 632,656 bytes of files, is not known", "no request of the size of the cap has been made",
                      "How long the cases publish takes is not known (the usage app's took 169 seconds).", "not on the Linux runner that runs the suite as the Hub's first step", "Info-ZIP, which stores directory entries"):
            self.assertIn(words, part, words)
        order = self.entry.split("**What a person has to do, in order.**")[1]
        for words in ("No hand step.", "(1) After this change is merged, run **`recording`** and then **`cases`**.", "`cases` is the one that has not published from the Operator yet; `recording` is run again because the container script is shared and changed for both kinds.",
                      "(2) Read the list of the functions in each summary (six and four) and the health answer of the cases app, both still made from the runner, and open the console once.",
                      "the order on a new estate is `recording`, `cases`, `operator`, and then `recording` and `cases` again", "Phase 3, which makes the apps private and moves the health check and the list of the functions inside, follows when both have passed."):
            self.assertIn(words, order, words)
        self.assertLess(order.index("**`recording`**"), order.index("**`cases`**"))
        for first, second in (("**What failed.**", "**Why.**"), ("**Why.**", "**What changed.**"), ("**What changed.**", "**What was checked.**"), ("**What was checked.**", "**Not checked, and why it matters.**"),
                              ("**Not checked, and why it matters.**", "**What a person has to do, in order.**")):
            self.assertLess(self.entry.index(first), self.entry.index(second))

    def test_it_holds_no_placeholder_and_no_id_and_sits_above_the_entries_that_it_corrects(self):
        self.assertNotIn("@@", self.entry, "no placeholder is left")
        self.assertNotRegex(self.entry, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", "no id of the tenant, the subscription or an object, and none of the tracking ids that Azure gave")
        self.assertNotIn("func-meternaut-", self.entry, "no name of a real app")
        below = ("## The code of both function apps is published from inside the network, in the Operator (built, not yet run) — 2026-11-06",
                 "## The private endpoints of the two function apps are waited for before their code is published (built, not yet run) — 2026-11-06",
                 "## The Event Hubs namespace is private-only on the real estate (deployed and proven)", "## Publishing code to the private apps, phase 1")
        positions = [self.changelog.index(title) for title in below]
        self.assertEqual(positions, sorted(positions), "the older entries keep their order")
        self.assertLess(self.changelog.index(self.HEADING), positions[0])

    def test_the_two_sentences_of_the_phase_2_entry_that_are_no_longer_true_say_so(self):
        older = self.changelog.split("## The code of both function apps is published from inside the network, in the Operator (built, not yet run) — 2026-11-06")[1].split("\n## ")[0]
        for words in ("within the 3,000,000 bytes that the tool takes (that figure was an assumption and it was wrong, and the step was replaced: see the entry above)",
                      "which is one switch) (answered by the first runs: Azure did not take it, the package was 614,068 bytes and not about 2 MB, and that way out was taken: see the entry above);"):
            self.assertIn(words, older, words)


class BothAppsArePublishedAndTheUsageAppIsPrivateRecord(unittest.TestCase):
    """The decision record, the bootstrap page, the README and the changelog on the runs of 2026-11-06 that proved phase 2 for both apps and phase 3 for the usage app."""

    HEADING = "## Publishing code to the private apps: phase 3 for the usage app (deployed and proven on 2026-11-06)"
    CHANGELOG_HEADING = "## Both apps are published from inside the network, and the usage app takes no public traffic: deployed and proven — 2026-11-06"

    def setUp(self):
        self.page = text("docs/proposals/07-private-by-default.md")
        self.assertIn(self.HEADING, self.page)
        self.section = self.page.split(self.HEADING)[1].split("\n## ")[0]
        self.changelog = text("CHANGELOG.md")
        self.assertIn(self.CHANGELOG_HEADING, self.changelog)
        self.entry = self.changelog.split(self.CHANGELOG_HEADING)[1].split("\n## ")[0]

    def test_the_state_table_says_that_the_usage_app_is_disabled_with_the_evidence_and_that_the_cases_app_waits_for_a_decision(self):
        state = self.page.split("## The rule and the state")[1].split("\n## ")[0]
        usage = [line for line in state.split("\n") if line.startswith("| Usage function app (Flex Consumption) |")][0]
        for words in ("**Disabled** on the real estate since 2026-11-06 ([deployed and proven](#publishing-code-to-the-private-apps-phase-3-for-the-usage-app-deployed-and-proven-on-2026-11-06))",
                      "Azure shows Disabled and the state Running", "anonymous requests to its public address got HTTP 403, for `/`, for `/admin/host/status` and for the deployment site's `/`"):
            self.assertIn(words, usage, words)
        self.assertNotIn("built, not yet deployed", usage)
        cases = [line for line in state.split("\n") if line.startswith("| Cases function app (")][0]
        self.assertIn("**Enabled**, until phase 3 for this app. The owner decided on 2026-11-06 that the app is closed and that the people who approve reach the function app through the platform's Application Gateway: "
                      "the code for that is built and not deployed, and the value flips in a later change, after the gateway objects exist and the owner has said yes ([phase 3 for the cases app](#publishing-code-to-the-private-apps-phase-3-for-the-cases-app-the-console-behind-the-platforms-application-gateway-built-not-deployed))", cases)
        self.assertNotIn("**Disabled**", cases)

    def test_the_section_says_what_changed_what_the_runs_showed_what_they_show_and_do_not_and_what_is_open(self):
        paragraphs = self.section.split("\n\n")
        changed, runs, shows, still_open = [next(p for p in paragraphs if p.startswith(lead)) for lead in ("**What changed.**", "**What the runs showed**", "**What this shows, and what it does not.**", "**What is still open.**")]
        for words in ("The constant `USAGE_APP_PUBLIC_NETWORK_ACCESS` in [`tools/environment-params.py`](../../tools/environment-params.py) is `Disabled`, so the template writes `publicNetworkAccess: Disabled` to the usage app, "
                      "and the cases app keeps `Enabled`.", "because it has no page for people, its timers and Event Hubs triggers run inside the network, and its code is published from inside the network",
                      "which had passed for it with the app still public. The change was run through the Hub on the real estate on 2026-11-06."):
            self.assertIn(words, changed, words)
        for words in ("(2026-11-06, UTC, as the session that ran the Hub reported them)",
                      "- `recording` (19:56 to 20:05) deployed the template. Azure shows the app's public network access as Disabled and its state as Running.",
                      "- Anonymous requests to the app's public address, resolved through a public resolver with the host name as SNI, were refused with HTTP 403: for `/`, for `/admin/host/status` and for the deployment site's `/`.",
                      "- The wait before the publish covered the app's own endpoint: the step said that the landing zone's policy had registered every private endpoint of the usage recording, the function app's own included.",
                      "- The Operator published into the app that was already private, at the first attempt, in 166 seconds.",
                      "- The runner's check of the functions, made from outside the network, listed 6 functions. So Azure Resource Manager's list of functions answers for an app whose public access is Disabled: "
                      "that had been read only on other apps of the landing zone, and it is now seen on this app.",
                      "- `recording-check` (20:06 to 20:12) passed with the app private: the control event woke the Flex Consumption app from zero, the three copy jobs ran, and 18 documents were in the container."):
            self.assertIn(words, runs, words)
        for words in ("The public address of the usage app is shut: nothing outside the network reaches the app or its deployment site, and what was tried from the workflow still works "
                      "(the publish from the Operator, the list of the functions from the runner, and the control event with its three copy jobs).",
                      "The requests were anonymous and came from a public resolver, so they show that the public address refuses, and nothing about what a machine with a route into the network sees."):
            self.assertIn(words, shows, words)
        for words in ("The cases app keeps `Enabled` until the people who approve have a network path to the function app, which is the owner's decision ([the function app for people](#decisions-for-the-owner));",
                      "the check of the function app's front door and the health check of the cases app still run from the runner, and they move inside only when that app is closed.",
                      "Application Insights and the workspace are still public: they need the owner's decision about the shared Azure Monitor private link scope ([the order of the work](#the-order-of-the-work), item 6).",
                      "**The way back** for the usage app is one value: set the constant to `Enabled` and run `recording`."):
            self.assertIn(words, still_open, words)
        self.assertNotRegex(self.section, r"\b[0-9]{11}\b", "the ids of runs belong in the changelog, not in the decision record")
        self.assertNotRegex(self.section, r"\b[Rr]un [0-9]{3}\b", "the run numbers are in the changelog only")

    def test_the_rows_and_sentences_that_described_the_publish_and_the_list_of_the_functions_say_the_state_of_2026_11_06(self):
        breaks = self.page.split("## What private access breaks")[1].split("\n## ")[0]
        row = [line for line in breaks.split("\n") if line.startswith("| Publishing code |")][0]
        self.assertIn("The Operator publishes from inside the network since phase 2, and it did so for both apps on 2026-11-06, the usage app also into the app that was already private "
                      "([phase 2](#publishing-code-to-the-private-apps-phase-2))", row)
        operator = self.page.split("## The Operator")[1].split("\n## ")[0]
        self.assertIn("`recording-check` and `cases-run` run their check tools in it, and `recording` and `cases` publish the code of their app in it ([phase 2](#publishing-code-to-the-private-apps-phase-2)).", operator)
        self.assertIn("| `recording`, `cases` | Publish the code from inside the network, as the deploy identity with the run's token and not with the Operator's own token: the runner sends each app's sources, "
                      "and the container builds the package and publishes it ([phase 2](#publishing-code-to-the-private-apps-phase-2); done for both apps on 2026-11-06) |", operator)
        self.assertNotIn("Gets the package (the routes below), posts it to the private deployment site with its identity's token", operator)
        checks = self.page.split("## The checks of the usage recording and the first cases run in the Operator")[1].split("\n## ")[0]
        self.assertIn("It answered for the usage app with its public access Disabled, from outside the network (six functions, on 2026-11-06); for the cases app, which is public, it has not been tried with the app private.", checks)
        self.assertNotIn("whether it still answers when the apps are private is not known", checks)
        probe = self.page.split("## What the probe proved on 2026-11-06")[1].split("\n## ")[0]
        self.assertIn("Publishing code to the private deployment sites is done for both apps: the Operator did it on 2026-11-06", probe)
        self.assertNotIn("phase 2 of it is built, ran for the usage app and has not run for the cases app since its fix", probe)

    def test_the_not_checked_section_closes_what_the_runs_closed_and_keeps_what_is_open(self):
        not_checked = self.page.split("## Not checked")[1].split("\n## ")[0]
        open_part, closed_part = not_checked.split("**Closed by the runs of 2026-11-06**")
        for words in ("Phase 3 of publishing code for the cases app ([the usage app is done](#publishing-code-to-the-private-apps-phase-3-for-the-usage-app-deployed-and-proven-on-2026-11-06)): "
                      "the owner decided that the people who approve reach the function app through the platform's Application Gateway, and the code for that is built and not deployed "
                      "([the section](#publishing-code-to-the-private-apps-phase-3-for-the-cases-app-the-console-behind-the-platforms-application-gateway-built-not-deployed)).",
                      "The health check of the cases app is built to run in the Operator, and the check of the function app's front door to knock at the gateway's host name.",
                      "Application Insights and the workspace are still public. They need the owner's decision about the shared Azure Monitor private link scope",
                      "the exact limit of a request (between 466,104 and 632,656 bytes of files; the runs did not narrow it)", "the machines of the other people who approve were not tested",
                      "The two waits and what a deployment site accepts from inside the network are in the closed list below."):
            self.assertIn(words, open_part, words)
        for words in ("Whether the zone group that the waits for the two apps' endpoints ask for is what the policy makes. It is:",
                      "Whether a deployment site takes a package from inside the network, through the private endpoint, from a container that signed in as the deploy identity with the run's token. It does, for both kinds:",
                      "(the container ran 169 seconds, and 166 into the app that was already private)", "(92 seconds, HTTP 200 at the first attempt)", "with Azure CLI 2.92.0 in the image",
                      "Whether the cases app's libraries build alone in the container from their lock (three libraries, the same flags, no `--ignore-requires-python`). They do: 208 files, 3 seconds, the hashes checked.",
                      "Whether Azure Resource Manager's list of functions answers for an app whose public access is Disabled. It does for the usage app: six functions, from outside the network",
                      "Whether the usage app still publishes, wakes from zero and runs its copy jobs when its public access is Disabled. It does: the Operator published into it, and `recording-check` passed."):
            self.assertIn(words, closed_part, words)
        for stale in ("they have not run since they were added", "Open: the first `cases` publish through the Operator", "how long the cases publish takes, and whether", "and it has not run", "not tried", "nobody has seen"):
            self.assertNotIn(stale, not_checked, stale)

    def test_the_order_of_the_work_the_readme_and_the_bootstrap_page_say_the_same(self):
        order = self.page.split("## The order of the work")[1].split("\n## ")[0]
        self.assertIn("The owner has to decide about the shared Azure Monitor private link scope too (as the session that coordinates the work reported on 2026-11-06): "
                      "Application Insights and the workspace are still public until then.", order)
        readme = text("README.md")
        self.assertIn("Still open: the cases app's phase 3 (it serves the pages; the owner decided on 2026-11-06 that the people who approve reach it through the platform's Application Gateway, and on 2026-11-07 that "
                      "there is no gateway for it and that he reaches the private network instead: the code, the tests and the documents for both are built and nothing is deployed, "
                      "[the gateway route](docs/proposals/07-private-by-default.md#publishing-code-to-the-private-apps-phase-3-for-the-cases-app-the-console-behind-the-platforms-application-gateway-built-not-deployed) "
                      "and [the web page on the private network](docs/proposals/07-private-by-default.md#the-web-page-on-the-private-network-built-not-deployed)), "
                      "the telemetry read once Application Insights is private, "
                      "and the function app check; two decisions are the owner's (a public repository, and the traces of Foundry's agents).", readme)
        self.assertIn("The code of both apps is published from the Operator, as the deploy identity, since 2026-11-06 ([phase 2](docs/proposals/07-private-by-default.md#publishing-code-to-the-private-apps-phase-2)), "
                      "and the usage app was closed after that: anonymous requests to its public address get HTTP 403 "
                      "([phase 3 for the usage app](docs/proposals/07-private-by-default.md#publishing-code-to-the-private-apps-phase-3-for-the-usage-app-deployed-and-proven-on-2026-11-06)).", readme)
        self.assertNotIn("the publish through the Operator is built and has not run", readme)
        self.assertNotIn("Both function apps, Application Insights and the workspace still have public network access", readme)
        bootstrap = text("environment/BOOTSTRAP.md")
        self.assertNotIn("not run yet", bootstrap.split("## Changed on 2026-11-06: publishing code from inside the network, phase 2")[1].split("\n## ")[0])

    def test_the_figures_of_the_runs_are_the_same_in_the_record_and_the_changelog_and_only_the_changelog_has_the_run_numbers(self):
        for figure in ("169 seconds", "166 seconds", "92 seconds", "914 files", "208,046 bytes", "54 files", "208 files", "6 functions", "18 documents", "HTTP 403", "2.92.0", "25.0.1", "19:12 to 19:23", "19:56 to 20:05",
                       "20:06 to 20:12", "20:33 to 20:39"):
            self.assertIn(figure, self.entry, f"the changelog has {figure}")
            self.assertIn(figure, self.page, f"the record has {figure}")
        for run in ("42277631207", "42279231858", "42279986261", "42283960999", "42285487050", "42289309252"):
            self.assertIn(run, self.entry, run)
            self.assertNotIn(run, self.page, "the run numbers are in the changelog only")
        self.assertNotRegex(self.page, r"\b[0-9]{11}\b", "no run number in the decision record")

    def test_the_changelog_entry_says_what_happened_what_the_runs_showed_what_it_closes_what_is_open_and_that_a_person_has_nothing_to_do(self):
        entry = self.entry
        for words in ("**What happened.**", "the publish of both function apps from the Operator (phase 2, PR #69), the fix for the cases request that was too big (PR #71), "
                      "and the closing of the usage app's public access (PR #70, whose entry below says \"built, not yet deployed\")",
                      "Every run passed except the two `cases` runs that found the defect, and no hand step was needed.", "This entry changes documents and tests only",
                      "The results and the run numbers were passed on by the session that coordinates the work, who ran the Hub; nothing was read from GitHub or Azure here.",
                      "**What the runs showed.**", "`recording` (run 42277631207, 19:12 to 19:23) published the usage app from the Operator at the first attempt: the container ran 169 seconds",
                      "the sources were 15 files; the build gave 914 files and 7.0 MB zipped in 8 seconds with the hashes checked; and `config-zip` took the package through the private endpoint",
                      "`cases` (run 42279231858 at 19:25 and run 42279986261 at 19:31) failed twice at the step that makes the container group, with an Azure Resource Manager InternalServerError, and no container ran. "
                      "The request held 632,656 bytes of files.", "has the cause and the fix",
                      "`recording` (run 42283960999, 19:56 to 20:05): the template wrote public access Disabled, and Azure shows Disabled and the state Running.",
                      "Anonymous requests to the app's public address (resolved through a public resolver, with the host name as SNI) got HTTP 403, for `/`, for `/admin/host/status` and for the deployment site's `/`.",
                      "The wait step covered the app's own endpoint", "The Operator published into the app that was already private, at the first attempt, in 166 seconds.",
                      "listed 6 functions, so Azure Resource Manager's list answers for an app whose public access is Disabled: that had been read only on other apps of the landing zone, and is now seen on this one.",
                      "**`recording-check`** (run 42285487050, 20:06 to 20:12) passed with the app private: the control event woke the Flex Consumption app from zero, the three copy jobs ran, and 18 documents were in the container.",
                      "`cases` (run 42289309252, 20:33 to 20:39) published the app from the Operator at the first attempt: the container ran 92 seconds; the file of sources, `cases-source.zip`, was 208,046 bytes; "
                      "the sources were 54 files; the build gave 208 files and 0.5 MB zipped in 3 seconds with the hashes checked; the deployment site took the package (HTTP 200, attempt 1 of 5); `/healthz` answered 200; "
                      "the check of the console's front door passed all its lines; and the console loaded in a browser afterwards.",
                      "The redeploy had ended the earlier session, so Microsoft's account picker came up once and the sign-in completed with a click; the pages then showed.",
                      "**What this closes.**", "So phase 2 is done for both apps, and phase 3 is done for the usage app.",
                      "**Seen, and not a failure.**", "the entry about the fix said 52 files and 206,467 bytes: those were measured on Windows, which has no `zip`",
                      "the log cuts megabytes (of 1,048,576 bytes) to one decimal, so that agrees with the 614,068 bytes",
                      "**Still open, and unchanged.**", "The cases app keeps public access `Enabled` until the people who approve have a network path to the console, which is the owner's decision;",
                      "Application Insights and the workspace are still public: they need the owner's decision about the shared Azure Monitor private link scope.",
                      "The exact request limit of a container group lies between 466,104 and 632,656 bytes of files, and the runs did not narrow it.",
                      "and the console was opened from one machine only.",
                      "**What changed in the documents and the tests.**", "No older entry was changed.", "**What was checked.**", "No call was made to Azure or GitHub, and no code changed.",
                      "**Not checked, and why it matters.**", "The HTTP 403 comes from anonymous requests through a public resolver", "**What a person has to do.** Nothing for this change."):
            self.assertIn(words, entry, words)
        positions = [entry.index(lead) for lead in ("**What happened.**", "**What the runs showed.**", "**What this closes.**", "**Seen, and not a failure.**", "**Still open, and unchanged.**",
                                                    "**What changed in the documents and the tests.**", "**What was checked.**", "**Not checked, and why it matters.**", "**What a person has to do.**")]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("@@", entry, "no placeholder is left")
        self.assertNotRegex(entry, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", "no id of the tenant, the subscription or an object, and none of the tracking ids that Azure gave")
        self.assertNotIn("func-meternaut-", entry, "no name of a real app")

    def test_no_page_still_says_that_the_publish_or_the_closing_of_the_usage_app_has_not_run(self):
        for name in ("README.md", "docs/proposals/07-private-by-default.md", "environment/BOOTSTRAP.md"):
            page = text(name)
            for stale in ("(built, not yet deployed): the parameter `usageAppPublicNetworkAccess`", "built on 2026-11-06, not run yet", "has not run again", "has not run since its fix", "has not run for the cases app since its fix",
                          "the publish through the Operator is built and has not run", "phase 2 of it is built", "The first runs on the real estate are below: the usage app was published this way at the first attempt, and the cases app was not",
                          "The waits for the apps' endpoints were added after the runs above and have not run.", "Step 3 is the next change."):
                self.assertNotIn(stale, page, f"{name}: {stale}")

    def test_the_entry_is_above_the_entries_that_it_closes_and_the_older_entries_keep_their_order(self):
        below = ("## The cases app is built in the container, and a request takes at most 480,000 bytes of files (built, not yet run) — 2026-11-06",
                 "## The usage app takes no public traffic: its public access is switched off in the template (built, not yet deployed) — 2026-11-06",
                 "## The code of both function apps is published from inside the network, in the Operator (built, not yet run) — 2026-11-06",
                 "## The private endpoints of the two function apps are waited for before their code is published (built, not yet run) — 2026-11-06",
                 "## The Event Hubs namespace is private-only on the real estate (deployed and proven)", "## Publishing code to the private apps, phase 1")
        positions = [self.changelog.index(title) for title in below]
        self.assertEqual(positions, sorted(positions), "the older entries keep their order")
        self.assertLess(self.changelog.index(self.CHANGELOG_HEADING), positions[0], "the entry that records the runs is above the ones that record the builds")


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
        self.assertIn("The order of those three is `base`, `cases`, `operator`, and then, about ten minutes after `operator`", after)
        self.assertIn("The usage recording had two actions of its own, `recording` and `recording-check`: both are gone, and the action `retire-old` deletes what they made", after)
        self.assertIn("both by the Operator, so it comes after `operator` too", after)

    def test_it_says_what_a_check_costs_and_that_the_probe_passed_without_a_fallback(self):
        for words in ("at most 25 minutes for `recording-check` (about 2.3 US cents) and 40 for `cases-run` (about 3.6)", "20 seconds at the end", "it did not", "No new right is given to the deploy identity.",
                      "it passed on 2026-11-06, twice"):
            self.assertIn(words, self.section, words)


if __name__ == "__main__":
    unittest.main()
