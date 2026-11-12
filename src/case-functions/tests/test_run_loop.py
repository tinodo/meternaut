import datetime as dt
import json
import unittest
from dataclasses import replace

from support import ENV, NOW, RG, SUBSCRIPTION, FakeEstate, detective_says, disk_row, model_reply, pe_row, run_watch, skeptic_says

from cases import loop_config, people as people_mod, wiring
from cases.approvals import Approvals
from cases.families.gates import ChangeScope
from cases.memory_store import MemoryStore, stamp
from cases.models import StoreError

OID = "aaaaaaaa-1111-4222-8333-444444444444"
GROUP = "rg-meternaut"
PLANTED = {"meternaut-planted": "demo"}


class Moving:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += dt.timedelta(**kwargs)


def loop_for(clock, store=None, *, recheck_days=7, approvers=True, on_plan=None):
    store = store or MemoryStore(clock=clock)
    settings = loop_config.LoopSettings(store_account="stexample", change_scopes=(ChangeScope(SUBSCRIPTION, GROUP),), console_host="func.example.net",
                                        mail_sender=None, planted_tag="meternaut-planted", plan_ttl_hours=72, recheck_days=recheck_days)
    roles = ("owner", "approver", "ops") if approvers else ("owner",)
    people = people_mod.People((people_mod.Person(OID, "Tino", roles, "tino@example.com"),))
    extras = wiring.Extras(settings, store, people, Approvals(store, wiring.approval_settings(settings), clock))
    if on_plan:
        extras.on_plan = on_plan
    return extras


def estate_with(planted_disk=True, endpoints=0, group="rg-app"):
    estate = FakeEstate()
    if planted_disk:
        row = disk_row("planted-disk-1", GROUP, tags=PLANTED, timeCreated=stamp(NOW))
        estate.graph["orphan-managed-disk"] = [row]
        estate.graph["recent-creations"] = [{"targetId": row["id"].lower()}]
    estate.graph["orphan-private-endpoint"] = [pe_row(f"pe{n}", group) for n in range(endpoints)]
    return estate


def watch(estate, extras, clock):
    return run_watch(estate, clock=clock, extras=extras)


