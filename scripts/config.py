"""Shared configuration renderer; only generated files contain credentials."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def environment():
    values = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                values[key] = value
    values.update(os.environ)
    for key in ("API_KEY", "JWT_SECRET"):
        if not values.get(key):
            raise ValueError(f"Missing {key}; run python -m scripts.prepare_local")
    if len(values["JWT_SECRET"].encode()) < 32:
        raise ValueError("JWT_SECRET must contain at least 32 bytes")
    return values


def kong_config(values, targets):
    return {
        "_format_version": "3.0",
        "consumers": [
            {
                "username": "evaluator",
                "keyauth_credentials": [{"key": values["API_KEY"]}],
                "jwt_secrets": [
                    {
                        "key": "devops-assessment",
                        "algorithm": "HS256",
                        "secret": values["JWT_SECRET"],
                    }
                ],
            }
        ],
        "upstreams": [
            {
                "name": "devops-backends",
                "algorithm": "round-robin",
                "targets": [{"target": target, "weight": 100} for target in targets],
            }
        ],
        "services": [
            {
                "name": "devops",
                "host": "devops-backends",
                "port": 8080,
                "protocol": "http",
                "connect_timeout": 3000,
                "read_timeout": 10000,
                "retries": 0,
                "routes": [
                    {
                        "name": "devops-post",
                        "paths": ["~/DevOps$"],
                        "methods": ["POST"],
                        "strip_path": False,
                        "protocols": ["https"],
                        "plugins": [
                            {
                                "name": "pre-function",
                                "config": {
                                    "access": [
                                        'local token = kong.request.get_header("X-JWT-KWY"); '
                                        'kong.service.request.clear_header("Authorization"); '
                                        'if type(token) == "string" then '
                                        'kong.service.request.set_header("Authorization", '
                                        '"Bearer " .. token) end'
                                    ]
                                },
                            },
                            {
                                "name": "key-auth",
                                "config": {
                                    "key_names": ["X-Parse-REST-API-Key"],
                                    "key_in_query": False,
                                    "key_in_body": False,
                                    "hide_credentials": False,
                                },
                            },
                            {
                                "name": "jwt",
                                "config": {
                                    "header_names": ["Authorization"],
                                    "uri_param_names": [],
                                    "cookie_names": [],
                                    "claims_to_verify": ["exp", "nbf"],
                                    "maximum_expiration": 300,
                                },
                            },
                            {
                                "name": "request-size-limiting",
                                "config": {"allowed_payload_size": 16, "size_unit": "kilobytes"},
                            },
                        ],
                    },
                    {
                        "name": "devops-other-methods",
                        "paths": ["~/DevOps$"],
                        "methods": [
                            "GET",
                            "HEAD",
                            "PUT",
                            "PATCH",
                            "DELETE",
                            "OPTIONS",
                            "TRACE",
                            "CONNECT",
                        ],
                        "strip_path": False,
                        "protocols": ["https"],
                    },
                ],
            }
        ],
    }


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
