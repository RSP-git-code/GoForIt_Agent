from fastapi.testclient import TestClient

from app import config
from app.main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_binds_to_localhost_only():
    assert config.HOST == "127.0.0.1"
