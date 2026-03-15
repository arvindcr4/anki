#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 - <<'PY'
from pathlib import Path
import py_compile

addcards = Path("qt/aqt/addcards.py")
py_compile.compile(str(addcards), doraise=True)
text = addcards.read_text()

score = 0
gating_signals = 0
reset_signals = 0

for needle in ["Summarize", "Q&A", "Cloze"]:
    if needle in text:
        score += 1

if "set_llm_actions_enabled" in text:
    score += 3
    gating_signals += 1
if "setEnabled(False)" in text and "set_llm_actions_enabled(False)" in text:
    score += 2
    gating_signals += 1
if "set_llm_actions_enabled(True)" in text:
    score += 2
    gating_signals += 1
if "_reset_source_workflow" in text:
    score += 3
    reset_signals += 1
if text.count("_reset_source_workflow()") >= 2:
    score += 2
    reset_signals += 1
if "Source preview: drop a file or URL" in text and "provider not configured" in text:
    score += 1

syntax_ok = 1
print(f"METRIC workflow_gating_score={score}")
print(f"METRIC syntax_ok={syntax_ok}")
print(f"METRIC gating_signals={gating_signals}")
print(f"METRIC reset_signals={reset_signals}")
PY
