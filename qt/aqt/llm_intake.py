# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Source-to-flashcards intake pipeline.

Single entry point ``ingest_sources(mw, sources)`` accepts a heterogeneous
list of file paths and URLs, extracts text from each, calls the configured
LLM to generate Q&A cards, and adds them to a ``<topic>_<YYYY-MM-DD>`` deck
that is created if missing.

This module intentionally has no Qt UI — the deck browser drop zone (and
the Add/Capture intake panel) call into this from their own callbacks.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from concurrent.futures import Future
from datetime import date
from typing import Any

from anki.decks import DeckId


def _slugify(text: str, max_len: int = 50) -> str:
    text = (text or "").strip()
    if not text:
        return "untitled"
    text = re.sub(r"[^\w\s\-]", " ", text)
    text = re.sub(r"[\s\-_]+", "_", text).strip("_").lower()
    if not text:
        return "untitled"
    return text[:max_len].rstrip("_") or "untitled"


def _optimal_card_count(text: str) -> int:
    words = len(text.split())
    return max(3, min(25, words // 150))


def fetch_url_text(url: str, timeout: int = 30) -> tuple[str, str]:
    """Fetch a URL and return (title, main-text). Caps at 80k chars."""
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 Anki-LLM-Intake/1.0"
        )
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "nav",
            "footer",
            "aside",
            "header",
            "form",
            "iframe",
            "svg",
            "button",
        ]
    ):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    container = soup.find("article") or soup.find("main") or soup.body or soup
    parts: list[str] = []
    for el in container.find_all(
        ["h1", "h2", "h3", "h4", "h5", "p", "li", "blockquote", "pre"]
    ):
        t = el.get_text(" ", strip=True)
        if t:
            parts.append(t)
    return title, "\n\n".join(parts)[:80_000]


def extract_pdf_text(path: str) -> tuple[str, str]:
    """Extract main text from a PDF. Returns (title, text). Caps at 80k chars."""
    from pypdf import PdfReader

    reader = PdfReader(path)
    title = ""
    if reader.metadata and reader.metadata.title:
        title = str(reader.metadata.title).strip()
    if not title:
        title = os.path.splitext(os.path.basename(path))[0]
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            # bad page — skip
            continue
    text = "\n\n".join(p.strip() for p in parts if p.strip())
    return title, text[:80_000]


def _target_deck_id(col: Any, source_label: str) -> tuple[DeckId, str]:
    """Create or fetch the topic_<YYYY-MM-DD> deck for the source. Returns (id, name)."""
    slug = _slugify(source_label)
    deck_name = f"{slug}_{date.today().isoformat()}"
    return DeckId(col.decks.id(deck_name, create=True)), deck_name


def _add_qa_cards(
    col: Any,
    cards: list[Any],
    deck_id: DeckId,
    *,
    source_label: str,
    source_link: str | None,
) -> int:
    """Insert generated cards into the deck. Source link is appended to the back."""
    basic = col.models.by_name("Basic") or col.models.current()
    if basic is None:
        # Last-ditch fallback: pick the first registered model. col.new_note
        # raises if given None, so we must surface this clearly.
        all_models = (
            col.models.all_names_and_ids() if hasattr(col.models, "all_names_and_ids") else []
        )
        if all_models:
            basic = col.models.get(all_models[0].id)
    if basic is None:
        raise RuntimeError(
            "No note type available — Basic is missing and no fallback model registered."
        )
    added = 0
    for card in cards:
        note = col.new_note(basic)
        if note is None:
            continue
        if len(note.fields) >= 1:
            note.fields[0] = card.front
        if len(note.fields) >= 2:
            back = card.back
            if source_link:
                back = (
                    f'{back}<br><br>'
                    f'<i>Source: <a href="{source_link}">{source_label}</a></i>'
                )
            elif source_label:
                back = f"{back}<br><br><i>Source: {source_label}</i>"
            note.fields[1] = back
        note.tags = list(card.tags) if getattr(card, "tags", None) else [
            "llm-generated",
            "from-intake",
        ]
        try:
            col.add_note(note, deck_id)
            added += 1
        except Exception:
            pass
    return added


def ingest_one(mw: Any, source: str) -> dict[str, Any]:
    """Synchronous (blocking) ingest of a single source.

    ``source`` is either an absolute file path (PDF) or an HTTP(S) URL.
    Returns ``{"ok": bool, "added": int, "deck": str, "label": str, "error": str?}``.
    Intended to be called from a background thread.
    """
    from aqt.llm_generate import generate_cards

    is_url = bool(re.match(r"^https?://", source, re.IGNORECASE))
    label = ""
    text = ""
    source_link: str | None = None

    if is_url:
        try:
            label, text = fetch_url_text(source)
            source_link = source
        except Exception as exc:
            return {"ok": False, "error": f"Could not fetch URL: {exc}", "source": source}
    else:
        if not os.path.isfile(source):
            return {"ok": False, "error": f"File not found: {source}", "source": source}
        if not source.lower().endswith(".pdf"):
            return {
                "ok": False,
                "error": f"Only PDFs are supported for file drops (got {os.path.basename(source)}).",
                "source": source,
            }
        try:
            label, text = extract_pdf_text(source)
        except Exception as exc:
            return {"ok": False, "error": f"PDF text extraction failed: {exc}", "source": source}

    if not text.strip():
        return {"ok": False, "error": "No textual content extracted.", "source": source}

    n = _optimal_card_count(text)
    try:
        result = generate_cards(
            text,
            "qa",
            num_cards=n,
            context=(
                f"Source: {label}" + (f"\nURL: {source}" if source_link else "")
            ),
        )
    except Exception as exc:
        return {"ok": False, "error": f"LLM error: {exc}", "source": source}
    if not result.cards:
        return {"ok": False, "error": "LLM returned no usable cards.", "source": source}

    try:
        deck_id, deck_name = _target_deck_id(mw.col, label or source)
        added = _add_qa_cards(
            mw.col,
            result.cards,
            deck_id,
            source_label=label or source,
            source_link=source_link,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Could not add cards to deck: {exc}",
            "source": source,
        }
    return {
        "ok": True,
        "added": added,
        "requested": n,
        "deck": deck_name,
        "label": label or source,
        "model": result.model_used,
        "source": source,
    }


def ingest_sources(
    mw: Any,
    sources: list[str],
    *,
    on_progress: Any = None,
    on_done: Any = None,
) -> None:
    """Ingest a list of sources in the background. Calls callbacks on the main thread.

    on_progress(source: str, status: str) — called as each source starts.
    on_done(results: list[dict]) — called once with all results.
    """
    from aqt.llm_generate import get_api_key, is_local_available

    if not get_api_key() and not is_local_available():
        if on_done:
            on_done(
                [
                    {
                        "ok": False,
                        "error": "No LLM configured. Open Add/Capture → LLM setup.",
                        "source": s,
                    }
                    for s in sources
                ]
            )
        return

    def task() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for s in sources:
            if on_progress is not None:
                mw.taskman.run_on_main(
                    lambda src=s: on_progress(src, "starting")
                )
            res = ingest_one(mw, s)
            out.append(res)
        return out

    def _on_done(future: Future) -> None:
        try:
            results = future.result()
        except Exception as exc:
            results = [{"ok": False, "error": str(exc), "source": "(batch)"}]
        if on_done is not None:
            on_done(results)

    mw.taskman.run_in_background(task, _on_done)
