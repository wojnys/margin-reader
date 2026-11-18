"""Bound batch multipart bodies while they stream, before form parsing can spool them."""

from typing import cast

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BATCH_REQUEST_BYTES = 81 * 1024 * 1024


class BatchBodyTooLarge(MultiPartException):
    pass


class BatchBodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = cast(str, scope.get("path", ""))
        if scope["type"] != "http" or not path.startswith("/api/capture/") or not path.endswith("/batch"):
            await self.app(scope, receive, send)
            return
        received = 0
        rejected = False

        async def limited_receive() -> Message:
            nonlocal received, rejected
            message = await receive()
            if message["type"] == "http.request":
                received += len(cast(bytes, message.get("body", b"")))
                # 80 MB content plus bounded multipart overhead. This applies even
                # to chunked requests without a trustworthy Content-Length header.
                if received > MAX_BATCH_REQUEST_BYTES:
                    rejected = True
                    # MultiPartParser closes any already-spooled files on this exception.
                    raise BatchBodyTooLarge("The batch is too large")
            return message

        async def limited_send(message: Message) -> None:
            # FastAPI may convert a parser exception into its generic 400 response.
            # Suppress that response and return the precise 413 after unwinding.
            if not rejected:
                await send(message)

        try:
            await self.app(scope, limited_receive, limited_send)
        except BatchBodyTooLarge:
            rejected = True
        if rejected:
            await JSONResponse({"detail": "The batch must be smaller than 80 MB in total"}, status_code=413)(
                scope, receive, send
            )
