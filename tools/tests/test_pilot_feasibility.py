import datetime as dt
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

TOOL = Path(__file__).resolve().parents[1] / "pilot-feasibility.py"
spec = importlib.util.spec_from_file_location("pilot_feasibility", TOOL)
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)

SUB = "/subscriptions/11111111-2222-3333-4444-555555555555"
TODAY = dt.date(2026, 11, 3)

MCA_CSV = (
    "date,ResourceId,costInBillingCurrency,billingCurrencyCode,chargeType,pricingModel,effectivePrice,PayGPrice,paygCostInBillingCurrency,benefitName\n"
    "2026-09-01,/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1,60.00,EUR,Usage,OnDemand,0.06,0.10,100.00,\n"
    "2026-09-02,/subscriptions/s/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/st1,30.00,EUR,Usage,Reservation,0.03,0.03,30.00,Reservation A\n"
    "2026-09-03,,10.00,EUR,Purchase,,,,,\n"
)
EA_CSV = (
    "Date,InstanceName,Cost,BillingCurrency,UnitPrice,EffectivePrice\n"
    "09/01/2026,vm1,50,USD,0.10,0.10\n"
    "09/02/2026,vm2,50,USD,0.10,0.10\n"
)
FOCUS_CSV = (
    "BilledCost,BillingCurrency,ResourceId,ChargeCategory,PricingCategory,CommitmentDiscountName,ListCost,ListUnitPrice,x_EffectiveUnitPrice\n"
    "50.00,EUR,/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1,Usage,Standard,,100.00,0.10,0.05\n"
    "30.00,EUR,/subscriptions/s/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/st1,Usage,Committed,Reservation A,30.00,0.03,0.03\n"
    "10.00,EUR,,Purchase,Standard,,10.00,,\n"
)


def query_response(rows, currency=True):
    columns = [{"name": "Cost", "type": "Number"}] + ([{"name": "Currency", "type": "String"}] if currency else [])
    return 200, {}, json.dumps({"properties": {"columns": columns, "rows": rows}}).encode("utf-8")


class FakeTransport(pf.Transport):
    def __init__(self, routes):
        super().__init__(sleep=lambda s: None)
        self.routes, self.calls = list(routes), []

    def request(self, method, url, body=None, *, auth=True):
        self.calls.append((method, url, body, auth))
        for i, (m, fragment, response) in enumerate(self.routes):
            if m == method and fragment in url:
                self.routes.pop(i)
                return response
        raise AssertionError(f"no scripted answer for {method} {url}")


class Ok(io.BytesIO):
    status = 200

    def __init__(self, data=b"", headers=None, status=200):
        super().__init__(data)
        self.status, self.headers = status, headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class ScopeAndMonthTests(unittest.TestCase):
    def test_a_closed_month(self):
        self.assertEqual(pf.month_bounds("2026-09", TODAY), ("2026-09-01", "2026-09-30"))
        self.assertEqual(pf.month_bounds("2025-12", TODAY), ("2025-12-01", "2025-12-31"))

    def test_an_open_or_future_month_is_refused(self):
        for month in ("2026-11", "2026-12"):
            with self.assertRaises(pf.Problem):
                pf.month_bounds(month, TODAY)

    def test_a_month_closes_on_the_sixth_day_after_it_ends(self):
        with self.assertRaises(pf.Problem) as raised:
            pf.month_bounds("2026-10", TODAY)
        self.assertIn("sixth day", str(raised.exception))
        with self.assertRaises(pf.Problem):
            pf.month_bounds("2026-10", dt.date(2026, 11, 5))
        self.assertEqual(pf.month_bounds("2026-10", dt.date(2026, 11, 6)), ("2026-10-01", "2026-10-31"))

    def test_a_malformed_month_is_refused(self):
        for month in ("2026-13", "26-09", "september"):
            with self.assertRaises(pf.Problem):
                pf.month_bounds(month, TODAY)

    def test_scopes(self):
        billing = "/providers/Microsoft.Billing/billingAccounts/abc"
        for scope in (SUB, SUB + "/resourceGroups/rg-web", "/providers/Microsoft.Billing/billingAccounts/123:456_2019-01-01",
                      billing + "/billingProfiles/def", billing + "/billingProfiles/def/invoiceSections/ghi",
                      billing + "/departments/1", billing + "/enrollmentAccounts/2", billing + "/customers/3",
                      "/providers/Microsoft.Billing/departments/12345", "/providers/Microsoft.Billing/enrollmentAccounts/1234"):
            self.assertEqual(pf.check_scope(scope + "/"), scope)
        for scope in ("", "/", "subscriptions/x", "/subscriptions/not-a-guid", "/providers/Microsoft.Compute/virtualMachines/vm",
                      billing + "/invoiceSections/ghi", billing + "/departments", "/providers/Microsoft.Management/managementGroups/mg"):
            with self.assertRaises(pf.Problem):
                pf.check_scope(scope)


