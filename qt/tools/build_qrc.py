# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import os
import sys
from pathlib import Path

if len(sys.argv) < 3:
    raise SystemExit("usage: build_qrc.py <output.qrc> <icon> [<icon> ...]")

qrc_file = Path(sys.argv[1]).resolve()
icons = [Path(icon) for icon in sys.argv[2:]]

file_skeleton = """
<RCC>
    <qresource prefix="/">
FILES
    </qresource>
</RCC>
""".strip()

indent = " " * 8
lines = []
for icon in icons:
    base = icon.name
    path = os.path.relpath(icon, start=qrc_file.parent)
    line = f'{indent}<file alias="icons/{base}">{path}</file>'
    lines.append(line)

with qrc_file.open("w") as file:
    file.write(file_skeleton.replace("FILES", "\n".join(lines)))
