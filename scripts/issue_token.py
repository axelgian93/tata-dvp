"""Operator-only JWT issuance. Never expose the signing key to evaluators."""

import argparse
import time
from uuid import uuid4

import jwt

from scripts.config import environment


def issue_token(secret, ttl=60):
    if type(ttl) is not int or not 1 <= ttl <= 300:
        raise ValueError("TTL must be between 1 and 300 seconds")
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "devops-assessment",
            "aud": "devops",
            "iat": now,
            "nbf": now,
            "exp": now + ttl,
            "jti": str(uuid4()),
        },
        secret,
        algorithm="HS256",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ttl", type=int, default=60)
    args = parser.parse_args()
    print(issue_token(environment()["JWT_SECRET"], args.ttl))


if __name__ == "__main__":
    main()
