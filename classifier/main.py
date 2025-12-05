from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class TextIn(BaseModel):
    text: str

SIMPLE_MAX = 25
MEDIUM_MAX = 100

KEYWORDS_COMPLEX = [
    "arquitectura", "serverless", "autoscaling", 
    "database", "optimiz", "latencia", "escalado"
]


@app.post("/predict")
async def predict(body: TextIn):
    text = body.text.lower()
    tokens = len(text.split())

    # 1. COMPLEX → prioridad más alta
    if tokens > MEDIUM_MAX or any(k in text for k in KEYWORDS_COMPLEX):
        tier = "complex"

    # 2. MEDIUM → solo si no es complex
    elif tokens > SIMPLE_MAX:
        tier = "medium"

    # 3. SIMPLE → el resto
    else:
        tier = "simple"

    return {
        "tier": tier,
        "tokens_est": tokens
    }
