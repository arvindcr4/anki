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
front_center_actions = 0
preview_first_signals = 0

for needle, pts in [
    ("LLM status", 1),
    ("LLM setup", 1),
    ("Choose files", 1),
    ("Paste URL", 1),
    ("Last source", 1),
]:
    if needle in text:
        score += pts

for needle in ["Summarize", "Q&A", "Cloze"]:
    if needle in text:
        score += 2
        front_center_actions += 1

for needle in ["Preview first", "preview-first", "ready for"]:
    if needle in text or needle in doc_text:
        score += 1
        preview_first_signals += 1

if "_show_llm_action" in text:
    score += 2
if "set_llm_status(" in text and "_insert_source_links" in text and "ready" in text:
    score += 2
if "provider not configured" in text:
    score += 1
if "prompt presets" in doc_text or "preview-first" in doc_text:
    score += 1

syntax_ok = 1
print(f"METRIC llm_workspace_score={score}")
print(f"METRIC syntax_ok={syntax_ok}")
print(f"METRIC front_center_actions={front_center_actions}")
print(f"METRIC preview_first_signals={preview_first_signals}")
PY
