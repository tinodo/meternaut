"""The console behind the platform's Application Gateway (docs/proposals/07-private-by-default.md, phase 3 for the cases app): what the parameter builder, the cases template and the steps of the
deploy workflow do with the console's host name, and what the documents say about it. Self-contained, as the other test files are: it loads what it tests and has its own helpers."""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ep = load("environment_params_of_the_console_gateway_tests", "tools/environment-params.py")
cc = load("console_check_of_the_console_gateway_tests", "tools/console-check.py")
operator_tool = load("operator_run_of_the_console_gateway_tests", "tools/operator-run.py")


def text(relative):
    return (ROOT / relative).read_text(encoding="utf-8").replace("\r\n", "\n")


def code_of(source):
    """A Bicep or shell source without its comment lines."""
    return "\n".join(line for line in source.splitlines() if not line.strip().startswith(("//", "#")))


WORKFLOW = text(".github/workflows/deploy-hub.yml")
MODELS = ROOT / "environment" / "models.json"
SETTINGS = {
    "ENV_SUBSCRIPTION_ID": "11111111-2222-3333-4444-555555555555",
    "ENV_RESOURCE_GROUP": "rg-example",
    "ENV_LOCATION": "swedencentral",
    "ENV_VNET_PREFIX": "10.53.0.0/24",
    "ENV_PE_SUBNET_PREFIX": "10.53.0.0/27",
    "ENV_DNS_SERVERS": "10.20.0.4",
    "ENV_OWNER": "owner@example.com",
    "ENV_BUDGET_AMOUNT": "25",
    "ENV_ALERT_EMAILS": "owner@example.com",
    "ENV_BUDGET_START": "2026-11-01",
    "GATEWAY_APPINSIGHTS_ID": "/subscriptions/66666666-7777-8888-9999-000000000000/resourceGroups/rg-gateway/providers/microsoft.insights/components/example-insights",
}


def build(**changes):
    """The parameter builder with the settings of an estate that has the cases: its exit code, what it printed, what it said on standard error and the parameter files that it wrote."""
    with tempfile.TemporaryDirectory() as tmp:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ep.main(["build", "--models", str(MODELS), "--out-dir", tmp], environ={**SETTINGS, **changes})
        files = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in Path(tmp).glob("*.json")}
    return code, out.getvalue(), err.getvalue(), files


def values(document):
    return {k: v["value"] for k, v in document["parameters"].items()}


def outputs(out):
    return dict(line.split("=", 1) for line in out.splitlines())


class TheConsoleHostNameInTheParameterBuilder(unittest.TestCase):
    """The optional variable CONSOLE_HOST_NAME: empty, everything is as it was; with a name it is the console's address."""

    def test_without_a_name_the_console_is_opened_on_the_apps_own_name_and_the_app_stays_open_as_it_was(self):
        code, out, err, files = build()
        self.assertEqual((code, err), (0, ""))
        cases = values(files["cases.parameters.json"])
        self.assertEqual(cases["consoleHostName"], "", "the parameter is always written, and empty")
        lines = outputs(out)
        self.assertEqual(lines["console_host"], f"{cases['functionAppName']}.azurewebsites.net", "what the check of the front door knocks at: the app's own name")
        self.assertEqual((lines["console_host_set"], lines["cases_public_network_access"]), ("false", "Enabled"))

    def test_a_blank_variable_is_no_name_because_a_variable_that_is_not_set_reaches_the_job_as_an_empty_string(self):
        for given in ("", " ", "\t"):
            code, out, err, files = build(CONSOLE_HOST_NAME=given)
            self.assertEqual((code, err), (0, ""), repr(given))
            self.assertEqual(values(files["cases.parameters.json"])["consoleHostName"], "", repr(given))
            self.assertEqual(outputs(out)["console_host_set"], "false", repr(given))

    def test_a_name_is_the_console_s_address_in_lower_case_and_what_the_check_of_the_front_door_knocks_at(self):
        for given in ("console.example.com", "Console.Example.COM", "  console.example.com  ", "console.eu-west.example.co.uk", "c1.a-b.example.org"):
            code, out, err, files = build(CONSOLE_HOST_NAME=given)
            self.assertEqual((code, err), (0, ""), given)
            self.assertEqual(values(files["cases.parameters.json"])["consoleHostName"], given.strip().lower(), given)
            lines = outputs(out)
            self.assertEqual((lines["console_host"], lines["console_host_set"]), (given.strip().lower(), "true"), given)

    def test_the_name_reaches_the_file_of_the_cases_and_no_other_file_and_the_values_of_the_other_settings_are_unchanged(self):
        _, _, _, plain = build()
        _, _, _, named = build(CONSOLE_HOST_NAME="console.example.com")
        for name, document in named.items():
            if name == "cases.parameters.json":
                continue
            self.assertNotIn("consoleHostName", document["parameters"], name)
            self.assertEqual(document, plain[name], f"{name}: the name changes nothing outside the cases file")
        changed = {key for key in values(named["cases.parameters.json"]) if values(named["cases.parameters.json"])[key] != values(plain["cases.parameters.json"]).get(key)}
        self.assertEqual(changed, {"consoleHostName"})

    def test_a_name_that_is_not_a_host_name_is_refused_by_name_and_nothing_is_written(self):
        bad = ("https://console.example.com", "console.example.com/", "console.example.com/path", "console.example.com:443", "console", "-a.example.com", "a-.example.com", "a..example.com",
               "192.168.1.10", "10.53.0.4", "console_x.example.com", "a b.example.com", "x.example.com.", ".example.com", "*.example.com", "console.example.com?x=1", "console.1")
        for given in bad:
            code, out, err, files = build(CONSOLE_HOST_NAME=given)
            self.assertEqual((code, out, files), (2, "", {}), given)
            self.assertIn("CONSOLE_HOST_NAME is a host name such as console.example.com", err, given)

    def test_one_of_the_apps_own_names_is_refused_because_it_is_the_name_of_no_gateway(self):
        for given in ("func-meternaut-cases-0a1b2c3d.azurewebsites.net", "FUNC-X.AZUREWEBSITES.NET", "func-x.scm.azurewebsites.net", "func-x.privatelink.azurewebsites.net"):
            code, out, err, files = build(CONSOLE_HOST_NAME=given)
            self.assertEqual((code, out, files), (2, "", {}), given)
            self.assertIn("not one of the app's own names", err, given)
            self.assertIn("leave it empty when there is no gateway name", err, given)

    def test_the_closed_cases_app_without_a_name_is_refused_in_every_action_and_says_what_would_not_be_checked(self):
        with mock.patch.object(ep, "CASES_APP_PUBLIC_NETWORK_ACCESS", "Disabled"):
            code, out, err, files = build()
        self.assertEqual((code, out, files), (2, "", {}), "nothing is written: no action runs on a combination that cannot be checked")
        for words in ("CASES_APP_PUBLIC_NETWORK_ACCESS (in tools/environment-params.py) is Disabled and CONSOLE_HOST_NAME is not set", "nobody could open the console",
                      "the check of its front door, which knocks from the runner, would have no address to knock at",
                      "what a visitor without a sign-in gets would not be checked", "once the gateway and its DNS record exist (environment/BOOTSTRAP.md)", "or leave the app's public access Enabled"):
            self.assertIn(words, err)

    def test_the_closed_cases_app_with_a_name_is_taken_and_the_name_and_the_value_reach_the_cases_file(self):
        with mock.patch.object(ep, "CASES_APP_PUBLIC_NETWORK_ACCESS", "Disabled"):
            code, out, err, files = build(CONSOLE_HOST_NAME="console.example.com")
        self.assertEqual((code, err), (0, ""))
        cases = values(files["cases.parameters.json"])
        self.assertEqual((cases["casesAppPublicNetworkAccess"], cases["consoleHostName"]), ("Disabled", "console.example.com"))
        lines = outputs(out)
        self.assertEqual((lines["cases_public_network_access"], lines["console_host"], lines["console_host_set"]), ("Disabled", "console.example.com", "true"))

    def test_an_open_cases_app_takes_a_name_or_none_and_a_closed_usage_app_needs_no_name(self):
        self.assertEqual((ep.USAGE_APP_PUBLIC_NETWORK_ACCESS, ep.CASES_APP_PUBLIC_NETWORK_ACCESS), ("Disabled", "Enabled"), "the settings that the repository has: only the cases app serves people")
        for given in ("", "console.example.com"):
            self.assertEqual(build(CONSOLE_HOST_NAME=given)[0], 0, given)
        with mock.patch.object(ep, "USAGE_APP_PUBLIC_NETWORK_ACCESS", "Enabled"), mock.patch.object(ep, "CASES_APP_PUBLIC_NETWORK_ACCESS", "Enabled"):
            self.assertEqual(build()[0], 0)

    def test_the_name_is_read_by_one_function_that_takes_the_variable_and_nothing_else(self):
        self.assertEqual(ep.console_host_name({}), "")
        self.assertEqual(ep.console_host_name({"CONSOLE_HOST_NAME": None}), "")
        self.assertEqual(ep.console_host_name({"CONSOLE_HOST_NAME": " Console.Example.COM "}), "console.example.com")
        self.assertEqual(ep.console_parameters({"CONSOLE_HOST_NAME": "console.example.com"})["consoleHostName"], "console.example.com")
        self.assertEqual(ep.console_parameters({})["consoleHostName"], "")
        self.assertEqual(ep.APP_OWN_DOMAIN, ".azurewebsites.net")