class WhatTheLoopKeeps(unittest.TestCase):
    def setUp(self):
        self.clock = Moving()
        self.extras = loop_for(self.clock)
        self.store = self.extras.store

    def test_a_run_is_kept_with_its_counts_and_a_case_for_each_lead_that_was_taken_up(self):
        summary, events, _ = watch(estate_with(endpoints=2), self.extras, self.clock)
        runs = self.store.runs_recent()
        self.assertEqual(len(runs), 1)
        run = runs[0]
        self.assertEqual((run.ok, run.trigger, run.leads, run.cases, run.reason), (True, "control", 3, 3, None))
        self.assertEqual(run.finished_at, stamp(NOW))
        self.assertEqual(len(self.store.cases_recent()), 3)

    def test_the_waste_that_meternaut_planted_is_taken_up_first_even_when_dearer_leads_are_there(self):
        _, events, _ = watch(estate_with(endpoints=5), self.extras, self.clock)
        first = next(e for e in events if e["type"] == "lead.found")
        self.assertEqual((first["detector"], first["rank"]), ("orphan-managed-disk", 1))
        detectors_taken = sorted(c.detector for c in self.store.cases_recent())
        self.assertEqual(detectors_taken, ["orphan-managed-disk", "orphan-private-endpoint", "orphan-private-endpoint"])

    def test_a_planted_disk_in_the_change_group_is_not_held_back_for_being_new_and_gets_a_plan(self):
        watch(estate_with(), self.extras, self.clock)
        (case,) = self.store.cases_recent()
        self.assertEqual((case.status, case.detector, case.guards), ("awaiting_ok", "orphan-managed-disk", ()))
        self.assertTrue(case.plan_id)
        plan = self.store.plan_get(case.plan_id)
        self.assertEqual((plan.state, plan.family, plan.approvers), ("open", "delete-disk", (OID,)))
        self.assertEqual(case.models, {"detective": "gpt-6-luna", "skeptic": "gpt-6.1-sol"})
        self.assertEqual([s["step"] for s in case.steps], ["evidence", "guards", "detective", "skeptic"])
        self.assertEqual(case.facts["diskState"], "unattached")

    def test_the_models_are_told_that_the_disk_is_planted_and_are_not_shown_its_age(self):
        estate = estate_with()
        watch(estate, self.extras, self.clock)
        seen = [json.loads(prompt)["case"] for prompt in estate.prompts()]
        self.assertEqual(len(seen), 2, "the Detective and the Skeptic")
        for case in seen:
            self.assertIs(case["facts"]["planted"], True)
            self.assertNotIn("ageDays", case["facts"])
            self.assertEqual(case["flags"]["tooNew"], False)
        (kept,) = self.store.cases_recent()
        self.assertEqual((kept.facts["planted"], "ageDays" in kept.facts), (True, False), "the notebook shows the facts that the models saw")

    def test_a_disk_that_is_not_planted_is_shown_with_its_age_and_without_the_fact(self):
        estate = estate_with(planted_disk=False)
        row = disk_row("young-disk", GROUP, timeCreated=stamp(NOW))
        estate.graph["orphan-managed-disk"] = [row]
        estate.graph["recent-creations"] = [{"targetId": row["id"].lower()}]
        watch(estate, self.extras, self.clock)
        for prompt in estate.prompts():
            case = json.loads(prompt)["case"]
            self.assertEqual((case["facts"]["ageDays"], "planted" in case["facts"], case["flags"]["tooNew"]), (0, False, True))

    def test_the_same_disk_without_the_tag_is_held_back_and_gets_no_change_only_advice(self):
        estate = estate_with(planted_disk=False)
        row = disk_row("young-disk", GROUP, timeCreated=stamp(NOW))
        estate.graph["orphan-managed-disk"] = [row]
        estate.graph["recent-creations"] = [{"targetId": row["id"].lower()}]
        watch(estate, self.extras, self.clock)
        (case,) = self.store.cases_recent()
        (plan,) = self.store.plans_open()
        self.assertEqual((case.status, case.guards, case.plan_id), ("needs_human", ("too-new",), plan.plan_id))
        self.assertEqual((plan.family, plan.state), ("advise", "open"), "a person can answer it, and nothing can be changed by it")

    def test_a_planted_disk_in_another_group_is_not_a_fixture(self):
        estate = FakeEstate()
        row = disk_row("planted-elsewhere", "rg-other", tags=PLANTED, timeCreated=stamp(NOW))
        estate.graph["orphan-managed-disk"] = [row]
        estate.graph["recent-creations"] = [{"targetId": row["id"].lower()}]
        watch(estate, self.extras, self.clock)
        (case,) = self.store.cases_recent()
        self.assertEqual((case.status, case.guards), ("needs_human", ("too-new",)))

    def test_a_proposed_case_that_may_not_be_changed_gets_advice_and_not_a_plan_of_a_change(self):
        watch(estate_with(planted_disk=False, endpoints=1, group=GROUP), self.extras, self.clock)  # in the group where a change may be made, but without the planting tag
        (case,) = self.store.cases_recent()
        (plan,) = self.store.plans_open()
        self.assertEqual((case.status, case.recommendation, case.plan_id), ("proposed", "delete", plan.plan_id))
        self.assertEqual((plan.family, plan.case_id), ("advise", case.case_id))

    def test_a_lock_still_stops_a_planted_disk(self):
        estate = estate_with()
        row = estate.graph["orphan-managed-disk"][0]
        estate.locks_at[row["id"].lower()] = [{"id": f"{row['id']}/providers/Microsoft.Authorization/locks/keep"}]
        watch(estate, self.extras, self.clock)
        (case,) = self.store.cases_recent()
        self.assertEqual((case.status, case.guards), ("needs_human", ("locked",)))
        self.assertEqual([p.family for p in self.store.plans_open()], ["advise"], "no change can be made for it: a person can only say whether it is worth acting on")

    def test_a_skeptic_that_disagrees_stops_a_planted_disk_too(self):
        estate = estate_with()
        estate.chat_replies = [model_reply(detective_says()), model_reply(skeptic_says("disagree", ["it may be a backup"]))]
        watch(estate, self.extras, self.clock)
        (case,) = self.store.cases_recent()
        self.assertEqual((case.status, case.objections), ("needs_human", ("it may be a backup",)))
        self.assertEqual([p.family for p in self.store.plans_open()], ["advise"])

    def test_the_plan_event_and_the_hook_say_that_a_plan_was_made(self):
        made = []
        extras = loop_for(self.clock, on_plan=lambda plan, case: made.append((plan.plan_id, case.status)))
        _, events, _ = watch(estate_with(), extras, self.clock)
        (plan,) = extras.store.plans_open()
        self.assertEqual(made, [(plan.plan_id, "awaiting_ok")])
        created = [e for e in events if e["type"] == "plan.created"]
        self.assertEqual(len(created), 1)
        self.assertEqual((created[0]["planId"], created[0]["family"], created[0]["approvers"]), (plan.plan_id, "delete-disk", 1))

    def test_nobody_with_the_approver_role_means_no_plan(self):
        extras = loop_for(self.clock, approvers=False)
        watch(estate_with(), extras, self.clock)
        (case,) = extras.store.cases_recent()
        self.assertEqual((case.status, case.plan_id), ("proposed", None))


