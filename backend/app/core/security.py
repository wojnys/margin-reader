from __future__ import annotations

import secrets
from typing import Annotated
from urllib.parse import urlparse

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyCookie

from backend.app.api.dependencies import RuntimeDep

OWNER_COOKIE = APIKeyCookie(name="margin_owner", scheme_name="MarginOwner", auto_error=False)


def owner(
    request: Request, runtime: RuntimeDep, cookie: Annotated[str | None, Security(OWNER_COOKIE)]
) -> None:
    if not secrets.compare_digest(cookie or "", runtime.owner_secret):
        raise HTTPException(
            401, "Open the app on localhost on your computer. Phones use the paired upload link."
        )
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            raise HTTPException(403, "Cross-origin writes are not allowed")


def require_localhost(request: Request) -> None:
    origin = request.headers.get("origin")
    if (
        request.client is None
        or request.client.host not in {"127.0.0.1", "::1"}
        or request.url.hostname not in {"localhost", "127.0.0.1", "::1"}
        or (origin and urlparse(origin).netloc != request.headers.get("host"))
        or request.headers.get("sec-fetch-site") == "cross-site"
    ):
        raise HTTPException(403, "Use localhost on your computer; pair your phone from the app")