class TheCasesTemplateAndTheConsoleHostName(unittest.TestCase):
    """environment/cases/main.bicep: the setting CONSOLE_HOST, and the sign-in behind a reverse proxy."""

    def setUp(self):
        self.source = text("environment/cases/main.bicep")
        self.code = code_of(self.source)

    def test_the_name_is_an_optional_string_that_is_empty_by_default_and_the_parameter_file_fits_it(self):
        self.assertRegex(self.source, r"(?m)^param consoleHostName string = ''$")
        self.assertRegex(self.source, r"(?m)^@description\('The host name under which people open the console, [^\n]+'\)\nparam consoleHostName string = ''$")
        declared = {m.group(1): m.group(2) for m in re.finditer(r"(?m)^param (\w+) (\w+)", self.source)}
        self.assertEqual(declared["consoleHostName"], "string")
        _, _, _, files = build()
        self.assertIn("consoleHostName", files["cases.parameters.json"]["parameters"])

    def test_the_console_s_address_is_the_name_when_there_is_one_and_the_apps_own_name_when_there_is_none_and_one_setting_takes_it(self):
        self.assertIn("var consoleHost = empty(consoleHostName) ? '${functionAppName}.azurewebsites.net' : consoleHostName", self.code)
        self.assertEqual(re.findall(r"\{ name: 'CONSOLE_HOST', value: (.+?) \}", self.code), ["consoleHost"])
        self.assertEqual(self.code.count("name: 'CONSOLE_HOST'"), 1, "no other place gives the console's address a value")
        self.assertIn("output consoleUrl string = 'https://${consoleHost}'", self.code, "the output that names the console's address names the one that people open")
        self.assertNotIn("defaultHostName", self.code, "nothing takes the app's own name from the platform: the console's address is the variable above")
        self.assertNotIn("name: 'CONSOLE_HOST', value: '${functionAppName}", self.code)

    def test_the_sign_in_reads_the_host_from_the_header_that_the_gateway_adds_and_only_when_there_is_a_name(self):
        block = re.search(r"(?ms)^resource consoleSignIn 'Microsoft\.Web/sites/config@[0-9-]+' = if \(!empty\(consoleAppClientId\)\) \{\n.*?^\}\n", self.code)
        self.assertIsNotNone(block, "the sign-in is still made only when the app registration is named")
        settings = re.search(r"(?ms)^    httpSettings: \{\n(.*?)^    \}\n", block.group(0))
        self.assertIsNotNone(settings)
        self.assertEqual(
            settings.group(1),
            "      requireHttps: true\n      routes: {\n        apiPrefix: '/.auth'\n      }\n"
            "      forwardProxy: empty(consoleHostName) ? {\n        convention: 'NoProxy'\n      } : {\n        convention: 'Custom'\n        customHostHeaderName: 'X-Original-Host'\n      }\n",
            "the one setting that tells the sign-in where the original host is: Learn names httpSettings.forwardProxy for a reverse proxy, and the header X-Original-Host for Application Gateway")

    def test_nothing_else_of_the_sign_in_names_a_host_and_the_settings_that_the_gateway_does_not_need_are_not_set(self):
        self.assertNotIn("customProtoHeaderName", self.code, "the gateway connects to the app over HTTPS, so the scheme of the connection is the right one")
        self.assertNotIn("allowedExternalRedirectUrls", self.code, "an address within the app's own domain is allowed anyway, and the setting is for the backends of Windows Store apps")
        self.assertNotIn("X-Forwarded-Host", self.code, "the gateway adds X-Original-Host, and not this header")
        proxy = re.search(r"forwardProxy:.*?\n      \}\n", self.code, re.S).group(0)
        self.assertNotIn("'Standard'", proxy, "the convention is NoProxy or Custom: Standard reads X-Forwarded-Host, which the gateway does not send")
        self.assertIn("excludedPaths: [\n        '/healthz'\n      ]", self.code, "the probe of the gateway asks /healthz with no sign-in")

    def test_the_comment_cites_the_two_pages_of_learn_that_the_setting_rests_on(self):
        self.assertIn("https://learn.microsoft.com/azure/app-service/overview-app-gateway-integration#authentication-easy-auth", self.source)
        self.assertIn("https://learn.microsoft.com/azure/templates/microsoft.web/sites/config-authsettingsv2", self.source)


def find_bash():
    found = shutil.which("bash")
    for candidate in (found, r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
        if candidate and Path(candidate).exists():
            probe = subprocess.run([candidate, "-c", "echo ok"], capture_output=True, text=True)
            if probe.returncode == 0 and probe.stdout.strip() == "ok":
                return candidate
    return None


BASH = find_bash()


def step_script(name):
    """The `run:` script of the step with this name, as the runner would write it to a file."""
    block = re.search(rf"(?ms)^      - name: {re.escape(name)}\n(.*?)(?=^      - |\Z)", WORKFLOW)
    assert block, name
    run = re.search(r"(?ms)^        run: \|\n(.*)", block.group(1))
    assert run, name
    return textwrap.dedent(run.group(1))


def run_step_script(name, stand_ins, env, prelude=""):
    """Run the `run:` script of a step with bash, as the runner does, with stand-ins for the commands that it calls first on the PATH. A command that Git's own /usr/bin has (sleep) cannot be replaced
    from the PATH: give a shell function in `prelude`. Returns the finished process, the lines that the stand-ins logged and the summary that the step wrote."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        for command, body in stand_ins.items():
            path = bin_dir / command
            path.write_text(body, encoding="utf-8", newline="\n")
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        script = tmp / "step.sh"
        script.write_text(prelude + step_script(name), encoding="utf-8", newline="\n")
        log = tmp / "log.txt"
        log.write_text("", encoding="utf-8")
        (tmp / "summary.md").write_text("", encoding="utf-8")
        full = {**os.environ, "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": log.as_posix(), "FAKE_DIR": tmp.as_posix(),
                "GITHUB_STEP_SUMMARY": (tmp / "summary.md").as_posix(), "RUNNER_TEMP": tmp.as_posix(), **env}
        done = subprocess.run([BASH, "-e", "-o", "pipefail", script.as_posix()], capture_output=True, text=True, env=full, cwd=ROOT)
        return done, log.read_text(encoding="utf-8").splitlines(), (tmp / "summary.md").read_text(encoding="utf-8")


AZ = """#!/bin/bash
# stand-in for az in the steps that find the Operator, which only read: FAKE_IDENTITY_ID is what the list of the identity prints, FAKE_CLIENT what the read of the identity prints, and FAKE_SUBNET is ok,
# absent or throttled
echo "az $*" >> "$FAKE_LOG"
case "$*" in
  *"resource list"*) printf '%s' "$FAKE_IDENTITY_ID" ;;
  *"/userAssignedIdentities/"*) printf '%s' "$FAKE_CLIENT" ;;
  *"/subnets/snet-ops"*)
    case "$FAKE_SUBNET" in
      ok) echo snet-ops ;;
      absent) echo "ERROR: (ResourceNotFound) The Resource 'Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-ops' under resource group 'rg-of-the-project' was not found." >&2; exit 1 ;;
      throttled) echo "ERROR: (TooManyRequests) Too many requests for d0404e2a-5b6c-4d7e-8f90-a1b2c3d4e5f6, try again later." >&2; exit 1 ;;
    esac ;;
  *) echo "unexpected az call: $*" >&2; exit 9 ;;
