"""Generate bounded authenticated traffic to observe HPA; no tokens are logged."""

import argparse
import ssl
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from scripts.config import ROOT, environment
from scripts.issue_token import issue_token
from scripts.smoke import PAYLOAD


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://localhost:9443")
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--public-ca", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600 or not 1 <= args.workers <= 64:
        parser.error("seconds must be 1..600 and workers 1..64")
    values = environment()
    context = ssl.create_default_context(
        cafile=None if args.public_ca else ROOT / ".runtime/tls.crt"
    )
    deadline = time.monotonic() + args.seconds

    def worker(_):
        accepted, failed = 0, 0
        with httpx.Client(base_url=args.url, verify=context, timeout=10) as client:
            while time.monotonic() < deadline:
                try:
                    response = client.post(
                        "/DevOps",
                        json=PAYLOAD,
                        headers={
                            "X-Parse-REST-API-Key": values["API_KEY"],
                            "X-JWT-KWY": issue_token(values["JWT_SECRET"]),
                        },
                    )
                    if response.status_code == 200:
                        accepted += 1
                    else:
                        failed += 1
                except httpx.HTTPError:
                    failed += 1
        return accepted, failed

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        counts = list(pool.map(worker, range(args.workers)))
    print(f"Accepted={sum(x[0] for x in counts)} Failed={sum(x[1] for x in counts)}")
    if any(x[1] for x in counts):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
