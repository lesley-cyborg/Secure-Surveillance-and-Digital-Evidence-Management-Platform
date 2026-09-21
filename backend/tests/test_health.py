from app.main import app
from fastapi.testclient import TestClient


def test_liveness() -> None:
    with TestClient(
        app,
        base_url="http://localhost",
    ) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Correlation-ID"]