class ReadLinesTests(unittest.TestCase):
    def test_a_customer_agreement_file(self):
        stats = pf.read_lines(MCA_CSV)
        self.assertEqual(stats["lines"], 3)
        self.assertEqual(stats["resources"], 2)
        self.assertAlmostEqual(stats["totals"]["EUR"], 100.0)
        self.assertAlmostEqual(stats["unassigned_cost"], 10.0)
        self.assertAlmostEqual(stats["by_charge_type"]["Purchase"], 10.0)
        self.assertAlmostEqual(stats["price_evidence"]["cost_with_a_benefit"], 30.0)
        self.assertEqual(stats["price_evidence"]["lines_priced_below_payg"], 1)
        self.assertEqual(stats["price_evidence"]["lines_with_both_prices"], 2)

    def test_an_enterprise_agreement_file_with_other_column_names(self):
        stats = pf.read_lines(EA_CSV)
        self.assertEqual(stats["resources"], 2)
        self.assertEqual(stats["totals"], {"USD": 100.0})
        self.assertIsNone(stats["price_evidence"]["effective_to_payg_ratio"])

    def test_a_focus_export(self):
        stats = pf.read_lines(FOCUS_CSV)
        self.assertEqual(stats["totals"], {"EUR": 90.0})
        self.assertEqual(stats["resources"], 2)
        self.assertAlmostEqual(stats["unassigned_cost"], 10.0)
        self.assertAlmostEqual(stats["by_charge_type"]["Purchase"], 10.0)
        self.assertAlmostEqual(stats["by_pricing_model"]["Committed"], 30.0)
        self.assertAlmostEqual(stats["price_evidence"]["cost_with_a_benefit"], 30.0)
        self.assertEqual(stats["price_evidence"]["lines_priced_below_payg"], 1)
        for key in ("cost", "currency", "resource", "payg", "effective_price", "payg_price", "pricing_model", "charge_type", "benefit"):
            self.assertIn(key, stats["columns_found"])

    def test_a_file_without_a_cost_column(self):
        with self.assertRaises(pf.Problem):
            pf.read_lines("date,resourceId,currency\n2026-09-01,x,EUR\n")

    def test_a_file_without_a_resource_or_a_currency_column_is_refused(self):
        with self.assertRaises(pf.Problem) as raised:
            pf.read_lines("date,cost,currency\n2026-09-01,100,EUR\n")
        self.assertIn("resource column", str(raised.exception))
        with self.assertRaises(pf.Problem) as raised:
            pf.read_lines("date,cost,resourceId\n2026-09-01,100,/r/1\n")
        self.assertIn("currency column", str(raised.exception))

    def test_a_cost_that_is_not_a_number_names_its_line(self):
        with self.assertRaises(pf.Problem) as raised:
            pf.read_lines("cost,currency,resourceId\n5,EUR,/r/1\nabc,EUR,/r/2\n")
        self.assertIn("line 3", str(raised.exception))

    def test_an_empty_file(self):
        with self.assertRaises(pf.Problem):
            pf.read_lines("date,cost\n")

    def test_price_basis_evidence_says_what_it_sees(self):
        notes = pf.price_basis_evidence(pf.read_lines(MCA_CSV))
        self.assertTrue(any("pay-as-you-go cost" in n for n in notes))
        self.assertTrue(any("1 of 2 lines" in n for n in notes))
        self.assertTrue(any("benefit" in n for n in notes))
        self.assertIn("cannot be read", pf.price_basis_evidence(pf.read_lines("cost,currency,resourceId\n5,EUR,/r/1\n"))[0])


