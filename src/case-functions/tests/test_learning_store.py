"""The three tables of the learning (lessons, claims, capability profiles): both stores keep them the same way, and the Table store keeps them in tables of their own."""
import json
import unittest

from support import APP_ROOT  # noqa: F401  (puts the app on the path)
from test_store import ACCOUNT, Clock, FakeTables

from cases.http import Client
from cases.memory_store import MemoryStore
from cases.models import CapabilityRecord, ClaimRecord, LessonRecord, StoreError
from cases.store import CLAIMS, LESSONS, PROFILES, TABLES, TableStore, table_calls, type_key

DISKS = "microsoft.compute/disks"
ADDRESSES = "microsoft.network/publicipaddresses"


def lesson(lesson_id="p1", resource_type=DISKS, closed="2026-11-05T09:00:00Z", updated=None, **extra):
    base = dict(lesson_id=lesson_id, resource_type=resource_type, family="advise", detector="investigation", basis="no-usage", proposal="delete",
                signals={"cost": "10-100", "usage": "none"}, confidence=0.9, skeptic="agree", answer="approve", opened_at="2026-11-04T09:00:00Z", closed_at=closed,
                updated_at=updated or closed)
    base.update(extra)
    return LessonRecord(**base)


def claim(claim_id="c1", resource_type=DISKS, read="2026-11-05T09:00:00Z", **extra):
    base = dict(claim_id=claim_id, resource_type=resource_type, kind="minimum-charge", url="https://learn.microsoft.com/en-us/azure/example", quote="A quote of the page.",
                read_at=read, expires_at="2027-02-03T09:00:00Z", checked_at=read)
    base.update(extra)
    return ClaimRecord(**base)


def profile(run_id="r1", at="2026-11-05T05:30:00Z", **extra):
    return CapabilityRecord(run_id=run_id, at=at, subscriptions=3, **extra)


class LearningStoreContract:
    """What every store must do for the records of the learning."""

    def make(self):
        raise NotImplementedError

    def setUp(self):
        self.clock = Clock()
        self.store = self.make()

    def test_a_lesson_is_kept_by_its_plan_and_a_later_put_of_the_same_plan_replaces_it(self):
        self.store.lesson_put(lesson("p1", answer="approve"))
        self.store.lesson_put(lesson("p1", answer="approve", result="verified", predicted_usd_month=20.0, measured_usd_month=18.4, measured_at="2026-11-09T09:00:00Z"))
        (kept,) = self.store.lessons_recent()
        self.assertEqual((kept.result, kept.predicted_usd_month, kept.measured_usd_month), ("verified", 20.0, 18.4))
        self.assertEqual(kept.signals, {"cost": "10-100", "usage": "none"})

    def test_the_lessons_of_one_type_come_newest_closed_first_and_leave_the_other_types_out(self):
        self.store.lesson_put(lesson("a", DISKS, "2026-11-01T09:00:00Z"))
        self.store.lesson_put(lesson("b", DISKS, "2026-11-03T09:00:00Z"))
        self.store.lesson_put(lesson("c", ADDRESSES, "2026-11-02T09:00:00Z"))
        self.assertEqual([x.lesson_id for x in self.store.lessons_of(DISKS)], ["b", "a"])
        self.assertEqual([x.lesson_id for x in self.store.lessons_of(ADDRESSES)], ["c"])
        self.assertEqual(self.store.lessons_of("microsoft.cache/redis"), [])
        self.assertEqual(len(self.store.lessons_of(DISKS, 1)), 1)

    def test_the_recent_lessons_come_newest_updated_first(self):
        self.store.lesson_put(lesson("a", closed="2026-11-01T09:00:00Z", updated="2026-11-08T09:00:00Z"))
        self.store.lesson_put(lesson("b", closed="2026-11-03T09:00:00Z"))
        self.assertEqual([x.lesson_id for x in self.store.lessons_recent()], ["a", "b"])
        self.assertEqual(len(self.store.lessons_recent(1)), 1)

    def test_a_lesson_holds_what_a_closed_request_taught_and_nothing_of_a_person(self):
        names = {f for f in LessonRecord.__dataclass_fields__}
        self.assertFalse({"name", "approver", "approver_oid", "approver_name", "note", "text", "resource_id", "resource_name", "case_id"} & names)

    def test_a_claim_is_kept_by_its_id_by_type_and_newest_read_first(self):
        self.store.claim_put(claim("c1", DISKS, "2026-11-01T09:00:00Z"))
        self.store.claim_put(claim("c2", DISKS, "2026-11-04T09:00:00Z"))
        self.store.claim_put(claim("c3", ADDRESSES, "2026-11-03T09:00:00Z"))
        self.store.claim_put(claim("c1", DISKS, "2026-11-01T09:00:00Z", state="stale"))
        self.assertEqual([c.claim_id for c in self.store.claims_of(DISKS)], ["c2", "c1"])
        self.assertEqual(self.store.claims_of(DISKS)[1].state, "stale")
        self.assertEqual([c.claim_id for c in self.store.claims_recent()], ["c2", "c3", "c1"])
        self.assertEqual(len(self.store.claims_recent(2)), 2)

    def test_the_latest_profile_is_the_newest_and_there_is_none_to_start_with(self):
        self.assertIsNone(self.store.profile_latest())
        self.store.profile_put(profile("r1", "2026-11-05T05:30:00Z", agreement="enterprise"))
        self.store.profile_put(profile("r3", "2026-11-07T05:30:00Z", agreement="customer", reservations="not visible with this access"))
        self.store.profile_put(profile("r2", "2026-11-06T05:30:00Z"))
        latest = self.store.profile_latest()
        self.assertEqual((latest.run_id, latest.agreement, latest.reservations), ("r3", "customer", "not visible with this access"))

    def test_a_record_that_was_written_before_a_field_existed_still_reads(self):
        old = json.dumps({"lesson_id": "p9", "resource_type": DISKS, "family": "advise"})
        self.assertEqual(LessonRecord.from_json(old).answer, "expired")
        self.assertEqual(ClaimRecord.from_json(json.dumps({"claim_id": "c", "resource_type": DISKS, "kind": "other"})).state, "fresh")
        self.assertEqual(CapabilityRecord.from_json(json.dumps({"run_id": "r", "at": "2026-11-05T05:30:00Z"})).reservations, "unknown")


