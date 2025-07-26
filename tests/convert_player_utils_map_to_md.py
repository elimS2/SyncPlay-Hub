#!/usr/bin/env python3
"""Convert result.json map into docs/features/PLAYER_UTILS_FILE_MAP.md.

The script reads result.json produced by generate_player_utils_map.py and outputs a
Markdown document containing a human-readable map of the file to be refactored.
The script writes no stdout, only to the target MD file and result.json remains
untouched.
"""

import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
RESULT_PATH = ROOT_DIR / "result.json"
OUTPUT_MD = ROOT_DIR / "docs/features/PLAYER_UTILS_FILE_MAP.md"

# Load JSON map
with RESULT_PATH.open("r", encoding="utf-8") as f:
    data = json.load(f)

mapping = data["mapping"]
file_rel = data["file"]

lines_total = data["total_lines"]

# Build markdown content
lines = []
lines.append(f"# Player Utils File Map\n")
lines.append(f"Source file: `{file_rel}`  ")
lines.append(f"Total lines: **{lines_total}**\n")
lines.append("\n")
lines.append("Each segment is documented below. `hash` is SHA-1 of code with all whitespace removed, used to verify integrity after refactor.\n")
lines.append("\n")
lines.append("| # | Type | Function | Params | Lines | Hash |\n")
lines.append("|---|------|----------|--------|-------|------|\n")

for idx, seg in enumerate(mapping, 1):
    seg_type = seg["type"]
    name = seg.get("name", "")
    params = seg.get("params", "")
    line_range = f"{seg['start_line']}-{seg['end_line']}"
    seg_hash = seg.get("hash", "")
    # Escape pipe characters in params
    params = params.replace("|", "\\|")
    lines.append(f"| {idx} | {seg_type} | {name} | {params} | {line_range} | `{seg_hash}` |\n")

OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_MD.write_text("".join(lines), encoding="utf-8") 