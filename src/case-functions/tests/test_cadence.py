"""How often the investigation runs: the daily timer investigates when INVESTIGATE_EVERY_DAYS have passed since the last run that investigated; a run that a person starts always does.

A run of the investigation costs about half a US dollar of model calls (Cost Management, 2026-11-08), and the standing limit of the AI Gateway is 5 a day and 25 a month for each caller (AGENTS.md
rule 15 (g)), shared with the evaluations, the red team and the runs that a person starts: a weekly investigation uses about 2 of the 25, a daily one about 15. The leads of the fixed detectors are
judged by the Detective and the Skeptic every day, which costs cents. Everything in these tests is invented.
"""
import datetime as dt
import unittest
from types import SimpleNamespace

from support import ENV

from cases import config, run
from cases.foundry import FoundryError
from cases.memory_store import MemoryStore, stamp
from cases.models import RunRecord, StoreError
from test_investigate import FakeFoundry
from test_run import INVESTIGATING, estate_with_leads, investigating, of_type
from test_run_loop import Moving, loop_for

NOW = dt.datetime(2026, 11, 9, 5, 30, 0, tzinfo=dt.timezone.utc)


def services(store, now=NOW, every=7):
    return SimpleNamespace(settings=SimpleNamespace(investigate_every_days=every), extras=SimpleNamespace(store=store), clock=lambda: now)


def kept(store, ago, *, investigated=True, started_at=None):
    started = started_at or stamp(NOW - ago)
    store.run_put(RunRecord(run_id=f"r{abs(hash((started, investigated))) % 10**8:08d}", trigger="timer", started_at=started, finished_at=started, investigated=investigated))


class TheSetting(unittest.TestCase):
    def test_it_is_seven_days_unless_the_environment_says_another_number_from_one_to_thirty(self):
        self.assertEqual((config.DEFAULT_INVESTIGATE_EVERY_DAYS, config.LIMIT_INVESTIGATE_EVERY_DAYS, config.INVESTIGATE_EVERY_DAYS), (7, 30, "INVESTIGATE_EVERY_DAYS"))
        self.assertEqual(config.load(dict(ENV)).investigate_every_days, 7)
        for value in ("1", "14", "30"):
            with self.subTest(value):
                self.assertEqual(config.load({**ENV, "INVESTIGATE_EVERY_DAYS": value}).investigate_every_days, int(value))

    def test_a_number_outside_the_range_or_not_a_number_is_a_problem_that_the_settings_name(self):
        for value in ("0", "31", "-1", "often", "1.5"):
            with self.subTest(value):
                with self.assertRaises(config.ConfigError) as raised:
                    config.load({**ENV, "INVESTIGATE_EVERY_DAYS": value})
                self.assertIn("INVESTIGATE_EVERY_DAYS", str(raised.exception))

    def test_the_record_of_a_run_says_whether_it_investigated_and_an_old_record_says_no(self):
        record = RunRecord(run_id="r1", trigger="timer", started_at=stamp(NOW))
        self.assertIs(record.investigated, False)
        self.assertIs(RunRecord.from_json(RunRecord(run_id="r2", trigger="timer", started_at=stamp(NOW), investigated=True).to_json()).investigated, True)
        old = '{"run_id": "r3", "trigger": "timer", "started_at": "2026-11-01T05:30:00Z"}'
        self.assertIs(RunRecord.from_json(old).investigated, False)


