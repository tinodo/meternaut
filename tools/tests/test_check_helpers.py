"""tools/check-helpers.py: what the check tool of the cases (tools/cases-check.py) shares with nothing else: the object id of the signed-in identity, the one message to the control queue,
the telemetry read through Resource Manager or through the data plane of Application Insights, and the plain words about what a service answered.
The commands of the tool itself (the functions, the run) are tested in test_cases_check.py."""
import base64
import http.client
import importlib.util
import io
import json
import os
import re
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
cases_spec = importlib.util.spec_from_file_location("cases_check_of_the_helpers_tests", ROOT / "tools" / "cases-check.py")
cc = importlib.util.module_from_spec(cases_spec)
cases_spec.loader.exec_module(cc)
rc = cc.rc

DEFAULT = object()
SITE = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-example/providers/Microsoft.Web/sites/func-example"
INSIGHTS = "/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/rg-example/providers/Microsoft.Insights/components/appi-example"
ACCOUNT = "stexample"
OID = "99999999-8888-7777-6666-555555555555"
SECRET = "SECRET-TOKEN-VALUE"
DATA_TOKEN = "DATA-PLANE-TOKEN-VALUE"
APP_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
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


def component(**properties):
    """What Resource Manager says of a component. It holds more than the helpers may keep: the instrumentation key and the connection string must reach no line."""
    return {"id": INSIGHTS, "name": "appi-example", "type": "Microsoft.Insights/components",
            "properties": {"AppId": APP_ID, "InstrumentationKey": "KEY-THAT-MUST-NOT-BE-PRINTED", "ConnectionString": "InstrumentationKey=KEY-THAT-MUST-NOT-BE-PRINTED", **properties}}


def rows_of(*messages):
    return {"tables": [{"name": "PrimaryResult", "columns": [{"name": "timestamp"}, {"name": "message"}], "rows": [["2026-11-04T13:01:00Z", message] for message in messages]}]}


class Whoami(unittest.TestCase):
    def test_the_object_id_comes_from_the_claims_and_the_token_is_never_printed(self):
        token = jwt({"oid": OID.upper(), "x": SECRET})
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cc.main(["whoami"], azure(lambda args: (0, token + "\n", "")))
        self.assertEqual((code, out.getvalue().strip(), err.getvalue()), (0, OID, ""))
        self.assertNotIn(SECRET, out.getvalue() + err.getvalue())

    def test_a_token_without_an_object_id_is_refused(self):
        for token in (jwt({}), jwt({"oid": "not-a-guid"}), "no-dots", jwt({"oid": 5}), "a.!!!.c"):
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                code = cc.main(["whoami"], azure(lambda args, t=token: (0, t, "")))
            self.assertEqual(code, 1, token)
            self.assertIn("no object id", err.getvalue())

    def test_a_failed_sign_in_says_so_without_the_cli_output_beyond_its_first_line(self):
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = cc.main(["whoami"], azure(lambda args: (1, "", "ERROR: please run az login\nmore lines\n")))
        self.assertEqual(code, 1)
        self.assertIn("please run az login", err.getvalue())
        self.assertNotIn("more lines", err.getvalue())


