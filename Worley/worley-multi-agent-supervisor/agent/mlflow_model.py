"""MLflow ChatModel wrapper for deploying the supervisor agent to Model Serving.

Using ChatModel (instead of PythonModel) exposes a standard chat completions
interface, making the endpoint compatible with the Databricks AI Playground
and any OpenAI-compatible client.
"""

import uuid
from typing import Generator

from mlflow.pyfunc import ChatModel
from mlflow.types.llm import ChatChoice, ChatMessage, ChatChunkChoice, ChatChoiceDelta

# ChatResponse was renamed to ChatCompletionResponse in MLflow 2.18
try:
    from mlflow.types.llm import ChatCompletionResponse as ChatResponse
except ImportError:
    from mlflow.types.llm import ChatResponse

try:
    from mlflow.types.llm import ChatCompletionChunk
except ImportError:
    ChatCompletionChunk = None


class SupervisorAgent(ChatModel):
    """Wraps the LangGraph supervisor as an MLflow ChatModel."""

    def load_context(self, context):
        import mlflow

        from agent.supervisor import build_supervisor_graph

        # Trace routing is handled by the MLFLOW_EXPERIMENT_ID env var set on
        # the serving endpoint — no need to call set_destination() here.
        # Calling it spawns a local SQLite tracking store that corrupts when
        # multiple gunicorn workers race on it.
        mlflow.langchain.autolog(log_traces=True)
        self.graph = build_supervisor_graph()

    def predict(self, context, messages: list[ChatMessage], params=None) -> ChatResponse:
        from langchain_core.messages import AIMessage, HumanMessage

        trace_id = str(uuid.uuid4())
        authenticated_user = "serving-user"

        # Convert ChatMessage objects to LangChain messages
        lc_messages = []
        for m in messages:
            if m.role == "user":
                lc_messages.append(HumanMessage(content=m.content))
            else:
                lc_messages.append(AIMessage(content=m.content))

        result = self.graph.invoke(
            {
                "messages": lc_messages,
                "trace_id": trace_id,
                "authenticated_user": authenticated_user,
                "current_agent": "",
                "iteration_count": 0,
                "final_answer": "",
                "routed_agent": "",
                "sub_agent_input": "",
                "sub_agent_output": "",
            }
        )

        return ChatResponse(
            choices=[
                ChatChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=result["final_answer"]),
                )
            ],
            custom_outputs={
                "routed_agent": result.get("routed_agent", "unknown"),
                "sub_agent_input": result.get("sub_agent_input", ""),
                "sub_agent_output": result.get("sub_agent_output", ""),
            },
        )

    def predict_stream(self, context, messages: list[ChatMessage], params=None) -> Generator:
        """Streaming prediction — runs predict() then yields the result as chunks."""
        response = self.predict(context, messages, params)
        content = response.choices[0].message.content

        if ChatCompletionChunk is not None:
            yield ChatCompletionChunk(
                choices=[
                    ChatChunkChoice(
                        index=0,
                        delta=ChatChoiceDelta(role="assistant", content=content),
                    )
                ],
            )
        else:
            yield response
