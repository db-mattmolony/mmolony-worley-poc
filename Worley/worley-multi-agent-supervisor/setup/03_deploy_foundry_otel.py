# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy Azure AI Foundry OTEL Agent
# MAGIC
# MAGIC Logs the Foundry OTEL ChatModel to Unity Catalog and creates/updates
# MAGIC a Model Serving endpoint (`azure-foundry-otel`) that calls Azure AI Foundry
# MAGIC with OpenTelemetry tracing exported to Databricks.

# COMMAND ----------

# MAGIC %pip install "mlflow[databricks]" opentelemetry-sdk opentelemetry-api opentelemetry-exporter-otlp-proto-http -q
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import os
import sys
import time

import mlflow

mlflow.set_registry_uri("databricks-uc")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

UC_MODEL_NAME = os.environ.get("FOUNDRY_UC_MODEL", "az_databricks_poc.azure_foundry_otel.foundry_otel_model")
ENDPOINT_NAME = os.environ.get("FOUNDRY_ENDPOINT_NAME", "azure-foundry-otel")

# Azure AI Foundry settings — same Azure resource as the AI Gateway endpoints
AZURE_AI_ENDPOINT = "https://praju.openai.azure.com"
FOUNDRY_MODEL_NAME = os.environ.get("FOUNDRY_MODEL_NAME", "gpt-5.4-mini")
OTEL_UC_TABLE = "az_databricks_poc.multi_agent_supervisor.foundry_otel_spans"
OTEL_SERVICE_NAME = "worley-foundry-chat-agent"

# Secret scope for API keys
SECRET_SCOPE = os.environ.get("FOUNDRY_SECRET_SCOPE", "praju-foundry-keys")

print(f"UC Model:        {UC_MODEL_NAME}")
print(f"Endpoint Name:   {ENDPOINT_NAME}")
print(f"Foundry Model:   {FOUNDRY_MODEL_NAME}")
print(f"OTEL UC Table:   {OTEL_UC_TABLE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Schema

# COMMAND ----------

spark.sql("CREATE SCHEMA IF NOT EXISTS az_databricks_poc.azure_foundry_otel")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Log and Register Model

# COMMAND ----------

# Ensure the model code is importable
project_root = os.environ.get("DATABRICKS_BUNDLE_WORKING_DIRECTORY", "")
if not project_root:
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        project_root = os.path.dirname(os.getcwd())

if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Models from Code: pass the file path, not an instance.
# MLflow will load the class from source at serving time (no cloudpickle).
model_code_path = os.path.join(project_root, "azure-foundry-model", "foundry_otel_model.py")

with mlflow.start_run(run_name="deploy-foundry-otel") as run:
    model_info = mlflow.pyfunc.log_model(
        artifact_path="model",
        python_model=model_code_path,
        pip_requirements=[
            "requests",
            "opentelemetry-sdk",
            "opentelemetry-api",
            "opentelemetry-exporter-otlp-proto-http",
        ],
        registered_model_name=UC_MODEL_NAME,
    )
    print(f"Model logged: {model_info.model_uri}")
    print(f"Registered to: {UC_MODEL_NAME}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create/Update Serving Endpoint

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    EndpointTag,
    ServedEntityInput,
)

w = WorkspaceClient()

# Get latest model version
if hasattr(model_info, "registered_model_version") and model_info.registered_model_version:
    model_version = model_info.registered_model_version
else:
    versions = w.model_versions.list(full_name=UC_MODEL_NAME)
    model_version = max(v.version for v in versions)
print(f"Using model version: {model_version}")

# Wait for any in-progress endpoint updates
try:
    for _i in range(60):
        ep = w.serving_endpoints.get(ENDPOINT_NAME)
        update_state = str(ep.state.config_update)
        if "NOT_UPDATING" in update_state or "UPDATE_FAILED" in update_state:
            break
        print(f"  Endpoint updating, waiting... ({update_state})")
        time.sleep(15)
except Exception:
    pass  # Endpoint may not exist yet

served_entity = ServedEntityInput(
    entity_name=UC_MODEL_NAME,
    entity_version=str(model_version),
    workload_size="Small",
    scale_to_zero_enabled=True,
    environment_vars={
        "AZURE_AI_ENDPOINT": AZURE_AI_ENDPOINT,
        "FOUNDRY_MODEL_NAME": FOUNDRY_MODEL_NAME,
        "DATABRICKS_UC_TABLE": OTEL_UC_TABLE,
        "OTEL_SERVICE_NAME": OTEL_SERVICE_NAME,
        "AZURE_AI_API_KEY": f"{{{{secrets/{SECRET_SCOPE}/gpt-5-4-mini-key}}}}",
        "DATABRICKS_HOST": w.config.host,
        "DATABRICKS_TOKEN": f"{{{{secrets/{SECRET_SCOPE}/databricks-pat}}}}",
        "OTEL_EXPORTER_ENDPOINT": f"{w.config.host.rstrip('/')}/api/2.0/otel/v1/traces",
    },
)

config = EndpointCoreConfigInput(name=ENDPOINT_NAME, served_entities=[served_entity])

endpoint_exists = False
try:
    w.serving_endpoints.get(ENDPOINT_NAME)
    endpoint_exists = True
except Exception:
    pass

if endpoint_exists:
    try:
        w.serving_endpoints.update_config(ENDPOINT_NAME, served_entities=[served_entity])
        print(f"Updated endpoint: {ENDPOINT_NAME}")
    except Exception as e:
        if "non-agent" in str(e) or "vice-versa" in str(e):
            # Model type changed (e.g. PythonModel → ChatModel) — must recreate
            print(f"  Model type changed, deleting and recreating endpoint...")
            w.serving_endpoints.delete(ENDPOINT_NAME)
            import time as _time
            _time.sleep(10)
            w.serving_endpoints.create(name=ENDPOINT_NAME, config=config)
            print(f"Recreated endpoint: {ENDPOINT_NAME}")
        else:
            raise
else:
    w.serving_endpoints.create(name=ENDPOINT_NAME, config=config)
    print(f"Created endpoint: {ENDPOINT_NAME}")

# Tag the endpoint with UC2
endpoint_tags = [EndpointTag(key="poc_id", value="UC2")]
w.serving_endpoints.patch(ENDPOINT_NAME, add_tags=endpoint_tags)
print(f"Tagged {ENDPOINT_NAME} with poc_id=UC2")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Wait for Endpoint to be Ready
# MAGIC The supervisor agent deployment depends on this endpoint being queryable.

# COMMAND ----------

print(f"Waiting for {ENDPOINT_NAME} to become ready...")
for _i in range(60):
    try:
        ep = w.serving_endpoints.get(ENDPOINT_NAME)
        state = ep.state
        config_state = str(state.config_update) if state.config_update else ""
        ready_state = str(state.ready) if state.ready else ""
        if "READY" in ready_state and "NOT_UPDATING" in config_state:
            print(f"Endpoint {ENDPOINT_NAME} is READY.")
            break
        print(f"  State: ready={ready_state}, config={config_state} — waiting...")
    except Exception as e:
        print(f"  Error checking state: {e} — waiting...")
    time.sleep(15)
else:
    print(f"WARNING: Timed out waiting for {ENDPOINT_NAME} to become ready.")
