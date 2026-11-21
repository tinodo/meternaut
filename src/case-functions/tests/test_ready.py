"""The job `ready` (cases/ready.py): the three agents made from the lock before any run, through the harness, with no model call and typed lines only.

The real Foundry client runs against the fake Agent Service of tests/test_foundry.py, with the real harness and the real lock of the repository, so that `made` and `existing` are what the service did
and not what a fake says. Every name is invented (AGENTS.md rule 17).
"""
import json
import re
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest import mock

from support import ENV, ENV_NO_PROJECT, LogCapture, Ticker, fixed_clock, identity_fetch

from cases import agents, foundry as foundry_module, harness as harness_module, http, library, lockfile, ready, toolbox
from cases.events import History
from cases.foundry import FoundryError, Made
from cases.harness import HarnessRefused
from cases.http import Client
from cases.memory_store import MemoryStore, stamp
from cases.models import SwitchRecord
from cases.redact import Redactor

from test_foundry import ENDPOINT, HOST, Rig, Service, spec
from test_investigate import make_settings

LOCK = lockfile.load()
NAMES = (agents.INVESTIGATOR_NAME, agents.SKEPTIC_NAME, agents.SCHOLAR_NAME)
GUID = "99999999-aaaa-bbbb-cccc-dddddddddddd"
HOSTILE = f"no access to /subscriptions/{GUID}/resourceGroups/rg-secret/providers/Microsoft.Example/things/thing-secret; api-key: abcdef1234567890"
AGENT_ROUTES = {"GET agent", "POST agents", "POST versions"}
LINE_KEYS = {"v", "ts", "runId", "requestId", "type", "agent", "version", "definition", "outcome", "reason", "status"}
END_KEYS = {"v", "ts", "runId", "requestId", "type", "ok", "made", "existing", "refused", "failed", "why", "seconds"}


def locked(name: str) -> str:
    entry = LOCK.agents[name]
    return f"{entry['connection']}/{entry['model']}"


def settings_of(**changes):
    """The settings with the models that the lock says: what the definitions of the three agents come to is then what the lock holds."""
    values = {"foundry_model_investigator": locked(agents.INVESTIGATOR_NAME), "foundry_model_skeptic": locked(agents.SKEPTIC_NAME), **changes}
    return replace(make_settings(), **values)


class World:
    """One job with its fakes: the fake Agent Service, a store of switches, the real harness around the real client, and a History that is read back."""

    def __init__(self, rig=None, store="memory", lock=LOCK, lock_error="", **changes):
        self.rig = rig or Rig()
        self.settings = settings_of(**changes)
        self.store = MemoryStore(clock=fixed_clock) if store == "memory" else store
        self.alerts, self.redact, self.ticker = [], Redactor(), Ticker()
        self.history = History("r" * 32, "a" * 32, fixed_clock, self.redact)
        self.harness = harness_module.Harness(foundry=self.rig.foundry, store=self.store, lock=lock, lock_error=lock_error, budget=harness_module.Budget.of(self.settings),
                                              brake=harness_module.Brake(self.store, lambda code, detail: self.alerts.append(code), fixed_clock, self.redact), clock=fixed_clock,
                                              monotonic=self.ticker, redact=self.redact)

    def go(self):
        with LogCapture() as capture:
            self.done = ready.execute(self.history, self.settings, self.harness, self.ticker)
        self.log, self.events = capture.messages(), capture.events()
        return self

    @property
    def lines(self):
        return [event for event in self.events if event["type"] == "agents.ready"]

    @property
    def end(self):
        (end,) = [event for event in self.events if event["type"] == "agents.ready.finished"]
        return end

    def outcomes(self):
        return [(line["agent"], line["outcome"], line.get("reason")) for line in self.lines]

    def harness_lines(self):
        return [json.loads(message.split(" ", 1)[1]) for message in self.log if message.startswith("harness.run ")]


