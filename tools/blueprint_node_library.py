#!/usr/bin/env python3
"""
Build/search utility for Blueprint node paste library dumps.

Usage:
  python3 tools/blueprint_node_library.py build
  python3 tools/blueprint_node_library.py search --q "K2Node_CallFunction"
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "blueprint-node-library" / "NodeDump.txt"
INDEX_PATH = ROOT / "data" / "blueprint-node-library" / "node_library_index.json"


def parse_dump(text: str) -> Dict[str, Any]:
    lines = [ln.rstrip("\n") for ln in text.splitlines()]

    node_types: List[Dict[str, Any]] = []
    pin_types: List[Dict[str, str]] = []
    connection_patterns: List[Dict[str, Any]] = []

    current_section = ""
    current_node: Dict[str, Any] | None = None
    current_pattern: Dict[str, Any] | None = None

    node_header_re = re.compile(r"^---\s+(.+?)\s+---\s*$")
    section_re = re.compile(r"^(\d+)\.\s+(.+)$")
    pin_line_re = re.compile(r"^([\w\- ]+):\s+(.+)$")

    def flush_node() -> None:
        nonlocal current_node
        if current_node:
            node_types.append(current_node)
            current_node = None

    def flush_pattern() -> None:
        nonlocal current_pattern
        if current_pattern:
            connection_patterns.append(current_pattern)
            current_pattern = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("==="):
            continue

        sec_match = section_re.match(line)
        if sec_match:
            section_num = int(sec_match.group(1))
            if section_num > 3:
                # Ignore unsupported trailing sections in this parser.
                flush_node()
                flush_pattern()
                current_section = "ignored"
                continue

        if line == "1. NODE TYPES":
            flush_node()
            flush_pattern()
            current_section = "node_types"
            continue
        if line == "2. PIN TYPES":
            flush_node()
            flush_pattern()
            current_section = "pin_types"
            continue
        if line == "3. CONNECTION PATTERNS":
            flush_node()
            flush_pattern()
            current_section = "connection_patterns"
            continue

        if current_section == "node_types":
            m = node_header_re.match(line)
            if m:
                flush_node()
                current_node = {
                    "name": m.group(1),
                    "class": "",
                    "description": "",
                    "properties": "",
                    "pins": "",
                    "notes": [],
                }
                continue

            if current_node is None:
                continue

            if line.startswith("Class:"):
                current_node["class"] = line.removeprefix("Class:").strip()
            elif line.startswith("Properties:"):
                current_node["properties"] = line.removeprefix("Properties:").strip()
            elif line.startswith("Pins:"):
                current_node["pins"] = line.removeprefix("Pins:").strip()
            elif line.startswith("Notes:"):
                current_node["notes"].append(line.removeprefix("Notes:").strip())
            else:
                if not current_node["description"]:
                    current_node["description"] = line
                else:
                    # preserve extra details in notes
                    current_node["notes"].append(line)
            continue

        if current_section == "pin_types":
            m = pin_line_re.match(line)
            if m:
                pin_types.append({"pin_type": m.group(1).strip(), "details": m.group(2).strip()})
            else:
                # preserve special pin notes as pseudo entries
                if line.startswith("Special") or line.startswith("Self-context") or line.startswith("External") or line.startswith("Local scope"):
                    pin_types.append({"pin_type": "special", "details": line})
            continue

        if current_section == "connection_patterns":
            m = node_header_re.match(line)
            if m:
                flush_pattern()
                current_pattern = {"name": m.group(1), "steps": []}
                continue

            if current_pattern is None:
                continue

            current_pattern["steps"].append(line)
            continue

    flush_node()
    flush_pattern()

    return {
        "source": str(RAW_PATH),
        "node_types": node_types,
        "pin_types": pin_types,
        "connection_patterns": connection_patterns,
        "counts": {
            "node_types": len(node_types),
            "pin_types": len(pin_types),
            "connection_patterns": len(connection_patterns),
        },
    }


def build_index() -> Dict[str, Any]:
    if not RAW_PATH.exists():
        raise FileNotFoundError(f"Missing raw dump: {RAW_PATH}")

    parsed = parse_dump(RAW_PATH.read_text(encoding="utf-8", errors="replace"))
    INDEX_PATH.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
    return parsed


def search_index(query: str) -> Dict[str, Any]:
    if not INDEX_PATH.exists():
        build_index()

    idx = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    q = query.lower().strip()

    node_hits = [
        n for n in idx.get("node_types", [])
        if q in n.get("name", "").lower()
        or q in n.get("class", "").lower()
        or q in n.get("description", "").lower()
        or q in n.get("properties", "").lower()
        or q in n.get("pins", "").lower()
        or any(q in note.lower() for note in n.get("notes", []))
    ]

    pattern_hits = [
        p for p in idx.get("connection_patterns", [])
        if q in p.get("name", "").lower()
        or any(q in step.lower() for step in p.get("steps", []))
    ]

    return {
        "query": query,
        "node_hits": node_hits,
        "connection_pattern_hits": pattern_hits,
        "counts": {"node_hits": len(node_hits), "connection_pattern_hits": len(pattern_hits)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Blueprint node library index utility")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("build", help="Build normalized JSON index from NodeDump.txt")

    search = sub.add_parser("search", help="Search indexed node/pattern data")
    search.add_argument("--q", required=True, help="Case-insensitive query")

    args = parser.parse_args()

    if args.cmd == "build":
        result = build_index()
        print(json.dumps(result["counts"], indent=2))
        return 0

    result = search_index(args.q)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
