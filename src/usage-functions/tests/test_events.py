import logging
import unittest
import uuid
from unittest import mock

from support import ENV, FakeContainer, FakeEvent, ServiceError, json_event, sequential_ids

from usage import clients, config, events

try:
    import azure.functions as func
except ImportError:
    func = None

DOC_1 = "00000000-0000-0000-0000-000000000001"
CANARY = "CANARY-Jane-Doe-jane@example.com"
GATEWAY_EVENT = {
    "id": "ai-5a1e3f0c", "timestamp": "11/04/2026 12:00:00", "productName": "contract-1", "model": "gpt-4o",
    "promptTokens": 17, "responseTokens": 5, "totalTokens": 22, "note": "Zürich",
}


class IngestBatchTests(unittest.TestCase):
    def ingest(self, batch, container=None, stream="ai", level="INFO"):
        container = FakeContainer("events") if container is None else container
        with self.assertLogs(level=level) as logs:
            summary = events.ingest_batch(stream, batch, container, sequential_ids())
        return summary, container, logs

    def messages(self, logs, level):
        return [record.getMessage() for record in logs.records if record.levelno == level]

    def test_a_json_object_with_an_id_is_stored_as_it_is(self):
        summary, container, _ = self.ingest([json_event(GATEWAY_EVENT, 1)])
        self.assertEqual(container.upserts, [GATEWAY_EVENT])
        self.assertEqual((summary.received, summary.written, summary.skipped, summary.ids_added, summary.failed), (1, 1, 0, 0, 0))

    def test_the_indented_utf8_json_of_the_gateway_is_stored_as_it_is(self):
        _, container, _ = self.ingest([json_event(GATEWAY_EVENT, 1, indent=2, ensure_ascii=False)])
        self.assertEqual(container.upserts, [GATEWAY_EVENT])

    def test_a_body_without_an_id_gets_an_id_and_a_warning(self):
        body = {key: value for key, value in GATEWAY_EVENT.items() if key != "id"}
        summary, container, logs = self.ingest([json_event(body, 7)])
        self.assertEqual(container.upserts, [{"id": DOC_1, **body}])
        self.assertEqual(summary.ids_added, 1)
        self.assertEqual(self.messages(logs, logging.WARNING), ["ai usage event has no id, an id was added (sequence_number=7)"])

    def test_an_id_that_is_empty_or_not_a_string_counts_as_missing(self):
        for bad_id in ("", None, 5, ["a"]):
            with self.subTest(id=bad_id):
                _, container, _ = self.ingest([json_event({"id": bad_id, "productName": "p"}, 1)])
                self.assertEqual(container.upserts, [{"id": DOC_1, "productName": "p"}])

    def test_a_body_that_is_not_json_is_logged_with_its_sequence_number_and_skipped(self):
        for body in (b"not json", b"", b"{", b"\xff\xfe\xfa", b'{"a": 1} trailing'):
            with self.subTest(body=body):
                summary, container, logs = self.ingest([FakeEvent(body, 3)])
                self.assertEqual(container.upserts, [])
                self.assertEqual((summary.skipped, summary.written), (1, 0))
                self.assertEqual(self.messages(logs, logging.ERROR), ["ai usage event skipped: not_json (sequence_number=3)"])

    def test_a_json_body_that_is_not_an_object_is_logged_with_its_sequence_number_and_skipped(self):
        for body in (b"[1, 2]", b'"text"', b"42", b"null", b"true"):
            with self.subTest(body=body):
                summary, container, logs = self.ingest([FakeEvent(body, 4)])
                self.assertEqual(container.upserts, [])
                self.assertEqual(summary.skipped, 1)
                self.assertEqual(self.messages(logs, logging.ERROR), ["ai usage event skipped: not_an_object (sequence_number=4)"])

    def test_the_batch_goes_on_after_a_bad_event_and_the_summary_counts_it_all(self):
        batch = [json_event(GATEWAY_EVENT, 1), FakeEvent("x", 2), json_event({"productName": "p"}, 3), FakeEvent("[]", 4)]
        summary, container, logs = self.ingest(batch, stream="pii")
        self.assertEqual([document["id"] for document in container.upserts], ["ai-5a1e3f0c", DOC_1])
        self.assertEqual(
            self.messages(logs, logging.INFO),
            ['usage_events_result {"stream":"pii","received":4,"written":2,"skipped":2,"idsAdded":1,"failed":0}'],
        )
        self.assertEqual(summary.received, 4)

    def test_an_empty_batch_writes_only_its_summary(self):
        summary, container, logs = self.ingest([])
        self.assertEqual(container.upserts, [])
        self.assertEqual(self.messages(logs, logging.INFO), ['usage_events_result {"stream":"ai","received":0,"written":0,"skipped":0,"idsAdded":0,"failed":0}'])

    def test_a_write_error_is_raised_after_the_whole_batch_was_tried(self):
        container = FakeContainer("events")
        container.fail_on_attempt = 2
        batch = [json_event({"id": f"e{n}", "productName": "p"}, n) for n in (1, 2, 3)]
        with self.assertLogs(level="INFO") as logs, self.assertRaises(events.IngestionError) as caught:
            events.ingest_batch("ai", batch, container, sequential_ids())
        self.assertEqual([document["id"] for document in container.upserts], ["e1", "e3"])
        self.assertIsInstance(caught.exception.__cause__, ServiceError)
        self.assertEqual(str(caught.exception), "1 of 3 ai usage events were not written")
        self.assertEqual(self.messages(logs, logging.ERROR), ["ai usage event not written: ServiceError, status 503 (sequence_number=2)"])
        self.assertIn('"written":2,"skipped":0,"idsAdded":0,"failed":1', self.messages(logs, logging.INFO)[0])

    def test_the_sequence_number_may_be_missing_or_unreadable(self):
        class BrokenEvent:
            @property
            def sequence_number(self):
                raise RuntimeError("no metadata")

            def get_body(self):
                return b"x"

        _, _, logs = self.ingest([FakeEvent(b"x"), BrokenEvent()])
        self.assertEqual(
            self.messages(logs, logging.ERROR),
            ["ai usage event skipped: not_json (sequence_number=None)"] * 2,
        )

    def test_the_logs_hold_no_part_of_a_body(self):
        container = FakeContainer("events")
        container.fail_on_attempt = 3
        batch = [
            json_event({"id": "a", "name": CANARY}, 1),
            json_event({"name": CANARY}, 2),
            FakeEvent('{"name": "' + CANARY, 3),
            FakeEvent('["' + CANARY + '"]', 4),
            json_event({"id": "d", "name": CANARY}, 5),
        ]
        with self.assertLogs(level="DEBUG") as logs, self.assertRaises(events.IngestionError) as caught:
            events.ingest_batch("pii", batch, container, sequential_ids())
        texts = [record.getMessage() for record in logs.records] + [str(record.args) for record in logs.records]
        texts += [str(caught.exception), str(caught.exception.__cause__)]
        self.assertTrue(texts)
        for text in texts:
            self.assertNotIn(CANARY, text)
            self.assertNotIn("Jane", text)
        self.assertTrue(all(record.exc_info is None for record in logs.records))


