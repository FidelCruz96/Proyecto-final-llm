import os
import time
import httpx
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ===========================
# FastAPI App
# ===========================
app = FastAPI()

# ===========================
# Logging Config (Cloud Run compatible)
# ===========================
logger = logging.getLogger("router")
logger.setLevel(logging.INFO)

# StreamHandler para que Cloud Run capture los logs
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)

formatter = logging.Formatter("%(message)s")
handler.setFormatter(formatter)

logger.addHandler(handler)

# ===========================
# Environment Variables
# ===========================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CLASSIFIER_URL = os.getenv("CLASSIFIER_URL", "http://classifier:8080/predict")

# ===========================
# Request Schema
# ===========================
class QRequest(BaseModel):
    user_id: str
    text: str
    metadata: dict = {}

# ===========================
# Universal Gemini Caller
# ===========================
async def call_gemini_model(text: str, model: str):

    if not GEMINI_API_KEY:
        return {
            "provider": "gemini-mock",
            "model": model,
            "output": f"(mock gemini {model}) {text}"
        }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{
            "parts": [{"text": text}]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1024
        }
    }

    headers = {"Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()

        j = r.json()

        # Parse output
        if "candidates" in j and j["candidates"]:
            parts = j["candidates"][0]["content"].get("parts", [])
            if parts and "text" in parts[0]:
                return {
                    "provider": "gemini",
                    "model": model,
                    "output": parts[0]["text"]
                }

        return {"provider": "gemini", "model": model, "raw": j}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini API error: {e}")

# ===========================
# ROUTE ENDPOINT
# ===========================
@app.post("/route")
async def route(req: QRequest):

    start_time = time.time()

    # 1) Ask classifier
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(CLASSIFIER_URL, json={"text": req.text})
            resp.raise_for_status()
            decision = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Classifier error: {e}")

    tier = decision.get("tier")
    tokens_est = decision.get("tokens_est", -1)

    if not tier:
        raise HTTPException(status_code=500, detail="Classifier failed")

    # 2) Tier → Model mapping
    MODEL_MAP = {
        "simple": "gemini-2.0-flash-lite",
        "medium": "gemini-2.5-flash",
        "complex": "gemini-2.5-pro",
    }

    model_name = MODEL_MAP.get(tier)
    if not model_name:
        raise HTTPException(status_code=500, detail=f"Unknown tier: {tier}")

    # 3) Call Gemini
    result = await call_gemini_model(req.text, model_name)

    latency_ms = round((time.time() - start_time) * 1000, 2)

    # 4) Logging profesional
    logger.info(
        f"[ROUTER] user={req.user_id} tier={tier} model={model_name} "
        f"tokens_est={tokens_est} latency_ms={latency_ms}"
    )

    # 5) Response
    return {
        "routing": {
            "tier": tier,
            "model_used": model_name,
            "tokens_est": tokens_est,
            "latency_ms": latency_ms
        },
        "response": result
    }
