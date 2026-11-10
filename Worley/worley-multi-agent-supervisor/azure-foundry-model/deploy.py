"""Deploy the Foundry OTEL model as a Databricks Model Serving endpoint.

Runs entirely via REST API -- no local pip installs needed.
Requires: DATABRICKS_HOST and DATABRICKS_TOKEN in .env
"""

import json
import os
import subprocess
import sys
import time


def env():
    """Load .env file into dict."""
    vals = {}
    with open(os.path.join(os.path.dirname(__file__), ".env")) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
    return vals


def api(method, path, data=None):
    """Call Databricks REST API."""
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


def sql(statement):
    """Execute SQL via Databricks API."""
    # Find a SQL warehouse
    warehouses = api("GET", "/api/2.0/sql/warehouses").get("warehouses", [])
    if not warehouses:
        print("ERROR: No SQL warehouse found")
        sys.exit(1)
    wh_id = warehouses[0]["id"]

    result = api("POST", "/api/2.0/sql/statements", {
        "statement": statement,
        "warehouse_id": wh_id,
        "wait_timeout": "30s",
    })
    state = result.get("status", {}).get("state", "")
    if state == "FAILED":
        print(f"SQL ERROR: {result['status']['error']['message']}")
    else:
        print(f"SQL OK: {statement[:80]}...")
    return result


