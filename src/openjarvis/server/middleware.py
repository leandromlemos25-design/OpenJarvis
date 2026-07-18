"""Security middleware -- HTTP security headers and request guards."""

from __future__ import annotations

from typing import Any

__all__ = ["SECURITY_HEADERS", "create_security_middleware"]

# Locked to same-origin, but allow the data:/blob: URIs the UI needs:
# data: fonts (KaTeX) and images (inline SVG textures), and blob: audio/media
# (the Flux voice reply is played from a blob: URL).
_CSP = (
    "default-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "media-src 'self' blob:; "
    "connect-src 'self'"
)


def create_security_middleware() -> Any:
    """Create a FastAPI middleware that adds security headers.

    Returns a middleware class/callable, or None if FastAPI is not available.

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security: max-age=31536000; includeSubDomains
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: camera=(), microphone=(), geolocation=()

    OPTIONS requests are passed through without headers so that
    CORS preflight is not blocked.
    """
    try:
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request
        from starlette.responses import Response
    except ImportError:
        return None

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Any) -> Response:
            # Let CORS preflight requests pass through without
            # security headers that would conflict with CORS.
            if request.method == "OPTIONS":
                return await call_next(request)

            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            # Allow same-origin microphone so browser voice (STT dictation +
            # Flux voice mode) works; camera/geolocation stay off.
            response.headers["Permissions-Policy"] = (
                "camera=(), microphone=(self), geolocation=()"
            )
            response.headers["Content-Security-Policy"] = _CSP
            return response

    return SecurityHeadersMiddleware


# Also export the header values as constants for testing
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(self), geolocation=()",
    "Content-Security-Policy": _CSP,
}
