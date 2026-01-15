import pytest
from fastapi.testclient import TestClient
from app import app  # ajusta si tu router es main.py

client = TestClient(app)

class DummyResp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return self._payload

@pytest.fixture(autouse=True)
def env(monkeypatch):
    # evita llamar a Gemini real: usa mock
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("ALLOW_MOCK", "true")
    monkeypatch.setenv("CLASSIFIER_URL", "https://fake-classifier/predict")

def test_route_ok(monkeypatch):
    # mock classifier call
    async def fake_post(url, json=None, headers=None, timeout=None):
        assert url.endswith("/predict")
        return DummyResp({"tier": "simple", "tokens_est": 10, "reason": "test", "score": 0})

    # parchea el http_client global del router
    import app as router_mod
    monkeypatch.setattr(router_mod.http_client, "post", fake_post)

    r = client.post("/route", json={"user_id": "u1", "text": "Define API"})
    assert r.status_code == 200
    data = r.json()
    assert "request_id" in data
    assert data["routing"]["tier"] == "simple"
    assert "response" in data
