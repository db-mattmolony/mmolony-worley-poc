"""Node functions for the Worley Supervisor LangGraph."""

from __future__ import annotations

import time as _time

import mlflow
from databricks_langchain import ChatDatabricks
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.config import (
    DEFAULT_SUPERVISOR_MODEL,
    GENERAL_ASSISTANT_ENDPOINT,
    GENIE_SPACE_ID,
    KA_ENDPOINT_NAME,
    MAX_ITERATIONS,
)
from agent.state import SupervisorState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_llm(endpoint_name: str) -> ChatDatabricks:
    """Return a ChatDatabricks routed through the workspace AI Gateway.

    All endpoints (foundry-gpt-5-4-mini, foundry-grok-4-fast, etc.) are
    registered as external model endpoints in the workspace AI Gateway.
    The gateway handles rate limiting, guardrails, usage tracking, and
    secret-managed API keys for the upstream provider.

    ChatDatabricks automatically picks up credentials provisioned via
    mlflow.pyfunc.log_model(resources=...) inside Model Serving.
    """
    return ChatDatabricks(
        endpoint=endpoint_name,
        temperature=0.3,
        max_tokens=2048,
    )


def _safe_update_trace(state: SupervisorState) -> None:
    """Update the current MLflow trace if one exists, otherwise no-op."""
    try:
        mlflow.update_current_trace(tags={
            "user_trace_id": state["trace_id"],
            "authenticated_user": state["authenticated_user"],
            "app": "worley-supervisor",
            "routed_agent": state.get("routed_agent", ""),
        })
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

SUPERVISOR_SYSTEM_PROMPT = """You are a supervisor agent for Worley's Unified AI Platform.
You coordinate specialised sub-agents to answer user questions.
Answer the user's question directly, clearly, and concisely.
If you don't know the answer, say so."""

ROUTING_SYSTEM_PROMPT = """You are a routing agent for Worley's Unified AI Platform.
Your job is to decide which sub-agent should handle the user's question.

Available agents:
- knowledge_assistant: Use for questions about Worley's internal knowledge base, documents, policies, projects, engineering standards, safety procedures, or any Worley-specific domain knowledge.
- genie_space: Use for questions about Worley's stock price, share price, ASX performance, trading volume, market data, financial metrics, or any quantitative data analysis about Worley's market performance.
- general_assistant: Use for general questions, conversation, reasoning, summarisation, or anything not specific to Worley's knowledge base or financial data.

Respond with ONLY the agent name: either "knowledge_assistant", "genie_space", or "general_assistant". Nothing else."""


@mlflow.trace(name="supervisor_node")
def supervisor_node(
    state: SupervisorState,
    model_endpoint: str | None = None,
) -> SupervisorState:
    """Decide which sub-agent should handle the user's request."""
    _safe_update_trace(state)

    endpoint = model_endpoint or DEFAULT_SUPERVISOR_MODEL
    llm = get_llm(endpoint)
    routing_messages = [
        SystemMessage(content=ROUTING_SYSTEM_PROMPT),
    ] + state["messages"]

    try:
        routing_response = llm.invoke(routing_messages)
        route = routing_response.content.strip().lower()

        if "knowledge" in route:
            chosen_agent = "knowledge_assistant"
        elif "genie" in route:
            chosen_agent = "genie_space"
        elif "general" in route:
            chosen_agent = "general_assistant"
        else:
            chosen_agent = "general_assistant"

    except Exception:
        chosen_agent = "general_assistant"

    return {
        **state,
        "current_agent": chosen_agent,
        "routed_agent": chosen_agent,
        "iteration_count": state["iteration_count"] + 1,
    }


@mlflow.trace(name="general_assistant")
def general_assistant_node(
    state: SupervisorState,
    model_endpoint: str | None = None,
) -> SupervisorState:
    """Call an LLM via AI Gateway to answer the user's question."""
    _safe_update_trace(state)

    llm = get_llm(GENERAL_ASSISTANT_ENDPOINT)

    messages = [SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT)] + state["messages"]

    # Capture sub-agent input (last user message)
    sub_input = ""
    for m in reversed(state["messages"]):
        if hasattr(m, "type") and m.type == "human":
            sub_input = m.content
            break

    response: AIMessage = llm.invoke(messages)

    return {
        **state,
        "messages": [response],
        "final_answer": response.content,
        "current_agent": "done",
        "sub_agent_input": sub_input,
        "sub_agent_output": response.content,
    }


# ---------------------------------------------------------------------------
# Knowledge Assistant node
# ---------------------------------------------------------------------------

