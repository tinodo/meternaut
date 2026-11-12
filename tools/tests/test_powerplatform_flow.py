"""The rules of the flow `Meternaut cards` (powerplatform/solution/src/Workflows; docs/proposals/19-teams-cards-through-power-automate.md): what it reads, when it deletes a message, what it does when the post fails.

The flow has never run, and nothing here can say that it works in Power Automate: these tests read its JSON. They hold it to what was read of the two connectors' own definitions on 2026-11-11 (the Swagger of
shared_azurequeues and shared_teams, read from a Power Platform environment with the owner's sign-in, read only), to the rules of the design (a message is deleted only after a successful post or update, or when it can
never be handled; every other failure leaves it in the queue; a posted card is never posted twice), and to the structure of a flow definition (every action that is named exists, the runs follow one another without a
cycle, an expression is balanced). The body of the Teams action has a schema that the service makes when the designer asks for it, so its parameter names are what the connector's own description for a model says
('recipient' and 'messageBody'; the step that updates a card takes the message in 'messageId', which is inferred from it and not read): the first run in an environment, and `tools/powerplatform.py test-close`, prove them."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLOW_PATH = ROOT / "powerplatform" / "solution" / "src" / "Workflows" / "MeternautCards-E6272F40-4E93-4EF9-B20B-2FCD222057AF.json"
FLOW = json.loads(FLOW_PATH.read_text(encoding="utf-8"))
PROPERTIES = FLOW["properties"]
DEFINITION = PROPERTIES["definition"]
TRIGGER_NAME, TRIGGER = next(iter(DEFINITION["triggers"].items()))
ACTIONS = DEFINITION["actions"]

# Read from the live definitions on 2026-11-11 (operation id -> what the connector says about it); PutMessage_V2 is the operation that tools/powerplatform.py's test flow used live that day.
AZURE_QUEUES = {
    "OnMessages_V2": {"trigger": "batch", "parameters": {"storageAccountName", "queueName", "visibilitytimeout"}},
    "DeleteMessage_V2": {"parameters": {"storageAccountName", "queueName", "messageId", "popreceipt"}},
    "PutMessage_V2": {"parameters": {"storageAccountName", "queueName", "message"}},
}
# The message that the trigger returns for each queue message (the definition "Messages"): there is no dequeue count in it.
QUEUE_MESSAGE_FIELDS = {"MessageId", "InsertionTime", "ExpirationTime", "PopReceipt", "TimeNextVisible", "MessageText"}
# UpdateCardInConversation (Learn, "Microsoft Teams", read on 2026-11-12): poster, location, parentMessageId and a dynamic body. The names inside the body are not documented.
TEAMS = {"PostCardToConversation": {"parameters": {"poster", "location", "body/recipient", "body/messageBody"}},
         "UpdateCardInConversation": {"parameters": {"poster", "location", "body/recipient", "body/messageId", "body/messageBody"}}}
POSTER_STEP, UPDATE_STEP, CONDITION = "Post_card_in_a_chat_or_channel", "Update_an_adaptive_card_in_a_chat_or_channel", "Condition_The_message_replaces_a_card"
PUT_STEP, COMPOSE_STEP = "Put_a_message_on_a_queue_(V2)", "Compose_what_was_posted"
POSTERS = {"Power Apps", "Power Virtual Agents", "Flow bot", "User"}


def all_actions(actions=None):
    """Every action, the ones inside a condition too, by name."""
    found = {}
    for name, action in (ACTIONS if actions is None else actions).items():
        found[name] = action
        for branch in ("actions",):
            found.update(all_actions(action.get(branch, {})))
        found.update(all_actions(action.get("else", {}).get("actions", {})))
    return found


EVERY = all_actions()


def strings(node):
    """Every string of a JSON value."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from strings(value)


def expressions(node):
    return [s for s in strings(node) if "@" in s]


def without_literals(expression):
    """An expression without its string literals (a quote inside a literal is doubled)."""
    return re.sub(r"'(?:[^']|'')*'", "''", expression)


