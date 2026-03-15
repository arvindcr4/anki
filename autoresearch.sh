#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 - <<'PY'
from pathlib import Path
import py_compile

addcards = Path('qt/aqt/addcards.py')
toolbar = Path('qt/aqt/toolbar.py')
doc = Path('docs/llm-intake-ux.md')
py_compile.compile(str(addcards), doraise=True)
py_compile.compile(str(toolbar), doraise=True)
texts = [addcards.read_text(), toolbar.read_text(), doc.read_text() if doc.exists() else '']
joined = '\n'.join(texts)
score = 0
toolbar_affordance = 0
window_title_signal = 0
docs_signal = 0
checks = [
    ('Add / Capture', 3, 'toolbar'),
    ('source-first', 2, 'toolbar'),
    ('drag/drop files or URLs', 2, 'toolbar'),
    ('setWindowTitle', 1, 'title'),
    ('Capture', 2, 'title'),
    ('Open Add Cards', 2, 'docs'),
    ('press A', 1, 'docs'),
]
for needle, pts, bucket in checks:
    if needle in joined:
        score += pts
        if bucket == 'toolbar':
            toolbar_affordance += 1
        elif bucket == 'title':
            window_title_signal += 1
        elif bucket == 'docs':
            docs_signal += 1
print(f'METRIC entrypoint_discoverability_score={score}')
print(f'METRIC syntax_ok=1')
print(f'METRIC toolbar_affordance={toolbar_affordance}')
print(f'METRIC window_title_signal={window_title_signal}')
print(f'METRIC docs_signal={docs_signal}')
PY
