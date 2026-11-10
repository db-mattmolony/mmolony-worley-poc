"""Configuration for the Worley Supervisor Agent."""

import os
import mlflow
from databricks.sdk import WorkspaceClient


# ---------------------------------------------------------------------------
# Workspace / Auth
# ---------------------------------------------------------------------------


def get_workspace_client() -> WorkspaceClient:
    """Return a WorkspaceClient for the infrastructure workspace."""
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE") or os.environ.get("DATABRICKS_PROFILE")
    if profile:
        return WorkspaceClient(profile=profile)
    # Inside a Databricks App the SDK auto-discovers credentials
    return WorkspaceClient()


def get_authenticated_user() -> str:
    """Get the email of the user authenticated into the Databricks App.

    In a Databricks App the proxy sets X-Forwarded-Email / X-Forwarded-User.
    Locally we fall back to the CLI profile's identity.
    """
    # Check environment override first (set by app.py from request headers)
    user = os.environ.get("AUTHENTICATED_USER")
    if user:
        return user
    try:
        w = get_workspace_client()
        me = w.current_user.me()
        return me.user_name or me.display_name or "unknown"
    except Exception:
        return "local-dev-user"


# ---------------------------------------------------------------------------
# AI Gateway Endpoints (workspace-level external model endpoints)
# ---------------------------------------------------------------------------

# Registered via setup/01_register_foundry_endpoints.py — each endpoint
# routes through the workspace AI Gateway with rate limiting, guardrails,
# usage tracking, and secret-managed API keys.
GATEWAY_ENDPOINTS = {
    "foundry-gpt-5-4-mini": "GPT 5.4 Mini via Azure AI Foundry",
    "foundry-grok-4-fast": "Grok 4 Fast via Azure AI Foundry",
    "databricks-claude-sonnet-4-6": "Claude Sonnet 4.6 (Databricks FMAPI)",
}

# Default model — overridable via SUPERVISOR_MODEL env var
DEFAULT_SUPERVISOR_MODEL = os.environ.get("SUPERVISOR_MODEL", "foundry-gpt-5-4-mini")

MAX_ITERATIONS = 10


# ---------------------------------------------------------------------------
# Deployment / Model Serving
# ---------------------------------------------------------------------------

# Unity Catalog model path — override with SUPERVISOR_UC_MODEL env var
UC_MODEL_NAME = os.environ.get("SUPERVISOR_UC_MODEL", "main.default.worley_supervisor_agent")

# Secret scope used for serving endpoint environment vars
SECRET_SCOPE = os.environ.get("SUPERVISOR_SECRET_SCOPE", "praju-foundry-keys")

# Model to use inside Model Serving (workspace serving proxy)
SERVING_PROXY_MODEL = os.environ.get("SUPERVISOR_SERVING_MODEL", "foundry-gpt-5-4-mini")

# Serving endpoint name
SERVING_ENDPOINT_NAME = os.environ.get("SUPERVISOR_ENDPOINT_NAME", "worley-supervisor-agent")

# General Assistant serving endpoint (Azure AI Foundry via OTEL model)
GENERAL_ASSISTANT_ENDPOINT = os.environ.get("GENERAL_ASSISTANT_ENDPOINT", "azure-foundry-otel")

# Knowledge Assistant serving endpoint
KA_ENDPOINT_NAME = os.environ.get("SUPERVISOR_KA_ENDPOINT", "worley-knowledge-assistant")

# Genie Space (Worley ASX stock data)
GENIE_SPACE_ID = os.environ.get("SUPERVISOR_GENIE_SPACE_ID", "01f13498ed181fac818f4b5acde57c51")


# ---------------------------------------------------------------------------
# MLflow
# ---------------------------------------------------------------------------

MLFLOW_EXPERIMENT_NAME = "/Shared/worley-supervisor-agent"


def init_mlflow():
    """Initialise MLflow tracking pointed at the Databricks workspace."""
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE") or os.environ.get("DATABRICKS_PROFILE")
    if profile:
        # Set DATABRICKS_HOST so all MLflow/LangChain clients can discover the workspace
        w = get_workspace_client()
        os.environ.setdefault("DATABRICKS_HOST", w.config.host)
    mlflow.set_tracking_uri("databricks")
    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)
    try:
        mlflow.langchain.autolog(log_traces=True)
    except Exception:
        pass  # langchain not installed (e.g. thin app frontend)

