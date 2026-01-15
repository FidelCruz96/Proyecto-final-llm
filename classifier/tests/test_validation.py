from fastapi.testclient import TestClient
from main import app  # o app.py

client = TestClient(app)

def test_predict_requires_text():
    r = client.post("/predict", json={"metadata": {}})
    assert r.status_code == 422