class TheNamesThatAreChecked(unittest.TestCase):
    def test_a_site_that_is_not_a_function_app_is_refused(self):
        self.assertEqual(rc.check_site(SITE), SITE)
        for bad in ("", "/subscriptions/x", SITE.replace("Microsoft.Web/sites", "Microsoft.Storage/storageAccounts"), SITE + "/slots/x"):
            with self.assertRaises(rc.Problem, msg=bad):
                rc.check_site(bad)

    def test_a_component_that_is_not_an_application_insights_component_is_refused(self):
        self.assertEqual(rc.check_insights(INSIGHTS), INSIGHTS)
        for bad in ("", "/subscriptions/x", INSIGHTS.replace("Microsoft.Insights/components", "Microsoft.Storage/storageAccounts"), INSIGHTS + "/x"):
            with self.assertRaises(rc.Problem, msg=bad):
                rc.check_insights(bad)

    def test_a_storage_account_may_be_given_with_its_queue_host_and_a_bad_one_is_refused(self):
        self.assertEqual(rc.queue_host(ACCOUNT), f"{ACCOUNT}.queue.core.windows.net")
        self.assertEqual(rc.queue_host(f"{ACCOUNT}.queue.core.windows.net"), f"{ACCOUNT}.queue.core.windows.net")
        self.assertEqual(rc.queue_host(f"  {ACCOUNT.upper()} "), f"{ACCOUNT}.queue.core.windows.net", "a host name has no case")
        for bad in ("", "x", "ab", "a" * 25, "a b", "st-example", "st_example", "st/example", "st.other.net", f"{ACCOUNT}.blob.core.windows.net", f"{ACCOUNT}.servicebus.windows.net"):
            with self.assertRaises(rc.Problem, msg=bad):
                rc.queue_host(bad)

    def test_the_functions_of_an_app_are_listed_by_name(self):
        answer = {"value": [{"name": "func-example/console", "properties": {"name": "console"}}, {"name": "func-example/runner-tick"}, "x", {"properties": {}}]}
        calls = []

        def runner(args):
            calls.append(args)
            return 0, json.dumps(answer), ""

        self.assertEqual(rc.function_names(azure(runner), SITE), ["console", "runner-tick"])
        self.assertEqual(calls[0][:6], ["rest", "--method", "get", "--url", f"https://management.azure.com{SITE}/functions?api-version=2024-04-01", "--only-show-errors"])


