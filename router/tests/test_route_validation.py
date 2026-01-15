from fastapi.testclient import TestClient
from app import app  # ajusta

client = TestClient(app)

def test_route_requires_text():
    r = client.post("/route", json={"user_id": "u1"})
    assert r.status_code == 422