class TheAgentsAreMadeFromTheLock(unittest.TestCase):
    def test_a_project_without_the_agents_gets_the_three_made_and_each_line_says_what_it_made(self):
        world = World().go()
        self.assertEqual(world.outcomes(), [(name, "made", None) for name in NAMES])
        for line in world.lines:
            self.assertEqual((line["version"], line["definition"]), (1, LOCK.definition_sha256(line["agent"])[:12]), line["agent"])
            self.assertEqual(len(line["definition"]), 12)
        self.assertEqual(sorted(world.rig.service.agents), sorted(NAMES))
        end = world.end
        self.assertEqual((end["ok"], end["made"], end["existing"], end["refused"], end["failed"], end["why"]), (True, 3, 0, 0, 0, ""))

    def test_a_second_job_finds_the_three_existing_makes_no_version_and_writes_the_same_digests(self):
        first = World().go()
        again = World(rig=first.rig)
        first.rig.service.calls.clear()
        again.go()
        self.assertEqual(again.outcomes(), [(name, "existing", None) for name in NAMES])
        self.assertEqual([line["version"] for line in again.lines], [1, 1, 1])
        self.assertEqual([line["definition"] for line in again.lines], [line["definition"] for line in first.lines])
        self.assertEqual(set(first.rig.service.routes()), {"GET agent"}, "one read for each agent and the read back, and no write: nothing was made")
        self.assertEqual((again.end["ok"], again.end["made"], again.end["existing"]), (True, 0, 3))

    def test_an_agent_whose_stored_version_is_not_the_one_of_the_code_gets_a_new_version_and_the_others_stay(self):
        first = World().go()
        first.rig.service.agents[agents.SKEPTIC_NAME][-1]["metadata"] = {foundry_module.HASH_KEY: "0" * 64}
        again = World(rig=first.rig).go()
        self.assertEqual(again.outcomes(), [(agents.INVESTIGATOR_NAME, "existing", None), (agents.SKEPTIC_NAME, "made", None), (agents.SCHOLAR_NAME, "existing", None)])
        self.assertEqual([line["version"] for line in again.lines], [1, 2, 1])
        self.assertEqual((again.end["made"], again.end["existing"]), (1, 2))

    def test_the_versions_are_made_through_the_harness_and_so_the_job_has_its_lock_its_switches_and_its_line_of_a_refused_run(self):
        world = World()
        world.go()
        self.assertEqual([record.agent for record in world.harness.records], list(NAMES), "harness.ensure made each one: no agent was made by the client alone")
        self.assertEqual(world.harness_lines(), [], "an agent that was made ready and not run has no line of a run")

    def test_the_job_calls_no_model_and_reads_nothing_of_the_estate_it_only_reads_agents_and_makes_them(self):
        world = World().go()
        self.assertTrue(set(world.rig.service.routes()) <= AGENT_ROUTES, world.rig.service.routes())
        self.assertEqual({call["host"] for call in world.rig.service.calls}, {HOST})
        self.assertFalse([call for call in world.rig.service.calls if call["path"].startswith("/openai/")])

    def test_ensure_agent_gives_a_made_reference_only_when_it_made_the_version_and_it_still_is_the_text_name_colon_version(self):
        rig = Rig()
        made = rig.foundry.ensure_agent(spec())
        self.assertIsInstance(made, Made)
        self.assertEqual(made, f"{spec().name}:1")
        existing = rig.foundry.ensure_agent(spec())
        self.assertNotIsInstance(existing, Made)
        self.assertEqual((existing, type(existing)), (f"{spec().name}:1", str))
        newer = rig.foundry.ensure_agent(spec(instructions="You find more."))
        self.assertEqual((newer, isinstance(newer, Made)), (f"{spec().name}:2", True))


