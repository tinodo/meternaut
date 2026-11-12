"""The speed of the reads of the tools: how many calls a question to Azure costs, how many are made at the same time, and what is shared with the Watch. The estate answers with a real
pause (a few hundredths of a second), so a test sees the reads overlap; nothing here depends on how fast the machine is."""
import datetime as dt
import threading
import time
import unittest

import support  # noqa: F401 (it puts the app on the path)
from cases import toolbox as tb
from cases.arm import COST_RETRIES, Arm
from cases.http import Client, allowed_calls
from cases.redact import Redactor
from support import NOW, TOKEN
from test_toolbox import DISK, Estate, ask, row

PAUSE = 0.05


def subscription(number):
    return f"{number:08d}-1111-4222-8333-444444444444"


class Paced(Estate):
    """An estate whose cost reads take a moment and are counted as they overlap."""

    def __init__(self):
        super().__init__()
        self.cost_active = self.cost_busiest = 0

    def __call__(self, method, url, headers, data, timeout):
        if "/providers/microsoft.costmanagement/query" not in url.lower():
            return super().__call__(method, url, headers, data, timeout)
        with self.lock:
            self.cost_active += 1
            self.cost_busiest = max(self.cost_busiest, self.cost_active)
        try:
            time.sleep(PAUSE)
            return super().__call__(method, url, headers, data, timeout)
        finally:
            with self.lock:
                self.cost_active -= 1


def ten(count=10):
    estate = Paced()
    subs = [subscription(n + 1) for n in range(count)]
    for n, sub in enumerate(subs):
        estate.rows.append(row(DISK, f"d{n}", sub=sub))
        estate.cost_rows.append((sub, float(n + 1), estate.rows[-1]["id"].lower(), "Storage"))
    client = Client(allowed_calls(), Redactor(), transport=estate, sleep=lambda s: None, jitter=lambda: 0.5)
    arm = Arm(client, lambda resource: TOKEN)
    return estate, arm, subs


def cost_calls(estate):
    found = {}
    for call in estate.paths("costmanagement/query"):
        sub = call["path"].lower().split("/")[2]
        found[sub] = found.get(sub, 0) + 1
    return found


