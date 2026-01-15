import os
import json
import time
import uuid
import logging
from typing import Any, Dict, Optional
import asyncio
import httpx
from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ---------------------------
# Settings
# ---------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # prefer Secret Manager -> env var injection
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "1024"))
CLASSIFIER_URL = os.getenv("CLASSIFIER_URL")
if not CLASSIFIER_URL:
    raise RuntimeError("Missing CLASSIFIER_URL env var")

# Model routing map (override via env if you want)
MODEL_MAP = {
    "simple": os.getenv("MODEL_SIMPLE", "gemini-2.0-flash-lite"),
    "medium": os.getenv("MODEL_MEDIUM", "gemini-2.5-flash"),
    "complex": os.getenv("MODEL_COMPLEX", "gemini-2.5-pro"),
}

# Rough USD price configuration (put your real numbers here; keep it configurable)
# You can pass PRICING_JSON='{"gemini-2.0-flash-lite":{"in":0.0000,"out":0.0000}, ... }'
DEFAULT_PRICING = {
    "gemini-2.0-flash-lite": {"in": 0.0, "out": 0.0},
    "gemini-2.5-flash": {"in": 0.0, "out": 0.0},
    "gemini-2.5-pro": {"in": 0.0, "out": 0.0},
}
try:
    PRICING = json.loads(os.getenv("PRICING_JSON", "")) if os.getenv("PRICING_JSON") else DEFAULT_PRICING
except json.JSONDecodeError:
    PRICING = DEFAULT_PRICING

# ---------------------------
# FastAPI
# ---------------------------
app = FastAPI(title="LLM Multi-Model Router", version="1.0.0")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="ui")

# ---------------------------
# Structured logging (Cloud Run friendly)
# ---------------------------
logger = logging.getLogger("router")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(message)s"))
if not logger.handlers:
    logger.addHandler(_handler)

http_client: Optional[httpx.AsyncClient] = None


class RouteRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    text: str = Field(..., min_length=1, max_length=20_000)
    metadata: Dict[str, Any] = Field(default_factory=dict)


def get_request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id") or str(uuid.uuid4())

def _now_ms() -> float:
    return time.time() * 1000.0


def _log(event: Dict[str, Any]) -> None:
    """Emit JSON logs (best for Cloud Logging queries + log-based metrics)."""
    logger.info(json.dumps(event, ensure_ascii=False))


def _estimate_cost_usd(model: str, tokens_in: Optional[int], tokens_out: Optional[int]) -> float:
    p = PRICING.get(model) or {"in": 0.0, "out": 0.0}
    ti = max(0, int(tokens_in or 0))
    to = max(0, int(tokens_out or 0))
    # pricing is USD per 1 token here; if you store per 1K tokens, adjust accordingly.
    return round(ti * float(p.get("in", 0.0)) + to * float(p.get("out", 0.0)), 8)


async def call_gemini(text: str, model: str, request_id: str) -> Dict[str, Any]:
    """Call Gemini REST API with basic retry + safe parsing."""
    if not GEMINI_API_KEY:
        # Useful for local dev and CI
        return {
            "provider": "gemini-mock",
            "model": model,
            "output": f"(mock gemini {model}) {text[:300]}",
            "usage": {"input_tokens": None, "output_tokens": None, "total_tokens": None},
        }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Request-Id": request_id,
        "x-goog-api-key": GEMINI_API_KEY,
    }

    last_err: Optional[str] = None
    for attempt in range(1, 4):
        try:
            assert http_client is not None
            r = await http_client.post(url, json=payload, headers=headers, timeout=25.0)
            r.raise_for_status()
            j = r.json()

            # Parse output text
            out_text = None
            if j.get("candidates"):
                parts = (j["candidates"][0].get("content") or {}).get("parts") or []
                if parts and isinstance(parts[0], dict):
                    out_text = parts[0].get("text")

            usage = j.get("usageMetadata") or {}
            return {
                "provider": "gemini",
                "model": model,
                "output": out_text,
                "raw": None if out_text else j,
                "usage": {
                    "input_tokens": usage.get("promptTokenCount"),
                    "output_tokens": usage.get("candidatesTokenCount"),
                    "total_tokens": usage.get("totalTokenCount"),
                },
            }

        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as e:
            last_err = str(e)
            # exponential-ish backoff without blocking the event loop
            await asyncio.sleep(0.15 * attempt)

        except Exception as e:
            # unexpected parse/runtime errors
            last_err = str(e)
            await asyncio.sleep(0.15 * attempt)

    raise HTTPException(status_code=502, detail=f"Gemini API error after retries: {last_err}")