esac
"""

PYTHON3 = """#!/bin/bash
# stand-in for python3: one line for the program and one line, indented, for each argument. It fails FAKE_FAILS times with exit code 1, and then it exits with FAKE_EXIT (0 by default).
{ echo "python3"; for argument in "$@"; do echo "  $argument"; done; } >> "$FAKE_LOG"
count=$(cat "$FAKE_DIR/count" 2> /dev/null || echo 0)
count=$((count + 1))
echo "$count" > "$FAKE_DIR/count"
if [ "$count" -le "${FAKE_FAILS-0}" ]; then exit 1; fi
exit "${FAKE_EXIT-0}"
"""


def called(lines):
    """The calls that the stand-in python3 logged, as lists of arguments (the first one is the tool), and the other lines that the stand-ins logged."""
    calls, other = [], []
    for line in lines:
        if line == "python3":
            calls.append([])
        elif line.startswith("  ") and calls:
            calls[-1].append(line[2:])
        else:
            other.append(line)
    return calls, other


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheHealthCheckOfTheCasesAppRunsInsideTheNetwork(unittest.TestCase):
    """The step that waits until the cases app answers, run with bash against stand-ins for az and python3: once the app is closed this runner cannot ask its health address, so a container group of the
    Operator does, over the private endpoint. The step finds the Operator as the publish does, changes nothing, gives the container no token of the deploy identity and passes the tool's exit code on."""

    TITLE = "Wait until the cases app answers"
    SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
    GROUP = "rg-of-the-project"
    APP = "func-meternaut-cases-0a1b2c3d"
    SUBNET = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.Network/virtualNetworks/vnet-meternaut/subnets/snet-ops"
    IDENTITY = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-meternaut-operator"
    IMAGE = "mcr.microsoft.com/azure-cli@sha256:" + "ab" * 32
    CLIENT = "6e5f3a1c-2b7d-4c8e-9f10-3a4b5c6d7e8f"
    ARGS = f"health --host {APP}.azurewebsites.net --tries 60 --interval 10 --timeout 15 --private"

    def run_step(self, identity=None, client=None, subnet="ok", exit_code=0, dns="10.20.0.4,10.20.0.5"):
        env = {"ENV_SUBSCRIPTION_ID": self.SUBSCRIPTION, "ENV_RESOURCE_GROUP": self.GROUP, "ENV_DNS_SERVERS": dns, "GITHUB_RUN_ID": "1234567890", "OPERATOR_IMAGE": self.IMAGE, "ACTION": "cases",
               "FUNCTION_APP": self.APP, "FAKE_IDENTITY_ID": self.IDENTITY if identity is None else identity, "FAKE_CLIENT": self.CLIENT if client is None else client, "FAKE_SUBNET": subnet,
               "FAKE_EXIT": str(exit_code)}
        done, lines, summary = run_step_script(self.TITLE, {"az": AZ, "python3": PYTHON3}, env)
        calls, other = called(lines)
        return done, calls, other

    def expected(self, dns=("10.20.0.4", "10.20.0.5")):
        return (["tools/operator-run.py", "run", "--resource-group", self.GROUP, "--name", "op-health-1234567890", "--subnet-id", self.SUBNET, "--identity-id", self.IDENTITY, "--image", self.IMAGE,
                 "--script", "operator/run-tool.sh", "--secret-file", "console-check.py=tools/console-check.py",
                 "--env", f"OPERATOR_CLIENT_ID={self.CLIENT}", "--env", f"OPERATOR_SUBSCRIPTION={self.SUBSCRIPTION}", "--env", "TOOL_NAME=console-check", "--env", f"TOOL_ARGS={self.ARGS}"]
                + [word for server in dns for word in ("--dns-server", server)] + ["--timeout-seconds", "1800", "--summary"])

    def test_the_call_runs_the_tool_in_the_container_on_the_apps_own_name_with_the_operators_own_identity_and_no_token(self):
        done, calls, other = self.run_step()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        (argv,) = calls
        self.assertEqual(argv[:-1], self.expected())
        self.assertTrue(argv[-1].endswith("summary.md"), "the log of the container goes into the summary of the run")
        for word in argv:
            self.assertNotIn("--secure-env", word)
            self.assertNotIn("AZURE_FEDERATED_TOKEN", word)
        self.assertEqual([line for line in other if line.startswith("az ")], [
            "az resource list --resource-group rg-of-the-project --name id-meternaut-operator --query [0].id --output tsv",
            f"az rest --method get --url https://management.azure.com{self.IDENTITY}?api-version=2023-01-31 --query properties.clientId --output tsv",
            f"az rest --method get --url https://management.azure.com{self.SUBNET}?api-version=2025-05-01 --query name --output tsv"],
            "three reads, and nothing is changed: the container signs in as the Operator's own identity, whose client id is read here")

    def test_the_call_is_accepted_by_the_operator_tool_and_the_arguments_fit_the_container_script(self):
        done, calls, _ = self.run_step()
        (argv,) = calls
        args = operator_tool.build_parser().parse_args(argv[1:])
        plain, secure, servers = operator_tool.check_options(args)
        with contextlib.chdir(ROOT):
            files = operator_tool.read_files(args)
        self.assertEqual((secure, servers), ([], ["10.20.0.4", "10.20.0.5"]), "no secure value: nothing in the call is a secret")
        self.assertEqual(dict(plain), {"OPERATOR_CLIENT_ID": self.CLIENT, "OPERATOR_SUBSCRIPTION": self.SUBSCRIPTION, "TOOL_NAME": "console-check", "TOOL_ARGS": self.ARGS})
        self.assertEqual(sorted(files), ["console-check.py", "run-tool.sh"])
        self.assertEqual(files["console-check.py"], (ROOT / "tools" / "console-check.py").read_bytes(), "the tool goes whole")
        self.assertLess(sum(len(content) for content in files.values()), operator_tool.MAX_FILE_BYTES)
        self.assertEqual((args.name, args.timeout_seconds), ("op-health-1234567890", 1800))
        script = text("operator/run-tool.sh")
        characters = re.search(r"argument_characters='([^']+)'", script).group(1)
        command_word = re.search(r"command_word='([^']+)'", script).group(1)
        tool_name = re.search(r"tool_name='([^']+)'", script).group(1)
        self.assertRegex(self.ARGS, characters)
        self.assertLessEqual(len(self.ARGS), 600)
        self.assertRegex(self.ARGS.split()[0], command_word)
        self.assertRegex("console-check", tool_name)

    def test_the_tool_takes_the_arguments_that_the_step_builds_and_asks_the_health_address_over_a_private_address_only(self):
        done, calls, _ = self.run_step()
        (argv,) = calls
        arguments = dict(word.split("=", 1) for word in argv if word.startswith(("TOOL_ARGS=", "TOOL_NAME=")))
        words = arguments["TOOL_ARGS"].split()
        asked = []

        def get(url, headers, timeout):
            asked.append((url, timeout))
            return 200, {}, b"ok"

        out = io.StringIO()
        self.assertEqual(cc.main(words, get=get, out=out, resolve=lambda host: ["10.53.0.4"], sleep=lambda seconds: None), 0, out.getvalue())
        self.assertEqual(asked, [(f"https://{self.APP}.azurewebsites.net/healthz", 15.0)])
        self.assertIn("(private)", out.getvalue())
        asked.clear()
        out = io.StringIO()
        sleeps = []
        self.assertEqual(cc.main(words, get=get, out=out, resolve=lambda host: ["20.1.2.3"], sleep=sleeps.append), 1, "a public address is refused: the check is of the path that people take")
        self.assertEqual((asked, len(sleeps)), ([], 59), "no request is made to it, and the tool waits between its 60 tries")
        self.assertIn("a private address is required", out.getvalue())

    def test_an_operator_that_is_not_there_stops_the_step_before_anything_is_started_and_says_to_run_operator_first(self):
        for identity, client in (("", None), ("None", None), ("/not/a/subscription", None), (None, ""), (None, "not-a-guid"), (None, f"{self.CLIENT} x")):
            done, calls, other = self.run_step(identity=identity, client=client)
            self.assertEqual(done.returncode, 1, (identity, client))
            self.assertIn("The identity id-meternaut-operator is not there. The action cases asks the app's health address from inside the network, in the Operator, so run operator first, and then cases again. "
                          "The code was published, and the health of the app was not checked.", done.stdout, (identity, client))
            self.assertEqual(calls, [], "no container group is made")

    def test_a_subnet_that_is_not_there_or_cannot_be_read_stops_the_step_with_what_it_said(self):
        done, calls, _ = self.run_step(subnet="absent")
        self.assertEqual((done.returncode, calls), (1, []))
        self.assertIn("The subnet snet-ops is not there. The action cases asks the app's health address from inside the network, in the Operator, so run operator first, and then cases again.", done.stdout)
        done, calls, _ = self.run_step(subnet="throttled")
        self.assertEqual((done.returncode, calls), (1, []))
        self.assertIn("The subnet snet-ops could not be read: ERROR: (TooManyRequests) Too many requests for d0404e2a-5b6c-4d7e-8f90-a1b2c3d4e5f6, try again later.", done.stdout,
                      "an answer that holds the digits 404 inside an id is not taken for NotFound")
        self.assertNotIn("run operator first", done.stdout)

    def test_the_exit_code_of_the_tool_is_the_exit_code_of_the_step_and_the_step_says_what_to_read(self):
        for code in (1, 2, 124):
            done, calls, _ = self.run_step(exit_code=code)
            self.assertEqual(done.returncode, code)
            self.assertEqual(len(calls), 1, "the group is made once")
            self.assertIn(f"::error::The cases app does not answer on /healthz from inside the network (the exit code is {code};", done.stdout)
            self.assertIn("a container that does not answer to the platform's start probe", done.stdout)

    def test_the_landing_zone_s_dns_servers_are_given_one_flag_each_and_none_when_there_are_none(self):
        for dns, servers in (("10.20.0.4", ["10.20.0.4"]), ("10.20.0.4,10.20.0.5,10.20.0.6", ["10.20.0.4", "10.20.0.5", "10.20.0.6"]), ("", [])):
            done, calls, _ = self.run_step(dns=dns)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            argv = calls[0]
            self.assertEqual([argv[i + 1] for i, word in enumerate(argv) if word == "--dns-server"], servers, dns)

    def test_the_step_only_reads_and_asks_nothing_of_the_app_from_the_runner(self):
        done, calls, other = self.run_step()
        for call in [line for line in other if line.startswith("az ")]:
            self.assertRegex(call, r"^az (resource list|rest --method get) ")
        script = code_of(step_script(self.TITLE))
        for word in ("curl", "wget", "Invoke-WebRequest", "https://$FUNCTION_APP", "az role", "az container", "--method put", "--method post", "--method delete", "listKeys", "listSecrets"):
            self.assertNotIn(word, script, word)


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheCleanupOfTheHealthCheckGroup(unittest.TestCase):
    """The second line behind the tool's own delete: it asks the tool for the groups of the health check and a failure is only a warning."""

    TITLE = "Delete any container group of the health check of the cases app that is left"
    GROUP = "rg-of-the-project"

    def test_the_tool_is_asked_for_the_groups_that_start_with_the_name_of_the_health_check_and_the_call_is_accepted(self):
        done, lines, _ = run_step_script(self.TITLE, {"python3": PYTHON3}, {"ENV_RESOURCE_GROUP": self.GROUP})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        calls, _ = called(lines)
        self.assertEqual(calls, [["tools/operator-run.py", "cleanup", "--resource-group", self.GROUP, "--prefix", "op-health-", "--older-than-minutes", "0"]])
        args = operator_tool.build_parser().parse_args(calls[0][1:])
        self.assertEqual((args.prefix, args.older_than_minutes, args.resource_group), ("op-health-", 0.0, self.GROUP))
        self.assertTrue("op-health-1234567890".startswith(args.prefix), "the prefix is the start of the name that the health step gives its group")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
                self.assertEqual(operator_tool.cleanup_command(args, lambda arguments: (0, "[]", "")), 0, "the prefix is one that the tool accepts")

    def test_a_group_that_could_not_be_deleted_is_a_warning_and_does_not_fail_a_run_that_was_good(self):
        done, lines, _ = run_step_script(self.TITLE, {"python3": PYTHON3}, {"ENV_RESOURCE_GROUP": self.GROUP, "FAKE_EXIT": "1"})
        self.assertEqual(done.returncode, 0)
        self.assertIn("::warning::A container group whose name starts with op-health- may be left in resource group rg-of-the-project.", done.stdout)


