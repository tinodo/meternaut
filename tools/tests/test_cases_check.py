import datetime as dt
import importlib.util
import io
import json
import logging
import os
import re
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cases_check", ROOT / "tools" / "cases-check.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)
rc = cc.rc

SITE = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-example/providers/Microsoft.Web/sites/func-example"
INSIGHTS = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-example/providers/Microsoft.Insights/components/appi-example"
NAMESPACE = "evhns-example"
SECRET = "SECRET-TOKEN-VALUE"
ENV = {"GITHUB_ACTIONS": "true"}
ID = "c" * 32


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def azure(runner, post=None):
    clock = Clock()
    return cc.Azure(runner=runner, post=post or (lambda *a: (500, b"{}")), sleep=clock.sleep, clock=clock)


def listed(names):
    return {"value": [{"name": f"func-example/{n}", "properties": {"name": n}} for n in names]}


def event(kind, **fields):
    return {"v": 1, "ts": "2026-11-04T13:00:00Z", "runId": "run1", "requestId": ID, "type": kind, **fields}


def line(document):
    return cc.EVENT_PREFIX + json.dumps(document, separators=(",", ":"))


def telemetry(documents):
    rows = [["2026-11-04T13:01:00Z", line(d) if isinstance(d, dict) else d] for d in documents]
    return {"tables": [{"name": "PrimaryResult", "columns": [{"name": "timestamp"}, {"name": "message"}], "rows": rows}]}


def a_good_run(**finished):
    return [
        event("run.started", trigger="control", scopes=["sub1"], detectors=["orphan-private-endpoint"]),
        event("lead.found", leadId="l1", detector="orphan-private-endpoint", resourceId="/subscriptions/x/pe1", resourceType="microsoft.network/privateendpoints",
              resourceName="pe1", resourceGroup="rg1", costUsd30d=3.1, rank=1),
        event("lead.found", leadId="l2", detector="orphan-managed-disk", resourceId="/subscriptions/x/d1", resourceType="microsoft.compute/disks",
              resourceName="d1", resourceGroup="rg1", costUsd30d=1.5, rank=2),
        event("case.started", caseId="c1", leadId="l1"),
        event("case.step", caseId="c1", step="detective", model="gpt-6-luna", promptTokens=900, completionTokens=210, ms=3100, ok=True, note=None),
        event("case.step", caseId="c1", step="skeptic", model="gpt-6-luna", promptTokens=700, completionTokens=150, ms=2500, ok=True, note=None),
        event("case.result", caseId="c1", leadId="l1", detector="orphan-private-endpoint", resourceName="pe1", resourceType="microsoft.network/privateendpoints",
              resourceGroup="rg1", costUsd30d=3.1, status="needs_human", recommendation="delete", confidence=0.8, monthlySavingUsd=3.1,
              summary="The connection was never approved.", objections=["It may be in use by a pending request"], guards=["managed-group"]),
        event("run.finished", **{"ok": True, "leads": 2, "cases": 1, "proposed": 0, "needsHuman": 1, "dropped": 0, "errors": 0, "tokens": 1960, "seconds": 41, **finished}),
    ]


