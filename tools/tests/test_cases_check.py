import base64
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
ACCOUNT = "stexample"
SECRET = "SECRET-TOKEN-VALUE"
DATA_TOKEN = "DATA-PLANE-TOKEN-VALUE"
APP_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
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


def an_investigation(**finished):
    """The lines that the investigation writes (cases/investigate.py), without the cases that it opens."""
    return [
        event("investigation.started", investigator="meternaut-investigator:3", skeptic="meternaut-skeptic:2", modelInvestigator="gpt-6.1-sol", modelSkeptic="gpt-6-luna",
              maxCalls=24, maxSeconds=420),
        event("investigation.finding", finding=1, basis="idle", proposal="delete", confidence=0.85, claimed=3, handles=2, unknown=0, unproven=1, repeated=0, judgedLately=0,
              guarded=0, capped=0, coveredCostUsd30d=12.4, verdict="agree", kept=True, reason=None, summary="Two of them carried no traffic in 30 days."),
        event("investigation.finding", finding=2, basis="oversized", proposal="change", confidence=0.4, claimed=1, handles=0, unknown=1, unproven=0, repeated=0,
              judgedLately=0, guarded=0, capped=0, coveredCostUsd30d=None, verdict=None, kept=False, reason="no handle was proven", summary="Looks too big."),
        event("investigation.finished", **{"ok": True, "toolCalls": 14, "tokens": 52100, "seconds": 190, "examined": ["cost by service", "private endpoints"],
                                           "findingsKept": 1, "findingsDropped": 1, "cases": 2, "guarded": 0, **finished}),
    ]


class Functions(unittest.TestCase):
    def test_it_waits_until_all_the_functions_are_listed(self):
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
        self.assertEqual(len(cc.FUNCTIONS), 7, "seven since the cards close: the flow's message about a posted card has a function of its own")
        self.assertIn(f"lists {len(cc.FUNCTIONS)} functions", out.getvalue())
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

    def test_the_functions_and_the_queue_are_the_ones_the_app_and_the_template_name(self):
        app = ROOT / "src" / "case-functions" / "function_app.py"
        declared = re.findall(r'function_name\(name="([a-z-]+)"\)', app.read_text(encoding="utf-8"))
        self.assertEqual(sorted(declared), sorted(cc.FUNCTIONS))
        self.assertEqual(cc.CONTROL_QUEUE, "cases-control")
        self.assertIn("var controlQueueName = 'cases-control'", (ROOT / "environment" / "cases" / "main.bicep").read_text(encoding="utf-8"))
        self.assertIn("var casesControlQueueName = 'cases-control'", (ROOT / "environment" / "operator" / "main.bicep").read_text(encoding="utf-8"))


class PuttingTheMessage(unittest.TestCase):
    def test_the_message_goes_to_the_cases_queue_and_names_one_watch(self):
        posts = []

        def post(url, headers, body):
            posts.append((url, body))
            return 201, b""

        with mock.patch.dict(os.environ, ENV):
            rc.send_control_message(azure(lambda args: (0, SECRET + "\n", ""), post), ACCOUNT, "watch", ID, queue=cc.CONTROL_QUEUE)
        ((url, body),) = posts
        self.assertEqual(url, f"https://{ACCOUNT}.queue.core.windows.net/cases-control/messages?messagettl=3600&timeout=30")
        text = re.search(rb"<MessageText>([^<]+)</MessageText>", body).group(1)
        self.assertEqual(json.loads(base64.b64decode(text, validate=True)), {"job": "watch", "requestId": ID})

    def test_the_helper_has_no_default_queue_so_that_a_check_puts_a_message_only_in_the_queue_that_it_names(self):
        with self.assertRaises(TypeError):
            rc.send_control_message(azure(lambda args: (0, SECRET + "\n", ""), lambda url, headers, body: (201, b"")), ACCOUNT, "watch", ID)


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

    def test_the_lines_and_the_reasons_of_the_investigation_are_the_ones_the_app_writes_and_the_record_lists(self):
        import sys
        app = str(ROOT / "src" / "case-functions")
        sys.path.insert(0, app)
        try:
            from cases import events as writer
        finally:
            sys.path.remove(app)
        self.assertEqual(writer.INVESTIGATION_KINDS, ("investigation.started", "investigation.beat", "investigation.call", "investigation.finding", "investigation.finished"))
        record = (ROOT / "docs" / "proposals" / "06-foundry-agents.md").read_text(encoding="utf-8")
        source = (ROOT / "src" / "case-functions" / "cases" / "investigate.py").read_text(encoding="utf-8")
        beats_source = (ROOT / "src" / "case-functions" / "cases" / "beats.py").read_text(encoding="utf-8")
        run = (ROOT / "src" / "case-functions" / "cases" / "run.py").read_text(encoding="utf-8")
        for kind in writer.INVESTIGATION_KINDS:
            self.assertIn(f"`{kind}`", record, kind)
        row = next(line for line in record.splitlines() if line.startswith("| `investigation.call` |"))
        for name in ("beat", "n", "by", "tool", "resourceType", "handles", "metrics", "ok", "error", "chars", "seconds"):
            self.assertIn(f"`{name}`", row, name)
            self.assertTrue(f"{name}=" in source or f'"{name}"' in beats_source, name)
        for name in ("investigator", "skeptic", "modelInvestigator", "modelSkeptic", "maxCalls", "maxSeconds", "toolCalls", "findingsKept", "findingsDropped", "examined",
                     "finding", "basis", "proposal", "confidence", "claimed", "handles", "unknown", "unproven", "unmeasured", "shown", "repeated", "judgedLately", "guarded",
                     "capped", "coveredCostUsd30d", "verdict", "kept", "reason", "summary", "cases", "note"):
            self.assertIn(f"{name}=", source, name)
            self.assertIn(f"`{name}`", record, name)
        for reason in cc.BENIGN_NOT_RUN:
            self.assertIn(f'True, "{reason}"', source)
        self.assertIn('say(f"' + cc.NOT_RUN + '{investigation.note}")', run)


