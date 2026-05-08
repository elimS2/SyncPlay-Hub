#!/usr/bin/env python3
"""Generate minimal solid PNGs for remote PWA (stdlib only). Run from repo root or this folder."""
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def write_solid_png(path: Path, width: int, height: int, r: int, g: int, b: int) -> None:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = bytes([0]) + bytes([r, g, b] * width)
    raw = row * height
    compressed = zlib.compress(raw, 9)
    data = sig + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", compressed) + _png_chunk(b"IEND", b"")
    path.write_bytes(data)


def main() -> None:
    # Match static/css/remote.css --bg dark theme
    bg = (10, 10, 10)
    for name, size in (("remote-icon-180.png", 180), ("remote-icon-192.png", 192), ("remote-icon-512.png", 512)):
        write_solid_png(HERE / name, size, size, *bg)
    print("Wrote PNG icons to", HERE)


if __name__ == "__main__":
    main()