class TheServiceLimits(unittest.TestCase):
    def test_no_description_is_longer_than_the_256_characters_that_the_flow_service_takes(self):
        # The service refused the first flow on 2026-11-11: ActionDescriptionTooLong, 'maximum 256 and actual 295' (the Dataverse import has the same limit).
        for name, node in [*EVERY.items(), *DEFINITION["triggers"].items()]:
            self.assertLessEqual(len(node.get("description", "")), 256, name)


class TheFlowReadsTheQueueThroughTheConnector(unittest.TestCase):
    def test_the_trigger_is_the_v2_batch_trigger_of_azure_queues_with_the_parameters_that_the_connector_has(self):
        self.assertEqual(TRIGGER["type"], "OpenApiConnection")
        host = TRIGGER["inputs"]["host"]
        self.assertEqual((host["connectionName"], host["operationId"], host["apiId"]), ("shared_azurequeues", "OnMessages_V2", "/providers/Microsoft.PowerApps/apis/shared_azurequeues"))
        self.assertEqual(set(TRIGGER["inputs"]["parameters"]), AZURE_QUEUES["OnMessages_V2"]["parameters"])
        self.assertEqual(AZURE_QUEUES["OnMessages_V2"]["trigger"], "batch", "a batch trigger returns up to 32 messages, and the flow splits them into one run each")
        self.assertEqual(TRIGGER["inputs"]["authentication"], "@parameters('$authentication')")

    def test_the_endpoint_and_the_two_queues_are_the_three_environment_variables_and_nothing_of_the_estate_is_in_the_flow(self):
        parameters = TRIGGER["inputs"]["parameters"]
        self.assertEqual(parameters["storageAccountName"], "@parameters('Storage queue endpoint (mtnaut_StorageQueueEndpoint)')")
        self.assertEqual(parameters["queueName"], "@parameters('Queue name (mtnaut_QueueName)')")
        declared = {k: v for k, v in DEFINITION["parameters"].items() if "metadata" in v}
        self.assertEqual({v["metadata"]["schemaName"] for v in declared.values()}, {"mtnaut_StorageQueueEndpoint", "mtnaut_QueueName", "mtnaut_PostedQueueName"})
        for key, parameter in declared.items():
            self.assertEqual((parameter["type"], parameter["defaultValue"]), ("String", ""), f"{key}: no value in the repository")
            self.assertTrue(key.endswith(f"({parameter['metadata']['schemaName']})"), key)
        for text in strings(FLOW):
            self.assertNotRegex(text, r"(?i)queue\.core\.windows\.net|https://(?!schema\.management\.azure\.com)", text)

    def test_it_polls_once_a_minute_which_is_the_connectors_fastest_and_splits_the_messages_into_one_run_each_one_at_a_time(self):
        self.assertEqual(TRIGGER["recurrence"], {"interval": 1, "frequency": "Minute"}, "the connector allows one poll in 60 seconds")
        self.assertEqual(TRIGGER["splitOn"], "@triggerBody()?['QueueMessagesList']?['QueueMessage']", "the array of the definition Messages: QueueMessagesList.QueueMessage")
        self.assertEqual(TRIGGER["runtimeConfiguration"], {"concurrency": {"runs": 1}}, "a card at a time, in the order of the queue, and a batch of 32 is no burst for Teams")

    def test_the_visibility_timeout_is_longer_than_a_batch_takes_and_is_the_pace_of_a_retry(self):
        timeout = int(TRIGGER["inputs"]["parameters"]["visibilitytimeout"])
        # 32 messages one at a time, a post and a delete each: a few seconds each. Shorter than that, a message of the batch becomes visible again before its run reaches it, and a card is posted twice.
        self.assertGreaterEqual(timeout, 300)
        self.assertLessEqual(timeout, 3600, "a card that failed is tried again after this time, and a card is worth posting soon")
        self.assertIsInstance(TRIGGER["inputs"]["parameters"]["visibilitytimeout"], str, "the connector's parameter is a string")