class WhenTheHarnessSaysNo(unittest.TestCase):
    def test_a_definition_that_the_lock_does_not_say_is_refused_with_its_word_and_the_agent_that_is_right_is_made(self):
        world = World(foundry_model_investigator="another-model").go()
        self.assertEqual(world.outcomes(), [(agents.INVESTIGATOR_NAME, "refused", "lock-differs"), (agents.SKEPTIC_NAME, "made", None), (agents.SCHOLAR_NAME, "refused", "lock-differs")])
        self.assertEqual(sorted(world.rig.service.agents), [agents.SKEPTIC_NAME], "nothing was made from a definition that is not the lock's")
        end = world.end
        self.assertEqual((end["ok"], end["made"], end["refused"], end["failed"]), (False, 1, 2, 0))
        self.assertEqual([line["version"] for line in world.lines], [None, 1, None])
        self.assertEqual([(line["agent"], line["outcome"], line["reason"]) for line in world.harness_lines()], [(agents.INVESTIGATOR_NAME, "refused", "lock-differs"), (agents.SCHOLAR_NAME, "refused", "lock-differs")],
                         "the lines of the runs that the harness refused are written, as in a Watch")

    def test_the_code_of_a_tool_that_differs_from_the_lock_is_refused_the_same_way(self):
        world = World()
        implementations, module = harness_module.code_digests()
        world.harness.digests = lambda: ({**implementations, library.NAME: "0" * 64}, module)
        world.go()
        self.assertEqual([(outcome, reason) for _, outcome, reason in world.outcomes()], [("made", None), ("made", None), ("refused", "lock-differs")])

    def test_a_lock_that_cannot_be_used_refuses_all_three_with_the_word_lock_and_the_service_is_not_called(self):
        world = World(lock=None, lock_error="the file is not there").go()
        self.assertEqual(world.outcomes(), [(name, "refused", "lock") for name in NAMES])
        self.assertEqual([line["definition"] for line in world.lines], ["", "", ""], "there is no lock to take a digest from")
        self.assertEqual(world.rig.service.calls, [])
        self.assertNotIn("the file is not there", "\n".join(world.log), "the words of the error are not in a line of this job")

    def test_a_pulled_switch_refuses_all_three_before_any_call_and_either_of_the_two_switches_does(self):
        for switch in ("investigation", "all"):
            with self.subTest(switch=switch):
                world = World()
                world.store.switch_put(SwitchRecord(name=switch, paused=True, by="a person", at=stamp(fixed_clock())))
                world.go()
                self.assertEqual(world.outcomes(), [(name, "refused", "switch") for name in NAMES])
                self.assertEqual(world.rig.service.calls, [])
                self.assertEqual((world.end["ok"], world.end["refused"]), (False, 3))

    def test_a_switch_that_cannot_be_read_counts_as_pulled(self):
        class Broken:
            def switch_get(self, name):
                raise RuntimeError("the store does not answer")

        world = World(store=Broken()).go()
        self.assertEqual(world.outcomes(), [(name, "refused", "switch") for name in NAMES])

    def test_no_store_refuses_with_its_word(self):
        world = World(store=None).go()
        self.assertEqual(world.outcomes(), [(name, "refused", "no-store") for name in NAMES])
        self.assertEqual(world.rig.service.calls, [])

    def test_a_stored_definition_that_differs_is_refused_it_pulls_the_brake_once_and_the_switch_then_holds_the_other_two(self):
        world = World()
        original = Service.version

        def changed_in_the_portal(name, body, number):
            stored = original(name, body, number)
            return {**stored, "definition": {**stored["definition"], "instructions": "somebody changed this"}}

        world.rig.service.version = changed_in_the_portal
        world.go()
        self.assertEqual(world.outcomes(), [(agents.INVESTIGATOR_NAME, "refused", "definition"), (agents.SKEPTIC_NAME, "refused", "switch"), (agents.SCHOLAR_NAME, "refused", "switch")])
        self.assertEqual(world.alerts, ["definition"], "one letter, as in a real run")
        self.assertEqual([record.name for record in world.store.switches() if record.paused], ["investigation"])
        self.assertEqual(world.end["refused"], 3)

    def test_a_failure_of_the_service_is_failed_with_its_status_and_none_of_its_words(self):
        world = World()
        world.rig.service.failures["GET agent"] = (403, {"error": {"code": "Forbidden", "message": HOSTILE}})
        world.go()
        self.assertEqual(world.outcomes(), [(name, "failed", "service") for name in NAMES])
        self.assertEqual([line["status"] for line in world.lines], [403, 403, 403])
        self.assertEqual((world.end["ok"], world.end["failed"]), (False, 3))
        for secret in (GUID, "rg-secret", "thing-secret", "abcdef1234567890", "Forbidden"):
            self.assertNotIn(secret, "\n".join(world.log), secret)
        self.assertEqual([line["reason"] for line in world.harness_lines()], ["service"] * 3)

    def test_a_service_that_gives_no_status_is_failed_with_no_status_in_the_line(self):
        world = World()
        world.rig.foundry.ensure_agent = lambda spec: (_ for _ in ()).throw(FoundryError("it did not answer"))
        world.go()
        self.assertEqual(world.outcomes(), [(name, "failed", "service") for name in NAMES])
        self.assertFalse(any("status" in line for line in world.lines))

    def test_no_foundry_project_is_said_in_the_end_line_and_nothing_else_is_written(self):
        with LogCapture() as capture:
            done = ready.execute(History("r" * 32, "a" * 32, fixed_clock, Redactor()), settings_of(), None, Ticker())
        (end,) = capture.events()
        self.assertEqual((end["type"], end["ok"], end["why"], end["made"], end["existing"], end["refused"], end["failed"]), ("agents.ready.finished", False, "no-endpoint", 0, 0, 0, 0))
        self.assertEqual(sum(done.values()), 0)

    def test_a_job_that_breaks_inside_still_writes_its_end_line_with_the_word_error_and_raises_nothing(self):
        world = World()
        world.harness.ensure = lambda spec: (_ for _ in ()).throw(RuntimeError(HOSTILE))
        world.go()
        self.assertEqual(world.lines, [])
        self.assertEqual((world.end["ok"], world.end["why"]), (False, "error"))
        self.assertNotIn("rg-secret", "\n".join(world.log), "the type of the error is logged and the text of it is not")


