import os
import time
import json as json_module

import mlflow.pyfunc


class FoundryOtelModel(mlflow.pyfunc.PythonModel):
    """Calls Azure AI Foundry and emits OTEL traces to Databricks."""

    def load_context(self, context):
        import requests as req
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        host = os.environ.get("DATABRICKS_HOST", "")
        if host and not host.startswith("http"):
            host = f"https://{host}"
        token = os.environ.get("DATABRICKS_TOKEN", "")
        uc_table = os.environ.get("DATABRICKS_UC_TABLE", "")

        # OTEL exporter → Databricks OTLP endpoint
        exporter = OTLPSpanExporter(
            endpoint=f"{host}/api/2.0/otel/v1/traces",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Databricks-UC-Table-Name": uc_table,
            },
        )
        resource = Resource.create({
            "service.name": os.environ.get("OTEL_SERVICE_NAME", "worley-foundry-chat-agent"),
            "service.namespace": "azure-ai-foundry",
            "gen_ai.system": "azure.ai.foundry",
            "deployment.environment": "databricks-model-serving",
        })
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        self.tracer = trace.get_tracer("azure.ai.foundry.agent")

        # Azure AI Foundry config
        azure_endpoint = os.environ.get("AZURE_AI_ENDPOINT", "").rstrip("/")
        self.model_name = os.environ.get("FOUNDRY_MODEL_NAME", "gpt-5.4")
        self.foundry_url = f"{azure_endpoint}/openai/deployments/{self.model_name}/chat/completions?api-version=2024-10-21"
        self.foundry_headers = {
            "api-key": os.environ.get("AZURE_AI_API_KEY", ""),
            "Content-Type": "application/json",
        }
        self._requests = req

    def predict(self, context, model_input, params=None):
        import pandas as pd
        if isinstance(model_input, pd.DataFrame):
            raw = model_input["messages"].iloc[0]
        elif isinstance(model_input, dict):
            raw = model_input.get("messages", '[{"role": "user", "content": "Hello"}]')
        else:
            raw = str(model_input)

        messages = json_module.loads(raw) if isinstance(raw, str) else raw

        with self.tracer.start_as_current_span("foundry_agent.chat") as span:
            span.set_attribute("gen_ai.system", "azure.ai.foundry")
            span.set_attribute("gen_ai.request.model", self.model_name)
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("foundry.agent.name", "azure-foundry-otel-agent")
            span.set_attribute("gen_ai.input.messages", json_module.dumps(messages))

            start = time.time()
            resp = self._requests.post(
                self.foundry_url,
                headers=self.foundry_headers,
                json={"messages": messages},
            )
            latency = time.time() - start
            data = resp.json()

            answer = data["choices"][0]["message"]["content"]
            span.set_attribute("gen_ai.response.finish_reason", data["choices"][0]["finish_reason"])
            span.set_attribute("foundry.latency_seconds", round(latency, 3))
            span.set_attribute("gen_ai.output.messages", json_module.dumps(
                [{"role": "assistant", "content": answer}]
            ))

            usage = data.get("usage", {})
            if usage:
                span.set_attribute("gen_ai.usage.input_tokens", usage.get("prompt_tokens", 0))
                span.set_attribute("gen_ai.usage.output_tokens", usage.get("completion_tokens", 0))

            return {"response": answer}