class TheFlowPostsTheCardAsTheFlowBot(unittest.TestCase):
    def test_parse_reads_the_message_text_and_requires_what_the_post_needs(self):
        parse = ACTIONS["Parse_message"]
        self.assertEqual((parse["type"], parse["runAfter"], parse["inputs"]["content"]), ("ParseJson", {}, "@triggerBody()?['MessageText']"))
        schema = parse["inputs"]["schema"]
        self.assertEqual(set(schema["properties"]), {"v", "op", "id", "to", "title", "card", "request", "message"})
        self.assertEqual(set(schema["required"]), {"v", "id", "to", "card"}, "the title is for the people who read a failed run; the rest is for a request and for an update")
        self.assertEqual(schema["properties"]["v"], {"type": "integer", "enum": [1]}, "a message of another version is not read by this flow: it fails the parse")
        self.assertEqual(schema["properties"]["op"], {"type": "string", "enum": ["update"]}, "an operation that this flow does not know fails the parse, and the message is deleted")
        self.assertEqual(schema["properties"]["card"], {"type": "object"})

    def test_the_post_is_the_teams_action_that_posts_a_card_as_the_flow_bot_in_the_recipients_chat_with_it(self):
        post = EVERY[POSTER_STEP]
        host = post["inputs"]["host"]
        self.assertEqual((host["connectionName"], host["operationId"], host["apiId"]), ("shared_teams", "PostCardToConversation", "/providers/Microsoft.PowerApps/apis/shared_teams"))
        parameters = post["inputs"]["parameters"]
        self.assertEqual(set(parameters), TEAMS["PostCardToConversation"]["parameters"])
        self.assertIn(parameters["poster"], POSTERS)
        self.assertEqual((parameters["poster"], parameters["location"]), ("Flow bot", "Chat with Flow bot"))
        self.assertEqual(parameters["body/recipient"], "@body('Parse_message')?['to']")
        self.assertEqual(parameters["body/messageBody"], "@string(body('Parse_message')?['card'])", "the card is the JSON text of the Adaptive Card")
        self.assertEqual(post["runAfter"], {}, "it is the first step of the branch for a message that does not replace a card")
        self.assertIn(POSTER_STEP, ACTIONS[CONDITION]["else"]["actions"], "a message with no operation is a card to post")

    def test_only_these_eight_actions_call_a_connector_and_each_uses_the_parameters_that_its_operation_has(self):
        calls = {name: (a["inputs"]["host"]["connectionName"], a["inputs"]["host"]["operationId"], set(a["inputs"]["parameters"])) for name, a in EVERY.items() if a["type"] == "OpenApiConnection"}
        self.assertEqual(sorted(calls), sorted(["Delete_message_(V2)", "Delete_message_after_the_update_(V2)", "Delete_message_that_Teams_refused_(V2)", "Delete_message_that_Teams_refused_the_update_(V2)",
                                                "Delete_message_that_cannot_be_read_(V2)", PUT_STEP, POSTER_STEP, UPDATE_STEP]))
        for name, (connection, operation, parameters) in calls.items():
            if connection == "shared_azurequeues":
                self.assertIn(operation, ("DeleteMessage_V2", "PutMessage_V2"), name)
                self.assertEqual(parameters, AZURE_QUEUES[operation]["parameters"], name)
            else:
                self.assertIn(operation, TEAMS, name)
                self.assertEqual(parameters, TEAMS[operation]["parameters"], name)
        for action in EVERY.values():
            if action["type"] == "OpenApiConnection":
                self.assertEqual(action["inputs"]["authentication"], "@parameters('$authentication')")

    def test_both_connection_references_are_the_two_of_the_solution_and_are_the_creators_own(self):
        references = PROPERTIES["connectionReferences"]
        self.assertEqual({k: v["connection"]["connectionReferenceLogicalName"] for k, v in references.items()}, {"shared_azurequeues": "mtnaut_azurequeues", "shared_teams": "mtnaut_teams"})
        for key, reference in references.items():
            self.assertEqual(reference["api"], {"name": key})
            self.assertEqual(reference["runtimeSource"], "embedded", "an automated flow runs with the connections of the person who turned it on")
            self.assertNotIn("connectionName", reference["connection"], "no connection id: a person binds the connections when the solution is imported")


