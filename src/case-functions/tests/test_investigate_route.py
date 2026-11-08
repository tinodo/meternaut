"""Tests of what the investigation says in the History when a call of an agent through a connection fails, and of a model name with a slash on the pages and in the letters (docs/proposals/08-ai-gateway.md, step 2).

The fixed words come from the Foundry client (test_foundry_route): here they are the reason of a failed investigation, of agents that were not made ready and of a Skeptic that could not judge. The words of the Agent
Service as they came are kept in a note of their own, so that a cause that the fixed words did not name right can still be read. An error without fixed words is reported exactly as it always was.
"""
import unittest

from support import APP_ROOT  # noqa: F401  (puts the app on the path)
from test_foundry import JWT, Rig
from test_foundry_route import KINDS, NOT_FOUND, ROUTED, expected, failing
from test_investigate import FakeFoundry, Harness, make_settings
from test_letters import BASE, NOW, PERSON, make_case as make_letter_case, make_plan as make_letter_plan
from test_web_pages import INVESTIGATED
from test_web_support import Console, make_case
from cases import letters
from cases.foundry import FoundryError
from cases.roles import clean_text

INVESTIGATOR_MODEL, SKEPTIC_MODEL = "aigateway/gpt-6.1-sol", "aigateway/gpt-6-luna"
SETTINGS = make_settings(foundry_model_investigator=INVESTIGATOR_MODEL, foundry_model_skeptic=SKEPTIC_MODEL)
SERVICE_TEXT = "Foundry response failed: HTTP 404; DNS of the endpoint host: private; model_not_found: The model does not exist on the connection."


def routed_error(status=404, code="model_not_found", text=SERVICE_TEXT, route=None):
    """An error of the Foundry client as it leaves it for a model behind a connection: its own text, its status and its code, and the fixed words."""
    error = FoundryError(text)
    kind = next(kind for kind in KINDS if kind[0] == status)
    error.status, error.code, error.route = status, code, route if route is not None else expected(kind[3], kind[4], status, code)
    return error


class WhenAnAgentOnAConnectionCannotBeMadeReady(unittest.TestCase):
    def test_the_reason_is_the_fixed_words_and_the_words_of_the_service_are_a_note_of_their_own(self):
        foundry = FakeFoundry()
        foundry.ensure_error = routed_error()
        h = Harness(foundry, settings=SETTINGS)
        result = h.go()
        self.assertEqual((result.ran, result.note), (False, f"the agents could not be made ready ({expected(*NOT_FOUND, 404, 'model_not_found')})"))
        self.assertEqual([(e["type"], e["note"]) for e in h.events], [("run.note", f"the words of the Agent Service: {SERVICE_TEXT}")])
        self.assertEqual(h.notes, [f"the words of the Agent Service: {SERVICE_TEXT}"])

    def test_an_error_without_fixed_words_is_what_it_always_was(self):
        foundry = FakeFoundry()
        error = FoundryError("Foundry create agent failed: HTTP 400; invalid_request_error: The definition is not valid.")
        error.status, error.code = 400, "invalid_request_error"
        foundry.ensure_error = error
        h = Harness(foundry, settings=SETTINGS)
        result = h.go()
        self.assertEqual(result.note, "the agents could not be made ready (Foundry create agent failed: HTTP 400; invalid_request_error: The definition is not valid.)")
        self.assertEqual((h.events, h.notes), ([], []))


class WhenTheInvestigatorOnAConnectionGivesNoAnswer(unittest.TestCase):
    def test_the_note_of_the_investigation_and_its_end_say_why_in_the_fixed_words(self):
        for status, code, _, cause, check in KINDS:
            with self.subTest(status=status):
                foundry = FakeFoundry()
                foundry.investigator_error = routed_error(status, code, f"Foundry response failed: HTTP {status}; {code}: some words of the service")
                h = Harness(foundry, settings=SETTINGS)
                result = h.go()
                self.assertEqual(result.note, f"the investigator gave no answer ({expected(cause, check, status, code)})")
                self.assertEqual([e["type"] for e in h.events], ["investigation.started", "run.note", "investigation.finished"])
                started, words, end = h.events
                self.assertEqual((started["modelInvestigator"], started["modelSkeptic"]), (INVESTIGATOR_MODEL, SKEPTIC_MODEL))
                self.assertEqual(words["note"], f"the words of the Agent Service: Foundry response failed: HTTP {status}; {code}: some words of the service")
                self.assertEqual((end["ok"], end["note"]), (False, result.note))
                line = f"the investigation did not run: {result.note}"
                self.assertEqual(clean_text(line, 300), line, "the line that the run writes is not cut")

    def test_an_error_without_fixed_words_is_what_it_always_was(self):
        foundry = FakeFoundry()
        foundry.investigator_error = FoundryError("the budget of the run was reached")
        h = Harness(foundry, settings=SETTINGS)
        result = h.go()
        self.assertEqual(result.note, "the investigator gave no answer (the budget of the run was reached)")
        self.assertEqual([e["type"] for e in h.events], ["investigation.started", "investigation.finished"])
        self.assertEqual(h.notes, [])

    def test_the_words_of_the_service_are_redacted_and_cut_and_the_fixed_words_hold_no_secret(self):
        text = f"Foundry response failed: HTTP 403; PermissionDenied: api-key: SECRETKEYVALUE Bearer abcdefgh12345678 {JWT} " + "x" * 600
        foundry = FakeFoundry()
        foundry.investigator_error = routed_error(403, "PermissionDenied", text)
        h = Harness(foundry, settings=SETTINGS)
        result = h.go()
        everything = "\n".join([result.note, *h.notes, *h.messages, *(str(e) for e in h.events)])
        for secret in ("SECRETKEYVALUE", "abcdefgh12345678", JWT):
            self.assertNotIn(secret, everything)
        self.assertEqual(result.note, f"the investigator gave no answer ({expected(KINDS[1][3], KINDS[1][4], 403, 'PermissionDenied')})")
        self.assertTrue(all(len(e["note"]) <= 300 for e in h.of("run.note")))

    def test_the_whole_chain_from_the_service_to_the_history(self):
        for answer, stage in ((failing(403, "PermissionDenied", "The gateway refused the identity of the project."), "the investigator gave no answer"),
                              (failing(404, "model_not_found", "The model does not exist on the connection."), "the investigator gave no answer"),
                              (failing(429, "rate_limit_exceeded", "Too many requests."), "the investigator gave no answer")):
            with self.subTest(status=answer[0]):
                rig = Rig()
                rig.service.failures["POST responses"] = answer
                h = Harness(foundry=rig.foundry, settings=SETTINGS)
                result = h.go()
                kind = next(kind for kind in KINDS if kind[0] == answer[0])
                self.assertEqual(result.note, f"{stage} ({expected(kind[3], kind[4], answer[0], kind[1])})")
                self.assertEqual(rig.service.routes()[-1], "DELETE conversation", "the conversation is deleted")
        rig = Rig()
        rig.service.failures["POST agents"] = failing(404, "model_not_found", "The model does not exist on the connection.")
        h = Harness(foundry=rig.foundry, settings=SETTINGS)
        self.assertEqual(h.go().note, f"the agents could not be made ready ({expected(*NOT_FOUND, 404, 'model_not_found')})")
        self.assertEqual(rig.service.routes(), ["GET agent", "POST agents"])


