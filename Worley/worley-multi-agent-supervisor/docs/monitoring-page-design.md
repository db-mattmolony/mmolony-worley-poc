# Monitoring Page Design

## Overview

Add a second tab to the Databricks App that visualises agent execution traces. The monitoring page reads from the MLflow Traces API and the inference table to display real-time and historical analytics.

## Data Sources

### 1. MLflow Traces API
- Endpoint: `GET /api/2.0/mlflow/traces?experiment_ids={id}`
- Provides: execution_time_ms, status, token usage, span count, request/response payloads
- The trace response contains: `current_agent` (routing decision), `iteration_count`, model name, per-call token breakdown

### 2. Inference Table
- Table: `az_databricks_poc.multi_agent_supervisor.worley_supervisor_agent_payload`
- Provides: request_time, status_code, execution_duration_ms, requester, full request/response JSON
- Populated automatically by the serving endpoint

## Proposed Visualisations

### Row 1: Summary KPIs (4 cards)
- **Total Requests** — count of traces
- **Avg Latency** — mean execution_time_ms
- **Total Tokens** — sum of input + output tokens
- **Error Rate** — % of non-OK traces

### Row 2: Time Series Charts
- **Requests Over Time** — histogram of trace count by hour/day
- **Token Consumption Over Time** — stacked area chart (input vs output tokens by hour/day)

### Row 3: Distribution & Routing
- **Latency Distribution** — histogram of execution_time_ms
- **Sub-Agent Delegation** — pie/bar chart of `current_agent` values extracted from trace responses (knowledge_assistant vs general_assistant)

### Row 4: Detail Table
- **Recent Traces** — sortable table showing: timestamp, status, latency, tokens, routed agent, user question (truncated)

## Implementation Approach

### App Structure
The current `app.py` uses Gradio with a single chat interface. We'll add a `gr.Tab` layout:

```
gr.Blocks:
  Tab 1: "Chat" → existing chat interface
  Tab 2: "Monitoring" → new dashboard
```

### Data Fetching
Add a backend function that:
1. Calls the MLflow Traces API (via `WorkspaceClient`) to fetch recent traces
2. Parses `mlflow.trace.tokenUsage`, `mlflow.trace.response` metadata from each trace
3. Extracts `current_agent` from the response JSON to determine routing
4. Returns structured data for Gradio plots

### Visualisation Library
Use **Plotly** via Gradio's `gr.Plot` component for interactive charts. Plotly is already available in the Databricks App environment.

## Files to Modify

| File | Change |
|------|--------|
| `app.py` | Add Tab layout, monitoring tab with plots and data fetching |
| `requirements.txt` | Add `plotly` if not already present |

## Key Parsing Logic

From each trace, extract:
```python
# Token usage
token_meta = json.loads(trace["request_metadata"]["mlflow.trace.tokenUsage"])
input_tokens = token_meta["input_tokens"]
output_tokens = token_meta["output_tokens"]

# Routed agent
response = json.loads(trace["request_metadata"]["mlflow.trace.response"])
routed_agent = response["current_agent"]  # "general_assistant", "knowledge_assistant", "done"

# Model used
for msg in response["messages"]:
    if msg.get("response_metadata", {}).get("model"):
        model = msg["response_metadata"]["model"]

# Latency
latency_ms = trace["execution_time_ms"]

# Status
status = trace["status"]  # "OK" or "ERROR"
```