class ReconcileTests(unittest.TestCase):
    def test_inside_the_tolerance(self):
        result = pf.reconcile({"EUR": 100.0}, {"EUR": 100.9}, 1.0)
        self.assertTrue(result["pass"])
        self.assertEqual(result["difference"], 0.9)

    def test_outside_the_tolerance(self):
        self.assertFalse(pf.reconcile({"EUR": 100.0}, {"EUR": 102.0}, 1.0)["pass"])

    def test_more_than_one_currency_cannot_pass(self):
        result = pf.reconcile({"EUR": 50.0, "USD": 50.0}, {"EUR": 50.0, "USD": 50.0}, 1.0)
        self.assertFalse(result["pass"])
        self.assertIn("currency", result["reason"])

    def test_a_missing_total_cannot_pass(self):
        self.assertFalse(pf.reconcile({"EUR": 5.0}, {"EUR": 0.0}, 1.0)["pass"])
        self.assertTrue(pf.reconcile({"EUR": 0.0}, {"EUR": 0.0}, 1.0)["pass"])


class QueryTests(unittest.TestCase):
    def test_the_total_is_read_per_currency(self):
        transport = FakeTransport([("POST", "/query?", query_response([[60.0, "EUR"], [40.0, "EUR"]]))])
        self.assertEqual(pf.query_total(transport, SUB, "2026-09-01", "2026-09-30"), {"EUR": 100.0})
        method, url, body, auth = transport.calls[0]
        self.assertIn(f"{SUB}/providers/Microsoft.CostManagement/query", url)
        self.assertEqual(body["type"], "ActualCost")
        self.assertEqual(body["timePeriod"]["from"][:10], "2026-09-01")

    def test_a_missing_currency_column_is_unknown(self):
        transport = FakeTransport([("POST", "/query?", query_response([[5.0]], currency=False))])
        self.assertEqual(pf.query_total(transport, SUB, "2026-09-01", "2026-09-30"), {"unknown": 5.0})

    def test_a_forbidden_answer_names_the_role(self):
        transport = FakeTransport([("POST", "/query?", (403, {}, b"no"))])
        with self.assertRaises(pf.Problem) as raised:
            pf.query_total(transport, SUB, "2026-09-01", "2026-09-30")
        self.assertIn("Cost Management Reader", str(raised.exception))

    def test_every_page_is_followed_and_summed(self):
        next_link = f"{pf.ARM}{SUB}/providers/Microsoft.CostManagement/query?api-version=2023-11-01&$skiptoken=abc"
        first = (200, {}, json.dumps({"properties": {"nextLink": next_link, "columns": [{"name": "Cost"}, {"name": "Currency"}],
                                                      "rows": [[60.0, "EUR"]]}}).encode("utf-8"))
        transport = FakeTransport([("POST", "/query?", first), ("POST", "skiptoken=abc", query_response([[40.0, "EUR"]]))])
        self.assertEqual(pf.query_total(transport, SUB, "2026-09-01", "2026-09-30"), {"EUR": 100.0})
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(transport.calls[0][2], transport.calls[1][2])

    def test_no_content_means_no_cost(self):
        transport = FakeTransport([("POST", "/query?", (204, {}, b""))])
        self.assertEqual(pf.query_total(transport, SUB, "2026-09-01", "2026-09-30"), {})

    def test_an_endless_chain_of_pages_stops(self):
        page = (200, {}, json.dumps({"properties": {"nextLink": f"{pf.ARM}/more?x=1", "columns": [{"name": "Cost"}], "rows": [[1.0]]}}).encode("utf-8"))
        transport = FakeTransport([("POST", "query?", page)] + [("POST", "more", page) for _ in range(80)])
        with self.assertRaises(pf.Problem) as raised:
            pf.query_total(transport, SUB, "2026-09-01", "2026-09-30")
        self.assertIn("pages", str(raised.exception))


