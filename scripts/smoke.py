"""Exercise the public HTTPS contract, auth, load balancing and replay protection."""

import argparse
import ssl
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from scripts.config import ROOT, environment
from scripts.issue_token import issue_token

PAYLOAD = {
    "message": "This is a test",
    "to": "Juan Perez",
    "from": "Rita Asturia",
    "timeToLifeSec": 45,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://localhost:8443")
    parser.add_argument("--ca", default=str(ROOT / ".runtime/tls.crt"))
    parser.add_argument("--public-ca", action="store_true")
    parser.add_argument("--require-two-backends", action="store_true")
    args = parser.parse_args()
    values = environment()
    context = ssl.create_default_context(cafile=None if args.public_ca else args.ca)
    with httpx.Client(base_url=args.url, verify=context, timeout=15) as client:

        def headers():
            return {
                "X-Parse-REST-API-Key": values["API_KEY"],
                "X-JWT-KWY": issue_token(values["JWT_SECRET"]),
            }

        # A fresh headless Service can remain in Kong DNS negative cache briefly.
        deadline = time.monotonic() + 60
        while True:
            try:
                warmup = client.post("/DevOps", json=PAYLOAD, headers=headers())
                if warmup.status_code == 200:
                    break
                if warmup.status_code not in (502, 503, 504):
                    raise RuntimeError(f"Endpoint rejected warmup: {warmup.status_code}")
            except httpx.TransportError:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("HTTPS endpoint did not become ready within 60 seconds")
            time.sleep(2)
        served = set()
        for _ in range(20):
            response = client.post("/DevOps", json=PAYLOAD, headers=headers())
            assert response.status_code == 200, f"POST failed: {response.status_code}"
            assert response.json() == {"message": "Hello Juan Perez your message will be send"}
            served.add(response.headers["x-served-by"])
        assert client.post("/DevOps", json=PAYLOAD).status_code == 401
        auth = headers()
        assert (
            client.post(
                "/DevOps", json=PAYLOAD, headers={"X-JWT-KWY": auth["X-JWT-KWY"]}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/DevOps", json=PAYLOAD, headers={"X-Parse-REST-API-Key": values["API_KEY"]}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/DevOps", json=PAYLOAD, headers={**headers(), "X-JWT-KWY": "invalid"}
            ).status_code
            == 401
        )
        for method in ["GET", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"]:
            response = client.request(method, "/DevOps")
            assert response.status_code == 405 and response.text == "ERROR", method
        assert client.post("/DevOps", json={}, headers=headers()).status_code == 422
        auth = headers()
        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(
                pool.map(
                    lambda _: client.post("/DevOps", json=PAYLOAD, headers=auth).status_code,
                    range(8),
                )
            )
        assert sorted(statuses) == [200] + [409] * 7, statuses
        if args.require_two_backends:
            assert len(served) >= 2, f"Only {len(served)} backend observed"
        print(f"HTTPS, auth, contract and concurrent replay OK; backends observed: {len(served)}")


if __name__ == "__main__":
    main()