class TheLinesHoldTypedValuesOnly(unittest.TestCase):
    """A name or an id of the estate cannot get into a line of this job: every field is a number, a flag, a name of one of the three agents, 12 hex digits or a word of a closed list."""

    def check(self, event):
        keys = LINE_KEYS if event["type"] == "agents.ready" else END_KEYS
        self.assertLessEqual(set(event), keys, event)
        if event["type"] == "agents.ready":
            self.assertIn(event["agent"], NAMES)
            self.assertIsInstance(event["version"], (int, type(None)))
            self.assertRegex(event["definition"], r"^(?:[0-9a-f]{12})?$")
            self.assertIn(event["outcome"], ready.OUTCOMES)
            self.assertIn(event.get("reason", ""), ("",) + ready.REASONS)
            self.assertIn(event.get("status", 200), range(100, 600))
        else:
            self.assertIn(event["why"], ("",) + ready.WHY)
            for key in ("made", "existing", "refused", "failed", "seconds"):
                self.assertIsInstance(event[key], int, key)
            self.assertIsInstance(event["ok"], bool)

    def test_every_field_of_every_line_is_typed_whatever_the_service_and_the_estate_say(self):
        def a_guid_for_a_version(name, body, number):
            return {**Service.version(name, body, number), "version": GUID}

        worlds = []
        for what in ("made", "guid", "failed", "refused", "no store", "no lock", "no project"):
            world = World(store=None) if what == "no store" else World(lock=None) if what == "no lock" else World(foundry_model_investigator="another-model") if what == "refused" else World()
            if what == "guid":
                world.rig.service.version = a_guid_for_a_version
            if what == "failed":
                world.rig.service.failures["GET agent"] = (500, {"error": {"code": "x", "message": HOSTILE}})
            worlds.append(world.go())
        for world in worlds:
            for event in world.events:
                self.check(event)
        self.assertEqual([line["version"] for line in worlds[1].lines], [None, None, None], "a version that is not a number is left out")
        ours = "\n".join(message for world in worlds for message in world.log if message.startswith(("meternaut_event ", "harness.run ")))
        for secret in (GUID, "rg-secret", "thing-secret", "abcdef1234567890"):
            self.assertNotIn(secret, ours, secret)

    def test_a_reason_that_is_not_on_the_list_is_the_word_other_and_a_name_cannot_pass_as_one(self):
        world = World()

        def refuse(spec):
            error = HarnessRefused("the harness refused the run: it is words")
            error.reason = f"/subscriptions/{GUID}/resourceGroups/rg-secret"
            raise error

        world.harness.ensure = refuse
        world.go()
        self.assertEqual({line["reason"] for line in world.lines}, {"other"})
        self.assertNotIn(GUID, "\n".join(world.log))

    def test_a_status_that_is_no_http_status_is_left_out_and_so_is_a_flag(self):
        for status in (True, 0, 99, 600, "403", None):
            with self.subTest(status=status):
                world = World()

                def failing(spec, status=status):
                    error = FoundryError("no")
                    error.status = status
                    raise error

                world.harness.ensure = failing
                world.go()
                self.assertFalse(any("status" in line for line in world.lines))


class TheThreeAgentsAreTheOnesOfTheRuns(unittest.TestCase):
    def test_the_specs_are_the_locked_definitions_of_the_investigator_the_skeptic_and_the_scholar_in_that_order(self):
        made = ready.specs(settings_of())
        self.assertEqual([one.name for one in made], list(NAMES))
        for one in made:
            self.assertEqual(lockfile.compare(LOCK.entry(one.name), lockfile.facts_of(foundry_module.definition_of(one), LOCK.ignored)), [], one.name)
        self.assertEqual(made[0].tools, toolbox.SPECS)
        self.assertEqual(made[2].tools, (library.FETCH_DOC,))

    def test_the_investigation_and_the_study_build_the_same_specs_the_same_way_and_if_one_of_them_changes_this_job_does_too(self):
        from support import APP_ROOT
        investigate = (APP_ROOT / "cases" / "investigate.py").read_text(encoding="utf-8")
        study = (APP_ROOT / "cases" / "study.py").read_text(encoding="utf-8")
        self.assertIn("spec_i, spec_s = agents.investigator(st, toolbox.specs), agents.skeptic(st)", investigate)
        self.assertIn("spec = agents.scholar(st, (library.FETCH_DOC,))", study)


