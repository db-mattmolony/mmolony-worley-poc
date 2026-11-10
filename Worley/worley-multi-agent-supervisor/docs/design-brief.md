# Design Brief: Multi-Agent Supervisor + Monitoring

## Background

Worley is building agentic AI applications across multiple environments (Databricks, Azure AI Foundry, AWS Bedrock, ServiceNow, Copilot 365) without a unified governance framework. As agent adoption accelerates, the lack of centralised observability, cost monitoring, and access control poses operational and compliance risks.

This project (Use Cases 2 & 3 from the Worley-Databricks POC) delivers a **multi-agent supervisor** with an integrated **monitoring application** — giving Worley's AI governance team visibility into agent usage, costs, health, and trace-level execution detail across all agent sources.

## Goal

Build a Databricks-hosted application with two pages:

1. **Chat Page** — End users interact with a multi-agent supervisor that routes questions to the appropriate sub-agent
2. **Monitoring Page** — Visualises MLflow traces showing which agent sub-system handled each request, token usage, latency, and execution outcomes

## Architecture

```
Application (Databricks App)
├── Page 1: Chat UI
│   └── Multi-Agent Supervisor (serving endpoint)
│       ├── RAG Agent (Knowledge Assistant endpoint)
│       └── Foundry Endpoint — catch-all (Azure AI Foundry via AI Gateway)
│
├── Page 2: Monitoring Dashboard
│   ├── Databricks Experiment #1 → #1 Traces (Delta Tables)
│   └── Databricks Experiment #2 → #2 Traces (Delta Tables)
│
└── trace_id created by application (links chat turns to traces)
```

The application generates a `trace_id` for each conversation turn and passes it through the supervisor. This ID links the chat interaction to its MLflow traces, enabling the monitoring page to display end-to-end execution detail.

### Sub-Agent Routing

The supervisor uses an LLM to classify incoming questions and route to:

- **RAG Agent** (Knowledge Assistant) — Worley-specific domain questions (finance, procurement, engineering standards, policies, projects)
- **Foundry Endpoint** (catch-all) — General-purpose questions routed through Azure AI Foundry via the Databricks AI Gateway

A public-facing inverse-centre supervisor agent sits in front, providing the external interface.

### Trace Storage

Each sub-agent system logs to an independent MLflow experiment. Traces are synced to Unity Catalog Delta tables, enabling:

- SQL-based querying and dashboarding
- Cross-agent aggregate views
- Long-term retention and lineage

## Key Requirements

| Requirement | How Delivered |
|---|---|
| Multi-agent routing | LangGraph supervisor with LLM-based classification |
| AI Gateway control | Centralised rate limiting, fallback, guardrails, token tracking |
| Observability | MLflow traces with per-agent latency, token usage, execution status |
| Traceability | Request-level and step-level spans across orchestrator, agents, and APIs |
| Cost management | Token consumption per model/agent via inference tables and trace metadata |
| Interoperability | Unified tracing for Databricks-hosted and external models |
| Openness | All trace data persisted in Unity Catalog Delta tables (no vendor lock-in) |

## Current State

- Multi-agent supervisor deployed as MLflow ChatModel on a serving endpoint (`worley-supervisor-agent`)
- LangGraph graph with supervisor, general_assistant, and knowledge_assistant nodes
- MLflow tracing enabled via `langchain.autolog` — traces land in `/Shared/worley-supervisor-agent`
- Inference table enabled on the serving endpoint
- AI Gateway endpoints registered for Azure AI Foundry models (GPT 5.4 Mini, Grok 4 Fast)
- Databricks App scaffold exists (`app.py`, `app.yaml`) but is not yet updated for the two-page layout

## What Remains

- Build the two-page application UI (chat + monitoring)
- Connect the monitoring page to MLflow trace data (Delta tables or trace API)
- Wire `trace_id` from the application through to traces for end-to-end linking
- Add the external Foundry agent endpoint as a sub-agent route
- Set up independent MLflow experiments per sub-agent system
- Build evaluation datasets from traces and implement LLM-as-Judge scorers
- Configure alerting for agent failures, latency spikes, and abnormal token usage

## Dependencies

- Worley to create Azure AI Foundry agent
- Worley to provide sample data for the Knowledge Assistant
- Access to system tables for cost monitoring data

## POC Timeline

Start: 2026-04-02 | End: 2026-04-14

## Reference

- [Worley POC Document](https://docs.google.com/document/d/13DKntCzUi6k3hpSNAAH0svKp9Fjy8CrxAdReIkNPsTY/edit)
- Workspace: https://adb-7405604717684409.9.azuredatabricks.net
- Serving endpoint: `worley-supervisor-agent`
- MLflow experiment: `/Shared/worley-supervisor-agent`
- UC model: `az_databricks_poc.multi_agent_supervisor.worley_supervisor_agent`
