#!/usr/bin/env python3
"""Append a concise big-fix entry to data/agent-fix-log.jsonl.

Usage:
  python3 tools/log_fix_entry.py \
    --title "Menu Click Fix" \
    --issue "Menu visible but not clickable" \
    --root-cause "UMG/Slate overlap + input mode mismatch" \
    --change "Switched to Slate-first overlay, GameAndUI input, locked movement" \
    --result "Play button became clickable in PIE" \
    --files "/path/a.cpp,/path/b.cpp"
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "data" / "agent-fix-log.jsonl"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Append a concise fix log entry")
    p.add_argument("--title", required=True)
    p.add_argument("--issue", required=True)
    p.add_argument("--root-cause", required=True)
    p.add_argument("--change", required=True)
    p.add_argument("--result", required=True)
    p.add_argument("--files", default="")
    p.add_argument("--tags", default="")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    files = [x.strip() for x in args.files.split(",") if x.strip()]
    tags = [x.strip() for x in args.tags.split(",") if x.strip()]

    entry = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "title": args.title.strip(),
        "issue": args.issue.strip(),
        "root_cause": args.root_cause.strip(),
        "change": args.change.strip(),
        "result": args.result.strip(),
        "files": files,
        "tags": tags,
    }

    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")

    print(f"Logged fix: {entry['title']}")
    print(f"Log file: {LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
