import json
import re
import unittest

from support import llm_row, request_row

from usage import documents

LLM_FIELDS = [
    "id", "timestamp", "appId", "productName", "deploymentName", "backendId", "customDimension1", "customDimension2",
    "gatewayName", "gatewayRegion", "promptTokens", "responseTokens", "totalTokens", "completionAcceptedPredictionTokens",
    "completionAudioTokens", "completionReasoningTokens", "completionRejectedPredictionTokens", "promptAudioTokens",
    "promptCachedTokens", "targetService", "model", "aiGatewayId", "RequestIp", "operationName",
]
REQUEST_FIELDS = [
    "id", "timestamp", "appId", "productName", "deploymentName", "backendId", "assetType", "operationName", "gatewayName",
    "gatewayRegion", "requestCount", "targetService", "aiGatewayId",
]


class LlmDocumentTests(unittest.TestCase):
    def test_the_document_is_the_one_of_the_kit(self):
        self.assertEqual(
            documents.llm_document(llm_row(), "llm-1"),
            {
                "id": "llm-1", "timestamp": "11/4/2026 9:00:00 AM", "appId": "app-1", "productName": "contract-1",
                "deploymentName": "gpt-4o", "backendId": "backend-1", "customDimension1": "", "customDimension2": "",
                "gatewayName": "gateway-1", "gatewayRegion": "Sweden Central",
                "promptTokens": "17", "responseTokens": "5", "totalTokens": "22", "completionAcceptedPredictionTokens": "0",
                "completionAudioTokens": "0", "completionReasoningTokens": "3", "completionRejectedPredictionTokens": "0",
                "promptAudioTokens": "0", "promptCachedTokens": "2",
                "targetService": "NA", "model": "gpt-4o", "aiGatewayId": "managed", "RequestIp": "NA", "operationName": "NA",
            },
        )

    def test_the_fields_come_in_the_order_of_the_kit(self):
        self.assertEqual(list(documents.llm_document(llm_row(), "llm-1")), LLM_FIELDS)

    def test_the_model_is_the_deployment_name(self):
        document = documents.llm_document(llm_row(deploymentName="gpt-5-mini"), "llm-1")
        self.assertEqual((document["deploymentName"], document["model"]), ("gpt-5-mini", "gpt-5-mini"))

    def test_counts_are_strings_of_whole_numbers_whether_they_arrive_as_int_or_float(self):
        values = {17: "17", 17.0: "17", 0.0: "0", -0.0: "0", 1e15: "1000000000000000", 123456789012: "123456789012"}
        for value, expected in values.items():
            with self.subTest(value=value):
                document = documents.llm_document(llm_row(promptTokens=value, totalTokens=value), "llm-1")
                self.assertEqual((document["promptTokens"], document["totalTokens"]), (expected, expected))

    def test_a_float_never_shows_in_a_document(self):
        row = llm_row(**{field: 40.0 for field in documents.LLM_TOKEN_FIELDS})
        document = documents.llm_document(row, "llm-1")
        text = json.dumps(document)
        self.assertNotIn("40.0", text)
        self.assertIsNone(re.search(r'"-?\d+\.\d+"', text))
        for field in documents.LLM_TOKEN_FIELDS:
            self.assertEqual(document[field], "40")
            self.assertIsInstance(document[field], str)

    def test_a_count_that_is_not_a_whole_number_is_refused_with_its_field_name(self):
        for value in (1.5, float("nan"), float("inf"), None, True, "17", [17]):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "^totalTokens is not a"):
                documents.llm_document(llm_row(totalTokens=value), "llm-1")

    def test_a_missing_column_is_an_error(self):
        row = llm_row()
        del row["promptCachedTokens"]
        with self.assertRaises(KeyError):
            documents.llm_document(row, "llm-1")

    def test_a_null_text_becomes_an_empty_string(self):
        document = documents.llm_document(llm_row(appId=None, backendId=None), "llm-1")
        self.assertEqual((document["appId"], document["backendId"]), ("", ""))


class RequestCountDocumentTests(unittest.TestCase):
    def test_the_mcp_document_is_the_one_of_the_kit(self):
        self.assertEqual(
            documents.mcp_document(request_row(), "mcp-1"),
            {
                "id": "mcp-1", "timestamp": "11/4/2026 9:00:00 AM", "appId": "subscription-1", "productName": "contract-1",
                "deploymentName": "tool-server", "backendId": "backend-1", "assetType": "mcp", "operationName": "tools/call",
                "gatewayName": "gateway-1", "gatewayRegion": "Sweden Central", "requestCount": 3, "targetService": "MCP",
                "aiGatewayId": "managed",
            },
        )

    def test_the_agent_document_is_the_one_of_the_kit(self):
        document = documents.agent_document(request_row(assetType="a2a"), "agent-1")
        self.assertEqual((document["assetType"], document["targetService"], document["aiGatewayId"]), ("a2a", "A2A", "managed"))
        self.assertEqual(list(document), REQUEST_FIELDS)

    def test_the_asset_type_is_fixed_whatever_the_query_returned(self):
        self.assertEqual(documents.mcp_document(request_row(assetType="other"), "mcp-1")["assetType"], "mcp")
        self.assertEqual(documents.agent_document(request_row(assetType="other"), "agent-1")["assetType"], "a2a")

    def test_the_fields_come_in_the_order_of_the_kit(self):
        self.assertEqual(list(documents.mcp_document(request_row(), "mcp-1")), REQUEST_FIELDS)

    def test_the_request_count_is_a_json_number_and_a_whole_count_has_no_decimal_point(self):
        for value, shown in ((3.0, "3"), (3, "3"), (2.5, "2.5"), (0.0, "0")):
            with self.subTest(value=value):
                document = documents.mcp_document(request_row(requestCount=value), "mcp-1")
                self.assertIn(f'"requestCount": {shown},', json.dumps(document))
                self.assertNotIsInstance(document["requestCount"], str)

    def test_a_request_count_that_is_not_a_number_is_refused(self):
        for value in (None, "3", float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "^requestCount is not a"):
                documents.agent_document(request_row(requestCount=value), "agent-1")


if __name__ == "__main__":
    unittest.main()
