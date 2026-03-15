#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 - <<'PY'
from pathlib import Path
import py_compile

addcards = Path("qt/aqt/addcards.py")
for path in (addcards,):
    py_compile.compile(str(path), doraise=True)

text = addcards.read_text()
score = 0
visible_context = 0
auto_context_tags = 0

if "Current deck" in text and "Current note type" in text:
    score += 1
    visible_context += 1
if "capture::inbox" in text:
    score += 1
if "source::file::" in text or "source::web::" in text:
    score += 2
if 'deck::' in text and 'type::' in text:
    visible_context += 1
if '_organize_current_note' in text:
    score += 1
if 'Applied organization tags' in text:
    score += 1

# Automatic context tagging must happen inside source capture, not just manual organize.
insert_start = text.find('def _insert_source_links')
insert_end = text.find('def _show_intake_file_picker')
insert_block = text[insert_start:insert_end] if insert_start != -1 and insert_end != -1 else ''
if 'deck::' in insert_block:
    score += 2
    auto_context_tags += 1
if 'type::' in insert_block:
    score += 2
    auto_context_tags += 1
if 'tags: capture::inbox' in insert_block and 'deck::' in insert_block and 'type::' in insert_block:
    score += 1

syntax_ok = 1
print(f"METRIC source_organization_score={score}")
print(f"METRIC syntax_ok={syntax_ok}")
print(f"METRIC auto_context_tags={auto_context_tags}")
print(f"METRIC visible_context={visible_context}")
PY
