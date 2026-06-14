"""TLS certificate directory resolution (data root, not repo root)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_env_config() -> dict[str, str]:
    config: dict[str, str] = {}
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return config
    try:
        with open(env_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip().lstrip("\ufeff")
                if line and "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
    except OSError:
        pass
    return config


def get_certs_dir() -> Path:
    """Return certs root: CERTS_DIR, else ROOT_DIR/certs, else repo certs (dev fallback)."""
    env = _load_env_config()
    certs_dir = env.get("CERTS_DIR")
    if certs_dir:
        return Path(certs_dir)
    root_dir = env.get("ROOT_DIR")
    if root_dir:
        return Path(root_dir) / "certs"
    return REPO_ROOT / "certs"


def get_lan_cert_dir() -> Path:
    return get_certs_dir() / "lan"


def get_domain_certs_dir() -> Path:
    return get_certs_dir() / "domains"


def get_certbot_dir() -> Path:
    return get_certs_dir() / "certbot"
