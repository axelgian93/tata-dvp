"""Validate signed tokens and atomically consume their transaction IDs."""

import hmac
import time
from uuid import UUID

import jwt
from fastapi import HTTPException
from redis.exceptions import RedisError

from devops_service.settings import Settings


def authenticate(headers, settings: Settings) -> dict:
    supplied = headers.get("x-parse-rest-api-key", "")
    if not hmac.compare_digest(supplied.encode(), settings.api_key.encode()):
        raise HTTPException(401, "Invalid credentials")
    try:
        claims = jwt.decode(
            headers.get("x-jwt-kwy", ""),
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["iss", "aud", "iat", "nbf", "exp", "jti"]},
        )
        UUID(claims["jti"])
        if any(type(claims[key]) is not int for key in ("iat", "nbf", "exp")):
            raise ValueError("Timestamps must be integers")
        if not 0 < claims["exp"] - claims["iat"] <= 300:
            raise ValueError("Token lifetime out of bounds")
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(401, "Invalid credentials") from exc
    return claims


def consume_token(store, claims: dict) -> None:
    ttl = claims["exp"] - int(time.time())
    if ttl <= 0:
        raise HTTPException(401, "Expired token")
    try:
        accepted = store.set(f"used:{claims['iss']}:{claims['jti']}", "1", nx=True, ex=ttl)
    except RedisError as exc:
        raise HTTPException(503, "Service unavailable") from exc
    if not accepted:
        raise HTTPException(409, "Token already used")
