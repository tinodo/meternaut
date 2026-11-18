"""A resource that an automation manages is asked about, with a warning, and is never held back for it (docs/proposals/29-held-findings.md, 2026-11-18).

Advice changes nothing in Azure, and the right advice for a resource that something rewrites by itself is to change it where it is defined: so the finding is an ordinary request that carries a
warning. No change plan is ever made for such a resource. The held requests that were made for it before are turned into ordinary requests in place. Everything here is invented.
"""
import datetime as dt
import re
import unittest
from dataclasses import replace
from types import SimpleNamespace

import support  # noqa: F401  (it puts the app on the path)
from test_digest_page import desk, listed
from test_directory import A
from test_escalation import START, World as LadderWorld
from test_held_findings import BASE, BOB, GROUP, MEASURED, Base, automation, days_ago
from test_letters import BASE as LETTER_BASE, CONTACTS, PERSON, make_case as letter_case
from test_web_support import NOW, SUB, TINO, Console, make_advice, make_advice_case, walk_blocks

from cases import brief, cards, letters, upkeep
from cases.approvals import ADVICE_OPEN_MAX, PROMOTE_NEW, ApprovalSettings, Approvals, build_advice
from cases.detectors import Lead
from cases.families import digest as plan_digest
from cases.families.gates import ChangeScope
from cases.memory_store import MemoryStore, stamp
from cases.models import ADVICE_OPEN_HARD, ADVISE, AUTOMATED, HELD, started

TWO_DAYS = ("An automation changed this 2 days ago and would change it back, so a change by hand would not last. "
            "Change it where it is defined (the template or pipeline that deploys it).")


def lead_of(case, detector: str = "investigation") -> Lead:
    return Lead(detector=detector, resource_id=case.resource_id, resource_type=case.resource_type, name=case.resource_name, resource_group=case.resource_group,
                subscription_id=case.subscription_id, location="westeurope", tags={}, managed_by="", facts={})


class TheWarning(unittest.TestCase):
    def test_it_says_how_long_ago_and_where_to_change_it_in_the_words_of_code_and_only_for_a_change_within_14_days(self):
        self.assertEqual(brief.automation_note(automation(), NOW), TWO_DAYS)
        for days, said in ((0, "today"), (1, "yesterday"), (14, "2 weeks ago")):
            with self.subTest(days=days):
                note = brief.automation_note(automation(owner={"lookedUp": True, "automatedAt": days_ago(days)}), NOW)
                self.assertIn(f"changed this {said} and would change it back", note)
                self.assertTrue(note.endswith("(the template or pipeline that deploys it)."))
        for label, owner in (("15 days ago", {"lookedUp": True, "automatedAt": days_ago(15)}), ("no write", {"lookedUp": True}), ("nothing looked up", {}),
                             ("a record from before the field: a person changed it", {"lookedUp": True, "changedBy": "alice@example.com", "changedAt": days_ago(1)})):
            with self.subTest(case=label):
                self.assertEqual(brief.automation_note(automation(owner=owner), NOW), "")
        self.assertEqual(brief.automation_note(None, NOW), "")

    def test_a_record_from_before_the_field_names_an_automation_by_its_last_change(self):
        old = automation(owner={"lookedUp": True, "changedBy": "aaaaaaaa-1111-4222-8333-444444444444", "changedAt": days_ago(2)})
        self.assertEqual(brief.automation_note(old, NOW), TWO_DAYS)

    def test_it_holds_no_name_and_no_id_and_the_old_words_of_the_hold_stay_as_they_were(self):
        for text in (brief.automation_note(automation(), NOW), brief.HEADS_UP):
            self.assertNotRegex(text, r"(?i)alice|platform-team|[0-9a-f]{8}-|/subscriptions/")
        self.assertEqual(brief.HOLD_WORDS["automation"][1], "An automation changed this {when} and would change it back, so a change by hand would not last.")
        self.assertIn("automation", brief.TAKEN_BACK)
        self.assertEqual(brief.held_reason(automation(), NOW), "", "an automation is no hold")


