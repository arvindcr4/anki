# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Apple-Notes-style native title bar for macOS plus dynamic title text.

Two pieces:

1. ``apply_native_chrome(window)`` — on macOS, makes the NSWindow's
   title bar transparent and extends the content into it, so the
   toolbar webview blends seamlessly with the title area (the look used
   by Notes, Mail, Messages, etc.). On other platforms this is a no-op.

2. ``install_dynamic_title(mw)`` — keeps the window title in sync with
   the user's current activity, e.g.::

       Anki — 17 due today          (deck browser)
       attention_… — 12 due         (overview)
       attention_… — Reviewing      (review)

Both are wired up from ``aqt.main.AnkiQt.setupMainWindow`` /
``loadProfile``.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from aqt import gui_hooks

if TYPE_CHECKING:
    from aqt.main import AnkiQt


_IS_MAC = sys.platform == "darwin"


# --------------------------------------------------------------------- chrome


def apply_native_chrome(window: Any) -> None:
    """Make the window's title bar blend into the toolbar (Apple-Notes look).

    On macOS this drops the divider between the title bar and the
    central widget by setting ``NSWindowStyleMaskFullSizeContentView`` and
    ``titlebarAppearsTransparent``. The first toolbar row of the central
    widget then visually extends up under the traffic-light buttons.

    Silently no-ops on non-mac platforms or if PyObjC isn't installed.
    """

    if not _IS_MAC:
        return
    try:
        from AppKit import (
            NSWindowStyleMaskFullSizeContentView,
            NSWindowTitleHidden,
        )
    except Exception:
        return

    qwin = window.windowHandle()
    if qwin is None:
        # The QWindow is created lazily on first show(); re-attempt later.
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(0, lambda: apply_native_chrome(window))
        return

    try:
        ns_view_id = int(qwin.winId())
    except Exception:
        return

    try:
        import objc

        ns_view = objc.objc_object(c_void_p=ns_view_id)
        ns_window = ns_view.window()
        if ns_window is None:
            return
        current_mask = ns_window.styleMask()
        ns_window.setStyleMask_(current_mask | NSWindowStyleMaskFullSizeContentView)
        ns_window.setTitlebarAppearsTransparent_(True)
        # Hide the title text — the dynamic title is still readable from
        # Mission Control and the dock, but the title bar visual is clean.
        ns_window.setTitleVisibility_(NSWindowTitleHidden)
        # Unified look: toolbar buttons (in our case the toolbar webview)
        # appear as if they belong to the title area.
        try:
            window.setUnifiedTitleAndToolBarOnMac(True)
        except Exception:
            pass
    except Exception:
        # Any failure here should not break Anki — silently fall back to
        # the default chrome.
        return


# --------------------------------------------------------------------- title


def _due_count(mw: AnkiQt) -> int:
    try:
        col = mw.col
        if col is None:
            return 0
        tree = col.sched.deck_due_tree()
        if tree is None:
            return 0
        total = 0

        def walk(node: Any) -> None:
            nonlocal total
            total += (
                (getattr(node, "new_count", 0) or 0)
                + (getattr(node, "learn_count", 0) or 0)
                + (getattr(node, "review_count", 0) or 0)
            )
            for child in getattr(node, "children", []) or []:
                walk(child)

        for child in getattr(tree, "children", []) or []:
            walk(child)
        return total
    except Exception:
        return 0


def _short_deck_name(name: str, max_len: int = 36) -> str:
    if len(name) <= max_len:
        return name
    return name[: max_len - 1].rstrip("_") + "…"


def _compute_title(mw: AnkiQt) -> str:
    state = getattr(mw, "state", None)
    col = mw.col
    if col is None or state in (None, "startup", "profileManager"):
        return "Anki"
    if state == "review":
        deck = col.decks.current().get("name", "")
        return f"{_short_deck_name(deck)} — Reviewing"
    if state == "overview":
        deck = col.decks.current().get("name", "")
        return f"{_short_deck_name(deck)} — {_due_count(mw)} due"
    # deck browser, profile manager, etc.
    n = _due_count(mw)
    if n:
        return f"Anki — {n} due today"
    return "Anki"


def _refresh_title(mw: AnkiQt) -> None:
    try:
        mw.setWindowTitle(_compute_title(mw))
    except Exception:
        pass


def install_dynamic_title(mw: AnkiQt) -> None:
    """Hook into state and operation events to keep the title fresh."""

    gui_hooks.state_did_change.append(lambda *_args: _refresh_title(mw))
    gui_hooks.operation_did_execute.append(
        lambda changes, _h: changes.study_queues and _refresh_title(mw)
    )
    gui_hooks.profile_did_open.append(lambda: _refresh_title(mw))
    _refresh_title(mw)