class PuttingTheControlMessage(unittest.TestCase):
    def put(self, **changes):
        posts = []

        def runner(args):
            return 0, SECRET + "\n", ""

        def post(url, headers, body):
            posts.append((url, headers, body))
            if "raises" in changes:
                raise changes["raises"]
            return changes.get("status", 201), changes.get("answer", b"")

        with mock.patch.dict(os.environ, ENV):
            rc.send_control_message(azure(runner, post), changes.get("account", ACCOUNT), "watch", "a" * 32, queue=changes.get("queue", "a-control-queue"))
        return posts

    def test_one_message_goes_to_the_named_queue_with_the_operators_token_and_the_documented_headers(self):
        ((url, headers, body),) = self.put()
        self.assertEqual(url, f"https://{ACCOUNT}.queue.core.windows.net/a-control-queue/messages?messagettl=3600&timeout=30")
        self.assertEqual(headers, {"Authorization": f"Bearer {SECRET}", "x-ms-version": "2026-04-06", "Content-Type": "application/xml"},
                         "Put Message with a Microsoft Entra token: the Bearer scheme, a service version of 2017-11-09 or later, and an XML body")
        self.assertEqual(rc.QUEUE_SERVICE_VERSION, "2026-04-06")

    def test_the_body_is_the_xml_of_put_message_and_holds_the_base64_text_of_the_json_that_the_app_reads(self):
        ((_, _, body),) = self.put()
        root = ElementTree.fromstring(body.decode("utf-8"))
        self.assertEqual((root.tag, [child.tag for child in root]), ("QueueMessage", ["MessageText"]))
        text = root.find("MessageText").text
        decoded = base64.b64decode(text, validate=True)
        self.assertEqual(decoded.decode("utf-8"), '{"job":"watch","requestId":"' + "a" * 32 + '"}', "the Functions host decodes base64 before the app reads the message")
        self.assertEqual(json.loads(decoded), {"job": "watch", "requestId": "a" * 32})

    def test_the_text_that_the_app_gets_is_what_the_app_accepts(self):
        source = (ROOT / "src" / "case-functions" / "cases" / "control.py").read_text(encoding="utf-8")
        self.assertIn('REQUEST_ID = re.compile(r"^[0-9a-f]{32}$")', source)
        self.assertIn('JOB = "watch"', source)
        ((_, _, body),) = self.put()
        document = json.loads(base64.b64decode(ElementTree.fromstring(body.decode("utf-8")).find("MessageText").text))
        self.assertEqual(set(document), {"job", "requestId"}, "a message carries the job and the request id and nothing else")
        self.assertEqual(document["job"], "watch")
        self.assertRegex(document["requestId"], r"^[0-9a-f]{32}$")

    def test_the_queue_has_no_default(self):
        with self.assertRaises(TypeError):
            rc.send_control_message(azure(lambda args: (0, SECRET + "\n", ""), lambda url, headers, body: (201, b"")), ACCOUNT, "watch", "a" * 32)

    def test_a_message_that_nobody_takes_does_not_stay_for_a_week(self):
        ((url, _, _),) = self.put()
        self.assertIn("messagettl=3600", url)
        self.assertEqual(rc.MESSAGE_TTL_SECONDS, 3600)

    def test_the_token_is_asked_for_the_storage_audience_only(self):
        asked = []

        def runner(args):
            asked.append(args)
            return 0, SECRET + "\n", ""

        rc.send_control_message(azure(runner, lambda *a: (201, b"")), ACCOUNT, "watch", "b" * 32, queue="a-control-queue")
        self.assertEqual(asked, [["account", "get-access-token", "--resource", "https://storage.azure.com/", "--query", "accessToken", "--output", "tsv", "--only-show-errors"]])

    def test_a_created_message_is_the_only_answer_that_is_taken(self):
        self.put(status=201)
        for status in (200, 202, 204, 400, 401, 403, 404, 409, 500, 503):
            with self.assertRaises(rc.Problem, msg=status) as raised:
                self.put(status=status)
            self.assertIn(str(status), str(raised.exception))

    def test_a_refusal_says_the_status_the_code_and_the_first_line_of_the_message_and_never_the_token(self):
        answer = ('<?xml version="1.0" encoding="utf-8"?><Error><Code>AuthorizationPermissionMismatch</Code><Message>This request is not authorized to perform this operation '
                  'using this permission.\nRequestId:0f0f0f0f\nTime:2026-11-08T00:00:00.0000000Z</Message></Error>').encode("utf-8")
        with self.assertRaises(rc.Problem) as raised:
            self.put(status=403, answer=answer)
        message = str(raised.exception)
        self.assertIn("answered 403", message)
        self.assertIn("AuthorizationPermissionMismatch: This request is not authorized to perform this operation using this permission.", message)
        self.assertIn("no Storage Queue Data Contributor role on the queue yet", message)
        self.assertNotIn("RequestId", message)
        self.assertNotIn(SECRET, message)

    def test_a_refusal_that_echoes_the_token_does_not_show_it(self):
        with self.assertRaises(rc.Problem) as raised:
            self.put(status=401, answer=f"<Error><Code>InvalidAuthenticationInfo</Code><Message>Bad token {SECRET}</Message></Error>".encode("utf-8"))
        self.assertIn("401", str(raised.exception))
        self.assertIn("the token was not accepted by the Queue service", str(raised.exception))
        self.assertNotIn(SECRET, str(raised.exception))

    def test_a_queue_that_is_not_there_says_which_action_makes_it(self):
        with self.assertRaises(rc.Problem) as raised:
            self.put(status=404, answer=b"<Error><Code>QueueNotFound</Code><Message>The specified queue does not exist.</Message></Error>")
        self.assertIn("QueueNotFound: The specified queue does not exist.", str(raised.exception))
        self.assertIn("the action cases makes it", str(raised.exception))

    def test_an_answer_that_is_not_xml_is_said_in_one_short_line(self):
        with self.assertRaises(rc.Problem) as raised:
            self.put(status=500, answer=b"upstream\nsecond line")
        self.assertIn("500: upstream", str(raised.exception))
        self.assertNotIn("second line", str(raised.exception))

    def test_a_queue_that_cannot_be_reached_is_a_problem_and_not_a_traceback(self):
        for raised in (urllib.error.URLError("[Errno -2] Name or service not known"), OSError("timed out"), http.client.RemoteDisconnected("closed")):
            with self.assertRaises(rc.Problem, msg=repr(raised)) as caught:
                self.put(raises=raised)
            self.assertIn("the control message could not be sent", str(caught.exception))
            self.assertNotIn(SECRET, str(caught.exception))

    def test_a_bad_queue_name_or_account_is_refused_before_a_token_is_asked_for_or_anything_is_sent(self):
        asked, posts = [], []

        def runner(args):
            asked.append(args)
            return 0, SECRET + "\n", ""

        for bad in ("", "a", "ab", "A-queue", "-queue", "queue-", "a--b", "a_b", "a" * 64, "q/x", "q?x", "q x"):
            with mock.patch.dict(os.environ, ENV), self.assertRaises(rc.Problem, msg=bad):
                rc.send_control_message(azure(runner, lambda *a: posts.append(a) or (201, b"")), ACCOUNT, "watch", "a" * 32, queue=bad)
        with mock.patch.dict(os.environ, ENV), self.assertRaises(rc.Problem):
            rc.send_control_message(azure(runner, lambda *a: posts.append(a) or (201, b"")), "not an account", "watch", "a" * 32, queue="a-control-queue")
        self.assertEqual(posts, [])
        self.assertEqual(asked, [], "no token is asked for either")

    def test_a_queue_name_that_azure_accepts_is_accepted(self):
        for good in ("cases-control", "abc", "a1b", "q" * 63, "a-b-c"):
            self.put(queue=good)

    def test_only_a_github_actions_run_may_send(self):
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": ""}):
            with self.assertRaises(rc.Problem) as raised:
                rc.only_in_actions()
        self.assertIn("only a GitHub Actions run may do that", str(raised.exception))
        with mock.patch.dict(os.environ, ENV):
            rc.only_in_actions()


