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
visual_hierarchy = 0
drag_feedback = 0
context_clarity = 0
checks = [
    ("quickIntakeSection", 2, "visual"),
    ("quickIntakeChip", 2, "context"),
    ("quickIntakePrimaryAction", 2, "visual"),
    ("quickIntakeAccentAction", 2, "visual"),
    ("quickIntakeGhostAction", 1, "visual"),
    ("dragActive", 3, "drag"),
    ("_set_drag_active", 2, "drag"),
    ("Source-first capture", 2, "visual"),
    ("visual hierarchy", 1, "docs"),
    ("drag feedback", 1, "docs"),
]
for needle, pts, bucket in checks:
    if needle in text or needle in doc_text:
        score += pts
        if bucket == "visual":
            visual_hierarchy += 1
        elif bucket == "drag":
            drag_feedback += 1
        elif bucket == "context":
            context_clarity += 1
        elif bucket == "docs":
            visual_hierarchy += 1
print(f"METRIC intake_ux_polish_score={score}")
print(f"METRIC syntax_ok=1")
print(f"METRIC visual_hierarchy={visual_hierarchy}")
print(f"METRIC drag_feedback={drag_feedback}")
print(f"METRIC context_clarity={context_clarity}")
PY
