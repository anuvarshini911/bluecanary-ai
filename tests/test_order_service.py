"""
Week 4 smoke tests for order-service.
Run: pytest tests/ (from repo root, with apps/order-service on PYTHONPATH)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "order-service"))
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402
client = TestClient(app)
def test_healthz_returns_ok():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
def test_orders_returns_list():
    resp = client.get("/orders")
    assert resp.status_code == 200
    assert "orders" in resp.json()
def test_metrics_endpoint_exposes_prometheus_format():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"http_requests_total" in resp.content
def test_version_matches_env_default():
    resp = client.get("/version")
    assert resp.status_code == 200
    assert resp.json()["version"] == "v1"
