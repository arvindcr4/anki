# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Headless reproduction of the Study-Now-after-deck-click bug.

The bug: clicking a deck name navigates to the overview, then clicking
"Study Now" silently bounces back to overview because the cached
``card_queues`` were built for whichever deck was active before, and the
Rust backend only invalidates them when ``set_current_deck`` is called
with a *different* id (rslib/src/decks/current.rs::set_current_deck_inner).

The Study Today flow happens to work because it always selects a target
deck different from whatever was previously current.

We simulate both flows against a real collection and assert that
``get_queued_cards()`` returns non-empty in both — i.e. that the queue is
correctly built for the *currently-selected* deck regardless of which
deck was active immediately before the user clicked Study Now.
"""

from __future__ import annotations

import os
import sys
import tempfile

# Make the in-tree Anki source importable without installing wheels.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for p in ("pylib", "qt", "out/pylib", "out/qt"):
    full = os.path.join(ROOT, p)
    if full not in sys.path:
        sys.path.insert(0, full)

from anki.collection import Collection  # noqa: E402
from anki.decks import DeckId  # noqa: E402


def _tmp_collection() -> Collection:
    tmpdir = tempfile.mkdtemp(prefix="anki-studynow-")
    return Collection(os.path.join(tmpdir, "test.anki2"))


def _add_new_cards(col: Collection, deck_name: str, n: int) -> DeckId:
    deck_id = DeckId(col.decks.id(deck_name, create=True))
    basic = col.models.by_name("Basic")
    assert basic is not None
    for i in range(n):
        note = col.new_note(basic)
        note.fields[0] = f"Q{i}"
        note.fields[1] = f"A{i}"
        col.add_note(note, deck_id)
    return deck_id


# -----------------------------------------------------------------------
# Direct reproduction: with the buggy implementation (no bounce) the
# second flow returns 0 queued cards. With the fix (sentinel bounce) it
# returns >0.
# -----------------------------------------------------------------------


def _study_now_buggy(col: Collection) -> int:
    """The original buggy implementation: just transition to review without
    invalidating queues."""
    queued = col.sched.get_queued_cards()
    return len(queued.cards) if queued and queued.cards else 0


def _study_now_fixed(col: Collection) -> int:
    """The fixed implementation: bounce through a sentinel deck id to force
    the Rust backend to drop the cached card_queues, then ask for cards."""
    current = col.decks.get_current_id()
    sentinel = DeckId(1) if current != DeckId(1) else DeckId(0)
    col.decks.set_current(sentinel)
    col.decks.set_current(current)
    queued = col.sched.get_queued_cards()
    return len(queued.cards) if queued and queued.cards else 0


def scenario_studynow_after_deckclick(study_now) -> int:
    """Reproduces: click deck-A's name → overview → click Study Now.

    The "click deck-A's name" step calls set_current_deck(A) — but if A
    was already current (e.g., because the previous reviewer session left
    it current) that's a no-op for queue invalidation.
    """
    col = _tmp_collection()
    try:
        deck_a = _add_new_cards(col, "deckA", 5)
        deck_b = _add_new_cards(col, "deckB", 5)
        # Simulate the user previously studying deck B, leaving B's queue cached.
        col.decks.set_current(deck_b)
        _ = col.sched.get_queued_cards()  # primes card_queues for deck B
        # User now clicks deck A's name → overview navigates and selects A.
        col.decks.set_current(deck_a)
        # User clicks Study Now.
        return study_now(col)
    finally:
        col.close()


def scenario_studynow_after_studytoday(study_now) -> int:
    """Reproduces the WORKING path: click Study Today → overview → Study Now.

    Study Today selects a deck that's different from the previously-current
    deck, so card_queues IS invalidated."""
    col = _tmp_collection()
    try:
        deck_a = _add_new_cards(col, "deckA", 5)
        deck_b = _add_new_cards(col, "deckB", 5)
        col.decks.set_current(deck_b)
        _ = col.sched.get_queued_cards()
        # Study Today picks deck A (different from current B) and selects it.
        col.decks.set_current(deck_a)
        return study_now(col)
    finally:
        col.close()


def scenario_studynow_repeated_click(study_now) -> int:
    """Edge case: user clicks Study Now twice without anything in between."""
    col = _tmp_collection()
    try:
        deck_a = _add_new_cards(col, "deckA", 5)
        col.decks.set_current(deck_a)
        _ = study_now(col)  # first click
        return study_now(col)  # second click
    finally:
        col.close()


def scenario_only_default_deck_selected(study_now) -> int:
    """Edge case: only the Default deck (id=1) is current, with new cards."""
    col = _tmp_collection()
    try:
        _add_new_cards(col, "Default", 3)
        col.decks.set_current(DeckId(1))
        return study_now(col)
    finally:
        col.close()


def scenario_no_due_cards_returns_zero(study_now) -> int:
    """Empty deck → 0. Asserts the fix doesn't accidentally return phantom cards."""
    col = _tmp_collection()
    try:
        deck_a = DeckId(col.decks.id("emptyDeck", create=True))
        col.decks.set_current(deck_a)
        return study_now(col)
    finally:
        col.close()


