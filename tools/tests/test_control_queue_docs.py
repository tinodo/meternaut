"""The documents of the change that moved the control message from an Event Hubs namespace to a Storage queue (2026-11-08): what they say about the cost, the queue, the trade-off of the Operator's role,
the order of the real run and what is not known, and that they say that it is built and has not run in Azure.

The code of the change has tests of its own (test_retire_old.py, test_cases_check.py, test_check_helpers.py, test_environment_template.py and the app's test_control.py). Here the documents are held to the
code: the names, the numbers and the order of the actions are the ones that the code has."""
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELPERS = load("check_helpers_of_the_control_queue_docs", "check-helpers.py")
CASES_CHECK_SOURCE = (ROOT / "tools" / "cases-check.py").read_text(encoding="utf-8")
RETIRE = load("retire_old_of_the_control_queue_docs", "retire-old.py")


def text(path):
    return (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")


HEADING = "## Changed on 2026-11-08: the control message goes through a Storage queue (built, not deployed)"
BOOTSTRAP = text("environment/BOOTSTRAP.md")
SECTION = BOOTSTRAP.split(HEADING + "\n")[1].split("\n## ")[0]
README = text("README.md")
CASES = text("docs/proposals/02-first-cases.md")
PRIVATE = text("docs/proposals/07-private-by-default.md")
WORKFLOW = text(".github/workflows/deploy-hub.yml")
ANCHOR = "#changed-on-2026-11-08-the-control-message-goes-through-a-storage-queue-built-not-deployed"


class TheRecordSaysWhatChangedAndWhy(unittest.TestCase):
    def test_the_section_is_one_and_comes_before_the_page_that_says_what_to_do_after_it(self):
        self.assertEqual(BOOTSTRAP.count(HEADING), 1)
        self.assertLess(BOOTSTRAP.index(HEADING), BOOTSTRAP.index("\n## After it"))

    def test_it_gives_the_two_meters_and_what_they_add_up_to_and_where_the_prices_were_read(self):
        for words in ("| Event Hubs Standard, one throughput unit (Sweden Central) | 0.03 an hour | 21.9 |", "| The namespace's private endpoint | 0.01 an hour | 7.3 |", "| **Together** | | **29.2** |",
                      "https://prices.azure.com/api/retail/prices", "\"Standard Throughput Unit\"", "\"Standard Private Endpoint\""):
            self.assertIn(words, SECTION)
        self.assertEqual(round(0.03 * 730, 1), 21.9)
        self.assertEqual(round(0.01 * 730, 1), 7.3)
        self.assertEqual(round(21.9 + 7.3, 1), 29.2)
        self.assertIn("The amount was not read from the price list.", SECTION, "the price of the queue is not given as a fact that it is not")

    def test_it_says_that_it_is_built_and_has_not_run_and_never_that_it_is_deployed_or_proven(self):
        self.assertIn("Nothing of this ran in Azure when it was written.", SECTION)
        self.assertNotRegex(SECTION, r"(?i)deployed and proven|was proven|has been proven|passed on the real estate")
        for name, page in (("README", README), ("proposal 02", CASES), ("proposal 07", PRIVATE)):
            self.assertIn("not deployed", page, name)
        self.assertIn("built, not deployed", README)
        self.assertIn("built, not deployed", PRIVATE)

    def test_it_says_the_properties_of_the_queue_that_the_owner_asked_for(self):
        for words in ("up to one minute by default", "Delivery is at least once", "after five tries in all (the first included)", "`cases-control-poison`", "No key is involved at any point.",
                      "the base64 of the JSON, because the host decodes base64"):
            self.assertIn(words, SECTION)

    def test_it_says_the_trade_off_of_the_operators_role_in_the_one_sentence_that_it_needs(self):
        self.assertIn("That is wider than a sender needs: it can also read, delete and clear messages. The narrower *Storage Queue Data Message Sender* is not among the roles in the condition of the "
                      "deploy identity's role-assignment right, and adding it would be one more hand step for the owner. The queue holds only job names and request ids.", SECTION)

    def test_it_says_what_does_not_change_and_what_is_not_known(self):
        self.assertIn("**Nothing else changed.**", SECTION)
        for words in ("whether the scale controller of Flex Consumption wakes the app from zero for a queue message through the identity-based host connection is not known",
                      "whether the Operator's token for `https://storage.azure.com/` is accepted over the private endpoint for queues is not known either"):
            self.assertIn(words.lower(), SECTION.lower())
        self.assertNotRegex(SECTION, r"(?i)console", "the web page is the web page in new text")


class TheOrderOfTheRealRun(unittest.TestCase):
    ORDER = ("1. Merge. Nothing changes in Azure by the merge.", "2. The Hub action `cases`:", "3. The Hub action `operator`:", "4. The Hub action `cases-run`:", "5. Only then the Hub action `retire-event-hubs`.")

    def test_merge_then_cases_then_operator_then_cases_run_and_only_then_the_retirement(self):
        positions = [SECTION.index(step) for step in self.ORDER]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("A new role takes up to ten minutes to apply, so wait about ten minutes.", SECTION)
        self.assertIn("It may run only after `cases-run` has passed", SECTION)
        self.assertIn("it refuses to delete anything while the queue `cases-control` is not there", SECTION)

    def test_what_if_and_the_prechecks_work_before_and_after_the_namespace_is_gone(self):
        self.assertIn("`what-if` and the checks of each action before its deploy read no namespace, so they pass before the namespace is gone and after it, and on an estate that never had one.", SECTION)
        self.assertNotIn("evhns", WORKFLOW, "no step of the workflow names the namespace: the retirement builds its names in tools/retire-old.py")
        self.assertNotIn("EVENT_HUB_NAMESPACE", WORKFLOW)
        self.assertNotIn("event_hub_namespace", WORKFLOW)

    def test_the_other_pages_point_to_the_record_and_keep_to_the_same_order(self):
        for name, page in (("README", README), ("proposal 07", PRIVATE)):
            self.assertIn(ANCHOR, page, name)
        self.assertIn("after a run of `cases-run` has proved the queue", README)
        self.assertIn("once `cases-control` has been proved by a run of `cases-run`", PRIVATE)
        after = BOOTSTRAP.split("\n## After it")[1].split("\n## ")[0]
        self.assertIn("one more action, `retire-event-hubs`, comes only after `cases-run` has passed through the queue", after)

    def test_the_description_of_the_action_in_the_workflow_says_the_same(self):
        description = re.search(r'(?m)^        description: "(.*)"$', WORKFLOW).group(1)
        self.assertIn("retire-event-hubs: delete the Event Hubs namespace that carried the control event", description)
        self.assertIn("run it only after the action cases-run has proved the queue path", description)
        self.assertIn("it refuses to delete anything while the control queue cases-control is not there", description)


class TheDocumentsAreHeldToTheCode(unittest.TestCase):
    def test_the_names_and_the_numbers_are_the_ones_that_the_sender_and_the_host_have(self):
        self.assertEqual(HELPERS.QUEUE_SERVICE_VERSION, "2026-04-06")
        self.assertIn(f"`x-ms-version` ({HELPERS.QUEUE_SERVICE_VERSION})", SECTION)
        self.assertEqual(HELPERS.STORAGE_RESOURCE, "https://storage.azure.com/")
        self.assertIn(f"`{HELPERS.STORAGE_RESOURCE}`", SECTION)
        self.assertEqual(HELPERS.MESSAGE_TTL_SECONDS, 3600)
        self.assertIn("a time to live of one hour", SECTION)
        self.assertIn('CONTROL_QUEUE = "cases-control"', CASES_CHECK_SOURCE)
        self.assertIn("https://<storage account>.queue.core.windows.net/cases-control/messages", SECTION)
        host = json.loads(text("src/case-functions/host.json"))["extensions"]["queues"]
        self.assertEqual((host["batchSize"], host["newBatchThreshold"], host["maxDequeueCount"]), (1, 0, 5), "one message at a time, and five tries in all")

    def test_the_retirement_deletes_what_the_section_lists_by_the_names_that_it_gives(self):
        listed = RETIRE.event_hub_items("11111111-2222-3333-4444-555555555555", "rg-example")
        token = RETIRE.digest("11111111-2222-3333-4444-555555555555", "rg-example")
        self.assertEqual([item.name for item in listed], [f"pe-evhns-meternaut-{token}", f"evhns-meternaut-{token}", "azure-webjobs-eventhub"])
        for words in ("`pe-evhns-meternaut-<digest>`", "`evhns-meternaut-<digest>`", "`azure-webjobs-eventhub`", "`casesControl`"):
            self.assertIn(words, SECTION)
        self.assertEqual(RETIRE.CONTROL_QUEUE, "cases-control")

    def test_the_operators_role_is_the_one_that_the_documents_name_and_it_is_on_the_one_queue(self):
        template = text("environment/operator/main.bicep")
        self.assertIn("974c5e8b-45b9-4653-ba55-5f855dd0fb88", template, "Storage Queue Data Contributor")
        self.assertNotIn("c6a89b2d-59bc-44d0-9896-0f6e12d7b80a", template, "Storage Queue Data Message Sender is not assigned: the deploy identity may not assign it")
        self.assertRegex(template, r"scope: casesControlQueue")
        self.assertIn("*Role Based Access Control Administrator*", BOOTSTRAP)
        row = [line for line in BOOTSTRAP.splitlines() if line.startswith("| The same group | *Role Based Access Control Administrator*")][0]
        for words in ("*Storage Queue Data Contributor*", "since 2026-11-08, what the Operator's identity needs on the one control queue", "no template gives it since 2026-11-08"):
            self.assertIn(words, row)
        self.assertIn("Give a service principal one of nine roles", row, "the condition has not changed: the queue's role was in it already")


if __name__ == "__main__":
    unittest.main()
