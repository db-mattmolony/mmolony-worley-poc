# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy Worley Supervisor Agent via MLflow
# MAGIC
# MAGIC Logs the LangGraph supervisor agent as an MLflow pyfunc model,
# MAGIC registers it in Unity Catalog, and creates a Model Serving endpoint.

# COMMAND ----------

# MAGIC %pip install langchain langchain-core langchain-community databricks-langchain langgraph "mlflow[databricks]" databricks-sdk databricks-agents openai requests opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc -q
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import os
import mlflow

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment("/Shared/worley-supervisor-agent")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration
# MAGIC
# MAGIC All workspace-specific values are configurable via environment variables
# MAGIC or widget parameters, with sensible defaults.

# COMMAND ----------

UC_MODEL_NAME = os.environ.get("SUPERVISOR_UC_MODEL", "az_databricks_poc.multi_agent_supervisor.worley_supervisor_agent")
SECRET_SCOPE = os.environ.get("SUPERVISOR_SECRET_SCOPE", "praju-foundry-keys")
SERVING_PROXY_MODEL = os.environ.get("SUPERVISOR_SERVING_MODEL", "foundry-gpt-5-4-mini")
ENDPOINT_NAME = os.environ.get("SUPERVISOR_ENDPOINT_NAME", "worley-supervisor-agent")

# Set SUPERVISOR_MODEL so any model validation during log_model uses the
# workspace serving proxy — NOT the AI Gateway (which requires a different token).
os.environ["SUPERVISOR_MODEL"] = SERVING_PROXY_MODEL

print(f"UC Model:       {UC_MODEL_NAME}")
print(f"Secret Scope:   {SECRET_SCOPE}")
print(f"Serving Model:  {SERVING_PROXY_MODEL}")
print(f"Endpoint Name:  {ENDPOINT_NAME}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Log and Register Model
# MAGIC
# MAGIC Uses `code_paths` to bundle the `agent/` package so the real
# MAGIC `SupervisorAgent` class (with full OTEL instrumentation) is deployed.

# COMMAND ----------

import sys

# Ensure the agent package is importable
# In Databricks notebooks the cwd is the notebook's directory (setup/),
# so we go up one level to reach the project root where agent/ lives.
project_root = os.environ.get("DATABRICKS_BUNDLE_WORKING_DIRECTORY", "")
if not project_root:
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        # Databricks notebook — cwd is the notebook's directory
        project_root = os.path.dirname(os.getcwd())

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from agent.mlflow_model import SupervisorAgent
from agent.config import KA_ENDPOINT_NAME, GENIE_SPACE_ID
from mlflow.models.resources import (
    DatabricksServingEndpoint,
    DatabricksGenieSpace,
    DatabricksSQLWarehouse,
    DatabricksTable,
)

# Declare all resources the agent calls at runtime.
# This enables automatic credential passthrough — no PAT needed.
resources = [
    DatabricksServingEndpoint(endpoint_name=SERVING_PROXY_MODEL),
    DatabricksServingEndpoint(endpoint_name=KA_ENDPOINT_NAME),
    DatabricksServingEndpoint(endpoint_name="azure-foundry-otel"),
    DatabricksGenieSpace(genie_space_id=GENIE_SPACE_ID),
    DatabricksSQLWarehouse(warehouse_id="fa19907118a9f3ac"),
    DatabricksTable(table_name="az_databricks_poc.agent_monitor.wor_ax_stock_prices_5yr"),
]

pip_requirements = [
    "langchain>=0.3.0",
    "langgraph>=0.2.0",
    "langchain-core>=0.3.0",
    "langchain-community>=0.3.0",
    "databricks-langchain",
    "mcp>=1.0.0",
    "nest-asyncio",
    "mlflow>=3.0.0",
    "databricks-sdk>=0.30.0",
    "openai>=1.50.0",
    "requests>=2.31.0",
]

# ChatModel infers its own chat-completions-compatible signature automatically
with mlflow.start_run(run_name="supervisor-agent-v1") as run:
    model_info = mlflow.pyfunc.log_model(
        artifact_path="supervisor",
        python_model=SupervisorAgent(),
        code_paths=[os.path.join(project_root, "agent")],
        pip_requirements=pip_requirements,
        registered_model_name=UC_MODEL_NAME,
        resources=resources,
    )
    print(f"Model logged: {model_info.model_uri}")
    print(f"Registered to: {UC_MODEL_NAME}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Model Serving Endpoint

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import EndpointTag, AiGatewayInferenceTableConfig
from databricks import agents

w = WorkspaceClient()

# Get the model version — registered_model_version may be None if registration was async
if hasattr(model_info, "registered_model_version") and model_info.registered_model_version:
    model_version = model_info.registered_model_version
else:
    # Fallback: list versions and pick the latest
    versions = w.model_versions.list(full_name=UC_MODEL_NAME)
    model_version = max(v.version for v in versions)
print(f"Using model version: {model_version}")

# Wait for any in-progress endpoint updates to finish before deploying
import time
try:
    for _i in range(60):
        ep = w.serving_endpoints.get(ENDPOINT_NAME)
        update_state = str(ep.state.config_update)
        # Enum str is "EndpointStateConfigUpdate.NOT_UPDATING" — check with 'in'
        if "NOT_UPDATING" in update_state or "UPDATE_FAILED" in update_state:
            break
        print(f"  Endpoint updating, waiting... ({update_state})")
        time.sleep(15)
except Exception:
    pass  # Endpoint may not exist yet

# Deploy using databricks-agents SDK — this automatically wires up
# MLflow trace logging, inference tables, and a review app.
deployment = agents.deploy(
    UC_MODEL_NAME,
    str(model_version),
    endpoint_name=ENDPOINT_NAME,
    tags={"poc_id": "UC2"},
    workload_size="Small",
)
print(f"Deployed to endpoint: {deployment.endpoint_name}")

# Ensure tags are set via SDK as well (agents.deploy tags are metadata tags)
endpoint_tags = [EndpointTag(key="poc_id", value="UC2")]
w.serving_endpoints.patch(ENDPOINT_NAME, add_tags=endpoint_tags)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Enable Inference Table
# MAGIC This is separate from deployment so a failure here does not block the endpoint update.

# COMMAND ----------

try:
    inference_table_config = AiGatewayInferenceTableConfig(
        catalog_name="az_databricks_poc",
        schema_name="multi_agent_supervisor",
        table_name_prefix="worley_supervisor_agent",
        enabled=True,
    )
    w.serving_endpoints.put_ai_gateway(ENDPOINT_NAME, inference_table_config=inference_table_config)
    print(f"Inference table enabled in az_databricks_poc.multi_agent_supervisor")
except Exception as e:
    print(f"Warning: Could not enable inference table (non-blocking): {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Deployment Complete
# MAGIC Endpoint update has been triggered. It will be ready in ~10 minutes.

# COMMAND ----------

print(f"Deployment triggered for {ENDPOINT_NAME} with model version {model_version}.")
print("The endpoint will update in the background — no need to wait.")