class WhatTheLoopDoesNotRepeat(unittest.TestCase):
    def setUp(self):
        self.clock = Moving()
        self.extras = loop_for(self.clock)
        self.store = self.extras.store

    def test_leads_that_were_judged_lately_are_not_taken_up_again_and_the_slots_go_to_other_leads(self):
        estate = estate_with(planted_disk=False, endpoints=5)
        _, first, _ = watch(estate, self.extras, self.clock)
        self.assertEqual(len(self.store.cases_recent()), 3)
        self.clock.advance(days=1)
        estate.calls.clear()
        _, second, _ = watch(estate, self.extras, self.clock)
        self.assertEqual(len(self.store.cases_recent()), 5)
        notes = [e["note"] for e in second if e["type"] == "run.note"]
        self.assertIn("3 leads were judged within the last 7 days and not taken up again", notes)
        self.assertEqual(len(estate.chat_calls()), 4, "two leads, a Detective and a Skeptic each")
        runs = self.store.runs_recent()
        self.assertIn("3 leads were judged within the last 7 days and not taken up again", runs[0].notes)

    def test_after_the_days_have_passed_a_lead_is_judged_again_and_the_case_counts_the_runs(self):
        estate = estate_with(planted_disk=False, endpoints=1)
        watch(estate, self.extras, self.clock)
        self.clock.advance(days=8)
        watch(estate, self.extras, self.clock)
        (case,) = self.store.cases_recent()
        self.assertEqual(case.runs_seen, 2)
        self.assertEqual(case.first_seen_at, stamp(NOW))
        self.assertEqual(case.updated_at, stamp(NOW + dt.timedelta(days=8)))

    def test_a_case_with_an_open_plan_is_left_alone_by_the_next_run(self):
        estate = estate_with()
        watch(estate, self.extras, self.clock)
        (before,) = self.store.cases_recent()
        self.clock.advance(days=1)
        watch(estate, self.extras, self.clock)
        (after,) = self.store.cases_recent()
        self.assertEqual(before, replace(after, cost_series=before.cost_series, cost_series_end=before.cost_series_end), "judged again by nobody: only its daily cost moves on")
        self.assertEqual((before.cost_series_end, after.cost_series_end), ("2026-11-03", "2026-11-04"))
        self.assertEqual(len(self.store.plans_open()), 1)

    def test_a_case_that_ended_in_an_error_is_taken_up_again(self):
        estate = estate_with(planted_disk=False, endpoints=1)
        estate.failures["chat"] = [500, 500, 500, 500]
        watch(estate, self.extras, self.clock)
        (case,) = self.store.cases_recent()
        self.assertEqual(case.status, "error")
        estate.failures.clear()
        self.clock.advance(hours=1)
        watch(estate, self.extras, self.clock)
        (again,) = self.store.cases_recent()
        self.assertEqual((again.status, again.runs_seen), ("proposed", 2))

    def test_a_case_whose_change_failed_or_was_stopped_is_taken_up_again_and_asked_about_again(self):
        from dataclasses import replace
        estate = estate_with()
        watch(estate, self.extras, self.clock)
        (case,) = self.store.cases_recent()
        (plan,) = self.store.plans_open()
        self.store.plan_put(replace(plan, state="failed"))
        self.store.case_put(replace(case, status="failed"))
        self.clock.advance(hours=1)
        watch(estate, self.extras, self.clock)
        (again,) = self.store.cases_recent()
        self.assertEqual((again.status, again.runs_seen, len(self.store.plans_open())), ("awaiting_ok", 2, 1), "nothing was changed, the request is closed: the next Watch asks again")


class WhenTheStoreFails(unittest.TestCase):
    def test_a_store_that_fails_never_stops_the_run_and_the_history_says_so(self):
        clock = Moving()

        class Broken(MemoryStore):
            def case_put(self, case):
                raise StoreError("the table service is down")

            def run_put(self, run):
                raise StoreError("the table service is down")

        extras = loop_for(clock, Broken(clock=clock))
        summary, events, messages = watch(estate_with(), extras, clock)
        self.assertTrue(summary.ok)
        self.assertEqual(summary.cases, 1)
        self.assertTrue(any("could not be kept in the store" in e.get("note", "") for e in events if e["type"] == "run.note"))
        self.assertTrue(any("the run could not be kept in the store" in m for m in messages))
        self.assertEqual(events[-1]["type"], "run.finished")

    def test_a_run_that_fails_is_kept_as_a_failed_run(self):
        clock = Moving()
        extras = loop_for(clock)
        estate = estate_with()
        estate.failures = {f"graph:{name}": 400 for name in estate.graph} | {"advisor": 403}
        summary, _, _ = watch(estate, extras, clock)
        self.assertFalse(summary.ok)
        (run,) = extras.store.runs_recent()
        self.assertEqual((run.ok, run.finished_at is not None), (False, True))
        self.assertTrue(run.reason)


class WithoutTheLoop(unittest.TestCase):
    def test_a_run_without_the_settings_of_the_loop_touches_no_store(self):
        summary, events, _ = run_watch(estate_with())
        self.assertTrue(summary.ok)
        self.assertNotIn("plan.created", [e["type"] for e in events])


if __name__ == "__main__":
    unittest.main()
