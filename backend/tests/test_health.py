from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_status_code():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_body():
    response = client.get("/health")
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "travel-planning-agent"


def test_app_is_configured():
    assert app.title == "travel-planning-agent"