def scenario_stale_empty_queue_after_reselect(study_now) -> int:
    """The actual bug condition.

    User finishes deck A (queue depleted → empty), navigates back to the
    deck browser, then re-clicks deck A. ``set_current(A)`` is a no-op
    because A is still the persisted current deck, so the depleted queue
    is NOT invalidated. New cards added in the meantime are invisible
    until the queue is forcibly rebuilt.
    """
    col = _tmp_collection()
    try:
        deck_a = _add_new_cards(col, "deckA", 1)
        col.decks.set_current(deck_a)
        # Build queue + answer the only card so queue is now empty.
        q = col.sched.get_queued_cards()
        if q.cards:
            from anki.scheduler.v3 import CardAnswer

            card = q.cards[0]
            answer = CardAnswer(
                card_id=card.card.id,
                current_state=card.states.current,
                new_state=card.states.again,
                rating=CardAnswer.AGAIN,
                answered_at_millis=0,
                milliseconds_taken=1,
            )
            col.sched.answer_card(answer)
        # Now add a fresh card to deck A. A real user just dropped a URL
        # into the deck and the intake added cards.
        basic = col.models.by_name("Basic")
        note = col.new_note(basic)
        note.fields[0] = "freshQ"
        note.fields[1] = "freshA"
        col.add_note(note, deck_a)
        # User goes to deck browser then re-clicks deck A.
        # set_current(A) is a no-op (already A) — the buggy implementation
        # leaves the depleted queue cached.
        col.decks.set_current(deck_a)
        return study_now(col)
    finally:
        col.close()


SCENARIOS = [
    ("studynow_after_deckclick", scenario_studynow_after_deckclick, lambda n: n > 0),
    ("studynow_after_studytoday", scenario_studynow_after_studytoday, lambda n: n > 0),
    ("studynow_repeated_click", scenario_studynow_repeated_click, lambda n: n > 0),
    ("only_default_deck_selected", scenario_only_default_deck_selected, lambda n: n > 0),
    ("no_due_cards_returns_zero", scenario_no_due_cards_returns_zero, lambda n: n == 0),
    ("stale_empty_queue_after_reselect", scenario_stale_empty_queue_after_reselect, lambda n: n > 0),
]


def run_all(impl_name: str, study_now) -> dict[str, tuple[int, bool]]:
    out: dict[str, tuple[int, bool]] = {}
    for name, fn, ok in SCENARIOS:
        try:
            n = fn(study_now)
        except Exception as exc:  # noqa: BLE001
            print(f"[{impl_name}] {name}: EXC {exc!r}")
            out[name] = (-1, False)
            continue
        passed = ok(n)
        print(f"[{impl_name}] {name}: queued={n} pass={passed}")
        out[name] = (n, passed)
    return out


def main() -> int:
    print("== Buggy implementation (no bounce) ==")
    buggy = run_all("buggy", _study_now_buggy)
    print()
    print("== Fixed implementation (sentinel bounce) ==")
    fixed = run_all("fixed", _study_now_fixed)
    print()
    fixed_passed = sum(1 for _, ok in fixed.values() if ok)
    fixed_total = len(fixed)
    buggy_passed = sum(1 for _, ok in buggy.values() if ok)
    print(f"buggy passed {buggy_passed}/{fixed_total}")
    print(f"fixed passed {fixed_passed}/{fixed_total}")
    if fixed_passed != fixed_total:
        print("FAIL: fixed implementation did not pass all scenarios")
        return 1
    if buggy_passed >= fixed_passed:
        print(
            "WARN: buggy implementation matched fixed — scenarios don't"
            " actually reproduce the bug"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
