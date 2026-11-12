"""The walk through several separate requests ("Review all"): a link on the Decisions page, one page and one answer for each request, and after each answer the next request.
Each request keeps its own plan, code and form, and there is no answer that covers several requests."""
import dataclasses
import unittest

from test_web_support import DISK, MAYA, TINO, VM, Console, make_advice, make_advice_case, make_case, make_decision, make_plan

from cases.models import Begun, DecideResult
from cases.web import approval, router

APPROVE = "Approve"
AFTER_TWO = "You are going through your requests one by one. 2 more wait after this one, and the next opens when you have answered this one."
AFTER_ONE = "You are going through your requests one by one. 1 more waits after this one, and the next opens when you have answered this one."
LAST = "You are going through your requests one by one. This is the last one that waits for you."
OFFERED = ("declined", "asked", "later", "not_mine", "acknowledged", "confirmed", "ran", "ran_unconfirmed", "running", "unchanged", "stopped", "azure_refused", "failed", "step_up_failed",
           "expired")
NOT_OFFERED = ("signin_failed", "refused_code", "refused_state", "refused_role", "refused_paused", "duplicate", "error")  # the person has more to do with this request
SUCCESSES = ("declined", "asked", "later", "acknowledged", "confirmed", "not_mine", "ran", "ran_unconfirmed", "running", "unchanged")


def add(console: Console, n: int, saving: float, **changes) -> None:
    """Another disk request of the same person, with its own case, code and figure: the bigger saving comes first on the Decisions page."""
    name = f"planted-disk-{n}"
    resource = DISK.replace("planted-disk-1", name)
    console.store.case_put(make_case(case_id=f"case000{n}", plan_id=f"plan000{n}", resource_id=resource, resource_name=name, saving_usd_month=saving, cost_usd_30d=saving))
    console.store.plan_put(make_plan(plan_id=f"plan000{n}", case_id=f"case000{n}", resource_id=resource, resource_name=name, code=f"7F3K92Q{n}", saving_usd_month=saving, **changes))


def way_in(reply):
    found = [a for a in reply.main.find_all("a") if a.text().startswith("Go through the")]
    return (found[0].text(), found[0].attrs["href"]) if found else None


def links(reply) -> list[tuple[str, str]]:
    return [(a.attrs["href"], a.text()) for a in reply.main.find_all("a")]


class TheWayIn(unittest.TestCase):
    def setUp(self):
        self.console = Console()
        self.console.seed()

    def test_one_request_has_no_walk_and_several_have_one_link_to_the_one_with_most_at_stake(self):
        self.assertIsNone(way_in(self.console.get("/")))
        add(self.console, 3, 40.0)
        add(self.console, 4, 20.0)
        page = self.console.get("/")
        self.assertEqual(way_in(page), ("Go through the 3 requests one by one", "/ok/plan0003?walk=1"))
        self.assertIn("Each has its own page and its own answer. After each answer the next one opens.", page.content)
        self.assertEqual((page.forms(), page.root.find_all("button")), ([], []), "a link that opens a request, never a button that answers")

    def test_what_the_person_answered_and_what_is_not_theirs_is_left_out(self):
        add(self.console, 3, 40.0)
        add(self.console, 4, 20.0, approvers=(MAYA,))
        add(self.console, 5, 10.0)
        self.console.store.decision_put(make_decision(plan_id="plan0005", decision="later", plan_code="7F3K92Q5"))
        self.assertEqual(way_in(self.console.get("/")), ("Go through the 2 requests one by one", "/ok/plan0003?walk=1"))
        self.console.store.decision_put(make_decision(plan_id="plan0003", decision="ask", plan_code="7F3K92Q3", note="Who owns it?"))
        self.assertIsNone(way_in(self.console.get("/")), "one request is left, and it needs no walk")

    def test_advice_of_one_kind_is_one_row_but_each_request_has_its_own_turn(self):
        console = Console()
        for n, name, saving in ((2, "oversized-vm-1", 120.0), (3, "oversized-vm-2", 60.0)):
            vm = VM.replace("oversized-vm-1", name)
            console.store.case_put(make_advice_case(case_id=f"case000{n}", plan_id=f"plan000{n}", resource_id=vm, resource_name=name, saving_usd_month=saving))
            console.store.plan_put(make_advice(plan_id=f"plan000{n}", case_id=f"case000{n}", resource_id=vm, resource_name=name, code=f"B4N8X2K{n}", saving_usd_month=saving))
        page = console.get("/")
        self.assertTrue(page.has_table("members-plan0002"), "one row that opens")
        self.assertEqual(way_in(page), ("Go through the 2 requests one by one", "/ok/plan0002?walk=1"))
        self.assertIn(AFTER_ONE, console.get("/ok/plan0002", query={"walk": "1"}).content)
        console.store.decision_put(make_decision(plan_id="plan0002", decision="ask", plan_code="B4N8X2K2", note="Who owns it?"))
        self.assertIn(LAST, console.get("/ok/plan0003", query={"walk": "1"}).content)