class Run(unittest.TestCase):
    def args(self, *extra):
        return ["run", "--storage-account", ACCOUNT, "--insights", INSIGHTS, *extra]

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
                     "Leads 2; cases taken 1: proposed 0, needs a person 1, dropped 0, errors 0; tokens of the Detective and the Skeptic 1960.",
                     "Leads by detector: orphan-managed-disk 1, orphan-private-endpoint 1",
                     "1. orphan-private-endpoint: pe1 (microsoft.network/privateendpoints, rg1)",
                     "status needs_human, confidence 0.8; cost of the last 30 days 3.10 USD (Cost Management cost lines, not an invoice); monthly saving if removed 3.10 USD",
                     "summary: The connection was never approved.",
                     "objections: It may be in use by a pending request",
                     "guards: managed-group",
                     "step detective gpt-6-luna: ok, 900+210 tokens, 3100 ms"):
            self.assertIn(text, out)
        self.assertNotIn(SECRET, out)

    def test_the_investigation_is_told_in_plain_words(self):
        events = a_good_run()
        events[-1:-1] = an_investigation()
        code, out, err, _ = self.go([telemetry(events)])
        self.assertEqual((code, err), (0, ""))
        for text in ("Investigation (two agents in Foundry, with read-only tools):",
                     "The Investigator ran on gpt-6.1-sol and the Skeptic on gpt-6-luna; the budget was 24 tool calls and 420 seconds.",
                     "It ended well after 190 seconds: 14 tool calls and 52100 tokens through Foundry; findings kept 1, dropped 1; cases opened 2, "
                     "resources held back by a guard 0.",
                     "What it says it examined: cost by service; private endpoints",
                     "Finding 1: idle, proposal delete, confidence 0.85; 3 resources claimed, 2 left after the checks of code",
                     "their cost of the last 30 days 12.40 USD (Cost Management cost lines, not an invoice); the Skeptic: agree; kept",
                     "Two of them carried no traffic in 30 days.",
                     "Finding 2: oversized, proposal change, confidence 0.4;",
                     "their cost of the last 30 days unknown (Cost Management cost lines, not an invoice); the Skeptic: no verdict; dropped: no handle was proven"):
            self.assertIn(text, out)
        self.assertLess(out.index("Leads by detector"), out.index("Investigation (two agents"))
        self.assertLess(out.index("Investigation (two agents"), out.index("Cases:"))

    def test_a_run_without_an_investigation_says_nothing_of_one(self):
        _, out, _, _ = self.go([telemetry(a_good_run())])
        self.assertNotIn("Investigation", out)

    def test_the_summary_says_how_many_subscriptions_the_watch_read_and_where_its_list_came_from(self):
        for scope_from, words in (("estate", "(every subscription that the app's identity can read)"), ("setting", "(the subscriptions of the app's setting)"),
                                  ("setting-fallback", "because the list that its identity can read could not be had")):
            events = a_good_run()
            events[0] = event("run.started", trigger="control", subscriptions=23, scopes=["11111111", "22222222", "33333333", "44444444", "55555555"], scopeFrom=scope_from,
                              detectors=["orphan-private-endpoint"])
            code, out, err, _ = self.go([telemetry(events)])
            self.assertEqual((code, err), (0, ""))
            self.assertIn(f"The Watch read 23 subscriptions {words}" if scope_from != "setting-fallback" else words, out, scope_from)
            self.assertIn("; the first: 11111111, 22222222, 33333333, 44444444, 55555555.", out)
        events = a_good_run()
        events[0] = event("run.started", trigger="timer", subscriptions=1, scopes=["11111111"], scopeFrom="estate", detectors=[])
        self.assertIn("The Watch read 1 subscription (every subscription that the app's identity can read); the first: 11111111.", self.go([telemetry(events)])[1])

    def test_a_run_whose_started_line_has_no_count_gets_no_line_about_subscriptions_and_a_bad_count_is_not_trusted(self):
        _, out, _, _ = self.go([telemetry(a_good_run())])
        self.assertNotIn("The Watch read", out, "an older app wrote scopes and no count")
        for bad in (True, "23", None, 2.5, [1]):
            events = a_good_run()
            events[0] = event("run.started", trigger="control", subscriptions=bad, scopes=["sub1"], detectors=[])
            self.assertNotIn("The Watch read", self.go([telemetry(events)])[1], repr(bad))

    def test_text_in_the_started_line_cannot_start_a_command_or_run_long(self):
        events = a_good_run()
        events[0] = event("run.started", trigger="control", subscriptions=2, scopes=["::error::x `rm`", "\nline"], scopeFrom="::set-output::", detectors=[])
        out = self.go([telemetry(events)])[1]
        self.assertNotIn("::error::", out)
        self.assertNotIn("`", out)

    def test_findings_are_listed_in_their_own_order_and_an_end_that_did_not_arrive_is_said(self):
        events = a_good_run()
        started, first, second, _ = an_investigation()
        events[-1:-1] = [started, second, first]
        code, out, _, _ = self.go([telemetry(events)])
        self.assertEqual(code, 0, "an end that has not arrived is said, and the run's own end decides")
        self.assertIn("The end of the investigation did not arrive.", out)
        self.assertLess(out.index("Finding 1:"), out.index("Finding 2:"))

    def test_an_investigation_that_ended_badly_fails_the_check_and_says_why(self):
        events = a_good_run()
        events[-1:-1] = an_investigation(ok=False, note="the investigator gave no answer (Foundry response failed: HTTP 403)")
        code, out, _, _ = self.go([telemetry(events)])
        self.assertEqual(code, 1)
        self.assertIn("It ended badly", out)
        self.assertIn("Why: the investigator gave no answer (Foundry response failed: HTTP 403)", out)

    def test_an_investigation_that_did_not_run_fails_the_check_unless_it_was_switched_off_or_had_no_project(self):
        for reason, expected in (("the agents could not be made ready (Foundry create agent failed: HTTP 403)", 1), ("it is switched off", 0),
                                 ("no Foundry endpoint is set", 0)):
            events = a_good_run()
            events.insert(-1, event("run.note", note=cc.NOT_RUN + reason))
            code, out, _, _ = self.go([telemetry(events)])
            self.assertEqual(code, expected, reason)
            self.assertIn("Note: " + cc.NOT_RUN + reason, out)

    def test_text_of_an_agent_cannot_start_a_runner_command_or_break_out_of_the_code_block(self):
        events = a_good_run()
        events[-1:-1] = an_investigation(note="x", examined=["a\n::add-mask::secret\n```\n## injected"])
        events[-1:-1] = [event("investigation.finding", finding=3, basis="idle", summary="line one\n::error::fake\r\n##[group]x `tick`", kept=True)]
        code, out, _, _ = self.go([telemetry(events)])
        self.assertEqual(code, 0)
        for printed in out.splitlines():
            self.assertFalse(printed.lstrip().startswith("::"), printed)
            self.assertNotIn("##[", printed)
            self.assertNotIn("```", printed)
        self.assertIn("Finding 3: idle", out)

    def test_the_investigation_state_of_the_end_decides_without_its_lines(self):
        for state, expected, text in (("ran", 0, "The investigation ran."), ("failed", 1, "The investigation was meant to run and did not, or it ended badly."),
                                      ("off", 0, "The investigation did not run: it is switched off or the app has no Foundry project.")):
            code, out, _, _ = self.go([telemetry(a_good_run(investigation=state, investigationLines=0))])
            self.assertEqual(code, expected, state)
            self.assertIn(text, out)

    def test_it_waits_for_the_investigation_lines_that_the_end_counts(self):
        everything = a_good_run(investigation="ran", investigationLines=4)
        everything[-1:-1] = an_investigation()
        early = [e for e in everything if e["type"] != "investigation.finished"]
        code, out, _, asked = self.go([telemetry(early), telemetry(everything)])
        self.assertEqual((code, len(asked)), (0, 2))
        self.assertIn("It ended well after 190 seconds", out)

    def test_after_the_deadline_the_investigation_lines_that_did_not_arrive_are_said(self):
        everything = a_good_run(investigation="ran", investigationLines=4)
        everything[-1:-1] = an_investigation()
        early = [e for e in everything if e["type"] != "investigation.finished"]
        code, out, _, _ = self.go([telemetry(early)], "--minutes", "1")
        self.assertEqual(code, 0)
        self.assertIn("the telemetry has not delivered: investigation lines: 3 of 4", out)

    def test_the_text_of_the_end_of_the_run_is_the_one_the_app_writes(self):
        run = (ROOT / "src" / "case-functions" / "cases" / "run.py").read_text(encoding="utf-8")
        self.assertIn("investigation=investigation.state", run)
        self.assertIn('investigationLines=h.lines("investigation.")', run)

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
        noise = ["meternaut_event not json", "another_line_of_the_log {}", cc.EVENT_PREFIX + json.dumps({"type": 5})]
        code, out, _, _ = self.go([telemetry([*noise, *a_good_run()])])
        self.assertEqual(code, 0)

    def test_a_refused_message_stops_before_anything_is_waited_for(self):
        code, out, err, asked = self.go([telemetry([])], post_status=403)
        self.assertEqual(code, 1)
        self.assertIn("403", err)
        self.assertEqual(asked, [])

    def test_only_a_github_actions_run_may_put_the_message_in_the_queue(self):
        code, out, err, asked = self.go([telemetry([])], env={"GITHUB_ACTIONS": ""})
        self.assertEqual(code, 1)
        self.assertIn("only a GitHub Actions run may do that", err)
        self.assertEqual(asked, [])

    def test_bad_names_are_refused_before_anything_is_sent(self):
        for argv in (["run", "--storage-account", "x", "--insights", INSIGHTS], ["run", "--storage-account", ACCOUNT, "--insights", "/subscriptions/x"],
                     ["run", "--storage-account", "st-example", "--insights", INSIGHTS]):
            sent = []
            with mock.patch.dict(os.environ, ENV), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                code = cc.main(argv, azure(lambda args: (0, "{}", ""), lambda *a: sent.append(a) or (201, b"")))
            self.assertNotEqual(code, 0, argv)
            self.assertEqual(sent, [], argv)

    def test_the_old_argument_is_gone(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cc.main(["run", "--namespace", "evhns-example", "--insights", INSIGHTS], azure(lambda args: (0, "{}", "")))

    def test_the_summary_file_gets_the_same_lines(self):
        with TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            code, out, _, _ = self.go([telemetry(a_good_run())], "--summary", str(summary))
            text = summary.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn(cc.SECTION_TITLE, text)
        for printed in out.splitlines():
            if "tokens of the Detective and the Skeptic" in printed:
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

    def a_run_that_names_the_estate(self):
        events = a_good_run()
        events[0] = event("run.started", trigger="control", subscriptions=23, scopes=["11111111", "22222222"], scopeFrom="estate", detectors=["orphan-private-endpoint"])
        events.insert(1, event("run.note", note="subscription 99999999-aaaa-bbbb-cccc-dddddddddddd could not be read"))
        events[-1:-1] = an_investigation(note="the Skeptic wrote about rg1 and the disk d1")
        return events

    def test_counts_only_prints_the_numbers_and_the_statuses_and_no_name_text_or_subscription_of_the_estate(self):
        code, out, err, _ = self.go([telemetry(self.a_run_that_names_the_estate())], "--counts-only")
        self.assertEqual((code, err), (0, ""))
        for text in ("The Watch read 23 subscriptions (every subscription that the app's identity can read).",
                     "The run ended well after 41 seconds (started by the control).",
                     "Leads 2; cases taken 1: proposed 0, needs a person 1, dropped 0, errors 0; tokens of the Detective and the Skeptic 1960.",
                     "Notes of the run: 1, not shown in a public log; they are in the History, in the app's telemetry.",
                     "Leads by detector: orphan-managed-disk 1, orphan-private-endpoint 1",
                     "It ended well after 190 seconds: 14 tool calls and 52100 tokens through Foundry; findings kept 1, dropped 1; cases opened 2, resources held back by a guard 0.",
                     "Why: not shown in a public log; it is in the History, in the app's telemetry.",
                     "Finding 1: proposal delete, confidence 0.85; 3 resources claimed, 2 left after the checks of code",
                     "their cost of the last 30 days 12.40 USD (Cost Management cost lines, not an invoice); the Skeptic: agree; kept",
                     "Finding 2: proposal change, confidence 0.4;", "the Skeptic: no verdict; dropped",
                     "1. orphan-private-endpoint: microsoft.network/privateendpoints",
                     "status needs_human, confidence 0.8; cost of the last 30 days 3.10 USD (Cost Management cost lines, not an invoice); monthly saving if removed 3.10 USD",
                     "step detective gpt-6-luna: ok, 900+210 tokens, 3100 ms"):
            self.assertIn(text, out)
        for text in ("pe1", "rg1", "11111111", "22222222", "99999999-aaaa", "The connection was never approved.", "It may be in use", "managed-group", "Two of them carried no traffic",
                     "Looks too big", "cost by service", "private endpoints", "no handle was proven", "the Skeptic wrote", "What it says it examined", "Note:", "summary:", "objections:", "guards:"):
            self.assertNotIn(text, out, text)

    def test_counts_only_does_not_show_why_a_run_failed_or_what_the_app_warned_about(self):
        code, out, _, _ = self.go([telemetry([event("run.started", trigger="control"), event("run.failed", reason="the disk d1 of rg1 could not be read")])], "--counts-only")
        self.assertEqual(code, 1)
        self.assertIn("The run failed. Why: not shown in a public log; it is in the History, in the app's telemetry.", out)
        self.assertNotIn("d1", out)
        empty = {"tables": [{"rows": []}]}
        warned = {"tables": [{"rows": [["2026-11-04T13:00:00Z", "The disk d1 of rg1 could not be read"]]}]}
        code, out, _, asked = self.go([empty, empty, empty, warned], "--counts-only", "--minutes", "1")
        self.assertEqual(code, 1)
        self.assertIn("no end of the run arrived in the telemetry within 1 minutes (0 lines of the run arrived)", out)
        self.assertIn("The last warnings and errors of the cases app are not shown in a public log", out)
        self.assertNotIn("d1", out)
        self.assertEqual(len(asked), 3, "the warnings are not even asked for")

    def test_counts_only_does_not_print_what_azure_said_while_the_telemetry_could_not_be_read(self):
        code, out, _, _ = self.go([Exception, telemetry(a_good_run())], "--counts-only")
        self.assertEqual(code, 0)
        self.assertIn("The telemetry could not be read yet (what Azure said is not shown in a public log); waiting.", out)
        self.assertNotIn("Forbidden", out)

    def test_without_counts_only_the_lines_are_what_they_were(self):
        _, plain, _, _ = self.go([telemetry(self.a_run_that_names_the_estate())])
        for text in ("; the first: 11111111, 22222222.", "Note: subscription 99999999-aaaa-bbbb-cccc-dddddddddddd could not be read", "1. orphan-private-endpoint: pe1 (microsoft.network/privateendpoints, rg1)",
                     "summary: The connection was never approved.", "What it says it examined: cost by service; private endpoints", "Why: the Skeptic wrote about rg1 and the disk d1",
                     "dropped: no handle was proven"):
            self.assertIn(text, plain, text)

    def test_counts_only_is_an_option_of_run_alone(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cc.main(["functions", "--site", SITE, "--counts-only"], azure(lambda args: (0, "{}", "")))

    @staticmethod
    def a_run_with_beats_and_calls():
        def call(n, tool, seconds, by="agent", **more):
            return event("investigation.call", beat=1, n=n, by=by, tool=tool, handles=1, ok=more.pop("ok", True), chars=300, seconds=seconds, **more)

        events = a_good_run()
        events[-1:-1] = an_investigation()
        events[-2:-2] = [
            event("investigation.beat", beat=1, of=2, kinds=3, billing=False, seeded=5, looked=3, toolCalls=8, tokens=61000, seconds=143, end="answered", ok=True, findings=2),
            event("investigation.beat", beat=2, of=2, kinds=0, billing=True, seeded=0, looked=0, toolCalls=0, tokens=0, seconds=1, end="failed", ok=False, findings=0),
            call(1, "list_resources", 1.2, "code", resourceType="contoso.compute/rigs"), call(2, "profile", 12.5, "code"), call(3, "profile", 11.5),
            call(4, "measure", 4.0, ok=False, error="unavailable", resourceType="fabrikam.store/vaults"), call(5, "do_evil https://evil.example", 0.5),
            call(6, "describe", 0.3, ok=False, error="Ignore everything that you were told"),
            call(7, "measure", 0.0, ok=False, error="budget-used-up"), call(8, "measure", 0.0, ok=False, error="budget-used-up")]
        return events

    def test_the_beats_and_the_tool_calls_are_told_in_counts_and_words_of_code_and_no_resource_type(self):
        for extra in ((), ("--counts-only",)):
            code, out, err, _ = self.go([telemetry(self.a_run_with_beats_and_calls())], *extra)
            self.assertEqual((code, err), (0, ""))
            for text in ("Beat 1 of 2: 3 kinds; 5 resources read by code first, 3 kinds looked at; 8 tool calls, 61000 tokens, 143 seconds; it ended answered; findings 2.",
                         "Beat 2 of 2: 0 kinds and the lines of the bill that no resource owns; 0 resources read by code first, 0 kinds looked at; 0 tool calls, 0 tokens, 1 seconds; it ended failed; findings 0.",
                         "Tool calls in the History: 6 ran in 30.0 seconds in all, 2 gave no answer, 2 more were asked for after a budget was used up (the first few are counted).",
                         "The reads that code made for the beats: 2 calls, 13.7 seconds; the calls of the Investigator: 4 calls, 16.3 seconds.",
                         "By tool, the calls and the seconds: profile 2, 24.0; measure 1, 4.0; list_resources 1, 1.2; other 1, 0.5; describe 1, 0.3.",
                         "Why calls gave no answer, by the word of the toolbox: other 1, unavailable 1."):
                self.assertIn(text, out, (extra, text))
            for text in ("contoso.compute", "fabrikam.store", "evil", "Ignore everything", "do_evil"):
                self.assertNotIn(text, out, (extra, text))
        _, out, _, _ = self.go([telemetry([*a_good_run()[:-1], *an_investigation(), a_good_run()[-1]])])
        self.assertNotIn("Tool calls in the History", out, "a run that wrote no line of a call says nothing of calls")
        self.assertNotIn("Beat 1", out)

    def test_a_beat_that_was_asked_once_more_for_its_answer_and_the_pictures_that_were_kept_are_told_in_counts(self):
        events = self.a_run_with_beats_and_calls()
        events[-2:-2] = [event("investigation.beat", beat=3, of=3, kinds=1, billing=False, seeded=2, looked=1, toolCalls=3, tokens=90000, seconds=170, end="time", ok=True, findings=1, salvaged=True),
                         event("investigation.call", beat=3, n=1, by="agent", tool="profile", handles=1, ok=True, chars=300, seconds=0.0, savedSeconds=18.4)]
        _, out, _, _ = self.go([telemetry(events)], "--counts-only")
        self.assertIn("it ended time and gave its answer when it was asked once more; findings 1.", out)
        self.assertIn("it ended answered; findings 2.", out, "the beats that were not cut off say what they said")
        self.assertIn("Pictures that were kept and answered again with no read: 1 calls, 18.4 seconds that their reads took and that were not spent again.", out)

    def test_the_claims_that_were_not_confirmed_are_added_up_by_reason_and_the_resources_that_were_too_small_are_counted(self):
        events = a_good_run()
        events[-1:-1] = [*an_investigation(), event("investigation.finding", finding=1, kept=False, noEntry=2, notMeasured=1, metricUnknown=0, totalDiffers=1, showsUse=1, tooBrief=0, tooSmall=0),
                         event("investigation.finding", finding=2, kept=True, noEntry=1, notMeasured=0, metricUnknown=2, totalDiffers=0, showsUse=0, tooBrief=3, tooSmall=4)]
        for extra in ((), ("--counts-only",)):
            _, out, _, _ = self.go([telemetry(events)], *extra)
            self.assertIn("Claims of the findings, over all of them: 3 listed with no measurement cited; 1 cited for a resource that no tool measured; 2 cited for a metric that no tool returned "
                          "for the resource; 1 cited with a total that none of the tools' totals equals; 1 cited with a total that shows use, against a claim of no usage; "
                          "3 cited with a measurement of too few days to prove no usage; 4 too small to open a case.", out, extra)
        _, out, _, _ = self.go([telemetry([*a_good_run()[:-1], *an_investigation(), a_good_run()[-1]])])
        self.assertNotIn("Claims of the findings", out, "findings that carry no counts say nothing of why")

    def test_the_totals_that_no_tool_equals_are_added_up_by_what_the_cited_number_is_in_counts_only(self):
        events = a_good_run()
        events[-1:-1] = [*an_investigation(), event("investigation.finding", finding=1, kept=False, totalDiffers=4, diffNone=1, diffNear=0, diffStat=2, diffZero=1, diffFar=0),
                         event("investigation.finding", finding=2, kept=True, totalDiffers=6, diffNone=0, diffNear=1, diffStat=0, diffZero=2, diffFar=3)]
        for extra in ((), ("--counts-only",)):
            _, out, _, _ = self.go([telemetry(events)], *extra)
            self.assertIn("Cited totals that none of the tools' totals equals, by what the number is: 1 not a number; 1 within 5 percent of a total; 2 the maximum, the average or the days "
                          "with data; 3 a zero; 3 another number.", out, extra)
        _, out, _, _ = self.go([telemetry([*a_good_run()[:-1], *an_investigation(), a_good_run()[-1]])])
        self.assertNotIn("Cited totals that none", out, "findings that carry no counts say nothing of them")

    def test_the_tools_that_are_named_are_the_first_twelve_by_their_seconds_and_the_others_are_counted(self):
        events = a_good_run()
        events[-1:-1] = [*an_investigation(), *[event("investigation.call", beat=1, n=n, by="agent", tool=f"tool_{chr(97 + n)}", handles=0, ok=True, chars=2, seconds=float(n)) for n in range(15)]]
        _, out, _, _ = self.go([telemetry(events)], "--counts-only")
        named = next(printed for printed in out.splitlines() if printed.strip().startswith("By tool"))
        self.assertEqual((named.count(","), named.count(";")), (13, 12), named)
        self.assertTrue(named.startswith("  By tool, the calls and the seconds: tool_o 1, 14.0; tool_n 1, 13.0;"), named)
        self.assertTrue(named.endswith("; 3 more tools."), named)

def component(**properties):
    """What Resource Manager says of a component. It holds more than the checker may keep: the instrumentation key and the connection string must reach no line."""
    return {"id": INSIGHTS, "name": "appi-example", "type": "Microsoft.Insights/components",
            "properties": {"AppId": APP_ID, "InstrumentationKey": "KEY-THAT-MUST-NOT-BE-PRINTED", "ConnectionString": "InstrumentationKey=KEY-THAT-MUST-NOT-BE-PRINTED", **properties}}


DEFAULT_COMPONENT = object()


class ReadingThroughTheDataPlane(unittest.TestCase):
    """--query-via: the History is read from the data plane of Application Insights, which keeps working when the component is private (docs/proposals/07-private-by-default.md)."""

    def go(self, answers, *extra, via="data-plane", arm=None, component_answer=DEFAULT_COMPONENT):
        """Runs the check. `answers` are what the data plane says to each query, in order, the last one repeated: a document, a (status, body) pair or an exception to raise.
        `arm` is what Resource Manager says to a query through its proxy. `calls` says what was asked, and in which order."""
        calls = {"order": [], "tokens": [], "components": [], "arm": [], "queries": [], "messages": []}
        queue = list(answers)

        def runner(args):
            if args[:2] == ["account", "get-access-token"]:
                resource = args[args.index("--resource") + 1]
                calls["tokens"].append(resource)
                return 0, (DATA_TOKEN if resource == rc.DATA_PLANE else SECRET) + "\n", ""
            url = args[args.index("--url") + 1]
            if "/query?" in url:
                calls["arm"].append(args)
                return 0, json.dumps(arm if arm is not None else telemetry([])), ""
            calls["order"].append("component")
            calls["components"].append(args)
            document = component() if component_answer is DEFAULT_COMPONENT else component_answer
            return 0, json.dumps(document), ""

        def post(url, headers, body):
            if ".queue.core.windows.net" in url:
                calls["order"].append("message")
                calls["messages"].append((url, headers, body))
                return 201, b""
            calls["order"].append("query")
            calls["queries"].append((url, headers, body))
            answer = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(answer, BaseException):
                raise answer
            status, document = answer if isinstance(answer, tuple) else (200, answer)
            return status, document if isinstance(document, bytes) else json.dumps(document).encode("utf-8")

        argv = ["run", "--storage-account", ACCOUNT, "--insights", INSIGHTS, *([] if via is None else ["--query-via", via]), *extra]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, ENV, clear=False), mock.patch.object(cc.uuid, "uuid4", return_value=mock.Mock(hex=ID)), \
                redirect_stdout(out), redirect_stderr(err):
            code = cc.main(argv, azure(runner, post))
        return code, out.getvalue(), err.getvalue(), calls

    def test_the_history_is_the_same_through_the_data_plane_as_through_resource_manager(self):
        events = a_good_run()
        events[-1:-1] = an_investigation()
        code_arm, through_arm, err_arm, _ = self.go([], via=None, arm=telemetry(events))
        code, through_data_plane, err, calls = self.go([telemetry(events)])
        self.assertEqual((code_arm, err_arm, code, err), (0, "", 0, ""))
        first, *rest = through_data_plane.splitlines()
        self.assertIn("The telemetry is read through the data plane of Application Insights", first)
        self.assertEqual(rest, through_arm.splitlines())
        self.assertEqual(calls["arm"], [], "no query goes through Resource Manager")
        for hidden in (SECRET, DATA_TOKEN, "KEY-THAT-MUST-NOT-BE-PRINTED"):
            self.assertNotIn(hidden, through_data_plane + err)

    def test_the_query_goes_to_the_app_endpoint_of_the_component_for_this_request_only(self):
        _, _, _, calls = self.go([telemetry(a_good_run())])
        ((url, headers, body),) = calls["queries"]
        self.assertEqual(url, f"https://api.applicationinsights.io/v1/apps/{APP_ID}/query")
        self.assertEqual(headers["Authorization"], f"Bearer {DATA_TOKEN}")
        self.assertEqual(headers["Content-Type"], "application/json")
        document = json.loads(body)
        self.assertEqual(set(document), {"query"})
        self.assertIn(ID, document["query"])
        self.assertIn("meternaut_event", document["query"])
        self.assertRegex(document["query"], r"^traces \| where timestamp > ago\(3h\)")
        self.assertEqual(calls["tokens"], ["https://storage.azure.com/", "https://api.applicationinsights.io"])

    def test_the_application_id_is_read_once_through_resource_manager_before_the_message_is_put_in_the_queue(self):
        everything = a_good_run()
        early = [e for e in everything if e["type"] != "case.result"]
        code, _, _, calls = self.go([telemetry(early), telemetry(everything)])
        self.assertEqual(code, 0)
        self.assertEqual(len(calls["queries"]), 2, "the loop asked twice")
        (read,) = calls["components"]
        self.assertEqual(read[read.index("--url") + 1], f"https://management.azure.com{INSIGHTS}?api-version=2020-02-02")
        self.assertEqual(calls["order"][:3], ["component", "message", "query"])

    def test_it_waits_through_a_403_and_names_the_likely_cause_if_it_stays(self):
        refused = (403, {"error": {"code": "InsufficientAccessError", "message": f"no access {DATA_TOKEN}"}})
        code, out, err, _ = self.go([refused, telemetry(a_good_run())])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("could not be read yet (the data-plane query answered 403", out)
        self.assertNotIn(DATA_TOKEN, out)
        code, out, _, calls = self.go([refused], "--minutes", "1")
        self.assertEqual(code, 1)
        self.assertIn("no end of the run arrived in the telemetry within 1 minutes (0 lines of the run arrived)", out)
        self.assertIn("The last warnings and errors of the cases app:", out)
        self.assertIn("traces: could not be read (the data-plane query answered 403 (the identity probably has no Reader or Monitoring Reader role", out)
        self.assertNotIn(DATA_TOKEN, out)
        self.assertEqual((len(calls["components"]), calls["arm"]), (1, []))

    def test_the_default_is_the_resource_manager_and_the_data_plane_is_not_touched(self):
        for via in (None, "arm"):
            code, out, err, calls = self.go([], via=via, arm=telemetry(a_good_run()))
            self.assertEqual((code, err), (0, ""), via)
            self.assertNotIn("data plane", out)
            self.assertEqual((calls["queries"], calls["components"]), ([], []), via)
            self.assertEqual(calls["tokens"], ["https://storage.azure.com/"], "no token for the data plane")
            (asked,) = calls["arm"]
            self.assertEqual(asked[asked.index("--url") + 1], f"https://management.azure.com{INSIGHTS}/query?api-version=2018-04-20")

    def test_a_component_without_an_application_id_stops_the_run_before_the_message_is_put_in_the_queue(self):
        for answer in ({}, {"properties": {"AppId": "not-a-guid"}}, None):
            code, _, err, calls = self.go([telemetry(a_good_run())], component_answer=answer)
            self.assertEqual(code, 1, answer)
            self.assertIn("gives the component no Application ID", err)
            self.assertEqual((calls["messages"], calls["queries"]), ([], []), answer)

    def test_the_option_belongs_to_run_and_takes_one_of_two_values(self):
        for argv in (["run", "--storage-account", ACCOUNT, "--insights", INSIGHTS, "--query-via", "other"], ["functions", "--site", SITE, "--query-via", "arm"]):
            sent = []
            with mock.patch.dict(os.environ, ENV), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as stop:
                    cc.main(argv, azure(lambda args: (0, "{}", ""), lambda *a: sent.append(a) or (201, b"")))
            self.assertEqual(stop.exception.code, 2, argv)
            self.assertEqual(sent, [], argv)


class Clean(unittest.TestCase):
    def test_what_clean_does(self):
        self.assertEqual(cc.clean(None), "")
        self.assertEqual(cc.clean("a\n\n b\t c"), "a b c")
        self.assertEqual(cc.clean("::error::x"), ": :error: :x")
        self.assertEqual(cc.clean("`a`"), "'a'")
        self.assertEqual(cc.clean("x" * 10, 5), "xx...")


class Clean(unittest.TestCase):
    def test_what_clean_does(self):
        self.assertEqual(cc.clean(None), "")
        self.assertEqual(cc.clean("a\n\n b\t c"), "a b c")
        self.assertEqual(cc.clean("::error::x"), ": :error: :x")
        self.assertEqual(cc.clean("`a`"), "'a'")
        self.assertEqual(cc.clean("x" * 10, 5), "xx...")


STUDY_URL = "https://learn.microsoft.com/en-us/azure/templates/microsoft.example/widgets"
GUID_IN_A_NOTE = "99999999-aaaa-bbbb-cccc-dddddddddddd"


def a_study(**finished):
    """The lines that one run of the Study writes (cases/study.py), with the fields that the check reads."""
    return [
        event("study.started", trigger="control", maxTypes=8, maxPages=8, maxSeconds=300, maxTokens=400000),
        event("study.note", note="claims thrown away: quote 1, cap 1"),
        event("study.claim", claimId="a" * 24, resourceType="microsoft.example/widgets", claimKind="minimum-charge", url=STUDY_URL),
        event("study.claim", claimId="b" * 24, resourceType="microsoft.example/widgets", claimKind="quota-limit", url=STUDY_URL),
        event("study.claim", claimId="c" * 24, resourceType="microsoft.example/gadgets", claimKind="quota-limit", url=STUDY_URL),
        event("study.finished", **{"state": "ran", "ok": True, "types": 4, "studied": 3, "kept": 3, "rejected": 2, "rechecked": 1, "stale": 0, "toolCalls": 11, "pages": 5, "tokens": 123456,
                                   "seconds": 142, "note": "", **finished}),
    ]


class TheStudy(unittest.TestCase):
    """The action study-run: the Operator puts the control message of the job study in the queue and reads the History of that request from the telemetry, and the public log gets counts and plain words."""

    def go(self, answers, *extra, post_status=201, env=ENV, extra_args=("--insights", INSIGHTS)):
        """Runs the check. `answers` are the answers of the telemetry, one for each query, the last one repeated. `posted` says what was put in the queue."""
        asked, posted = [], []
        queue = list(answers)

        def runner(args):
            if args[:2] == ["account", "get-access-token"]:
                return 0, SECRET + "\n", ""
            asked.append(args)
            answer = queue.pop(0) if len(queue) > 1 else queue[0]
            if answer is Exception:
                return 1, "", "ERROR: Forbidden\nmore"
            return 0, json.dumps(answer), ""

        def post(url, headers, body):
            posted.append((url, body))
            return post_status, b""

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(cc.uuid, "uuid4", return_value=mock.Mock(hex=ID)), redirect_stdout(out), redirect_stderr(err):
            code = cc.main(["study", "--storage-account", ACCOUNT, *extra_args, *extra], azure(runner, post))
        return code, out.getvalue(), err.getvalue(), asked, posted

    def test_the_message_names_the_job_study_and_the_request_and_nothing_else_and_goes_to_the_control_queue(self):
        _, _, _, _, posted = self.go([telemetry(a_study())])
        ((url, body),) = posted
        self.assertEqual(url, f"https://{ACCOUNT}.queue.core.windows.net/cases-control/messages?messagettl=3600&timeout=30")
        text = re.search(rb"<MessageText>([^<]+)</MessageText>", body).group(1)
        self.assertEqual(json.loads(base64.b64decode(text, validate=True)), {"job": "study", "requestId": ID})
        self.assertEqual(cc.STUDY_JOB, "study", "the job that cases/control.py starts a Study for")

    def test_a_good_study_passes_and_says_the_counts_in_plain_words(self):
        code, out, err, _, _ = self.go([telemetry(a_study())])
        self.assertEqual((code, err), (0, ""))
        for text in (f"Request {ID}:", "The Study started (by the control); its limits: 8 kinds of resource, 8 pages, 300 seconds, 400000 tokens.",
                     "The Study ended: ran, well, after 142 seconds.", "Kinds of resource given to the Scholar: 4; it says it read about: 3.",
                     "Pages read: 5; tool calls of the page reader: 11.", "Claims kept: 3 (minimum-charge 1, quota-limit 2); thrown away: 2; read again and still on their page: 1; read again and stale: 0.",
                     "Tokens through Foundry: 123456.", "claims thrown away: quote 1, cap 1", "The Study ran and read pages: passed."):
            self.assertIn(text, out)
        self.assertNotIn("microsoft.example", out, "a kind of resource of the estate is not named in a public log")
        self.assertNotIn("learn.microsoft.com", out)
        self.assertNotIn(SECRET, out)

    def test_the_query_is_made_for_this_request_only_and_through_the_resource_manager(self):
        _, _, _, asked, _ = self.go([telemetry(a_study())])
        args = asked[0]
        self.assertEqual(args[args.index("--url") + 1], f"https://management.azure.com{INSIGHTS}/query?api-version=2018-04-20")
        query = json.loads(args[args.index("--body") + 1])["query"]
        self.assertIn(ID, query)
        self.assertRegex(query, r"^traces \| where timestamp > ago\(3h\)")

    def test_it_waits_for_the_claim_lines_that_the_end_counts_and_after_the_deadline_says_which_did_not_arrive(self):
        everything = a_study()
        early = [e for e in everything if e["type"] != "study.claim"]
        code, out, _, asked, _ = self.go([telemetry(early), telemetry(everything)])
        self.assertEqual((code, len(asked)), (0, 2))
        self.assertIn("Claims kept: 3 (minimum-charge 1, quota-limit 2)", out)
        code, out, _, _, _ = self.go([telemetry(early)], "--minutes", "1")
        self.assertEqual(code, 0, "the end says that it ran well; what the telemetry lost is said, not hidden")
        self.assertIn("the telemetry has not delivered: study.claim: 0 of 3", out)

    def test_a_note_that_is_not_the_apps_own_words_is_not_printed_and_cannot_start_a_command_or_run_long(self):
        hostile = [f"could not read /subscriptions/{GUID_IN_A_NOTE}/resourceGroups/rg-secret/providers/Microsoft.Compute/disks/disk-secret (HTTP 403)",
                   "the group resourceGroups/rg-secret and resource group rg-secret2 and rg-secret3 were read",
                   f"object {GUID_IN_A_NOTE.upper()} and {GUID_IN_A_NOTE} are in the text",
                   "host func-meternaut-cases-0123abcd.azurewebsites.net and stexample.queue.core.windows.net and aif-x.services.ai.azure.com are the estate's",
                   "GET management.azure.com and learn.microsoft.com are public", "line one\n::error::fake\r\n##[group]x `tick` ```", "x" * 5000 + "\x00\x1b[31m"]
        events = a_study()
        events[1:1] = [event("study.note", note=text) for text in hostile]
        events[-1] = event("study.finished", state="failed", ok=False, types=1, studied=0, kept=0, rejected=0, rechecked=0, stale=0, toolCalls=0, pages=0, tokens=0, seconds=3,
                           note=f"the survey or the re-read of the claims could not be made (the client {GUID_IN_A_NOTE} has no right over /subscriptions/{GUID_IN_A_NOTE})")
        code, out, _, _, _ = self.go([telemetry(events)])
        self.assertEqual(code, 1)
        for secret in (GUID_IN_A_NOTE, GUID_IN_A_NOTE.upper(), "rg-secret", "disk-secret", "func-meternaut-cases-0123abcd", "stexample", "aif-x", "Microsoft.Compute", "management.azure.com", "HTTP 403"):
            self.assertNotIn(secret, out, secret)
        self.assertIn(cc.NOT_SHOWN, out)
        self.assertIn("the survey or the re-read of the claims could not be made (what follows is not shown in a public log)", out)
        for printed in out.splitlines():
            self.assertFalse(printed.lstrip().startswith("::"), printed)
            self.assertNotIn("##[", printed)
            self.assertNotIn("```", printed)
            self.assertNotIn("\x1b", printed)
            self.assertLessEqual(len(printed), 700, printed[:80])

    def test_the_apps_own_words_and_counts_are_shown_and_what_follows_them_is_not(self):
        for same in ("the Study is switched off", "claims thrown away: quote 1, cap 2", "3 of 3 calls of the page reader were refused or failed (unavailable 3)",
                     "2 of 5 calls of the page reader were refused or failed (unavailable 1, not-text 1)"):
            self.assertEqual(cc.study_note(same), same)
        self.assertEqual(cc.study_note("the Scholar gave no answer (Foundry response failed: HTTP 429 for /subscriptions/x)"), "the Scholar gave no answer (what follows is not shown in a public log)")
        self.assertEqual(cc.study_note("the Scholar gave no answer that could be read (x)"), "the Scholar gave no answer that could be read (what follows is not shown in a public log)")
        for other in ("FoundryError: Resource group 'rg-secret' could not be found.", "claims thrown away: quote 1 and rg-secret", "the Study is switched off and rg-secret", "the Scholar gave no answerx (rg-secret)"):
            self.assertEqual(cc.study_note(other), cc.NOT_SHOWN, other)
        self.assertEqual(cc.study_note(""), "")
        self.assertEqual(cc.study_note(None), "")

    def test_the_note_that_the_costs_could_not_be_read_is_one_of_the_apps_words_it_is_shown_and_it_does_not_fail_the_study(self):
        import sys
        app = str(ROOT / "src" / "case-functions")
        sys.path.insert(0, app)
        try:
            from cases import study as the_app
        finally:
            sys.path.remove(app)
        self.assertIn(the_app.COST_NOTE, cc.STUDY_NOTE_WORDS, "the note that the survey writes when a cost cannot be read is one of the words that a public log shows")
        self.assertEqual(cc.study_note(the_app.COST_NOTE), the_app.COST_NOTE)
        events = a_study()
        events.insert(1, event("study.note", note=the_app.COST_NOTE))
        code, out, _, _, _ = self.go([telemetry(events)])
        self.assertEqual(code, 0, "the Study ran on the old order: that is no failure")
        self.assertIn(f"    - {the_app.COST_NOTE}", out)

    def test_a_number_that_is_not_a_number_is_never_printed(self):
        code, out, _, _, _ = self.go([telemetry(a_study(seconds="::error::x", tokens=True, types="9" * 40, kept=-1, pages=2.5, toolCalls=None, state="RAN!"))])
        self.assertEqual(code, 1)
        for text in ("::error::x", "9" * 40, "RAN!"):
            self.assertNotIn(text, out)
        self.assertIn("after unknown seconds", out)
        self.assertIn("Tokens through Foundry: unknown.", out)

    def test_a_study_that_is_off_fails_and_says_what_to_set_and_what_to_run(self):
        events = [e for e in a_study() if e["type"] == "study.started"] + [event("study.finished", state="off", ok=True, types=0, studied=0, kept=0, rejected=0, rechecked=0, stale=0,
                                                                                  toolCalls=0, pages=0, tokens=0, seconds=0, note="the Study is switched off")]
        code, out, _, _, _ = self.go([telemetry(events)])
        self.assertEqual(code, 1)
        for text in ("The Study ended: off, well, after 0 seconds.", "the Study is switched off", "STUDY is off in the app: set the variable STUDY of the environment hub to on, run the action cases",
                     "and run study-run again.", "The Study did not pass."):
            self.assertIn(text, out)

    def test_each_note_of_the_app_that_means_it_did_not_work_has_its_own_words_for_what_to_check(self):
        known = (("held", "the switch all or the switch investigation is pulled, or cannot be read", "A switch stops the Study"),
                 ("held", "the Scholar could not be made ready (Foundry create agent failed: HTTP 403)", "The Scholar was not made"),
                 ("failed", "the Scholar could not be made ready (Foundry create agent failed: HTTP 403)", "The Scholar was not made"),
                 ("failed", "the Scholar gave no answer (Foundry response failed: HTTP 429)", "The Scholar's run did not end well"),
                 ("failed", "the Scholar gave no answer that could be read (the answer holds no list of claims)", "The Scholar's last text was not one list of claims"),
                 ("failed", "the survey or the re-read of the claims could not be made (HTTP 403)", "The app could not read the estate or its store of claims"),
                 ("off", "no Foundry endpoint is set", "The app has no Foundry project: run foundry and then cases"),
                 ("off", "no store keeps the claims, so there is nothing to study for", "The app has no store for the claims"),
                 ("failed", "something nobody foresaw", "The Study did not do its work"))
        for state, note, advice in known:
            events = [event("study.started", trigger="control"), event("study.finished", state=state, ok=state == "held" or state == "off", types=1, studied=0, kept=0, rejected=0, rechecked=0,
                                                                        stale=0, toolCalls=0, pages=0, tokens=0, seconds=1, note=note)]
            code, out, _, _, _ = self.go([telemetry(events)])
            self.assertEqual(code, 1, note)
            self.assertIn(advice, out, note)
            self.assertIn("What to check:", out)

    def test_a_study_that_ran_and_read_no_page_says_so_and_blames_the_network_only_when_every_call_was_unavailable(self):
        no_pages = [e for e in a_study(pages=0, kept=0, studied=0, toolCalls=6) if e["type"] != "study.claim"]
        code, out, _, _, _ = self.go([telemetry(no_pages)])
        self.assertEqual(code, 1)
        for text in ("Pages read: 0; tool calls of the page reader: 6.", "No page could be read, although the Scholar asked for some", "The Study did not pass."):
            self.assertIn(text, out)
        self.assertNotIn("Meternaut opens nothing itself", out, "zero pages alone do not show that the network is closed")
        for note, network in (("6 of 6 calls of the page reader were refused or failed (unavailable 6)", True), ("6 of 6 calls of the page reader were refused or failed (unavailable 4, not-text 2)", False)):
            code, out, _, _, _ = self.go([telemetry(no_pages[:1] + [event("study.note", note=note)] + no_pages[1:])])
            self.assertEqual(code, 1)
            self.assertEqual("every call of the page reader was unavailable" in out, network, note)
            if network:
                for text in ("learn.microsoft.com, azure.microsoft.com and prices.azure.com on port 443", "Meternaut opens nothing itself"):
                    self.assertIn(text, out)
        code, out, _, _, _ = self.go([telemetry([e for e in a_study(pages=0, kept=0, studied=0, toolCalls=0) if e["type"] != "study.claim"])])
        self.assertEqual(code, 1)
        self.assertIn("The Scholar made no call of the page reader", out)
        self.assertNotIn("No page could be read", out)

    def test_a_study_with_nothing_waiting_passes_and_says_so_and_one_that_read_pages_and_kept_nothing_passes_and_says_so(self):
        nothing = [e for e in a_study(types=0, studied=0, kept=0, rejected=0, rechecked=0, toolCalls=0, pages=0, note="no kind of resource waits to be studied") if e["type"] != "study.claim"]
        code, out, _, _, _ = self.go([telemetry(nothing)])
        self.assertEqual(code, 0)
        self.assertIn("Nothing waited to be studied", out)
        none_kept = [e for e in a_study(kept=0, rejected=4) if e["type"] != "study.claim"]
        code, out, _, _, _ = self.go([telemetry(none_kept)])
        self.assertEqual(code, 0)
        self.assertIn("No claim was kept", out)
        self.assertIn("passed", out)

    def test_an_app_that_does_not_report_the_pages_yet_is_not_failed_for_it(self):
        events = a_study()
        del events[-1]["pages"]
        code, out, _, _, _ = self.go([telemetry(events)])
        self.assertEqual(code, 0)
        self.assertIn("Pages read: not reported (the app is older than this change); tool calls of the page reader: 11.", out)

    def test_an_app_that_refuses_the_message_is_said_with_what_to_do(self):
        for reason, advice in (("the control message names a job that the app does not know: study", "the app is older than the Study: run cases"),
                               ("stale control message", "the app read the message too late"), ("something else", "The app refused the message")):
            code, out, _, _, _ = self.go([telemetry([event("run.failed", reason=reason)])])
            self.assertEqual(code, 1, reason)
            self.assertIn(f"The app refused the message: {reason}.", out)
            self.assertIn(advice, out)

    def test_a_study_that_never_started_fails_after_the_wait_and_says_what_to_check_and_asks_for_no_warning_of_the_app(self):
        empty = {"tables": [{"rows": []}]}
        code, out, _, asked, _ = self.go([empty], "--minutes", "1")
        self.assertEqual(code, 1)
        self.assertIn("No line of the Study arrived in the telemetry within 1 minutes.", out)
        for text in ("that the cases app is running and has the code of the Study (run cases: its functions include study-weekly)", "that its telemetry reaches its Application Insights"):
            self.assertIn(text, out)
        self.assertTrue(all("/query?" in " ".join(args) for args in asked) and len(asked) == 3, "only the History is asked for: the warnings of the app are not printed in a public log")
        self.assertNotIn("The last warnings and errors", out)

    def test_a_study_that_started_and_did_not_end_fails_and_says_so(self):
        code, out, _, _, _ = self.go([telemetry([a_study()[0]])], "--minutes", "1")
        self.assertEqual(code, 1)
        self.assertIn("The Study started and its end did not arrive in the telemetry within 1 minutes", out)
        self.assertNotIn("passed", out)

    def test_a_telemetry_that_cannot_be_read_yet_is_waited_for_and_what_azure_said_is_not_printed(self):
        code, out, _, _, _ = self.go([Exception, telemetry(a_study())])
        self.assertEqual(code, 0)
        self.assertIn("The telemetry could not be read yet (what Azure said is not shown in a public log); waiting.", out)
        self.assertNotIn("Forbidden", out)

    def test_a_line_of_another_request_is_not_this_studys(self):
        other = [{**e, "requestId": "d" * 32} for e in a_study()]
        code, out, _, _, _ = self.go([telemetry(other)], "--minutes", "1")
        self.assertEqual(code, 1)
        self.assertIn("No line of the Study arrived", out)

    def test_a_refused_message_stops_before_anything_is_waited_for_and_only_a_github_actions_run_may_send_one(self):
        code, _, err, asked, _ = self.go([telemetry([])], post_status=403)
        self.assertEqual((code, asked), (1, []))
        self.assertIn("403", err)
        code, _, err, asked, posted = self.go([telemetry([])], env={"GITHUB_ACTIONS": ""})
        self.assertEqual((code, asked, posted), (1, [], []))
        self.assertIn("only a GitHub Actions run may do that", err)

    def test_bad_names_are_refused_before_anything_is_sent_and_the_public_log_has_no_other_mode(self):
        for extra_args in (("--insights", "/subscriptions/x"), ("--insights", INSIGHTS, "--counts-only"), ("--insights", INSIGHTS, "--namespace", "x")):
            with redirect_stderr(io.StringIO()):
                try:
                    code, _, _, _, posted = self.go([telemetry([])], extra_args=extra_args)
                except SystemExit as stop:
                    code, posted = stop.code, []
            self.assertNotEqual(code, 0, extra_args)
            self.assertEqual(posted, [], extra_args)

    def test_the_summary_file_gets_the_same_lines_under_its_own_title(self):
        with TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            code, out, _, _, _ = self.go([telemetry(a_study())], "--summary", str(summary))
            text = summary.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn(cc.STUDY_TITLE, text)
        self.assertNotEqual(cc.STUDY_TITLE, cc.SECTION_TITLE)
        for printed in out.splitlines():
            if "Tokens through Foundry" in printed:
                self.assertIn(printed, text)

    def test_the_lines_and_the_fields_are_the_ones_the_app_writes_and_the_functions_that_the_job_needs_are_listed(self):
        import sys
        app = str(ROOT / "src" / "case-functions")
        sys.path.insert(0, app)
        try:
            from cases import events as writer
        finally:
            sys.path.remove(app)
        self.assertIn(cc.STUDY_ENDS[0], writer.STUDY_KINDS)
        self.assertIn(cc.STUDY_ENDS[1], writer.KINDS)
        source = (ROOT / "src" / "case-functions" / "cases" / "study.py").read_text(encoding="utf-8")
        for name in ("state", "ok", "types", "studied", "kept", "rejected", "rechecked", "stale", "toolCalls", "pages", "tokens", "seconds", "note", "trigger", "maxTypes", "maxPages", "maxSeconds",
                     "maxTokens", "claimKind"):
            self.assertRegex(source, rf"(?<![A-Za-z_]){name}=", name)
        self.assertIn("study-weekly", cc.FUNCTIONS, "the list that is waited for before the message is sent holds the function of the Study")

    def test_public_masks_what_identifies_the_estate_and_leaves_plain_words(self):
        self.assertEqual(cc.public("the cases app func-x.azurewebsites.net could not read /subscriptions/1/resourceGroups/g (HTTP 403)"), "the cases app <host> could not read <resource id> (HTTP 403)")
        self.assertEqual(cc.public("claims thrown away: quote 1, cap 2"), "claims thrown away: quote 1, cap 2")
        self.assertEqual(cc.public(None), "")
        self.assertEqual(cc.public("x" * 400, 50), "x" * 47 + "...")
        self.assertEqual(cc.public("model gpt-5.5 on learn.microsoft.com"), "model gpt-5.5 on learn.microsoft.com")


def a_ready(**finished):
    """The lines that the job ready writes (cases/ready.py), with the fields that the check reads: the Investigator made, the other two found."""
    return [
        event("agents.ready", agent="meternaut-investigator", version=18, definition="3f9a1c0b7e2d", outcome="made"),
        event("agents.ready", agent="meternaut-skeptic", version=4, definition="91d0aa4c2b77", outcome="existing"),
        event("agents.ready", agent="meternaut-scholar", version=3, definition="c7e5b1029f3a", outcome="existing"),
        event("agents.ready.finished", **{"ok": True, "made": 1, "existing": 2, "refused": 0, "failed": 0, "why": "", "seconds": 3, **finished}),
    ]


class TheReady(unittest.TestCase):
    """The action agents-ready: the Operator puts the control message of the job ready in the queue and reads the lines of that request from the telemetry, and the public log gets counts and plain words."""

    def go(self, answers, *extra, post_status=201, env=ENV, extra_args=("--insights", INSIGHTS)):
        """Runs the check. `answers` are the answers of the telemetry, one for each query, the last one repeated. `posted` says what was put in the queue."""
        asked, posted = [], []
        queue = list(answers)

        def runner(args):
            if args[:2] == ["account", "get-access-token"]:
                return 0, SECRET + "\n", ""
            asked.append(args)
            answer = queue.pop(0) if len(queue) > 1 else queue[0]
            if answer is Exception:
                return 1, "", "ERROR: Forbidden\nmore"
            return 0, json.dumps(answer), ""

        def post(url, headers, body):
            posted.append((url, body))
            return post_status, b""

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(cc.uuid, "uuid4", return_value=mock.Mock(hex=ID)), redirect_stdout(out), redirect_stderr(err):
            code = cc.main(["ready", "--storage-account", ACCOUNT, *extra_args, *extra], azure(runner, post))
        return code, out.getvalue(), err.getvalue(), asked, posted

    def test_the_message_names_the_job_ready_and_the_request_and_nothing_else_and_goes_to_the_control_queue(self):
        _, _, _, _, posted = self.go([telemetry(a_ready())])
        ((url, body),) = posted
        self.assertEqual(url, f"https://{ACCOUNT}.queue.core.windows.net/cases-control/messages?messagettl=3600&timeout=30")
        text = re.search(rb"<MessageText>([^<]+)</MessageText>", body).group(1)
        self.assertEqual(json.loads(base64.b64decode(text, validate=True)), {"job": "ready", "requestId": ID})

    def test_a_good_job_passes_and_says_for_each_agent_its_version_and_whether_it_was_made_and_what_comes_next(self):
        code, out, err, asked, _ = self.go([telemetry(a_ready())])
        self.assertEqual((code, err), (0, ""))
        for text in (f"Request {ID}:", "meternaut-investigator: version 18, made (definition 3f9a1c0b7e2d).", "meternaut-skeptic: version 4, existing (definition 91d0aa4c2b77).",
                     "meternaut-scholar: version 3, existing (definition c7e5b1029f3a).", "The job ended after 3 seconds: 1 made, 2 existing, 0 refused, 0 failed. It called no model and read nothing of the estate.",
                     "All three agents are ready: passed.", "nothing about how they answer", "What comes next: run foundry-evals on this version, then cases-run.",
                     "The replay covers the Investigator only: after a change to the Skeptic, cases-run is the first test of it, and after a change to the Scholar, study-run is."):
            self.assertIn(text, out)
        self.assertTrue(out.rstrip().endswith("after a change to the Scholar, study-run is."), "it is the last thing that the pass says: what comes next, and what the replay does not cover")
        self.assertNotIn(SECRET, out)
        args = asked[0]
        self.assertEqual(args[args.index("--url") + 1], f"https://management.azure.com{INSIGHTS}/query?api-version=2018-04-20")
        query = json.loads(args[args.index("--body") + 1])["query"]
        self.assertIn(ID, query)
        self.assertRegex(query, r"^traces \| where timestamp > ago\(3h\)")

    def test_it_waits_for_the_agent_lines_that_the_end_counts_and_after_the_deadline_says_which_did_not_arrive(self):
        everything = a_ready()
        early = [e for e in everything if e["type"] != "agents.ready"][:1] + everything[:1]
        code, out, _, asked, _ = self.go([telemetry(early), telemetry(everything)])
        self.assertEqual((code, len(asked)), (0, 2))
        self.assertIn("meternaut-scholar: version 3, existing", out)
        code, out, _, _, _ = self.go([telemetry(everything[:1] + everything[3:])], "--minutes", "1")
        self.assertEqual(code, 0, "the end says that all three are ready; what the telemetry lost is said, not hidden")
        self.assertIn("the telemetry has not delivered: agents.ready: 1 of 3", out)
        self.assertIn("meternaut-skeptic: no line arrived (the end of the job counts it).", out)

    def test_an_agent_that_was_refused_fails_the_check_with_its_reason_word_and_what_to_check(self):
        for reason, advice in (("lock", "The app cannot use the lock of the agents"), ("no-store", "no store for its switches"), ("switch", "A switch stops the agents"),
                               ("lock-differs", "is not the one in the lock, so nothing was made from it"), ("stored-unreadable", "could not be read back"),
                               ("stored-missing", "was not in the project after it was made"), ("version-moved", "A newer version appeared"), ("definition", "The stored definition differs from the lock"),
                               ("service", "The Foundry project gave no answer, or refused"), ("other", "a word that this check does not know")):
            events = a_ready(ok=False, made=0, existing=2, refused=1)
            events[0] = event("agents.ready", agent="meternaut-investigator", version=None, definition="3f9a1c0b7e2d", outcome="failed" if reason == "service" else "refused", reason=reason, **({"status": 403} if reason == "service" else {}))
            code, out, _, _, _ = self.go([telemetry(events)])
            self.assertEqual(code, 1, reason)
            self.assertIn(f"meternaut-investigator: {'failed' if reason == 'service' else 'refused'} ({reason}" + (", HTTP 403)." if reason == "service" else ")."), out, reason)
            self.assertIn(f"What to check: ", out)
            self.assertIn(advice, out, reason)
            self.assertIn("The agents were not made ready: the check did not pass.", out)
            self.assertNotIn("What comes next", out, "nothing is promised after a refusal")

    def test_a_job_that_could_not_begin_fails_and_says_why(self):
        for why, advice in (("no-endpoint", "The app has no Foundry project: run foundry and then cases."), ("setup", "a setting or the loop is not valid"), ("error", "The job broke where nobody foresaw")):
            events = [event("agents.ready.finished", ok=False, made=0, existing=0, refused=0, failed=0, why=why, seconds=0)]
            code, out, _, _, _ = self.go([telemetry(events)])
            self.assertEqual(code, 1, why)
            self.assertIn(f"The job could not begin: {why}.", out)
            self.assertIn(advice, out)
            self.assertIn("meternaut-investigator: no line arrived.", out)

    def test_every_word_of_the_job_has_its_words_for_what_to_check(self):
        import sys
        app = str(ROOT / "src" / "case-functions")
        sys.path.insert(0, app)
        try:
            from cases import control, events as writer, ready as the_app
        finally:
            sys.path.remove(app)
        self.assertEqual(set(cc.READY_ADVICE), set(the_app.REASONS) | set(the_app.WHY), "each word that the app writes has its advice, and each advice is for a word that it writes")
        self.assertEqual((cc.READY_JOB, cc.AGENTS), (control.READY_JOB, the_app.NAMES))
        self.assertIn(cc.READY_ENDS[0], writer.READY_KINDS)
        self.assertIn(cc.READY_ENDS[1], writer.KINDS)
        self.assertIn("agents.ready", writer.READY_KINDS)
        source = (ROOT / "src" / "case-functions" / "cases" / "ready.py").read_text(encoding="utf-8")
        for name in ("agent", "version", "definition", "outcome", "ok", "why", "seconds"):
            self.assertRegex(source, rf"(?<![A-Za-z_]){name}=", name)
        for name in ("reason", "status", "made", "existing", "refused", "failed"):
            self.assertIn(f'"{name}"', source, name)

    def test_nothing_of_a_line_that_is_not_a_name_of_the_three_agents_a_number_or_a_word_of_code_is_printed(self):
        hostile = f"rg-secret /subscriptions/{GUID_IN_A_NOTE}/resourceGroups/rg-secret ::error::x `tick` \x1b[31m"
        events = [event("agents.ready", agent=hostile, version=hostile, definition=hostile, outcome=hostile, reason=hostile, status=hostile),
                  event("agents.ready", agent="meternaut-skeptic", version=GUID_IN_A_NOTE, definition=GUID_IN_A_NOTE, outcome="refused", reason=hostile, status=True),
                  event("agents.ready", agent="meternaut-scholar", version=True, definition="G" * 12, outcome="made"),
                  event("agents.ready.finished", ok=hostile, made=hostile, existing=-1, refused=2.5, failed=None, why=hostile, seconds="::error::x")]
        code, out, _, _, _ = self.go([telemetry(events)])
        self.assertEqual(code, 1)
        for secret in ("rg-secret", GUID_IN_A_NOTE, "::error::x", "tick", "\x1b", "G" * 12, "subscriptions"):
            self.assertNotIn(secret, out, secret)
        self.assertIn("meternaut-skeptic: refused (other).", out)
        self.assertIn("meternaut-scholar: version unknown, made.", out)
        self.assertIn("meternaut-investigator: no line arrived.", out)
        self.assertIn("after unknown seconds: unknown made, unknown existing, unknown refused, unknown failed.", out)
        for printed in out.splitlines():
            self.assertFalse(printed.lstrip().startswith("::"), printed)
            self.assertLessEqual(len(printed), 400, printed[:80])

    def test_an_app_that_refuses_the_message_is_said_with_what_to_do(self):
        for reason, advice in (("the control message names a job that the app does not know: ready", "the app is older than this change: run cases"),
                               ("stale control message", "the app read the message too late"), ("something else", "the reason above says why")):
            code, out, _, _, _ = self.go([telemetry([event("run.failed", reason=reason)])])
            self.assertEqual(code, 1, reason)
            self.assertIn(f"The app refused the message: {reason}.", out)
            self.assertIn(advice, out)

    def test_a_job_that_never_arrived_fails_after_the_wait_and_says_what_to_check_and_asks_for_no_warning_of_the_app(self):
        code, out, _, asked, _ = self.go([{"tables": [{"rows": []}]}], "--minutes", "1")
        self.assertEqual(code, 1)
        self.assertIn("No line of the job arrived in the telemetry within 1 minutes.", out)
        for text in ("that the cases app is running and has the code of this job (run cases)", "that its telemetry reaches its Application Insights", "The agents were not made ready"):
            self.assertIn(text, out)
        self.assertTrue(all("/query?" in " ".join(args) for args in asked), "only the History is asked for: the warnings of the app are not printed in a public log")
        code, out, _, _, _ = self.go([telemetry(a_ready()[:2])], "--minutes", "1")
        self.assertEqual(code, 1)
        self.assertIn("2 lines of the job arrived in the telemetry within 1 minutes, and its end did not.", out)
        self.assertNotIn("passed", out)

    def test_a_message_that_the_host_handed_over_again_leaves_two_lines_for_an_agent_and_the_last_one_counts(self):
        events = [event("agents.ready", agent="meternaut-investigator", version=18, definition="3f9a1c0b7e2d", outcome="made")] + a_ready(made=0, existing=3)
        events[1:2] = [event("agents.ready", agent="meternaut-investigator", version=18, definition="3f9a1c0b7e2d", outcome="existing")]
        code, out, _, _, _ = self.go([telemetry(events)])
        self.assertEqual(code, 0)
        self.assertIn("meternaut-investigator: version 18, existing (definition 3f9a1c0b7e2d).", out)
        self.assertNotIn("meternaut-investigator: version 18, made", out)

    def test_an_end_that_says_not_ok_without_a_line_that_says_why_still_fails(self):
        code, out, _, _, _ = self.go([telemetry(a_ready(ok=False))])
        self.assertEqual(code, 1)
        self.assertIn("the end of the job does not say that all three agents are ready", out)

    def test_a_telemetry_that_cannot_be_read_yet_is_waited_for_and_what_azure_said_is_not_printed(self):
        code, out, _, _, _ = self.go([Exception, telemetry(a_ready())])
        self.assertEqual(code, 0)
        self.assertIn("The telemetry could not be read yet (what Azure said is not shown in a public log); waiting.", out)
        self.assertNotIn("Forbidden", out)

    def test_a_line_of_another_request_is_not_this_jobs(self):
        other = [{**e, "requestId": "d" * 32} for e in a_ready()]
        code, out, _, _, _ = self.go([telemetry(other)], "--minutes", "1")
        self.assertEqual(code, 1)
        self.assertIn("No line of the job arrived", out)

    def test_a_refused_message_stops_before_anything_is_waited_for_and_only_a_github_actions_run_may_send_one(self):
        code, _, err, asked, _ = self.go([telemetry([])], post_status=403)
        self.assertEqual((code, asked), (1, []))
        self.assertIn("403", err)
        code, _, err, asked, posted = self.go([telemetry([])], env={"GITHUB_ACTIONS": ""})
        self.assertEqual((code, asked, posted), (1, [], []))
        self.assertIn("only a GitHub Actions run may do that", err)

    def test_bad_names_are_refused_before_anything_is_sent_and_the_public_log_has_no_other_mode(self):
        for extra_args in (("--insights", "/subscriptions/x"), ("--insights", INSIGHTS, "--counts-only"), ("--insights", INSIGHTS, "--namespace", "x")):
            with redirect_stderr(io.StringIO()):
                try:
                    code, _, _, _, posted = self.go([telemetry([])], extra_args=extra_args)
                except SystemExit as stop:
                    code, posted = stop.code, []
            self.assertNotEqual(code, 0, extra_args)
            self.assertEqual(posted, [], extra_args)

    def test_the_summary_file_gets_the_same_lines_under_its_own_title(self):
        with TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            code, out, _, _, _ = self.go([telemetry(a_ready())], "--summary", str(summary))
            text = summary.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn(cc.READY_TITLE, text)
        self.assertNotIn(text.split("\n")[0], (cc.SECTION_TITLE, cc.STUDY_TITLE))
        for printed in out.splitlines():
            if "version 18, made" in printed:
                self.assertIn(printed, text)


class TheCheckerAsksForNoKeyAndCallsNothingElse(unittest.TestCase):
    def test_no_call_to_the_estate_and_no_key(self):
        source = (ROOT / "tools" / "cases-check.py").read_text(encoding="utf-8")
        code = re.sub(r'""".*?"""', "", source, flags=re.S)
        for word in ("listKeys", "listSecrets", "primaryKey", "SharedAccessSignature", "AccountKey", "api-key", "az login"):
            self.assertNotIn(word, code, word)
        self.assertNotRegex(code, r"https://[a-z0-9.-]+\.(azure-api|documents\.azure|blob\.core\.windows)\.", "it reads only the telemetry and puts one message in one queue")
        self.assertNotRegex(code, r"\.token\(", "it asks for no token of its own: the helpers of tools/check-helpers.py do, for the three resources that its own test pins")
        self.assertNotIn("api.applicationinsights.io", code, "the host of the data plane is in the helpers, and in one place")


if __name__ == "__main__":
    unittest.main()