@mlflow.trace(name="knowledge_assistant")
def knowledge_assistant_node(
    state: SupervisorState,
    model_endpoint: str | None = None,
) -> SupervisorState:
    """Call the Knowledge Assistant serving endpoint.

    Falls back to the general assistant if the KA endpoint fails.
    """
    _safe_update_trace(state)

    # Extract the latest user message
    last_message = ""
    for m in reversed(state["messages"]):
        if hasattr(m, "type") and m.type == "human":
            last_message = m.content
            break
        elif hasattr(m, "content"):
            last_message = m.content
            break

    try:
        ka_llm = ChatDatabricks(
            endpoint=KA_ENDPOINT_NAME,
            max_tokens=2048,
        )
        ka_messages = [HumanMessage(content=last_message)]
        response = ka_llm.invoke(ka_messages)
        answer = response.content

    except Exception:
        # Fall back to general assistant instead of crashing
        return general_assistant_node(state, model_endpoint=model_endpoint)

    return {
        **state,
        "messages": [AIMessage(content=answer)],
        "final_answer": answer,
        "current_agent": "done",
        "sub_agent_input": last_message,
        "sub_agent_output": answer,
    }


# ---------------------------------------------------------------------------
# Genie Space node (Worley ASX data)
# ---------------------------------------------------------------------------

@mlflow.trace(name="genie_space")
def genie_space_node(
    state: SupervisorState,
    model_endpoint: str | None = None,
) -> SupervisorState:
    """Call the Genie Space MCP server for financial/stock data questions.

    Falls back to the general assistant if the Genie Space fails.
    """
    _safe_update_trace(state)

    # Extract the latest user message
    last_message = ""
    for m in reversed(state["messages"]):
        if hasattr(m, "type") and m.type == "human":
            last_message = m.content
            break
        elif hasattr(m, "content"):
            last_message = m.content
            break

    t0 = _time.time()
    try:
        import asyncio
        import nest_asyncio
        from databricks.sdk import WorkspaceClient
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        nest_asyncio.apply()

        w = WorkspaceClient()
        host = w.config.host.rstrip("/")
        if host and not host.startswith("http"):
            host = f"https://{host}"
        token = w.config.authenticate().get("Authorization", "").replace("Bearer ", "")
        mcp_url = f"{host}/api/2.0/mcp/genie/{GENIE_SPACE_ID}"

        async def _call_genie(question: str) -> str:
            import json as _json
            import asyncio as _aio

            async with streamablehttp_client(
                mcp_url,
                headers={"Authorization": f"Bearer {token}"},
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools_resp = await session.list_tools()

                    # Identify query tool and poll tool
                    query_tool = None
                    poll_tool = None
                    for t in tools_resp.tools:
                        if t.name.startswith("poll_response"):
                            poll_tool = t.name
                        else:
                            query_tool = t.name

                    # Submit the question
                    response = await session.call_tool(query_tool, {"query": question})
                    result_text = "".join([c.text for c in response.content])

                    try:
                        result = _json.loads(result_text)
                    except _json.JSONDecodeError:
                        return result_text

                    conv_id = result.get("conversationId", "")
                    msg_id = result.get("messageId", "")

                    if not poll_tool or not conv_id:
                        texts = result.get("content", {}).get("textAttachments", [])
                        return "\n\n".join(texts) if texts else result_text

                    # Poll until completed (max 45 attempts, ~90s)
                    for _ in range(45):
                        await _aio.sleep(2)
                        poll_resp = await session.call_tool(
                            poll_tool,
                            {"conversation_id": conv_id, "message_id": msg_id},
                        )
                        poll_text = "".join([c.text for c in poll_resp.content])
                        try:
                            poll_data = _json.loads(poll_text)
                        except _json.JSONDecodeError:
                            return poll_text

                        status = poll_data.get("status", "")
                        if status == "COMPLETED":
                            texts = poll_data.get("content", {}).get("textAttachments", [])
                            return "\n\n".join(texts) if texts else poll_text
                        elif status in ("FAILED", "CANCELLED"):
                            return f"Genie query {status}"

                    return "Genie query timed out."

        answer = asyncio.run(_call_genie(last_message))

    except Exception as exc:
        import traceback
        error_detail = traceback.format_exc()
        answer = f"[Genie Space Error] {exc}\n\n{error_detail}"

    return {
        **state,
        "messages": [AIMessage(content=answer)],
        "final_answer": answer,
        "current_agent": "done",
        "sub_agent_input": last_message,
        "sub_agent_output": answer,
    }


# ---------------------------------------------------------------------------
# Conditional edge
# ---------------------------------------------------------------------------

def should_continue(state: SupervisorState) -> str:
    """Determine the next node or stop."""
    if state["current_agent"] == "done":
        return "end"
    if state["iteration_count"] >= MAX_ITERATIONS:
        return "end"
    return state["current_agent"]