@unittest.skipIf(BASH is None, "no bash on this machine")
class TheKnockAtTheConsolesFrontDoor(unittest.TestCase):
    """The step that knocks at the front door, run with bash against a stand-in for python3: it knocks at the name that people open (the console's host name on the platform's Application Gateway
    when there is one), says what it cannot check, and is never left out without a word."""

    TITLE = "Knock at the console's front door"
    APP_NAME = "func-meternaut-cases-0a1b2c3d.azurewebsites.net"
    PROLOGUE = "sleep() { :; }\n"

    def knock(self, host=None, host_set="false", access="Enabled", client="11111111-2222-3333-4444-555555555555", fails=0, exit_code=0):
        env = {"CONSOLE_HOST": host or self.APP_NAME, "CONSOLE_HOST_SET": host_set, "CASES_PUBLIC_ACCESS": access, "CONSOLE_APP_CLIENT_ID": client, "FAKE_FAILS": str(fails), "FAKE_EXIT": str(exit_code)}
        done, lines, _ = run_step_script(self.TITLE, {"python3": PYTHON3}, env, prelude=self.PROLOGUE)
        calls, _ = called(lines)
        return done, calls

    def test_with_no_name_the_front_door_is_knocked_at_on_the_apps_own_name_as_before_and_the_return_address_is_not_asked_to_name_a_host(self):
        done, calls = self.knock()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        (argv,) = calls
        self.assertEqual(argv[:-1], ["tools/console-check.py", "door", "--host", self.APP_NAME, "--expect", "signin", "--summary"])
        self.assertTrue(argv[-1].endswith("summary.md"))
        self.assertNotIn("--proxied", argv)

    def test_a_sign_in_that_is_not_set_up_is_expected_to_refuse_every_request(self):
        done, calls = self.knock(client="")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(calls[0][:6], ["tools/console-check.py", "door", "--host", self.APP_NAME, "--expect", "refuse"])

    def test_with_a_name_it_knocks_at_the_name_and_asks_that_the_sign_ins_return_address_names_it_whether_the_app_is_open_or_closed(self):
        for access in ("Enabled", "Disabled"):
            done, calls = self.knock(host="console.example.com", host_set="true", access=access)
            self.assertEqual(done.returncode, 0, (access, done.stdout + done.stderr))
            (argv,) = calls
            self.assertEqual(argv[:-1], ["tools/console-check.py", "door", "--host", "console.example.com", "--expect", "signin", "--proxied", "--summary"], access)

    def test_a_closed_app_with_no_name_is_not_checked_and_the_step_says_so_and_fails_instead_of_leaving_the_check_out(self):
        done, calls = self.knock(access="Disabled", host_set="false")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(calls, [], "nothing is knocked at")
        self.assertIn("::error::NOT CHECKED: the front door of the console. The cases app takes no public traffic and no console host name is set (the repository variable CONSOLE_HOST_NAME), "
                      "so there is no address that this runner can knock at, and what a visitor without a sign-in gets is not known. Nothing was changed.", done.stdout)

    def test_a_door_that_does_not_answer_as_expected_is_tried_five_times_and_fails_the_run_and_one_that_answers_later_passes(self):
        done, calls = self.knock(fails=99)
        self.assertEqual((done.returncode, len(calls)), (1, 5))
        self.assertIn("The front door did not answer as expected (attempt 5 of 5).", done.stdout)
        self.assertIn("::error::The console's front door is not shut as it should be.", done.stdout)
        done, calls = self.knock(fails=2)
        self.assertEqual((done.returncode, len(calls)), (0, 3))

    def test_the_arguments_that_the_step_builds_are_the_ones_that_the_tool_takes_and_the_door_behind_a_proxy_is_judged_by_the_return_address(self):
        done, calls = self.knock(host="console.example.com", host_set="true")
        (argv,) = calls
        words = argv[1:-2]
        self.assertEqual(words[0], "door")
        asked = []

        def door(host, return_to):
            def get(url, headers):
                asked.append(url)
                if url.endswith("/healthz"):
                    return 200, {}, b"ok"
                target = f"https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize?redirect_uri=https%3A%2F%2F{return_to}%2F.auth%2Flogin%2Faad%2Fcallback&client_id=x"
                return 302, {"location": target}, b""
            return cc.main(words, get=get, out=io.StringIO())

        self.assertEqual(door("console.example.com", "console.example.com"), 0, "a return address that names the gateway's host passes")
        self.assertEqual(door("console.example.com", self.APP_NAME), 1, "one that names the app's own name fails: the closed app answers nobody there")
        self.assertTrue(all(url.startswith("https://console.example.com/") for url in asked), "every request goes to the name that people open")


