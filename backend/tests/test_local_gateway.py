import httpx
import pytest
from fastapi.testclient import TestClient

from app import local_gateway


@pytest.mark.parametrize("path", ["/", "/unrelated", "/api/internal/incidents/extra"])
def test_gateway_rejects_other_post_paths(path):
    with TestClient(local_gateway.app) as client:
        response = client.post(path, headers={"X-Internal-Token": "test-token"})
    assert response.status_code == 404


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
def test_gateway_rejects_other_methods(method):
    with TestClient(local_gateway.app) as client:
        response = client.request(method, "/api/internal/incidents")
    assert response.status_code == 405


def test_gateway_rejects_missing_token():
    with TestClient(local_gateway.app) as client:
        response = client.post("/api/internal/incidents", json={})
    assert response.status_code == 401


def test_gateway_forwards_valid_request(monkeypatch):
    captured = {}

    class FakeAsyncClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, *, content, headers):
            captured.update(url=url, content=content, headers=headers)
            return httpx.Response(201, json={"id": "inc_demo", "status": "new"})

    monkeypatch.setattr(local_gateway.httpx, "AsyncClient", FakeAsyncClient)
    payload = b'{"camera_id":"cam_01"}'
    with TestClient(local_gateway.app) as client:
        response = client.post(
            "/api/internal/incidents",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Internal-Token": "test-token",
            },
        )

    assert response.status_code == 201
    assert response.json() == {"id": "inc_demo", "status": "new"}
    assert captured["url"] == "http://127.0.0.1:8000/api/internal/incidents"
    assert captured["content"] == payload
    assert captured["headers"] == {
        "X-Internal-Token": "test-token",
        "Content-Type": "application/json",
    }
    assert captured["timeout"] == local_gateway.UPSTREAM_TIMEOUT_SECONDS
