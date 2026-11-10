# Databricks notebook source
# MAGIC %md
# MAGIC # Register Azure AI Foundry Endpoints in AI Gateway
# MAGIC
# MAGIC This notebook registers two Azure AI Foundry model endpoints as external models
# MAGIC in the Databricks AI Gateway, enabling unified governance, rate limiting,
# MAGIC usage tracking, and guardrails.
# MAGIC
# MAGIC Base URL: https://praju.openai.azure.com/openai/v1/
# MAGIC Provider type: openai (NOT azure) — Foundry exposes OpenAI-compatible endpoints

# COMMAND ----------

# MAGIC %pip install "mlflow[databricks]" -q
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import mlflow.deployments
import time

client = mlflow.deployments.get_deploy_client("databricks")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

FOUNDRY_BASE_URL = "https://praju.openai.azure.com/openai/v1"
SECRET_SCOPE = "praju-foundry-keys"

ENDPOINTS = [
    {
        "name": "foundry-grok-4-fast",
        "model": "grok-4-fast-reasoning",
        "secret_key": "grok-4-fast-key",
        "description": "Grok 4 Fast Reasoning via Azure AI Foundry",
    },
    {
        "name": "foundry-gpt-5-4-mini",
        "model": "gpt-5.4-mini",
        "secret_key": "gpt-5-4-mini-key",
        "description": "GPT 5.4 Mini via Azure AI Foundry",
    },
]

# COMMAND ----------

# MAGIC %md
# MAGIC ## Register Endpoints

# COMMAND ----------

for ep in ENDPOINTS:
    print(f"Registering {ep['name']}...")

    try:
        client.delete_endpoint(endpoint=ep["name"])
        print(f"  Deleted existing endpoint {ep['name']}")
    except Exception:
        pass

    client.create_endpoint(
        name=ep["name"],
        config={
            "served_entities": [
                {
                    "external_model": {
                        "name": ep["model"],
                        "provider": "openai",
                        "task": "llm/v1/chat",
                        "openai_config": {
                            "openai_api_type": "openai",
                            "openai_api_key": f"{{{{secrets/{SECRET_SCOPE}/{ep['secret_key']}}}}}",
                            "openai_api_base": FOUNDRY_BASE_URL,
                        },
                    }
                }
            ],
        },
    )
    print(f"  ✓ Created endpoint {ep['name']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Validate Endpoints

# COMMAND ----------

time.sleep(3)

for ep in ENDPOINTS:
    print(f"\nTesting {ep['name']}...")
    try:
        resp = client.predict(
            endpoint=ep["name"],
            inputs={
                "messages": [{"role": "user", "content": "Say hello in one sentence."}],
                "max_tokens": 50,
            },
        )
        content = resp["choices"][0]["message"]["content"]
        print(f"  ✓ Response: {content}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
