"""The Cosmos DB documents that the export jobs write.

Field names and value types are those of the kit's Logic App workflows: the timestamp and the nine LLM token counts are
strings (whole numbers, for example "17"), and requestCount is a JSON number.
"""
import math
from collections.abc import Mapping
from typing import Any

Row = Mapping[str, Any]

LLM_TOKEN_FIELDS = (
    "promptTokens",
    "responseTokens",
    "totalTokens",
    "completionAcceptedPredictionTokens",
    "completionAudioTokens",
    "completionReasoningTokens",
    "completionRejectedPredictionTokens",
    "promptAudioTokens",
    "promptCachedTokens",
)


def text(row: Row, field: str) -> str:
    """A string column. A null value becomes an empty string, as in the kit."""
    value = row[field]
    return "" if value is None else str(value)


def json_number(value: object, field: str) -> int | float:
    """A numeric column as a JSON number: a whole value is an int (3, never 3.0)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} is not a number")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field} is not a finite number")
        if value.is_integer():
            return int(value)
    return value


def whole_number(value: object, field: str) -> int:
    """Log Analytics sums arrive as int or float. A token count must be a whole number."""
    number = json_number(value, field)
    if not isinstance(number, int):
        raise ValueError(f"{field} is not a whole number")
    return number


def llm_document(row: Row, doc_id: str) -> dict[str, Any]:
    document: dict[str, Any] = {
        "id": doc_id,
        "timestamp": text(row, "timestamp"),
        "appId": text(row, "appId"),
        "productName": text(row, "productName"),
        "deploymentName": text(row, "deploymentName"),
        "backendId": text(row, "backendId"),
        "customDimension1": "",
        "customDimension2": "",
        "gatewayName": text(row, "gatewayName"),
        "gatewayRegion": text(row, "gatewayRegion"),
    }
    for field in LLM_TOKEN_FIELDS:
        document[field] = str(whole_number(row[field], field))
    document["targetService"] = "NA"
    document["model"] = document["deploymentName"]
    document["aiGatewayId"] = "managed"
    document["RequestIp"] = "NA"
    document["operationName"] = "NA"
    return document


def request_count_document(row: Row, doc_id: str, asset_type: str, target_service: str) -> dict[str, Any]:
    return {
        "id": doc_id,
        "timestamp": text(row, "timestamp"),
        "appId": text(row, "appId"),
        "productName": text(row, "productName"),
        "deploymentName": text(row, "deploymentName"),
        "backendId": text(row, "backendId"),
        "assetType": asset_type,
        "operationName": text(row, "operationName"),
        "gatewayName": text(row, "gatewayName"),
        "gatewayRegion": text(row, "gatewayRegion"),
        "requestCount": json_number(row["requestCount"], "requestCount"),
        "targetService": target_service,
        "aiGatewayId": "managed",
    }


def mcp_document(row: Row, doc_id: str) -> dict[str, Any]:
    return request_count_document(row, doc_id, asset_type="mcp", target_service="MCP")


def agent_document(row: Row, doc_id: str) -> dict[str, Any]:
    return request_count_document(row, doc_id, asset_type="a2a", target_service="A2A")