class ReadingTheTelemetryThroughTheDataPlane(unittest.TestCase):
    """--query-via data-plane: the telemetry is read from the data plane of Application Insights, which keeps working when the component is private (docs/proposals/07-private-by-default.md)."""

    def go(self, answer, component_answer=DEFAULT, data_token_fails=False):
        """One query through the data plane. `answer` is what the data plane says: a document, a (status, body) pair or an exception to raise. `seen` says what was asked."""
        seen = {"posts": [], "components": [], "tokens": []}

        def runner(args):
            if args[:2] == ["account", "get-access-token"]:
                resource = args[args.index("--resource") + 1]
                seen["tokens"].append(resource)
                if resource == rc.DATA_PLANE and data_token_fails:
                    return 1, "", "ERROR: AADSTS500011 no such resource\nthe second line"
                return 0, (DATA_TOKEN if resource == rc.DATA_PLANE else SECRET) + "\n", ""
            seen["components"].append(args)
            document = component() if component_answer is DEFAULT else component_answer
            if document is Exception:
                return 1, "", "ERROR: (AuthorizationFailed) no right\nthe second line"
            return 0, json.dumps(document), ""

        def post(url, headers, body):
            seen["posts"].append((url, headers, body))
            if isinstance(answer, BaseException):
                raise answer
            status, document = answer if isinstance(answer, tuple) else (200, answer)
            return status, document if isinstance(document, bytes) else json.dumps(document).encode("utf-8")

        through = azure(runner, post)
        through.query_via = "data-plane"
        return through, seen

    def test_the_query_goes_to_the_app_endpoint_of_the_component_with_a_token_for_that_resource(self):
        through, seen = self.go(rows_of("one", "two"))
        rows = rc.query_telemetry(through, INSIGHTS, "traces | take 2")
        self.assertEqual(rows, [["2026-11-04T13:01:00Z", "one"], ["2026-11-04T13:01:00Z", "two"]])
        ((url, headers, body),) = seen["posts"]
        self.assertEqual(url, f"https://api.applicationinsights.io/v1/apps/{APP_ID}/query")
        self.assertEqual(headers["Authorization"], f"Bearer {DATA_TOKEN}")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(json.loads(body), {"query": "traces | take 2"})
        self.assertEqual(seen["tokens"], ["https://api.applicationinsights.io"], "the audience of the data plane, asked for when a query is made")

    def test_the_application_id_is_read_once_through_resource_manager(self):
        through, seen = self.go(rows_of("one"))
        rc.query_telemetry(through, INSIGHTS, "traces | take 1")
        rc.query_telemetry(through, INSIGHTS, "traces | take 1")
        (read,) = seen["components"]
        self.assertEqual(read[:6], ["rest", "--method", "get", "--url", f"https://management.azure.com{INSIGHTS}?api-version=2020-02-02", "--only-show-errors"])
        self.assertEqual(len(seen["posts"]), 2)

    def test_a_component_without_an_application_id_is_a_problem_before_anything_is_sent(self):
        for answer in ({}, {"properties": {}}, {"properties": {"AppId": ""}}, {"properties": {"AppId": 5}}, {"properties": {"AppId": "not-a-guid"}},
                       {"properties": {"AppId": APP_ID + "/../x"}}, {"properties": {"AppId": APP_ID + "\n"}}, {"properties": {"AppId": APP_ID + "?x=1"}},
                       {"properties": "x"}, ["x"], None):
            through, seen = self.go(rows_of("one"), component_answer=answer)
            with self.assertRaises(rc.Problem, msg=answer) as raised:
                rc.query_telemetry(through, INSIGHTS, "traces | take 1")
            self.assertIn("gives the component no Application ID", str(raised.exception))
            self.assertIn("--insights", str(raised.exception))
            self.assertEqual(seen["posts"], [], answer)

    def test_a_component_that_cannot_be_read_is_a_problem_before_anything_is_sent(self):
        through, seen = self.go(rows_of("one"), component_answer=Exception)
        with self.assertRaises(rc.Problem) as raised:
            rc.query_telemetry(through, INSIGHTS, "traces | take 1")
        self.assertIn("get appi-example failed: ERROR: (AuthorizationFailed) no right", str(raised.exception))
        self.assertNotIn("second line", str(raised.exception))
        self.assertEqual(seen["posts"], [])

    def test_a_malformed_answer_is_a_problem(self):
        for body, why in ((b"<html>please sign in</html>", "is not JSON"), (b"", "is not JSON"), (b"\xff\xfe", "is not JSON"), (b"[]", "is not a query result"),
                          (b"{}", "is not a query result"), (b'{"tables": "x"}', "is not a query result"), (b'{"tables": [5]}', "is not a query result"),
                          (b'{"tables": [{"rows": "x"}]}', "is not a query result"), (b'{"tables": [{"rows": [5]}]}', "is not a query result"),
                          (b'{"tables": [{"rows": null}]}', "is not a query result")):
            through, _ = self.go((200, body))
            with self.assertRaises(rc.Problem, msg=body) as raised:
                rc.query_telemetry(through, INSIGHTS, "traces | take 1")
            self.assertIn(f"the data-plane answer {why}", str(raised.exception), body)

    def test_an_answer_without_rows_is_no_rows_and_not_a_malformed_one(self):
        for empty in ({"tables": []}, {"tables": [{"name": "PrimaryResult", "columns": [], "rows": []}]}, {"tables": [{"columns": []}]}):
            through, _ = self.go(empty)
            self.assertEqual(rc.query_telemetry(through, INSIGHTS, "traces | take 1"), [], empty)

    def test_a_403_names_the_likely_cause_and_never_shows_the_token(self):
        refused = (403, {"error": {"code": "InsufficientAccessError", "message": f"The provided credentials have insufficient access. {DATA_TOKEN}\nsecond line"}})
        through, _ = self.go(refused)
        with self.assertRaises(rc.Problem) as raised:
            rc.query_telemetry(through, INSIGHTS, "traces | take 1")
        message = str(raised.exception)
        self.assertIn("answered 403", message)
        self.assertIn("no Reader or Monitoring Reader role on the component or above it", message)
        self.assertIn("a new role takes minutes to apply", message)
        self.assertIn("[token hidden]", message)
        for shown in (DATA_TOKEN, SECRET, "second line"):
            self.assertNotIn(shown, message)

    def test_every_other_failure_is_a_problem_too(self):
        failures = (((401, {"error": {"message": "bad token"}}), "answered 401 (the token was not accepted by the Application Insights API): bad token"),
                    ((404, b"not found"), "answered 404: not found"), ((429, b""), "answered 429"), ((500, b"boom"), "answered 500: boom"),
                    ((503, b"<html>unavailable</html>"), "answered 503: <html>unavailable</html>"),
                    (urllib.error.URLError("getaddrinfo failed"), "could not be sent: URLError: <urlopen error getaddrinfo failed>"),
                    (ConnectionResetError("reset by peer"), "could not be sent: ConnectionResetError: reset by peer"),
                    (http.client.RemoteDisconnected("closed"), "could not be sent: RemoteDisconnected: closed"),
                    (TimeoutError("timed out"), "could not be sent: TimeoutError: timed out"))
        for answer, expected in failures:
            through, _ = self.go(answer)
            with self.assertRaises(rc.Problem, msg=answer) as raised:
                rc.query_telemetry(through, INSIGHTS, "traces | take 1")
            self.assertIn(f"the data-plane query {expected}", str(raised.exception), answer)

    def test_no_token_for_the_data_plane_is_a_problem_without_the_second_line_and_nothing_is_sent(self):
        through, seen = self.go(rows_of("one"), data_token_fails=True)
        with self.assertRaises(rc.Problem) as raised:
            rc.query_telemetry(through, INSIGHTS, "traces | take 1")
        self.assertIn("no token for https://api.applicationinsights.io: ERROR: AADSTS500011 no such resource", str(raised.exception))
        self.assertNotIn("second line", str(raised.exception))
        self.assertEqual(seen["posts"], [])

    def test_the_rows_have_the_shape_that_resource_manager_gives(self):
        document = rows_of("one")

        def runner(args):
            if args[:2] == ["account", "get-access-token"]:
                return 0, DATA_TOKEN + "\n", ""
            return 0, json.dumps(document if "/query?" in args[args.index("--url") + 1] else component()), ""

        through_arm = azure(runner)
        through_data_plane = azure(runner, lambda url, headers, body: (200, json.dumps(document).encode("utf-8")))
        through_data_plane.query_via = "data-plane"
        self.assertEqual(rc.query_telemetry(through_data_plane, INSIGHTS, "traces | take 1"), rc.query_telemetry(through_arm, INSIGHTS, "traces | take 1"))
        self.assertEqual(rc.query_telemetry(through_data_plane, INSIGHTS, "traces | take 1"), document["tables"][0]["rows"])

    def test_the_default_is_the_resource_manager_and_the_data_plane_is_not_touched(self):
        asked = []

        def runner(args):
            asked.append(args)
            return 0, json.dumps(rows_of("one")), ""

        sent = []
        through = azure(runner, lambda *a: sent.append(a) or (200, b"{}"))
        self.assertEqual(through.query_via, "arm")
        self.assertEqual(rc.query_telemetry(through, INSIGHTS, "traces | take 1"), [["2026-11-04T13:01:00Z", "one"]])
        self.assertEqual(sent, [])
        (call,) = asked
        self.assertEqual(call[call.index("--url") + 1], f"https://management.azure.com{INSIGHTS}/query?api-version=2018-04-20")

    def test_the_option_takes_one_of_two_values_and_the_application_id_of_a_private_component_is_read_before_anything_else(self):
        self.assertEqual(rc.QUERY_VIA, ("arm", "data-plane"))
        with self.assertRaises(rc.Problem):
            rc.choose_query_path(azure(lambda args: (0, "{}", "")), "other", INSIGHTS)
        through, seen = self.go(rows_of("one"))
        out = io.StringIO()
        with redirect_stdout(out):
            rc.choose_query_path(through, "data-plane", INSIGHTS)
        self.assertIn("The telemetry is read through the data plane of Application Insights", out.getvalue())
        self.assertEqual(len(seen["components"]), 1, "the Application ID is read first, so that a component that cannot be read stops the run before an event is sent")
        arm = azure(lambda args: (0, "{}", ""))
        rc.choose_query_path(arm, "arm", INSIGHTS)
        self.assertEqual(arm.query_via, "arm")

    def test_the_diagnostics_are_read_the_same_way_and_say_when_there_is_nothing(self):
        through, _ = self.go({"tables": [{"rows": []}]})
        self.assertEqual(rc.problem_lines(through, INSIGHTS), ["  nothing: the function app wrote no warning and no exception in the last hour"])
        through, _ = self.go(rows_of("The Python worker failed to index functions\nand a second line"))
        lines = rc.problem_lines(through, INSIGHTS)
        self.assertTrue(any("The Python worker failed to index functions" in line for line in lines))
        self.assertFalse(any("second line" in line for line in lines))
        through, _ = self.go((403, b'{"error": {"message": "no access to this resource"}}'))
        lines = rc.problem_lines(through, INSIGHTS)
        self.assertTrue(any("could not be read (the data-plane query answered 403" in line and "no access to this resource" in line for line in lines), lines)

    def test_the_host_the_api_version_and_the_audience_are_the_documented_ones(self):
        self.assertEqual(rc.DATA_PLANE, "https://api.applicationinsights.io")
        self.assertEqual(rc.COMPONENT_API, "2020-02-02")
        self.assertEqual(rc.QUERY_API, "2018-04-20", "the Resource Manager's own query API did not change")


