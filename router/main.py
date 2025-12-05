import os
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CLASSIFIER_URL = os.getenv("CLASSIFIER_URL", "http://classifier:8080/predict")

# ===========================
# Request schema
# ===========================
class QRequest(BaseModel):
    user_id: str
    text: str
    metadata: dict = {}

# ===========================
# Single Gemini caller
# ===========================
async def call_gemini_model(text: str, model: str):
    """Universal Gemini caller for flash, pro, ultra."""
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
        # Parse the content
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
    # 1) Ask classifier
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(CLASSIFIER_URL, json={"text": req.text})
            resp.raise_for_status()
            decision = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Classifier error: {e}")

    tier = decision.get("tier")
    if not tier:
        raise HTTPException(status_code=500, detail="Classifier failed")

    # 2) Map tier → Gemini model
    MODEL_MAP = {
        "simple": "gemini-2.0-flash",
        "medium": "gemini-1.5-pro",
        "complex": "gemini-2.5-pro",
    }

    model_name = MODEL_MAP.get(tier)
    if not model_name:
        raise HTTPException(status_code=500, detail=f"Unknown tier: {tier}")

    # 3) Call Gemini with selected model
    result = await call_gemini_model(req.text, model_name)

    return {
        "routing": decision,
        "response": result
    }