class DetailsApiTests(unittest.TestCase):
    def routes(self):
        manifest = {"status": "Completed", "manifest": {"blobs": [{"blobLink": "https://blob.example/a?sig=1"}, {"blobLink": "https://blob.example/b?sig=2"}]}}
        return [
            ("POST", "generateCostDetailsReport", (202, {"Location": f"{pf.ARM}{SUB}/providers/Microsoft.CostManagement/costDetailsOperationStatus/op1?api-version=2022-05-01", "Retry-After": "7"}, b"")),
            ("GET", "costDetailsOperationStatus", (202, {"Retry-After": "3"}, b"")),
            ("GET", "costDetailsOperationStatus", (200, {}, json.dumps(manifest).encode("utf-8"))),
            ("GET", "blob.example/a", (200, {}, b"cost,ResourceId,BillingCurrencyCode\n10,/r/1,EUR\n")),
            ("GET", "blob.example/b", (200, {}, b"cost,ResourceId,BillingCurrencyCode\n20,/r/2,EUR\n")),
        ]

    def test_the_report_is_requested_polled_and_joined(self):
        transport = FakeTransport(self.routes())
        slept = []
        transport.sleep = slept.append
        text = pf.details_api_csv(transport, SUB, "2026-09-01", "2026-09-30")
        self.assertEqual(text.splitlines(), ["cost,ResourceId,BillingCurrencyCode", "10,/r/1,EUR", "20,/r/2,EUR"])
        self.assertEqual(slept, [7.0, 3.0])
        body = transport.calls[0][2]
        self.assertEqual(body, {"metric": "ActualCost", "timePeriod": {"start": "2026-09-01", "end": "2026-09-30"}})

    def test_the_token_is_never_sent_to_a_download_link(self):
        transport = FakeTransport(self.routes())
        pf.details_api_csv(transport, SUB, "2026-09-01", "2026-09-30")
        for method, url, body, auth in transport.calls:
            if "blob.example" in url:
                self.assertFalse(auth)
            else:
                self.assertTrue(auth)

    def test_a_compressed_part_is_read(self):
        import gzip
        routes = self.routes()
        routes[3] = ("GET", "blob.example/a", (200, {}, gzip.compress(b"cost,ResourceId,BillingCurrencyCode\n10,/r/1,EUR\n")))
        text = pf.details_api_csv(FakeTransport(routes), SUB, "2026-09-01", "2026-09-30")
        self.assertIn("10,/r/1,EUR", text)

    def test_a_scope_the_api_does_not_serve_points_to_the_file_route(self):
        transport = FakeTransport([("POST", "generateCostDetailsReport", (400, {}, b"not supported"))])
        with self.assertRaises(pf.Problem) as raised:
            pf.details_api_csv(transport, SUB, "2026-09-01", "2026-09-30")
        self.assertIn("--file", str(raised.exception))

    def test_a_report_that_never_completes_stops(self):
        routes = [("POST", "generateCostDetailsReport", (202, {"Location": "https://x.example/op", "Retry-After": "1"}, b""))]
        routes += [("GET", "x.example/op", (202, {"Retry-After": "1"}, b"")) for _ in range(3)]
        transport = FakeTransport(routes)
        with self.assertRaises(pf.Problem):
            pf.details_api_csv(transport, SUB, "2026-09-01", "2026-09-30", poll_limit=2)

    def test_a_failed_report_or_no_data_stops_at_once(self):
        for state, words in (("Failed", "failed"), ("NoDataFound", "no cost data")):
            location = {"Location": "https://x.example/op", "Retry-After": "1"}
            routes = [("POST", "generateCostDetailsReport", (202, location, b"")),
                      ("GET", "x.example/op", (200, {}, json.dumps({"status": state}).encode("utf-8")))]
            transport = FakeTransport(routes)
            with self.assertRaises(pf.Problem) as raised:
                pf.details_api_csv(transport, SUB, "2026-09-01", "2026-09-30")
            self.assertIn(words, str(raised.exception))
            self.assertEqual(len(transport.calls), 2)

    def test_no_content_is_no_data(self):
        for routes in ([("POST", "generateCostDetailsReport", (204, {}, b""))],
                       [("POST", "generateCostDetailsReport", (202, {"Location": "https://x.example/op"}, b"")), ("GET", "x.example/op", (204, {}, b""))]):
            with self.assertRaises(pf.Problem) as raised:
                pf.details_api_csv(FakeTransport(routes), SUB, "2026-09-01", "2026-09-30")
            self.assertIn("no cost data", str(raised.exception))

    def test_a_polling_link_off_management_azure_com_never_gets_the_token(self):
        transport = pf.Transport(token_command=[sys.executable, "-c", "print('secret-token')"], sleep=lambda s: None)
        seen = []

        def fake_urlopen(request, timeout):
            seen.append(request.full_url)
            return Ok(b"", {"Location": "https://evil.example/op", "Retry-After": "1"}, status=202)

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(pf.Problem) as raised:
                pf.details_api_csv(transport, SUB, "2026-09-01", "2026-09-30")
        self.assertIn("other than management.azure.com", str(raised.exception))
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0].startswith(pf.ARM))


