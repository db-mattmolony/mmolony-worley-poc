"""Worley Multi-Agent Supervisor – FastAPI backend.

API routes:
  POST /api/chat    — proxy chat to the serving endpoint
  GET  /api/traces  — fetch and parse MLflow traces for monitoring
  GET  /api/health  — health check
  GET  /            — serve React frontend
"""

from __future__ import annotations

import asyncio
import json
import os
import time as _time
import uuid
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import openai

from agent.config import get_workspace_client

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SERVING_ENDPOINT_NAME = os.environ.get("SUPERVISOR_ENDPOINT", "worley-supervisor-agent")
MLFLOW_EXPERIMENT_ID = os.environ.get("MLFLOW_EXPERIMENT_ID", "2992023807343021")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Worley Multi-Agent Supervisor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class ChatResponse(BaseModel):
    content: str
    latency_ms: float
    routed_agent: str = "unknown"
    sub_agent_input: str = ""
    sub_agent_output: str = ""


# ---------------------------------------------------------------------------
# API: Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "endpoint": SERVING_ENDPOINT_NAME}


@app.get("/api/debug")
async def debug():
    """Temporary debug endpoint — remove before production."""
    import traceback
    info = {"endpoint": SERVING_ENDPOINT_NAME}
    try:
        w = get_workspace_client()
        info["host"] = w.config.host
        info["auth_type"] = str(w.config.auth_type)
    except Exception as e:
        info["workspace_client_error"] = str(e)

    try:
        w = get_workspace_client()
        auth = w.config.authenticate()
        info["auth_result_type"] = str(type(auth))
        info["auth_result_repr"] = repr(auth)[:300]
        if hasattr(auth, "get"):
            info["auth_has_authorization"] = "Authorization" in auth
            token = auth.get("Authorization", "")
            info["token_prefix"] = token[:20] + "..." if token else "EMPTY"
        elif callable(auth):
            info["auth_is_callable"] = True
    except Exception as e:
        info["auth_error"] = str(e)
        info["auth_traceback"] = traceback.format_exc()[-500:]

    try:
        client = _get_openai_client()
        info["openai_base_url"] = str(client.base_url)
        info["openai_api_key_prefix"] = client.api_key[:20] + "..." if client.api_key else "EMPTY"
    except Exception as e:
        info["openai_client_error"] = str(e)
        info["openai_traceback"] = traceback.format_exc()[-500:]

    # Try an actual call
    try:
        client = _get_openai_client()
        resp = client.chat.completions.create(
            model=SERVING_ENDPOINT_NAME,
            messages=[{"role": "user", "content": "ping"}],
        )
        info["test_call"] = "SUCCESS"
        info["test_response"] = resp.choices[0].message.content[:100]
    except Exception as e:
        info["test_call"] = "FAILED"
        info["test_error"] = str(e)
        info["test_traceback"] = traceback.format_exc()[-800:]

    return info


# ---------------------------------------------------------------------------
# API: Chat
# ---------------------------------------------------------------------------

def _get_openai_client():
    """Get an OpenAI-compatible client for Databricks serving endpoints."""
    w = get_workspace_client()
    host = w.config.host.rstrip("/")
    if host and not host.startswith("http"):
        host = f"https://{host}"
    token = w.config.authenticate().get("Authorization", "").replace("Bearer ", "")
    return openai.OpenAI(api_key=token, base_url=f"{host}/serving-endpoints")



