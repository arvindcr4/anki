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
source_preview_signals = 0
llm_workspace_signals = 0

for needle in ["LLM workspace", "Source preview", "Summarize", "Q&A", "Cloze"]:
    if needle in text:
        score += 2
        if needle in {"LLM workspace"}:
            llm_workspace_signals += 1
        if needle in {"Source preview"}:
            source_preview_signals += 1

for needle in ["next step", "Preview first", "ready for"]:
    if needle in text or needle in doc_text:
        score += 1
        if needle == "next step":
            source_preview_signals += 1
        else:
            llm_workspace_signals += 1

if "set_source_preview" in text:
    score += 2
    source_preview_signals += 1
if "_update_source_preview" in text:
    score += 2
    source_preview_signals += 1
if "_show_llm_action" in text and "selected action" in text:
    score += 2
    llm_workspace_signals += 1
if "Source preview" in doc_text and "preview-first" in doc_text:
    score += 1

syntax_ok = 1
print(f"METRIC source_preview_loop_score={score}")
print(f"METRIC syntax_ok={syntax_ok}")
print(f"METRIC source_preview_signals={source_preview_signals}")
print(f"METRIC llm_workspace_signals={llm_workspace_signals}")
PY