class AFindingThatAnAutomationManagesIsAsked(Base):
    def test_it_gets_an_ordinary_open_request_that_keeps_the_time_of_the_change(self):
        case = automation()
        self.store.case_put(case)
        self.assertEqual((self.approvals.held_why(case), brief.held_reason(case, self.now)), ("", ""))
        plan = self.approvals.advise(case, (TINO,))
        self.assertEqual((plan.state, plan.family, plan.preconditions[AUTOMATED], HELD in plan.preconditions), ("open", ADVISE, days_ago(2), False))
        self.assertEqual((self.store.case_get(case.case_id).plan_id, self.store.plans_held(), self.store.plans_open()), (plan.plan_id, [], [plan]))
        self.assertEqual(plan_digest.problem(plan, plan.digest), "")

    def test_a_request_for_it_keeps_its_answers_and_has_no_approve_of_a_change(self):
        case = automation()
        self.store.case_put(case)
        plan = self.approvals.advise(case, (TINO,))
        found = brief.build_brief(case, plan, now=self.now, may_answer=True)
        self.assertEqual((found.kind, found.state, found.hold, found.answers), ("advice", "open", None, ("approve", "decline", "not_mine", "ask", "later")))
        self.assertEqual((found.change, found.heads_up), (brief.ADVICE_CHANGE, TWO_DAYS))
        self.assertEqual(self.approvals.check_approve(BOB, plan.plan_id, plan.code)[1].kind, "refused_state", "there is no change to approve, and no sign-in to Azure is begun")
        self.assertTrue(self.answer(plan, "decline", reason="handled").ok)

    def test_the_warning_is_kept_for_what_is_asked_and_never_for_what_meternaut_planted(self):
        group = "meternaut-test-rg"
        approvals = Approvals(self.store, ApprovalSettings(change_scopes=(ChangeScope(SUB, group),)), lambda: self.now)
        planted = automation(resource_group=group, case_id="k-planted", resource_id=f"{BASE}/Microsoft.Foo/bars/planted")
        self.store.case_put(planted)
        plan = approvals.advise(planted, (TINO,))
        self.assertEqual((plan.state, AUTOMATED in plan.preconditions), ("open", False))
        self.assertEqual(brief.build_brief(planted, plan, now=self.now).heads_up, "")

    def test_a_finding_under_the_minimum_or_answered_lately_is_still_not_asked(self):
        quiet = automation(objections=("no measurement backs this finding; a person has to judge it",), saving_usd_month=None, cost_usd_30d=3.0)
        self.store.case_put(quiet)
        self.assertIsNone(self.approvals.advise(quiet, (TINO,)))
        self.setUp()
        case = automation()
        self.store.case_put(case)
        self.store.plan_put(make_advice(plan_id="p-no", case_id=case.case_id, resource_id=case.resource_id, state="declined", created_at=days_ago(3)))
        self.assertIsNone(self.approvals.advise(case, (TINO,)), "a person said lately that it is not worth it")
        self.store.plan_put(make_advice(plan_id="p-no", case_id=case.case_id, resource_id=case.resource_id, state="declined", created_at=days_ago(40)))
        self.assertIsNotNone(self.approvals.advise(case, (TINO,)), "and a month later it is asked again")

    def test_it_waits_for_a_place_like_any_finding_that_the_ais_did_not_settle(self):
        for number in range(ADVICE_OPEN_MAX):
            other = make_advice_case(case_id=f"k-open-{number}", resource_id=f"{BASE}/Microsoft.Foo/bars/o{number}", resource_name=f"o{number}", plan_id=None, status="needs_human")
            self.store.case_put(other)
            self.assertIsNotNone(self.approvals.advise(other, (TINO,)))
        self.assertIsNone(self.approvals.advise(automation(), (TINO,)))
        self.assertIsNotNone(self.approvals.advise(automation(status="proposed"), (TINO,)), "a finding that both AIs agree on is not held by the cap")


class TheWarningIsOneLineOnEveryChannel(unittest.TestCase):
    def setUp(self):
        self.console = Console()
        self.approvals = Approvals(self.console.store, ApprovalSettings(change_scopes=()), lambda: NOW)
        self.case = automation()
        self.console.store.case_put(self.case)
        self.plan = self.approvals.advise(self.case, (TINO,))
        self.console.use(self.approvals)
        self.brief = brief.build_brief(self.case, self.plan, now=NOW, may_answer=True)

    def test_the_page_of_the_request_and_the_page_that_answers_it_have_it_under_the_figure(self):
        for path in ("/why/k-automation", f"/ok/{self.plan.plan_id}"):
            with self.subTest(path=path):
                reply = self.console.get(path)
                self.assertEqual((reply.status, reply.problems), (200, []))
                (line,) = [p.text() for p in reply.main.find_all("p", class_="m") if p.text().startswith("Heads-up:")]
                self.assertEqual(line, f"Heads-up: {TWO_DAYS}")
                self.assertEqual(reply.main.text().count("Heads-up:"), 1, "one distinct line, said once")
                self.assertFalse(reply.has_button("Approve"))
                self.assertTrue(reply.has_button("Worth acting on"))

    def test_the_card_has_it_as_one_block_and_a_request_without_it_has_none(self):
        card = cards.decision_card(self.brief, cards.CardContext(page_url=f"https://meternaut.example/ok/{self.plan.plan_id}"))
        texts = {block["id"]: block["text"] for block in walk_blocks(card)}
        self.assertEqual(texts["heads-up"], f"**Heads-up:** {TWO_DAYS}")
        plain = brief.build_brief(make_advice_case(), make_advice(), now=NOW, may_answer=True)
        self.assertNotIn("heads-up", {block["id"] for block in walk_blocks(cards.decision_card(plain, cards.CardContext(page_url="https://meternaut.example/ok/plan0002")))})

    def test_the_letter_has_it_as_one_line(self):
        letter = letters.approval_letter(self.plan, self.case, PERSON, LETTER_BASE, NOW, CONTACTS)
        self.assertEqual(letter.text.count(f"Heads-up: {TWO_DAYS}"), 1)
        self.assertEqual(letters.approval_letter(make_advice(), make_advice_case(), PERSON, LETTER_BASE, NOW, CONTACTS).text.count("Heads-up"), 0)

    def test_the_letters_of_the_ladder_have_it(self):
        one = letters.escalation_letter(self.plan, self.case, PERSON, LETTER_BASE, NOW, CONTACTS, source="same")
        many = letters.escalation_digest_letter(PERSON, LETTER_BASE, NOW, [(self.plan, self.case, "same")], CONTACTS)
        weekly = letters.escalation_weekly_letter(PERSON, LETTER_BASE, NOW, [(self.plan, self.case)], CONTACTS)
        for letter in (one, many, weekly):
            self.assertIn(f"Heads-up: {TWO_DAYS}", letter.text)

    def test_the_weekly_desk_has_it_on_the_line_of_the_request(self):
        graph = desk(self.console)
        (line,) = listed(graph.sent[0][1]["body"]["content"])
        self.assertTrue(line.endswith(f"Heads-up: {TWO_DAYS}"), line)