class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="feasibility-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.csv = self.tmp / "lines.csv"
        self.csv.write_text(MCA_CSV, encoding="utf-8")

    def args(self, out, **kw):
        base = dict(scope=SUB, month="2026-09", file=str(self.csv), out=str(out), tolerance_pct=1.0)
        base.update(kw)
        return type("Args", (), base)()

    def run_tool(self, args, query):
        transport = FakeTransport([("POST", "/query?", query)])
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            code = pf.run(args, transport, TODAY)
        return code, out.getvalue()

    def test_a_matching_month_passes_and_the_record_names_what_a_person_must_add(self):
        out = self.tmp / "record.json"
        code, text = self.run_tool(self.args(out), query_response([[100.0, "EUR"]]))
        self.assertEqual(code, 0)
        self.assertIn("PASS", text)
        record = json.loads(out.read_text(encoding="utf-8"))
        self.assertTrue(record["passed_by_the_tool"])
        self.assertEqual(record["reconciliation"]["difference"], 0.0)
        self.assertEqual(record["lines"]["unassigned_share"], 0.1)
        self.assertEqual(set(record["to_confirm_by_name"]), {"price_basis", "pilot_owner", "access", "hub", "region", "model_quota"})
        self.assertIsNone(record["to_confirm_by_name"]["pilot_owner"])

    def test_a_mismatch_does_not_pass(self):
        code, text = self.run_tool(self.args(self.tmp / "record.json"), query_response([[130.0, "EUR"]]))
        self.assertEqual(code, 1)
        self.assertIn("NOT PASSED", text)

    def test_a_file_with_no_resource_column_is_refused_and_one_with_empty_ids_cannot_pass(self):
        self.csv.write_text("date,cost,currency\n2026-09-01,100,EUR\n", encoding="utf-8")
        with self.assertRaises(pf.Problem):
            self.run_tool(self.args(self.tmp / "record.json"), query_response([[100.0, "EUR"]]))
        self.csv.write_text("date,cost,currency,resourceId\n2026-09-01,100,EUR,\n", encoding="utf-8")
        code, text = self.run_tool(self.args(self.tmp / "record.json"), query_response([[100.0, "EUR"]]))
        self.assertEqual(code, 1)
        self.assertIn("WARNING", text)

    def test_a_month_that_matches_but_is_nearly_all_unassigned_passes_with_a_warning_for_a_person(self):
        self.csv.write_text("date,cost,currency,resourceId\n2026-09-01,1,EUR,/r/1\n2026-09-02,99,EUR,\n", encoding="utf-8")
        out = self.tmp / "record.json"
        code, text = self.run_tool(self.args(out), query_response([[100.0, "EUR"]]))
        self.assertEqual(code, 0)
        self.assertIn("WARNING: 99% of the cost is on lines with no resource id", text)
        self.assertEqual(len(json.loads(out.read_text(encoding="utf-8"))["warnings"]), 1)

    def test_the_record_is_never_written_inside_the_repository(self):
        inside = pf.ROOT / "records" / "feasibility.json"
        with self.assertRaises(pf.Problem) as raised:
            pf.run(self.args(inside), FakeTransport([]), TODAY)
        self.assertIn("inside this repository", str(raised.exception))
        self.assertFalse(inside.exists())

    def test_the_local_folder_takes_a_record_only_while_git_ignores_it(self):
        with mock.patch.object(pf, "ROOT", self.tmp.resolve()):
            record = self.tmp / "local" / "records" / "feasibility.json"
            pf.refuse_where_git_tracks(record, ignored=lambda path: True)
            with self.assertRaises(pf.Problem) as not_ignored:
                pf.refuse_where_git_tracks(record, ignored=lambda path: False)
            self.assertIn("does not ignore", str(not_ignored.exception))
            with self.assertRaises(pf.Problem) as elsewhere:
                pf.refuse_where_git_tracks(self.tmp / "docs" / "feasibility.json", ignored=lambda path: True)
            self.assertIn("inside this repository", str(elsewhere.exception))
            pf.refuse_where_git_tracks(self.tmp.parent / "outside.json", ignored=lambda path: False)

    @unittest.skipUnless((pf.ROOT / ".git").exists() and shutil.which("git"), "needs a git checkout")
    def test_git_ignores_the_local_folder_of_this_repository(self):
        self.assertTrue(pf.git_ignores(pf.ROOT / "local" / "records" / "feasibility.json"))
        self.assertFalse(pf.git_ignores(pf.ROOT / "docs" / "feasibility.json"))

    def test_an_open_month_is_refused_before_any_call(self):
        transport = FakeTransport([])
        with self.assertRaises(pf.Problem):
            pf.run(self.args(self.tmp / "r.json", month="2026-11"), transport, TODAY)
        self.assertEqual(transport.calls, [])

    def test_main_requires_the_scope_the_month_and_the_output(self):
        with self.assertRaises(SystemExit):
            with mock.patch("sys.stderr", io.StringIO()):
                pf.main(["--month", "2026-09"])