def anchor(heading):
    """The anchor that GitHub makes of a heading: lower case, punctuation taken out, spaces made hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.lstrip("# ").lower()).replace(" ", "-")


def section_of(page, heading):
    return page.split(heading, 1)[1].split("\n## ", 1)[0]


class TheDocumentsOfTheConsoleBehindTheGateway(unittest.TestCase):
    """The decision record, the bootstrap page, the changelog and the pages that point at them: they say what is built, what is not deployed, what Learn says, what the platform team adds and what is not proven."""

    HEADING = "## Publishing code to the private apps: phase 3 for the cases app, the console behind the platform's Application Gateway (built, not deployed)"
    BOOTSTRAP_HEADING = "## Changed on 2026-11-06: the console behind the platform's Application Gateway"
    CHANGELOG_HEADING = "## The console behind the platform's Application Gateway, so that the cases app can be closed (built, not deployed) — 2026-11-06"
    OLDER_HEADING = "## Agents through the gateway: the reason given for the exception was wrong, and a keyless route is documented — 2026-11-06"

    def setUp(self):
        self.page = text("docs/proposals/07-private-by-default.md")
        self.section = section_of(self.page, self.HEADING)
        self.bootstrap = text("environment/BOOTSTRAP.md")
        self.bootstrap_section = section_of(self.bootstrap, self.BOOTSTRAP_HEADING)
        self.changelog = text("CHANGELOG.md")
        self.entry = section_of(self.changelog, self.CHANGELOG_HEADING)

    def block(self, section):
        (script,) = re.findall(r"```powershell\n(.*?)\n```", section, re.S)
        return script

    def test_the_section_sits_after_the_usage_apps_phase_3_and_before_the_telemetry_section_and_every_link_to_it_names_its_anchor(self):
        usage = "## Publishing code to the private apps: phase 3 for the usage app (deployed and proven on 2026-11-06)"
        self.assertLess(self.page.index(usage), self.page.index(self.HEADING))
        self.assertLess(self.page.index(self.HEADING), self.page.index("## Reading telemetry when the component is private"))
        mine = anchor(self.HEADING)
        self.assertEqual(mine, "publishing-code-to-the-private-apps-phase-3-for-the-cases-app-the-console-behind-the-platforms-application-gateway-built-not-deployed")
        pages = {name: text(name) for name in ("docs/proposals/07-private-by-default.md", "docs/proposals/04-the-loop.md", "docs/proposals/05-run-as-the-approver.md", "README.md", "CHANGELOG.md",
                                               "environment/BOOTSTRAP.md")}
        for name, page in pages.items():
            for found in re.findall(r"#(publishing-code-to-the-private-apps-phase-3-for-the-cases-app[^)\s]*)", page):
                self.assertEqual(found, mine, f"{name} links to an anchor that the heading does not make")
        for name in ("docs/proposals/07-private-by-default.md", "docs/proposals/04-the-loop.md", "docs/proposals/05-run-as-the-approver.md", "README.md", "CHANGELOG.md", "environment/BOOTSTRAP.md"):
            self.assertIn(f"#{mine}", pages[name], f"{name} points at the section")
        mine_bootstrap = anchor(self.BOOTSTRAP_HEADING)
        for name in ("docs/proposals/07-private-by-default.md", "CHANGELOG.md", "environment/BOOTSTRAP.md"):
            self.assertIn(f"#{mine_bootstrap}", pages[name], f"{name} points at the bootstrap section")
        for name, page in pages.items():
            for found in re.findall(r"#(changed-on-2026-11-06-the-console-behind[^)\s]*)", page):
                self.assertEqual(found, mine_bootstrap, name)

    def test_the_decision_is_in_the_owners_words_and_the_record_says_that_nothing_is_deployed_and_that_the_constant_stays_enabled(self):
        for words in ("\"In general, public endpoints are not allowed. You can only connect through gateways (App GW or API Mgmt).\"", "\"THAT CAN BE PRIVATE.\"",
                      "Nothing is deployed: no Azure change was made, no Hub run was made, and the cases app is still public (`casesAppPublicNetworkAccess` is `Enabled`).",
                      "a path into the network for each approver, and Azure Front Door with Private Link, are not chosen",
                      "**The constant stays `Enabled`.** `CASES_APP_PUBLIC_NETWORK_ACCESS` in `tools/environment-params.py` is not changed here. The parameter builder refuses `Disabled` while `CONSOLE_HOST_NAME` is empty",
                      "That value flips in a later change, after the gateway objects exist and the owner has said yes"):
            self.assertIn(words, self.section, words)
        decisions = section_of(self.page, "## Decisions for the owner")
        self.assertIn("**The console for people (decided on 2026-11-06).**", decisions)
        self.assertIn("The owner chose neither.", decisions)
        self.assertNotIn("Until the owner says which, the cases app stays public", self.page)

    def test_the_changes_in_the_repository_are_listed_with_the_variable_the_template_the_two_checks_the_refusal_and_the_return_addresses(self):
        for words in ("1. **A new optional repository variable, `CONSOLE_HOST_NAME`:**", "It is an address and no secret", "`vars.` in the job's `env`", "and it is written nowhere in the repository",
                      "refuses a value that is not a host name, and a value that is one of the app's own names (`<app>.azurewebsites.net`)",
                      "2. **The template.**", "The setting `CONSOLE_HOST` is that name when there is one, and `<app>.azurewebsites.net` when there is none.", "so no code of the app changes",
                      "`httpSettings.forwardProxy` with the convention `Custom` and the header `X-Original-Host`. Without one it gets `NoProxy`, its default (inferred:",
                      "3. **The two checks that asked the app on its public name.**", "*The wait until the app answers* runs in the Operator.", "(`op-health-<run id>`)", "`health` through [`operator/run-tool.sh`]",
                      "at most 60 tries of at most 15 seconds, ten seconds apart", "With `--private` the name has to resolve to a private address inside the network",
                      "The container signs in as the Operator's own identity and holds no token of the deploy identity.", "Its two files are about 21 KB, far below the 480,000 bytes that a request takes",
                      "A fresh sign-in comes before the step", "a step after it deletes any group that is left (the prefix is `op-health-`)",
                      "*The check of the front door* knocks at the console's host name when there is one.", "so the check is of the path that people take",
                      "never a page: for every path of the console, for `/arm/return` with and without a code, and with a made-up sign-in header",
                      "(`redirect_uri`, or `post_login_redirect_uri` when the redirect is the sign-in's own)", "Without a host name the check knocks at the app's own name, as before.",
                      "*What is refused.* A closed app with no host name has no address that the runner can knock at", "says \"NOT CHECKED\" and stops",
                      "4. **The return addresses.**", "needs no new option: `--host` is the name that people open", "removes nothing. The addresses of the app's own name stay until a person removes them in the portal"):
            self.assertIn(words, self.section, words)
        sizes = (ROOT / "tools" / "console-check.py").stat().st_size + (ROOT / "operator" / "run-tool.sh").stat().st_size
        self.assertLess(sizes, 22_000, "about 21 KB, as the record says")
        self.assertGreater(sizes, 20_000)

    def test_what_learn_says_is_quoted_with_its_pages_and_the_two_differences_from_the_plan_are_named(self):
        table = self.section.split("**What Learn says** (read on 2026-11-06).")[1].split("**Where Learn says something other than the plan assumed.**")[0]
        for words in ("\"Because App Service doesn't know the original host name of the request, the redirect is done on the default domain name and usually results in an error.\"",
                      "\"Application Gateway uses a header named `X-Original-Host`\"", "`httpSettings.forwardProxy` with `convention` `Custom` and `customHostHeaderName` `X-Original-Host`",
                      "`forwardProxy` has the conventions `NoProxy`, `Standard` and `Custom`", "\"Other reverse proxies, like Azure Application Gateway or non-Microsoft products, might use different headers and need a different forwardProxy setting.\"",
                      "\"You need to use az rest\"", "\"Application gateway inserts six additional headers to all requests before it forwards the requests to the backend\"",
                      "`x-forwarded-for`, `x-forwarded-port`, `x-forwarded-proto`, `x-original-host`, `x-original-url` and `x-appgw-trace-id`",
                      "\"URLs within the current domain are always implicitly allowed\"", "\"typically only needed by Windows Store application backends\"", "\"You might need to restart the application gateway\"",
                      "\"It isn't possible to use reverse proxy for the SCM site.\"", "\"a healthy HTTP response has a status code between 200 and 399\"", "\"The default is 20 seconds.\"",
                      "\"In most cases, you shouldn't override the host name.\"", "\"the free App Service managed certificate can't be used\"",
                      "\"Never use the value of the host in a security mechanism. The browser or another user agent provides the value, and a user can change it.\""):
            self.assertIn(words, table, words)
        for page in ("app-service/overview-app-gateway-integration", "templates/microsoft.web/sites/config-authsettingsv2", "app-service/overview-authentication-authorization", "application-gateway/how-application-gateway-works",
                     "application-gateway/application-gateway-probe-overview", "application-gateway/configuration-http-settings", "architecture/best-practices/host-name-preservation"):
            self.assertIn(f"https://learn.microsoft.com/azure/{page}", table, page)
            self.assertIn(f"https://learn.microsoft.com/azure/{page}", self.page.split("\n## Sources", 1)[1], f"{page} is in the sources")
        differs = self.section.split("**Where Learn says something other than the plan assumed.**")[1].split("**The other way, which Learn recommends, and why it is not chosen.**")[0]
        for words in ("Learn says that it inserts the six headers into all requests, so the header is there whether or not the host is overridden.",
                      "Learn recommends the opposite for a reverse proxy, which is to preserve the host.", "This change follows the platform's pattern and names the other way next, so that the owner can choose it."):
            self.assertIn(words, differs, words)
        other = self.section.split("**The other way, which Learn recommends, and why it is not chosen.**")[1].split("**What this does to the security of the console.**")[0]
        for words in ("attach `<console host name>` to the cases app as a custom domain, validate it with a TXT record", "the free managed certificate cannot be used behind a proxy",
                      "The sign-in then needs no `forwardProxy`.", "What it costs:", "What it gives:", "It is not chosen because the platform's other apps use the override"):
            self.assertIn(words, other, words)

    def test_the_five_objects_the_dns_record_and_what_is_not_an_object_are_named(self):
        objects = self.section.split("**The objects that the platform team adds.**")[1].split("**Who adds them, and how.**")[0]
        rows = [line for line in objects.split("\n") if line.startswith("| ") and not line.startswith(("| Object", "|---"))]
        self.assertEqual([row.split(" | ")[0] for row in rows], ["| HTTPS listener", "| Backend pool", "| Backend setting", "| Custom probe", "| Routing rule", "| DNS record"])
        joined = "\n".join(rows)
        for words in ("The gateway's public frontend IP configuration, port 443, the console's host name, and the platform's certificate", "One target: the cases app's own name, `<cases app name>.azurewebsites.net`",
                      "HTTPS, port 443, the host name picked from the backend address, the probe below, no cookie affinity (the app sets none), and the platform's usual request timeout",
                      "HTTPS, the host name taken from the backend setting, the path `/healthz`, healthy only when the status is 200", "A basic rule for the listener, with the pool and the setting, and a priority that no other rule has",
                      "One CNAME record set for the console's host name in the platform owner's public zone, pointing to the gateway's public name", "Meternaut creates no zone ([rule 19](../../AGENTS.md))",
                      "The default probe would count the redirect to the sign-in as healthy"):
            self.assertIn(words, joined, words)
        self.assertIn("Two more things are not objects of the gateway: the return addresses in Microsoft Entra (item 4 above), and the repository variable.", objects)
        self.assertIn("clientAffinityEnabled: false", text("environment/cases/main.bicep"), "the app sets no affinity cookie, as the table says")
        self.assertIn("excludedPaths: [\n        '/healthz'\n      ]", text("environment/cases/main.bicep"), "the probe's path is the one that the app serves with no sign-in")

    def test_the_commands_are_the_same_in_the_record_and_on_the_bootstrap_page_read_before_they_write_and_delete_nothing(self):
        record, bootstrap = self.block(self.section), self.block(self.bootstrap_section)
        self.assertEqual(record, bootstrap, "one block, in two places")
        comments = re.findall(r"(?m)^# (\d)\. ", record)
        self.assertEqual(comments, ["1", "2", "3", "4", "5", "6", "7"])
        steps = re.split(r"(?m)^# \d\. .*$", record)[1:]
        self.assertEqual(len(steps), 7)
        for line in steps[0].strip().split("\n"):
            self.assertRegex(line, r"^az network (application-gateway [\w-]+|dns record-set) list ", "step 1 only lists")
        creates = re.findall(r"(?m)^az network application-gateway ([\w-]+) create ", steps[1])
        self.assertEqual(creates, ["address-pool", "probe", "http-settings", "http-listener", "rule"], "each object is made after the one that it refers to")
        self.assertEqual(len(steps[1].strip().split("\n")), 5)
        self.assertIn("show-backend-health", steps[2])
        self.assertEqual(len(re.findall(r"(?m)^az ", steps[3])), 2)
        self.assertRegex(steps[3], r"(?m)^az network public-ip show ")
        self.assertRegex(steps[3], r"(?m)^az network dns record-set cname set-record .* --if-none-match$")
        self.assertIn("python tools/console-check.py door --host $console --expect signin", steps[4])
        self.assertNotIn("--proxied", steps[4], "the sign-in does not know the host yet, so its return address is not asked for")
        self.assertIn("python tools/entra-setup.py check", steps[5])
        self.assertIn("python tools/entra-setup.py apply", steps[5])
        self.assertIn("gh variable set CONSOLE_HOST_NAME --repo $repo --body $console", steps[6])
        code = "\n".join(line for line in record.split("\n") if not line.startswith("#"))
        for word in (r"\bdelete\b", r"\bupdate\b", r"\bpurge\b", r"az role", r"private-dns", r"dns zone", r"--force", r"az group", r"az resource", r"application-gateway stop", r"application-gateway start", r"restart",
                     r"--yes", r"az login", r"az account"):
            self.assertNotRegex(code, word, word)
        self.assertEqual(len(re.findall(r"(?m)^az network application-gateway \S+ create ", record)), 5)
        verbs = [match.group(1).split()[-1] for match in re.finditer(r"(?m)^az ((?:[\w-]+ )+)--", record)]
        self.assertEqual([verb for verb in verbs if verb not in ("list", "show", "show-backend-health")], ["create"] * 5 + ["set-record"], "five objects and one record: nothing else is written")
        self.assertNotRegex(record, r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}", "no id")
        self.assertEqual(len(re.findall(r"\$gwSub", record)), len(re.findall(r"--subscription \$gwSub", record)) + 1, "every call at the gateway names the gateway's subscription")

    def test_the_block_parses_as_powershell_in_every_engine_on_this_machine_because_every_placeholder_is_a_quoted_value(self):
        record = self.block(self.section)
        engines = [path for path in (shutil.which("pwsh"), shutil.which("powershell")) if path]
        if not engines:
            self.skipTest("no PowerShell on this machine")
        script = ("$s = [Console]::In.ReadToEnd(); $e = $null; $t = $null; [System.Management.Automation.Language.Parser]::ParseInput($s, [ref]$t, [ref]$e) | Out-Null; "
                  "$e | ForEach-Object { $_.Message + ' @ line ' + $_.Extent.StartLineNumber }")
        for engine in engines:
            done = subprocess.run([engine, "-NoProfile", "-NonInteractive", "-Command", script], input=record, capture_output=True, text=True, timeout=120)
            self.assertEqual((done.returncode, done.stdout.strip()), (0, ""), f"{engine}: {done.stdout}{done.stderr}")
        for line in record.split("\n"):
            if not line.startswith("#"):
                self.assertNotRegex(re.sub(r"'[^']*(?:''[^']*)*'", "''", line), r"<", f"a placeholder outside quotes: {line[:80]}")

    def test_the_order_stops_at_the_health_of_the_new_pool_and_the_flip_is_a_change_of_its_own_after_the_owners_yes(self):
        order = self.section.split("**The order of the steps.**")[1].split("**The way back**")[0]
        positions = [order.index(f"\n{number}. ") if number > 1 else order.index("\n1. ") for number in range(1, 9)]
        self.assertEqual(positions, sorted(positions))
        for words in ("1. The owner says yes in plain words, to each of the five gateway objects, the DNS record, the return addresses and the variable.",
                      "The health of the new pool is read (step 3). It has to say Healthy. Anything else is the first answer to the question that is not proven below, whether the gateway reaches the app's private endpoint "
                      "through the hub, and the work stops here with nothing else changed.", "a restart stops every site behind it, so that is the platform team's decision",
                      "Now the whole path has been shown with no change to the app", "the browser check of [rule 28](../../AGENTS.md) through the console's host name",
                      "8. Only then, in a change of its own and after the owner's yes: `CASES_APP_PUBLIC_NETWORK_ACCESS` is set to `Disabled`, the test that pins it is changed with it, and `cases` runs once more."):
            self.assertIn(words, order, words)
        way_back = self.section.split("**The way back** is one constant and one run")[1].split("**Cost.**")[0]
        for words in ("set `CASES_APP_PUBLIC_NETWORK_ACCESS` back to `Enabled` and run `cases`", "clear the variable and run `cases` (the constant goes first, because the parameter builder refuses `Disabled` with no host name)",
                      "The platform team removes the five objects by their names.", "The return addresses of the app's own name were never removed"):
            self.assertIn(words, way_back, words)
        who = self.section.split("**Who adds them, and how.**")[1].split("```powershell")[0]
        for words in ("[rule 15 (b)](../../AGENTS.md) applies: the owner approves each object in plain words first.", "the deploy identity holds no right at the gateway or in the zone, and gets none",
                      "That makes the steps break-glass under [rule 18](../../AGENTS.md). The agent runs them with the owner's own Azure CLI session, on his written word, and reports at once. The owner runs no script.",
                      "Nothing is deleted."):
            self.assertIn(words, who, words)

    def test_the_cost_and_what_is_not_proven_are_written_down_and_the_not_proven_list_holds_what_the_real_set_up_will_show(self):
        cost = self.section.split("**Cost.**")[1].split("**What is not proven.**")[0]
        for words in ("lists no meter for a listener, a rule, a pool, a setting or a probe of an Application Gateway", "0.26 US dollars an hour", "is the platform's and is paid already",
                      "the first 10,000 record sets of a public zone", "about 2.7 US cents", "Nothing standing is added."):
            self.assertIn(words, cost, words)
        unproven = self.section.split("**What is not proven.**")[1]
        for words in ("None of it has run.", "Whether traffic from the gateway reaches the app's private endpoint.", "the traffic crosses the hub", "it is the first thing the real set-up shows (step 3 of the order)",
                      "Whether the gateway resolves the app's name to the endpoint's address", "the two pages of Learn differ on that", "How the certificate and the host name behave.",
                      "a certificate from a private authority would make it fail with a certificate error, and it would say so",
                      "Whether the sign-in redirects as Learn describes when `forwardProxy` is `Custom`", "Only the first real sign-in shows this.", "`login.allowedExternalRedirectUrls`",
                      "What the gateway does with an `X-Original-Host` that the client sends.", "Whether the sign-in refuses an authenticated POST through the gateway with an empty 403 ([rule 28](../../AGENTS.md)).",
                      "20 seconds by default", "Whether the list of the app's four functions", "WebSockets are not used. The console's content security policy is `default-src 'none'`"):
            self.assertIn(words, unproven, words)
        self.assertIn("default-src 'none'", text("src/case-functions/cases/web/layout.py"), "the policy that the record cites")

    def test_the_status_the_state_table_the_order_of_the_work_the_not_checked_list_and_the_other_pages_say_the_same(self):
        status = self.page.split("\n")[2]
        self.assertIn("The owner then decided that the cases app, which also serves the console, is closed too and that people reach the console only through the platform's Application Gateway; the code, the tests "
                      "and the documents for that are built, nothing is deployed, and the app is still public", status)
        self.assertNotIn("built, not yet deployed", status)
        state = section_of(self.page, "## The rule and the state")
        cases = [line for line in state.split("\n") if line.startswith("| Cases function app (Basic plan;")][0]
        self.assertIn("**Enabled**, until phase 3 for this app. The owner decided on 2026-11-06 that the app is closed", cases)
        breaks = section_of(self.page, "## What private access breaks")
        for lead in ("| Checking the console's access |", "| People using the console |"):
            row = [line for line in breaks.split("\n") if line.startswith(lead)][0]
            self.assertIn("#publishing-code-to-the-private-apps-phase-3-for-the-cases-app-the-console-behind-the-platforms-application-gateway-built-not-deployed", row)
        order = section_of(self.page, "## The order of the work")
        self.assertIn("The console stays public until the gateway objects exist and the owner has said yes.", order)
        not_checked = section_of(self.page, "## Not checked")
        self.assertIn("None of it has run. The section lists what is not proven", not_checked)
        self.assertIn("Read on 2026-11-06 for phase 3 of the cases app:", self.page.split("\n## Sources", 1)[1])
        self.assertIn("People open them on the app's own name, or, once the app is closed, on the console's host name on the platform's Application Gateway", text("docs/proposals/04-the-loop.md"))
        self.assertIn("That host name is the console's host name on the platform's Application Gateway when the repository variable `CONSOLE_HOST_NAME` is set, and the app's own name when it is not",
                      text("docs/proposals/05-run-as-the-approver.md"))
        readme = text("README.md")
        self.assertIn("(the cases app is to be closed and its console reached through the platform's Application Gateway: built, not deployed)", readme)
        self.assertIn("it serves the console, and the owner decided on 2026-11-06 that the people who approve reach it through the platform's Application Gateway", readme)

    def test_the_bootstrap_page_has_the_section_between_phase_2_and_the_end_and_names_the_variable_the_hand_steps_and_the_way_back(self):
        phase_2 = "## Changed on 2026-11-06: publishing code from inside the network, phase 2"
        self.assertLess(self.bootstrap.index(phase_2), self.bootstrap.index(self.BOOTSTRAP_HEADING))
        self.assertLess(self.bootstrap.index(self.BOOTSTRAP_HEADING), self.bootstrap.index("\n## After it"))
        for words in ("**Built, not deployed:** the repository holds the code, the tests and the documents. No Azure change was made, no Hub run was made, and the cases app is still public.",
                      "**One new repository variable, optional: `CONSOLE_HOST_NAME`.**", "it is never committed: it lives only in the repository's variables", "`tools/environment-params.py` refuses `CASES_APP_PUBLIC_NETWORK_ACCESS` as `Disabled` while the variable is empty. That constant stays `Enabled` in this change",
                      "**The hand steps.**", "Each object needs the owner's plain-word yes first ([rule 15 (b)](../AGENTS.md)). The steps are break-glass ([rule 18](../AGENTS.md)): the agent runs them with the owner's own Azure CLI session, "
                      "on his written word, and reports at once. The owner runs no script", "and a test keeps the two equal", "nothing of the owner's environment is written in this repository",
                      "2. Step 3: the health of the new pool must say Healthy.", "6. Only then, in a change of its own and on the owner's yes", "**Going back** is one constant and one run",
                      "`gh variable delete CONSOLE_HOST_NAME --repo <owner>/<repository>`", "**What is not proven.** None of it has run."):
            self.assertIn(words, self.bootstrap_section, words)
        self.assertIn("A fourth, optional one, `CONSOLE_HOST_NAME`, is the host name of the console on the platform's Application Gateway", self.bootstrap)
        after = self.bootstrap.split("\n## After it")[1].split("\n## ")[0]
        self.assertIn("The console behind the platform's Application Gateway is not on that list: each object on the gateway, the DNS record and the return addresses need their own plain-word yes, and it is built and not deployed", after)
        self.assertLess(after.index("One yes to the whole list"), after.index("The console behind the platform's Application Gateway is not on that list"))

    def test_the_changelog_entry_follows_the_one_of_the_ai_gateway_and_says_what_was_said_built_checked_and_left_open_and_the_older_entry_is_as_it_was(self):
        headings = re.findall(r"(?m)^## .+$", self.changelog)
        self.assertEqual(headings[6:8], [self.CHANGELOG_HEADING, self.OLDER_HEADING], "the six entries of the AI Gateway and of the undo of the API Management changes (test_aigateway_deployed.py, test_aigateway_docs.py, test_aigateway_agents_docs.py, test_aigateway_subnet_first.py) are above this one, and the entry below it is untouched")
        positions = [self.entry.index(lead) for lead in ("**What the owner said.**", "**What is built.**", "**Where Learn says something other than the plan assumed.**", "**What was checked.**", "**Not checked.**",
                                                         "**What a person has to do, in order.**")]
        self.assertEqual(positions, sorted(positions))
        for words in ("\"I don't know what the cases app is but in general, public endpoints are not allowed. You can only connect through gateways (App GW or API Mgmt). What is the cases app? [its address] THAT CAN BE PRIVATE.\"",
                      "Nothing is deployed: no Azure change, no Hub run and no workflow run was made, the cases app is still public, and the constant `CASES_APP_PUBLIC_NETWORK_ACCESS` is still `Enabled`.",
                      "**A new optional repository variable, `CONSOLE_HOST_NAME`**", "`httpSettings.forwardProxy` with the convention `Custom` and the header `X-Original-Host`", "The wait until the app answers now runs in the Operator (`op-health-<run id>`",
                      "asks with `--proxied` that the return address in the sign-in's redirect names that host", "**What is refused.**", "stops with \"NOT CHECKED\"",
                      "the agent adds them with the owner's own Azure CLI session, on his written word, and reports at once (rule 18, break-glass)", "The way back is one constant and one run."):
            self.assertIn(words, self.entry, words)
        self.assertNotIn("TESTS_CHECKED", self.entry, "the figures are filled in")
        self.assertRegex(self.entry.split("**What was checked.**")[1].split("**Not checked.**")[0], r"\d,\d{3} tests")

    def test_nothing_of_the_owners_environment_is_in_what_this_change_wrote(self):
        for label, part in (("the record", self.section), ("the bootstrap page", self.bootstrap_section), ("the changelog", self.entry)):
            self.assertNotRegex(part, r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", f"{label}: no id")
            self.assertNotRegex(part, r"func-meternaut-(cases|usage)-[0-9a-f]{8}", f"{label}: no real resource name")
            for found in re.findall(r"(\S+)\.azurewebsites\.net", part):
                self.assertTrue(found.endswith((">", "$app", "<app>")) or found.startswith(("<", "$", "`<")) or found.endswith(("<cases app name>", "<app>")), f"{label}: a real host name? {found}")
        for name in ("tools/console-check.py", "tools/environment-params.py", "tools/entra-setup.py", "environment/cases/main.bicep"):
            self.assertNotRegex(text(name), r"func-meternaut-(cases|usage)-[0-9a-f]{8}", name)


class TheWorkflowTellsTheSameStory(unittest.TestCase):
    """The variable that feeds the settings, and the summary of the workflow."""

    def test_the_variable_reaches_the_job_like_the_other_values_of_the_estate_and_is_never_written_in_the_repository(self):
        self.assertIn("      CONSOLE_HOST_NAME: ${{ vars.CONSOLE_HOST_NAME }}\n", WORKFLOW)
        job_env = re.search(r"(?ms)^    env:\n(.*?)^    steps:", WORKFLOW).group(1)
        for name in ("CONSOLE_APP_CLIENT_ID", "CONSOLE_PEOPLE", "CONSOLE_HOST_NAME", "MAIL_SENDER"):
            self.assertIn(f"      {name}: ${{{{ vars.{name} }}}}\n", job_env, name)
        self.assertNotIn("secrets.CONSOLE_HOST_NAME", WORKFLOW, "a host name is an address and no secret: it is a variable, like the client id of the app registration")
        self.assertEqual(WORKFLOW.count("CONSOLE_HOST_NAME: "), 1)

    def test_the_summary_of_a_cases_run_says_which_address_was_knocked_at_and_that_the_health_check_ran_inside_the_network(self):
        (finished,) = re.findall(r"(?m)^\s+cases\) echo \"(The first cases are in resource group.*?)\" ;;$", WORKFLOW)
        for words in ("the check that the app answers is made from inside the network too: a second container group of the Operator asked the app's own health address over its private endpoint",
                      "The console's front door is knocked at from this runner, on the console's host name on the platform's Application Gateway when the repository variable CONSOLE_HOST_NAME is set",
                      "(the check then also asks that the sign-in's return address names it), and on the app's own name when it is not"):
            self.assertIn(words, finished)
        self.assertNotIn("still made from the runner, against the public address", finished)
        (failed,) = re.findall(r"(?m)^\s+cases\) echo \"(Part of the first cases may exist now.*?)\" ;;$", WORKFLOW)
        for words in ("If they stop at the step that waits for the app to answer, the app was given its code and did not answer on `/healthz` from inside the network",
                      "If they stop at the front door, the console's address got something that it should not, or there is no address to knock at (the cases app takes no public traffic and no console host name is set)"):
            self.assertIn(words.replace("`", "\\`"), failed)


if __name__ == "__main__":
    unittest.main()
