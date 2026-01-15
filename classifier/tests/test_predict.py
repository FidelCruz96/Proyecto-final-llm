from fastapi.testclient import TestClient
from app import app  # o "from app import app" si no es paquete

client = TestClient(app)

def test_predict_returns_tier():
    r = client.post("/predict", json={"text": "Define API with example", "metadata": {}})
    assert r.status_code == 200
    data = r.json()
    assert data["tier"] in {"simple", "medium", "complex"}
    assert "tokens_est" in data
    assert "reason" in data
