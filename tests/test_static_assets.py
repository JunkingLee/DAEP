from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_dashboard_serves_agent_script_from_static_mount():
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert '<script src="/static/agents.js"></script>' in dashboard.text

    script = client.get("/static/agents.js")
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"].lower()
    assert "function init()" in script.text


def test_static_mount_does_not_intercept_api_routes():
    response = client.get("/readyz")
    assert response.status_code == 200
