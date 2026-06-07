#!/usr/bin/env python3
"""Generate a self-signed TLS cert for LAN HTTPS (PWA install on Android).

Includes SAN entries for localhost, 127.0.0.1, and the detected LAN IP.
Re-run if your LAN IP changes.

Usage (from repo root):
    python scripts/generate_lan_ssl_cert.py
    python scripts/generate_lan_ssl_cert.py --extra-ip 192.168.1.50
"""
from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = REPO_ROOT / "certs" / "lan"


def detect_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _collect_sans(lan_ip: str, extra_ips: list[str]) -> list[x509.GeneralName]:
    names: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    seen = {"127.0.0.1"}
    for ip in [lan_ip, *extra_ips]:
        ip = ip.strip()
        if not ip or ip in seen:
            continue
        try:
            names.append(x509.IPAddress(ipaddress.ip_address(ip)))
            seen.add(ip)
        except ValueError as exc:
            raise SystemExit(f"Invalid IP for SAN: {ip!r}") from exc
    return names


def generate_cert(out_dir: Path, lan_ip: str, extra_ips: list[str], days: int) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    key_path = out_dir / "key.pem"
    cert_path = out_dir / "cert.pem"

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SyncPlay-Hub"),
            x509.NameAttribute(NameOID.COMMON_NAME, lan_ip),
        ]
    )
    san = _collect_sans(lan_ip, extra_ips)
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate LAN self-signed TLS certificate")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Output directory")
    parser.add_argument("--extra-ip", action="append", default=[], help="Additional LAN IP for SAN")
    parser.add_argument("--days", type=int, default=825, help="Certificate validity in days")
    args = parser.parse_args()

    lan_ip = detect_lan_ip()
    cert_path, key_path = generate_cert(args.out_dir, lan_ip, args.extra_ip, args.days)
    sans = ["localhost", "127.0.0.1", lan_ip, *args.extra_ip]

    print("Wrote certificate files:")
    print(f"  {cert_path}")
    print(f"  {key_path}")
    print()
    print("SAN entries:", ", ".join(dict.fromkeys(sans)))
    print()
    print("Start the server with HTTPS:")
    print("  python app.py --root \"<DATA_ROOT>\" --https")
    print()
    print(f"On your phone open: https://{lan_ip}:8000/remote")
    print("Accept the security warning once (self-signed cert), then install the app.")


if __name__ == "__main__":
    main()