class NoChangePlanIsMadeForAManagedResource(unittest.TestCase):
    """Whatever finds it: the AI, Advisor or an older detector, and whatever is asked about it. A change is planned only in a group of Meternaut's own, for what it planted."""

    def settings(self, *scopes):
        return ApprovalSettings(change_scopes=scopes)

    def test_every_path_makes_advice_and_never_a_plan_of_a_change(self):
        for settings, label in ((self.settings(), "no group where a change may be made"), (self.settings(ChangeScope(SUB, "rg-planted-elsewhere")), "another group"),
                                (self.settings(ChangeScope(SUB, "team-apps-rg")), "its own group, but nothing that Meternaut planted")):
            for detector in ("investigation", "advisor-cost", "orphan-managed-disk", "idle-vm", "unused-public-ip"):
                for recommendation in ("delete", "change", "investigate"):
                    with self.subTest(scope=label, detector=detector, recommendation=recommendation):
                        store = MemoryStore(lambda: NOW)
                        approvals = Approvals(store, settings, lambda: NOW)
                        case = automation(detector=detector, status="proposed", recommendation=recommendation, facts=MEASURED if recommendation != "investigate" else {})
                        store.case_put(case)
                        self.assertIsNone(approvals.create(case, lead_of(case, detector), (TINO,)), "no change plan")
                        plan = approvals.plan_for(case, lead_of(case, detector), (TINO,))
                        self.assertEqual((plan.family, plan.state), (ADVISE, "open"))
                        self.assertEqual(plan.target, {})

    def test_the_only_code_that_makes_a_plan_of_a_change_is_the_one_that_the_gates_guard(self):
        import pathlib

        sources = {path.name: path.read_text(encoding="utf-8") for path in (pathlib.Path(support.__file__).parent.parent / "cases").glob("*.py")}
        self.assertEqual(sorted(name for name, text in sources.items() if re.search(r"\bbuild_plan\(", text)), ["approvals.py"])
        self.assertEqual(len(re.findall(r"\bbuild_plan\(", sources["approvals.py"])), 2, "its definition and the one call in `create`, which every gate of why_not guards")


