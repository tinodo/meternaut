import base64
import importlib.util
import io
import json
import os
import re
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("recording_check", ROOT / "tools" / "recording-check.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

SITE = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-example/providers/Microsoft.Web/sites/func-example"
INSIGHTS = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-example/providers/Microsoft.Insights/components/appi-example"
NAMESPACE = "evhns-example"
OID = "99999999-8888-7777-6666-555555555555"
SECRET = "SECRET-TOKEN-VALUE"
ENV = {"GITHUB_ACTIONS": "true"}


def jwt(claims):
    def part(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
    return f"{part({'alg': 'none'})}.{part(claims)}.signature"


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def azure(runner, post=None):
    clock = Clock()
    return rc.Azure(runner=runner, post=post or (lambda *a: (500, b"{}")), sleep=clock.sleep, clock=clock)


def listed(names):
    return {"value": [{"name": f"func-example/{n}", "properties": {"name": n}} for n in names]}


def result(job, request_id, **changes):
    document = {"job": job, "requestId": request_id, "trigger": "control", "ok": True, "firstRun": False, "from": "2026-11-04T10:00:00",
                "to": "2026-11-04T13:00:00", "rows": 3, "written": 3, "containerCount": 5, "marker": "2026-11-04T13:00:00", "error": None}
    document.update(changes)
    return document


def telemetry(documents):
    rows = [["2026-11-04T13:01:00Z", rc.RESULT_PREFIX + json.dumps(d, separators=(",", ":"))] for d in documents]
    return {"tables": [{"name": "PrimaryResult", "columns": [{"name": "timestamp"}, {"name": "message"}], "rows": rows}]}


class Whoami(unittest.TestCase):
    def test_the_object_id_comes_from_the_claims_and_the_token_is_never_printed(self):
        token = jwt({"oid": OID.upper(), "x": SECRET})
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = rc.main(["whoami"], azure(lambda args: (0, token + "\n", "")))
        self.assertEqual((code, out.getvalue().strip(), err.getvalue()), (0, OID, ""))
        self.assertNotIn(SECRET, out.getvalue() + err.getvalue())

    def test_a_token_without_an_object_id_is_refused(self):
        for token in (jwt({}), jwt({"oid": "not-a-guid"}), "no-dots", jwt({"oid": 5}), "a.!!!.c"):
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                code = rc.main(["whoami"], azure(lambda args, t=token: (0, t, "")))
            self.assertEqual(code, 1, token)
            self.assertIn("no object id", err.getvalue())

    def test_a_failed_sign_in_says_so_without_the_cli_output_beyond_its_first_line(self):
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = rc.main(["whoami"], azure(lambda args: (1, "", "ERROR: please run az login\nmore lines\n")))
        self.assertEqual(code, 1)
        self.assertIn("please run az login", err.getvalue())
        self.assertNotIn("more lines", err.getvalue())


class Functions(unittest.TestCase):
    def test_it_waits_until_the_six_functions_are_listed(self):
        answers = iter([Exception, listed(rc.FUNCTIONS[:2]), listed(rc.FUNCTIONS)])
        calls = []

        def runner(args):
            calls.append(args)
            step = next(answers)
            if step is Exception:
                return 1, "", "ERROR: BadGateway"
            return 0, json.dumps(step), ""

        out = io.StringIO()
        with redirect_stdout(out):
            code = rc.main(["functions", "--site", SITE], azure(runner))
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 3)
        self.assertIn("lists 6 functions", out.getvalue())
        for name in rc.FUNCTIONS:
            self.assertIn(name, out.getvalue())
        self.assertEqual(calls[0][:6], ["rest", "--method", "get", "--url", f"https://management.azure.com{SITE}/functions?api-version=2024-04-01", "--only-show-errors"])

    def test_it_names_what_is_missing_when_it_gives_up(self):
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = rc.main(["functions", "--site", SITE, "--minutes", "1"], azure(lambda args: (0, json.dumps(listed(rc.FUNCTIONS[:4])), "")))
        self.assertEqual(code, 1)
        self.assertIn("missing: pii-usage-ingestion, usage-control", err.getvalue())

    def test_a_site_that_is_not_a_function_app_is_refused(self):
        for bad in ("", "/subscriptions/x", SITE.replace("Microsoft.Web/sites", "Microsoft.Storage/storageAccounts"), SITE + "/slots/x"):
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                self.assertEqual(rc.main(["functions", "--site", bad], azure(lambda args: (0, "[]", ""))), 1)
            self.assertIn("--site", err.getvalue())

    def test_the_six_functions_are_the_ones_the_app_and_the_template_name(self):
        app = (ROOT / "src" / "usage-functions" / "function_app.py").read_text(encoding="utf-8") if (ROOT / "src" / "usage-functions" / "function_app.py").exists() else ""
        if app:
            self.assertEqual(sorted(re.findall(r'function_name\(name="([a-z-]+)"\)', app)), sorted(rc.FUNCTIONS))
        self.assertEqual(rc.CONTROL_HUB, "usage-control")
        self.assertIn("var controlHubName = 'usage-control'", (ROOT / "environment" / "recording" / "main.bicep").read_text(encoding="utf-8"))


class SendingTheEvent(unittest.TestCase):
    def sent(self, **changes):
        posts = []

        def runner(args):
            return 0, SECRET + "\n", ""

        def post(url, headers, body):
            posts.append((url, headers, body))
            return changes.get("status", 201), changes.get("answer", b"")

        with mock.patch.dict(os.environ, ENV):
            rc.send_control_event(azure(runner, post), changes.get("namespace", NAMESPACE), "all", "a" * 32)
        return posts

    def test_one_event_goes_to_the_control_hub_with_the_workflows_token_and_the_job_and_the_request(self):
        (url, headers, body), = self.sent()
        self.assertEqual(url, f"https://{NAMESPACE}.servicebus.windows.net/usage-control/messages?timeout=60&api-version=2014-01")
        self.assertEqual(headers["Authorization"], f"Bearer {SECRET}")
        self.assertEqual(headers["Content-Type"], "application/atom+xml;type=entry;charset=utf-8", "the type that the Event Hubs REST send documents; another one is answered with 415")
        self.assertEqual(json.loads(body), {"job": "all", "requestId": "a" * 32})

    def test_the_token_is_asked_for_the_event_hubs_audience_only(self):
        asked = []

        def runner(args):
            asked.append(args)
            return 0, SECRET + "\n", ""

        rc.send_control_event(azure(runner, lambda *a: (201, b"")), NAMESPACE, "all", "b" * 32)
        self.assertEqual(asked, [["account", "get-access-token", "--resource", "https://eventhubs.azure.net", "--query", "accessToken", "--output", "tsv", "--only-show-errors"]])

    def test_a_namespace_may_be_given_with_its_host_suffix_and_a_bad_one_is_refused(self):
        self.assertEqual(rc.namespace_host(f"{NAMESPACE}.servicebus.windows.net"), f"{NAMESPACE}.servicebus.windows.net")
        for bad in ("", "x", "a b", "evh/ns", "evh.other.net"):
            with self.assertRaises(rc.Problem):
                rc.namespace_host(bad)

    def test_a_refusal_says_the_status_and_the_first_line_of_the_answer_and_never_the_token(self):
        with self.assertRaises(rc.Problem) as raised:
            self.sent(status=401, answer=b"401:Unauthorized\nsecond line")
        message = str(raised.exception)
        self.assertIn("401", message)
        self.assertIn("Unauthorized", message)
        self.assertNotIn("second line", message)
        self.assertNotIn(SECRET, message)


class Parsing(unittest.TestCase):
    def test_only_a_line_with_exactly_the_agreed_keys_is_a_result(self):
        good = rc.RESULT_PREFIX + json.dumps(result("llm-usage-ingestion", "r"))
        self.assertEqual(rc.parse_result(good)["job"], "llm-usage-ingestion")
        missing = result("llm-usage-ingestion", "r")
        del missing["containerCount"]
        for bad in (rc.RESULT_PREFIX + json.dumps(missing), rc.RESULT_PREFIX + json.dumps({**result("x", "r"), "extra": 1}), rc.RESULT_PREFIX + "not json",
                    rc.RESULT_PREFIX + "[1]", "something else", None, 5):
            self.assertIsNone(rc.parse_result(bad), bad)

    def test_the_keys_are_the_ones_the_functions_write(self):
        self.assertEqual(rc.RESULT_KEYS, {"job", "requestId", "trigger", "ok", "firstRun", "from", "to", "rows", "written", "containerCount", "marker", "error"})
        self.assertEqual(rc.RESULT_PREFIX, "usage_job_result ")

    def test_a_line_that_the_functions_write_is_read_by_the_checker(self):
        # the other side of the agreement: the function app's own writer (src/usage-functions/usage/results.py, standard library only)
        app = str(ROOT / "src" / "usage-functions")
        sys.path.insert(0, app)
        try:
            from usage import results
        finally:
            sys.path.remove(app)
        self.assertEqual(results.RESULT_PREFIX, rc.RESULT_PREFIX)
        good = results.JobResult(job="llm-usage-ingestion", request_id="r", trigger="control", ok=True, first_run=False, window_from="2026-11-04T10:00:00",
                                 window_to="2026-11-04T13:00:00", rows=3, written=3, container_count=5, marker="2026-11-04T13:00:00", error=None)
        failed = results.JobResult(job="mcp-usage-ingestion", request_id="r", trigger="control", ok=False, first_run=False, window_from=None, window_to=None,
                                   rows=0, written=0, container_count=None, marker=None, error="HttpResponseError: (Forbidden) no role")
        for written in (good, failed):
            parsed = rc.parse_result(written.to_line())
            self.assertIsNotNone(parsed, written.to_line())
            self.assertEqual(set(parsed), rc.RESULT_KEYS)
            self.assertEqual((parsed["job"], parsed["ok"], parsed["requestId"], parsed["trigger"]), (written.job, written.ok, "r", "control"))


class Run(unittest.TestCase):
    ID = "c" * 32

    def args(self, *extra):
        return ["run", "--namespace", NAMESPACE, "--insights", INSIGHTS, *extra]

    def go(self, answers, *extra, post_status=201, env=ENV):
        """Runs the check. `answers` are the answers of the telemetry, one for each query, the last one repeated."""
        asked = []
        queue = list(answers)

        def runner(args):
            if args[:2] == ["account", "get-access-token"]:
                return 0, SECRET + "\n", ""
            asked.append(args)
            answer = queue.pop(0) if len(queue) > 1 else queue[0]
            if answer is Exception:
                return 1, "", "ERROR: Forbidden\nmore"
            return 0, json.dumps(answer), ""

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(rc.uuid, "uuid4", return_value=mock.Mock(hex=self.ID)), \
                redirect_stdout(out), redirect_stderr(err):
            code = rc.main(self.args(*extra), azure(runner, lambda *a: (post_status, b"")))
        return code, out.getvalue(), err.getvalue(), asked

    def test_three_good_results_pass_and_are_printed_with_their_numbers(self):
        results = [result(job, self.ID) for job in rc.TIMED_JOBS]
        code, out, err, asked = self.go([telemetry(results)])
        self.assertEqual((code, err), (0, ""))
        for job in rc.TIMED_JOBS:
            self.assertIn(f"{job}: ok", out)
        self.assertIn("3 rows read, 3 documents written, 5 documents in the container, marker 2026-11-04T13:00:00", out)
        self.assertNotIn(SECRET, out)

    def test_the_query_is_made_for_this_request_only_and_through_the_resource_manager(self):
        _, _, _, asked = self.go([telemetry([result(job, self.ID) for job in rc.TIMED_JOBS])])
        args = asked[0]
        self.assertEqual(args[:2], ["rest", "--method"])
        self.assertEqual(args[args.index("--url") + 1], f"https://management.azure.com{INSIGHTS}/query?api-version=2018-04-20")
        query = json.loads(args[args.index("--body") + 1])["query"]
        self.assertIn(self.ID, query)
        self.assertIn("usage_job_result", query)
        self.assertRegex(query, r"^traces \| where timestamp > ago\(2h\)")

    def test_a_job_that_failed_fails_the_check_and_shows_its_error(self):
        failed = result("llm-usage-ingestion", self.ID, ok=False, containerCount=None, marker=None, error="HttpResponseError: (Forbidden) no role")
        code, out, err, _ = self.go([telemetry([failed, result("mcp-usage-ingestion", self.ID), result("agent-usage-ingestion", self.ID)])])
        self.assertEqual(code, 1)
        self.assertIn("llm-usage-ingestion: FAILED; error HttpResponseError: (Forbidden) no role", out)

    def test_a_first_run_is_said_to_have_written_only_its_marker(self):
        first = result("llm-usage-ingestion", self.ID, firstRun=True, rows=0, written=0, containerCount=0)
        code, out, _, _ = self.go([telemetry([first])], "--job", "llm-usage-ingestion")
        self.assertEqual(code, 0)
        self.assertIn("first run (marker written, nothing copied)", out)

    def test_it_waits_for_the_telemetry_and_gives_up_with_the_warnings_and_errors_of_the_app(self):
        empty = {"tables": [{"rows": []}]}
        problems = {"tables": [{"rows": [["2026-11-04T13:00:00Z", "The Python worker failed to index functions\nand a second line"]]}]}
        code, out, err, asked = self.go([empty, empty, empty, problems], "--minutes", "1")
        self.assertEqual(code, 1)
        self.assertIn("0 of 3 results arrived", out)
        self.assertIn("The last warnings and errors of the function app:", out)
        self.assertIn("The Python worker failed to index functions", out)
        self.assertNotIn("second line", out)
        self.assertGreater(len(asked), 3)

    def test_a_telemetry_that_cannot_be_read_yet_is_waited_for(self):
        good = telemetry([result("llm-usage-ingestion", self.ID)])
        code, out, err, _ = self.go([Exception, good], "--job", "llm-usage-ingestion")
        self.assertEqual(code, 0)
        self.assertIn("could not be read yet", out)

    def test_a_line_of_another_request_or_of_a_timer_is_not_this_results(self):
        other = result("llm-usage-ingestion", "d" * 32)
        timer = result("mcp-usage-ingestion", self.ID, trigger="timer")
        code, out, _, _ = self.go([telemetry([other, timer])], "--job", "llm-usage-ingestion", "--minutes", "1")
        self.assertEqual(code, 1)
        self.assertIn("0 of 1 results arrived", out)

    def test_a_refused_event_stops_before_anything_is_waited_for(self):
        code, out, err, asked = self.go([telemetry([])], post_status=403)
        self.assertEqual(code, 1)
        self.assertIn("403", err)
        self.assertEqual(asked, [])

    def test_only_a_github_actions_run_may_send_the_event(self):
        code, out, err, asked = self.go([telemetry([])], env={"GITHUB_ACTIONS": ""})
        self.assertEqual(code, 1)
        self.assertIn("only a GitHub Actions run may do that", err)
        self.assertEqual(asked, [])

    def test_bad_names_are_refused_before_anything_is_sent(self):
        for argv in (["run", "--namespace", "x", "--insights", INSIGHTS], ["run", "--namespace", NAMESPACE, "--insights", "/subscriptions/x"],
                     ["run", "--namespace", NAMESPACE, "--insights", INSIGHTS, "--job", "other"]):
            err = io.StringIO()
            sent = []
            with mock.patch.dict(os.environ, ENV), redirect_stderr(err), redirect_stdout(io.StringIO()):
                try:
                    code = rc.main(argv, azure(lambda args: (0, "{}", ""), lambda *a: sent.append(a) or (201, b"")))
                except SystemExit as stop:
                    code = stop.code
            self.assertNotEqual(code, 0, argv)
            self.assertEqual(sent, [], argv)

    def test_the_summary_file_gets_the_same_lines(self):
        good = telemetry([result(job, self.ID) for job in rc.TIMED_JOBS])
        with TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            code, out, _, _ = self.go([good], "--summary", str(summary))
            text = summary.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn("### The copy job, started once, and what it said", text)
        for line in out.splitlines():
            if "documents written" in line:
                self.assertIn(line, text)


class NothingReadsTheStore(unittest.TestCase):
    def test_the_checker_makes_no_call_to_cosmos_db_and_asks_for_no_key(self):
        source = (ROOT / "tools" / "recording-check.py").read_text(encoding="utf-8")
        code = re.sub(r'""".*?"""', "", source, flags=re.S)
        for word in ("documents.azure.com", "cosmos.azure.com", "listKeys", "listConnectionStrings", "primaryKey", "SharedAccessSignature", "AccountKey"):
            self.assertNotIn(word, code, word)
        self.assertEqual(sorted(set(re.findall(r'token\(\s*["\']([^"\']+)["\']', code)) | set(re.findall(r"token\(\s*'([^']+)'\)", code))), ["https://eventhubs.azure.net", "https://management.azure.com"])


if __name__ == "__main__":
    unittest.main()