@app.on_event("startup")
async def startup() -> None:
    global http_client
    timeout = httpx.Timeout(connect=5.0, read=25.0, write=10.0, pool=5.0)
    limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)
    http_client = httpx.AsyncClient(timeout=timeout, limits=limits)

@app.on_event("shutdown")
async def shutdown() -> None:
    global http_client
    if http_client:
        await http_client.aclose()
        http_client = None


@app.get("/")
def root():
    return {"service": "ok"}

@app.get("/health")
def health(resp: Response):
    resp.headers["Cache-Control"] = "no-store"
    return {"status": "ok"}

@app.get("/ready")
def ready(resp: Response):
    resp.headers["Cache-Control"] = "no-store"
    return {"status": "ok"}


@app.post("/route")
async def route(req: RouteRequest) -> Dict[str, Any]:
    request_id = req.metadata.get("request_id") or str(uuid.uuid4())
    start_ms = _now_ms()

    # 1) Ask classifier
    cls_start = _now_ms()
    try:
        assert http_client is not None
        resp = await http_client.post(
            CLASSIFIER_URL,
            json={"text": req.text, "metadata": req.metadata, "request_id": request_id},
            timeout=8.0,
        )
        resp.raise_for_status()
        decision = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Classifier error: {e}")

    cls_ms = round(_now_ms() - cls_start, 2)
    tier = decision.get("tier")
    tokens_est = decision.get("tokens_est")
    reason = decision.get("reason")

    if tier not in MODEL_MAP:
        raise HTTPException(status_code=500, detail=f"Classifier failed/unknown tier: {tier}")

    model_name = MODEL_MAP[tier]

    # 2) Call Gemini
    llm_start = _now_ms()
    result = await call_gemini(req.text, model_name, request_id=request_id)
    llm_ms = round(_now_ms() - llm_start, 2)

    # 3) Cost estimation (if usage is available, prefer it)
    usage = result.get("usage") or {}
    cost_usd = _estimate_cost_usd(
        model_name,
        tokens_in=usage.get("input_tokens") or tokens_est,
        tokens_out=usage.get("output_tokens"),
    )

    latency_ms = round(_now_ms() - start_ms, 2)

    # 4) JSON log (easy dashboards + log-based metrics)
    _log(
        {
            "service": "router",
            "event": "routed_request",
            "request_id": request_id,
            "user_id": req.user_id,
            "tier": tier,
            "model": model_name,
            "tokens_est": tokens_est,
            "classifier_ms": cls_ms,
            "llm_ms": llm_ms,
            "latency_ms": latency_ms,
            "cost_est_usd": cost_usd,
            "reason": reason,
            "status": "ok",
        }
    )

    return {
        "request_id": request_id,
        "routing": {
            "tier": tier,
            "model_used": model_name,
            "tokens_est": tokens_est,
            "reason": reason,
            "latency_ms": latency_ms,
            "breakdown_ms": {"classifier": cls_ms, "llm": llm_ms},
            "cost_est_usd": cost_usd,
        },
        "response": {
            "provider": result.get("provider"),
            "model": result.get("model"),
            "text": result.get("output"),
            "usage": result.get("usage"),
        },
    }