class TheEntryPoint(unittest.TestCase):
    ENV = {**ENV, "FOUNDRY_PROJECT_ENDPOINT": ENDPOINT, "FOUNDRY_MODEL_INVESTIGATOR": locked(agents.INVESTIGATOR_NAME), "FOUNDRY_MODEL_SKEPTIC": locked(agents.SKEPTIC_NAME)}

    def go(self, env=None, service=None, extras="store", **more):
        service = service or Service()
        store = MemoryStore(clock=fixed_clock)
        given = SimpleNamespace(store=store, on_alert=None) if extras == "store" else extras
        with LogCapture() as capture:
            done = ready.run_ready("control", "b" * 32, self.ENV if env is None else env, transport=service, sleep=lambda s: None, clock=fixed_clock, monotonic=Ticker(), fetch=identity_fetch,
                                   new_id=lambda: "r" * 32, extras=given, **more)
        return done, capture.events(), capture.messages(), service

    def test_the_whole_job_makes_the_three_agents_then_finds_them_and_calls_only_the_agent_routes_of_the_project(self):
        service = Service()
        done, lines, _, _ = self.go(service=service)
        self.assertEqual(([e["outcome"] for e in lines if e["type"] == "agents.ready"], dict(done)), (["made"] * 3, {"made": 3}))
        self.assertEqual({e["requestId"] for e in lines}, {"b" * 32}, "the lines carry the request of the message")
        done, lines, _, _ = self.go(service=service)
        self.assertEqual([e["outcome"] for e in lines if e["type"] == "agents.ready"], ["existing"] * 3)
        self.assertTrue(set(service.routes()) <= AGENT_ROUTES, service.routes())
        self.assertEqual({call["host"] for call in service.calls}, {HOST})

    def test_a_project_that_is_not_set_is_said_and_nothing_is_called(self):
        service = Service()
        done, lines, _, _ = self.go(env=ENV_NO_PROJECT, service=service)
        self.assertEqual([(e["type"], e["why"], e["ok"]) for e in lines], [("agents.ready.finished", "no-endpoint", False)])
        self.assertEqual(service.calls, [])

    def test_the_client_that_the_job_builds_may_read_an_agent_and_make_one_and_it_may_not_run_one_or_reach_another_host(self):
        built = []

        class Recording(Client):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                built.append(self)

        with mock.patch.object(ready, "Client", Recording):
            self.go()
        (client,) = built
        for method, path in (("GET", f"/agents/{agents.INVESTIGATOR_NAME}"), ("POST", "/agents"), ("POST", f"/agents/{agents.SKEPTIC_NAME}/versions")):
            client.check(method, ENDPOINT + path)
        for method, address in (("POST", ENDPOINT + "/openai/v1/responses"), ("POST", ENDPOINT + "/openai/v1/conversations"), ("DELETE", ENDPOINT + "/openai/v1/conversations/conv_abc"),
                                ("GET", "https://management.azure.com/subscriptions"), ("POST", "https://x.ai.gateway.azure.com/default/models/openai/v1/chat/completions"),
                                ("GET", ENDPOINT + "/connections")):
            with self.subTest(address=address), self.assertRaises(http.Refused):
                client.check(method, address)
        self.assertIsNotNone(client.deadline, "the calls of the job have a deadline of their own")

    def test_settings_that_are_not_valid_are_a_failure_of_the_setup_that_raises_nothing_and_says_no_name_of_the_estate_in_its_line(self):
        for env in ({}, {**self.ENV, "SCOPE_SUBSCRIPTIONS": "not-a-subscription"}):
            done, lines, messages, service = self.go(env=env)
            self.assertEqual([(e["type"], e["why"], e["ok"]) for e in lines], [("agents.ready.finished", "setup", False)])
            self.assertEqual(service.calls, [])
            self.assertTrue(any(message.startswith("the agents could not be made ready: ") for message in messages))

    def test_without_the_loop_there_is_no_store_and_the_three_are_refused_with_that_word(self):
        service = Service()
        done, lines, _, _ = self.go(service=service, extras=None)
        self.assertEqual([(e["outcome"], e["reason"]) for e in lines if e["type"] == "agents.ready"], [("refused", "no-store")] * 3)
        self.assertEqual(service.calls, [])


if __name__ == "__main__":
    unittest.main()