class WhatAServiceSays(unittest.TestCase):
    def test_what_said_does(self):
        self.assertEqual(rc.said(b"", "t"), "")
        self.assertEqual(rc.said(None, "t"), "")
        self.assertEqual(rc.said(b'{"error": {"message": "no\\nsecond"}}', "t"), "no")
        self.assertEqual(rc.said(b'{"error": "text"}', ""), '{"error": "text"}')
        self.assertEqual(rc.said("a token-1 b", "token-1"), "a [token hidden] b")
        self.assertEqual(rc.said("a token-1 b", ""), "a token-1 b", "an empty token hides nothing")
        self.assertEqual(rc.said("x\x1b[31m y", ""), "x [31m y")
        self.assertEqual(rc.said(b"\xff", ""), "\ufffd")
        long = rc.said("x" * 500, "")
        self.assertEqual((len(long), long.endswith("...")), (160, True))


class NoRedirects(unittest.TestCase):
    def test_a_redirect_is_not_followed_so_the_token_is_not_sent_on(self):
        request = urllib.request.Request("https://api.applicationinsights.io/v1/apps/x/query", data=b"{}", headers={"Authorization": f"Bearer {DATA_TOKEN}"}, method="POST")
        for code in (301, 302, 303, 307, 308):
            self.assertIsNone(rc.NoRedirect().redirect_request(request, io.BytesIO(b""), code, "moved", {}, "https://elsewhere.example/"), code)
        handlers = rc.OPENER.handlers
        self.assertTrue(any(isinstance(h, rc.NoRedirect) for h in handlers))
        self.assertFalse(any(type(h) is urllib.request.HTTPRedirectHandler for h in handlers), "the default redirect handler is replaced")

    def test_post_http_gives_a_redirect_and_an_error_back_as_an_answer(self):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *stop):
                return False

            def read(self):
                return b"fine"

        class Opener:
            def __init__(self, raises=None):
                self.raises = raises

            def open(self, request, timeout):
                self.timeout = timeout
                if self.raises:
                    raise self.raises
                return Response()

        moved = urllib.error.HTTPError("https://x.example/", 307, "Temporary Redirect", {}, io.BytesIO(b"moved"))
        refused = urllib.error.HTTPError("https://x.example/", 403, "Forbidden", {}, io.BytesIO(b"no"))
        for opener, expected in ((Opener(), (200, b"fine")), (Opener(moved), (307, b"moved")), (Opener(refused), (403, b"no"))):
            with mock.patch.object(rc, "OPENER", opener):
                self.assertEqual(rc.post_http("https://x.example/", {}, b"{}"), expected)
            self.assertEqual(opener.timeout, 60)


