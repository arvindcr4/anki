#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 - <<'PY'
from pathlib import Path
import py_compile

addcards = Path("qt/aqt/addcards.py")
doc = Path("docs/llm-intake-ux.md")
py_compile.compile(str(addcards), doraise=True)
text = addcards.read_text()
doc_text = doc.read_text() if doc.exists() else ""

score = 0
detail_visibility = 0
tag_visibility = 0
reset_behavior = 0

checks = [
    ("Source details", 2, "detail"),
    ("set_source_details", 2, "detail"),
    ("_update_source_details", 3, "detail"),
    ("capture::inbox", 1, "tags"),
    ("source::", 1, "tags"),
    ("deck::", 1, "tags"),
    ("type::", 1, "tags"),
    ("_reset_source_workflow", 1, "reset"),
    ("Source details: waiting for a file or URL", 2, "reset"),
]
for needle, pts, bucket in checks:
    if needle in text or needle in doc_text:
        score += pts
        if bucket == "detail":
            detail_visibility += 1
        elif bucket == "tags":
            tag_visibility += 1
        elif bucket == "reset":
            reset_behavior += 1

syntax_ok = 1
print(f"METRIC source_detail_score={score}")
print(f"METRIC syntax_ok={syntax_ok}")
print(f"METRIC detail_visibility={detail_visibility}")
print(f"METRIC tag_visibility={tag_visibility}")
print(f"METRIC reset_behavior={reset_behavior}")
PY