class TheHeldRequestsOfTheOldReasonBecomeRequests(Base):
    def legacy(self, number: int, saving: float, status: str = "proposed", age: int = 5, **more):
        """A held request of the reason that no longer holds anything, as the real store has them: the Watch made it before an automation was a warning."""
        case = automation(case_id=f"k-old-{number}", resource_id=f"{BASE}/Microsoft.Foo/bars/b{number}", resource_name=f"b{number}", resource_type="microsoft.foo/bars", resource_group=GROUP,
                          status=status, saving_usd_month=saving, cost_usd_30d=saving * 2, **more)
        plan = build_advice(case, (TINO,), self.now - dt.timedelta(days=age), self.approvals.settings, new_id=lambda: f"p-old-{number}", held="automation")
        self.store.case_put(replace(case, plan_id=plan.plan_id))
        self.store.plan_put(plan)
        return self.store.case_get(case.case_id), plan

    def test_each_is_promoted_in_place_with_the_same_request_the_same_case_and_its_own_start(self):
        case, held = self.legacy(1, 120.0)
        self.assertEqual((held.state, brief.held_of(held), AUTOMATED in held.preconditions), (HELD, "automation", False))
        self.assertEqual(self.settle(), [], "nothing is closed")
        plan = self.store.plan_get(held.plan_id)
        self.assertEqual((plan.state, plan.plan_id, plan.case_id, plan.family, plan.approvers), ("open", held.plan_id, case.case_id, ADVISE, (TINO,)))
        self.assertEqual((HELD in plan.preconditions, plan.preconditions[AUTOMATED], plan.preconditions["caseStatus"]), (False, days_ago(2), "proposed"))
        self.assertEqual((plan.created_at, plan.waiting_since, started(plan)), (held.created_at, held.created_at, held.created_at), "the wait starts when the request was first made")
        self.assertEqual(plan_digest.problem(plan, plan.digest), "", "it is sealed again, for what it is now")
        self.assertEqual((self.store.plans_held(), self.store.plans_open()), ([], [plan]))
        self.assertEqual((self.store.case_get(case.case_id).plan_id, self.store.case_get(case.case_id).status), (plan.plan_id, "proposed"))
        self.assertEqual(self.approvals.promoted, [(plan, case)])
        found = brief.build_brief(case, plan, now=self.now, may_answer=True)
        self.assertEqual((found.state, found.hold, found.heads_up, found.waiting.days, found.waiting.since), ("open", None, TWO_DAYS, 5, brief.day_text(held.created_at, self.now)))
        self.assertEqual(found.saving.monthly, 120.0)

    def test_the_dearest_come_first_at_most_five_a_watch_and_the_rest_wait_and_go_on_at_the_next_watch(self):
        for number, saving in enumerate((10, 80, 30, 70, 20, 60, 40, 50), 1):
            self.legacy(number, float(saving))
        self.settle()
        self.assertEqual((PROMOTE_NEW, sorted(p.saving_usd_month for p in self.store.plans_open())), (5, [40.0, 50.0, 60.0, 70.0, 80.0]))
        waiting = self.store.plans_held()
        self.assertEqual((sorted(p.saving_usd_month for p in waiting), {brief.held_of(p) for p in waiting}), ([10.0, 20.0, 30.0], {"automation"}),
                         "they wait for the next Watch and nothing else: the reason that they had, and its words, not those of a place that is not free")
        shown = brief.hold_of(waiting[0], self.store.case_get(waiting[0].case_id), self.now)
        self.assertEqual((shown.heading, shown.why), (brief.HOLD_WORDS["automation"][0], brief.HOLD_WORDS["automation"][1].format(when="2 days ago")))
        self.settle()
        self.assertEqual((len(self.store.plans_open()), self.store.plans_held()), (8, []), "the next Watch goes on")
        before = dict(self.store.plans)
        self.settle()
        self.assertEqual((self.store.plans, self.approvals.promoted), (before, []), "and a third Watch changes nothing: nothing is promoted twice")

    def test_none_is_promoted_while_the_places_are_full_and_one_when_a_place_is_free(self):
        for number in range(ADVICE_OPEN_MAX):
            other = make_advice_case(case_id=f"k-open-{number}", resource_id=f"{BASE}/Microsoft.Foo/bars/o{number}", resource_name=f"o{number}", plan_id=None, status="needs_human")
            self.store.case_put(other)
            self.approvals.advise(other, (TINO,))
        _, many = self.legacy(1, 50.0, status="needs_human")
        _, agreed = self.legacy(2, 30.0, status="proposed")
        self.settle()
        self.assertEqual((self.store.plan_get(many.plan_id).state, brief.held_of(self.store.plan_get(many.plan_id))), (HELD, "waiting"))
        self.assertEqual(self.store.plan_get(agreed.plan_id).state, "open", "a finding that both AIs agree on is not held by the cap")
        self.answer(next(p for p in self.store.plans_open() if p.preconditions.get("caseStatus") == "needs_human"), "decline", reason="handled")
        self.settle()
        self.assertEqual(self.store.plan_get(many.plan_id).state, "open", "a place is free")

    def test_a_held_request_of_another_reason_is_not_promoted(self):
        self.put("unchecked")
        self.put("impact")
        self.settle()
        self.settle()
        self.assertEqual((sorted(brief.held_of(p) for p in self.store.plans_held()), self.store.plans_open(), self.approvals.promoted), (["impact", "unchecked"], [], []))

    def test_a_held_request_of_the_reason_rules_is_never_made_an_open_request_by_this_step_although_no_guard_holds_it_now(self):
        self.put("rules")
        self.settle()
        self.assertEqual([brief.held_of(p) for p in self.store.plans_held()], ["rules"])
        self.assertEqual(self.approvals._guard(self.store.case_get("k-rules")), "", "no guard holds the finding of the rules back now: only the reason of its request keeps it from being promoted")
        self.settle()
        self.settle()
        self.assertEqual((self.store.plans_open(), self.approvals.promoted, [brief.held_of(p) for p in self.store.plans_held()]), ([], [], ["rules"]),
                         "a guard that ends by itself closes nothing: a judgment does, and the normal path asks")

    def test_a_request_that_waits_for_the_next_watch_stays_as_it_was_and_every_held_request_stays_linked_to_its_case_after_a_judgment(self):
        cases = [self.legacy(number, float(saving))[0] for number, saving in enumerate((10, 80, 30, 70, 20, 60, 40, 50), 1)]
        for case in cases:
            self.judged_again(self.store.case_get(case.case_id))  # what every judgment of the investigation does: the case is written again, with no link to a request
        self.assertEqual({self.store.case_get(case.case_id).plan_id for case in cases}, {None})
        self.settle()
        opened, waiting = self.store.plans_open(), self.store.plans_held()
        self.assertEqual((len(opened), len(waiting)), (PROMOTE_NEW, 3))
        for plan in (*opened, *waiting):
            self.assertEqual(self.store.case_get(plan.case_id).plan_id, plan.plan_id, "the page of the finding finds its request through this link")
        self.assertEqual({brief.held_of(p) for p in waiting}, {"automation"}, "the three wait for the next Watch and nothing else: they keep the reason that they had, and its words")
        console = Console(store=self.store)
        console.use(self.approvals)
        reply = console.get(f"/why/{waiting[0].case_id}")
        self.assertIn(brief.HOLD_WORDS["automation"][0], reply.content)
        for label in ("Not worth it", "Ask or tell", "Decide later", "This is not mine"):
            self.assertTrue(reply.has_button(label), label)

    def test_a_request_that_waits_for_a_place_says_so_and_is_linked_to_its_case_and_so_is_one_when_nobody_can_answer(self):
        for number in range(ADVICE_OPEN_MAX):
            other = make_advice_case(case_id=f"k-open-{number}", resource_id=f"{BASE}/Microsoft.Foo/bars/o{number}", resource_name=f"o{number}", plan_id=None, status="needs_human")
            self.store.case_put(other)
            self.approvals.advise(other, (TINO,))
        case, held = self.legacy(1, 50.0, status="needs_human")
        self.judged_again(self.store.case_get(case.case_id))
        self.settle()
        plan = self.store.plan_get(held.plan_id)
        self.assertEqual((plan.state, brief.held_of(plan), self.store.case_get(case.case_id).plan_id), (HELD, "waiting", held.plan_id))
        other_case, other_held = self.legacy(2, 120.0)
        self.judged_again(self.store.case_get(other_case.case_id))
        self.settle(())
        self.assertEqual(self.store.case_get(other_case.case_id).plan_id, other_held.plan_id, "nobody can answer: nothing is promoted, and the link stays")

    def test_a_promoted_request_keeps_the_code_that_it_had_so_that_a_page_made_before_still_answers_it(self):
        case, held = self.legacy(1, 120.0)
        console = Console(store=self.store)
        console.use(self.approvals)
        form = console.get(f"/why/{case.case_id}").form(has_button="Not worth it")  # a page that was opened while the request was held
        self.settle()
        plan = self.store.plan_get(held.plan_id)
        self.assertEqual((plan.state, plan.code), ("open", held.code))
        self.assertNotEqual(plan_digest.code_of(plan.digest), plan.code, "it is the code that the request had, not the code of what it is now: advice changes nothing in Azure, and nothing checks its digest")
        self.assertEqual(console.submit(form, "Not worth it", reason="handled").status, 200)
        self.assertEqual((self.store.plan_get(held.plan_id).state, self.store.case_get(case.case_id).status), ("declined", "declined"))

    def test_a_finding_that_nobody_is_to_be_asked_about_is_closed_and_not_promoted(self):
        quiet = dict(objections=("no measurement backs this finding; a person has to judge it",))
        _, small = self.legacy(1, 0.0, **quiet)
        self.store.case_put(replace(self.store.case_get("k-old-1"), saving_usd_month=None, cost_usd_30d=3.0))
        _, answered = self.legacy(2, 90.0)
        self.store.plan_put(make_advice(plan_id="p-no", case_id="k-old-2", resource_id=self.store.case_get("k-old-2").resource_id, state="declined", created_at=days_ago(3)))
        closed = self.settle()
        self.assertEqual(sorted(plan.preconditions["takenBack"] for plan, _ in closed), ["released", "released"])
        self.assertEqual((self.store.plans_open(), self.store.plans_held()), ([], []))

    def test_a_held_request_of_a_finding_that_no_saving_backs_is_closed_and_not_promoted_however_much_the_resource_costs(self):
        _, unpriced = self.legacy(1, 0.0)
        self.store.case_put(replace(self.store.case_get("k-old-1"), saving_usd_month=None, cost_usd_30d=848.0, objections=()))
        _, waiting = self.legacy(2, 0.0)
        self.store.case_put(replace(self.store.case_get("k-old-2"), saving_usd_month=0.0, cost_usd_30d=848.0, objections=()))
        self.store.plan_put(replace(self.store.plan_get(waiting.plan_id), preconditions={**self.store.plan_get(waiting.plan_id).preconditions, HELD: "waiting"}))
        _, priced = self.legacy(3, 120.0)
        closed = self.settle()
        self.assertEqual(sorted((plan.plan_id, plan.preconditions["takenBack"]) for plan, _ in closed), sorted([(unpriced.plan_id, "released"), (waiting.plan_id, "released")]))
        self.assertEqual([p.plan_id for p in self.store.plans_open()], [priced.plan_id], "only the finding that code priced is made a request")
        self.assertEqual(([p.plan_id for p, _ in self.approvals.promoted], self.store.plans_held()), ([priced.plan_id], []))
        self.assertEqual((self.settle(), self.approvals.promoted), ([], []), "a second Watch changes nothing")

    def test_nothing_is_promoted_when_nobody_can_answer_and_a_reason_that_changed_is_kept(self):
        _, held = self.legacy(1, 120.0)
        self.settle(())
        self.assertEqual((self.store.plan_get(held.plan_id).state, brief.held_of(self.store.plan_get(held.plan_id))), (HELD, "automation"))
        changed = self.store.case_get("k-old-1")
        self.store.case_put(replace(changed, recommendation="delete", facts=MEASURED, resource_type="microsoft.compute/disks", owner={}))
        self.settle()
        self.assertEqual((self.store.plan_get(held.plan_id).state, brief.held_of(self.store.plan_get(held.plan_id))), (HELD, "unchecked"), "a guard that holds it is still a guard")

    def test_a_person_who_answered_a_held_request_keeps_the_answer_and_a_do_not_touch_mark_closes_it(self):
        _, held = self.legacy(1, 120.0)
        _, marked = self.legacy(2, 90.0)
        self.assertTrue(self.answer(held, "ask", note="who owns it?").ok)
        from cases.models import NoteRecord
        self.store.note_put(NoteRecord(note_id="n1", oid=TINO, kind="do_not_touch", text="leave it", scope_resource_id=self.store.case_get("k-old-2").resource_id, created_at=stamp(self.now)))
        self.settle()
        self.assertEqual(self.store.plan_get(held.plan_id).state, "open", "a question does not end a held request: it is a request now, and the question stays")
        self.assertEqual(len(self.store.decisions_of_plan(held.plan_id)), 1)
        self.assertEqual(self.store.plan_get(marked.plan_id).preconditions["takenBack"], "left-alone")

    def test_the_history_says_each_request_that_was_made_and_the_old_words_stay_valid(self):
        self.legacy(1, 120.0)
        ex = SimpleNamespace(approvals=self.approvals, approvers=lambda: (TINO,))
        self.assertEqual(upkeep.take_back(ex, self.history), {})
        (said,) = [line for line in self.lines.found if line["type"] == "plan.created"]
        self.assertEqual((said["planId"], said["caseKey"], said["family"], said["approvers"], said["was"]), ("p-old-1", "k-old-1", ADVISE, 1, "held"))
        self.assertEqual([line for line in self.lines.found if line["type"] in ("case.held", "case.released")], [], "no line says that it was held back or released")
        from cases.approvals import HELD_BACK
        self.assertEqual(HELD_BACK["automation"], "held back: managed by an automation")