def main():
    cfg = env()
    print("=== Step 1: Create UC schema ===")
    sql("CREATE SCHEMA IF NOT EXISTS az_databricks_poc.azure_foundry_otel")

    print("\n=== Step 2: Upload model files ===")
    # Upload model.py to workspace
    host = cfg["DATABRICKS_HOST"].rstrip("/")
    token = cfg["DATABRICKS_TOKEN"]
    workspace_path = "/Users/_matthew.moloney@worley.com/azure-foundry-otel-model"

    subprocess.run([
        "databricks", "workspace", "mkdirs", workspace_path,
        "--profile", "worley-dev"
    ], capture_output=True)

    model_dir = os.path.dirname(os.path.abspath(__file__))
    for f in ["model.py", "requirements.txt"]:
        filepath = os.path.join(model_dir, f)
        subprocess.run([
            "databricks", "workspace", "import", filepath,
            f"{workspace_path}/{f}",
            "--profile", "worley-dev", "--overwrite"
        ], capture_output=True)
        print(f"  Uploaded {f}")

    print("\n=== Step 3: Create serving endpoint ===")
    endpoint_name = "azure-foundry-otel"

    # Check if endpoint exists
    existing = api("GET", f"/api/2.0/serving-endpoints/{endpoint_name}")
    if "name" in existing:
        print(f"  Endpoint '{endpoint_name}' already exists, updating...")

    # For a custom model serving endpoint, we need to log the model first
    # via a notebook or API. Let's use the jobs API to run a quick notebook.

    # Read model.py source to embed in the notebook
    model_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(model_dir, "model.py")) as f:
        model_source = f.read()

    notebook_content = f'''# Databricks notebook source
# COMMAND ----------
%pip install openai opentelemetry-sdk opentelemetry-api opentelemetry-exporter-otlp-proto-http
dbutils.library.restartPython()

# COMMAND ----------
import mlflow
import mlflow.pyfunc

# --- Inline model class (from model.py) ---
{model_source}
# --- End model class ---

mlflow.set_tracking_uri("databricks")

catalog = "az_databricks_poc"
schema = "azure_foundry_otel"
model_name = f"{{catalog}}.{{schema}}.foundry_otel_model"

# ChatModel infers its own chat completions signature automatically
with mlflow.start_run(run_name="deploy-foundry-otel") as run:
    mlflow.pyfunc.log_model(
        artifact_path="model",
        python_model=FoundryOtelModel(),
        pip_requirements=["openai", "opentelemetry-sdk", "opentelemetry-api", "opentelemetry-exporter-otlp-proto-http"],
        registered_model_name=model_name,
    )
    print(f"Model logged: {{run.info.run_id}}")
    print(f"Registered as: {{model_name}}")
'''
    # Upload notebook
    import base64
    nb_path = f"{workspace_path}/log_model"
    nb_b64 = base64.b64encode(notebook_content.encode()).decode()
    api("POST", "/api/2.0/workspace/import", {
        "path": nb_path,
        "format": "SOURCE",
        "language": "PYTHON",
        "content": nb_b64,
        "overwrite": True,
    })
    print("  Uploaded log_model notebook")

    # Run the notebook
    print("  Running notebook to log model...")
    run_result = api("POST", "/api/2.1/jobs/runs/submit", {
        "run_name": "log-foundry-otel-model",
        "tasks": [{
            "task_key": "log_model",
            "notebook_task": {"notebook_path": nb_path},
            "new_cluster": {
                "spark_version": "15.4.x-scala2.12",
                "num_workers": 0,
                "node_type_id": "Standard_D4ds_v5",
            },
        }],
    })
    run_id = run_result.get("run_id")
    if not run_id:
        print(f"  ERROR: {run_result}")
        sys.exit(1)
    print(f"  Job run ID: {run_id}")

    # Wait for completion
    print("  Waiting for model to be logged...", end="", flush=True)
    while True:
        time.sleep(10)
        print(".", end="", flush=True)
        status = api("GET", f"/api/2.1/jobs/runs/get?run_id={run_id}")
        state = status.get("state", {}).get("life_cycle_state", "")
        if state in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            result_state = status.get("state", {}).get("result_state", "")
            print(f" {result_state}")
            if result_state != "SUCCESS":
                print(f"  ERROR: {status.get('state', {}).get('state_message', '')}")
                sys.exit(1)
            break

    print("\n=== Step 4: Create serving endpoint ===")
    # Get latest model version
    model_name = "az_databricks_poc.azure_foundry_otel.foundry_otel_model"
    versions = api("GET", f"/api/2.1/unity-catalog/models/{model_name}/versions")
    latest = max(versions.get("model_versions", []), key=lambda v: int(v["version"]))
    version = latest["version"]
    print(f"  Latest model version: {version}")

    endpoint_config = {
        "name": endpoint_name,
        "config": {
            "served_entities": [{
                "entity_name": model_name,
                "entity_version": version,
                "workload_size": "Small",
                "scale_to_zero_enabled": True,
                "environment_vars": {
                    "AZURE_AI_ENDPOINT": "https://ai-unifiedaiplateform-poc.services.ai.azure.com",
                    "FOUNDRY_MODEL_NAME": cfg.get("FOUNDRY_MODEL_NAME", "gpt-5.4"),
                    "DATABRICKS_HOST": cfg["DATABRICKS_HOST"],
                    "DATABRICKS_TOKEN": cfg["DATABRICKS_TOKEN"],
                    "DATABRICKS_UC_TABLE": "az_databricks_poc.azure_foundry_otel.otel_spans",
                    "OTEL_SERVICE_NAME": "worley-foundry-chat-agent",
                    "AZURE_AI_API_KEY": cfg.get("AZURE_AI_API_KEY", "placeholder"),
                },
            }],
        },
    }

    if "name" in existing:
        result = api("PUT", f"/api/2.0/serving-endpoints/{endpoint_name}/config",
                      endpoint_config["config"])
    else:
        result = api("POST", "/api/2.0/serving-endpoints", endpoint_config)

    if "error_code" in result:
        print(f"  ERROR: {result}")
    else:
        print(f"  Endpoint '{endpoint_name}' created/updated!")
        print(f"  URL: {cfg['DATABRICKS_HOST']}/serving-endpoints/{endpoint_name}/invocations")

    print("\nDone! Endpoint may take a few minutes to become ready.")


if __name__ == "__main__":
    main()
