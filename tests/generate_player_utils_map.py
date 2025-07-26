#!/usr/bin/env python3
"""Generate a JSON map of static/js/modules/player-utils.js.

The map covers every line of the file. For each contiguous segment it records:
- type: function | blank_or_comments | other_code
- name: function name (for type == function)
- params: raw parameter string (functions only)
- start_line / end_line (1-indexed, inclusive)
- hash: SHA-1 of code with whitespace stripped (functions and other_code)

The output is written to result.json in the project root. The script prints
nothing to stdout (compliance with CI expectations).
"""

import json
import os
import re
import hashlib
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FILE_PATH = ROOT_DIR / "static/js/modules/player-utils.js"
OUTPUT_PATH = ROOT_DIR / "result.json"

# ---------- Helpers -------------------------------------------------------------------

FN_PATTERNS = [
    re.compile(r"^\s*function\s+(\w+)\s*\(([^)]*)\)"),
    re.compile(r"^\s*export\s+function\s+(\w+)\s*\(([^)]*)\)"),
    # NEW: export async function pattern
    re.compile(r"^\s*export\s+async\s+function\s+(\w+)\s*\(([^)]*)\)"),
    # NEW: async function pattern (non-exported)
    re.compile(r"^\s*async\s+function\s+(\w+)\s*\(([^)]*)\)"),
    re.compile(r"^\s*(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function\s*\(([^)]*)\)"),
    re.compile(r"^\s*(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>"),
]


def detect_function_start(line: str):
    """Return (name, params) if the line looks like a function start, else None."""
    for pattern in FN_PATTERNS:
        m = pattern.match(line)
        if m:
            return m.group(1), m.group(2)
    return None


def compute_hash(code: str) -> str:
    """Compute SHA-1 of code stripped from all whitespace characters."""
    compact = re.sub(r"\s+", "", code)
    return hashlib.sha1(compact.encode("utf-8")).hexdigest()

# ---------- Main ----------------------------------------------------------------------

mapping = []

try:
    with FILE_PATH.open("r", encoding="utf-8") as f:
        lines = f.readlines()
except FileNotFoundError:
    raise SystemExit(f"Target file not found: {FILE_PATH}")

total = len(lines)
index = 0

while index < total:
    line = lines[index]
    # NEW: detect import/export statements (non-function)
    if re.match(r"^\s*(?:import|export)\s+(?!function)(?!async)", line):
        seg_start = index + 1
        seg_idx = index
        while seg_idx < total and re.match(r"^\s*(?:import|export)\s+(?!function)(?!async)", lines[seg_idx]):
            seg_idx += 1
        seg_end = seg_idx  # exclusive
        snippet = "".join(lines[seg_start - 1: seg_end])
        mapping.append({
            "type": "import_export",
            "start_line": seg_start,
            "end_line": seg_end,
            "hash": compute_hash(snippet)
        })
        index = seg_end
        continue
    fn_info = detect_function_start(line)
    if fn_info:
        # ---------------- FUNCTION SEGMENT -----------------------------------------
        name, params = fn_info
        start = index + 1  # 1-indexed

        # Distinguish between arrow body expression and block.
        arrow_expression = "=>" in line and "{" not in line

        brace_depth = 0
        saw_brace = False
        end_idx = index

        if arrow_expression:
            # Read until semicolon that ends the expression (robust enough for one-liners)
            while end_idx < total and ";" not in lines[end_idx]:
                end_idx += 1
        else:
            while end_idx < total:
                brace_depth += lines[end_idx].count("{")
                brace_depth -= lines[end_idx].count("}")
                if "{" in lines[end_idx]:
                    saw_brace = True
                if saw_brace and brace_depth == 0:
                    break
                end_idx += 1
        end = end_idx + 1  # inclusive, 1-indexed

        snippet = "".join(lines[start - 1 : end])
        mapping.append(
            {
                "type": "function",
                "name": name,
                "params": params,
                "start_line": start,
                "end_line": end,
                "hash": compute_hash(snippet),
            }
        )
        index = end  # continue after this function
    else:
        # ---------------- NON-FUNCTION SEGMENT -------------------------------------
        region_start = index + 1
        end_idx = index
        while end_idx < total and not detect_function_start(lines[end_idx]):
            end_idx += 1
        region_end = end_idx  # exclusive index
        seg_lines = "".join(lines[region_start - 1 : region_end])
        stripped = seg_lines.strip()
        seg_type = (
            "blank_or_comments"
            if stripped == "" or all(
                s.strip() == "" or s.strip().startswith("//") or s.strip().startswith("/*")
                for s in seg_lines.splitlines()
            )
            else "other_code"
        )
        seg_hash = compute_hash(seg_lines) if seg_type == "other_code" else ""
        mapping.append(
            {
                "type": seg_type,
                "start_line": region_start,
                "end_line": region_end,
                "hash": seg_hash,
            }
        )
        index = region_end

# Sort final mapping explicitly by start_line (defensive)
mapping.sort(key=lambda item: item["start_line"])

# Write JSON output
output = {
    "file": str(FILE_PATH.relative_to(ROOT_DIR)),
    "total_lines": total,
    "mapping": mapping,
}

OUTPUT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8") 