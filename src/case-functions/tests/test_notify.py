import datetime as dt
import json
import logging
import unittest

from cases import loop_config, notify, people as people_mod
from cases.memory_store import MemoryStore
from cases.models import SettingsRecord, SwitchRecord

from test_letters import make_action, make_case, make_plan, make_run

TINO = "aaaaaaaa-1111-4222-8333-444444444444"
OPS = "22222222-3333-4444-5555-666666666666"
NO_MAIL = "33333333-4444-5555-6666-777777777777"
STRANGER = "44444444-5555-6666-7777-888888888888"
SENDER = "meternaut-ai@example.com"
TUESDAY = dt.datetime(2026, 11, 3, 10, 0, 0, tzinfo=dt.timezone.utc)
ENV = {
    "STORE_ACCOUNT_NAME": "stexample", "WRITER_RESOURCE_GROUP": "rg-meternaut", "WRITER_SUBSCRIPTION_ID": "bbbbbbbb-2222-4333-9444-555555555555",
    "WRITER_CLIENT_ID": "55555555-4444-3333-2222-111111111111", "CONSOLE_HOST": "func.example.net", "MAIL_SENDER": SENDER,
    "CONSOLE_PEOPLE": json.dumps([
        {"oid": TINO, "name": "Tino", "roles": ["owner", "approver", "ops"], "mail": "tino@example.com"},
        {"oid": OPS, "name": "Ops", "roles": ["ops"], "mail": "ops@example.com"},
        {"oid": NO_MAIL, "name": "Nomail", "roles": ["approver"]},
    ]),
}


def plan(**changes):
    return make_plan(**{"approvers": (TINO,), **changes})


class Clock:
    def __init__(self, now=TUESDAY):
        self.now = now

    def __call__(self):
        return self.now


class Graph:
    """Graph's sendMail: it remembers what it was given and answers 202."""

    def __init__(self):
        self.sent = []

    def __call__(self, method, url, headers, data, timeout):
        self.sent.append((url, json.loads(data.decode("utf-8"))["message"]))
        return 202, {}, b""

    def to(self):
        return [m["toRecipients"][0]["emailAddress"]["address"] for _, m in self.sent]

    def subjects(self):
        return [m["subject"] for _, m in self.sent]


class Fixture:
    def __init__(self, store=None, transport=None):
        self.clock, self.graph = Clock(), Graph()
        self.store = store or MemoryStore(self.clock)
        self.people = people_mod.load(ENV)
        settings = loop_config.load(ENV)
        self.on_plan, self.on_action, self.on_run = notify.hooks(
            ENV, settings, self.store, self.people, lambda resource: "tok", lambda text: text, transport=transport or self.graph, sleep=lambda s: None,
            monotonic=lambda: 0.0, clock=self.clock)

    def records(self, oid=TINO):
        return [(m.kind, m.status, m.plan_id) for m in sorted(self.store.mails, key=lambda m: m.mail_id) if m.oid == oid]


