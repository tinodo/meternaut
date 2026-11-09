import ast
import dataclasses
import datetime as dt
import math
import re
import unicodedata
import unittest
from pathlib import Path

from test_web_support import GROUP, NOW, SUB, VM, at, make_action, make_advice, make_advice_case, make_case, make_decision, make_plan

import support  # noqa: F401  (puts the app on the path)
from cases import brief
from cases.brief import (Brief, build_brief, check_lines, confidence_of, contact_text, days_text, doubt_of, facts_of, footer_line, headline_of, kind_words, models_of, number_text,
                         order_key, owner_of, plain, plan_headline, portal_url, quantity, reasoning_of, usd_text, visible, written_by)
from cases.families import registry
from cases.families.words import SHOWN
from cases.models import ADVISE

IP = f"/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Network/publicIPAddresses/planted-ip-1"
INJECTIONS = (
    "<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "[click here](javascript:alert(1))", "![x](https://evil.example/p.png)", "[Approve](https://evil.example/ok/1)",
    "<https://evil.example/login>", "see https://evil.example/login now", "ftp://evil.example/x", "\u202eevil\u202c", "zero\u200bwidth\u200djoin\ufeffbom\u2060",
    "line one\r\nBcc: evil@example.com\r\nSubject: hijack", "line one\nline two\u2028line three\u2029line four", "x" * 5000, "\x00\x07\x1b[31mred\x1b[0m", "javascript:alert(1)",
    "&lt;b&gt; &amp; \"quote\" 'tick'", "tab\tseparated\vvertical\x0cform", "\ud800 lone surrogate", "private \ue000 use", "tag \U000e0041 character", "",
)


def ip_case(**changes):
    values = dict(case_id="case0003", resource_id=IP, resource_name="planted-ip-1", resource_type="microsoft.network/publicipaddresses", detector="orphan-public-ip",
                  facts={"allocation": "static"}, plan_id="plan0003")
    values.update(changes)
    return make_case(**values)


def ip_plan(**changes):
    values = dict(plan_id="plan0003", case_id="case0003", family="delete-public-ip", resource_id=IP, resource_name="planted-ip-1", saving_usd_month=3.65, waiting_costs_usd_day=0.12,
                  preconditions={"family": "delete-public-ip", "tag": "meternaut-planted"})
    values.update(changes)
    return make_plan(**values)


def brief_of(case, plan, **kwargs) -> Brief:
    return build_brief(case, plan, kwargs.pop("action", None), kwargs.pop("decisions", ()), now=kwargs.pop("now", NOW), **kwargs)


class TheHeadline(unittest.TestCase):
    """One line: a verb, the thing and the place. Written by code, never by a model."""

    def test_a_change_names_the_kind_of_resource_in_the_words_of_its_family(self):
        self.assertEqual(headline_of("delete-disk", "d-1", "rg-a", "microsoft.compute/disks", "delete"), "Delete the unattached disk d-1 in group rg-a")
        self.assertEqual(headline_of("delete-public-ip", "ip-1", "rg-a", "microsoft.network/publicipaddresses", None), "Delete the unassigned public IP address ip-1 in group rg-a")

    def test_a_finding_that_cannot_be_changed_is_a_consideration_in_the_words_of_its_recommendation(self):
        for recommendation, verb in (("delete", "Consider deleting"), ("change", "Consider changing"), ("keep", "Keep"), (None, "Look at"), ("something new", "Look at")):
            with self.subTest(recommendation=recommendation):
                self.assertEqual(headline_of(ADVISE, "vm-1", "rg-a", "microsoft.compute/virtualmachines", recommendation), f"{verb} the virtual machine vm-1 in group rg-a")

    def test_a_type_without_words_is_a_resource_and_a_missing_group_is_left_out(self):
        self.assertEqual(headline_of(ADVISE, "x", "", "microsoft.thing/things", "delete"), "Consider deleting the resource x")
        self.assertEqual(headline_of("", "x", "g", "", None), "Look at the resource x in group g")
        self.assertEqual(headline_of("delete-disk", "", "", "", None), "Delete the unattached disk this resource")

    def test_a_family_without_words_of_its_own_keeps_the_title_of_its_plan(self):
        self.assertEqual(headline_of("resize-disk", "d", "g", "microsoft.compute/disks", None, "Resize an unattached disk"), "Resize an unattached disk")

    def test_every_type_that_has_words_is_named_in_the_headline_of_a_consideration_and_a_workspace_is_one_of_them(self):
        self.assertEqual(headline_of(ADVISE, "ws-demo", "rg-demo", "Microsoft.OperationalInsights/workspaces", "change"), "Consider changing the Log Analytics workspace ws-demo in group rg-demo")
        for rtype, (_, noun) in brief.TYPE_WORDS.items():
            with self.subTest(type=rtype):
                found = headline_of(ADVISE, "x-1", "rg-demo", rtype, "change")
                self.assertEqual(found, f"Consider changing the {noun} x-1 in group rg-demo")
                self.assertNotIn("the resource", found)

    def test_a_name_is_cut_and_is_one_line(self):
        found = headline_of("delete-disk", "n" * 500 + "\n<b>", "g", "microsoft.compute/disks", None)
        self.assertEqual(found.count("\n"), 0)
        self.assertLessEqual(len(found), 200)
        self.assertIn("...", found)

    def test_the_headline_of_a_plan_alone_needs_no_case(self):
        self.assertEqual(plan_headline(make_plan()), "Delete the unattached disk planted-disk-1 in group meternaut-test-rg")
        self.assertEqual(plan_headline(make_advice(title="Consider changing the virtual machine oversized-vm-1 in group team-apps-rg")),
                         "Consider changing the virtual machine oversized-vm-1 in group team-apps-rg")
        self.assertEqual(plan_headline(make_advice(title="")), "Look at the resource oversized-vm-1 in group team-apps-rg")


class TheBriefOfADeleteDisk(unittest.TestCase):
    def setUp(self):
        self.brief = brief_of(make_case(plan_id="plan0001"), make_plan(), may_answer=True)

    def test_it_answers_the_eight_questions(self):
        b = self.brief
        self.assertEqual((b.kind, b.family, b.state, b.plan_id, b.case_id, b.plan_code), ("change", "delete-disk", "open", "plan0001", "case0001", "7F3K92QD"))
        self.assertEqual(b.headline, "Delete the unattached disk planted-disk-1 in group meternaut-test-rg")  # 1 what am I asked to decide
        self.assertEqual((b.saving.monthly, b.saving.level, b.saving.waiting_per_day), (7.17, "Expected", 0.24))  # 2 what do I get
        self.assertEqual((b.confidence.level, b.confidence.because), ("High", "Both AI reviewers agree; code read the facts itself."))  # 3 how sure
        self.assertEqual([f.label for f in b.facts], ["Cost, last 30 days", "State", "Locks and keep tags"])
        self.assertEqual(b.change, "Deletes the disk planted-disk-1 in resource group meternaut-test-rg. Nothing else changes.")  # 4 what happens
        self.assertEqual(b.who_acts, brief.WHO_ACTS)
        self.assertIn("Meternaut holds no right of its own to change anything.", b.who_acts)
        self.assertIn("still unattached, still tagged as planted by Meternaut, still in this resource group and not locked", b.rechecked)
        self.assertEqual((b.undo.reversible, b.undo.how), (False, "A deleted disk cannot be restored. A new, empty disk can be made."))  # 5 can it be undone
        self.assertEqual((b.risk.level, b.risk.text), ("medium", "If something still uses the disk, that use stops, and the data on it is lost for good."))  # 6 what could go wrong
        self.assertEqual((b.owner.known, b.owner.text), (False, "Meternaut has not looked up who owns this resource yet."))  # 7 whose is it
        self.assertEqual(b.answers, ("approve", "decline", "not_mine", "ask", "later"))  # 8 what are my choices

    def test_where_it_is_and_the_one_portal_address_that_is_made_from_the_id(self):
        where = self.brief.where
        self.assertEqual((where.subscription, where.group, where.kind, where.name), ("bbbbbbbb", "meternaut-test-rg", "Managed disk", "planted-disk-1"))
        self.assertEqual(where.portal_url, f"https://portal.azure.com/#resource{make_plan().resource_id}")

    def test_the_age_the_end_the_models_and_nothing_decided_yet(self):
        b = self.brief
        self.assertEqual((b.found_at, b.age_days, b.expires_at), (make_case().first_seen_at, 3, make_plan().expires_at))
        self.assertEqual(b.models, ("model-detective-x", "model-skeptic-y"))
        self.assertEqual((b.outcome.state, b.outcome.lines, b.two_people), ("", (), False))
        self.assertEqual((b.reasoning, b.doubt), ("The disk is not attached and nothing uses it.", "It may hold data that somebody wants."))

    def test_a_plan_of_two_people_says_so(self):
        self.assertTrue(brief_of(make_case(), make_plan(approval_class="R3")).two_people)

    def test_an_open_plan_past_its_time_is_expired_and_has_no_answers(self):
        late = brief_of(make_case(), make_plan(expires_at=at(minutes=-1)), may_answer=True)
        self.assertEqual((late.state, late.answers, late.outcome.state), ("expired", (), "expired"))
        self.assertEqual(brief_of(make_case(), make_plan(expires_at="not a time"), may_answer=True).state, "expired")
        self.assertEqual(brief_of(make_case(), make_plan(expires_at=at()), may_answer=True).state, "expired", "a plan that ends at this moment has ended")

    def test_the_brief_is_the_same_for_the_same_records_and_a_naive_time_is_utc(self):
        one = brief_of(make_case(), make_plan())
        self.assertEqual(one, brief_of(make_case(), make_plan()))
        self.assertEqual(one, brief_of(make_case(), make_plan(), now=NOW.replace(tzinfo=None)))
        self.assertEqual(one, brief_of(make_case(), make_plan(), now=NOW.astimezone(dt.timezone(dt.timedelta(hours=-5)))))

    def test_it_cannot_be_changed_after_it_is_made(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.brief.headline = "other"  # type: ignore[misc]


class TheBriefOfADeletePublicIp(unittest.TestCase):
    def setUp(self):
        self.brief = brief_of(ip_case(), ip_plan(), may_answer=True)

    def test_it_has_the_words_of_its_own_family(self):
        b = self.brief
        self.assertEqual((b.kind, b.family), ("change", "delete-public-ip"))
        self.assertEqual(b.headline, "Delete the unassigned public IP address planted-ip-1 in group meternaut-test-rg")
        self.assertEqual(b.change, "Deletes the public IP address planted-ip-1 in resource group meternaut-test-rg. Nothing else changes.")
        self.assertEqual(b.undo.how, "A deleted public IP address cannot be restored. The address is released, and a new one can be made.")
        self.assertFalse(b.undo.reversible)
        self.assertEqual(b.risk.text, "If something still points at the address, that traffic stops, and the same address may not be given again.")
        self.assertIn("reads the public IP address again", b.rechecked)
        self.assertIn("still unassigned", b.rechecked)
        self.assertEqual((b.saving.monthly, b.saving.waiting_per_day), (3.65, 0.12))
        self.assertEqual(b.where.kind, "Public IP address")

    def test_the_facts_say_why_it_is_a_lead_and_what_it_is_like(self):
        self.assertEqual([(f.label, f.value) for f in self.brief.facts], [("Cost, last 30 days", "7.17 US dollars"), ("State", "Not assigned to anything"), ("Address", "Static"),
                                                                           ("Locks and keep tags", "None found")])


class TheBriefOfAdvice(unittest.TestCase):
    def setUp(self):
        self.case, self.plan = make_advice_case(), make_advice()
        self.brief = brief_of(self.case, self.plan, may_answer=True)

    def test_nothing_changes_in_azure_and_the_answers_are_the_five(self):
        b = self.brief
        self.assertEqual((b.kind, b.family, b.state), ("advice", "advise", "open"))
        self.assertEqual(b.headline, "Consider changing the virtual machine oversized-vm-1 in group team-apps-rg")
        self.assertEqual((b.change, b.who_acts, b.rechecked), (brief.ADVICE_CHANGE, brief.ADVICE_WHO, ""))
        self.assertEqual((b.undo.reversible, b.undo.how), (True, brief.ADVICE_UNDO))
        self.assertEqual((b.risk.level, b.risk.text), ("low", brief.ADVICE_RISK))
        self.assertEqual(b.answers, ("approve", "decline", "not_mine", "ask", "later"))
        self.assertEqual(b.where.kind, "Virtual machine")
        self.assertEqual(b.where.portal_url, f"https://portal.azure.com/#resource{VM}")

    def test_its_saving_is_a_scenario_because_azure_advisor_or_a_change_to_a_smaller_size_has_no_cost_line_of_its_own(self):
        self.assertEqual((self.brief.saving.level, self.brief.saving.monthly), ("Scenario", 120.0))
        self.assertIn("no cost line of this resource backs it", self.brief.saving.basis)

    def test_how_sure_it_is_comes_from_what_the_origin_status_of_the_case_was(self):
        self.assertEqual(confidence_of(make_advice_case(status="needs_human"), make_advice()).level, "Low")
        agreed = make_advice(preconditions={"family": "advise", "caseStatus": "proposed"})
        self.assertEqual(confidence_of(make_advice_case(status="acknowledged", confidence=0.9), agreed).level, "High")
        self.assertEqual(confidence_of(make_advice_case(status="acknowledged", confidence=0.9), make_advice()).level, "Low", "the status that the case had when the plan was made counts")

    def test_what_became_of_a_request_of_advice_is_said_in_the_words_of_advice(self):
        found = {state: brief_of(self.case, make_advice(state=state), decisions=[make_decision(plan_id="plan0002", decision=decision, approver_name="Maya", reason=reason)]).outcome
                 for state, decision, reason in (("consumed", "approve", ""), ("declined", "decline", "figure-wrong"), ("withdrawn", "not_mine", ""))}
        self.assertEqual((found["consumed"].title, found["consumed"].lines), ("Worth acting on", ("Maya said this is worth acting on.", "Nothing was changed in Azure.")))
        self.assertEqual((found["declined"].title, found["declined"].lines), ("Not worth it", ("Maya said it is not worth acting on. Reason: the figure is wrong.", "Nothing changed.")))
        self.assertEqual((found["withdrawn"].title, found["withdrawn"].result), ("Not theirs", "Not theirs"))
        self.assertEqual(found["consumed"].result, "Worth acting on")


class TheBriefWithoutAPlan(unittest.TestCase):
    def test_a_case_without_a_plan_is_information_and_asks_nothing(self):
        b = brief_of(make_case(), None, may_answer=True)
        self.assertEqual((b.kind, b.family, b.state, b.plan_id, b.plan_code, b.expires_at), ("info", "", "none", "", "", ""))
        self.assertEqual(b.headline, "Consider deleting the disk planted-disk-1 in group meternaut-test-rg")
        self.assertEqual((b.change, b.who_acts, b.answers), (brief.NO_CHANGE, "", ()))
        self.assertEqual((b.undo.reversible, b.risk.level), (True, "low"))
        self.assertEqual((b.outcome.state, b.where.name, b.where.kind), ("", "planted-disk-1", "Managed disk"))
        self.assertEqual(b.found_at, make_case().first_seen_at)

    def test_a_plan_without_a_case_still_makes_a_brief_from_the_plan_alone(self):
        b = brief_of(None, make_plan(), may_answer=True)
        self.assertEqual((b.kind, b.headline, b.case_id), ("change", "Delete the unattached disk planted-disk-1 in group meternaut-test-rg", "case0001"))
        self.assertEqual((b.confidence.level, b.confidence.because), ("Low", "No record of the review is stored."), "without the case nothing says what the reviewers thought")
        self.assertEqual((b.facts, b.reasoning, b.doubt, b.models), ((), "", "", ()))
        self.assertEqual(b.saving.monthly, 7.17)
        self.assertEqual(b.found_at, make_plan().created_at, "without a case the plan says when it was found")
        self.assertEqual(b.where.kind, "Managed disk", "a plan of a change knows what it changes")

    def test_a_case_that_ended_in_an_error_shows_no_ai_text(self):
        b = brief_of(make_case(status="error", summary="the token budget of the run was reached"), None)
        self.assertEqual((b.reasoning, b.doubt), ("", ""))
        self.assertEqual(b.headline, "Consider deleting the disk planted-disk-1 in group meternaut-test-rg")

    def test_there_is_nothing_to_show_without_both(self):
        b = brief_of(None, None)
        self.assertEqual((b.kind, b.headline, b.where.name, b.facts, b.answers), ("info", "Look at the resource this resource", "", (), ()))


class TheAnswers(unittest.TestCase):
    def test_the_answers_that_exist_depend_on_the_person_the_state_the_switches_and_the_kind(self):
        case, plan = make_case(), make_plan()
        self.assertEqual(brief_of(case, plan, may_answer=True).answers, ("approve", "decline", "not_mine", "ask", "later"))
        self.assertEqual(brief_of(case, plan, may_answer=False).answers, (), "a person who may not answer has none")
        self.assertEqual(brief_of(case, plan, may_answer=True, changes_paused=True).answers, ("decline", "not_mine", "ask", "later"), "a switch takes the approval away")
        for state in ("approved", "consumed", "declined", "withdrawn", "failed", "expired"):
            self.assertEqual(brief_of(case, make_plan(state=state), may_answer=True).answers, (), state)
        advice = brief_of(make_advice_case(), make_advice(), may_answer=True, changes_paused=True)
        self.assertEqual(advice.answers, ("decline", "not_mine", "ask", "later"), "the full stop takes the answer 'worth acting on' away from advice too")
        self.assertEqual(brief_of(case, None, may_answer=True).answers, ())


class TheConfidence(unittest.TestCase):
    """How sure it is, by code: from the second AI's verdict, the checks that fired and the share of the cited numbers that code re-checked."""

    def test_both_agree_nothing_fired_and_the_first_was_sure_is_high(self):
        found = confidence_of(make_case(confidence=0.91), make_plan())
        self.assertEqual((found.level, found.because), ("High", "Both AI reviewers agree; code read the facts itself."))
        self.assertEqual(confidence_of(make_case(confidence=None), make_plan()).level, "High")

    def test_a_first_ai_that_was_only_fairly_sure_makes_it_medium_and_one_that_was_not_sure_makes_it_low(self):
        self.assertEqual(confidence_of(make_case(confidence=0.8), make_plan()).level, "Medium")
        self.assertEqual(confidence_of(make_case(confidence=0.85), make_plan()).level, "High")
        low = confidence_of(make_case(confidence=0.6), make_plan())
        self.assertEqual(low.level, "Low")
        self.assertIn("the first AI was not sure enough", low.because)

    def test_a_check_that_held_it_back_makes_it_low_and_is_named(self):
        found = confidence_of(make_case(guards=("locked", "keep-tag", "too-new")), make_plan())
        self.assertEqual(found.level, "Low")
        self.assertEqual(found.because, "Both AI reviewers agree; a check by code held it back (a management lock covers the resource; a tag asks to keep the resource); "
                                        "code read the facts itself.")

    def test_a_finding_of_the_investigation_is_high_only_when_code_re_checked_every_number_that_the_ai_cited(self):
        investigated = dict(detector="investigation", status="proposed", confidence=0.9, facts={"metrics": {"A": 1, "B": 0}})
        self.assertEqual(confidence_of(make_case(**{**investigated, "facts": {"metrics": {"A": 1, "B": 0}, "citedMetrics": 2}})).level, "High")
        some = confidence_of(make_case(**{**investigated, "facts": {"metrics": {"A": 1, "B": 0}, "citedMetrics": 3}}))
        self.assertEqual((some.level, some.because), ("Medium", "Both AI reviewers agree; code re-checked 2 of 3 numbers."))
        none = confidence_of(make_case(**{**investigated, "facts": {}}))
        self.assertEqual((none.level, none.because), ("Low", "Both AI reviewers agree; no number backs it."))
        self.assertEqual(confidence_of(make_case(**{**investigated, "facts": {"metrics": {"A": 1}}})).because, "Both AI reviewers agree; code re-checked 1 number.")

    def test_a_second_ai_that_did_not_agree_is_low_and_the_words_say_why(self):
        base = dict(status="needs_human", detector="investigation", facts={"metrics": {"A": 1}}, confidence=0.9)
        asked = ({"step": "investigator", "ok": True}, {"step": "skeptic", "ok": True})
        models = {"investigator": "m1", "skeptic": "m2"}
        cases = (
            ({"steps": asked, "objections": ("It may be needed.",), "models": models}, "The second AI raised an objection; code re-checked 1 number."),
            ({"steps": asked, "objections": (), "models": models}, "The AI reviewers did not settle it; code re-checked 1 number."),
            ({"steps": ({"step": "investigator", "ok": True}, {"step": "skeptic", "ok": False}), "objections": (), "models": models}, "The second AI gave no verdict; code re-checked 1 number."),
            ({"steps": ({"step": "investigator", "ok": True},), "objections": (), "models": {"investigator": "m1", "skeptic": None}}, "Only one AI reviewed it; code re-checked 1 number."),
        )
        for changes, because in cases:
            with self.subTest(because=because):
                found = confidence_of(make_case(**{**base, **changes}))
                self.assertEqual((found.level, found.because), ("Low", because))

    def test_a_status_that_has_moved_on_no_longer_says_what_the_second_ai_thought(self):
        found = confidence_of(make_case(status="declined"))
        self.assertEqual(found.because, "The second AI's verdict is no longer recorded; code read the facts itself.")
        self.assertEqual(found.level, "Medium")

    def test_no_case_means_no_record_of_the_review(self):
        self.assertEqual((confidence_of(None).level, confidence_of(None).because), ("Low", "No record of the review is stored."))

    def test_the_notes_that_code_wrote_among_the_objections_are_not_a_doubt_of_the_second_ai(self):
        self.assertEqual(brief.CODE_NOTES, ("no measurement backs this finding", "the Investigator gave a confidence of", "past cases like this"))
        notes = ("no measurement backs this finding: the tools returned no number", "the Investigator gave a confidence of 0.5, under the 0.7 that a proposal needs")
        found = confidence_of(make_case(status="needs_human", objections=notes, steps=({"step": "skeptic", "ok": True},), models={"skeptic": "m"}))
        self.assertEqual(found.because, "The AI reviewers did not settle it; code read the facts itself.")
        self.assertEqual(doubt_of(make_case(objections=notes + ("A real doubt.",))), "A real doubt.")
        self.assertEqual(doubt_of(make_case(objections=notes, steps=({"step": "skeptic", "ok": True},))), "The second AI raised no objection.")

    def test_the_code_notes_are_the_ones_that_the_deciding_code_writes(self):
        from cases import decide
        self.assertTrue(decide.NO_MEASUREMENT.startswith(brief.CODE_NOTES[0]))


class TheDoubtAndTheReasoning(unittest.TestCase):
    def test_the_doubt_is_the_first_objection_of_the_second_ai_or_what_it_did_instead(self):
        self.assertEqual(doubt_of(make_case(objections=("First.", "Second."))), "First.")
        self.assertEqual(doubt_of(make_case(objections=(), models={"detective": "m", "skeptic": None}, steps=())), "The second AI was not asked.")
        self.assertEqual(doubt_of(make_case(objections=())), "The second AI gave no verdict on this finding.", "the skeptic step of the fixture is not ok")
        self.assertEqual(doubt_of(make_case(objections=(), steps=({"step": "skeptic", "ok": True},))), "The second AI raised no objection.")
        self.assertEqual(doubt_of(make_case(objections=(), status="needs_human", steps=({"step": "skeptic", "ok": True},))), "The second AI raised no objection in words.")
        self.assertEqual((doubt_of(None), doubt_of(make_case(status="error"))), ("", ""))

    def test_the_reasoning_and_the_doubt_are_cut_to_240_characters_and_are_one_line(self):
        long = make_case(summary="word " * 100 + "\n<b>x</b>", objections=("y" * 500,))
        self.assertLessEqual(len(reasoning_of(long)), 240)
        self.assertLessEqual(len(doubt_of(long)), 240)
        self.assertNotIn("\n", reasoning_of(long))
        self.assertEqual((reasoning_of(None), reasoning_of(make_case(status="error"))), ("", ""))


class TheFacts(unittest.TestCase):
    def test_at_most_five_rows_the_cost_first_then_a_check_that_held_it_back_then_what_was_measured(self):
        case = make_case(guards=("locked",), facts={"metrics": {"Percentage CPU": 3.2, "Network In": 1536, "Disk Reads": 0}, "metricUnits": {"Percentage CPU": "Percent",
                         "Network In": "Bytes", "Disk Reads": "Count"}, "metricDays": {"Percentage CPU": 30, "Network In": 7, "Disk Reads": 30}, "diskState": "unattached"})
        rows = facts_of(case)
        self.assertEqual(len(rows), 5)
        self.assertEqual([r.label for r in rows][:2], ["Cost, last 30 days", "Held back by"])
        self.assertEqual([(r.label, r.value, r.source) for r in rows[2:4]],
                         [("Disk Reads", "0 in 30 days", "Azure Monitor, 30 days"), ("Network In", "1.5 KB in 7 days", "Azure Monitor, 7 days")],
                         "what was measured: the ones with nothing recorded first, and two at most")
        self.assertEqual(rows[1].value, "A management lock covers the resource.")

    def test_the_units_of_a_measurement_are_said_in_words(self):
        for total, unit, expected in ((3.2, "Percent", "3.2%"), (1536, "Bytes", "1.5 KB"), (5 * 1024 ** 3, "Bytes", "5 GB"), (12, "Seconds", "12 seconds"), (5, "Milliseconds", "5 ms"),
                                      (2.5, "CountPerSecond", "2.5 per second"), (2048, "BytesPerSecond", "2 KB per second"), (0, "Count", "0"), (7, None, "7"), (7, "Unspecified", "7"),
                                      (3, "Foo", "3 Foo"), (1234567, "Count", "1,234,567"), (0.5, "Percent", "0.5%"), (-1536, "Bytes", "-1.5 KB"), (500, "bytes", "500 bytes")):
            with self.subTest(total=total, unit=unit):
                self.assertEqual(quantity(total, unit), expected)
        for bad in (None, "x", True, math.nan, math.inf, [1]):
            self.assertEqual(quantity(bad, "Count"), "")
        self.assertEqual(quantity(3, "x" * 100), "3 " + "x" * 21 + "...")

    def test_a_number_has_thousands_separated_at_most_two_decimals_and_no_trailing_zero(self):
        for value, expected in ((1234567.891, "1,234,567.89"), (5.0, "5"), (0.5, "0.5"), (0, "0"), (2.50, "2.5"), (1000, "1,000"), (True, ""), (None, ""), (math.nan, ""), ("5", "")):
            with self.subTest(value=value):
                self.assertEqual(number_text(value), expected)
        self.assertEqual(days_text(1), "1 day")
        self.assertEqual((days_text(30), days_text(0), days_text(-1), days_text("30"), days_text(True), days_text(None)), ("30 days", "", "", "", "", ""))

    def test_the_typed_facts_say_what_the_resource_is_like_and_the_row_for_the_age_is_made_today_or_days(self):
        case = make_case(facts={"ageDays": 0, "sizeGb": "up to 128", "sku": "premium_lrs", "tier": "basic", "workers": 2, "vcpu": 8, "sizeFamily": "D", "allocation": "static"})
        labels = {r.label: r.value for r in facts_of(dataclasses.replace(case, facts={"ageDays": 0}))}
        self.assertEqual(labels["Age"], "Made today")
        every = {}
        for key, label in (("ageDays", "Age"), ("sizeGb", "Size"), ("sku", "Type"), ("tier", "Tier"), ("workers", "Workers"), ("allocation", "Address")):
            row = [r for r in brief._typed_facts(dataclasses.replace(case, facts={key: case.facts[key]})) if r.label == label]
            every[label] = row[0].value
        self.assertEqual(every, {"Age": "Made today", "Size": "up to 128 GB", "Type": "Premium SSD (LRS)", "Tier": "Basic", "Workers": "2", "Address": "Static"})
        self.assertEqual([r.value for r in brief._typed_facts(dataclasses.replace(case, facts={"vcpu": 8, "sizeFamily": "D"})) if r.label == "Size"], ["8 vCPUs, family D"])
        self.assertEqual([r.value for r in brief._typed_facts(make_case(facts={"ageDays": 12})) if r.label == "Age"], ["12 days"])

    def test_a_value_that_is_not_one_of_the_known_shapes_is_not_a_fact(self):
        self.assertEqual([r.label for r in brief._typed_facts(make_case(facts={"sizeGb": "<script>", "sku": "other", "ageDays": -1, "workers": True, "allocation": "other"}))],
                         ["State"])

    def test_the_last_change_comes_from_the_owner_record_and_the_checks_that_found_nothing_say_so(self):
        rows = facts_of(make_case(owner={"changedBy": "bob@example.com", "changedAt": "2026-10-01T08:00:00Z", "lookedUp": True}))
        self.assertIn(("Last change", "2026-10-01 by bob@example.com", "Azure Activity Log"), [(r.label, r.value, r.source) for r in rows])
        self.assertEqual([r.value for r in facts_of(make_case()) if r.label == "Locks and keep tags"], ["None found"])
        self.assertEqual([r for r in facts_of(make_case(guards=("locked",))) if r.label == "Locks and keep tags"], [])
        self.assertEqual(facts_of(None), ())

    def test_a_case_without_a_cost_figure_has_no_cost_row(self):
        self.assertNotIn("Cost, last 30 days", [r.label for r in facts_of(make_case(cost_usd_30d=None))])
        self.assertEqual([r.value for r in facts_of(make_case(cost_usd_30d=0.0)) if r.label == "Cost, last 30 days"], ["0.00 US dollars"])


class TheSaving(unittest.TestCase):
    """What it is worth, in US dollars a month with its level and its basis, or why there is no figure."""

    def test_expected_when_cost_lines_back_it_with_the_cost_of_waiting(self):
        saving = brief_of(make_case(), make_plan(saving_usd_month=41.2, waiting_costs_usd_day=1.37)).saving
        self.assertEqual((saving.monthly, saving.level, saving.basis, saving.waiting_per_day), (41.2, "Expected", "the cost lines of the last 30 days", 1.37))
        self.assertEqual(brief_of(make_case(), make_plan(saving_usd_month=30.0, waiting_costs_usd_day=None)).saving.waiting_per_day, 1.0, "a month of 30 days")

    def test_scenario_when_azure_advisor_or_a_proposed_change_is_the_only_basis(self):
        for case in (make_case(detector="advisor-cost"), make_case(detector="investigation", recommendation="change")):
            with self.subTest(detector=case.detector):
                saving = brief_of(case, make_plan()).saving
                self.assertEqual(saving.level, "Scenario")
        self.assertEqual(brief_of(make_case(detector="investigation", recommendation="delete"), make_plan()).saving.level, "Expected")

    def test_verified_only_when_the_cost_lines_after_the_change_show_no_cost(self):
        check = {"gone": True, "costAfterUsd": 0.0, "costBeforeUsd30d": 41.2, "currency": "USD"}
        verified = brief_of(make_case(), make_plan(state="consumed"), action=make_action(state="verified", verification=check)).saving
        self.assertEqual((verified.monthly, verified.level), (41.2, "Verified"))
        for changes in ({"costAfterUsd": 1.0}, {"costBeforeUsd30d": 0}, {"costAfterUsd": None}):
            with self.subTest(changes=changes):
                still = brief_of(make_case(), make_plan(state="consumed"), action=make_action(state="verified", verification={**check, **changes})).saving
                self.assertEqual(still.level, "Expected")
        self.assertEqual(brief_of(make_case(), make_plan(state="consumed"), action=make_action(state="done", verification=check)).saving.level, "Expected")

    def test_no_figure_says_why_in_one_phrase(self):
        none = brief_of(make_case(saving_usd_month=None, cost_usd_30d=None), make_plan(saving_usd_month=None)).saving
        self.assertEqual((none.monthly, none.level, none.why_none), (None, "", "No cost line of the last 30 days was read for this resource."))
        free = brief_of(make_case(cost_usd_30d=0.0), make_plan(saving_usd_month=0)).saving
        self.assertEqual(free.why_none, "The resource had no cost in the last 30 days.")
        costly = brief_of(make_case(cost_usd_30d=848.75, saving_usd_month=None), make_plan(saving_usd_month=None)).saving
        self.assertEqual((costly.monthly, costly.why_none), (None, "The resource cost 848.75 US dollars in the last 30 days. What a change would save was not worked out."))
        self.assertNotIn("No cost line", costly.why_none, "a cost that is known is never said to be missing")
        self.assertEqual([none.specific, free.specific, costly.specific], [False, False, False], "that no saving was worked out from the cost that was read is not a reason of the finding's own")
        for bad in (-5.0, math.nan, math.inf, True, "7"):
            with self.subTest(figure=bad):
                self.assertIsNone(brief_of(make_case(), make_plan(saving_usd_month=bad)).saving.monthly)

    def test_money_is_in_us_dollars_with_two_decimals(self):
        for value, expected in ((41.2, "41.20 US dollars"), (1234.5, "1,234.50 US dollars"), (0, "0.00 US dollars"), (0.005, "0.01 US dollars"), (-3, "-3.00 US dollars")):
            with self.subTest(value=value):
                self.assertEqual(usd_text(value), expected)
        for bad in (None, "5", True, math.nan, math.inf):
            self.assertEqual(usd_text(bad), "")

    def test_the_words_of_money_never_say_that_something_was_saved(self):
        for text in (usd_text(41.2), brief_of(make_case(), make_plan()).saving.basis, brief.WHO_ACTS, brief.ADVICE_CHANGE, brief.ADVICE_RISK):
            self.assertNotRegex(text, r"\b(saved|saves)\b")


WORKSPACE = "microsoft.operationalinsights/workspaces"
WORKSPACE_ID = f"/subscriptions/{SUB}/resourceGroups/rg-demo/providers/Microsoft.OperationalInsights/workspaces/ws-demo"
LINE = {"kind": "Syslog", "gb": 5.0, "share": 0.05, "runs": 0}


def digest_of(**changes) -> dict:
    """What cases/unread.py keeps in the facts of the case of a workspace: 60 of its 100 GB are read by nothing, and it cost 80 US dollars."""
    values = {"days": 30, "billableGb": 100.0, "unreadGb": 60.0, "share": 0.6, "runsRecorded": True, "more": 0, "unknown": 0, "costUsd30d": 80.0, "savingUsd": 48.0,
              "kinds": [{"kind": "AzureDiagnostics", "gb": 40.0, "share": 0.4, "runs": 0}, {"kind": "Syslog", "gb": 20.0, "share": 0.2, "runs": 0, "writers": ["microsoft.compute/virtualmachines"]}]}
    values.update(changes)
    return values


def workspace_case(found=None, **changes):
    values = dict(resource_id=WORKSPACE_ID, resource_name="ws-demo", resource_type=WORKSPACE, resource_group="rg-demo", saving_usd_month=None, cost_usd_30d=80.0,
                  facts={"unread": digest_of() if found is None else found})
    values.update(changes)
    return make_advice_case(**values)


def workspace_plan(**changes):
    values = dict(resource_id=WORKSPACE_ID, resource_name="ws-demo", resource_group="rg-demo", saving_usd_month=48.0, waiting_costs_usd_day=1.6,
                  title="Consider changing the Log Analytics workspace ws-demo in group rg-demo")
    values.update(changes)
    return make_advice(**values)


class TheDataThatNothingReads(unittest.TestCase):
    """What a workspace takes in and nothing reads: the digest that code kept in the facts of the case, and what the brief makes of it."""

    def test_the_brief_has_the_figure_as_a_scenario_with_its_method_the_lines_and_the_choices(self):
        b = brief_of(workspace_case(), workspace_plan())
        self.assertEqual(b.headline, "Consider changing the Log Analytics workspace ws-demo in group rg-demo")
        self.assertEqual((b.saving.monthly, b.saving.level, b.saving.waiting_per_day), (48.0, "Scenario", 1.6))
        self.assertEqual(b.saving.basis, "the workspace's cost of the last 30 days times the share of its data that nothing reads, about 60 percent")
        self.assertEqual(b.unread.sentence, "About 60 percent of what this workspace is billed for is data that nothing reads.")
        self.assertEqual(b.unread.volume, "That is 60 GB of the 100 GB that it took in over 30 days.")
        self.assertEqual([(line.kind, line.gb, line.percent, line.writers) for line in b.unread.lines],
                         [("AzureDiagnostics", "40 GB", "40 percent", ""), ("Syslog", "20 GB", "20 percent", "Virtual machine")])
        self.assertEqual(b.unread.lines[0].reads, "Read by 0 rules, 0 saved searches and 0 workbooks; 0 queries run")
        self.assertEqual((len(b.options), b.unread.more, b.unread.note), (3, 0, ""))

    def test_a_digest_that_is_not_as_it_should_be_shows_nothing_and_never_something_else(self):
        self.assertIsNone(brief.unread_of(None))
        self.assertIsNone(brief.unread_of(make_advice_case(facts={})))
        self.assertIsNone(brief.unread_of(make_advice_case(facts=None)))
        for name, found in (("text", "text"), ("a list", [1]), ("no kinds", digest_of(kinds=[])), ("kinds that are not a list", digest_of(kinds="x")),
                            ("items that are not kinds", digest_of(kinds=[5, None, "x", ["y"]])), ("a share of nothing", digest_of(share=0)), ("a share above 1", digest_of(share=1.2)),
                            ("a share that is text", digest_of(share="0.6")), ("a share that is not a number", digest_of(share=math.nan)), ("more than the whole", digest_of(unreadGb=120.0)),
                            ("nothing that is unread", digest_of(unreadGb=0)), ("no days", digest_of(days=0)), ("days that are a flag", digest_of(days=True)),
                            ("days that are text", digest_of(days="30")), ("a kind that something reads", digest_of(kinds=[{**LINE, "runs": 3}])),
                            ("a kind with no name", digest_of(kinds=[{**LINE, "kind": ""}])), ("a negative volume", digest_of(kinds=[{**LINE, "gb": -5.0}])),
                            ("a share above 1", digest_of(kinds=[{**LINE, "share": 2}])), ("runs that are text", digest_of(kinds=[{**LINE, "runs": "0"}])),
                            ("runs that are a flag", digest_of(kinds=[{**LINE, "runs": False}]))):
            with self.subTest(digest=name):
                self.assertIsNone(brief.unread_of(workspace_case(found)))
        found = brief.unread_of(workspace_case(digest_of(kinds=[{**LINE, "runs": 3}, LINE, "x"])))
        self.assertEqual([line.kind for line in found.lines], ["Syslog"], "a kind that is read is left out, and the others stay")

    def test_six_lines_are_shown_what_is_left_is_counted_and_what_was_not_counted_is_said(self):
        kinds = [{"kind": f"K{n}", "gb": 1.0, "share": 0.01, "runs": 0} for n in range(9)]
        found = brief.unread_of(workspace_case(digest_of(kinds=kinds, more=2)))
        self.assertEqual(([line.kind for line in found.lines], found.more), ([f"K{n}" for n in range(6)], 5), "the three that are left out and the two that the digest counted")
        found = brief.unread_of(workspace_case(digest_of(unknown=2, runsRecorded=False, kinds=[{**LINE, "runs": None}])))
        self.assertEqual(found.lines[0].reads, "Read by 0 rules, 0 saved searches and 0 workbooks; queries run: not recorded")
        self.assertEqual(found.note, "What reads 2 other kinds of data could not be read, so they are not counted. "
                                     "The queries that people run were not counted: the record of them is off or could not be read in full.")
        one = brief.unread_of(workspace_case(digest_of(unknown=1)))
        self.assertEqual(one.note, "What reads 1 other kind of data could not be read, so it is not counted.")

    def test_the_figure_is_the_one_of_the_digest_when_it_is_above_nothing_and_not_above_the_cost(self):
        for figure, expected in ((48.0, 48.0), (47.996, 48.0), (80.0, 80.0), (80.004, 80.0), (80.01, None), (0, None), (-1.0, None), (True, None), ("48", None), (math.nan, None),
                                 (math.inf, None), (None, None)):
            with self.subTest(figure=figure):
                self.assertEqual(brief.unread_saving(workspace_case(digest_of(savingUsd=figure))), expected)
        self.assertIsNone(brief.unread_saving(workspace_case(cost_usd_30d=None)))
        self.assertIsNone(brief.unread_saving(workspace_case(cost_usd_30d=40.0)), "a figure above what the resource cost is not a figure")
        self.assertIsNone(brief.unread_saving(workspace_case({"missing": "volume"})))
        self.assertIsNone(brief.unread_saving(None))

    def test_a_figure_above_the_cost_is_not_shown_by_the_brief_and_a_case_without_a_request_shows_the_one_of_the_digest(self):
        b = brief_of(workspace_case(cost_usd_30d=40.0), workspace_plan(saving_usd_month=None, waiting_costs_usd_day=None))
        self.assertIsNone(b.saving.monthly)
        info = brief_of(workspace_case(), None)
        self.assertEqual((info.kind, info.saving.monthly, info.saving.level, info.options), ("info", 48.0, "Scenario", ()))

    def test_a_digest_that_says_what_is_missing_gives_no_figure_and_the_sentence_of_what_is_missing(self):
        for missing in ("volume", "readers"):
            with self.subTest(missing=missing):
                b = brief_of(workspace_case({"missing": missing}), workspace_plan(saving_usd_month=None, waiting_costs_usd_day=None))
                self.assertEqual((b.saving.monthly, b.saving.why_none, b.saving.specific), (None, brief.UNREAD_MISSING[missing], True))
                self.assertLess(len(b.saving.why_none), 200)
                self.assertEqual((b.unread, b.options), (None, ()))
        other = brief_of(workspace_case({"missing": "anything else"}), workspace_plan(saving_usd_month=None, waiting_costs_usd_day=None)).saving
        self.assertEqual(other.why_none, "The resource cost 80.00 US dollars in the last 30 days. What a change would save was not worked out.")
        self.assertFalse(other.specific)

    def test_the_figure_of_advisor_stays_when_the_finding_has_one_and_the_lines_are_still_shown(self):
        b = brief_of(workspace_case(saving_usd_month=12.0), workspace_plan(saving_usd_month=12.0, waiting_costs_usd_day=0.4))
        self.assertEqual((b.saving.monthly, b.saving.level, b.saving.basis), (12.0, "Scenario", "Azure Advisor's own estimate: no cost line of this resource backs it"))
        self.assertEqual(len(b.unread.lines), 2)

    def test_the_two_cited_measurements_are_left_out_of_the_facts_when_the_lines_say_more_and_stay_when_they_do_not(self):
        measured = {"metrics": {"Billable GB Syslog": 20.0, "Readers Syslog": 0}, "metricUnits": {"Billable GB Syslog": "GB"}, "metricDays": {"Billable GB Syslog": 30, "Readers Syslog": 30}}
        self.assertEqual([fact.label for fact in facts_of(workspace_case(facts={"unread": digest_of(), **measured}))], ["Cost, last 30 days", "Locks and keep tags"])
        labels = [fact.label for fact in facts_of(workspace_case(facts={"unread": {"missing": "readers"}, **measured}))]
        self.assertIn("Billable GB Syslog", labels)
        self.assertIn("Readers Syslog", labels)

    def test_the_choices_are_code_s_words_they_name_the_listed_kinds_and_the_writers_and_never_an_invented_one(self):
        unread = brief.unread_of(workspace_case())
        first, second, third = brief.options_of(unread, True)
        self.assertTrue(first.what.startswith("Stop sending AzureDiagnostics and Syslog at the source: the log categories that a diagnostic setting sends, or the data collection rule that writes it."))
        self.assertIn("On the last closed day, the largest writers of Syslog were: Virtual machine.", first.what)
        self.assertNotIn("writers of AzureDiagnostics", first.what)
        self.assertIn("a transformation in the data collection rule", second.what)
        self.assertIn("Basic or Auxiliary plan", third.what)
        for option in (first, second, third):
            self.assertTrue(option.risk, "each choice says what is lost or at risk")
        self.assertTrue(third.risk.endswith("That lowers the bill by less than the figure above."))
        self.assertFalse(brief.options_of(unread, False)[2].risk.endswith("That lowers the bill by less than the figure above."), "no figure, no remark about it")
        nothing_shown = brief.unread_of(workspace_case(digest_of(kinds=[{**LINE, "writers": [5, None, ""]}])))
        self.assertNotIn("largest writers", brief.options_of(nothing_shown, False)[0].what)
        many = brief.unread_of(workspace_case(digest_of(more=2, kinds=[{**LINE, "kind": name} for name in ("A", "B", "C", "D", "E")])))
        self.assertTrue(brief.options_of(many, False)[0].what.startswith("Stop sending A, B, C and 4 more at the source"))
        self.assertEqual((brief.options_of(None, True), brief.options_of(dataclasses.replace(unread, lines=()), True)), ((), ()))

    def test_only_a_request_to_a_person_for_advice_has_the_choices(self):
        self.assertEqual(len(brief_of(workspace_case(), workspace_plan()).options), 3)
        self.assertEqual(brief_of(workspace_case(), None).options, ())
        self.assertEqual(brief_of(make_advice_case(), make_advice()).options, (), "advice about anything else has none")
        self.assertIsNone(brief_of(make_advice_case(), make_advice()).unread)
        self.assertEqual(brief_of(make_case(), make_plan()).options, ())

    def test_a_name_is_cut_and_the_text_of_the_estate_is_plain_text(self):
        hostile = "<script>alert(1)</script>[x](javascript:alert(1)) https://evil.example/x\u202e" + "n" * 300
        found = brief.unread_of(workspace_case(digest_of(kinds=[{**LINE, "kind": "t1", "name": hostile, "writers": [hostile]}])))
        (line,) = found.lines
        self.assertLessEqual(len(line.kind), 64)
        for text in (line.kind, line.writers, " ".join(option.what for option in brief.options_of(found, True))):
            self.assertNotRegex(text, r"https?://|\]\(|\u202e|\n")
        self.assertIn("...", line.kind)


class TheOwner(unittest.TestCase):
    def test_who_the_resource_probably_belongs_to_is_said_as_plain_facts(self):
        owner = owner_of(make_case(owner={"tagOwner": "alice@example.com", "tagName": "owner", "createdBy": "bob@example.com", "createdAt": "2026-03-01T08:00:00Z",
                                         "changedBy": "carol@example.com", "changedAt": "2026-10-01", "lookedUp": True}))
        self.assertEqual((owner.known, owner.text), (True, "Tag owner: alice@example.com. Created by bob@example.com on 2026-03-01. "
                                                          "Last changed by carol@example.com on 2026-10-01."))

    def test_the_tag_is_named_once_and_by_its_own_name(self):
        self.assertEqual(owner_of(make_case(owner={"tagOwner": "platform", "tagName": "team", "lookedUp": True})).text, "Tag team: platform.")
        self.assertEqual(owner_of(make_case(owner={"tagOwner": "platform", "lookedUp": True})).text, "Tag owner: platform.")

    def test_an_identity_that_is_only_an_id_is_said_to_be_an_identity_and_not_taken_for_a_name(self):
        guid = "3F2A9C1E-5B7D-4E8A-9C3B-1D2E3F4A5B6C"
        said = f"an application or service identity (id {guid.lower()})"
        self.assertEqual(brief.who_text(guid), said)
        self.assertEqual(brief.who_text("bob@example.com"), "bob@example.com")
        self.assertEqual(brief.who_text("3f2a9c1e-5b7d-4e8a-9c3b-1d2e3f4a5b6c0"), "3f2a9c1e-5b7d-4e8a-9c3b-1d2e3f4a5b6c0", "more than an id is not an id")
        self.assertEqual(brief.who_text(None), "")
        text = owner_of(make_case(owner={"createdBy": guid, "changedBy": guid, "changedAt": "2026-10-01", "lookedUp": True})).text
        self.assertEqual(text, f"Created by {said}. Last changed by {said} on 2026-10-01.")
        row = [r for r in facts_of(make_case(owner={"changedBy": guid, "changedAt": "2026-10-01T08:00:00Z", "lookedUp": True})) if r.label == "Last change"]
        self.assertEqual([r.value for r in row], [f"2026-10-01 by {said}"])

    def test_a_missing_owner_is_said_and_so_is_a_lookup_that_was_not_made(self):
        self.assertEqual(owner_of(make_case()), brief.OwnerLine(False, "Meternaut has not looked up who owns this resource yet."))
        self.assertEqual(owner_of(None), brief.OwnerLine(False, "Meternaut has not looked up who owns this resource yet."))
        self.assertEqual(owner_of(make_case(owner={"lookedUp": True})), brief.OwnerLine(False, "No owner is recorded on the resource."))
        self.assertEqual(owner_of(make_case(owner={"lookedUp": True, "tagOwner": "   "})).known, False)

    def test_a_part_of_the_record_is_enough_and_a_key_that_is_not_known_is_left_out(self):
        self.assertEqual(owner_of(make_case(owner={"createdBy": "bob@example.com", "somethingNew": "x"})).text, "Created by bob@example.com.")
        self.assertEqual(owner_of(make_case(owner={"changedAt": "2026-10-01T08:00:00Z"})).text, "Last changed on 2026-10-01.")

    def test_text_from_the_estate_is_data_and_is_made_safe_by_plain(self):
        owner = owner_of(make_case(owner={"tagOwner": "[mail me](javascript:alert(1)) https://evil.example\u202e", "createdBy": "x" * 500, "lookedUp": True}))
        self.assertNotIn("[", owner.text)
        self.assertNotIn("://", owner.text)
        self.assertNotIn("\u202e", owner.text)
        self.assertLessEqual(len(owner.text), 80 + 80 + 100)


class TheOutcome(unittest.TestCase):
    def outcome(self, state, *, action=None, decisions=(), case=None):
        return brief_of(case or make_case(), make_plan(state=state), action=action, decisions=decisions).outcome

    def test_a_request_that_is_open_has_no_outcome(self):
        self.assertEqual(self.outcome("open").state, "")

    def test_expired_nobody_answered(self):
        found = self.outcome("expired")
        self.assertEqual((found.state, found.title, found.lines, found.result, found.at), ("expired", "Expired", ("Nobody answered in time.", "Nothing changed."),
                                                                                       "Expired, nobody answered", make_plan().expires_at))

    def test_declined_names_who_and_the_reason(self):
        found = self.outcome("declined", decisions=[make_decision(decision="decline", reason="handled", approver_name="Maya")])
        self.assertEqual((found.title, found.lines, found.by), ("Declined", ("Declined by Maya. Reason: it is already handled.", "Nothing changed."), "Maya"))
        self.assertEqual(self.outcome("declined").lines[0], "Declined by A person.")

    def test_approved_says_that_the_change_is_being_made_or_waits_for_the_extra_sign_in_check(self):
        queued = self.outcome("approved", action=make_action(state="queued"), decisions=[make_decision()])
        self.assertEqual(queued.lines, ("Approved by Tino.", "The change is being made now."))
        waiting = self.outcome("approved", action=make_action(state="queued", step_up=True), decisions=[make_decision()])
        self.assertEqual(waiting.lines[1], brief.WAITING_FOR_THE_CHECK)
        self.assertEqual(self.outcome("approved", action=make_action(state="running", step_up=True), decisions=[make_decision()]).lines[1], "The change is being made now.")

    def test_done_and_verified_say_that_the_change_was_made_with_the_approvers_own_rights(self):
        done = self.outcome("consumed", action=make_action(state="done", result="Deleted. Azure no longer lists the resource.", verification={"gone": True}), decisions=[make_decision()])
        self.assertEqual((done.state, done.title), ("done", "Done"))
        self.assertEqual(done.lines, ("Approved by Tino, and made with their own Azure rights.", "Deleted. Azure no longer lists the resource."))
        verified = self.outcome("consumed", action=make_action(state="verified", result="Deleted.", verification={"gone": True, "costAfterUsd": 0.0, "costBeforeUsd30d": 7.17}),
                                decisions=[make_decision()])
        self.assertEqual((verified.title, verified.result), ("Done and checked", "Done and checked"))
        self.assertIn("The 30 days before the change cost 7.17 US dollars.", verified.lines)
        unknown = self.outcome("consumed", action=make_action(state="unknown", result="Azure accepted the delete."), decisions=[make_decision()])
        self.assertEqual(unknown.result, "Done, not confirmed yet")

    def test_failed_says_what_went_wrong(self):
        found = self.outcome("failed", action=make_action(state="failed", error="Azure refused (403)."), decisions=[make_decision()])
        self.assertEqual((found.state, found.title, found.lines), ("failed", "Not made", ("Azure refused (403).",)))
        self.assertEqual(self.outcome("failed", action=make_action(state="failed", error="", result=""), decisions=[make_decision()]).lines, ("The change could not be finished.",))

    def test_the_decisive_answer_is_the_latest_of_its_kind(self):
        first = make_decision(decision="decline", approver_name="Old", at=at(hours=-3))
        second = make_decision(decision="decline", approver_name="New", at=at(hours=-1), approver_oid="b" * 36)
        self.assertEqual(self.outcome("declined", decisions=[first, second]).by, "New")


class TheOrderOfAList(unittest.TestCase):
    def test_the_larger_saving_first_a_request_with_no_figure_last_then_the_one_that_waited_longest(self):
        made = [brief_of(make_case(first_seen_at=at(days=-days)), make_plan(plan_id=f"p{n}", saving_usd_month=saving)) for n, (saving, days) in
                enumerate(((5.0, 1), (50.0, 2), (None, 9), (50.0, 7), (5.0, 3)))]
        order = [b.plan_id for b in sorted(made, key=order_key)]
        self.assertEqual(order, ["p3", "p1", "p4", "p0", "p2"])

    def test_two_requests_that_tie_are_ordered_by_their_id_so_that_a_list_is_the_same_every_time(self):
        a, b = brief_of(make_case(), make_plan(plan_id="pa")), brief_of(make_case(), make_plan(plan_id="pb"))
        self.assertEqual([x.plan_id for x in sorted([b, a], key=order_key)], ["pa", "pb"])


class TheSmallWords(unittest.TestCase):
    def test_how_long_ago_in_days_and_in_words(self):
        for days, words in ((0, "today"), (1, "yesterday"), (5, "5 days ago"), (14, "2 weeks ago"), (59, "8 weeks ago"), (60, "2 months ago"), (400, "13 months ago")):
            with self.subTest(days=days):
                self.assertEqual(brief.ago_text(NOW, at(days=-days)), (days, words))
        self.assertEqual(brief.ago_text(NOW, "not a time"), (None, ""))
        self.assertEqual(brief.ago_text(NOW, at(days=3)), (0, "today"), "a time ahead is not a negative age")

    def test_the_kind_of_a_resource_in_words(self):
        self.assertEqual(kind_words("Microsoft.Compute/Disks"), ("Managed disk", "disk"))
        self.assertEqual(kind_words("Microsoft.OperationalInsights/Workspaces"), ("Log Analytics workspace", "Log Analytics workspace"))
        self.assertEqual(kind_words("Microsoft.CognitiveServices/accounts"), ("AI services account", "AI services account"))
        self.assertEqual(kind_words("microsoft.thing/things"), ("microsoft.thing/things", "resource"))
        self.assertEqual(kind_words(""), ("Resource", "resource"))
        every_type = {kind.type for family in registry.REGISTRY for kind in family.kinds}
        self.assertEqual(every_type - set(brief.TYPE_WORDS), set(), "every kind of resource that a family of change changes has words in the brief")

    def test_the_portal_address_is_made_only_from_the_id_of_one_resource(self):
        good = f"/subscriptions/{SUB}/resourceGroups/rg-a/providers/Microsoft.Compute/disks/d-1"
        self.assertEqual(portal_url(good), f"https://portal.azure.com/#resource{good}")
        sub = f"/subscriptions/{SUB}/resourceGroups/rg-a/providers/Microsoft.Sql/servers/s/databases/db"
        self.assertEqual(portal_url(sub), f"https://portal.azure.com/#resource{sub}")
        for bad in ("", None, 'x"><script>', "javascript:alert(1)", good + '"', good + " x", good + "?x=1", good + "#y", "/subscriptions/x/resourceGroups/g/providers/p/t/n", good.replace("rg-a", "rg a"),
                    good + "/" + "x" * 101, "https://evil.example/" + good, good + "\n", good.replace("Compute/disks/d-1", "Compute"), good.upper().replace(SUB.upper(), "z" * 36)):
            with self.subTest(bad=bad):
                self.assertEqual(portal_url(bad), "")

    def test_the_models_that_took_part_are_named_once_each_and_only_when_they_are_text(self):
        self.assertEqual(models_of(make_case(models={"detective": "m1", "skeptic": "m1"})), ("m1",))
        self.assertEqual(models_of(make_case(models={"detective": "m1", "skeptic": None})), ("m1",))
        self.assertEqual(models_of(make_case(models={"a": 5, "b": " ", "c": "m3"})), ("m3",))
        self.assertEqual((models_of(None), models_of(make_case(models={}))), ((), ()))
        self.assertEqual(models_of(make_case(models={"a": "x\u202e[y](javascript:z)"})), ("x(y)(javascript:z)",))

    def test_the_footer_says_that_an_ai_wrote_it_why_the_person_got_it_and_whom_to_talk_to(self):
        self.assertEqual(written_by(("m1", "m2")), "Written by an AI (models: m1, m2); a person approves every change.")
        self.assertEqual(written_by(()), "Written by an AI; a person approves every change.")
        self.assertEqual(footer_line(("m1",), "You got this because you are on my list of people.", ("Olga (olga@example.com)",)),
                         "Written by an AI (models: m1); a person approves every change. You got this because you are on my list of people. Talk to a person: Olga (olga@example.com).")
        self.assertTrue(footer_line((), "Why.").endswith("Talk to a person: whoever put you on my list of people."))

    def test_a_person_to_talk_to_is_plain_text_with_the_address(self):
        self.assertEqual(contact_text("Olga", "olga@example.com"), "Olga (olga@example.com)")
        self.assertEqual((contact_text("Olga", ""), contact_text("", "olga@example.com"), contact_text(None, None)), ("Olga", "olga@example.com", ""))
        hostile = contact_text("[Olga](javascript:alert(1))\u202e", "o@example.com\nBcc: x@example.com")
        self.assertNotIn("[", hostile)
        self.assertNotIn("\n", hostile)
        self.assertNotIn("\u202e", hostile)

    def test_what_the_check_after_a_change_found_without_saying_the_same_twice(self):
        check = {"gone": True, "costAfterUsd": 0.0, "costBeforeUsd30d": 7.17, "currency": "USD", "note": "Confirmed."}
        self.assertEqual(check_lines(check), ["Azure no longer lists the resource.", "Cost lines since the change: 0.00 US dollars.", "The 30 days before the change cost 7.17 US dollars.",
                                              "Confirmed."])
        self.assertEqual(check_lines(check, "Deleted. Azure no longer lists the resource.")[0], "Cost lines since the change: 0.00 US dollars.")
        self.assertEqual(check_lines({"gone": False}), ["Azure still lists the resource."])
        self.assertEqual(check_lines({"costAfterUsd": 3.0, "currency": "EUR"}), [], "a figure in another currency is not shown as dollars")
        self.assertEqual(check_lines({}), [])


class ThePlainSanitiser(unittest.TestCase):
    """`plain` is the one rule for text that did not come from code, in every render: a page, a letter and a card."""

    def test_what_it_makes_of_each_kind_of_hostile_text(self):
        for text, expected in (
                ("[click here](javascript:alert(1))", "(click here)(javascript:alert(1))"),
                ("![x](https://evil.example/p.png)", "!(x)(https: //evil.example/p.png)"),
                ("see https://evil.example/login now", "see https: //evil.example/login now"),
                ("<https://evil.example/login>", "<https: //evil.example/login>"),
                ("a\u202eb\u200bc\x00d\r\ne", "abcd e"),
                ("zero\u200bwidth\u200djoin\ufeffbom\u2060", "zerowidthjoinbom"),
                ("line one\nline two\u2028line three\u2029line four", "line one line two line three line four"),
                ("tab\tseparated\vvertical\x0cform", "tab separated vertical form"),
                ("\x00\x07\x1b[31mred\x1b[0m", "(31mred(0m"),
                ("  spaced   out  ", "spaced out"), ("plain text stays", "plain text stays"), (None, ""), (12, "12"), ("", ""),
                ("tag \U000e0041 character", "tag character"), ("private \ue000 use", "private use")):
            with self.subTest(text=text):
                self.assertEqual(plain(text), expected)

    def test_every_hostile_text_comes_out_as_one_safe_line_whatever_the_length(self):
        for text in INJECTIONS:
            for limit in (10, 120, 400):
                with self.subTest(text=text[:30], limit=limit):
                    found = plain(text, limit)
                    self.assertLessEqual(len(found), limit)
                    self.assertEqual(found, found.strip())
                    self.assertNotIn("\n", found)
                    self.assertNotIn("\r", found)
                    for ch in found:
                        self.assertNotIn(unicodedata.category(ch), ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"), repr(ch))
                    self.assertNotIn("[", found)
                    self.assertNotIn("]", found)
                    self.assertNotRegex(found, r"(?i)\b[a-z][a-z0-9+.-]*://")
                    self.assertEqual(plain(found, limit), found, "plain is idempotent")

    def test_a_long_text_is_cut_with_an_ellipsis_and_a_short_one_is_not(self):
        self.assertEqual(plain("x" * 200, 20), "x" * 17 + "...")
        self.assertEqual(plain("short", 20), "short")
        self.assertLessEqual(len(plain("word " * 100, 50)), 50)

    def test_visible_drops_only_what_hides_text_and_keeps_a_line_break(self):
        self.assertEqual(visible("a\u202eb\u200bc\x00d\ne\tf"), "abcd\ne\tf")
        self.assertEqual(visible(None), "")
        self.assertEqual(visible("[kept](https://kept.example)"), "[kept](https://kept.example)")

    def test_it_is_the_name_that_the_first_modules_use(self):
        self.assertIs(brief.text_of, brief.plain)

    def test_every_text_of_a_brief_made_from_hostile_records_is_safe_for_a_page_a_letter_and_a_card(self):
        for text in INJECTIONS:
            case = make_case(resource_id=text, resource_name=text, resource_group=text, resource_type=text, summary=text, objections=(text,), guards=(text,),
                             models={"detective": text, "skeptic": text},
                             facts={"basis": text, "sku": text, "tier": text, "targetService": text, "impact": text, "metrics": {text: 3}, "metricUnits": {text: text}},
                             owner={"tagOwner": text, "tagName": text, "createdBy": text, "createdAt": text, "changedBy": text, "changedAt": text, "lookedUp": True},
                             detector="investigation", recommendation=text, steps=())
            plan = make_plan(resource_id=text, resource_name=text, resource_group=text, title=text, what_changes=text, could_go_wrong=text, undo=text, family="resize-disk")
            for made in (build_brief(case, plan, make_action(state="failed", error=text, result=text, verification={"note": text, "gone": True}), (make_decision(approver_name=text, note=text),),
                                     now=NOW, may_answer=True),
                         build_brief(case, make_advice(resource_id=text, resource_name=text, resource_group=text, title=text), None, (), now=NOW),
                         build_brief(case, None, now=NOW)):
                for path, value in strings_of(made):
                    if path.endswith("where.portal_url"):
                        self.assertEqual(value, "", "an id of the estate that is not the id of one resource makes no link")
                        continue
                    with self.subTest(text=text[:20], field=path):
                        self.assertEqual(visible(value), value)
                        self.assertNotIn("\n", value)
                        self.assertNotIn("[", value)
                        self.assertNotIn("]", value)
                        self.assertNotRegex(value, r"(?i)\b[a-z][a-z0-9+.-]*://")

    def test_the_brief_of_a_card_can_be_written_as_json_text_without_loss(self):
        import json
        made = brief_of(make_case(), make_plan(), may_answer=True)
        document = json.loads(json.dumps(dataclasses.asdict(made)))
        self.assertEqual(document["headline"], made.headline)
        self.assertEqual(document["where"]["portal_url"], made.where.portal_url)
        self.assertEqual(document["answers"], list(made.answers))


def strings_of(value, path="brief"):
    """Every string in a brief, with its path."""
    if isinstance(value, str):
        yield path, value
    elif dataclasses.is_dataclass(value):
        for field in dataclasses.fields(value):
            yield from strings_of(getattr(value, field.name), f"{path}.{field.name}")
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            yield from strings_of(item, f"{path}[{index}]")


class WhatTheModuleIs(unittest.TestCase):
    source = (Path(support.APP_ROOT) / "cases" / "brief.py").read_text(encoding="utf-8")
    words_source = (Path(support.APP_ROOT) / "cases" / "families" / "words.py").read_text(encoding="utf-8")

    def test_it_imports_only_the_standard_library_the_records_and_the_words_of_the_families(self):
        allowed = {"__future__", "datetime", "math", "re", "unicodedata", "dataclasses", "typing"}
        for node in ast.walk(ast.parse(self.source)):
            if isinstance(node, ast.Import):
                self.assertLessEqual({a.name.split(".")[0] for a in node.names}, allowed)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 1:
                    self.assertIn(node.module, ("models", "families.words"), "the words of the families are a module that holds no way to reach Azure (next test)")
                else:
                    self.assertIn((node.module or "").split(".")[0], allowed)

    def test_the_words_of_the_families_import_only_the_standard_library_and_the_records_and_read_nothing(self):
        allowed = {"__future__", "re", "dataclasses", "typing"}
        for node in ast.walk(ast.parse(self.words_source)):
            if isinstance(node, ast.Import):
                self.assertLessEqual({a.name.split(".")[0] for a in node.names}, allowed)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    self.assertEqual((node.level, node.module), (2, "models"))
                else:
                    self.assertIn((node.module or "").split(".")[0], allowed)
        for pattern in (r"\.(now|utcnow|today)\(", r"\bimport time\b", r"\bopen\(", r"\bprint\(", r"\bos\.", r"\bsys\.", r"\burlopen", r"\bsocket", r"\blogging", r"\brandom\b", r"\buuid\b",
                        r"https?://", r"\bhttp\b"):
            self.assertIsNone(re.search(pattern, self.words_source), pattern)

    def test_it_reads_no_clock_and_does_no_input_or_output(self):
        for pattern in (r"\.(now|utcnow|today)\(", r"\bimport time\b", r"\btime\.(time|sleep|monotonic)\(", r"\bopen\(", r"\bprint\(", r"\bos\.", r"\bsys\.", r"\burlopen",
                        r"\bsocket", r"\blogging", r"\brandom\b", r"\buuid\b"):
            self.assertIsNone(re.search(pattern, self.source), pattern)

    def test_it_makes_no_link_but_the_portal_address_of_a_checked_id(self):
        self.assertEqual(sorted(set(re.findall(r"https?://[A-Za-z0-9./#{}_-]+", self.source))), ["https://portal.azure.com/#resource{resource_id}"])

    def test_a_change_family_that_has_words_is_a_family_of_the_registry_and_advise_is_neither(self):
        self.assertEqual(set(SHOWN), set(registry.names()))
        self.assertNotIn(ADVISE, SHOWN)
        self.assertEqual(brief.called_of(ADVISE), "change", "a name that is not a family of change is called just a change")


if __name__ == "__main__":
    unittest.main()
