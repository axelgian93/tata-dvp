"""Create local-only signing material and HTTPS certificate without printing secrets."""

import ipaddress
import secrets
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from scripts.config import ROOT, environment, kong_config, write_json


def main():
    env_path = ROOT / ".env"
    if not env_path.exists():
        env_path.write_text(
            "API_KEY=2f5ae96c-b558-4c7b-a590-a501ae1c3f6c\n"
            f"JWT_SECRET={secrets.token_urlsafe(48)}\n",
            encoding="utf-8",
        )
        env_path.chmod(0o600)
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    (runtime / "error.txt").write_text("ERROR", encoding="utf-8")
    write_json(runtime / "kong.json", kong_config(environment(), ["app1:8080", "app2:8080"]))
    if not (runtime / "tls.crt").exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        now = datetime.now(UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=30))
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
                ),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        (runtime / "tls.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (runtime / "tls.key").write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    print("Local configuration ready in .runtime/ (ignored by Git).")


if __name__ == "__main__":
    main()
