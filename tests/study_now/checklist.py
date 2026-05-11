# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Checklist score for the Study-Now decoupling autoresearch loop.

We score the *implementation* in qt/aqt/overview.py — not just whether
tests pass. Higher score == more of the invariants we want present.

Total: 60 pts.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OVERVIEW = os.path.join(ROOT, "qt", "aqt", "overview.py")


def _read() -> str:
    with open(OVERVIEW, encoding="utf-8") as f:
        return f.read()


def score() -> int:
    src = _read()
    pts = 0
    # --- 15 pts: forces queue invalidation via sentinel bounce ---
    if "sentinel" in src.lower() and "set_current(" in src:
        pts += 15
    # --- 10 pts: pre-flight check that there are queued cards
    if "get_queued_cards" in src and "queued.cards" in src:
        pts += 10
    # --- 10 pts: explicit moveToState("review") (no double-bounce indirection) ---
    if 'moveToState("review")' in src:
        pts += 10
    # --- 5 pts: graceful empty-queue tooltip (no silent transition to review) ---
    if "studying_no_cards_are_due_yet" in src:
        pts += 5
    # --- 5 pts: timebox is started ---
    if "startTimebox" in src:
        pts += 5
    # --- 5 pts: handler explicitly handles the "study" url ---
    if 'if url == "study"' in src or "url == \"study\"" in src:
        pts += 5
    # --- 10 pts: code does not blindly trust prior set_current call (i.e. it
    # always invalidates the cache) by ensuring two distinct selects ---
    if (
        src.count("col.decks.set_current(") >= 2
        or src.count("decks.select(") + src.count("decks.set_current(") >= 2
    ):
        pts += 10
    return pts


def main() -> int:
    print(score())
    return 0


if __name__ == "__main__":
    sys.exit(main())
