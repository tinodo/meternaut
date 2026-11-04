"""Copies the usage data of the Azure API Management AI gateway into Azure Cosmos DB.

Three scheduled jobs export Application Insights custom metrics (LLM tokens, MCP requests, agent requests).
Two Event Hub functions store the AI usage and PII usage events. One control function runs an export job on demand.
"""