class WhenTheInvestigationIsDue(unittest.TestCase):
    def wait(self, store, trigger="timer", **options):
        return run.investigation_wait(services(store, **options), trigger)

    def test_a_run_that_a_person_starts_always_investigates_whatever_ran_before(self):
        store = MemoryStore(clock=lambda: NOW)
        kept(store, dt.timedelta(hours=2))
        for trigger in ("control", "manual", "anything"):
            self.assertIsNone(self.wait(store, trigger), trigger)

    def test_the_timer_investigates_when_no_run_ever_did(self):
        store = MemoryStore(clock=lambda: NOW)
        self.assertIsNone(self.wait(store))
        kept(store, dt.timedelta(days=1), investigated=False)
        self.assertIsNone(self.wait(store), "a run that did not investigate does not start the clock")

    def test_the_timer_waits_until_the_days_have_passed_with_an_hour_of_slack_for_the_timer(self):
        for ago, waits in ((dt.timedelta(hours=1), True), (dt.timedelta(days=1), True), (dt.timedelta(days=6, hours=22), True), (dt.timedelta(days=6, hours=23), False),
                           (dt.timedelta(days=7), False), (dt.timedelta(days=30), False)):
            with self.subTest(ago=ago):
                store = MemoryStore(clock=lambda: NOW)
                kept(store, ago)
                self.assertEqual(self.wait(store) is not None, waits)

    def test_the_latest_run_that_investigated_counts(self):
        store = MemoryStore(clock=lambda: NOW)
        kept(store, dt.timedelta(days=20))
        kept(store, dt.timedelta(days=2))
        kept(store, dt.timedelta(hours=3), investigated=False)
        self.assertIn("the last investigation ran 2 days ago", self.wait(store))

    def test_the_reason_says_how_long_ago_and_how_to_get_it_at_once(self):
        store = MemoryStore(clock=lambda: NOW)
        kept(store, dt.timedelta(days=1, hours=2))
        self.assertEqual(self.wait(store), "the last investigation ran 1 day ago, and the timer investigates every 7 days (INVESTIGATE_EVERY_DAYS); a run that a person starts does it at once")
        other = MemoryStore(clock=lambda: NOW)
        kept(other, dt.timedelta(hours=5))
        self.assertIn("ran 0 days ago", self.wait(other))

    def test_the_number_of_days_is_the_setting(self):
        store = MemoryStore(clock=lambda: NOW)
        kept(store, dt.timedelta(days=2))
        self.assertIsNotNone(self.wait(store, every=3))
        self.assertIsNone(self.wait(store, every=2))
        self.assertIsNone(self.wait(store, every=1))

    def test_a_run_dated_in_the_future_counts_for_nothing(self):
        store = MemoryStore(clock=lambda: NOW)
        kept(store, -dt.timedelta(days=20))
        self.assertIsNone(self.wait(store), "a record from the future must not hold the timer off")
        kept(store, dt.timedelta(days=2))
        self.assertIn("the last investigation ran 2 days ago", self.wait(store))

    def test_a_store_that_cannot_be_read_means_wait_and_a_time_that_cannot_be_read_is_left_out(self):
        class Broken(MemoryStore):
            def runs_recent(self, limit=20):
                raise StoreError("the table could not be read")

        self.assertIn("could not be read", self.wait(Broken(clock=lambda: NOW)))
        store = MemoryStore(clock=lambda: NOW)
        kept(store, dt.timedelta(days=1), started_at="not a time")
        self.assertIsNone(self.wait(store))

    def test_without_the_loop_there_is_nothing_to_weigh_and_the_run_investigates(self):
        bare = SimpleNamespace(settings=SimpleNamespace(investigate_every_days=7), extras=None, clock=lambda: NOW)
        self.assertIsNone(run.investigation_wait(bare, "timer"))


