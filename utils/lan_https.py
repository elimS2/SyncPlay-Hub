"""LAN HTTPS helpers (settings-driven, optional Let's Encrypt domain)."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LAN_CERT_DIR = REPO_ROOT / "certs" / "lan"
LAN_CERT_PATH = LAN_CERT_DIR / "cert.pem"
LAN_KEY_PATH = LAN_CERT_DIR / "key.pem"
DOMAIN_CERTS_DIR = REPO_ROOT / "certs" / "domains"

SETTING_HTTPS_ENABLED = "server_https_enabled"
SETTING_HTTPS_DOMAIN = "server_https_domain"

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\.?$",
    re.IGNORECASE,
)


def is_valid_domain(domain: str) -> bool:
    domain = (domain or "").strip().rstrip(".")
    if not domain or len(domain) > 253:
        return False
    return bool(_DOMAIN_RE.match(domain))


def normalize_domain(domain: str) -> str:
    return (domain or "").strip().lower().rstrip(".")


def domain_cert_dir(domain: str) -> Path:
    safe = normalize_domain(domain).replace("*", "wildcard")
    return DOMAIN_CERTS_DIR / safe


def cert_paths_for_domain(domain: str | None) -> tuple[Path, Path]:
    domain = normalize_domain(domain or "")
    if domain:
        cert_dir = domain_cert_dir(domain)
        return cert_dir / "cert.pem", cert_dir / "key.pem"
    return LAN_CERT_PATH, LAN_KEY_PATH


def certs_available(cert_path: Path, key_path: Path) -> bool:
    return cert_path.is_file() and key_path.is_file()


def get_https_settings_from_db() -> dict[str, str | bool]:
    try:
        from database import get_connection, get_user_setting

        with get_connection() as conn:
            enabled = (get_user_setting(conn, SETTING_HTTPS_ENABLED, "false") or "false").lower() == "true"
            domain = normalize_domain(get_user_setting(conn, SETTING_HTTPS_DOMAIN, "") or "")
        return {"enabled": enabled, "domain": domain}
    except Exception:
        return {"enabled": False, "domain": ""}


def resolve_https_enabled(https_flag: bool | None) -> bool:
    """CLI --https/--no-https overrides DB; default is HTTP."""
    if https_flag is False:
        return False
    if https_flag is True:
        return True
    return bool(get_https_settings_from_db().get("enabled"))


def resolve_cert_paths(https_flag: bool | None, ssl_cert: Path | None, ssl_key: Path | None) -> tuple[Path, Path]:
    if ssl_cert and ssl_key:
        return ssl_cert, ssl_key
    settings = get_https_settings_from_db()
    domain = settings.get("domain") or ""
    if resolve_https_enabled(https_flag) and domain:
        return cert_paths_for_domain(str(domain))
    return LAN_CERT_PATH, LAN_KEY_PATH


def normalize_restart_argv(argv: list[str]) -> list[str]:
    """Preserve startup args; HTTPS only when enabled in settings or explicit --https."""
    cleaned: list[str] = []
    skip_next = False
    drop_flags = {"--force", "--https", "--no-https"}
    drop_with_value = {"--ssl-cert", "--ssl-key"}
    explicit_https: bool | None = None

    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg == "--https":
            explicit_https = True
            continue
        if arg == "--no-https":
            explicit_https = False
            continue
        if arg in drop_flags:
            continue
        if arg in drop_with_value:
            skip_next = True
            continue
        cleaned.append(arg)

    use_https = resolve_https_enabled(explicit_https)
    if use_https:
        cleaned.append("--https")
    else:
        cleaned.append("--no-https")
    cleaned.append("--force")
    return cleaned
