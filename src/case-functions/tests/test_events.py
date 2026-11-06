import json
import logging
import unittest

from support import KEY, LogCapture, NOW, fixed_clock
from cases import events
from cases.events import EVENT_PREFIX, History, KINDS
from cases.redact import Redactor


def history(redact=None):
    return History("r" * 32, "a" * 32, fixed_clock, redact or Redactor())


class Lines(unittest.TestCase):
    def test_a_line_is_the_prefix_and_one_compact_json_object_with_the_fixed_fields(self):
        with LogCapture() as capture:
            returned = history().emit("run.started", trigger="control", scopes=["11111111"], detectors=["a", "b"])
        (message,) = capture.messages()
        self.assertTrue(message.startswith("meternaut_event "))
        document = json.loads(message[len(EVENT_PREFIX):])
        self.assertEqual(document, returned)
        self.assertEqual(document, {"v": 1, "ts": "2026-11-04T12:00:00Z", "runId": "r" * 32, "requestId": "a" * 32, "type": "run.started", "trigger": "control",
                                    "scopes": ["11111111"], "detectors": ["a", "b"]})
        body = message[len(EVENT_PREFIX):]
        self.assertNotIn(", ", body, "compact: no space after a comma")
        self.assertNotIn('": ', body, "compact: no space after a colon")

    def test_the_line_is_logged_at_information_so_that_the_host_keeps_it(self):
        with LogCapture() as capture:
            history().emit("run.note", note="x")
        self.assertEqual([r.levelno for r in capture.records], [logging.INFO])

    def test_the_kinds_are_the_ones_of_the_proposal_and_another_is_refused(self):
        self.assertEqual(KINDS, ("run.started", "run.note", "lead.found", "case.started", "case.step", "case.result", "run.finished", "run.failed"))
        with self.assertRaises(ValueError):
            history().emit("run.exploded")

    def test_the_lines_of_the_investigation_are_kinds_of_their_own_and_the_kinds_that_the_tools_read_are_the_same(self):
        self.assertEqual(events.INVESTIGATION_KINDS, ("investigation.started", "investigation.finding", "investigation.finished"))
        self.assertFalse(set(events.INVESTIGATION_KINDS) & set(KINDS + events.LOOP_KINDS))
        with LogCapture() as capture:
            for kind in events.INVESTIGATION_KINDS:
                history().emit(kind, note="x")
        self.assertEqual([e["type"] for e in capture.events()], list(events.INVESTIGATION_KINDS))
        with self.assertRaises(ValueError):
            history().emit("investigation.exploded")

    def test_a_request_id_of_none_is_null(self):
        with LogCapture() as capture:
            History("r" * 32, None, fixed_clock, Redactor()).emit("run.note", note="x")
        self.assertIsNone(capture.events()[0]["requestId"])

    def test_non_ascii_is_escaped_so_that_the_line_is_plain_ascii(self):
        with LogCapture() as capture:
            history().emit("run.note", note="Zoë and 日本")
        self.assertTrue(capture.messages()[0].isascii())
        self.assertEqual(capture.events()[0]["note"], "Zoë and 日本")