class TheLadderTreatsAPromotedRequestLikeAnyOpenOne(unittest.TestCase):
    def test_its_wait_counts_from_the_held_request_and_its_steps_and_letters_follow(self):
        world = LadderWorld(plans=0)
        world.clock.advance(days=5)
        case = letter_case(case_id="c1", status="needs_human", plan_id="p1", resource_name="disk-p1", owner={"lookedUp": True, "automatedAt": stamp(START + dt.timedelta(days=4))})
        world.store.case_put(case)
        settings = ApprovalSettings(change_scopes=())
        held = build_advice(case, (A,), START, settings, new_id=lambda: "p1", held="automation")
        world.store.plan_put(held)
        Approvals(world.store, settings, world.clock).settle((A,))
        plan = world.store.plan_get("p1")
        self.assertEqual((plan.state, started(plan)), ("open", stamp(START)))
        world.tick()
        (step,) = world.steps("p1")
        self.assertEqual((step.number, step.source), (1, "same"), "the reminder is due at once: it has waited five days")
        (sent,) = world.mail.sent_to("ada@example.com")
        self.assertIn("A decision has waited 5 days", sent[1])
        self.assertIn("Heads-up: An automation changed this yesterday and would change it back", sent[2])
        world.clock.advance(days=2)
        world.tick()
        self.assertEqual([r.number for r in world.steps("p1")], [1, 2], "and the next step on the seventh day, as for any request")


