#!/usr/bin/env python3
"""Mechanical checklist for first-class TikZ support.

Outputs a single integer score (0-100) on stdout. No exceptions —
unrecognised diagrams.py just yields a low score, never a crash.
"""

from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent.parent / "qt" / "aqt" / "diagrams.py"


def score() -> int:
    if not TARGET.exists():
        return 0
    src = TARGET.read_text()
    pts = 0

    # Existing baseline (transform + hooks): 30 pts ----------------------
    if "transform_card_html" in src:
        pts += 5
    if "[tikz]" in src.lower() and 'text/tikz' in src:
        pts += 5
    if "[mermaid]" in src.lower() and 'class="mermaid"' in src:
        pts += 5
    if r"\begin{tikzpicture}" in src:
        pts += 5
    if "card_will_show" in src and ".append" in src:
        pts += 5
    if "reviewer_did_show" in src:
        pts += 5

    # Lazy / explicit JS loader: 5 pts ----------------------------------
    if "createElement" in src:
        pts += 5

    # First-class scope: offline + cached rendering ---------------------
    # Offline asset / vendored loader: 15 pts
    if any(
        marker in src
        for marker in (
            "OFFLINE_TIKZJAX",
            "install_tikzjax_assets",
            "_local_loader_html",
            "VENDORED_TIKZJAX",
            "tikzjax_local",
        )
    ):
        pts += 15

    # Cache helper present: 15 pts
    if "cache_diagram_svg" in src or "_cache_to_media" in src:
        pts += 15

    # Hash-based cache key: 5 pts
    if "hashlib" in src:
        pts += 5

    # Cache lookup before re-render (media.have / media.exists): 10 pts
    if "media.have" in src or "media.exists" in src:
        pts += 10

    # Error fallback path: 10 pts
    if ("try:" in src and "except" in src
            and ("error" in src.lower() or "fallback" in src.lower())):
        pts += 10

    # Theme awareness already shipped: 5 pts
    if "prefers-color-scheme" in src:
        pts += 5

    return min(pts, 100)


if __name__ == "__main__":
    print(score())