class Counting(unittest.TestCase):
    """The History counts its own lines by kind, so that the end of a run can say how many lines of the investigation were written without anyone counting by hand."""

    KINDS = ("run.started", "run.note", "run.note", "investigation.started", "investigation.finding", "investigation.finding", "investigation.finished", "case.result")

    def test_a_history_counts_the_lines_that_it_wrote_by_kind(self):
        recorded = history()
        with LogCapture() as capture:
            for kind in self.KINDS:
                recorded.emit(kind, note="x")
        self.assertEqual(dict(recorded.counts), {"run.started": 1, "run.note": 2, "investigation.started": 1, "investigation.finding": 2, "investigation.finished": 1,
                                                 "case.result": 1})
        self.assertEqual(recorded.lines(), len(capture.messages()), "one count for each line that went to the log")

    def test_the_lines_of_a_prefix_are_the_lines_of_the_kinds_that_start_with_it(self):
        recorded = history()
        with LogCapture():
            for kind in self.KINDS:
                recorded.emit(kind, note="x")
        self.assertEqual((recorded.lines("investigation."), recorded.lines("run."), recorded.lines("case."), recorded.lines("investigation.finding"), recorded.lines()),
                         (4, 3, 1, 2, 8))
        self.assertEqual((recorded.lines("nothing."), recorded.lines("investigation"), recorded.lines("finding")), (0, 4, 0))

    def test_a_history_that_wrote_nothing_has_counted_nothing_and_each_history_counts_only_its_own_lines(self):
        first, second = history(), history()
        self.assertEqual((first.lines(), first.lines("investigation."), dict(first.counts)), (0, 0, {}))
        with LogCapture():
            first.emit("investigation.started")
            first.emit("investigation.finished")
        self.assertEqual((first.lines("investigation."), second.lines("investigation.")), (2, 0))

    def test_a_kind_that_is_refused_is_not_counted(self):
        recorded = history()
        with self.assertRaises(ValueError):
            recorded.emit("investigation.exploded")
        self.assertEqual(recorded.lines(), 0)

    def test_a_line_that_was_cut_to_fit_is_one_line_and_is_counted_once(self):
        recorded = history()
        with LogCapture() as capture:
            recorded.emit("investigation.finding", summary="s" * 9000, note="n" * 9000, reason="r" * 9000, finding=1)
        self.assertEqual((recorded.lines("investigation."), len(capture.messages())), (1, 1))

    def test_the_lines_of_the_investigation_are_the_three_kinds_of_investigation_kinds(self):
        recorded = history()
        with LogCapture():
            for kind in events.INVESTIGATION_KINDS + KINDS[:2]:
                recorded.emit(kind, note="x")
        self.assertEqual({kind: recorded.counts[kind] for kind in events.INVESTIGATION_KINDS}, {kind: 1 for kind in events.INVESTIGATION_KINDS})
        self.assertTrue(all(kind.startswith("investigation.") for kind in events.INVESTIGATION_KINDS))
        self.assertEqual(recorded.lines("investigation."), len(events.INVESTIGATION_KINDS))


class Secrets(unittest.TestCase):
    def test_a_secret_in_a_field_is_redacted_before_it_is_logged(self):
        redact = Redactor()
        redact.add(KEY)
        with LogCapture() as capture:
            history(redact).emit("run.failed", reason=f"the gateway said {KEY} and api-key: abcdef123456")
        self.assertNotIn(KEY, "\n".join(capture.messages()))
        self.assertNotIn("abcdef123456", "\n".join(capture.messages()))
        self.assertIn("[redacted]", capture.events()[0]["reason"])


class Size(unittest.TestCase):
    def test_a_short_line_is_left_alone(self):
        with LogCapture() as capture:
            history().emit("case.result", summary="short", objections=["a"])
        self.assertEqual(capture.events()[0]["summary"], "short")

    def test_a_line_that_is_too_long_loses_its_objections_first_then_is_cut(self):
        with LogCapture() as capture:
            history().emit("case.result", caseId="c", summary="s" * 300, objections=["o" * 200] * 60, status="proposed")
        (message,) = capture.messages()
        self.assertLessEqual(len(message), events.MAX_LINE)
        document = capture.events()[0]
        self.assertNotIn("objections", document)
        self.assertEqual((document["status"], document["caseId"]), ("proposed", "c"))
        self.assertEqual(document["summary"], "s" * 300, "the objections went first and that was enough")

    def test_after_the_objections_the_texts_are_cut_to_200_characters_and_only_then_dropped(self):
        with LogCapture() as capture:
            history().emit("case.result", caseId="c", summary="s" * 9000, status="needs_human")
        document = capture.events()[0]
        self.assertEqual((len(document["summary"]), document["summary"][-3:]), (200, "..."))
        with LogCapture() as capture:
            history().emit("case.result", caseId="c", summary="s" * 100, note="n" * 9000, status="needs_human")
        document = capture.events()[0]
        self.assertEqual((document["summary"], len(document["note"])), ("s" * 100, 200))
        with LogCapture() as capture:
            history().emit("case.result", caseId="c", summary="s" * 100, extra=["x" * 100] * 100, status="needs_human")
        document = capture.events()[0]
        self.assertNotIn("summary", document, "cutting was not enough, so the texts went")

    def test_a_line_that_cannot_be_shrunk_keeps_only_its_identity(self):
        with LogCapture() as capture:
            history().emit("run.started", scopes=["x" * 9000])
        document = capture.events()[0]
        self.assertEqual(sorted(document), ["requestId", "runId", "ts", "type", "v"])
        self.assertLessEqual(len(capture.messages()[0]), events.MAX_LINE)


if __name__ == "__main__":
    unittest.main()
