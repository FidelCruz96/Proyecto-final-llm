# classifier/main.py
from fastapi import FastAPI
from pydantic import BaseModel
import tiktoken # or simple tokenizer
import os

app = FastAPI()

class TextIn(BaseModel):
    text: str

# thresholds (tune in experiments)
SIMPLE_TOKENS = 40
COMPLEX_KEYWORDS = ["error","exception","stacktrace","optimiz","database","how to fix","why does"]

@app.post("/predict")
async def predict(body: TextIn):
    text = body.text.lower()
    n_tokens = len(text.split())
    complexity = "simple"
    if any(k in text for k in COMPLEX_KEYWORDS) or n_tokens > 180:
        complexity = "complex"
    elif n_tokens > 60:
        complexity = "medium"

    if complexity == "simple":
        model = "gemini-flash"
    elif complexity == "medium":
        model = "gpt-4-turbo"
    else:
        model = "claude-3.5"

    return {"tier": complexity, "model": model, "tokens_est": n_tokens}
