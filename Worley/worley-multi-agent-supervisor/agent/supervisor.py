"""LangGraph StateGraph definition for the Worley Supervisor Agent."""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, StateGraph

from agent.config import DEFAULT_SUPERVISOR_MODEL
from agent.nodes import (
    general_assistant_node,
    genie_space_node,
    knowledge_assistant_node,
    should_continue,
    supervisor_node,
)
from agent.state import SupervisorState


def build_supervisor_graph(model_endpoint: str | None = None):
    """Construct and compile the supervisor LangGraph.

    Args:
        model_endpoint: AI Gateway endpoint name for the LLM.
            Defaults to DEFAULT_SUPERVISOR_MODEL from config.

    Returns:
        A compiled LangGraph ready to .invoke().
    """
    endpoint = model_endpoint or DEFAULT_SUPERVISOR_MODEL

    # Bind the model endpoint into nodes that need it
    bound_supervisor = partial(supervisor_node, model_endpoint=endpoint)
    bound_assistant = partial(general_assistant_node, model_endpoint=endpoint)

    graph = StateGraph(SupervisorState)

    # Add nodes
    graph.add_node("supervisor", bound_supervisor)
    graph.add_node("general_assistant", bound_assistant)
    bound_knowledge = partial(knowledge_assistant_node, model_endpoint=endpoint)
    graph.add_node("knowledge_assistant", bound_knowledge)
    bound_genie = partial(genie_space_node, model_endpoint=endpoint)
    graph.add_node("genie_space", bound_genie)

    # Edges
    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        should_continue,
        {
            "general_assistant": "general_assistant",
            "knowledge_assistant": "knowledge_assistant",
            "genie_space": "genie_space",
            "end": END,
        },
    )
    graph.add_edge("general_assistant", END)
    graph.add_edge("knowledge_assistant", END)
    graph.add_edge("genie_space", END)

    return graph.compile()
