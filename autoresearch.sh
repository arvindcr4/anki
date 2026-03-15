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
front_center_affordance = 0
env_detection = 0
codex_status_surface = 0

checks = [
    ("Connect Codex", 2, "front"),
    ("Codex connection", 2, "status"),
    ("_show_codex_connect", 2, "front"),
    ("OPENAI_API_KEY", 2, "env"),
    ("set_codex_status", 1, "status"),
    ("_refresh_codex_connection", 2, "env"),
    ("Codex", 1, "status"),
]
for needle, pts, bucket in checks:
    if needle in text or needle in doc_text:
        score += pts
        if bucket == "front":
            front_center_affordance += 1
        elif bucket == "env":
            env_detection += 1
        elif bucket == "status":
            codex_status_surface += 1

syntax_ok = 1
print(f"METRIC codex_connect_score={score}")
print(f"METRIC syntax_ok={syntax_ok}")
print(f"METRIC front_center_affordance={front_center_affordance}")
print(f"METRIC env_detection={env_detection}")
print(f"METRIC codex_status_surface={codex_status_surface}")
PY