class TheReadsOfManySubscriptions(unittest.TestCase):
    def test_the_overview_of_ten_subscriptions_is_one_question_to_resource_graph_and_one_read_of_cost_for_each(self):
        estate, arm, subs = ten()
        box = tb.Toolbox(arm, tuple(subs), NOW, [])
        answer = ask(box, "estate_overview")
        self.assertEqual(len(answer["subscriptions"]), 10)
        self.assertEqual(estate.graph_names(), ["estate-types"])  # one query for all of them; it was one for each subscription
        self.assertEqual(cost_calls(estate), {sub: 1 for sub in subs})
        self.assertEqual(len(estate.calls), 1 + 10)

    def test_the_cost_reads_overlap_up_to_the_number_of_workers_and_no_more(self):
        estate, arm, subs = ten()
        box = tb.Toolbox(arm, tuple(subs), NOW, [])
        began = time.monotonic()
        ask(box, "estate_overview")
        seconds = time.monotonic() - began
        self.assertGreaterEqual(estate.cost_busiest, 2)
        self.assertLessEqual(estate.cost_busiest, tb.READ_WORKERS)
        self.assertEqual(tb.READ_WORKERS, 4)
        self.assertLess(seconds, 10 * PAUSE * 0.8, "ten reads of a twentieth of a second each, four at a time, are not read one after the other")

    def test_one_worker_reads_one_subscription_after_the_other(self):
        estate, arm, subs = ten(6)
        box = tb.Toolbox(arm, tuple(subs), NOW, [])
        box.read_workers = 1
        ask(box, "estate_overview")
        self.assertEqual(estate.cost_busiest, 1)

    def test_a_listing_reads_the_cost_of_the_subscriptions_that_have_the_type_at_the_same_time_and_once(self):
        estate, arm, subs = ten()
        box = tb.Toolbox(arm, tuple(subs), NOW, [])
        answer = ask(box, "list_resources", type=DISK)
        self.assertEqual(answer["total"], 10)
        self.assertEqual(estate.graph_names(), ["type-resources"])
        self.assertEqual(cost_calls(estate), {sub: 1 for sub in subs})
        self.assertGreaterEqual(estate.cost_busiest, 2)
        calls = len(estate.calls)
        ask(box, "list_resources", type=DISK, offset=5)
        ask(box, "estate_overview")
        ask(box, "cost_lines")
        ask(box, "describe", handle=answer["rows"][0][0])
        self.assertEqual(len(estate.calls), calls + 1)  # the one read of the counts for the overview: nothing is read twice

    def test_the_cost_lines_of_a_subscription_are_read_once_between_the_watch_and_the_tools(self):
        estate, arm, subs = ten(3)
        today = NOW.date()
        totals, currency = arm.costs(subs[0], today - dt.timedelta(days=30), today - dt.timedelta(days=1))  # what the Watch asks for
        self.assertEqual((totals, currency), ({estate.rows[0]["id"].lower(): 1.0}, "USD"))
        ask(tb.Toolbox(arm, tuple(subs), NOW, []), "estate_overview")
        self.assertEqual(cost_calls(estate), {sub: 1 for sub in subs})

    def test_two_reads_of_the_same_lines_at_the_same_moment_make_one_call(self):
        estate, arm, subs = ten(1)
        today = NOW.date()
        results = []
        threads = [threading.Thread(target=lambda: results.append(arm.cost_lines(subs[0], today - dt.timedelta(days=30), today - dt.timedelta(days=1)))) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(results), 4)
        self.assertEqual(cost_calls(estate), {subs[0]: 1})
        self.assertTrue(all(found == results[0] for found in results))

    def test_a_read_that_failed_is_not_asked_again_by_the_tools_in_the_run_but_the_memo_keeps_no_failure_for_the_watch(self):
        estate, arm, subs = ten(2)
        box = tb.Toolbox(arm, tuple(subs), NOW, [])
        estate.failures["costs"] = [500] * (2 * (1 + COST_RETRIES))  # both subscriptions are turned away at every try
        self.assertEqual(ask(box, "cost_lines")["costs"], "unavailable")
        estate.failures["costs"] = None
        before = sum(cost_calls(estate).values())
        self.assertNotIn("usd30d", ask(box, "list_resources", type=DISK)["cols"])  # the tools do not hammer a service that has just refused them
        self.assertEqual(sum(cost_calls(estate).values()), before)
        today = NOW.date()
        self.assertEqual(len(arm.cost_lines(subs[0], today - dt.timedelta(days=30), today - dt.timedelta(days=1))), 1)  # a failure is no answer, so the Watch asks again
        self.assertEqual(sum(cost_calls(estate).values()), before + 1)

    def test_every_cost_call_carries_the_header_that_gives_it_a_bucket_of_its_own(self):
        estate, arm, subs = ten(2)
        ask(tb.Toolbox(arm, tuple(subs), NOW, []), "estate_overview")
        calls = estate.paths("costmanagement/query")
        self.assertEqual(len(calls), 2)
        self.assertEqual({call["headers"].get("ClientType") for call in calls}, {"Meternaut"})

    def test_the_cost_read_asks_for_the_resource_and_the_service_and_nothing_else_of_the_estate(self):
        estate, arm, subs = ten(1)
        ask(tb.Toolbox(arm, tuple(subs), NOW, []), "estate_overview")
        (call,) = estate.paths("costmanagement/query")
        self.assertEqual([g["name"] for g in call["body"]["dataset"]["grouping"]], ["ResourceId", "ServiceName"])
        self.assertEqual(call["body"]["dataset"]["granularity"], "None")

    def test_the_questions_to_resource_graph_name_every_subscription_in_one_call(self):
        estate, arm, subs = ten()
        ask(tb.Toolbox(arm, tuple(subs), NOW, []), "estate_overview")
        (call,) = [c for c in estate.calls if c["path"].lower().endswith("microsoft.resourcegraph/resources")]
        self.assertEqual(sorted(call["body"]["subscriptions"]), sorted(subs))


if __name__ == "__main__":
    unittest.main()