class TheFlowTellsTheAppWhichMessageItPosted(unittest.TestCase):
    def test_what_the_post_gave_is_written_to_the_queue_of_the_posted_cards_as_base64_text_because_the_functions_host_decodes_it(self):
        compose = EVERY[COMPOSE_STEP]
        self.assertEqual((compose["type"], compose["runAfter"]), ("Compose", {POSTER_STEP: ["Succeeded"]}))
        self.assertEqual(compose["inputs"], {"v": 1, "request": "@body('Parse_message')?['request']", "to": "@body('Parse_message')?['to']",
                                             "message": f"@body('{POSTER_STEP}')?['id']", "conversation": f"@body('{POSTER_STEP}')?['conversationId']"},
                         "the id and the conversationId of PostToConversationResponse (Learn, Microsoft Teams, Post adaptive card in a chat or channel)")
        put = EVERY[PUT_STEP]
        self.assertEqual(put["runAfter"], {COMPOSE_STEP: ["Succeeded"]})
        self.assertEqual(put["inputs"]["host"]["connectionName"], "shared_azurequeues")
        self.assertEqual(put["inputs"]["parameters"], {"storageAccountName": "@parameters('Storage queue endpoint (mtnaut_StorageQueueEndpoint)')",
                                                       "queueName": "@parameters('Posted queue name (mtnaut_PostedQueueName)')", "message": f"@base64(string(outputs('{COMPOSE_STEP}')))"})

    def test_a_card_that_was_posted_is_never_posted_again_because_the_message_is_deleted_whatever_the_write_came_to(self):
        self.assertEqual(EVERY["Delete_message_(V2)"]["runAfter"], {PUT_STEP: ["Succeeded", "Failed", "TimedOut"]})
        terminate = EVERY["Terminate_posted_message_not_written"]
        self.assertEqual(terminate["runAfter"], {"Delete_message_(V2)": ["Succeeded", "Failed"], PUT_STEP: ["Failed", "TimedOut"]}, "after the delete, and only when the write failed: the run says so")
        self.assertEqual((terminate["type"], terminate["inputs"]["runStatus"], terminate["inputs"]["runError"]["code"]), ("Terminate", "Failed", "PostedMessageNotWritten"))


class TheFlowReplacesACardWhenTheAppSaysSo(unittest.TestCase):
    def test_a_message_with_the_operation_update_goes_one_way_and_every_other_message_the_other(self):
        condition = ACTIONS[CONDITION]
        self.assertEqual((condition["type"], condition["runAfter"], condition["expression"]), ("If", {"Parse_message": ["Succeeded"]}, {"equals": ["@body('Parse_message')?['op']", "update"]}))
        self.assertEqual(sorted(a for a in ACTIONS), sorted([CONDITION, "Parse_message", "Delete_message_that_cannot_be_read_(V2)", "Terminate_message_that_cannot_be_read"]))
        self.assertIn(UPDATE_STEP, condition["actions"])
        self.assertNotIn(POSTER_STEP, condition["actions"])

    def test_the_update_is_the_teams_action_that_updates_a_card_as_the_flow_bot_with_the_message_that_the_app_names(self):
        update = EVERY[UPDATE_STEP]
        host = update["inputs"]["host"]
        self.assertEqual((host["connectionName"], host["operationId"], host["apiId"]), ("shared_teams", "UpdateCardInConversation", "/providers/Microsoft.PowerApps/apis/shared_teams"))
        parameters = update["inputs"]["parameters"]
        post = EVERY[POSTER_STEP]["inputs"]["parameters"]
        self.assertEqual({k: parameters[k] for k in ("poster", "location", "body/recipient", "body/messageBody")}, {k: post[k] for k in ("poster", "location", "body/recipient", "body/messageBody")},
                         "the same chat, the same person and the same card text as the post")
        self.assertEqual(parameters["body/messageId"], "@body('Parse_message')?['message']")
        self.assertEqual(update["runAfter"], {})

    def test_the_update_deletes_the_message_only_after_it_succeeded_and_ends_as_failed_otherwise(self):
        self.assertEqual(EVERY["Delete_message_after_the_update_(V2)"]["runAfter"], {UPDATE_STEP: ["Succeeded"]})
        refused = EVERY["Condition_Teams_refused_the_update_for_good"]
        self.assertEqual(refused["runAfter"], {UPDATE_STEP: ["Failed", "TimedOut"]})
        self.assertIn("Delete_message_that_Teams_refused_the_update_(V2)", refused["actions"])
        self.assertEqual(refused["else"], {"actions": {}})
        self.assertEqual(EVERY["Terminate_card_not_updated"]["runAfter"], {"Condition_Teams_refused_the_update_for_good": ["Succeeded", "Failed"]})
        self.assertEqual(EVERY["Terminate_card_not_updated"]["inputs"]["runStatus"], "Failed")


