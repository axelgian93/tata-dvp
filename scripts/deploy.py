"""Render and apply namespaced infrastructure; secrets are never printed."""

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import time

import yaml

from scripts.config import ROOT, environment, kong_config


def render(image, local=False):
    if not local and not re.fullmatch(r"ghcr\.io/[a-z0-9._/-]+@sha256:[a-f0-9]{64}", image):
        raise ValueError("Production image must be a GHCR reference pinned by SHA256 digest")
    values = environment()
    config = json.dumps(kong_config(values, ["devops.devops.svc.cluster.local:8080"]))
    if local:
        cert = (ROOT / ".runtime/tls.crt").read_text()
        key = (ROOT / ".runtime/tls.key").read_text()
    else:
        cert = base64.b64decode(os.environ["TLS_CERT_B64"], validate=True).decode()
        key = base64.b64decode(os.environ["TLS_KEY_B64"], validate=True).decode()

    def secret(name, data, kind="Opaque"):
        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": name, "namespace": "devops"},
            "type": kind,
            "stringData": data,
        }

    secrets = [
        secret("devops-auth", {"API_KEY": values["API_KEY"], "JWT_SECRET": values["JWT_SECRET"]}),
        secret("kong-config", {"kong.json": config, "error.txt": "ERROR"}),
        secret("devops-tls", {"tls.crt": cert, "tls.key": key}, "kubernetes.io/tls"),
    ]
    resources = list(yaml.safe_load_all((ROOT / "infra/k8s/workloads.yaml").read_text()))
    digest = hashlib.sha256((config + cert + key).encode()).hexdigest()
    for resource in resources:
        name = resource["metadata"]["name"]
        if resource["kind"] == "Deployment" and name in ("devops", "kong"):
            template = resource["spec"]["template"]
            template["metadata"]["annotations"] = {"checksum/config": digest}
            if name == "devops":
                template["spec"]["containers"][0]["image"] = image
        if local and resource["kind"] == "Service" and name == "kong":
            resource["spec"]["type"] = "NodePort"
            resource["spec"]["ports"][0]["nodePort"] = 30443
    return secrets + resources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--context")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    resources = render(args.image, args.local)
    command = ["kubectl"] + (["--context", args.context] if args.context else [])
    command += ["-n", "devops"]
    for resource in resources:
        apply = command + ["apply", "--server-side", "--field-manager=devops-assessment", "-f", "-"]
        if args.dry_run:
            apply += ["--dry-run=server"]
        result = subprocess.run(apply, input=json.dumps(resource), text=True, capture_output=True)
        if result.returncode:
            # kubectl can echo entire rejected Secret objects in its error output.
            raise SystemExit(
                f"Apply failed: {resource['kind']}/{resource['metadata']['name']}. "
                "Inspect cluster events locally; secret output was suppressed."
            )
        print(f"Validated {resource['kind']}/{resource['metadata']['name']}", flush=True)
    if not args.dry_run:
        for name in ("redis", "devops", "kong"):
            subprocess.run(
                command + ["rollout", "status", f"deployment/{name}", "--timeout=180s"], check=True
            )

        deadline = time.monotonic() + 90
        while True:
            state = json.loads(
                subprocess.check_output(
                    command + ["get", "deployment/devops", "-o", "json"], text=True
                )
            )
            if state.get("status", {}).get("readyReplicas", 0) >= 2:
                break
            if time.monotonic() >= deadline:
                raise SystemExit("HPA did not establish at least two ready replicas")
            time.sleep(3)


if __name__ == "__main__":
    main()