@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    """Proxy a chat message to the serving endpoint."""
    messages = list(req.history)
    messages.append({"role": "user", "content": req.message})

    client = _get_openai_client()

    t0 = _time.time()
    raw_resp = client.chat.completions.with_raw_response.create(
        model=SERVING_ENDPOINT_NAME,
        messages=messages,
    )
    latency_ms = round((_time.time() - t0) * 1000, 2)

    data = json.loads(raw_resp.text)
    content = data["choices"][0]["message"]["content"]
    custom = data.get("custom_outputs", {}) or {}

    return ChatResponse(
        content=content,
        latency_ms=latency_ms,
        routed_agent=custom.get("routed_agent", "unknown"),
        sub_agent_input=custom.get("sub_agent_input", ""),
        sub_agent_output=custom.get("sub_agent_output", ""),
    )


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Stream chat response via Server-Sent Events."""
    messages = list(req.history)
    messages.append({"role": "user", "content": req.message})

    async def event_generator():
        t0 = _time.time()

        try:
            # Run the synchronous serving endpoint call in a thread
            # so we don't block the event loop.
            def _call_endpoint():
                client = _get_openai_client()
                return client.chat.completions.with_raw_response.create(
                    model=SERVING_ENDPOINT_NAME,
                    messages=messages,
                )

            raw_resp = await asyncio.to_thread(_call_endpoint)
            latency_ms = round((_time.time() - t0) * 1000, 2)

            data = json.loads(raw_resp.text)
            content = data["choices"][0]["message"]["content"]
            custom = data.get("custom_outputs", {}) or {}

            # Stream content word-by-word for progressive display
            words = content.split(" ")
            for i, word in enumerate(words):
                token = word if i == 0 else " " + word
                yield f"data: {json.dumps({'type': 'delta', 'content': token})}\n\n"
                await asyncio.sleep(0.02)

            # Send metadata after content
            yield f"data: {json.dumps({'type': 'metadata', 'routed_agent': custom.get('routed_agent', 'unknown'), 'latency_ms': latency_ms, 'sub_agent_input': custom.get('sub_agent_input', ''), 'sub_agent_output': custom.get('sub_agent_output', '')})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# API: Traces (for monitoring page)
# ---------------------------------------------------------------------------

@app.get("/api/traces")
async def get_traces(max_results: int = 200):
    """Fetch and parse MLflow traces for the monitoring dashboard."""
    w = get_workspace_client()

    resp = w.api_client.do(
        "GET",
        "/api/2.0/mlflow/traces",
        query={"experiment_ids": MLFLOW_EXPERIMENT_ID, "max_results": str(max_results)},
    )
    raw_traces = resp.get("traces", [])

    parsed = []
    for t in raw_traces:
        meta = {m["key"]: m["value"] for m in t.get("request_metadata", [])}

        # Token usage
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        cache_read_tokens = 0
        try:
            tok = json.loads(meta.get("mlflow.trace.tokenUsage", "{}"))
            input_tokens = tok.get("input_tokens", 0)
            output_tokens = tok.get("output_tokens", 0)
            total_tokens = tok.get("total_tokens", 0)
            cache_read_tokens = tok.get("cache_read_input_tokens", 0)
        except (json.JSONDecodeError, TypeError):
            pass

        # Trace size & span stats
        num_spans = 0
        trace_size_bytes = 0
        span_p50 = 0
        span_max = 0
        try:
            ss = json.loads(meta.get("mlflow.trace.sizeStats", "{}"))
            num_spans = ss.get("num_spans", 0)
            trace_size_bytes = ss.get("total_size_bytes", 0)
            span_p50 = ss.get("p50", 0)
            span_max = ss.get("max", 0)
        except (json.JSONDecodeError, TypeError):
            pass

        # Model version ID
        model_version_id = meta.get("mlflow.modelId", "unknown")

        # Routed agent from tags (reliable, never truncated)
        tags = {tag["key"]: tag["value"] for tag in t.get("tags", [])}
        routed_agent = tags.get("routed_agent", "unknown") or "unknown"

        # Model from response (may be truncated, use regex fallback)
        model = "unknown"
        raw_response = meta.get("mlflow.trace.response", "")
        try:
            response_data = json.loads(raw_response)
            for msg in response_data.get("messages", []):
                rm = msg.get("response_metadata", {})
                if rm.get("model"):
                    model = rm["model"]
        except (json.JSONDecodeError, TypeError):
            import re
            m = re.search(r'"model":\s*"([^"]+)"', raw_response)
            if m:
                model = m.group(1)

        # User question
        question = ""
        try:
            req_data = json.loads(meta.get("mlflow.trace.request", "{}"))
            for msg in req_data.get("messages", []):
                if msg.get("type") == "human":
                    question = msg.get("content", "")[:120]
                    break
        except (json.JSONDecodeError, TypeError):
            pass

        parsed.append({
            "timestamp": datetime.fromtimestamp(t["timestamp_ms"] / 1000).isoformat(),
            "status": t.get("status", "UNKNOWN"),
            "latency_ms": t.get("execution_time_ms", 0),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cache_read_tokens": cache_read_tokens,
            "num_spans": num_spans,
            "trace_size_bytes": trace_size_bytes,
            "span_p50": span_p50,
            "span_max": span_max,
            "model_version_id": model_version_id,
            "routed_agent": routed_agent,
            "model": model,
            "question": question,
            "source": meta.get("mlflow.source.type", "unknown"),
        })

    return {"traces": parsed}


# ---------------------------------------------------------------------------
# Serve React frontend (must be last)
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