class TransportTests(unittest.TestCase):
    def test_the_token_comes_from_the_command_and_is_cached(self):
        transport = pf.Transport(token_command=[sys.executable, "-c", "print('tok')"])
        self.assertEqual(transport.token(), "tok")
        transport.token_command = ["does-not-exist"]
        self.assertEqual(transport.token(), "tok")

    def test_no_token_is_a_problem_that_says_what_to_do(self):
        transport = pf.Transport(token_command=[sys.executable, "-c", "import sys; sys.exit(1)"])
        with self.assertRaises(pf.Problem) as raised:
            transport.token()
        self.assertIn("az login", str(raised.exception))

    def test_a_throttled_call_waits_for_the_longest_retry_after(self):
        class Ok(io.BytesIO):
            status = 200
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        throttled = urllib.error.HTTPError("https://x", 429, "slow", {"x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after": "5",
                                                                  "x-ms-ratelimit-microsoft.costmanagement-entity-retry-after": "9"}, io.BytesIO(b""))
        outcomes = [throttled, Ok(b"{}")]
        slept = []

        def fake_urlopen(request, timeout):
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        transport = pf.Transport(token_command=[sys.executable, "-c", "print('t')"], sleep=slept.append)
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            status, _, body = transport.request("POST", f"{pf.ARM}/query", {"a": 1})
        self.assertEqual((status, body), (200, b"{}"))
        self.assertEqual(slept, [9.0])

    def test_the_token_goes_only_to_management_azure_com(self):
        transport = pf.Transport(token_command=[sys.executable, "-c", "print('secret-token')"])
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("no request may be made")):
            for url in ("https://evil.example/x", f"{pf.ARM}.evil.example/x", "http://management.azure.com/x"):
                with self.assertRaises(pf.Problem):
                    transport.request("GET", url)
            with self.assertRaises(pf.Problem):
                transport.request("GET", "http://blob.example/x", auth=False)

    def test_a_message_never_repeats_the_query_string_or_a_signature_of_a_link(self):
        message = "could not read https://acct.blob.example/c/f.csv?sv=2024&sig=SECRETSIG%3D&se=2026 and sig=ABC123 again"
        text = str(pf.Problem(message))
        self.assertNotIn("SECRETSIG", text)
        self.assertNotIn("ABC123", text)
        self.assertNotIn("?sv=", text)
        self.assertIn("https://acct.blob.example/c/f.csv", text)

    def test_an_unreachable_host_is_a_problem_without_the_query_string(self):
        transport = pf.Transport(token_command=[sys.executable, "-c", "print('t')"])
        error = urllib.error.URLError("name not resolved")
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(pf.Problem) as raised:
                transport.request("GET", "https://blob.example/a?sig=SECRETSIG", auth=False)
        self.assertNotIn("SECRETSIG", str(raised.exception))

    def test_the_az_command_is_run_without_a_shell(self):
        with mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="tok\n")
            pf.Transport(token_command=["az", "x"]).token()
        self.assertNotIn("shell", run.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
