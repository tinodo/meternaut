import base64
import importlib.util
import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("recording_check", ROOT / "tools" / "recording-check.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

SITE = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-example/providers/Microsoft.Web/sites/logic-example"
OID = "99999999-8888-7777-6666-555555555555"
SECRET = "SECRET-TOKEN-VALUE"


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
    return rc.Azure(runner=runner, post=post or (lambda *a: (500, b"{}", {})), sleep=clock.sleep, clock=clock)


def workflows(count):
    return [{"name": f"wf-{i}", "kind": "Stateful", "health": {"state": "Healthy"}} for i in range(count)]


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


class Workflows(unittest.TestCase):
    def test_it_waits_until_enough_workflows_are_listed(self):
        answers = iter([Exception, 2, 5])
        calls = []

        def runner(args):
            calls.append(args)
            step = next(answers)
            if step is Exception:
                return 1, "", "ERROR: BadGateway"
            return 0, json.dumps(workflows(step)), ""

        out = io.StringIO()
        with redirect_stdout(out):
            code = rc.main(["workflows", "--site", SITE, "--expect", "5"], azure(runner))
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 3)
        self.assertIn("lists 5 workflows", out.getvalue())
        self.assertIn("wf-0 (Stateful, Healthy)", out.getvalue())
        self.assertIn("/hostruntime/runtime/webhooks/workflow/api/management/workflows?api-version=2018-11-01", calls[0][4])

    def test_it_gives_up_with_the_last_reason(self):
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = rc.main(["workflows", "--site", SITE, "--expect", "5", "--minutes", "1"], azure(lambda args: (0, json.dumps(workflows(1)), "")))
        self.assertEqual(code, 1)
        self.assertIn("1 of 5 workflows are listed", err.getvalue())

    def test_a_site_that_is_not_a_logic_app_is_refused(self):
        for bad in ("", "/subscriptions/x", SITE.replace("Microsoft.Web/sites", "Microsoft.Storage/storageAccounts"), SITE + "/slots/x"):
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                self.assertEqual(rc.main(["workflows", "--site", bad], azure(lambda args: (0, "[]", ""))), 1)
            self.assertIn("--site", err.getvalue())

    def test_a_workflow_that_is_disabled_is_shown_as_disabled(self):
        self.assertEqual(rc.describe({"name": "a", "kind": "Stateful", "isDisabled": True}), "a (Stateful, disabled)")


