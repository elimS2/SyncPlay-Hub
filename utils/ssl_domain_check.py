"""Check whether a public domain is ready for Let's Encrypt (HTTP-01 oriented)."""

from __future__ import annotations

import socket
import urllib.error
import urllib.request
from pathlib import Path

from cryptography import x509

from utils.lan_https import cert_paths_for_domain, certs_available, is_valid_domain, normalize_domain


def _detect_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _resolve_dns(domain: str) -> list[str]:
    ips: list[str] = []
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(domain, None):
            if family == socket.AF_INET:
                ips.append(sockaddr[0])
            elif family == socket.AF_INET6:
                ips.append(sockaddr[0])
    except OSError:
        return []
    return list(dict.fromkeys(ips))


def _http_probe(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "SyncPlay-Hub-SSL-Check/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        if exc.code in (301, 302, 307, 308, 401, 403, 404):
            return True, f"HTTP {exc.code} (reachable)"
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)


def _read_cert_info(cert_path: Path, domain: str) -> dict:
    if not cert_path.is_file():
        return {"present": False, "matches_domain": False, "expires": None, "issuer": None}
    try:
        pem = cert_path.read_bytes()
        cert = x509.load_pem_x509_certificate(pem)
        sans: list[str] = []
        try:
            ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            sans = [str(x.value) for x in ext.value]
        except x509.ExtensionNotFound:
            pass
        cn = None
        for attr in cert.subject:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                cn = attr.value
        names = {normalize_domain(n) for n in sans if n}
        if cn:
            names.add(normalize_domain(str(cn)))
        domain = normalize_domain(domain)
        matches = domain in names or any(n.startswith("*.") and domain.endswith(n[1:]) for n in names if n.startswith("*."))
        issuer = cert.issuer.rfc4514_string()
        expires = cert.not_valid_after_utc.isoformat()
        return {
            "present": True,
            "matches_domain": matches,
            "expires": expires,
            "issuer": issuer,
            "names": sorted(names),
        }
    except Exception as exc:
        return {"present": True, "matches_domain": False, "expires": None, "issuer": None, "error": str(exc)}


def check_domain_ssl_readiness(domain: str, app_port: int = 8000) -> dict:
    domain = normalize_domain(domain)
    local_ip = _detect_lan_ip()
    checks: list[dict] = []

    if not is_valid_domain(domain):
        checks.append({"id": "domain_format", "ok": False, "message": "Invalid domain name"})
        return {"domain": domain, "ready": False, "checks": checks, "local_ip": local_ip, "dns_ips": []}

    checks.append({"id": "domain_format", "ok": True, "message": f"Domain looks valid: {domain}"})

    dns_ips = _resolve_dns(domain)
    if dns_ips:
        checks.append({"id": "dns", "ok": True, "message": f"DNS resolves to: {', '.join(dns_ips)}"})
    else:
        checks.append({"id": "dns", "ok": False, "message": "DNS does not resolve (add an A/AAAA record first)"})

    dns_has_local = local_ip in dns_ips
    dns_has_loopback = any(ip in ("127.0.0.1", "::1") for ip in dns_ips)
    if dns_ips and (dns_has_local or dns_has_loopback):
        checks.append(
            {
                "id": "dns_local",
                "ok": True,
                "message": f"DNS includes this server ({local_ip}) — good for LAN access",
            }
        )
    elif dns_ips:
        checks.append(
            {
                "id": "dns_local",
                "ok": False,
                "message": f"DNS does not point to this LAN host ({local_ip}). Use split DNS or a local DNS override for phones on Wi‑Fi.",
            }
        )

    http80_ok, http80_msg = _http_probe(f"http://{domain}/", timeout=4.0)
    checks.append(
        {
            "id": "http80_public",
            "ok": http80_ok,
            "message": f"Port 80 reachable at domain: {http80_msg}"
            + ("" if http80_ok else " (required for Let's Encrypt HTTP-01 unless you use DNS-01)"),
        }
    )

    http_app_ok, http_app_msg = _http_probe(f"http://{local_ip}:{app_port}/", timeout=3.0)
    checks.append(
        {
            "id": "http_app_local",
            "ok": http_app_ok,
            "message": f"App reachable on LAN: {http_app_msg}",
        }
    )

    cert_path, key_path = cert_paths_for_domain(domain)
    cert_info = _read_cert_info(cert_path, domain)
    has_cert = certs_available(cert_path, key_path)
    if has_cert:
        msg = f"Certificate found at {cert_path.parent}"
        if cert_info.get("matches_domain"):
            msg += f"; valid for domain (expires {cert_info.get('expires')})"
        else:
            msg += "; certificate does not match this domain"
        checks.append({"id": "cert_files", "ok": cert_info.get("matches_domain", False), "message": msg})
    else:
        checks.append(
            {
                "id": "cert_files",
                "ok": False,
                "message": f"No certificate yet. After LE issuance, place fullchain/cert + key in {cert_path.parent}",
            }
        )

    le_ready = (
        checks[0]["ok"]
        and any(c["id"] == "dns" and c["ok"] for c in checks)
        and any(c["id"] == "http80_public" and c["ok"] for c in checks)
    )
    checks.append(
        {
            "id": "letsencrypt_ready",
            "ok": le_ready,
            "message": "Ready to request Let's Encrypt (HTTP-01)"
            if le_ready
            else "Not ready for Let's Encrypt HTTP-01 yet — fix failed checks above",
        }
    )

    https_ready = has_cert and cert_info.get("matches_domain", False)
    checks.append(
        {
            "id": "https_ready",
            "ok": https_ready,
            "message": "HTTPS can be enabled (certificate matches domain)"
            if https_ready
            else "HTTPS cannot be enabled until a matching certificate is installed",
        }
    )

    return {
        "domain": domain,
        "ready": https_ready,
        "letsencrypt_ready": le_ready,
        "checks": checks,
        "local_ip": local_ip,
        "dns_ips": dns_ips,
        "cert_dir": str(cert_path.parent),
        "cert": cert_info,
    }
