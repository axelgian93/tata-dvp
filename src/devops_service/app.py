"""Application factory."""

from fastapi import FastAPI


def create_app(settings=None, redis_client=None):
    return FastAPI()
