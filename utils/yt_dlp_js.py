"""
YouTube extraction via yt-dlp requires External JS (EJS): solver scripts + a JS runtime.

- PyPI install must include the `yt-dlp-ejs` scripts (see `yt-dlp[default]` in requirements).
- Default yt-dlp enables Deno; if Deno is missing, use Node (common on Windows).

Env (optional):
  YTDLP_JS_RUNTIME     — deno | node | bun | quickjs (default: auto-detect)
  YTDLP_JS_RUNTIME_EXE — full path to the runtime binary (optional)
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, MutableSequence, Optional

_SUPPORTED = frozenset({"deno", "node", "bun", "quickjs"})
_MIN_NODE_VERSION = (22, 0, 0)


def ytdlp_ejs_installed() -> bool:
    return importlib.util.find_spec("yt_dlp_ejs") is not None


def _parse_version(version_str: str) -> Optional[tuple[int, ...]]:
    try:
        parts = version_str.strip().lstrip("v").split(".")
        return tuple(int(p) for p in parts[:3])
    except (TypeError, ValueError):
        return None


def _find_deno_exe() -> Optional[str]:
    deno = shutil.which("deno")
    if deno:
        return deno
    home = Path.home()
    for candidate in (
        home / ".deno" / "bin" / "deno.exe",
        home / ".deno" / "bin" / "deno",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def _find_supported_node_exe() -> Optional[str]:
    node = shutil.which("node")
    if not node:
        for candidate in (
            Path(r"C:\Program Files\nodejs\node.exe"),
            Path.home() / "AppData" / "Roaming" / "JetBrains" / "PhpStorm2024.2" / "node" / "versions" / "20.17.0" / "node.exe",
        ):
            if candidate.is_file():
                node = str(candidate)
                break
    if not node:
        return None
    try:
        result = subprocess.run(
            [node, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = _parse_version((result.stdout or result.stderr or "").strip())
    except (OSError, subprocess.TimeoutExpired):
        return None
    if not version or version < _MIN_NODE_VERSION:
        return None
    return node


def ytdlp_js_runtime_bin_dir() -> Optional[str]:
    """Directory to prepend to PATH so yt-dlp subprocesses can find the JS runtime."""
    deno = _find_deno_exe()
    if deno:
        return str(Path(deno).parent)
    node = _find_supported_node_exe()
    if node:
        return str(Path(node).parent)
    return None


def _runtime_from_env() -> Optional[Dict[str, Dict[str, Any]]]:
    name = (os.environ.get("YTDLP_JS_RUNTIME") or "").strip().lower()
    if not name:
        return None
    if name not in _SUPPORTED:
        return None
    exe = (os.environ.get("YTDLP_JS_RUNTIME_EXE") or "").strip()
    cfg: Dict[str, Any] = {}
    if exe:
        cfg["path"] = exe
    return {name: cfg}


def _auto_js_runtimes() -> Dict[str, Dict[str, Any]]:
    explicit = _runtime_from_env()
    if explicit:
        return explicit

    deno = _find_deno_exe()
    if deno:
        return {"deno": {"path": deno}}

    node = _find_supported_node_exe()
    if node:
        return {"node": {"path": node}}

    if shutil.which("bun"):
        return {"bun": {}}
    for candidate in ("qjs", "quickjs"):
        if shutil.which(candidate):
            return {"quickjs": {}}

    # Last resort: pass bare "deno" so yt-dlp can surface a clear EJS error.
    return {"deno": {}}


def merge_ytdlp_js_params(opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return a copy of opts with js_runtimes / remote_components set for YouTube EJS."""
    merged: Dict[str, Any] = dict(opts or {})
    if "js_runtimes" not in merged:
        merged["js_runtimes"] = _auto_js_runtimes()
    if not ytdlp_ejs_installed():
        rc = set(merged.get("remote_components") or ())
        rc.add("ejs:github")
        merged["remote_components"] = rc
    return merged


def ytdlp_cli_js_prefix() -> List[str]:
    """Extra CLI tokens to insert after the `yt-dlp` executable name."""
    args: List[str] = []
    for name, cfg in _auto_js_runtimes().items():
        token = name
        path = (cfg or {}).get("path")
        if path:
            token = f"{name}:{path}"
        args.extend(["--js-runtimes", token])
    if not ytdlp_ejs_installed():
        args.extend(["--remote-components", "ejs:github"])
    return args


def extend_ytdlp_cli_cmd(cmd: MutableSequence[str]) -> None:
    """Insert EJS-related flags immediately after `cmd[0]` (the program name)."""
    if not cmd:
        return
    extra = ytdlp_cli_js_prefix()
    if not extra:
        return
    for i, token in enumerate(extra):
        cmd.insert(1 + i, token)
