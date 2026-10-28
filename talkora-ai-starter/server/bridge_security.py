"""Protect Node-to-Python calls without changing local development defaults.

In production a service secret is mandatory. In development the secret is
optional, but if supplied it is always enforced. Never log this value.
"""

from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request


def is_production() -> bool:
    environment = (os.getenv("TALKORA_ENV") or os.getenv("ENVIRONMENT")
                   or os.getenv("NODE_ENV") or "development")
    return environment.strip().lower() == "production"


async def require_bridge_key(request: Request) -> None:
    expected = os.getenv("TALKORA_SERVICE_KEY", "")
    if is_production() and len(expected) < 32:
        # Do not turn a deployment mistake into an unauthenticated AI endpoint.
        raise HTTPException(503, "AI bridge service authentication is not configured")
    if not expected:
        return  # Legacy local development only.

    supplied = request.headers.get("x-talkora-service-key", "")
    if not hmac.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8")):
        raise HTTPException(401, "AI bridge authentication required")


async def require_experimental_chat_approval() -> None:
    # /chat is a developer research endpoint, not the canonical student route.
    if is_production() and os.getenv("TALKORA_ENABLE_EXPERIMENTAL_CHAT", "").lower() != "true":
        raise HTTPException(404, "Not found")