class TheWalk(unittest.TestCase):
    def setUp(self):
        self.console = Console(decider="loop")
        self.console.seed()
        add(self.console, 3, 40.0)
        add(self.console, 4, 20.0)

    def page(self, plan_id: str, **query):
        return self.console.get(f"/ok/{plan_id}", query=query)

    def decline(self, plan_id: str):
        form = self.page(plan_id, walk="1").form(f"/ok/{plan_id}", has_button="Decline")
        return self.console.submit(form, "Decline")

    def next_requests(self, reply) -> list[tuple[str, list[str]]]:
        return [(a.attrs["href"], a.classes()) for a in reply.main.find_all("a") if a.text() == "Next request"]

    def test_each_answer_leads_to_the_next_request_and_each_has_its_own_page_code_and_form(self):
        first = self.page("plan0003", walk="1")
        self.assertIn(AFTER_TWO, first.content)
        form = first.form("/ok/plan0003", has_button="Decline")
        self.assertEqual((form.action, form.fields["code"]), ("/ok/plan0003", "7F3K92Q3"), "the form answers this request only, and carries nothing of the walk")
        done = self.decline("plan0003")
        self.assertEqual(self.next_requests(done), [("/ok/plan0004?walk=1", ["btn", "primary"])])
        self.assertIn(("/ok/plan0003", "Back to the request"), links(done), "the way back stays, as a link under the words")
        second = self.page("plan0004", walk="1")
        self.assertIn(AFTER_ONE, second.content)
        self.assertEqual(second.form("/ok/plan0004", has_button="Decline").fields["code"], "7F3K92Q4")
        done = self.decline("plan0004")
        self.assertEqual([href for href, _ in self.next_requests(done)], ["/ok/plan0001?walk=1"])
        self.assertIn(LAST, self.page("plan0001", walk="1").content)
        done = self.decline("plan0001")
        self.assertEqual(self.next_requests(done), [])
        self.assertEqual([(a.attrs["href"], a.text(), a.classes()) for a in done.main.find_all("a") if a.text().startswith("Back to")],
                         [("/ok/plan0001", "Back to the request", ["btn", "primary"])], "nothing is left: the way back is the main button again")
        self.assertIsNone(way_in(self.console.get("/")))

    def test_a_page_without_the_walk_or_of_a_closed_request_has_no_line_about_it(self):
        self.assertNotIn("one by one", self.page("plan0003").content)
        self.assertNotIn("one by one", self.page("plan0003", walk="2").content)
        closed = dataclasses.replace(self.console.store.plan_get("plan0004"), state="declined")
        self.console.store.plan_put(closed)
        self.assertNotIn("one by one", self.page("plan0004", walk="1").content)

    def test_the_walk_adds_one_line_and_changes_nothing_that_a_page_allows(self):
        def shape(reply):
            return [(f.action, sorted(set(f.fields) - {"nonce"}), f.buttons) for f in reply.forms()]
        self.assertEqual(shape(self.page("plan0003")), shape(self.page("plan0003", walk="1")))


class TheResultsThatOfferTheNextRequest(unittest.TestCase):
    def setUp(self):
        self.console = Console()
        self.console.seed()
        add(self.console, 3, 40.0)

    def result(self, kind: str) -> DecideResult:
        return DecideResult(kind in SUCCESSES, kind, "a message of the result", make_plan())

    def by_decider(self, kind: str):
        self.console.decider.result = self.result(kind)
        return self.console.submit(self.console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE), "Decline")

    def by_begin(self, kind: str):
        self.console.delegate.begun = Begun(refusal=self.result(kind))
        return self.console.submit(self.console.get("/ok/plan0001").form("/ok/plan0001", has_button=APPROVE), APPROVE)

    def by_return(self, kind: str):
        self.console.delegate.finished = self.result(kind)
        return self.console.get("/arm/return", query={"code": "a-code", "state": "a-state"})

    def test_the_next_request_is_offered_once_the_persons_part_of_this_one_is_done_and_never_before(self):
        self.assertEqual(set(OFFERED) | set(NOT_OFFERED), set(approval.STATUS))
        self.assertEqual(set(OFFERED), set(approval.NEXT_AFTER))
        for route in (self.by_decider, self.by_begin, self.by_return):
            for kind in OFFERED + NOT_OFFERED:
                with self.subTest(route=route.__name__, kind=kind):
                    reply = route(kind)
                    found = [(a.attrs["href"], a.text()) for a in reply.main.find_all("a") if a.text() == "Next request"]
                    self.assertEqual(found, [("/ok/plan0003?walk=1", "Next request")] if kind in OFFERED else [])

    def test_an_approval_that_returns_from_azure_offers_the_next_request_too(self):
        reply = self.by_return("ran")
        self.assertEqual([(href, text) for href, text in links(reply) if text in ("Next request", "See the history")],
                         [("/history", "See the history"), ("/ok/plan0003?walk=1", "Next request")])


class NoApproveAll(unittest.TestCase):
    def test_every_route_that_answers_names_exactly_one_request(self):
        answering = [pattern for method, pattern, _, _ in router.ROUTES if method == "POST" and "/ok/" in pattern]
        self.assertEqual(len(answering), 3)
        self.assertTrue(all(pattern.count("(?P<plan_id>") == 1 for pattern in answering), answering)

    def test_nothing_answers_for_all_the_requests_at_once(self):
        console = Console()
        console.seed()
        add(console, 3, 40.0)
        for path in ("/", "/ok/all", "/ok"):
            with self.subTest(path=path):
                reply = console.post(path, {"decision": "approve", "code": "7F3K92QD"})
                self.assertIn(reply.status, (404, 405))
        self.assertEqual((console.decider.calls, console.delegate.begins, console.delegate.finishes), ([], [], []))
        self.assertEqual({p.state for p in console.store.plans_open()}, {"open"})


if __name__ == "__main__":
    unittest.main()
