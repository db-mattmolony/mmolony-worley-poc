"""Deploy the Foundry OTEL model as a Databricks Model Serving endpoint."""

import base64
import json
import os
import subprocess
import sys
import time


def env():
    vals = {}
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
    return vals


def api(method, path, data=None):
    cfg = env()
    host = cfg["DATABRICKS_HOST"].rstrip("/")
    token = cfg["DATABRICKS_TOKEN"]
    cmd = ["curl", "-s", "-X", method, f"{host}{path}",
           "-H", f"Authorization: Bearer {token}",
           "-H", "Content-Type: application/json"]
    if data:
        cmd.extend(["-d", json.dumps(data)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout) if result.stdout else {}


def main():
    cfg = env()
    workspace_path = "/Users/_matthew.moloney@worley.com/azure-foundry-otel-model"

    print("=== Upload model files ===")
    subprocess.run(["databricks", "workspace", "mkdirs", workspace_path, "--profile", "worley-dev"], capture_output=True)
    model_dir = os.path.dirname(os.path.abspath(__file__))
    for f in ["model.py", "requirements.txt"]:
        subprocess.run(["databricks", "workspace", "import", os.path.join(model_dir, f),
                        f"{workspace_path}/{f}", "--profile", "worley-dev", "--overwrite"], capture_output=True)
        print(f"  Uploaded {f}")

    print("\n=== Log model via notebook ===")
    with open(os.path.join(model_dir, "model.py")) as f:
        model_source = f.read()

    notebook_content = f'''# Databricks notebook source
# COMMAND ----------
%pip install openai opentelemetry-sdk opentelemetry-api opentelemetry-exporter-otlp-proto-http requests --quiet
dbutils.library.restartPython()

# COMMAND ----------
import mlflow
import mlflow.pyfunc
from mlflow.models.signature import ModelSignature
from mlflow.types.schema import ColSpec, Schema

# --- Inline model class ---
{model_source}
# --- End model class ---

mlflow.set_tracking_uri("databricks")
model_name = "az_databricks_poc.azure_foundry_otel.foundry_otel_model"
signature = ModelSignature(
    inputs=Schema([ColSpec("string", "messages")]),
    outputs=Schema([ColSpec("string", "response")]),
)

with mlflow.start_run(run_name="deploy-foundry-otel") as run:
    mlflow.pyfunc.log_model(
        artifact_path="model",
        python_model=FoundryOtelModel(),
        pip_requirements=["requests", "opentelemetry-sdk", "opentelemetry-api", "opentelemetry-exporter-otlp-proto-http"],
        registered_model_name=model_name,
        signature=signature,
    )
    print(f"Model logged: {{run.info.run_id}}")
    print(f"Registered as: {{model_name}}")
'''

    nb_path = f"{workspace_path}/log_model"
    nb_b64 = base64.b64encode(notebook_content.encode()).decode()
    api("POST", "/api/2.0/workspace/import", {
        "path": nb_path, "format": "SOURCE", "language": "PYTHON",
        "content": nb_b64, "overwrite": True,
    })

    print("  Running notebook...")
    run_result = api("POST", "/api/2.1/jobs/runs/submit", {
        "run_name": "log-foundry-otel-model",
        "tasks": [{"task_key": "log_model", "notebook_task": {"notebook_path": nb_path},
                    "new_cluster": {"spark_version": "15.4.x-scala2.12", "num_workers": 0, "node_type_id": "Standard_D4ds_v5"}}],
    })
    run_id = run_result.get("run_id")
    if not run_id:
        print(f"  ERROR: {run_result}")
        sys.exit(1)

    while True:
        time.sleep(10)
        print(".", end="", flush=True)
        status = api("GET", f"/api/2.1/jobs/runs/get?run_id={run_id}")
        state = status.get("state", {}).get("life_cycle_state", "")
        if state in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            result_state = status.get("state", {}).get("result_state", "")
            print(f" {result_state}")
            if result_state != "SUCCESS":
                task_run = status.get("tasks", [{}])[0].get("run_id", "")
                out = api("GET", f"/api/2.1/jobs/runs/get-output?run_id={task_run}")
                print(f"  ERROR: {out.get('error', '')[:500]}")
                sys.exit(1)
            break

    print("\n=== Update serving endpoint ===")
    versions = api("GET", "/api/2.1/unity-catalog/models/az_databricks_poc.azure_foundry_otel.foundry_otel_model/versions")
    latest = max(versions.get("model_versions", []), key=lambda v: int(v["version"]))
    version = latest["version"]
    print(f"  Model version: {version}")

    API_KEY = "<YOUR_AZURE_AI_API_KEY>"
    result = api("PUT", "/api/2.0/serving-endpoints/azure-foundry-otel/config", {
        "served_entities": [{
            "entity_name": "az_databricks_poc.azure_foundry_otel.foundry_otel_model",
            "entity_version": version,
            "workload_size": "Small",
            "scale_to_zero_enabled": True,
            "environment_vars": {
                "AZURE_AI_ENDPOINT": "https://ai-unifiedaiplateform-poc.services.ai.azure.com",
                "FOUNDRY_MODEL_NAME": cfg.get("FOUNDRY_MODEL_NAME", "gpt-5.4"),
                "DATABRICKS_HOST": cfg["DATABRICKS_HOST"],
                "DATABRICKS_TOKEN": cfg["DATABRICKS_TOKEN"],
                "DATABRICKS_UC_TABLE": "az_databricks_poc.multi_agent_supervisor.foundry_otel_spans",
                "OTEL_SERVICE_NAME": "worley-foundry-chat-agent",
                "AZURE_AI_API_KEY": API_KEY,
            },
        }],
    })
    if "error_code" in result:
        print(f"  ERROR: {result}")
    else:
        print(f"  Endpoint updated to v{version}!")

    print("\nDone! Wait for the endpoint to redeploy (~5-10 min).")


if __name__ == "__main__":
    main()
