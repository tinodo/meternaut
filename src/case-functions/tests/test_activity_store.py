"""The record of an investigation (docs/proposals/23-what-the-ai-looked-at.md): both stores keep it the same way, the newest 20 are kept, and the Table store has a table of its own for it."""
import json
import unittest

from support import APP_ROOT  # noqa: F401  (puts the app on the path)
from test_store import ACCOUNT, Clock, FakeTables

from cases.http import Client
from cases.memory_store import MemoryStore
from cases.models import INVESTIGATION_ENDS, KEPT_INVESTIGATIONS, InvestigationRecord
from cases.store import INVESTIGATIONS, MAX_DATA, TABLES, TableStore, table_calls


def record(n: int, **more) -> InvestigationRecord:
    """The n-th investigation, one a day from 2026-11-01."""
    base = dict(run_id=f"run{n:03d}", at=f"2026-11-{n:02d}T05:30:00Z", trigger="timer", investigator="model-a", skeptic="model-b", calls=12, max_calls=30, tokens=1500, seconds=90,
                max_seconds=600, end="answered", answered=True, examined=("a phrase of the AI",), known=5, looked=3)
    base.update(more)
    return InvestigationRecord(**base)


class InvestigationContract:
    """What every store must do for the records of the investigations."""

    def make(self):
        raise NotImplementedError

    def setUp(self):
        self.clock = Clock()
        self.store = self.make()

    def test_there_is_none_to_start_with(self):
        self.assertEqual(self.store.investigations_recent(), [])

    def test_the_records_come_newest_first_and_a_limit_cuts_the_oldest(self):
        for n in (3, 1, 2):
            self.store.investigation_put(record(n))
        self.assertEqual([r.run_id for r in self.store.investigations_recent()], ["run003", "run002", "run001"])
        self.assertEqual([r.run_id for r in self.store.investigations_recent(2)], ["run003", "run002"])

    def test_a_record_comes_back_as_it_was_kept(self):
        full = record(5, findings=({"n": 1, "basis": "no-usage", "says": "A sentence.", "fates": {"request": 2}},), kinds=(["contoso.example/widgets", "lm"],), unread=("contoso.example/gadgets",),
                      note="a note", stop="tokens", subs=3, subs_costed=2)
        self.store.investigation_put(full)
        (kept,) = self.store.investigations_recent()
        self.assertEqual(kept, full)
        self.assertEqual(kept.findings[0]["fates"], {"request": 2})

    def test_only_the_newest_twenty_are_kept_whatever_the_order_in_which_they_were_written(self):
        self.assertEqual(KEPT_INVESTIGATIONS, 20)
        for n in list(range(10, 29)) + list(range(1, 10)):
            self.store.investigation_put(record(n))
        kept = [r.run_id for r in self.store.investigations_recent(100)]
        self.assertEqual(kept, [f"run{n:03d}" for n in range(28, 8, -1)])

    def test_the_same_run_written_twice_is_one_record(self):
        self.store.investigation_put(record(4, calls=5))
        self.store.investigation_put(record(4, calls=9))
        (kept,) = self.store.investigations_recent()
        self.assertEqual(kept.calls, 9)

    def test_a_record_that_was_written_before_a_field_existed_still_reads_and_a_newer_one_reads_in_an_older_version(self):
        old = InvestigationRecord.from_json(json.dumps({"run_id": "r", "at": "2026-11-05T05:30:00Z"}))
        self.assertEqual((old.end, old.answered, old.examined, old.findings, old.known, old.unread), ("failed", False, (), (), 0, ()))
        newer = InvestigationRecord.from_json(json.dumps({"run_id": "r", "at": "2026-11-05T05:30:00Z", "a_field_of_the_future": 1, "examined": ["x"]}))
        self.assertEqual(newer.examined, ("x",))

    def test_the_words_of_how_an_investigation_ended(self):
        self.assertEqual(INVESTIGATION_ENDS, ("answered", "time", "calls", "refused", "failed"))


class MemoryStoreKeepsInvestigations(InvestigationContract, unittest.TestCase):
    def make(self):
        return MemoryStore(clock=self.clock)


class TableStoreKeepsInvestigations(InvestigationContract, unittest.TestCase):
    def make(self):
        self.service = FakeTables()
        client = Client(table_calls(ACCOUNT), lambda text: text, transport=self.service.transport, sleep=lambda s: None, monotonic=lambda: 0.0)
        return TableStore(client, lambda resource: "token-value", ACCOUNT, clock=self.clock)

    def test_it_has_a_table_of_its_own_that_is_made_when_it_is_first_written_and_never_by_a_read(self):
        self.assertEqual(self.store.investigations_recent(), [])
        self.assertEqual(self.service.tables, {}, "a read never makes a table")
        self.store.investigation_put(record(1))
        self.assertEqual(list(self.service.tables), [INVESTIGATIONS])
        self.assertEqual(INVESTIGATIONS, "mninvestigations")
        self.assertIn(INVESTIGATIONS, TABLES, "the calls to it are on the list of the calls that the store may make")

    def test_the_key_sorts_the_newest_first_and_a_write_that_makes_the_twenty_first_deletes_the_oldest_row(self):
        for n in range(1, 22):
            self.store.investigation_put(record(n))
        keys = sorted(key for (_, key), _ in self.service.tables[INVESTIGATIONS].items())
        self.assertEqual(len(keys), 20)
        self.assertTrue(keys[0].endswith("_run021") and keys[-1].endswith("_run002"), keys)
        deletes = [url for method, url in self.service.calls if method == "DELETE"]
        self.assertEqual(len(deletes), 1)

    def test_a_record_is_kept_in_one_property_that_is_far_below_the_largest_that_the_store_writes(self):
        self.store.investigation_put(record(1))
        ((row, _),) = self.service.tables[INVESTIGATIONS].values()
        self.assertLess(len(row["data"]), MAX_DATA // 10)
        self.assertEqual(row["PartitionKey"], "i")


if __name__ == "__main__":
    unittest.main()