class ProductionEntryTests(unittest.TestCase):
    def run_with_fake_cosmos(self, env=ENV):
        containers: dict[str, FakeContainer] = {}
        expected_client_id = (env.get("AZURE_CLIENT_ID") or "").strip()

        def cosmos_container(client_id, endpoint, database, container):
            self.assertEqual((client_id, endpoint, database), (expected_client_id, ENV["COSMOS_ENDPOINT"], "usage-db"))
            return containers.setdefault(container, FakeContainer(container))

        patches = (
            mock.patch.dict("os.environ", env, clear=True),
            mock.patch.object(clients, "cosmos_container", side_effect=cosmos_container),
        )
        return containers, patches

    def test_ai_events_go_to_the_ai_container_and_pii_events_to_the_pii_container(self):
        containers, (environment, cosmos) = self.run_with_fake_cosmos()
        pii_event = {"id": "p-1", "type": "PII_Processing"}
        with environment, cosmos, self.assertLogs(level="INFO"):
            events.ingest_ai([json_event(GATEWAY_EVENT, 1)])
            events.ingest_pii([json_event(pii_event, 1)])
        self.assertEqual(sorted(containers), ["ai-container", "pii-container"])
        self.assertEqual(containers["ai-container"].upserts, [GATEWAY_EVENT])
        self.assertEqual(containers["pii-container"].upserts, [pii_event])

    def test_an_added_id_is_a_random_uuid(self):
        containers, (environment, cosmos) = self.run_with_fake_cosmos()
        with environment, cosmos, self.assertLogs(level="INFO"):
            events.ingest_ai([json_event({"productName": "p"}, 1)])
        added = containers["ai-container"].upserts[0]["id"]
        self.assertEqual(uuid.UUID(added).version, 4)
        self.assertEqual(added, str(uuid.UUID(added)))

    def test_a_missing_app_setting_is_named(self):
        for ingest, container_setting in ((events.ingest_ai, "COSMOS_CONTAINER_AI_USAGE"), (events.ingest_pii, "COSMOS_CONTAINER_PII_USAGE")):
            for name in ("COSMOS_ENDPOINT", "COSMOS_DATABASE", container_setting):
                with self.subTest(setting=name):
                    env = {key: value for key, value in ENV.items() if key != name}
                    with mock.patch.dict("os.environ", env, clear=True), self.assertRaises(config.ConfigError) as caught:
                        ingest([])
                    self.assertEqual(str(caught.exception), f"Missing required app setting(s): {name}")

    def test_the_client_id_is_not_required_and_without_it_the_app_runs_as_its_system_assigned_identity(self):
        without = {key: value for key, value in ENV.items() if key != "AZURE_CLIENT_ID"}
        for env in (without, {**without, "AZURE_CLIENT_ID": ""}, {**without, "AZURE_CLIENT_ID": "   "}):
            with self.subTest(client_id=env.get("AZURE_CLIENT_ID")):
                containers, (environment, cosmos) = self.run_with_fake_cosmos(env)
                with environment, cosmos, self.assertLogs(level="INFO"):
                    events.ingest_ai([json_event(GATEWAY_EVENT, 1)])
                    events.ingest_pii([json_event({"id": "p-1"}, 1)])
                self.assertEqual(sorted(containers), ["ai-container", "pii-container"])
                self.assertEqual(containers["ai-container"].upserts, [GATEWAY_EVENT])

    def test_the_settings_of_the_exports_are_not_needed(self):
        env = {key: value for key, value in ENV.items() if key not in ("GATEWAY_APPINSIGHTS_ID", "COSMOS_CONTAINER_CONFIG", "COSMOS_CONTAINER_LLM_USAGE")}
        containers, (_, cosmos) = self.run_with_fake_cosmos()
        with mock.patch.dict("os.environ", env, clear=True), cosmos, self.assertLogs(level="INFO"):
            events.ingest_ai([json_event(GATEWAY_EVENT, 1)])
        self.assertEqual(list(containers), ["ai-container"])


@unittest.skipIf(func is None, "azure-functions is not installed here; the CI runner installs it")
class AzureFunctionsEventTests(unittest.TestCase):
    def test_an_azure_functions_event_hub_event_works_as_an_event(self):
        container = FakeContainer("events")
        batch = [
            func.EventHubEvent(body=b'{"id": "a", "productName": "p"}', sequence_number=11),
            func.EventHubEvent(body=b"not json", sequence_number=12),
        ]
        with self.assertLogs(level="INFO") as logs:
            summary = events.ingest_batch("ai", batch, container, sequential_ids())
        self.assertEqual(container.upserts, [{"id": "a", "productName": "p"}])
        self.assertEqual((summary.written, summary.skipped), (1, 1))
        self.assertIn("ai usage event skipped: not_json (sequence_number=12)", [record.getMessage() for record in logs.records])


if __name__ == "__main__":
    unittest.main()
