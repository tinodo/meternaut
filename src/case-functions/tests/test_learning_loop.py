"""The timer of the loop keeps the lessons: a request that has ended leaves its lesson, and nothing of a person or of the estate is in it."""
import dataclasses
import json
import unittest
from unittest import mock

from test_loop_end_to_end import DISK, GROUP, OID, Story, watch

from cases import learning


class TheTimerKeepsTheLessons(Story):
    def after_approval(self):
        watch(self.world, self.clock)
        (plan,) = self.store.plans_open()
        self.assertEqual(self.approve(plan).status, 200)
        return plan

    def test_the_lesson_of_an_approved_change_is_written_by_the_timer_and_holds_no_name_and_no_id(self):
        plan = self.after_approval()
        self.assertEqual(self.store.lessons_recent(), [], "the person's answer writes none: the timer does")
        self.tick()
        (lesson,) = self.store.lessons_recent()
        self.assertEqual((lesson.lesson_id, lesson.resource_type, lesson.family, lesson.answer, lesson.result), (plan.plan_id, "microsoft.compute/disks", "delete-disk", "approve", "ran"))
        self.assertEqual((lesson.detector, lesson.skeptic, lesson.proposal), ("orphan-managed-disk", "agree", "delete"))
        self.assertEqual(lesson.predicted_usd_month, plan.saving_usd_month)
        text = json.dumps(dataclasses.asdict(lesson)).lower()
        for private in ("planted-disk-1", GROUP, OID, "tino", "subscriptions", "http"):
            self.assertNotIn(private.lower(), text)
        rows = self.world.tables.tables["mnlessons"]
        self.assertEqual(len(rows), 1)
        self.assertNotIn(DISK.lower(), repr(rows).lower())

    def test_the_one_answered_request_is_counted_for_its_type_and_family_and_is_too_little_to_say_anything(self):
        self.after_approval()
        self.tick()
        past = learning.past_of(self.store.lessons_of("microsoft.compute/disks"), "microsoft.compute/disks", "delete-disk")
        self.assertEqual((past.answered, past.approved), (1, 1))
        self.assertFalse(learning.digest_of(past)["enough"])

    def test_the_sweep_runs_in_each_fifth_minute_of_the_hour_and_only_there(self):
        calls = []
        with mock.patch.object(learning, "sync", side_effect=lambda store, now, **kwargs: calls.append(now.minute)):
            for minute in (0, 1, 4, 5, 6, 30, 59):
                self.clock.now = self.clock.now.replace(minute=minute)
                self.tick()
        self.assertEqual(calls, [0, 5, 30])

    def test_a_second_tick_changes_nothing_that_the_first_wrote(self):
        self.after_approval()
        self.tick()
        before = repr(self.world.tables.tables["mnlessons"])
        self.clock.advance(seconds=20)
        self.tick()
        self.assertEqual(repr(self.world.tables.tables["mnlessons"]), before)

    def test_a_timer_that_finds_no_ended_request_makes_no_lesson_table(self):
        watch(self.world, self.clock)
        self.tick()
        self.assertNotIn("mnlessons", self.world.tables.tables)


if __name__ == "__main__":
    unittest.main()