class Run(unittest.TestCase):
    ENV = {"GITHUB_ACTIONS": "true"}

    def fake(self, status="Succeeded", cosmos_status=200, pages=None):
        calls = []
        pages = pages if pages is not None else {
            rc.USAGE_CONTAINER: [[{"id": "llm-1", "productName": "p", "deploymentName": "gpt-6-luna", "promptTokens": 12, "responseTokens": 5, "totalTokens": 17, "_ts": 1000},
                                  {"id": "llm-2", "productName": "p", "deploymentName": "gpt-6.1-sol", "promptTokens": 1, "responseTokens": 2, "totalTokens": 3, "_ts": 2000}]],
            rc.MARKER_CONTAINER: [[{"id": "002", "lastExportDate": "2026-11-04T10:00:00", "totalExportedRecords": 2}]],
        }
        posted = []

        def runner(args):
            calls.append(args)
            if args[0] == "account":
                return 0, SECRET + "\n", ""
            method, url = args[2], args[4]
            if method == "post":
                return 0, "", ""
            if "/runs/" in url and url.split("?")[0].endswith("/actions"):
                return 0, json.dumps({"value": [
                    {"name": "Read_Export_Config", "properties": {"status": "Succeeded", "startTime": "2026-11-04T10:00:01Z"}},
                    {"name": "Run_query", "properties": {"status": "Failed", "startTime": "2026-11-04T10:00:02Z", "error": {"code": "Forbidden", "message": "no access\nsecond line"}}}]}), ""
            if url.split("?")[0].endswith("/runs"):
                start = (datetime.now(timezone.utc) + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
                return 0, json.dumps({"value": [{"name": "08585", "properties": {"status": status, "startTime": start}}]}), ""
            return 0, json.dumps(workflows(5)), ""

        def post(url, headers, body):
            posted.append((url, headers, json.loads(body)))
            container = url.split("/colls/")[1].split("/")[0]
            if cosmos_status != 200:
                return cosmos_status, json.dumps({"message": "Request blocked by Auth\nactivity id"}).encode(), {}
            queue = pages[container]
            page = queue.pop(0)
            return 200, json.dumps({"Documents": page}).encode(), {"x-ms-continuation": "next"} if queue else {}

        return azure(runner, post), calls, posted

    def run_main(self, fake, *extra, env=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.ENV if env is None else env, clear=False), redirect_stdout(out), redirect_stderr(err):
            code = rc.main(["run", "--site", SITE, "--cosmos-account", "cosmos-example", *extra], fake)
        return code, out.getvalue(), err.getvalue()

    def test_a_good_run_prints_the_actions_and_the_documents_and_no_token(self):
        fake, calls, posted = self.fake()
        code, out, err = self.run_main(fake)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Run 08585 of llm-usage-ingestion: Succeeded", out)
        self.assertIn("Read_Export_Config: Succeeded", out)
        self.assertIn("llm-usage-container: 2 documents", out)
        self.assertIn("prompt 1  response 2  total 3", out)
        self.assertLess(out.index("model gpt-6.1-sol"), out.index("model gpt-6-luna"), "the newest document is listed first")
        self.assertIn("002: copied up to 2026-11-04T10:00:00, 2 records", out)
        self.assertNotIn(SECRET, out + err)
        self.assertTrue(any(c[2] == "post" and c[4].split("?")[0].endswith("/triggers/Recurrence/run") for c in calls if c[0] == "rest"))

    def test_the_store_is_read_with_the_identity_token_and_plain_queries_only(self):
        fake, calls, posted = self.fake()
        self.run_main(fake)
        self.assertEqual([p[0] for p in posted], [
            "https://cosmos-example.documents.azure.com/dbs/ai-usage-db/colls/llm-usage-container/docs",
            "https://cosmos-example.documents.azure.com/dbs/ai-usage-db/colls/streaming-export-config/docs"])
        for _, headers, body in posted:
            self.assertEqual(headers["Authorization"], f"type%3Daad%26ver%3D1.0%26sig%3D{SECRET}")
            self.assertEqual(headers["x-ms-documentdb-query-enablecrosspartition"], "True")
            for word in ("ORDER BY", "TOP", "COUNT", "DISTINCT", "GROUP BY"):
                self.assertNotIn(word, body["query"].upper())
        self.assertIn(["account", "get-access-token", "--resource", "https://cosmos-example.documents.azure.com", "--query", "accessToken", "--output", "tsv", "--only-show-errors"], calls)

    def test_a_second_page_is_read_by_its_continuation(self):
        pages = {rc.USAGE_CONTAINER: [[{"id": "a", "_ts": 1}], [{"id": "b", "_ts": 2}]], rc.MARKER_CONTAINER: [[]]}
        fake, calls, posted = self.fake(pages=pages)
        code, out, err = self.run_main(fake)
        self.assertEqual(code, 0)
        self.assertIn("llm-usage-container: 2 documents", out)
        self.assertEqual(posted[1][1]["x-ms-continuation"], "next")
        self.assertNotIn("x-ms-continuation", posted[0][1])

    def test_a_failed_run_fails_the_check_and_shows_why(self):
        fake, _, _ = self.fake(status="Failed")
        code, out, err = self.run_main(fake)
        self.assertEqual(code, 1)
        self.assertIn("Run 08585 of llm-usage-ingestion: Failed", out)
        self.assertIn("Run_query: Failed: Forbidden no access", out)
        self.assertNotIn("second line", out)

    def test_a_store_that_cannot_be_read_fails_the_check_and_says_what_the_service_said(self):
        fake, _, _ = self.fake(cosmos_status=403)
        code, out, err = self.run_main(fake)
        self.assertEqual(code, 1)
        self.assertIn("The usage store could not be read: reading llm-usage-container answered 403: Request blocked by Auth", out)
        self.assertNotIn("activity id", out)
        self.assertNotIn(SECRET, out + err)

    def test_only_a_github_actions_run_may_start_the_job(self):
        fake, calls, posted = self.fake()
        code, out, err = self.run_main(fake, env={"GITHUB_ACTIONS": ""})
        self.assertEqual(code, 1)
        self.assertIn("only a GitHub Actions run", err)
        self.assertEqual((calls, posted), ([], []), "nothing is asked of Azure")

    def test_bad_names_are_refused_before_anything_is_asked(self):
        for extra in (("--workflow", "a b"), ("--workflow", "../x"), ("--trigger", "x;y")):
            fake, calls, _ = self.fake()
            code, out, err = self.run_main(fake, *extra)
            self.assertEqual((code, calls), (1, []), extra)
        fake, calls, _ = self.fake()
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.ENV), redirect_stdout(out), redirect_stderr(err):
            code = rc.main(["run", "--site", SITE, "--cosmos-account", "Bad_Name"], fake)
        self.assertEqual((code, calls), (1, []))

    def test_the_summary_file_gets_the_same_lines(self):
        fake, _, _ = self.fake()
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.md"
            code, out, err = self.run_main(fake, "--summary", str(path))
            text = path.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn("### The copy job and the usage store", text)
        self.assertIn("llm-usage-container: 2 documents", text)
        self.assertNotIn(SECRET, text)

    def test_a_run_that_never_ends_times_out(self):
        def runner(args):
            if args[0] == "account":
                return 0, SECRET, ""
            if args[2] == "post":
                return 0, "", ""
            if args[4].split("?")[0].endswith("/runs"):
                start = (datetime.now(timezone.utc) + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
                return 0, json.dumps({"value": [{"name": "1", "properties": {"status": "Running", "startTime": start}}]}), ""
            return 0, json.dumps(workflows(5)), ""

        code, out, err = self.run_main(azure(runner), "--minutes", "1")
        self.assertEqual(code, 1)
        self.assertIn("did not end within 1 minutes", err)


class Lines(unittest.TestCase):
    def test_a_time_that_cannot_be_read_is_a_question_mark(self):
        self.assertEqual(rc.iso(None), "?")
        self.assertEqual(rc.iso("x"), "?")
        self.assertEqual(rc.iso(0), "1970-01-01T00:00:00Z")

    def test_only_five_documents_are_listed_but_all_are_counted(self):
        lines = rc.usage_lines([{"id": str(i), "_ts": i} for i in range(9)])
        self.assertEqual(len(lines), 6)
        self.assertEqual(lines[0], "llm-usage-container: 9 documents")

    def test_no_prompt_and_no_answer_is_in_what_is_asked_for(self):
        for word in ("messages", "prompt\"", "content", "appId", "RequestIp"):
            self.assertNotIn(word, rc.USAGE_FIELDS)


if __name__ == "__main__":
    unittest.main()
