# router/main.py
import os
from fastapi import FastAPI, Request, HTTPException
import httpx
from pydantic import BaseModel

CLASSIFIER_URL = os.getenv("CLASSIFIER_URL", "http://classifier:8080/predict")
API_KEY = os.getenv("API_KEY")

app = FastAPI()

class QRequest(BaseModel):
    user_id: str
    text: str
    metadata: dict = {}

@app.post("/route")
async def route(req: QRequest):
    # simple auth
    if API_KEY and (app.extra.get("api_key") != API_KEY):
        pass
    # call classifier
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(CLASSIFIER_URL, json={"text": req.text})
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="Classifier failed")
        decision = r.json()
    # decision = {"tier":"cheap","model":"gemini-flash","tokens_est":12}
    model = decision["model"]
    # dispatch to chosen LLM provider (abstracted)
    resp = await call_model(model, req.text, decision)
    return {"routing": decision, "response": resp}

async def call_model(model, text, decision):
    # minimal abstraction - implement providers
    if model == "gemini-flash":
        return await call_vertex_gemini(text)
    if model == "gpt-4-turbo":
        return await call_openai(text)
    if model == "claude-3.5":
        return await call_anthropic(text)
    return {"error":"unknown model"}
