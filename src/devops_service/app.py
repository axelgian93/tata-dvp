"""REST boundary: validation, authentication and one transaction per token."""

import json
import socket
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from redis import Redis
from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool

from devops_service.security import authenticate, consume_token
from devops_service.settings import Settings

Text = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=4096)
]


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: Text
    to: Text
    sender: Text = Field(alias="from")
    timeToLifeSec: Annotated[int, Field(strict=True, ge=1, le=86400)]


def create_app(settings: Settings | None = None, redis_client=None):
    settings = settings or Settings.from_env()
    owned = redis_client is None
    store = (
        redis_client
        if redis_client is not None
        else Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    )

    @asynccontextmanager
    async def lifespan(_app):
        yield
        if owned:
            await run_in_threadpool(store.close)

    app = FastAPI(
        title="DevOps Assessment",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )

    @app.middleware("http")
    async def reject_methods(request: Request, call_next):
        if request.url.path == "/DevOps" and request.method != "POST":
            return PlainTextResponse("ERROR", status_code=405, headers={"Allow": "POST"})
        return await call_next(request)

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/readyz")
    def ready():
        try:
            store.ping()
        except RedisError as exc:
            raise HTTPException(503, "Service unavailable") from exc
        return {"status": "ready"}

    @app.post("/DevOps")
    async def devops(request: Request):
        claims = authenticate(request.headers, settings)
        if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
            raise HTTPException(415, "Content-Type must be application/json")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 16384:
                raise HTTPException(413, "Request too large")
        try:
            message = Message.model_validate(json.loads(body))
        except ValueError as exc:
            raise HTTPException(422, "Invalid message payload") from exc
        await run_in_threadpool(consume_token, store, claims)
        return JSONResponse(
            {"message": f"Hello {message.to} your message will be send"},
            headers={"X-Served-By": socket.gethostname()},
        )

    return app
