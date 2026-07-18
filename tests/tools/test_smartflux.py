"""Tests for the SmartFlux operation tool."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from openjarvis.tools.smartflux import SmartFluxTool

BASE = "https://smartflux.example.com"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SMARTFLUX_BASE_URL", BASE)
    monkeypatch.setenv("SMARTFLUX_API_TOKEN", "tok-123")


def test_unknown_action():
    result = SmartFluxTool().execute(action="nope")
    assert not result.success
    assert "Unknown action" in result.content


def test_missing_config(monkeypatch):
    monkeypatch.delenv("SMARTFLUX_API_TOKEN")
    result = SmartFluxTool().execute(action="briefing")
    assert not result.success
    assert "not configured" in result.content


@respx.mock
def test_briefing_get_sends_bearer():
    route = respx.get(f"{BASE}/api/outbound/briefing").mock(
        return_value=Response(200, json={"actions": [{"title": "Responder leads"}]})
    )
    result = SmartFluxTool().execute(action="briefing")
    assert result.success
    assert "Responder leads" in result.content
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok-123"


@respx.mock
def test_discover_posts_body():
    route = respx.post(f"{BASE}/api/discover").mock(
        return_value=Response(200, json={"leads": []})
    )
    result = SmartFluxTool().execute(
        action="discover",
        businessType="advocacia",
        city="Uberaba",
        state="MG",
        payload={"maxResults": 5},
    )
    assert result.success
    import json

    body = json.loads(route.calls.last.request.content)
    assert body["businessType"] == "advocacia"
    assert body["city"] == "Uberaba"
    assert body["state"] == "MG"
    assert body["maxResults"] == 5


@respx.mock
def test_http_error_reported():
    respx.get(f"{BASE}/api/outbound/finance").mock(
        return_value=Response(401, json={"error": "invalid token"})
    )
    result = SmartFluxTool().execute(action="finance")
    assert not result.success
    assert "401" in result.content
