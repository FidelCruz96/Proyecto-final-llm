import re
from typing import Any, Dict, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="Query Classifier", version="1.0.0")


class TextIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=20_000)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    request_id: Optional[str] = None


SIMPLE_MAX = int(25)
MEDIUM_MAX = int(100)

# Keep it bilingual; open source people will test in English too.
KEYWORDS_COMPLEX = [
    "arquitectura", "architecture",
    "serverless", "autoscaling", "escalabilidad", "scaling",
    "database", "postgres", "sql",
    "optimiz", "optimize", "latencia", "latency",
    "throughput", "concurrency", "timeout",
    "caching", "cache", "redis",
]

CODE_HINTS = [
    "```", "select ", "insert ", "update ", "dockerfile", "kubernetes", "yaml:", "terraform",
]


def estimate_tokens(text: str) -> int:
    """
    Cheap token estimate (provider-agnostic).
    - words is OK for Spanish, but we add a char-based fallback for code-like text.
    """
    words = len(text.split())
    chars = len(text)
    approx = max(words, int(chars / 4))  # ~4 chars/token is a decent rough average
    return max(1, approx)


def complexity_score(text_l: str) -> int:
    score = 0
    score += 2 * sum(1 for k in KEYWORDS_COMPLEX if k in text_l)
    score += 3 * sum(1 for h in CODE_HINTS if h in text_l)
    # Code blocks / lots of symbols usually mean higher complexity
    if re.search(r"[{}();<>]=|->|::|/\w+|\\n", text_l):
        score += 2
    return score


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/predict")
async def predict(body: TextIn):
    text_l = body.text.lower()
    tokens = estimate_tokens(text_l)
    score = complexity_score(text_l)

    # Optional override (useful for admin / experiments)
    forced = (body.metadata or {}).get("force_tier")
    if forced in {"simple", "medium", "complex"}:
        return {
            "tier": forced,
            "tokens_est": tokens,
            "reason": "forced_by_metadata",
            "score": score,
        }

    # Rule-based tiers (fast + cheap). You can later swap this with embeddings/ML.
    if tokens > MEDIUM_MAX or score >= 5:
        tier = "complex"
        reason = "tokens_or_signals_high"
    elif tokens > SIMPLE_MAX or score >= 2:
        tier = "medium"
        reason = "tokens_or_signals_medium"
    else:
        tier = "simple"
        reason = "tokens_and_signals_low"

    return {"tier": tier, "tokens_est": tokens, "reason": reason, "score": score}