class WhenTheSkepticOnAConnectionCannotJudge(unittest.TestCase):
    def test_the_step_and_the_note_of_the_run_say_why_in_the_fixed_words(self):
        for status, code, _, cause, check in KINDS:
            with self.subTest(status=status):
                foundry = FakeFoundry()
                foundry.skeptic_error = routed_error(status, code, f"Foundry response failed: HTTP {status}; {code}: some words of the service")
                h = Harness(foundry, settings=SETTINGS, with_store=True)
                h.go()
                fixed = expected(cause, check, status, code)
                steps = {c.steps[1]["note"] for c in h.store.cases_recent()}
                self.assertEqual(steps, {fixed})
                self.assertIn(f"the Skeptic could not judge every finding ({fixed}); a finding without a verdict needs a person", h.notes)
                self.assertIn(f"the words of the Agent Service: Foundry response failed: HTTP {status}; {code}: some words of the service", h.notes)
                self.assertEqual((h.result.ran, h.result.needs_human), (True, 2), "the findings are left to a person, as they were")

    def test_an_error_without_fixed_words_is_what_it_always_was(self):
        foundry = FakeFoundry()
        foundry.skeptic_error = FoundryError("the project is busy")
        h = Harness(foundry, settings=SETTINGS, with_store=True)
        h.go()
        self.assertEqual({c.steps[1]["note"] for c in h.store.cases_recent()}, {"the project is busy"})
        self.assertIn("the Skeptic could not judge every finding (the project is busy); a finding without a verdict needs a person", h.notes)
        self.assertFalse([n for n in h.notes if n.startswith("the words of the Agent Service")])


class AModelNameWithASlash(unittest.TestCase):
    def test_it_is_named_in_the_events_the_cases_and_the_steps_exactly_as_it_was_set(self):
        h = Harness(settings=SETTINGS, with_store=True)
        h.go()
        started = h.of("investigation.started")[0]
        self.assertEqual((started["modelInvestigator"], started["modelSkeptic"]), (INVESTIGATOR_MODEL, SKEPTIC_MODEL))
        self.assertEqual([s.model for s in h.foundry.specs], [INVESTIGATOR_MODEL, SKEPTIC_MODEL])
        case = h.store.cases_recent()[0]
        self.assertEqual(case.models, {"investigator": INVESTIGATOR_MODEL, "skeptic": SKEPTIC_MODEL})
        self.assertEqual([step["model"] for step in case.steps], [INVESTIGATOR_MODEL, SKEPTIC_MODEL])

    def test_the_page_of_the_case_the_footer_and_the_letters_show_it_whole(self):
        slashed = {**INVESTIGATED, "models": {"investigator": INVESTIGATOR_MODEL, "skeptic": SKEPTIC_MODEL},
                   "steps": ({**INVESTIGATED["steps"][0], "model": INVESTIGATOR_MODEL}, {**INVESTIGATED["steps"][1], "model": SKEPTIC_MODEL})}
        console = Console(models=(INVESTIGATOR_MODEL, SKEPTIC_MODEL))
        console.seed()
        console.store.case_put(make_case(**slashed))
        reply = console.get("/why/case0100")
        self.assertEqual(reply.status, 200)
        self.assertEqual([row["Model"] for row in reply.table("steps").rows], [INVESTIGATOR_MODEL, SKEPTIC_MODEL])
        labels = [p.text() for p in reply.main.find_all("p", class_="quote-label")]
        self.assertEqual(labels[2:], [f"Written by AI (model: {INVESTIGATOR_MODEL}): summary", f"Written by AI (model: {SKEPTIC_MODEL}): objection 1"])
        line = f"Written by an AI (models: {INVESTIGATOR_MODEL}, {SKEPTIC_MODEL}); a person approves every change."
        self.assertIn(line, reply.root.find("footer").text())
        letter = letters.approval_letter(make_letter_plan(), make_letter_case(detector="investigation", models=slashed["models"]), PERSON, BASE, NOW)
        self.assertIn(line, letter.text)


if __name__ == "__main__":
    unittest.main()