class TheFirstDay(unittest.TestCase):
    """What one person is sent on the day of the first Watch after the change, for five held requests that were made five days ago: the numbers of the table in proposal 29."""

    def promoted(self, store, clock, approver, how_many=5):
        settings = ApprovalSettings(change_scopes=())
        for number in range(1, how_many + 1):
            case = letter_case(case_id=f"c{number}", resource_id=f"/subscriptions/s/resourceGroups/rg/providers/Microsoft.Foo/bars/b{number}", resource_name=f"b{number}", status="proposed",
                               plan_id=f"p{number}", saving_usd_month=10.0 * number, cost_usd_30d=20.0 * number, owner={"lookedUp": True, "automatedAt": stamp(clock() - dt.timedelta(days=2))})
            store.case_put(case)
            store.plan_put(build_advice(case, (approver,), clock() - dt.timedelta(days=5), settings, new_id=lambda number=number: f"p{number}", held="automation"))
        Approvals(store, settings, clock).settle((approver,))
        return store.plans_open()

    def test_a_person_who_chose_e_mail_gets_no_card_and_one_reminder_that_lists_the_requests_that_have_waited_three_days(self):
        world = LadderWorld(plans=0)
        self.assertEqual(len(self.promoted(world.store, world.clock, A)), 5)
        world.tick(3)
        (sent,) = world.mail.sent_to("ada@example.com")
        self.assertEqual(sent[1], "[Meternaut] 5 decisions have waited without an answer")
        self.assertEqual(len(listed(sent[2])), 5)
        self.assertEqual(sent[2].count("Heads-up: An automation changed this 2 days ago"), 5)
        world.clock.advance(hours=23)
        world.tick()
        self.assertEqual(len(world.mail.sent_to("ada@example.com")), 1, "never more than one a day")

    def test_a_person_who_chose_teams_gets_the_cards_that_the_weekly_budget_allows_and_the_reminder_goes_by_letter(self):
        from cardsupport import MAYA as CARD_MAYA, World as CardWorld

        world = CardWorld()
        world.introduce(CARD_MAYA)
        world.channel(CARD_MAYA)
        self.assertEqual(len(self.promoted(world.store, world.clock, CARD_MAYA)), 5)
        world.run()
        sent = [m for m in world.tries(CARD_MAYA, "advice-card") if m.status == "sent"]
        held = [m for m in world.tries(CARD_MAYA, "advice-card") if m.status == "held"]
        self.assertEqual((len(sent), len(held), len(world.queue_fake.cards())), (3, 2, 3), "three cards at most in a week: the other two wait for Monday")
        self.assertIn("weekly budget of 3 messages", held[0].detail)
        for text in (block for card in world.queue_fake.cards() for block in [b for b in walk_blocks(card) if b["id"] == "heads-up"]):
            self.assertTrue(text["text"].startswith("**Heads-up:** An automation changed this 2 days ago"))

    def test_the_weekly_desk_lists_five_lines_with_the_warning_once_on_the_desk_day(self):
        console = Console()
        approvals = Approvals(console.store, ApprovalSettings(change_scopes=()), lambda: NOW)
        for number in range(1, 6):
            case = automation(case_id=f"k-d{number}", resource_id=f"{BASE}/Microsoft.Foo/kind{number}/d{number}", resource_name=f"d{number}", resource_type=f"microsoft.foo/kind{number}",
                              saving_usd_month=10.0 * number, cost_usd_30d=20.0 * number, plan_id=None)
            console.store.case_put(case)
            self.assertIsNotNone(approvals.advise(case, (TINO,)))
        graph = desk(console)
        (subject,) = graph.subjects()
        self.assertEqual(subject, "[Meternaut] 5 decisions wait for you")
        self.assertEqual(sum(line.count("Heads-up:") for line in listed(graph.sent[0][1]["body"]["content"])), 5)