class InARealRun(unittest.TestCase):
    def setUp(self):
        counter = iter(range(1, 10_000))
        self.new_id = lambda: f"{next(counter):032x}"  # run_watch makes ids that start again at 1 in every call: two runs of one test would be one record in the store

    def watch(self, clock, extras, trigger, **options):
        return investigating(estate_with_leads(), clock=clock, extras=extras, trigger=trigger, new_id=self.new_id, **options)

    def test_the_first_timer_run_investigates_the_next_one_does_not_and_a_control_run_does_again(self):
        clock = Moving()
        extras = loop_for(clock)
        _, first, _, foundry_one, _ = self.watch(clock, extras, "timer")
        self.assertEqual(len(of_type(first, "investigation.started")), 1)
        self.assertEqual(len(foundry_one.runs), 2)
        self.assertEqual([r.investigated for r in extras.store.runs_recent()], [True])
        clock.advance(days=1)
        _, second, _, foundry_two, _ = self.watch(clock, extras, "timer")
        self.assertEqual(of_type(second, "investigation.started"), [])
        self.assertEqual(foundry_two.runs, [], "no call of the Investigator or the Skeptic")
        notes = [e["note"] for e in of_type(second, "run.note") if "did not run" in e["note"]]
        self.assertEqual(len(notes), 1)
        self.assertIn("the last investigation ran 1 day ago", notes[0])
        self.assertEqual(of_type(second, "run.finished")[0]["investigation"], "off")
        self.assertEqual(sorted(r.investigated for r in extras.store.runs_recent()), [False, True])
        clock.advance(days=1)
        _, third, _, foundry_three, _ = self.watch(clock, extras, "control")
        self.assertEqual(len(of_type(third, "investigation.started")), 1)
        self.assertGreaterEqual(len(foundry_three.runs), 1, "the Investigator ran (the Skeptic has nothing to judge when every resource was judged lately)")

    def test_on_the_days_that_the_investigation_waits_the_leads_go_to_the_detective_and_the_skeptic(self):
        clock = Moving()
        extras = loop_for(clock)
        self.watch(clock, extras, "timer")
        clock.advance(days=1)
        estate = estate_with_leads()
        summary, events, _, _, _ = investigating(estate, clock=clock, extras=extras, trigger="timer", new_id=self.new_id)
        self.assertGreater(len(estate.chat_calls()), 0, "the cheap path judges the leads of the fixed detectors every day")
        self.assertEqual([e["detector"] for e in of_type(events, "case.result") if e["detector"] == "investigation"], [])
        self.assertGreater(len(of_type(events, "case.started")), 0)

    def test_the_seventh_day_investigates_again(self):
        clock = Moving()
        extras = loop_for(clock)
        self.watch(clock, extras, "timer")
        clock.advance(days=7)
        _, again, _, foundry, _ = self.watch(clock, extras, "timer")
        self.assertEqual(len(of_type(again, "investigation.started")), 1)
        self.assertEqual(len(foundry.runs), 2)

    def test_a_fault_after_the_investigation_does_not_make_the_next_timer_pay_again(self):
        from unittest import mock
        from test_run_loop import estate_with
        clock = Moving()
        extras = loop_for(clock)
        with mock.patch.object(run, "work_case", side_effect=RuntimeError("a fault after the investigation")):
            try:
                investigating(estate_with(planted_disk=True), clock=clock, extras=extras, trigger="timer", new_id=self.new_id)
            except Exception:  # noqa: BLE001 (the fault may or may not leave run_watch: the record of the run is what is asserted)
                pass
        records = extras.store.runs_recent()
        self.assertEqual([(r.investigated, r.finished_at) for r in records], [(True, None)], "the record of the run that died says that it investigated")
        clock.advance(days=1)
        _, next_day, _, foundry, _ = self.watch(clock, extras, "timer")
        self.assertEqual(of_type(next_day, "investigation.started"), [])
        self.assertEqual(foundry.runs, [])

    def test_a_run_that_could_not_investigate_does_not_start_the_clock(self):
        clock = Moving()
        extras = loop_for(clock)
        foundry = FakeFoundry()
        foundry.investigator_error = FoundryError("the project is busy")
        investigating(estate_with_leads(), foundry=foundry, clock=clock, extras=extras, trigger="timer", new_id=self.new_id)
        self.assertEqual([r.investigated for r in extras.store.runs_recent()], [False])
        clock.advance(days=1)
        _, next_day, _, _, _ = self.watch(clock, extras, "timer")
        self.assertEqual(len(of_type(next_day, "investigation.started")), 1, "the next day tries again")


if __name__ == "__main__":
    unittest.main()
