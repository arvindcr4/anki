#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 - <<'PY'
from pathlib import Path
import py_compile

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
llm_status_surface = 0

if "def dragEnterEvent" in editor_text and "def dropEvent" in editor_text:
    score += 1
if "def urlToLink" in editor_text and "def _processUrls" in editor_text:
    score += 1
if "modelArea" in ui_text and "deckArea" in ui_text:
    score += 1
    organization_support += 1

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
if "LLM status" in addcards_text:
    score += 2
    llm_status_surface += 1
if "set_llm_status" in addcards_text:
    score += 1
    llm_status_surface += 1
if "Last source" in addcards_text:
    score += 1
if "set_last_source" in addcards_text:
    score += 1
if "capture::inbox" in addcards_text and "source::" in addcards_text:
    score += 1

for needle in ["Current deck", "Current note type", "capture::inbox", "source::"]:
    if needle in addcards_text:
        organization_support += 1

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

print(f"METRIC llm_intake_flow_score={score}")
print(f"METRIC syntax_ok={syntax_ok}")
print(f"METRIC organization_support={organization_support}")
print(f"METRIC research_doc_ready={research_doc_ready}")
print(f"METRIC llm_status_surface={llm_status_surface}")
PY