class TheCapAndTheOrderOfTheRequests(Base):
    """Nothing expires, so a place is freed only by an answer: the cap is 30 and a finding that is worth more than the least of the open requests is never held behind it. What waits is ranked by its
    figure, the largest first, then by who has waited longest, in every list."""

    def case(self, number: int, saving, **more):
        return make_advice_case(case_id=f"k-cap-{number}", resource_id=f"{BASE}/Microsoft.Foo/kind{number}/c{number}", resource_name=f"c{number}", resource_type=f"microsoft.foo/kind{number}",
                                plan_id=None, status="needs_human", saving_usd_month=saving, cost_usd_30d=(saving or 45.0) * 2, objections=("It may be in use.",), **more)

    def fill(self) -> None:
        for number in range(ADVICE_OPEN_MAX):
            case = self.case(number, 10.0 + number)
            self.store.case_put(case)
            self.assertIsNotNone(self.approvals.advise(case, (TINO,)))

    def test_the_places_are_thirty_up_to_a_ceiling_of_forty_five_and_the_waiting_words_say_so(self):
        self.assertEqual((ADVICE_OPEN_MAX, ADVICE_OPEN_HARD), (30, 45))
        self.assertEqual(brief.HOLD_WORDS["waiting"][1], "Nothing holds it back any more, but it waits for a free place. Meternaut keeps 30 requests open at once for findings that the AIs did not settle, "
                                                           "and up to 45 when a finding is worth more than the smallest of them.")

    def test_the_ceiling_holds_whatever_a_finding_is_worth_nothing_open_is_displaced_and_a_freed_place_goes_to_the_dearest_that_waits(self):
        self.fill()
        for number in range(100, 120):
            dearer = self.case(number, 500.0 + number)
            self.store.case_put(dearer)
            self.approvals.advise(dearer, (TINO,))
        self.assertEqual(len(self.store.plans_open()), ADVICE_OPEN_HARD, "30 open, and the 15 dearer findings that came first were asked about: nothing is asked about beyond the ceiling")
        self.assertEqual(len({p.case_id for p in self.store.plans_open()} & {f"k-cap-{n}" for n in range(ADVICE_OPEN_MAX)}), ADVICE_OPEN_MAX, "nothing that was open was displaced")
        self.settle()
        waiting = sorted(self.store.plans_held(), key=lambda p: p.case_id)
        self.assertEqual(([p.case_id for p in waiting], {brief.held_of(p) for p in waiting}), ([f"k-cap-{n}" for n in range(115, 120)], {"waiting"}), "the five that did not fit are shown")
        least = min(self.store.plans_open(), key=lambda p: p.saving_usd_month)
        self.assertTrue(self.answer(least, "decline", reason="handled").ok)
        self.settle()
        self.assertEqual(([p.case_id for p, _ in self.approvals.promoted], len(self.store.plans_open())), (["k-cap-119"], ADVICE_OPEN_HARD), "one place was freed: the dearest of the five takes it")

    def test_a_finding_worth_more_than_the_least_open_request_is_asked_and_one_worth_no_more_waits_and_is_shown(self):
        self.fill()
        dearer = self.case(100, 500.0)
        self.store.case_put(dearer)
        self.assertIsNotNone(self.approvals.advise(dearer, (TINO,)), "worth more than the least of them: it is not held behind it")
        self.assertEqual(len(self.store.plans_open()), ADVICE_OPEN_MAX + 1)
        for number, saving in ((200, 10.0), (201, 5.0)):
            late = self.case(number, saving)
            self.store.case_put(late)
            self.assertIsNone(self.approvals.advise(late, (TINO,)), f"worth {saving}: as much as the least, or less")
        unpriced = self.case(202, None)
        self.store.case_put(unpriced)
        self.assertIsNone(self.approvals.advise(unpriced, (TINO,)), "no saving was priced: it is no request at all, and no place is waited for")
        self.settle()
        waiting = {p.case_id: p for p in self.store.plans_held()}
        self.assertEqual(sorted(waiting), ["k-cap-200", "k-cap-201"], "each that waits for a place is shown as a held request, and the finding that no saving backs is not")
        self.assertEqual({brief.held_of(p) for p in waiting.values()}, {"waiting"})
        self.assertEqual(brief.build_brief(self.store.case_get("k-cap-201"), waiting["k-cap-201"], now=self.now).hold.why, brief.HOLD_WORDS["waiting"][1])

    def test_a_waiting_request_is_made_an_ordinary_one_when_a_place_is_free_the_dearest_first(self):
        self.fill()
        for number, saving in ((200, 9.0), (201, 5.0)):
            self.store.case_put(self.case(number, saving))
        self.settle()
        self.assertEqual(len(self.store.plans_held()), 2)
        least = min(self.store.plans_open(), key=lambda p: p.saving_usd_month)
        self.assertTrue(self.answer(least, "decline", reason="handled").ok)
        self.settle()
        self.assertEqual([p.case_id for p, _ in self.approvals.promoted], ["k-cap-200"], "29 are open, so one place is free: the one that is worth most takes it")
        self.assertEqual([p.case_id for p in self.store.plans_held()], ["k-cap-201"], "and the other is worth no more than the least that is open now")

    def test_the_migration_promotes_in_the_order_of_the_pages_the_largest_figure_first_then_who_waited_longest(self):
        for number, (saving, age) in enumerate(((40.0, 3), (300.0, 1), (40.0, 9), (None, 20), (90.0, 5), (40.0, 6)), 1):
            case = automation(case_id=f"k-o{number}", resource_id=f"{BASE}/Microsoft.Foo/kind{number}/o{number}", resource_name=f"o{number}", resource_type=f"microsoft.foo/kind{number}",
                              saving_usd_month=saving, cost_usd_30d=(saving or 60.0) * 2, status="proposed", first_seen_at=days_ago(age),
                              **({"detector": "orphan-private-endpoint"} if saving is None else {}))  # a finding of the investigation with no saving is not asked about: this one is of a rule-based detector, and is ranked by its cost
            self.store.case_put(case)
            self.store.plan_put(build_advice(case, (TINO,), self.now - dt.timedelta(days=age), self.approvals.settings, new_id=lambda number=number: f"p-o{number}", held="automation"))
            self.store.case_put(replace(case, plan_id=f"p-o{number}"))
        self.settle()
        self.assertEqual([plan.plan_id for plan, _ in self.approvals.promoted], ["p-o2", "p-o4", "p-o5", "p-o3", "p-o6"],
                         "the figure that the pages show (a saving, else the cost): 300, 120, 90, and then the three of 40 by who has waited longest (9, 6 and 3 days); five a Watch")
        self.assertEqual([p.plan_id for p in self.store.plans_held()], ["p-o1"])


