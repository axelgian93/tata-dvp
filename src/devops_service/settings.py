"""Configuration supplied by the environment, never committed secrets."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_key: str
    jwt_secret: str
    redis_url: str
    jwt_issuer: str = "devops-assessment"
    jwt_audience: str = "devops"

    def __post_init__(self):
        if not self.api_key or len(self.jwt_secret.encode()) < 32:
            raise ValueError("API key and JWT secret of at least 32 bytes are required")

    @classmethod
    def from_env(cls):
        return cls(
            api_key=os.environ["API_KEY"],
            jwt_secret=os.environ["JWT_SECRET"],
            redis_url=os.environ["REDIS_URL"],
        )
