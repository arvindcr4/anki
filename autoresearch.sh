#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 - <<'PY'
from pathlib import Path
import py_compile
import re

addcards = Path("qt/aqt/addcards.py")
editor = Path("qt/aqt/editor.py")
ui = Path("qt/aqt/forms/addcards.ui")
doc = Path("docs/llm-intake-ux.md")

for path in (addcards, editor):
    py_compile.compile(str(path), doraise=True)

addcards_text = addcards.read_text()
editor_text = editor.read_text()
ui_text = ui.read_text()
doc_text = doc.read_text() if doc.exists() else ""

score = 0
organization_support = 0
research_doc_ready = 0

# Existing baseline capabilities worth preserving.
if "def dragEnterEvent" in editor_text and "def dropEvent" in editor_text:
    score += 1
if "def urlToLink" in editor_text and "def _processUrls" in editor_text:
    score += 1
if "modelArea" in ui_text and "deckArea" in ui_text:
    score += 1
    organization_support += 1

# New quick-intake surface.
if "QuickIntakeFrame" in addcards_text:
    score += 2
if "setAcceptDrops(True)" in addcards_text and "dropEvent" in addcards_text:
    score += 2
if "_show_intake_file_picker" in addcards_text:
    score += 1
if "_prompt_for_source_url" in addcards_text:
    score += 1
if "_show_llm_setup" in addcards_text:
    score += 1
if "_organize_current_note" in addcards_text:
    score += 1

# Visible copy / affordances.
for needle in [
    "Drop files",
    "Paste URL",
    "LLM",
    "Organize",
    "Current deck",
    "Current note type",
    "source::",
    "capture::inbox",
]:
    if needle in addcards_text:
        score += 1

for needle in ["Current deck", "Current note type", "source::", "capture::inbox"]:
    if needle in addcards_text:
        organization_support += 1

# Research doc coverage.
for heading in [
    "# LLM-era Add Cards UX",
    "## Friction in the current flow",
    "## Design principles",
    "## Proposed interaction model",
    "## Future LLM API surface",
    "## Card organization defaults",
]:
    if heading in doc_text:
        research_doc_ready += 1

score += research_doc_ready
syntax_ok = 1

print(f"METRIC llm_intake_score={score}")
print(f"METRIC syntax_ok={syntax_ok}")
print(f"METRIC organization_support={organization_support}")
print(f"METRIC research_doc_ready={research_doc_ready}")
PY
