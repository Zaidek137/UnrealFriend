# Agent Big-Fix Log

Purpose: keep short, high-signal notes for major fixes.

Log file:
- `/Users/ericdiaz/Desktop/Unreal Friend/data/agent-fix-log.jsonl`

Entry format (one JSON object per line):
- `timestamp_utc`
- `title`
- `issue`
- `root_cause`
- `change`
- `result`
- `files` (array)
- `tags` (array)

Guidelines:
- Keep each field concise (1 sentence).
- Prefer root cause over symptoms.
- Include only the files that were key to the fix.
- Log only major fixes; skip routine edits.

Helper script:
- `python3 /Users/ericdiaz/Desktop/Unreal Friend/tools/log_fix_entry.py --title ... --issue ... --root-cause ... --change ... --result ... --files "file1,file2"`
