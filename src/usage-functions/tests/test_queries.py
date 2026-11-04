import re
import unittest

from support import LLM_COLUMNS, REQUEST_COLUMNS, kit_query, kit_workflow

from usage import queries

START = "2026-11-04T09:00:00"
END = "2026-11-04T12:00:00"
TEMPLATES = {"llm": queries.LLM_QUERY, "mcp": queries.MCP_QUERY, "agent": queries.AGENT_QUERY}
LLM_METRICS = (
    "Prompt Tokens",
    "Completion Tokens",
    "Total Tokens",
    "Completion Accepted Prediction Tokens",
    "Completion Audio Tokens",
    "Completion Reasoning Tokens",
    "Completion Rejected Prediction Tokens",
    "Prompt Audio Tokens",
    "Prompt Cached Tokens",
)


@unittest.skipIf(kit_workflow("llm") is None, "the kit clone is not present (local/working-files/citadel or kit)")
class KitTextTests(unittest.TestCase):
    def test_each_query_is_the_text_of_the_kit_with_the_window_put_in(self):
        for job, template in TEMPLATES.items():
            with self.subTest(job=job):
                self.assertEqual(queries.build_query(template, START, END), kit_query(job, START, END))


class QueryContentTests(unittest.TestCase):
    def test_the_window_is_in_the_two_let_lines_that_open_every_query(self):
        for job, template in TEMPLATES.items():
            with self.subTest(job=job):
                query = queries.build_query(template, START, END)
                self.assertTrue(query.startswith(f"let startTime = todatetime('{START}');\nlet endTime = todatetime('{END}');\n"))
                self.assertNotIn("<<", query)
                self.assertIn("| where ingestion_time() between(startTime .. endTime) and ", query)

    def test_the_llm_query_sums_the_nine_token_metrics(self):
        query = queries.build_query(queries.LLM_QUERY, START, END)
        self.assertIn("name in (" + ", ".join(f"'{name}'" for name in LLM_METRICS) + ")", query)
        for name in LLM_METRICS:
            self.assertIn(f'sumif(value, name == "{name}")', query)
        self.assertIn('backendId = tostring(customDimensions["Backend ID"])', query)

    def test_the_mcp_query_sums_the_mcp_requests(self):
        query = queries.build_query(queries.MCP_QUERY, START, END)
        self.assertIn("and name == 'McpRequests'", query)
        self.assertIn("requestCount = sum(valueSum)", query)
        self.assertIn('backendId = tostring(customDimensions["backendId"])', query)

    def test_the_agent_query_sums_the_agent_requests(self):
        query = queries.build_query(queries.AGENT_QUERY, START, END)
        self.assertIn("and name == 'A2ARequests'", query)
        self.assertIn("requestCount = sum(valueSum)", query)

    def test_a_query_projects_the_columns_that_the_documents_read(self):
        expected = {"llm": LLM_COLUMNS, "mcp": REQUEST_COLUMNS, "agent": REQUEST_COLUMNS}
        for job, template in TEMPLATES.items():
            with self.subTest(job=job):
                projected = template.splitlines()[-1]
                match = re.fullmatch(r'\| project timestamp = format_datetime\(timeBin, "[^"]*"\), (.*)', projected)
                self.assertIsNotNone(match)
                self.assertEqual(("timestamp", *match.group(1).split(", ")), expected[job])


if __name__ == "__main__":
    unittest.main()
