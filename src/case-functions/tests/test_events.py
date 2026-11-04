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

    def test_a_request_id_of_none_is_null(self):
        with LogCapture() as capture:
            History("r" * 32, None, fixed_clock, Redactor()).emit("run.note", note="x")
        self.assertIsNone(capture.events()[0]["requestId"])

    def test_non_ascii_is_escaped_so_that_the_line_is_plain_ascii(self):
        with LogCapture() as capture:
            history().emit("run.note", note="Zoë and 日本")
        self.assertTrue(capture.messages()[0].isascii())
        self.assertEqual(capture.events()[0]["note"], "Zoë and 日本")


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