class NothingReadsTheStoreAndNothingOfTheUsageRecordingIsLeft(unittest.TestCase):
    def setUp(self):
        source = (ROOT / "tools" / "check-helpers.py").read_text(encoding="utf-8")
        self.code = re.sub(r'""".*?"""', "", source, flags=re.S)

    def test_the_helpers_make_no_call_to_cosmos_db_and_ask_for_no_key(self):
        for word in ("documents.azure.com", "cosmos.azure.com", "listKeys", "listConnectionStrings", "primaryKey", "SharedAccessSignature", "AccountKey"):
            self.assertNotIn(word, self.code, word)
        for word in ("x-api-key", "api_key", "apikey", "demo_key"):
            self.assertNotIn(word, self.code.lower(), "the API key of Application Insights queries is retired, and no key is used (AGENTS.md rule 23)")
        literal = set(re.findall(r'token\(\s*["\']([^"\']+)["\']', self.code))
        named = {getattr(rc, name) for name in re.findall(r"token\(\s*([A-Z_]+)\s*\)", self.code)}
        self.assertEqual(sorted(literal | named), ["https://api.applicationinsights.io", "https://management.azure.com", "https://storage.azure.com/"])

    def test_nothing_of_the_usage_recording_is_in_the_code_and_no_file_of_it_is_left(self):
        for word in ("usage-control", "ai-usage", "pii-usage", "usage_job_result", "TIMED_JOBS", "FUNCTIONS =", "RESULT_PREFIX"):
            self.assertNotIn(word, self.code, word)
        self.assertFalse((ROOT / "tools" / "recording-check.py").exists(), "the checker of the usage recording was removed on 2026-11-07: its shared helpers are tools/check-helpers.py")
        self.assertFalse((ROOT / "tools" / "tests" / "test_recording_check.py").exists())


if __name__ == "__main__":
    unittest.main()
