import os
import time
import json as json_module

from mlflow.pyfunc import ChatModel
from mlflow.types.llm import ChatChoice, ChatMessage

try:
    from mlflow.types.llm import ChatCompletionResponse as ChatResponse
except ImportError:
    from mlflow.types.llm import ChatResponse


class FoundryOtelModel(ChatModel):
    """Calls Azure AI Foundry and emits OTEL traces to Databricks.

    Environment variables (set on the serving endpoint):
        AZURE_AI_ENDPOINT: Azure AI Foundry base URL
        FOUNDRY_MODEL_NAME: Model deployment name (e.g. gpt-5.4-mini)
        AZURE_AI_API_KEY: API key for Azure AI Foundry
        DATABRICKS_HOST: Workspace URL for OTEL export
        DATABRICKS_TOKEN: PAT for OTEL export authentication
        DATABRICKS_UC_TABLE: UC table for OTEL spans
        OTEL_EXPORTER_ENDPOINT: Full OTLP endpoint URL (optional override)
        OTEL_SERVICE_NAME: Service name for OTEL resource
    """

    def load_context(self, context):
        self._initialized = False
        self.tracer = None

        azure_endpoint = os.environ.get("AZURE_AI_ENDPOINT", "")
        if not azure_endpoint:
            return

        import requests as req

        # OTEL tracing — degrades gracefully if host/token unavailable
        host = os.environ.get("DATABRICKS_HOST", "")
        if host:
            try:
                from opentelemetry import trace
                from opentelemetry.sdk.trace import TracerProvider
                from opentelemetry.sdk.trace.export import BatchSpanProcessor
                from opentelemetry.sdk.resources import Resource
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

                if not host.startswith("http"):
                    host = f"https://{host}"
                token = os.environ.get("DATABRICKS_TOKEN", "")
                uc_table = os.environ.get("DATABRICKS_UC_TABLE", "")
                otel_endpoint = os.environ.get(
                    "OTEL_EXPORTER_ENDPOINT",
                    f"{host}/api/2.0/otel/v1/traces",
                )

                exporter = OTLPSpanExporter(
                    endpoint=otel_endpoint,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Databricks-UC-Table-Name": uc_table,
                    },
                )
                resource = Resource.create({
                    "service.name": os.environ.get("OTEL_SERVICE_NAME", "worley-foundry-chat-agent"),
                    "service.namespace": "azure.ai.foundry",
                    "gen_ai.system": "azure.ai.foundry",
                    "deployment.environment": "databricks-model-serving",
                })
                provider = TracerProvider(resource=resource)
                provider.add_span_processor(BatchSpanProcessor(exporter))
                trace.set_tracer_provider(provider)
                self.tracer = trace.get_tracer("azure.ai.foundry.agent")
            except Exception:
                self.tracer = None

        # Azure AI Foundry config
        azure_endpoint = azure_endpoint.rstrip("/")
        self.model_name = os.environ.get("FOUNDRY_MODEL_NAME", "gpt-5.4-mini")
        self.foundry_url = f"{azure_endpoint}/openai/deployments/{self.model_name}/chat/completions?api-version=2024-10-21"
        self.foundry_headers = {
            "api-key": os.environ.get("AZURE_AI_API_KEY", ""),
            "Content-Type": "application/json",
        }
        self._requests = req
        self._initialized = True

    def predict(self, context, messages: list[ChatMessage], params=None) -> ChatResponse:
        if not self._initialized:
            return ChatResponse(
                choices=[
                    ChatChoice(
                        index=0,
                        message=ChatMessage(role="assistant", content="Model not initialized."),
                    )
                ],
            )

        msg_dicts = [{"role": m.role, "content": m.content} for m in messages]

        def _call_foundry(span=None):
            if span:
                span.set_attribute("gen_ai.system", "azure.ai.foundry")
                span.set_attribute("gen_ai.request.model", self.model_name)
                span.set_attribute("gen_ai.operation.name", "chat")
                span.set_attribute("foundry.agent.name", "azure-foundry-otel-agent")
                span.set_attribute("gen_ai.input.messages", json_module.dumps(msg_dicts))

            start = time.time()
            resp = self._requests.post(
                self.foundry_url,
                headers=self.foundry_headers,
                json={"messages": msg_dicts},
            )
            latency = time.time() - start
            data = resp.json()

            if "choices" not in data:
                raise RuntimeError(
                    f"Azure AI Foundry error (HTTP {resp.status_code}): {json_module.dumps(data)[:500]}"
                )

            answer = data["choices"][0]["message"]["content"]

            if span:
                span.set_attribute("gen_ai.response.finish_reason", data["choices"][0]["finish_reason"])
                span.set_attribute("foundry.latency_seconds", round(latency, 3))
                span.set_attribute("gen_ai.output.messages", json_module.dumps(
                    [{"role": "assistant", "content": answer}]
                ))
                usage = data.get("usage", {})
                if usage:
                    span.set_attribute("gen_ai.usage.input_tokens", usage.get("prompt_tokens", 0))
                    span.set_attribute("gen_ai.usage.output_tokens", usage.get("completion_tokens", 0))

            return answer

        if self.tracer:
            with self.tracer.start_as_current_span("foundry_agent.chat") as span:
                answer = _call_foundry(span)
        else:
            answer = _call_foundry()

        return ChatResponse(
            choices=[
                ChatChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=answer),
                )
            ],
        )


# Models from Code: MLflow loads this class from source at serving time
import mlflow
mlflow.models.set_model(FoundryOtelModel())
