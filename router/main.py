# router/main.py
import os
import json
import httpx
from typing import Any, Dict
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException

CLASSIFIER_URL = os.getenv("CLASSIFIER_URL", "http://classifier:8080/predict")

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # API Studio key

app = FastAPI()


class QRequest(BaseModel):
    user_id: str
    text: str
    metadata: dict = {}


@app.post("/route")
async def route(req: QRequest):
    # 1) call classifier
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(CLASSIFIER_URL, json={"text": req.text})
            resp.raise_for_status()
            decision = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Classifier error: {e}")

    model = decision.get("model")
    if not model:
        raise HTTPException(status_code=500, detail="Classifier returned no model")

    # 2) call model provider
    try:
        result = await call_model(model, req.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model call failed: {e}")

    return {"routing": decision, "response": result}


async def call_model(model: str, text: str):
    """
    Dispatch to provider. If API keys are missing, returns a local mock response.
    Models expected from classifier: "gemini-flash", "gpt-4-turbo", "claude-3.5"
    """
    if model == "gemini-flash":
        return await call_gemini_api(text)
    if model == "gpt-4-turbo":
        return await call_openai(text)
    if model == "gemini-pro":
        return await call_gemini_pro(text)
    return {"error": "unknown model", "model": model}


# -------------------------
# Providers
# -------------------------

# 1) Gemini API Studio (Generative Language) - simple API key
async def call_gemini_api(text: str):
    """
    Uses Google Generative Language REST API (API Studio). Requires GEMINI_API_KEY.
    Endpoint format:
      https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key=API_KEY
    """
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    api_key = GEMINI_API_KEY

    if not api_key:
        return {"provider": "gemini-mock", "model": model, "output": f"(mock gemini) {text}"}

    # Use v1beta generateContent
    base_urls = [
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    ]

    # New payload structure for generateContent
    payload = {
        "contents": [{
            "parts": [{"text": text}]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 512,
        }
    }

    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=20.0) as client:
        for url in base_urls:
            try:
                # send API key as query param
                r = await client.post(f"{url}?key={api_key}", json=payload, headers=headers)
                
                if r.status_code == 200:
                    j = r.json()
                    # Parse generateContent response
                    # candidates[0].content.parts[0].text
                    if "candidates" in j and isinstance(j["candidates"], list) and j["candidates"]:
                        cand = j["candidates"][0]
                        content = cand.get("content", {})
                        parts = content.get("parts", [])
                        if parts and "text" in parts[0]:
                            return {"provider": "gemini", "model": model, "output": parts[0]["text"]}
                    
                    # fallback
                    return {"provider": "gemini", "model": model, "raw": j}
                
                # non-200: raise to attempt next url or surface error
                r.raise_for_status()
            except httpx.HTTPStatusError as he:
                last_err = he
            except Exception as e:
                last_err = e
        # if all endpoints failed:
        raise RuntimeError(f"Gemini API failed: {last_err}")


# 2) OpenAI via REST
async def call_openai(text: str):
    if not OPENAI_KEY:
        return {"provider": "openai-mock", "output": f"(mock openai) {text}"}

    endpoint = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "messages": [{"role": "user", "content": text}],
        "temperature": 0.2,
        "max_tokens": 512,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(endpoint, headers=headers, json=payload)
        r.raise_for_status()
        j = r.json()
    choices = j.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content") or choices[0].get("text")
        return {"provider": "openai", "model": payload["model"], "output": content}
    return {"provider": "openai", "model": payload["model"], "raw": j}


# 3) Gemini Ultra (via Gemini API) - replacing Anthropic
async def call_gemini_pro(text: str):
    """
    Uses Google Generative Language REST API with gemini-1.5-pro (Ultra equivalent).
    """
    model = "gemini-pro-latest"
    api_key = GEMINI_API_KEY

    if not api_key:
        return {"provider": "gemini-ultra-mock", "model": model, "output": f"(mock gemini ultra) {text}"}

    # Use v1beta generateContent
    base_urls = [
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    ]

    # Payload for generateContent
    payload = {
        "contents": [{
            "parts": [{"text": text}]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1024, # Increased for "Ultra" capability
        }
    }

    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30.0) as client: # Increased timeout for larger model
        for url in base_urls:
            try:
                r = await client.post(f"{url}?key={api_key}", json=payload, headers=headers)
                
                if r.status_code == 200:
                    j = r.json()
                    if "candidates" in j and isinstance(j["candidates"], list) and j["candidates"]:
                        cand = j["candidates"][0]
                        content = cand.get("content", {})
                        parts = content.get("parts", [])
                        if parts and "text" in parts[0]:
                            return {"provider": "gemini-ultra", "model": model, "output": parts[0]["text"]}
                    
                    return {"provider": "gemini-ultra", "model": model, "raw": j}
                
                r.raise_for_status()
            except httpx.HTTPStatusError as he:
                last_err = he
            except Exception as e:
                last_err = e
        
        raise RuntimeError(f"Gemini Ultra API failed: {last_err}")
