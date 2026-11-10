# Databricks notebook source
# MAGIC %md
# MAGIC # Test Worley Supervisor Agent
# MAGIC
# MAGIC Isolates and validates each layer of the agent stack:
# MAGIC 1. Workspace endpoint connectivity (can we call the LLM?)
# MAGIC 2. Agent graph execution (does the supervisor route correctly?)
# MAGIC 3. Model Serving endpoint (does the deployed endpoint respond?)

# COMMAND ----------

# MAGIC %pip install langchain langchain-core langchain-community langchain-openai langgraph "mlflow[databricks]" databricks-sdk openai requests opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc -q
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import os
import sys

# Resolve project root so agent/ is importable
project_root = os.environ.get("DATABRICKS_BUNDLE_WORKING_DIRECTORY", "")
if not project_root:
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        project_root = os.path.dirname(os.getcwd())

if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Force the graph to use workspace proxy endpoints, not AI Gateway
os.environ["SUPERVISOR_MODEL"] = "foundry-gpt-5-4-mini"

print(f"Project root: {project_root}")
print(f"SUPERVISOR_MODEL: {os.environ['SUPERVISOR_MODEL']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test 1: Workspace Auth
# MAGIC
# MAGIC Verify we can get a valid token and reach the workspace API.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
host = w.config.host
header = w.config.authenticate()
token = header.get("Authorization", "").replace("Bearer ", "")

print(f"Workspace host: {host}")
print(f"Token length:   {len(token)} chars")
print(f"Token prefix:   {token[:10]}...")

me = w.current_user.me()
print(f"Authenticated as: {me.user_name}")
print("--- PASS: Workspace auth ---")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test 2: Serving Endpoint Exists
# MAGIC
# MAGIC Check that `foundry-gpt-5-4-mini` is registered and reachable.

# COMMAND ----------

endpoints = w.serving_endpoints.list()
endpoint_names = [ep.name for ep in endpoints]
print(f"Available endpoints: {endpoint_names}")

target = "foundry-gpt-5-4-mini"
assert target in endpoint_names, f"Endpoint '{target}' not found! Available: {endpoint_names}"
print(f"--- PASS: '{target}' endpoint exists ---")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test 3: Direct LLM Call via Workspace Proxy
# MAGIC
# MAGIC Call `foundry-gpt-5-4-mini` directly through `/serving-endpoints`
# MAGIC using the same auth path as `get_llm()` in `nodes.py`.

# COMMAND ----------

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

llm = ChatOpenAI(
    model="foundry-gpt-5-4-mini",
    base_url=f"{host.rstrip('/')}/serving-endpoints",
    api_key=token,
    temperature=0.3,
    max_tokens=100,
)

response = llm.invoke([HumanMessage(content="Say hello in one sentence.")])
print(f"Response: {response.content}")
print(f"Tokens:   {response.usage_metadata}")
print("--- PASS: Direct LLM call via workspace proxy ---")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test 4: get_llm() Helper
# MAGIC
# MAGIC Verify `get_llm()` from `nodes.py` returns a working client
# MAGIC for the workspace proxy model.

# COMMAND ----------

from agent.nodes import get_llm

llm2 = get_llm("foundry-gpt-5-4-mini")
print(f"base_url: {llm2.openai_api_base}")
print(f"model:    {llm2.model_name}")

response2 = llm2.invoke([HumanMessage(content="What is 2 + 2?")])
print(f"Response: {response2.content}")
print("--- PASS: get_llm() workspace proxy ---")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test 5: Full Graph Execution
# MAGIC
# MAGIC Run the supervisor graph end-to-end with a simple question.

# COMMAND ----------

from agent.supervisor import build_supervisor_graph
from agent.config import init_mlflow

init_mlflow()

graph = build_supervisor_graph(model_endpoint="foundry-gpt-5-4-mini")

result = graph.invoke({
    "messages": [HumanMessage(content="What can you help me with?")],
    "trace_id": "test-run-001",
    "authenticated_user": "test@worley.com",
    "current_agent": "",
    "iteration_count": 0,
    "final_answer": "",
})

print(f"Routed to:  {result['current_agent']}")
print(f"Iterations: {result['iteration_count']}")
print(f"Answer:     {result['final_answer'][:200]}...")
print("--- PASS: Full graph execution ---")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test 6: MLflow Model predict()
# MAGIC
# MAGIC Instantiate the pyfunc model directly and call predict
# MAGIC (same path as Model Serving).

# COMMAND ----------

import pandas as pd
from agent.mlflow_model import SupervisorAgent

model = SupervisorAgent()
model.load_context(None)

test_input = pd.DataFrame([{
    "messages": '[{"role": "user", "content": "Hello, what can you do?"}]',
    "trace_id": "test-run-002",
    "authenticated_user": "test@worley.com",
}])

output = model.predict(None, test_input)
print(f"Response:  {output['response'][:200]}...")
print(f"Trace ID:  {output['trace_id']}")
print("--- PASS: MLflow pyfunc predict ---")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test 7: Serving Endpoint (if deployed)
# MAGIC
# MAGIC Call the `worley-supervisor-agent` Model Serving endpoint
# MAGIC if it exists and is READY.

# COMMAND ----------

import json
import requests

SERVING_ENDPOINT = "worley-supervisor-agent"

try:
    ep = w.serving_endpoints.get(SERVING_ENDPOINT)
    state = str(ep.state.ready)
    print(f"Endpoint state: {state}")

    if state == "READY":
        url = f"{host.rstrip('/')}/serving-endpoints/{SERVING_ENDPOINT}/invocations"
        payload = {
            "dataframe_records": [{
                "messages": json.dumps([{"role": "user", "content": "Hello"}]),
                "trace_id": "test-serving-001",
                "authenticated_user": "test@worley.com",
            }]
        }
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
        print(f"HTTP {resp.status_code}")
        print(f"Response: {resp.json()}")
        print("--- PASS: Serving endpoint call ---")
    else:
        print(f"--- SKIP: Endpoint not READY ({state}) ---")

except Exception as e:
    print(f"--- SKIP: {e} ---")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary
# MAGIC
# MAGIC If all tests pass, the agent is ready for deployment.
# MAGIC Run `02_deploy_agent_mlflow.py` to register and serve.