class AMessageIsDeletedOnlyAfterAPostOrAnUpdateOrWhenItCanNeverBeHandled(unittest.TestCase):
    CONDITIONS = (("Condition_Teams_refused_the_card_for_good", POSTER_STEP, "Delete_message_that_Teams_refused_(V2)"),
                  ("Condition_Teams_refused_the_update_for_good", UPDATE_STEP, "Delete_message_that_Teams_refused_the_update_(V2)"))

    def deletes(self):
        return {name: action for name, action in EVERY.items() if action["type"] == "OpenApiConnection" and action["inputs"]["host"]["operationId"] == "DeleteMessage_V2"}

    def test_the_normal_delete_runs_only_after_the_post_succeeded_and_the_write_that_follows_it_was_tried(self):
        self.assertEqual(EVERY["Delete_message_(V2)"]["runAfter"], {PUT_STEP: ["Succeeded", "Failed", "TimedOut"]})
        self.assertEqual(EVERY[PUT_STEP]["runAfter"], {COMPOSE_STEP: ["Succeeded"]})
        self.assertEqual(EVERY[COMPOSE_STEP]["runAfter"], {POSTER_STEP: ["Succeeded"]}, "so the delete cannot run before the post succeeded")

    def test_the_other_deletes_are_for_a_message_that_can_never_be_handled_and_nothing_else_deletes(self):
        self.assertEqual(sorted(self.deletes()), ["Delete_message_(V2)", "Delete_message_after_the_update_(V2)", "Delete_message_that_Teams_refused_(V2)",
                                                  "Delete_message_that_Teams_refused_the_update_(V2)", "Delete_message_that_cannot_be_read_(V2)"])
        unreadable = ACTIONS["Delete_message_that_cannot_be_read_(V2)"]
        self.assertEqual(unreadable["runAfter"], {"Parse_message": ["Failed"]}, "a message that is not of this version can never be handled")
        for name, step, delete in self.CONDITIONS:
            refused = EVERY[name]
            self.assertIn(delete, refused["actions"], "inside the condition, and nowhere else")
            self.assertEqual(refused["runAfter"], {step: ["Failed", "TimedOut"]})
            self.assertEqual(refused["else"], {"actions": {}}, "every other failure leaves the message in the queue: it is tried again after the visibility timeout")

    def test_only_a_400_a_404_or_a_413_of_teams_deletes_the_message_and_a_timeout_an_authorisation_or_a_throttle_does_not(self):
        for name, step, _ in self.CONDITIONS:
            expression = EVERY[name]["expression"]
            self.assertEqual(list(expression), ["or"])
            codes = []
            for clause in expression["or"]:
                self.assertEqual(list(clause), ["equals"])
                left, right = clause["equals"]
                self.assertEqual(left, f"@outputs('{step}')?['statusCode']")
                codes.append(right)
            self.assertEqual(codes, [400, 404, 413], "413 is 'Request Entity too large': a card of more than about 28 KB stays too large")
            for retried in (401, 403, 408, 429, 500, 502, 503, 504, None):
                self.assertNotIn(retried, codes, f"{retried}: the card is not at fault, or the failure goes away: the message stays")

    def test_each_delete_names_the_queue_and_the_message_of_the_trigger_and_its_pop_receipt(self):
        for name, action in self.deletes().items():
            parameters = action["inputs"]["parameters"]
            self.assertEqual(parameters["messageId"], "@triggerBody()?['MessageId']", name)
            self.assertEqual(parameters["popreceipt"], "@triggerBody()?['PopReceipt']", name)
            self.assertEqual(parameters["queueName"], "@parameters('Queue name (mtnaut_QueueName)')", name)
            self.assertEqual(parameters["storageAccountName"], "@parameters('Storage queue endpoint (mtnaut_StorageQueueEndpoint)')", name)
        self.assertLessEqual({"MessageId", "PopReceipt", "MessageText"}, QUEUE_MESSAGE_FIELDS)

    def test_a_run_that_did_not_finish_its_work_ends_as_failed_so_that_the_run_history_says_so(self):
        ends = {"Terminate_message_that_cannot_be_read": "Delete_message_that_cannot_be_read_(V2)", "Terminate_card_not_posted": "Condition_Teams_refused_the_card_for_good",
                "Terminate_card_not_updated": "Condition_Teams_refused_the_update_for_good", "Terminate_posted_message_not_written": "Delete_message_(V2)"}
        self.assertEqual(sorted(name for name, action in EVERY.items() if action["type"] == "Terminate"), sorted(ends))
        for name, after in ends.items():
            action = EVERY[name]
            self.assertEqual(action["inputs"]["runStatus"], "Failed")
            self.assertEqual(action["runAfter"][after], ["Succeeded", "Failed"], "it runs whatever the delete did")
            self.assertTrue(action["inputs"]["runError"]["code"] and action["inputs"]["runError"]["message"])
        # On the way of a card that was posted or replaced nothing terminates: the end actions follow the paths of a failure only.
        for name in ("Parse_message", CONDITION, POSTER_STEP, COMPOSE_STEP, PUT_STEP, "Delete_message_(V2)", UPDATE_STEP, "Delete_message_after_the_update_(V2)"):
            self.assertNotEqual(EVERY[name]["type"], "Terminate", name)