class EveryListRanksByTheFigureThenByWhoWaitedLongest(unittest.TestCase):
    def test_the_page_and_the_weekly_desk_list_the_largest_figure_first_what_has_no_figure_last_and_ties_by_who_waited_longest(self):
        from cases.web import home

        console = Console()
        rows = (("small", 40.0, 2), ("tied-old", 90.0, 9), ("large", 300.0, 1), ("tied-young", 90.0, 3), ("none", None, 30))
        for number, (name, saving, waited) in enumerate(rows, 1):
            case = make_advice_case(case_id=f"k-r{number}", resource_id=f"{BASE}/Microsoft.Foo/kind{number}/{name}", resource_name=name, resource_type=f"microsoft.foo/kind{number}", plan_id=f"p-r{number}",
                                    status="needs_human", saving_usd_month=saving, cost_usd_30d=None, first_seen_at=days_ago(waited))
            console.store.case_put(case)
            console.store.plan_put(make_advice(plan_id=f"p-r{number}", case_id=case.case_id, resource_id=case.resource_id, resource_name=name, saving_usd_month=saving, created_at=days_ago(waited),
                                               title=f"Look at {name}"))
        wanted = ["large", "tied-old", "tied-young", "small", "none"]
        ctx_rows = [home.Row(brief.build_brief(console.store.case_get(f"k-r{n}"), console.store.plan_get(f"p-r{n}"), now=NOW, may_answer=True), console.store.case_get(f"k-r{n}"), False)
                    for n in range(1, len(rows) + 1)]
        self.assertEqual([unit.first.case.resource_name for unit in home.units_of(ctx_rows)], wanted, "the Decisions page, which is the start page, ranks with this code")
        letter_lines = listed(desk(console).sent[0][1]["body"]["content"])
        self.assertEqual([next(name for name in wanted if re.search(rf"\b{name}\b", line)) for line in letter_lines], wanted, "the weekly desk lists the rows of the page in the same order")


class TheRevivalAndTheMigrationAgree(Base):
    """The requests that the old clock closed come back at the Watch (cases/escalation.py revive), and the held ones become requests: neither may undo the other."""

    def test_a_revived_request_is_never_made_held_and_a_held_request_for_its_resource_closes_when_it_is_open_again(self):
        from cases import escalation

        case = make_advice_case(case_id="k-rev", status="expired", plan_id="p-rev", recommendation="investigate", owner={"lookedUp": True, "automatedAt": days_ago(2)})
        self.store.case_put(case)
        old = make_advice(plan_id="p-rev", case_id="k-rev", resource_id=case.resource_id, state="expired", created_at=days_ago(5), expires_at=days_ago(2),
                          preconditions={"family": ADVISE, "caseStatus": "needs_human"})
        self.store.plan_put(old)
        self.assertEqual(self.settle(), [])
        self.assertEqual(self.store.plans_held(), [], "a request that the clock closed is no finding that waits: nothing is held for it")
        (revived,) = escalation.revive(self.store, self.now)
        self.assertEqual((revived.plan_id, self.store.plan_get("p-rev").state, self.store.case_get("k-rev").status), ("p-rev", "open", "needs_human"))
        self.assertEqual(self.settle(), [])
        self.assertEqual((self.store.plans_held(), self.store.plan_get("p-rev").state, started(self.store.plan_get("p-rev"))), ([], "open", days_ago(5)), "it stays open, with its own start")
        again = replace(case, status="needs_human", case_id="k-rev-2", resource_id=case.resource_id)
        self.store.case_put(again)
        held = build_advice(again, (TINO,), self.now - dt.timedelta(days=1), self.approvals.settings, new_id=lambda: "p-held", held="automation")
        self.store.plan_put(held)
        (closed,) = self.settle()
        self.assertEqual((closed[0].plan_id, closed[0].preconditions["takenBack"], self.store.plan_get("p-rev").state), ("p-held", "released", "open"), "an open request for the resource wins: the held one ends")
        self.assertEqual(self.approvals.promoted, [])


class TheOldWordsStillRenderForOldRequests(unittest.TestCase):
    def test_a_held_request_of_the_old_reason_and_a_request_taken_back_for_it_say_what_they_said(self):
        case = automation()
        held = replace(make_advice(), state=HELD, preconditions={"held": "automation"})
        found = brief.hold_of(held, case, NOW)
        self.assertEqual((found.reason, found.heading, found.why), ("automation", "An automation changes it", brief.HOLD_WORDS["automation"][1].format(when="2 days ago")))
        ended = replace(make_advice(), state="expired", expires_at="2026-11-04T09:00:00Z", preconditions={"takenBack": "automation"})
        outcome = brief.build_brief(case, ended, now=NOW).outcome
        self.assertEqual((outcome.title, outcome.lines[0]), ("Taken back", brief.TAKEN_BACK["automation"]))