class Functions(unittest.TestCase):
    def test_it_waits_until_both_functions_are_listed(self):
        answers = iter([Exception, listed(["watch-daily"]), listed(cc.FUNCTIONS)])
        calls = []

        def runner(args):
            calls.append(args)
            step = next(answers)
            if step is Exception:
                return 1, "", "ERROR: BadGateway"
            return 0, json.dumps(step), ""

        out = io.StringIO()
        with redirect_stdout(out):
            code = cc.main(["functions", "--site", SITE], azure(runner))
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 3)
        self.assertIn("lists 2 functions", out.getvalue())
        for name in cc.FUNCTIONS:
            self.assertIn(name, out.getvalue())

    def test_it_names_what_is_missing_when_it_gives_up(self):
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = cc.main(["functions", "--site", SITE, "--minutes", "1"], azure(lambda args: (0, json.dumps(listed(["watch-daily"])), "")))
        self.assertEqual(code, 1)
        self.assertIn("missing: cases-control", err.getvalue())

    def test_a_site_that_is_not_a_function_app_is_refused(self):
        for bad in ("", "/subscriptions/x", SITE.replace("Microsoft.Web/sites", "Microsoft.Storage/storageAccounts"), SITE + "/slots/x"):
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                self.assertEqual(cc.main(["functions", "--site", bad], azure(lambda args: (0, "[]", ""))), 1)
            self.assertIn("--site", err.getvalue())

    def test_the_two_functions_and_the_hub_are_the_ones_the_app_and_the_template_name(self):
        app = ROOT / "src" / "case-functions" / "function_app.py"
        declared = re.findall(r'function_name\(name="([a-z-]+)"\)', app.read_text(encoding="utf-8"))
        self.assertEqual(sorted(declared), sorted(cc.FUNCTIONS))
        self.assertEqual(cc.CONTROL_HUB, "cases-control")
        self.assertIn("var controlHubName = 'cases-control'", (ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8"))


class SendingTheEvent(unittest.TestCase):
    def test_the_event_goes_to_the_cases_hub_and_names_one_watch(self):
        posts = []

        def post(url, headers, body):
            posts.append((url, body))
            return 201, b""

        with mock.patch.dict(os.environ, ENV):
            rc.send_control_event(azure(lambda args: (0, SECRET + "\n", ""), post), NAMESPACE, "watch", ID, hub=cc.CONTROL_HUB)
        ((url, body),) = posts
        self.assertEqual(url, f"https://{NAMESPACE}.servicebus.windows.net/cases-control/messages?timeout=60&api-version=2014-01")
        self.assertEqual(json.loads(body), {"job": "watch", "requestId": ID})

    def test_the_usage_checker_still_sends_to_its_own_hub_by_default(self):
        posts = []
        rc.send_control_event(azure(lambda args: (0, SECRET + "\n", ""), lambda url, headers, body: posts.append(url) or (201, b"")), NAMESPACE, "all", ID)
        self.assertIn("/usage-control/messages", posts[0])


class Parsing(unittest.TestCase):
    def test_only_a_line_with_the_prefix_and_a_json_object_with_a_type_is_an_event(self):
        self.assertEqual(cc.parse_event(line(event("run.started")))["type"], "run.started")
        for bad in ("meternaut_event not json", "meternaut_event [1]", cc.EVENT_PREFIX + json.dumps({"no": "type"}), cc.EVENT_PREFIX + json.dumps({"type": 5}),
                    "something else", None, 5):
            self.assertIsNone(cc.parse_event(bad), bad)

    def test_the_prefix_is_the_one_of_the_workbook_and_the_proposal(self):
        self.assertEqual(cc.EVENT_PREFIX, "meternaut_event ")
        workbook = (ROOT / "environment" / "cases" / "history.workbook.json").read_text(encoding="utf-8")
        self.assertIn("meternaut_event", workbook)
        proposal = (ROOT / "docs" / "proposals" / "02-first-cases.md").read_text(encoding="utf-8")
        self.assertIn("`meternaut_event `", proposal)
        for kind in ("run.started", "run.note", "lead.found", "case.started", "case.step", "case.result", "run.finished", "run.failed"):
            self.assertIn(f"`{kind}`", proposal, kind)

    def test_a_line_that_the_functions_write_is_read_by_the_checker(self):
        # the other side of the agreement: the cases app's own writer (src/case-functions/cases/events.py, standard library only)
        import sys
        app = str(ROOT / "src" / "case-functions")
        sys.path.insert(0, app)
        try:
            from cases import events as writer
        finally:
            sys.path.remove(app)
        self.assertEqual(writer.EVENT_PREFIX, cc.EVENT_PREFIX)
        self.assertEqual(writer.KINDS, ("run.started", "run.note", "lead.found", "case.started", "case.step", "case.result", "run.finished", "run.failed"))
        lines = []

        class Capture(logging.Handler):
            def emit(self, record):
                lines.append(record.getMessage())

        logger = logging.getLogger("meternaut.history.test")
        logger.setLevel(logging.INFO)
        logger.addHandler(Capture())
        history = writer.History("r" * 32, "a" * 32, lambda: dt.datetime(2026, 11, 4, 12, tzinfo=dt.timezone.utc), lambda text: text, logger)
        history.emit("run.finished", ok=True, leads=1, cases=1, proposed=1, needsHuman=0, dropped=0, errors=0, tokens=10, seconds=2)
        parsed = cc.parse_event(lines[0])
        self.assertEqual((parsed["type"], parsed["requestId"], parsed["tokens"]), ("run.finished", "a" * 32, 10))


class Run(unittest.TestCase):
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
        with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(cc.uuid, "uuid4", return_value=mock.Mock(hex=ID)), \
                redirect_stdout(out), redirect_stderr(err):
            code = cc.main(self.args(*extra), azure(runner, lambda *a: (post_status, b"")))
        return code, out.getvalue(), err.getvalue(), asked

    def test_a_good_run_passes_and_says_what_it_found_in_plain_words(self):
        code, out, err, _ = self.go([telemetry(a_good_run())])
        self.assertEqual((code, err), (0, ""))
        for text in ("The run ended well after 41 seconds (started by the control).",
                     "Leads 2; cases taken 1: proposed 0, needs a person 1, dropped 0, errors 0; tokens through the gateway 1960.",
                     "Leads by detector: orphan-managed-disk 1, orphan-private-endpoint 1",
                     "1. orphan-private-endpoint: pe1 (microsoft.network/privateendpoints, rg1)",
                     "status needs_human, confidence 0.8; cost of the last 30 days 3.10 USD (Cost Management cost lines, not an invoice); monthly saving if removed 3.10 USD",
                     "summary: The connection was never approved.",
                     "objections: It may be in use by a pending request",
                     "guards: managed-group",
                     "step detective gpt-6-luna: ok, 900+210 tokens, 3100 ms"):
            self.assertIn(text, out)
        self.assertNotIn(SECRET, out)

    def test_the_query_is_made_for_this_request_only_and_through_the_resource_manager(self):
        _, _, _, asked = self.go([telemetry(a_good_run())])
        args = asked[0]
        self.assertEqual(args[:2], ["rest", "--method"])
        self.assertEqual(args[args.index("--url") + 1], f"https://management.azure.com{INSIGHTS}/query?api-version=2018-04-20")
        query = json.loads(args[args.index("--body") + 1])["query"]
        self.assertIn(ID, query)
        self.assertIn("meternaut_event", query)
        self.assertRegex(query, r"^traces \| where timestamp > ago\(3h\)")

    def test_a_failed_run_fails_the_check_and_shows_its_reason(self):
        code, out, _, _ = self.go([telemetry([event("run.started", trigger="control"), event("run.failed", reason="the gateway key could not be read")])])
        self.assertEqual(code, 1)
        self.assertIn("The run failed: the gateway key could not be read", out)

    def test_a_run_that_ended_badly_or_with_an_error_fails_the_check(self):
        for changes in ({"ok": False}, {"errors": 1}):
            code, out, _, _ = self.go([telemetry(a_good_run(**changes))])
            self.assertEqual(code, 1, changes)

    def test_a_case_that_ended_in_an_error_fails_the_check_even_when_the_end_says_nothing_of_it(self):
        events = a_good_run()
        events[6]["status"] = "error"
        code, out, _, _ = self.go([telemetry(events)])
        self.assertEqual(code, 1)
        self.assertIn("status error", out)

    def test_it_waits_for_the_lines_that_the_end_counts(self):
        everything = a_good_run()
        early = [e for e in everything if e["type"] != "case.result"]
        code, out, _, asked = self.go([telemetry(early), telemetry(everything)])
        self.assertEqual(code, 0)
        self.assertEqual(len(asked), 2)
        self.assertIn("1. orphan-private-endpoint", out)

    def test_after_the_deadline_the_run_is_reported_with_what_did_not_arrive(self):
        early = [e for e in a_good_run() if e["type"] != "case.result"]
        code, out, _, _ = self.go([telemetry(early)], "--minutes", "1")
        self.assertEqual(code, 0, "the end says ok; what the telemetry lost is said, not hidden")
        self.assertIn("the telemetry has not delivered: case.result: 0 of 1", out)

    def test_it_waits_for_the_end_and_gives_up_with_the_warnings_and_errors_of_the_app(self):
        empty = {"tables": [{"rows": []}]}
        problems = {"tables": [{"rows": [["2026-11-04T13:00:00Z", "The Python worker failed to index functions\nand a second line"]]}]}
        code, out, err, asked = self.go([empty, empty, empty, problems], "--minutes", "1")
        self.assertEqual(code, 1)
        self.assertIn("no end of the run arrived in the telemetry within 1 minutes (0 lines of the run arrived)", out)
        self.assertIn("The last warnings and errors of the cases app:", out)
        self.assertIn("The Python worker failed to index functions", out)
        self.assertNotIn("second line", out)

    def test_a_telemetry_that_cannot_be_read_yet_is_waited_for(self):
        code, out, _, _ = self.go([Exception, telemetry(a_good_run())])
        self.assertEqual(code, 0)
        self.assertIn("could not be read yet", out)

    def test_a_line_of_another_request_is_not_this_runs(self):
        other = [{**e, "requestId": "d" * 32} for e in a_good_run()]
        code, out, _, _ = self.go([telemetry(other)], "--minutes", "1")
        self.assertEqual(code, 1)
        self.assertIn("0 lines of the run arrived", out)

    def test_lines_that_are_not_events_are_ignored(self):
        noise = ["meternaut_event not json", "usage_job_result {}", cc.EVENT_PREFIX + json.dumps({"type": 5})]
        code, out, _, _ = self.go([telemetry([*noise, *a_good_run()])])
        self.assertEqual(code, 0)

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
        for argv in (["run", "--namespace", "x", "--insights", INSIGHTS], ["run", "--namespace", NAMESPACE, "--insights", "/subscriptions/x"]):
            sent = []
            with mock.patch.dict(os.environ, ENV), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                code = cc.main(argv, azure(lambda args: (0, "{}", ""), lambda *a: sent.append(a) or (201, b"")))
            self.assertNotEqual(code, 0, argv)
            self.assertEqual(sent, [], argv)

    def test_the_summary_file_gets_the_same_lines(self):
        with TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            code, out, _, _ = self.go([telemetry(a_good_run())], "--summary", str(summary))
            text = summary.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn(cc.SECTION_TITLE, text)
        for printed in out.splitlines():
            if "tokens through the gateway" in printed:
                self.assertIn(printed, text)

    def test_text_from_the_estate_cannot_start_a_runner_command_or_break_out_of_the_code_block(self):
        events = a_good_run()
        events[6]["resourceName"] = "pe1\n::add-mask::secret\n```\n## injected"
        events[6]["summary"] = "line one\n::error::fake\r\n##[group]x `tick`"
        code, out, _, _ = self.go([telemetry(events)])
        self.assertEqual(code, 0)
        for printed in out.splitlines():
            self.assertFalse(printed.lstrip().startswith("::"), printed)
            self.assertNotIn("##[", printed)
            self.assertNotIn("```", printed)
        self.assertIn("pe1 ::add-mask::secret".replace("::", ": :"), out)

    def test_long_text_is_cut_and_control_characters_are_dropped(self):
        events = a_good_run()
        events[6]["summary"] = "x" * 5000 + "\x00\x1b[31m"
        _, out, _, _ = self.go([telemetry(events)])
        summary = next(printed for printed in out.splitlines() if printed.strip().startswith("summary:"))
        self.assertLessEqual(len(summary), 700)
        self.assertTrue(summary.endswith("..."))
        self.assertNotIn("\x1b", out)


class Clean(unittest.TestCase):
    def test_what_clean_does(self):
        self.assertEqual(cc.clean(None), "")
        self.assertEqual(cc.clean("a\n\n b\t c"), "a b c")
        self.assertEqual(cc.clean("::error::x"), ": :error: :x")
        self.assertEqual(cc.clean("`a`"), "'a'")
        self.assertEqual(cc.clean("x" * 10, 5), "xx...")


class TheCheckerAsksForNoKeyAndCallsNothingElse(unittest.TestCase):
    def test_no_call_to_the_estate_and_no_key(self):
        source = (ROOT / "tools" / "cases-check.py").read_text(encoding="utf-8")
        code = re.sub(r'""".*?"""', "", source, flags=re.S)
        for word in ("listKeys", "listSecrets", "primaryKey", "SharedAccessSignature", "AccountKey", "api-key", "az login"):
            self.assertNotIn(word, code, word)
        self.assertNotRegex(code, r"https://[a-z0-9.-]+\.(azure-api|documents\.azure|blob\.core\.windows)\.", "it reads only the telemetry and sends one event")


if __name__ == "__main__":
    unittest.main()