class TheDefinitionIsWellFormed(unittest.TestCase):
    def test_every_action_that_an_action_or_an_expression_names_exists(self):
        names = set(EVERY)
        for name, action in EVERY.items():
            for predecessor in action["runAfter"]:
                self.assertIn(predecessor, names, f"{name} runs after {predecessor}")
        for expression in expressions(DEFINITION):
            for referenced in re.findall(r"(?:body|outputs|actions|items)\('([^']+)'\)", expression):
                self.assertIn(referenced, names, f"{expression} names {referenced}")

    def test_the_runs_follow_one_another_with_no_cycle(self):
        def depth(name, seen=()):
            self.assertNotIn(name, seen, f"a cycle at {name}")
            predecessors = EVERY[name]["runAfter"]
            return 1 + max([depth(p, (*seen, name)) for p in predecessors], default=0)
        for name in EVERY:
            depth(name)

    def test_the_expressions_are_balanced_and_the_trigger_is_used_only_by_its_own_fields(self):
        for expression in expressions(DEFINITION):
            code = without_literals(expression)
            self.assertEqual(code.count("("), code.count(")"), expression)
            self.assertEqual(code.count("["), code.count("]"), expression)
            self.assertEqual(code.count("{"), code.count("}"), expression)
        for expression in expressions(DEFINITION):
            for field in re.findall(r"triggerBody\(\)\?\['(\w+)'\]", expression):
                self.assertIn(field, QUEUE_MESSAGE_FIELDS | {"QueueMessagesList"}, f"{expression}: not a field of the trigger's message")

    def test_the_definition_has_the_shape_of_a_flow_of_a_solution(self):
        self.assertEqual(DEFINITION["$schema"], "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#")
        self.assertEqual(FLOW["schemaVersion"], "1.0.0.0")
        self.assertEqual({k for k in DEFINITION["parameters"] if k.startswith("$")}, {"$connections", "$authentication"})
        for item in [TRIGGER, *EVERY.values()]:
            self.assertRegex(item["metadata"]["operationMetadataId"], r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        ids = [i["metadata"]["operationMetadataId"] for i in [TRIGGER, *EVERY.values()]]
        self.assertEqual(len(ids), len(set(ids)), "every step has an id of its own")

    def test_the_flow_holds_no_key_no_connection_string_and_no_token(self):
        for text in strings(FLOW):
            self.assertNotRegex(text, r"(?i)accountkey|sharedaccesssignature|sig=|connectionstring|password|bearer ", text)


if __name__ == "__main__":
    unittest.main()