class MemoryStoreKeepsTheLearning(LearningStoreContract, unittest.TestCase):
    def make(self):
        return MemoryStore(clock=self.clock)


class TableStoreKeepsTheLearning(LearningStoreContract, unittest.TestCase):
    def make(self):
        self.service = FakeTables()
        client = Client(table_calls(ACCOUNT), lambda text: text, transport=self.service.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
        return TableStore(client, lambda resource: "token-value", ACCOUNT, clock=self.clock)

    def test_each_kind_has_a_table_of_its_own_and_a_table_is_made_when_it_is_first_written(self):
        self.assertEqual(self.store.lessons_recent(), [])
        self.assertEqual(self.store.claims_of(DISKS), [])
        self.assertEqual(self.service.tables, {}, "a read never makes a table")
        self.store.lesson_put(lesson())
        self.store.claim_put(claim())
        self.store.profile_put(profile())
        self.assertEqual(sorted(self.service.tables), sorted([LESSONS, CLAIMS, PROFILES]))
        self.assertEqual((LESSONS, CLAIMS, PROFILES), ("mnlessons", "mnclaims", "mnprofiles"))
        self.assertTrue({LESSONS, CLAIMS, PROFILES} <= set(TABLES))

    def test_the_calls_to_the_new_tables_are_on_the_list_of_the_store_and_the_list_has_no_other_table(self):
        self.store.lesson_put(lesson())
        self.store.claim_put(claim())
        self.store.profile_put(profile())
        self.store.lessons_of(DISKS)
        self.store.claims_of(DISKS)
        self.store.profile_latest()
        self.assertTrue(all(url.startswith(f"https://{ACCOUNT}.table.core.windows.net/") for _, url in self.service.calls))
        with self.assertRaises(Exception):
            self.store.client.request("GET", f"https://{ACCOUNT}.table.core.windows.net/mnother()")

    def test_a_type_is_kept_in_a_key_form_that_a_filter_may_hold(self):
        self.assertEqual(type_key(DISKS), "microsoft.compute_disks")
        self.store.lesson_put(lesson("p1", DISKS))
        rows = [row for (_, key), (row, _) in self.service.tables[LESSONS].items()]
        self.assertEqual([row["rtype"] for row in rows], ["microsoft.compute_disks"])
        self.assertEqual(rows[0]["PartitionKey"], "l")

    def test_a_type_with_a_character_that_a_filter_may_not_hold_is_refused_before_a_call(self):
        before = len(self.service.calls)
        for bad in ("a'b/c", "a b/c", "x" * 201):
            with self.assertRaises(StoreError):
                self.store.lessons_of(bad)
        self.assertEqual(len(self.service.calls), before)

    def test_the_latest_profile_is_the_first_row_because_the_key_sorts_the_newest_first(self):
        self.store.profile_put(profile("r1", "2026-11-05T05:30:00Z"))
        self.store.profile_put(profile("r2", "2026-11-07T05:30:00Z"))
        keys = sorted(key for (_, key), _ in self.service.tables[PROFILES].items())
        self.assertTrue(keys[0].endswith("_r2"), keys)
        before = len(self.service.calls)
        self.store.profile_latest()
        self.assertIn("$top=1&", self.service.calls[before][1])


if __name__ == "__main__":
    unittest.main()
