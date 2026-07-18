"""SmartFlux tool — lets Flux operate the SmartFlux Lead Radar via its API.

SmartFlux (lead-search-smartflux) runs on Cloudflare Pages; every route is
authenticated with a Bearer ``PUBLIC_API_TOKEN``. This tool exposes the
operation to the agent: daily briefing, funnel overview, pending replies,
finance, conversion insights, lead discovery and the lead dossier (Raio-X).

Environment:
    SMARTFLUX_BASE_URL   e.g. https://smartflux.pages.dev (no trailing slash)
    SMARTFLUX_API_TOKEN  the PUBLIC_API_TOKEN configured on Cloudflare
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

# action -> (method, path). Read actions are GET; discover/dossier POST a body.
_ACTIONS: dict[str, tuple[str, str]] = {
    "briefing": ("GET", "/api/outbound/briefing"),
    "overview": ("GET", "/api/outbound/overview"),
    "replies": ("GET", "/api/outbound/replies"),
    "finance": ("GET", "/api/outbound/finance"),
    "insights": ("GET", "/api/outbound/insights"),
    "discover": ("POST", "/api/discover"),
    "dossier": ("POST", "/api/dossier"),
}

_MAX_CONTENT = 12_000  # keep tool output within a sane prompt budget


@ToolRegistry.register("smartflux")
class SmartFluxTool(BaseTool):
    """Operate the SmartFlux Lead Radar (leads, campaigns, finance)."""

    tool_id = "smartflux"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="smartflux",
            description=(
                "Operate the user's SmartFlux lead-generation platform."
                " Actions: 'briefing' (today's prioritized actions),"
                " 'overview' (funnel + campaigns + live feed),"
                " 'replies' (pending WhatsApp replies to review),"
                " 'finance' (closed deals, MRR, pipeline),"
                " 'insights' (which segment/city converts best),"
                " 'discover' (search new leads; requires businessType, city,"
                " state), 'dossier' (deep company profile; pass lead fields in"
                " payload). Use for anything about leads, campaigns or the"
                " SmartFlux operation."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": sorted(_ACTIONS),
                        "description": "Which SmartFlux operation to run.",
                    },
                    "businessType": {
                        "type": "string",
                        "description": "discover: business segment, e.g. 'advocacia'.",
                    },
                    "city": {
                        "type": "string",
                        "description": "discover: city name, e.g. 'Uberaba'.",
                    },
                    "state": {
                        "type": "string",
                        "description": "discover: UF, e.g. 'MG'.",
                    },
                    "payload": {
                        "type": "object",
                        "description": (
                            "Extra fields merged into the request body"
                            " (discover options or dossier lead data)."
                        ),
                    },
                },
                "required": ["action"],
            },
            category="business",
        )

    def execute(self, **params: Any) -> ToolResult:
        action = params.get("action", "")
        if action not in _ACTIONS:
            return ToolResult(
                tool_name="smartflux",
                content=f"Unknown action {action!r}. Valid: {', '.join(sorted(_ACTIONS))}",
                success=False,
            )

        base_url = os.environ.get("SMARTFLUX_BASE_URL", "").rstrip("/")
        token = os.environ.get("SMARTFLUX_API_TOKEN", "")
        if not base_url or not token:
            return ToolResult(
                tool_name="smartflux",
                content=(
                    "SmartFlux is not configured. Set SMARTFLUX_BASE_URL and"
                    " SMARTFLUX_API_TOKEN environment variables and restart."
                ),
                success=False,
            )

        method, path = _ACTIONS[action]
        body: dict[str, Any] | None = None
        if method == "POST":
            body = dict(params.get("payload") or {})
            for key in ("businessType", "city", "state"):
                if params.get(key):
                    body[key] = params[key]

        try:
            resp = httpx.request(
                method,
                f"{base_url}{path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=90.0,
            )
        except httpx.RequestError as exc:
            return ToolResult(
                tool_name="smartflux",
                content=f"SmartFlux request failed: {exc}",
                success=False,
            )

        text = resp.text
        try:
            # Re-serialize compactly so more data fits the content budget.
            text = json.dumps(resp.json(), ensure_ascii=False, separators=(",", ":"))
        except ValueError:
            pass
        if len(text) > _MAX_CONTENT:
            text = text[:_MAX_CONTENT] + "…(truncated)"

        if resp.status_code >= 400:
            return ToolResult(
                tool_name="smartflux",
                content=f"SmartFlux {action} -> HTTP {resp.status_code}: {text}",
                success=False,
            )
        return ToolResult(tool_name="smartflux", content=text, success=True)
