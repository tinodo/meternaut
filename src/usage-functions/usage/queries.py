"""The KQL of the three export jobs.

Each query is the text of the kit's workflow (src/usage-ingestion-logicapp/<job>/workflow.json, action Run_query_and_list_results),
copied as it is. Only the two Logic App expressions that held the window are replaced: START_TIME and END_TIME.
The lines are not wrapped, so that the text can be compared with the kit's text.
"""

START_TIME = "<<START_TIME>>"
END_TIME = "<<END_TIME>>"

LLM_QUERY = """\
let startTime = todatetime('<<START_TIME>>');
let endTime = todatetime('<<END_TIME>>');

let timeInterval = 1h;
let timeBinFormat = "M/dd/yyyy h:mm:ss tt";

customMetrics
| extend appId = tostring(customDimensions["appId"]),
         productName = tostring(customDimensions["productName"]),
         deploymentName = tostring(customDimensions["deploymentName"]),
         backendId = tostring(customDimensions["Backend ID"]),
         gatewayName = tostring(customDimensions["Service Name"]),
         gatewayRegion = tostring(customDimensions["Region"]),
         timeBin = bin(timestamp, timeInterval)
| where ingestion_time() between(startTime .. endTime) and name in ('Prompt Tokens', 'Completion Tokens', 'Total Tokens', 'Completion Accepted Prediction Tokens', 'Completion Audio Tokens', 'Completion Reasoning Tokens', 'Completion Rejected Prediction Tokens', 'Prompt Audio Tokens', 'Prompt Cached Tokens')
| summarize totalTokens = sumif(value, name == "Total Tokens"),
            responseTokens = sumif(value, name == "Completion Tokens"),
            promptTokens = sumif(value, name == "Prompt Tokens"),
            completionAcceptedPredictionTokens = sumif(value, name == "Completion Accepted Prediction Tokens"),
            completionAudioTokens = sumif(value, name == "Completion Audio Tokens"),
            completionReasoningTokens = sumif(value, name == "Completion Reasoning Tokens"),
            completionRejectedPredictionTokens = sumif(value, name == "Completion Rejected Prediction Tokens"),
            promptAudioTokens = sumif(value, name == "Prompt Audio Tokens"),
            promptCachedTokens = sumif(value, name == "Prompt Cached Tokens")
            by appId, deploymentName, productName, backendId, gatewayName, gatewayRegion, timeBin
| project timestamp = format_datetime(timeBin, "M/dd/yyyy h:mm:ss tt"), appId, deploymentName, productName, backendId, gatewayName, gatewayRegion, promptTokens, responseTokens, totalTokens, completionAcceptedPredictionTokens, completionAudioTokens, completionReasoningTokens, completionRejectedPredictionTokens, promptAudioTokens, promptCachedTokens"""

MCP_QUERY = """\
let startTime = todatetime('<<START_TIME>>');
let endTime = todatetime('<<END_TIME>>');
let timeInterval = 1h;
customMetrics
| extend appId = tostring(customDimensions["appId"]),
         productName = tostring(customDimensions["productName"]),
         deploymentName = tostring(customDimensions["deploymentName"]),
         backendId = tostring(customDimensions["backendId"]),
         assetType = tostring(customDimensions["customDimension1"]),
         operationName = tostring(customDimensions["customDimension2"]),
         gatewayName = tostring(customDimensions["Service Name"]),
         gatewayRegion = tostring(customDimensions["Region"]),
         timeBin = bin(timestamp, timeInterval)
| where ingestion_time() between(startTime .. endTime) and name == 'McpRequests'
| summarize requestCount = sum(valueSum) by appId, deploymentName, productName, backendId, assetType, operationName, gatewayName, gatewayRegion, timeBin
| project timestamp = format_datetime(timeBin, "M/dd/yyyy h:mm:ss tt"), appId, deploymentName, productName, backendId, assetType, operationName, gatewayName, gatewayRegion, requestCount"""

AGENT_QUERY = """\
let startTime = todatetime('<<START_TIME>>');
let endTime = todatetime('<<END_TIME>>');
let timeInterval = 1h;
customMetrics
| extend appId = tostring(customDimensions["appId"]),
         productName = tostring(customDimensions["productName"]),
         deploymentName = tostring(customDimensions["deploymentName"]),
         backendId = tostring(customDimensions["backendId"]),
         assetType = tostring(customDimensions["customDimension1"]),
         operationName = tostring(customDimensions["customDimension2"]),
         gatewayName = tostring(customDimensions["Service Name"]),
         gatewayRegion = tostring(customDimensions["Region"]),
         timeBin = bin(timestamp, timeInterval)
| where ingestion_time() between(startTime .. endTime) and name == 'A2ARequests'
| summarize requestCount = sum(valueSum) by appId, deploymentName, productName, backendId, assetType, operationName, gatewayName, gatewayRegion, timeBin
| project timestamp = format_datetime(timeBin, "M/dd/yyyy h:mm:ss tt"), appId, deploymentName, productName, backendId, assetType, operationName, gatewayName, gatewayRegion, requestCount"""


def build_query(template: str, start: str, end: str) -> str:
    """Put the window ("yyyy-MM-ddTHH:mm:ss" strings) into a query template."""
    return template.replace(START_TIME, start).replace(END_TIME, end)
