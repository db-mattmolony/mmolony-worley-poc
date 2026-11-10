"""LangGraph state schema for the Worley Supervisor Agent."""

from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class SupervisorState(TypedDict):
    """State carried through every node in the supervisor graph."""

    # Chat messages (LangGraph's add_messages reducer appends automatically)
    messages: Annotated[list[BaseMessage], add_messages]

    # Unique ID for this user interaction – propagated into every MLflow span
    trace_id: str

    # Email of the authenticated Databricks App user
    authenticated_user: str

    # Which sub-agent is currently active
    current_agent: str

    # Guard against runaway loops
    iteration_count: int

    # The final synthesised response to return to the user
    final_answer: str

    # Routing visibility — preserved for custom_outputs
    routed_agent: str
    sub_agent_input: str
    sub_agent_output: str