class AboutAPlan(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def test_the_first_plan_brings_the_first_contact_and_the_approval_and_the_next_only_the_approval(self):
        self.f.on_plan(plan(), make_case())
        self.assertEqual(sorted(k for k, _, _ in self.f.records()), ["approval", "first_contact"])
        self.f.on_plan(plan(plan_id="p2", case_id="c2"), make_case(case_id="c2"))
        self.assertEqual(sorted((k, p) for k, _, p in self.f.records()), [("approval", "p1a2b3c4d5"), ("approval", "p2"), ("first_contact", None)])
        self.assertEqual(self.f.graph.to(), ["tino@example.com"] * 3)

    def test_the_same_plan_is_never_written_about_twice(self):
        self.f.on_plan(plan(), make_case())
        self.f.on_plan(plan(), make_case())
        self.assertEqual(len(self.f.graph.sent), 2)

    def test_only_an_approver_of_the_plan_who_is_listed_and_has_an_address_is_written_to(self):
        self.f.on_plan(plan(approvers=(TINO, NO_MAIL, STRANGER)), make_case())
        self.assertEqual(self.f.graph.to(), ["tino@example.com", "tino@example.com"])
        self.assertEqual(self.f.records(NO_MAIL), [])
        self.assertEqual(self.f.records(STRANGER), [])

    def test_a_person_who_is_not_an_approver_of_the_plan_gets_nothing_even_when_listed(self):
        self.f.on_plan(plan(approvers=(OPS,)), make_case())
        self.assertEqual(self.f.graph.to(), ["ops@example.com", "ops@example.com"])
        self.assertEqual(self.f.records(TINO), [])

    def test_the_subject_holds_no_resource_name_and_the_link_is_the_console(self):
        made = plan()
        self.f.on_plan(made, make_case())
        for subject in self.f.graph.subjects():
            self.assertTrue(subject.startswith("[Meternaut]"))
            self.assertNotIn(made.resource_name, subject)
        approval = next(m for _, m in self.f.graph.sent if "ok/" in m["body"]["content"])
        self.assertIn(f"https://func.example.net/ok/{made.plan_id}", approval["body"]["content"])

    def test_a_pulled_messages_switch_holds_every_letter_and_the_record_says_so(self):
        self.f.store.switch_put(SwitchRecord(name="messages", paused=True, by=TINO, at="2026-11-03T09:00:00Z"))
        self.f.on_plan(plan(), make_case())
        self.assertEqual(self.f.graph.sent, [])
        self.assertEqual({s for _, s, _ in self.f.records()}, {"held"})

    def test_a_held_letter_is_offered_again_after_the_wait_and_not_before(self):
        self.f.store.switch_put(SwitchRecord(name="messages", paused=True, by=TINO, at="2026-11-03T09:00:00Z"))
        made = plan()
        self.f.on_plan(made, make_case())
        self.f.store.switch_put(SwitchRecord(name="messages", paused=False))
        self.f.on_plan(made, make_case())
        self.assertEqual(len(self.f.graph.sent), 0, "the last try was a moment ago")
        self.f.clock.now += dt.timedelta(minutes=notify.RETRY_MINUTES)
        self.f.on_plan(made, make_case())
        self.assertEqual(sorted(k for k in (m.kind for m in self.f.store.mails if m.status == "sent")), ["approval", "first_contact"])
        self.assertEqual(len(self.f.graph.sent), 2)
        self.f.clock.now += dt.timedelta(hours=1)
        self.f.on_plan(made, make_case())
        self.assertEqual(len(self.f.graph.sent), 2, "what was sent is never sent again")

    def test_a_letter_that_keeps_failing_is_given_up_after_the_tries_and_each_try_leaves_a_record(self):
        def refuse(method, url, headers, data, timeout):
            return 403, {}, b'{"error":{"code":"ErrorAccessDenied","message":"no"}}'

        f = Fixture(transport=refuse)
        made = plan()
        for _ in range(notify.MAX_TRIES + 5):
            f.on_plan(made, make_case())
            f.clock.now += dt.timedelta(minutes=notify.RETRY_MINUTES)
        tries = [m for m in f.store.mails if m.kind == "approval"]
        self.assertEqual((len(tries), {m.status for m in tries}), (notify.MAX_TRIES, {"failed"}))
        self.assertEqual(len([m for m in f.store.mails if m.kind == "first_contact"]), notify.MAX_TRIES)

    def test_a_letter_that_failed_goes_out_when_the_sender_works_and_then_never_again(self):
        answers = [(403, {}, b'{"error":{"code":"ErrorAccessDenied","message":"no"}}')] * 2

        def flaky(method, url, headers, data, timeout):
            return answers.pop(0) if answers else (202, {}, b"")

        f = Fixture(transport=flaky)
        made = plan()
        f.on_plan(made, make_case())
        self.assertEqual({m.status for m in f.store.mails}, {"failed"})
        f.clock.now += dt.timedelta(minutes=notify.RETRY_MINUTES)
        f.on_plan(made, make_case())
        self.assertEqual({(m.kind, m.status) for m in f.store.mails if m.status == "sent"}, {("first_contact", "sent"), ("approval", "sent")})
        before = len(f.store.mails)
        f.clock.now += dt.timedelta(days=1)
        f.on_plan(made, make_case())
        self.assertEqual(len(f.store.mails), before)


class AboutAChange(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.plan, self.case = plan(), make_case(status="done")

    def test_a_change_that_ran_is_told_once_as_a_notice_and_the_check_once_as_verified(self):
        self.f.on_action(make_action(state="done"), self.plan, self.case)
        self.f.on_action(make_action(state="done"), self.plan, self.case)
        self.assertEqual([k for k, _, _ in self.f.records()], ["notice"])
        self.f.on_action(make_action(state="verified"), self.plan, self.case)
        self.f.on_action(make_action(state="verified"), self.plan, self.case)
        self.assertEqual(sorted(k for k, _, _ in self.f.records()), ["notice", "verified"])
        self.assertEqual(len(self.f.graph.sent), 2)

    def test_a_change_that_failed_is_told_too(self):
        self.f.on_action(make_action(state="failed", result="The resource has a lock."), self.plan, self.case)
        self.assertEqual([k for k, _, _ in self.f.records()], ["notice"])
        self.assertIn("did not run", self.f.graph.subjects()[0])

    def test_a_record_that_is_missing_sends_nothing(self):
        self.f.on_action(make_action(), None, self.case)
        self.f.on_action(make_action(), self.plan, None)
        self.assertEqual(self.f.graph.sent, [])

    def test_the_letters_about_a_change_are_never_held_by_the_weekly_budget(self):
        self.f.store.settings_put(SettingsRecord(oid=TINO, weekly_budget=0))
        self.f.on_action(make_action(state="done"), self.plan, self.case)
        self.f.on_action(make_action(state="verified"), self.plan, self.case)
        self.assertEqual(self.f.graph.to(), ["tino@example.com", "tino@example.com"])


class AboutTheWeeklyDesk(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def digests(self, oid=TINO):
        return [r for r in self.f.records(oid) if r[0] == "digest"]

    def test_the_desk_goes_to_the_approver_or_owner_with_an_address_on_the_desk_day_only(self):
        self.f.on_run(make_run())
        self.assertEqual(len(self.digests()), 1)
        self.assertEqual(self.f.records(OPS), [], "a person who is neither an approver nor an owner gets no desk")
        self.assertEqual(self.f.records(NO_MAIL), [])

    def test_not_on_another_day(self):
        self.f.clock.now = TUESDAY + dt.timedelta(days=2)
        self.f.on_run(make_run())
        self.assertEqual(self.f.graph.sent, [])

    def test_only_once_in_a_week_and_again_the_week_after(self):
        self.f.on_run(make_run())
        self.f.on_run(make_run())
        self.assertEqual(len(self.digests()), 1)
        self.f.clock.now = TUESDAY + dt.timedelta(days=7)
        self.f.on_run(make_run())
        self.assertEqual(len(self.digests()), 2)

    def test_a_person_chooses_the_day(self):
        self.f.store.settings_put(SettingsRecord(oid=TINO, desk_day=4))
        self.f.on_run(make_run())
        self.assertEqual(self.digests(), [])
        self.f.clock.now = TUESDAY + dt.timedelta(days=2)
        self.f.on_run(make_run())
        self.assertEqual(len(self.digests()), 1)

    def test_the_desk_says_what_waits_and_what_was_found_this_week(self):
        self.f.store.run_put(make_run(run_id="r1", started_at="2026-11-02T06:00:00Z"))
        self.f.store.case_put(make_case(case_id="c9", status="proposed", updated_at="2026-11-02T06:05:00Z"))
        self.f.store.plan_put(plan(plan_id="open1", approvers=(TINO,)))
        self.f.on_run(make_run())
        (subject,) = self.f.graph.subjects()
        self.assertTrue(subject.startswith("[Meternaut]"))


class WhenSomethingFails(unittest.TestCase):
    class Broken(MemoryStore):
        def mails_since(self, oid, since):
            raise RuntimeError("the store cannot be read")

    def test_no_hook_raises_and_the_failure_is_logged(self):
        f = Fixture(store=self.Broken(Clock()))
        with self.assertLogs("meternaut.notify", level=logging.ERROR) as logged:
            f.on_plan(plan(), make_case())
            f.on_action(make_action(), plan(), make_case())
            f.on_run(make_run())
        self.assertEqual(len(logged.output), 3)
        self.assertEqual(f.graph.sent, [])

    def test_a_refusal_by_graph_is_recorded_as_failed_and_the_loop_goes_on(self):
        f = Fixture()

        def refuse(method, url, headers, data, timeout):
            return 403, {}, b'{"error":{"code":"ErrorAccessDenied","message":"no"}}'

        f2 = Fixture.__new__(Fixture)
        f2.clock, f2.graph = f.clock, refuse
        f2.store = MemoryStore(f.clock)
        f2.people = f.people
        f2.on_plan, f2.on_action, f2.on_run = notify.hooks(ENV, loop_config.load(ENV), f2.store, f2.people, lambda resource: "tok", lambda text: text, transport=refuse,
                                                           sleep=lambda s: None, monotonic=lambda: 0.0, clock=f.clock)
        f2.on_plan(plan(), make_case())
        self.assertEqual({s for _, s, _ in f2.records()}, {"failed"})


if __name__ == "__main__":
    unittest.main()
