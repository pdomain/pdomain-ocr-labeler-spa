"""Suite compute-device endpoint wiring."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_suite_device_route_is_mounted(client: TestClient) -> None:
    response = client.get("/api/suite/device")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "local"
    assert isinstance(payload["available"], list)
    assert any(device["id"] == "cpu" for device in payload["available"])
