# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
import os
import re
import urllib.parse
from collections.abc import Callable, Sequence
from concurrent.futures import Future

import aqt.editor
import aqt.forms
from anki._legacy import deprecated
from anki.collection import OpChanges, OpChangesWithCount, SearchNode
from anki.decks import DeckId
from anki.models import NotetypeId
from anki.notes import Note, NoteFieldsCheckResult, NoteId
from anki.utils import html_to_text_line, is_mac
from aqt import AnkiQt, gui_hooks
from aqt.deckchooser import DeckChooser
from aqt.notetypechooser import NotetypeChooser
from aqt.operations.note import add_note
from aqt.qt import *
from aqt.sound import av_player
from aqt.utils import (
    HelpPage,
    ask_user_dialog,
    askUser,
    downArrow,
    getFile,
    openHelp,
    restoreGeom,
    saveGeom,
    shortcut,
    showInfo,
    showWarning,
    tooltip,
    tr,
)


class QuickIntakeFrame(QFrame):
    def __init__(
        self,
        *,
        on_drop: Callable[[Sequence[str], Sequence[str]], None],
        on_choose_files: Callable[[], None],
        on_paste_url: Callable[[], None],
        on_llm_setup: Callable[[], None],
        on_codex_connect: Callable[[], None],
        on_llm_action: Callable[[str], None],
        on_organize: Callable[[], None],
    ) -> None:
        super().__init__()
        self._on_drop = on_drop
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("quickIntakeFrame")
        self.setProperty("dragActive", False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        eyebrow = QLabel("Source-first capture")
        eyebrow.setObjectName("quickIntakeEyebrow")
        layout.addWidget(eyebrow)

        headline = QLabel("Turn files and URLs into clean cards")
        headline.setObjectName("quickIntakeHeadline")
        headline.setWordWrap(True)
        layout.addWidget(headline)

        body = QLabel(
            "Start from source material, confirm where the note will land, then preview an LLM action before anything is written into fields."
        )
        body.setObjectName("quickIntakeBody")
        body.setWordWrap(True)
        layout.addWidget(body)

        chip_row = QHBoxLayout()
        chip_row.setSpacing(8)
        self.deck_chip = QLabel("Deck: —")
        self.deck_chip.setObjectName("quickIntakeChip")
        chip_row.addWidget(self.deck_chip)
        self.note_type_chip = QLabel("Note type: —")
        self.note_type_chip.setObjectName("quickIntakeChip")
        chip_row.addWidget(self.note_type_chip)
        chip_row.addStretch(1)
        layout.addLayout(chip_row)

        actions = QHBoxLayout()
        actions.setSpacing(8)

        choose_files = QPushButton("Choose files")
        choose_files.setObjectName("quickIntakePrimaryAction")
        choose_files.setAutoDefault(False)
        qconnect(choose_files.clicked, on_choose_files)
        actions.addWidget(choose_files)

        paste_url = QPushButton("Paste URL")
        paste_url.setObjectName("quickIntakePrimaryAction")
        paste_url.setAutoDefault(False)
        qconnect(paste_url.clicked, on_paste_url)
        actions.addWidget(paste_url)

        connect_codex = QPushButton("Connect Codex")
        connect_codex.setObjectName("quickIntakeAccentAction")
        connect_codex.setAutoDefault(False)
        qconnect(connect_codex.clicked, on_codex_connect)
        actions.addWidget(connect_codex)

        llm_setup = QPushButton("LLM setup")
        llm_setup.setObjectName("quickIntakeGhostAction")
        llm_setup.setAutoDefault(False)
        qconnect(llm_setup.clicked, on_llm_setup)
        actions.addWidget(llm_setup)

        organize = QPushButton("Organize note")
        organize.setObjectName("quickIntakeGhostAction")
        organize.setAutoDefault(False)
        qconnect(organize.clicked, on_organize)
        actions.addWidget(organize)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.capture_section = self._make_section(layout, "Capture from source")
        capture_layout = self.capture_section.layout()
        assert isinstance(capture_layout, QVBoxLayout)

        self.context_label = QLabel()
        self.context_label.setObjectName("quickIntakeContextHint")
        self.context_label.setWordWrap(True)
        capture_layout.addWidget(self.context_label)

        self.source_preview_label = QLabel(
            "Source preview: drop a file or URL, then preview Summarize, Q&A, or Cloze."
        )
        self.source_preview_label.setObjectName("quickIntakeSupportingText")
        self.source_preview_label.setWordWrap(True)
        capture_layout.addWidget(self.source_preview_label)

        self.source_details_label = QLabel("Source details: waiting for a file or URL")
        self.source_details_label.setObjectName("quickIntakeStatusTone")
        self.source_details_label.setWordWrap(True)
        capture_layout.addWidget(self.source_details_label)

        self.workspace_section = self._make_section(layout, "LLM workspace")
        workspace_layout = self.workspace_section.layout()
        assert isinstance(workspace_layout, QVBoxLayout)

        self.llm_status_label = QLabel("LLM status: not configured")
        self.llm_status_label.setObjectName("quickIntakeStatusTone")
        self.llm_status_label.setWordWrap(True)
        workspace_layout.addWidget(self.llm_status_label)

        self.codex_status_label = QLabel("Codex connection: not connected")
        self.codex_status_label.setObjectName("quickIntakeSupportingText")
        self.codex_status_label.setWordWrap(True)
        workspace_layout.addWidget(self.codex_status_label)

        workspace_label = QLabel(
            "Preview first: choose how an LLM should turn this source into cards."
        )
        workspace_label.setObjectName("quickIntakeSupportingText")
        workspace_label.setWordWrap(True)
        workspace_layout.addWidget(workspace_label)

        llm_actions = QHBoxLayout()
        llm_actions.setSpacing(8)

        self.summarize_button = QPushButton("Summarize")
        self.summarize_button.setObjectName("quickIntakePrimaryAction")
        self.summarize_button.setAutoDefault(False)
        qconnect(self.summarize_button.clicked, lambda: on_llm_action("Summarize"))
        llm_actions.addWidget(self.summarize_button)

        qa_label = "Q&A"
        self.qa_button = QPushButton(qa_label.replace("&", "&&"))
        self.qa_button.setObjectName("quickIntakePrimaryAction")
        self.qa_button.setAutoDefault(False)
        qconnect(self.qa_button.clicked, lambda: on_llm_action(qa_label))
        llm_actions.addWidget(self.qa_button)

        self.cloze_button = QPushButton("Cloze")
        self.cloze_button.setObjectName("quickIntakePrimaryAction")
        self.cloze_button.setAutoDefault(False)
        qconnect(self.cloze_button.clicked, lambda: on_llm_action("Cloze"))
        llm_actions.addWidget(self.cloze_button)
        llm_actions.addStretch(1)
        workspace_layout.addLayout(llm_actions)

        self.status_label = QLabel(
            "Tip: use capture::inbox plus source:: tags so imported material stays easy to triage later."
        )
        self.status_label.setObjectName("quickIntakeSupportingText")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.setStyleSheet(
            """
#quickIntakeFrame {
  border: 1px solid palette(midlight);
  border-radius: 18px;
  background: palette(base);
}
#quickIntakeFrame[dragActive="true"] {
  border: 2px solid palette(highlight);
  background: palette(alternate-base);
}
QFrame#quickIntakeSection {
  border: 1px solid palette(midlight);
  border-radius: 14px;
  background: palette(alternate-base);
}
QLabel#quickIntakeEyebrow {
  font-size: 11px;
  font-weight: 700;
  color: palette(highlight);
  letter-spacing: 0.08em;
}
QLabel#quickIntakeHeadline {
  font-size: 18px;
  font-weight: 700;
}
QLabel#quickIntakeBody {
  font-size: 13px;
}
QLabel#quickIntakeSectionTitle {
  font-size: 13px;
  font-weight: 700;
}
QLabel#quickIntakeChip {
  border: 1px solid palette(midlight);
  border-radius: 999px;
  background: palette(window);
  padding: 4px 10px;
  font-weight: 600;
}
QLabel#quickIntakeContextHint,
QLabel#quickIntakeSupportingText {
  font-size: 12px;
}
QLabel#quickIntakeStatusTone {
  border-left: 3px solid palette(highlight);
  padding-left: 10px;
  font-size: 12px;
}
QPushButton#quickIntakePrimaryAction,
QPushButton#quickIntakeAccentAction,
QPushButton#quickIntakeGhostAction {
  min-height: 30px;
  padding: 4px 12px;
  border-radius: 9px;
  font-weight: 600;
}
QPushButton#quickIntakePrimaryAction {
  border: 1px solid palette(midlight);
  background: palette(button);
}
QPushButton#quickIntakeAccentAction {
  border: 1px solid palette(highlight);
  background: palette(window);
}
QPushButton#quickIntakeGhostAction {
  border: 1px solid transparent;
  background: transparent;
}
QPushButton#quickIntakePrimaryAction:disabled,
QPushButton#quickIntakeAccentAction:disabled,
QPushButton#quickIntakeGhostAction:disabled {
  color: palette(mid);
  border-color: palette(midlight);
}
"""
        )

    def _make_section(self, parent_layout: QVBoxLayout, title: str) -> QFrame:
        section = QFrame()
        section.setObjectName("quickIntakeSection")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(12, 12, 12, 12)
        section_layout.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName("quickIntakeSectionTitle")
        section_layout.addWidget(heading)
        parent_layout.addWidget(section)
        return section

    def _set_drag_active(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def set_context(self, *, deck_name: str, note_type_name: str) -> None:
        self.deck_chip.setText(f"Deck: {deck_name}")
        self.note_type_chip.setText(f"Note type: {note_type_name}")
        self.context_label.setText(
            f"Cards will land in <b>{deck_name}</b> using the <b>{note_type_name}</b> note type."
        )

    def set_llm_status(self, text: str) -> None:
        self.llm_status_label.setText(text)

    def set_codex_status(self, text: str) -> None:
        self.codex_status_label.setText(text)

    def set_source_preview(self, text: str) -> None:
        self.source_preview_label.setText(text)

    def set_source_details(self, text: str) -> None:
        self.source_details_label.setText(text)

    def set_llm_actions_enabled(self, enabled: bool) -> None:
        self.summarize_button.setEnabled(enabled)
        self.qa_button.setEnabled(enabled)
        self.cloze_button.setEnabled(enabled)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        mime = event.mimeData()
        if mime.hasUrls():
            self._set_drag_active(True)
            event.acceptProposedAction()
            return
        if mime.hasText() and re.match(r"https?://", mime.text().strip()):
            self._set_drag_active(True)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drag_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        mime = event.mimeData()
        files: list[str] = []
        urls: list[str] = []
        if mime.hasUrls():
            for qurl in mime.urls():
                if qurl.isLocalFile():
                    files.append(qurl.toLocalFile())
                else:
                    url = qurl.toString().strip()
                    if url:
                        urls.append(url)
        elif mime.hasText():
            text = mime.text().strip()
            if re.match(r"https?://", text):
                urls.append(text)

        self._set_drag_active(False)
        if files or urls:
            self._on_drop(files, urls)
            event.acceptProposedAction()
            return

        super().dropEvent(event)


def _apply_llm_env(cfg: dict[str, str]) -> None:
    """Apply a saved LLM config to environment variables consumed by llm_generate."""
    from aqt.llm_generate import apply_llm_config

    apply_llm_config(cfg)


class AddCards(QMainWindow):
    def __init__(self, mw: AnkiQt) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self._close_event_has_cleaned_up = False
        self.mw = mw
        self.col = mw.col
        form = aqt.forms.addcards.Ui_Dialog()
        form.setupUi(self)
        self.form = form
        self.setWindowTitle(f"{tr.actions_add()} / Capture")
        self.setMinimumHeight(720)
        self.setMinimumWidth(900)
        if mw.pm.profile is not None:
            saved_cfg = mw.pm.profile.get("llm_config")
            if isinstance(saved_cfg, dict):
                _apply_llm_env(saved_cfg)
        self.setup_choosers()
        self.setup_intake_panel()
        self.setupEditor()
        self._load_new_note()
        self.setupButtons()
        self.history: list[NoteId] = []
        self._last_added_note: Note | None = None
        gui_hooks.operation_did_execute.append(self.on_operation_did_execute)
        restoreGeom(self, "add", default_size=(1020, 880))
        gui_hooks.add_cards_did_init(self)
        if not is_mac:
            self.setMenuBar(None)
        self.show()

    def set_deck(self, deck_id: DeckId) -> None:
        self.deck_chooser.selected_deck_id = deck_id

    def set_note_type(self, note_type_id: NotetypeId) -> None:
        self.notetype_chooser.selected_notetype_id = note_type_id

    def set_note(self, note: Note, deck_id: DeckId | None = None) -> None:
        """Set tags, field contents and notetype according to `note`. Deck is set
        to `deck_id` or the deck last used with the notetype.
        """
        self.notetype_chooser.selected_notetype_id = note.mid
        if deck_id or (deck_id := self.col.default_deck_for_notetype(note.mid)):
            self.deck_chooser.selected_deck_id = deck_id

        new_note = self._new_note()
        new_note.fields = note.fields[:]
        new_note.tags = note.tags[:]

        self.editor.orig_note_id = note.id
        self.setAndFocusNote(new_note)

    def setup_intake_panel(self) -> None:
        self.intake_frame = QuickIntakeFrame(
            on_drop=self._ingest_dropped_content,
            on_choose_files=self._show_intake_file_picker,
            on_paste_url=self._prompt_for_source_url,
            on_llm_setup=self._show_llm_setup,
            on_codex_connect=self._show_codex_connect,
            on_llm_action=self._show_llm_action,
            on_organize=self._organize_current_note,
        )
        layout = self.form.centralwidget.layout()
        assert layout is not None
        # layout is a QVBoxLayout per addcards.ui
        from aqt.qt import QVBoxLayout

        assert isinstance(layout, QVBoxLayout)
        layout.insertWidget(1, self.intake_frame)
        self._last_source_summary: str | None = None
        self._update_intake_context()
        self._refresh_codex_connection()
        self._reset_source_workflow()

    def _update_intake_context(self) -> None:
        self.intake_frame.set_context(
            deck_name=self.deck_chooser.selected_deck_name(),
            note_type_name=self.notetype_chooser.selected_notetype_name(),
        )

    def _update_intake_status(self, message: str) -> None:
        self.intake_frame.set_status(message)

    def _codex_api_key_present(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def _codex_preferred(self) -> bool:
        assert self.mw.pm.profile is not None
        return bool(self.mw.pm.profile.get("codexProviderPreferred", False))

    def _set_codex_preferred(self, enabled: bool) -> None:
        assert self.mw.pm.profile is not None
        self.mw.pm.profile["codexProviderPreferred"] = enabled

    def _refresh_codex_connection(self) -> None:
        if self._codex_preferred() and self._codex_api_key_present():
            self.intake_frame.set_codex_status(
                "Codex connection: OPENAI_API_KEY detected • Codex preferred provider • ready for preview-first actions"
            )
        elif self._codex_preferred():
            self.intake_frame.set_codex_status(
                "Codex connection: Codex preferred provider selected • add OPENAI_API_KEY to enable preview-first actions"
            )
        elif self._codex_api_key_present():
            self.intake_frame.set_codex_status(
                "Codex connection: available • press Connect Codex to make it the preferred provider"
            )
        else:
            self.intake_frame.set_codex_status(
                "Codex connection: not connected • press Connect Codex or set OPENAI_API_KEY"
            )

    def _reset_source_workflow(self) -> None:
        self._last_source_summary = None
        self._captured_source_text: str = ""
        self._captured_source_title: str = ""
        self._captured_source_url: str = ""
        self._refresh_llm_readiness()
        self.intake_frame.set_source_preview(
            "Source preview: drop a file or URL, then preview Summarize, Q&A, or Cloze."
        )
        self.intake_frame.set_source_details(
            "Source details: waiting for a file or URL"
        )
        self.intake_frame.set_llm_actions_enabled(False)

    def _fetch_source_url(self, url: str) -> tuple[str, str]:
        """Fetch a URL and extract its main textual content. Returns (title, text)."""
        import requests
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 Anki-LLM-Capture/1.0"
            )
        }
        resp = requests.get(url, headers=headers, timeout=30)
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
            text = el.get_text(" ", strip=True)
            if text:
                parts.append(text)
        text = "\n\n".join(parts)
        # Cap to keep prompts under provider context limits.
        return title, text[:80_000]

    def _refresh_llm_readiness(self, source_summary: str | None = None) -> None:
        if source_summary is not None:
            self._last_source_summary = source_summary
        if self._last_source_summary:
            if self._codex_preferred() and self._codex_api_key_present():
                self.intake_frame.set_llm_status(
                    f"LLM status: Codex preferred provider ready for Summarize, Q&A, or Cloze on {self._last_source_summary}"
                )
            elif self._codex_preferred():
                self.intake_frame.set_llm_status(
                    "LLM status: Codex preferred provider selected • add OPENAI_API_KEY to enable Summarize, Q&A, and Cloze previews"
                )
            elif self._codex_api_key_present():
                self.intake_frame.set_llm_status(
                    f"LLM status: Codex ready for Summarize, Q&A, or Cloze on {self._last_source_summary}"
                )
            else:
                self.intake_frame.set_llm_status(
                    f"LLM status: ready for Summarize, Q&A, or Cloze on {self._last_source_summary} once provider is configured"
                )
        elif self._codex_preferred() and self._codex_api_key_present():
            self.intake_frame.set_llm_status(
                "LLM status: Codex preferred provider connected • capture a source to start preview-first actions"
            )
        elif self._codex_preferred():
            self.intake_frame.set_llm_status(
                "LLM status: Codex preferred provider selected • add OPENAI_API_KEY to enable preview-first actions"
            )
        elif self._codex_api_key_present():
            self.intake_frame.set_llm_status(
                "LLM status: Codex connected • capture a source to start preview-first actions"
            )
        else:
            self.intake_frame.set_llm_status(
                "LLM status: provider not configured • preview first with Summarize, Q&A, or Cloze"
            )

    def _update_source_preview(
        self, summary: str, *, selected_action: str | None = None
    ) -> None:
        self._refresh_llm_readiness(summary)
        self.intake_frame.set_llm_actions_enabled(True)
        if selected_action:
            self.intake_frame.set_source_preview(
                f"Source preview: {summary} • selected action: {selected_action} • next step: preview output before writing"
            )
        else:
            self.intake_frame.set_source_preview(
                f"Source preview: {summary} • next step: preview Summarize, Q&A, or Cloze"
            )

    def _update_source_details(
        self, labels: Sequence[str], tags: Sequence[str]
    ) -> None:
        shown_labels = ", ".join(labels[:3])
        if len(labels) > 3:
            shown_labels += ", …"
        shown_tags = " • ".join(tags[:4])
        self.intake_frame.set_source_details(
            f"Source details: {shown_labels}\nTags: {shown_tags}"
        )

    def _normalize_tag(self, text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        return cleaned or "source"

    def _append_tags(self, *tags: str) -> None:
        note = self.editor.note
        if not note:
            return
        changed = False
        for tag in tags:
            if tag and tag not in note.tags:
                note.tags.append(tag)
                changed = True
        if changed:
            self.editor.web.eval(f"setTags({json.dumps(note.tags)});")

    def _paste_html_into_current_note(self, html: str) -> None:
        def insert() -> None:
            self.editor.doPaste(html, True)

        if self.editor.currentField is None:
            self.editor.currentField = 0
            self.editor.web.evalWithCallback(
                "focusField(0); true;", lambda _ret: insert()
            )
        else:
            insert()

    def _insert_source_links(self, sources: Sequence[str], *, source_kind: str) -> None:
        if not sources:
            return

        html_parts: list[str] = []
        deck_tag = (
            f"deck::{self._normalize_tag(self.deck_chooser.selected_deck_name())}"
        )
        type_tag = f"type::{self._normalize_tag(self.notetype_chooser.selected_notetype_name())}"
        tags = ["capture::inbox", deck_tag, type_tag]
        labels: list[str] = []
        for source in sources:
            if source_kind == "file":
                link = self.editor.urlToLink(QUrl.fromLocalFile(source).toString())
                labels.append(os.path.basename(source))
                stem = os.path.splitext(os.path.basename(source))[0]
                tags.append(f"source::file::{self._normalize_tag(stem)}")
            else:
                normalized = QUrl.fromUserInput(source).toString()
                link = self.editor.urlToLink(normalized)
                parsed = urllib.parse.urlparse(normalized)
                labels.append(parsed.netloc or normalized)
                tags.append(
                    f"source::web::{self._normalize_tag(parsed.netloc or normalized)}"
                )
            html_parts.append(link)

        self._paste_html_into_current_note("<br>".join(html_parts))
        self._append_tags(*tags)
        self._update_source_details(labels, tags)
        summary = ", ".join(labels[:3])
        if len(labels) > 3:
            summary += ", …"
        plural = "" if len(labels) == 1 else "s"
        self._update_source_preview(summary)
        self._update_intake_status(
            f"Added {len(labels)} {source_kind}{plural} to the current note • tags: capture::inbox • {deck_tag} • {type_tag} • source::{source_kind}::*"
        )
        tooltip(f"Captured: {summary}", period=1200)

    def _show_intake_file_picker(self) -> None:
        result = getFile(
            self,
            title="Choose files to learn from",
            cb=None,
            key="quickIntake",
            multi=True,
        )
        if not result:
            return
        paths = [path for path in result if path]
        self._insert_source_links(paths, source_kind="file")

    def _prompt_for_source_url(self) -> None:
        from aqt.llm_generate import (
            LLMError,
            generate_cards,
            get_api_key,
            is_local_available,
        )

        # Reapply any saved profile config so generation has the right keys.
        if self.mw.pm.profile is not None:
            saved_cfg = self.mw.pm.profile.get("llm_config")
            if isinstance(saved_cfg, dict):
                _apply_llm_env(saved_cfg)

        if not get_api_key() and not is_local_available():
            showWarning(
                "No LLM backend configured.\n\n"
                "Click “LLM setup” in the intake panel and add an Anthropic or OpenAI API key first.",
                parent=self,
            )
            return

        url, num_cards, ok = self._ask_url_and_count()
        if not ok or not url:
            return

        auto_count = num_cards == 0

        self.intake_frame.set_llm_actions_enabled(False)
        self.intake_frame.set_status(f"Fetching {url}…")
        self.intake_frame.set_llm_status(f"LLM status: fetching {url}…")

        def task() -> dict[str, object]:
            title, content = self._fetch_source_url(url)
            if not content.strip():
                return {"error": "No textual content extracted from that URL."}
            requested_n = self._optimal_card_count(content) if auto_count else num_cards
            self.mw.taskman.run_on_main(
                lambda label=title or url,
                n=requested_n: self.intake_frame.set_llm_status(
                    f"LLM status: generating {n} cards from {label}…"
                )
            )
            result = generate_cards(
                content,
                "qa",
                num_cards=requested_n,
                context=(
                    f"Source URL: {url}\nSource title: {title}"
                    if title
                    else f"Source URL: {url}"
                ),
            )
            return {"title": title, "result": result, "requested_n": requested_n}

        def on_done(future: Future) -> None:
            try:
                payload = future.result()
            except LLMError as exc:
                showWarning(f"LLM error:\n{exc}", parent=self)
                self.intake_frame.set_status(f"LLM error: {exc}")
                return
            except Exception as exc:
                showWarning(f"Could not fetch URL:\n{exc}", parent=self)
                self.intake_frame.set_status(f"Fetch failed: {exc}")
                return
            if "error" in payload:
                showWarning(str(payload["error"]), parent=self)
                self.intake_frame.set_status(str(payload["error"]))
                return
            title = str(payload.get("title", "") or "")
            result = payload["result"]
            from aqt.llm_generate import GenerationResult

            assert isinstance(result, GenerationResult)
            if not result.cards:
                showWarning(
                    "LLM returned no usable cards. Try increasing the count or changing model.",
                    parent=self,
                )
                self.intake_frame.set_status("LLM returned no cards.")
                return
            # Always create/use a topic_<date> deck for LLM-generated cards
            # (must run on the main thread — touches the collection).
            deck_id = self._target_deck_for_url(url, title)
            deck_name = self.col.decks.name(deck_id) or "(unknown)"
            added = self._add_cards_from_url(
                result.cards,
                deck_id,
                source_url=url,
                source_title=title,
            )
            label = title or url
            requested = int(payload.get("requested_n", added) or added)
            count_note = f" (auto-sized to {requested})" if auto_count else ""
            self.intake_frame.set_status(
                f"Added {added} cards from {label} → deck “{deck_name}”{count_note}"
            )
            self.intake_frame.set_llm_status(
                f"LLM status: added {added}/{len(result.cards)} cards with {result.model_used} → {deck_name}{count_note}"
            )
            tooltip(f"Added {added} cards to {deck_name}{count_note}", period=3000)

        self.mw.taskman.run_in_background(task, on_done)

    def _ask_url_and_count(self) -> tuple[str, int, bool]:
        """Ask for URL + number of cards. Returns (url, n, ok).

        ``n == 0`` means "auto-determine from article length" — the caller will
        compute it after fetching.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle("Paste a URL — generate Q&A cards")
        dlg.setMinimumWidth(560)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)

        intro = QLabel(
            "Anki will fetch the page, extract the main text, and add Q&A cards "
            "to a new deck named <code>&lt;topic&gt;_&lt;today&gt;</code> "
            "(topic from the article title; created if it doesn't exist)."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("URL:"))
        url_edit = QLineEdit()
        url_edit.setPlaceholderText("https://example.com/article")
        url_row.addWidget(url_edit)
        layout.addLayout(url_row)

        assert self.mw.pm.profile is not None
        saved_n = int(self.mw.pm.profile.get("llm_url_card_count", 0) or 0)
        saved_auto = bool(self.mw.pm.profile.get("llm_url_card_count_auto", True))

        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("Cards:"))
        auto_check = QCheckBox("Auto (from article length)")
        auto_check.setChecked(saved_auto)
        count_row.addWidget(auto_check)
        count_spin = QSpinBox()
        count_spin.setRange(1, 50)
        count_spin.setValue(saved_n if saved_n > 0 else 10)
        count_spin.setEnabled(not saved_auto)
        count_row.addWidget(count_spin)
        count_row.addStretch(1)
        layout.addLayout(count_row)

        qconnect(
            auto_check.stateChanged,
            lambda _: count_spin.setEnabled(not auto_check.isChecked()),
        )

        hint = QLabel(
            "Auto picks roughly one card per 150 words of extracted text, "
            "clamped between 3 and 25."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        layout.addWidget(hint)

        deck_label = QLabel(
            "Deck: <i>auto — “&lt;topic&gt;_&lt;today&gt;” based on the article title</i>"
        )
        deck_label.setWordWrap(True)
        layout.addWidget(deck_label)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(btns)
        qconnect(btns.accepted, dlg.accept)
        qconnect(btns.rejected, dlg.reject)

        url_edit.setFocus()
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return "", 0, False
        url = url_edit.text().strip()
        if not url:
            return "", 0, False
        if not re.match(r"^https?://", url, re.IGNORECASE):
            url = "https://" + url

        is_auto = auto_check.isChecked()
        self.mw.pm.profile["llm_url_card_count_auto"] = is_auto
        if not is_auto:
            self.mw.pm.profile["llm_url_card_count"] = count_spin.value()
            return url, count_spin.value(), True
        # 0 signals "auto" — the caller computes after fetching.
        return url, 0, True

    @staticmethod
    def _optimal_card_count(text: str) -> int:
        """Heuristic: ~1 card per 150 words of extracted content, clamped [3, 25]."""
        words = len(text.split())
        return max(3, min(25, words // 150))

    @staticmethod
    def _slugify_topic(text: str, max_len: int = 50) -> str:
        """Turn an article title or URL fragment into a deck-safe slug."""
        text = (text or "").strip()
        if not text:
            return "untitled"
        # drop anything that's not word chars / spaces / hyphens
        text = re.sub(r"[^\w\s\-]", " ", text)
        text = re.sub(r"[\s\-_]+", "_", text).strip("_").lower()
        if not text:
            return "untitled"
        return text[:max_len].rstrip("_") or "untitled"

    def _target_deck_for_url(self, url: str, title: str) -> DeckId:
        """Create-or-find a `topic_YYYY-MM-DD` deck for LLM-generated cards.

        Topic comes from the article title; falls back to URL hostname.
        """
        from datetime import date

        topic_source = title.strip() if title else ""
        if not topic_source:
            try:
                topic_source = urllib.parse.urlparse(url).netloc or url
            except Exception:
                topic_source = url
        slug = self._slugify_topic(topic_source)
        deck_name = f"{slug}_{date.today().isoformat()}"
        return DeckId(self.col.decks.id(deck_name, create=True))

    def _add_cards_from_url(
        self,
        cards: Sequence,
        deck_id: DeckId,
        *,
        source_url: str,
        source_title: str,
    ) -> int:
        """Add Front/Back cards generated from a URL directly to deck_id."""
        col = self.col
        basic = col.models.by_name("Basic") or col.models.current()
        added = 0
        for card in cards:
            note = col.new_note(basic)
            if len(note.fields) >= 1:
                note.fields[0] = card.front
            if len(note.fields) >= 2:
                back = card.back
                if source_url:
                    label = source_title or source_url
                    back = (
                        f"{back}<br><br>"
                        f'<i>Source: <a href="{source_url}">{label}</a></i>'
                    )
                note.fields[1] = back
            note.tags = (
                list(card.tags)
                if getattr(card, "tags", None)
                else [
                    "llm-generated",
                    "from-url",
                ]
            )
            try:
                col.add_note(note, deck_id)
                added += 1
            except Exception:
                pass
        self.mw.reset()
        return added

    def _show_llm_setup(self) -> None:
        from aqt.llm_generate import DEFAULT_API_MODEL

        assert self.mw.pm.profile is not None
        cfg = dict(self.mw.pm.profile.get("llm_config", {}))

        dlg = QDialog(self)
        dlg.setWindowTitle("LLM setup")
        dlg.setMinimumWidth(520)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)

        intro = QLabel(
            "Pick a provider and paste an API key. Settings persist per profile and "
            "are also exposed via environment variables to llm_generate.py."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("Provider:"))
        provider_combo = QComboBox()
        provider_combo.addItems(["claude", "openai", "gemini", "local"])
        provider_combo.setCurrentText(cfg.get("provider", "claude"))
        provider_row.addWidget(provider_combo)
        provider_row.addStretch(1)
        layout.addLayout(provider_row)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))
        model_edit = QLineEdit()
        model_edit.setPlaceholderText("(provider default)")
        model_edit.setText(cfg.get("model", ""))
        model_row.addWidget(model_edit)
        layout.addLayout(model_row)

        claude_row = QHBoxLayout()
        claude_row.addWidget(QLabel("Anthropic key:"))
        claude_edit = QLineEdit()
        claude_edit.setEchoMode(QLineEdit.EchoMode.Password)
        claude_edit.setText(cfg.get("anthropic_api_key", ""))
        claude_row.addWidget(claude_edit)
        layout.addLayout(claude_row)

        openai_row = QHBoxLayout()
        openai_row.addWidget(QLabel("OpenAI key:"))
        openai_edit = QLineEdit()
        openai_edit.setEchoMode(QLineEdit.EchoMode.Password)
        openai_edit.setText(cfg.get("openai_api_key", ""))
        openai_row.addWidget(openai_edit)
        layout.addLayout(openai_row)

        gemini_row = QHBoxLayout()
        gemini_row.addWidget(QLabel("Gemini key:"))
        gemini_edit = QLineEdit()
        gemini_edit.setEchoMode(QLineEdit.EchoMode.Password)
        gemini_edit.setText(cfg.get("gemini_api_key", ""))
        gemini_row.addWidget(gemini_edit)
        layout.addLayout(gemini_row)

        show_keys = QCheckBox("Show keys")
        layout.addWidget(show_keys)

        def _toggle_echo() -> None:
            mode = (
                QLineEdit.EchoMode.Normal
                if show_keys.isChecked()
                else QLineEdit.EchoMode.Password
            )
            claude_edit.setEchoMode(mode)
            openai_edit.setEchoMode(mode)
            gemini_edit.setEchoMode(mode)

        qconnect(show_keys.stateChanged, lambda _: _toggle_echo())

        hint = QLabel("")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        layout.addWidget(hint)

        def _refresh_hint() -> None:
            provider = provider_combo.currentText()
            default = DEFAULT_API_MODEL.get(provider, "(local)")
            hint.setText(f"Default model for {provider}: {default}")

        qconnect(provider_combo.currentTextChanged, lambda _: _refresh_hint())
        _refresh_hint()

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(btns)
        qconnect(btns.accepted, dlg.accept)
        qconnect(btns.rejected, dlg.reject)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new_cfg = {
            "provider": provider_combo.currentText(),
            "model": model_edit.text().strip(),
            "anthropic_api_key": claude_edit.text().strip(),
            "openai_api_key": openai_edit.text().strip(),
            "gemini_api_key": gemini_edit.text().strip(),
        }
        self.mw.pm.profile["llm_config"] = new_cfg
        _apply_llm_env(new_cfg)

        self.intake_frame.set_llm_status(
            f"LLM status: {new_cfg['provider']} configured • "
            f"model {new_cfg['model'] or DEFAULT_API_MODEL.get(new_cfg['provider'], '(local)')}"
        )
        self._refresh_llm_readiness(self._last_source_summary)
        self._refresh_codex_connection()

    def _show_codex_connect(self) -> None:
        self._set_codex_preferred(True)
        self._refresh_codex_connection()
        self._refresh_llm_readiness(self._last_source_summary)
        if self._codex_api_key_present():
            showInfo(
                "Codex preferred provider selected.\n\nOPENAI_API_KEY was detected, so Codex is ready to handle Summarize, Q&A, and Cloze previews.",
                parent=self,
            )
        else:
            showInfo(
                "Codex preferred provider selected.\n\nAdd OPENAI_API_KEY to your environment to let Codex handle Summarize, Q&A, and Cloze previews from this workspace.",
                parent=self,
            )

    def _show_llm_action(self, action: str) -> None:
        from aqt.llm_generate import ActionType

        target = self._last_source_summary or "the current note"
        # Map UI action names to generation types
        action_map: dict[str, ActionType] = {
            "Summarize": "summarize",
            "Q&A": "qa",
            "Cloze": "cloze",
        }
        gen_action: ActionType = action_map.get(action, "qa")

        # Source text: prefer fetched URL/file content, otherwise note fields.
        note = self.editor.note
        if note is None:
            showWarning("No note loaded.", parent=self)
            return

        captured = getattr(self, "_captured_source_text", "")
        if captured.strip():
            source_text = captured
            if self._captured_source_title:
                target = self._captured_source_title
            elif self._captured_source_url:
                target = self._captured_source_url
        else:
            source_text = "\n".join(
                html_to_text_line(field) if "<" in field else field
                for field in note.fields
                if field.strip()
            )
        if not source_text.strip():
            showWarning(
                "No source text yet. Paste a URL, drop a file, or type into a field first.",
                parent=self,
            )
            return

        self.intake_frame.set_llm_status(
            f"LLM status: generating {action} from {target}…"
        )
        self._update_source_preview(target, selected_action=action)

        # Run generation in a thread to avoid blocking the UI
        from aqt.llm_generate import (
            LLMError,
            generate_cards,
            get_api_key,
            is_local_available,
        )

        if not get_api_key() and not is_local_available():
            showWarning(
                "No LLM backend configured.\n\n"
                "Open “LLM setup” to set a provider and API key, or:\n"
                "• Set ANTHROPIC_API_KEY (Claude) or OPENAI_API_KEY (OpenAI)\n"
                "• Install mlx-lm for local inference: pip install mlx-lm",
                parent=self,
            )
            self.intake_frame.set_llm_status("LLM status: no backend available")
            return

        context = f"Deck: {self.deck_chooser.selected_deck_name()}"

        def do_generate() -> None:
            try:
                from aqt.llm_generate import ensure_local_model

                # Auto-download model on first use if using local backend
                if is_local_available() and not get_api_key():
                    self.mw.taskman.run_on_main(
                        lambda: self.intake_frame.set_llm_status(
                            "LLM status: checking local model…"
                        )
                    )
                    ready, status = ensure_local_model()
                    if not ready:
                        self.mw.taskman.run_on_main(
                            lambda: self._handle_llm_error(
                                f"Local model not ready: {status}"
                            )
                        )
                        return
                    self.mw.taskman.run_on_main(
                        lambda: self.intake_frame.set_llm_status(
                            f"LLM status: {status} — generating {action}…"
                        )
                    )

                result = generate_cards(source_text, gen_action, context=context)
                self.mw.taskman.run_on_main(
                    lambda: self._apply_llm_result(result, action)
                )
            except LLMError as llm_err:
                err_msg = str(llm_err)
                self.mw.taskman.run_on_main(
                    lambda err=err_msg: self._handle_llm_error(err)  # type: ignore[misc]
                )

        self.mw.taskman.run_in_background(do_generate)

    def _apply_llm_result(self, result: object, action: str) -> None:
        """Apply LLM generation results to the current note."""
        from aqt.llm_generate import GenerationResult

        if not isinstance(result, GenerationResult):
            return

        note = self.editor.note
        if note is None:
            return

        added_count = 0

        if result.action == "qa" and result.cards:
            # Add all generated Q&A pairs as separate notes
            deck_id = self.deck_chooser.selected_deck_id
            for card in result.cards:
                new_note = self.col.new_note(note.note_type())
                if len(new_note.fields) >= 1:
                    new_note.fields[0] = card.front
                if len(new_note.fields) >= 2:
                    new_note.fields[1] = card.back
                new_note.tags = list(card.tags)
                try:
                    self.col.add_note(new_note, deck_id)
                    added_count += 1
                except Exception:
                    pass  # skip duplicates or invalid notes

            self.intake_frame.set_llm_status(
                f"LLM status: added {added_count}/{len(result.cards)} Q&A cards with {result.model_used}"
            )

        elif result.action == "cloze" and result.clozes:
            # Switch to a Cloze notetype if current notetype isn't one
            current_nt = note.note_type()
            if current_nt and not any(
                "cloze" in t["qfmt"].lower() or "cloze" in t.get("afmt", "").lower()
                for t in current_nt.get("tmpls", [])
            ):
                # Try to find and switch to the built-in Cloze notetype
                for nt in self.col.models.all_names_and_ids():
                    if "cloze" in nt.name.lower():
                        self.notetype_chooser.selected_notetype_id = NotetypeId(nt.id)
                        self.on_notetype_change(NotetypeId(nt.id))
                        note = self.editor.note
                        if note is None:
                            return
                        break

            if len(note.fields) >= 1:
                note.fields[0] = result.clozes[0].text
            self.editor.loadNote()

            self.intake_frame.set_llm_status(
                f"LLM status: generated {len(result.clozes)} cloze cards with {result.model_used}"
            )

        elif result.action == "summarize" and result.summary:
            target_idx = 1 if len(note.fields) >= 2 else 0
            note.fields[target_idx] = result.summary
            self.editor.loadNote()

            self.intake_frame.set_llm_status(
                f"LLM status: generated summary with {result.model_used}"
            )

        if added_count > 0:
            # Reset editor for next note
            self.mw.reset()
            self.set_note(self.col.new_note(note.note_type()), None)
            tooltip(
                f"Added {added_count} {action} cards to deck",
                period=2000,
            )
        else:
            # Reload editor to show field changes
            if result.action != "qa":
                current_tags = note.string_tags()
                if "ai-generated" not in current_tags:
                    note.tags.append("ai-generated")
                    self.editor.loadNote()
            tooltip(
                f"{action} generated with {result.model_used}",
                period=2000,
            )

    def _handle_llm_error(self, error_msg: str) -> None:
        """Handle LLM generation errors."""
        self.intake_frame.set_llm_status("LLM status: generation failed")
        showWarning(f"LLM generation failed:\n\n{error_msg}", parent=self)

    def _organize_current_note(self) -> None:
        deck_tag = (
            f"deck::{self._normalize_tag(self.deck_chooser.selected_deck_name())}"
        )
        type_tag = f"type::{self._normalize_tag(self.notetype_chooser.selected_notetype_name())}"
        self._append_tags("capture::inbox", deck_tag, type_tag)
        self._update_intake_status(
            f"Applied organization tags • capture::inbox • {deck_tag} • {type_tag}"
        )
        tooltip("Organization tags added", period=1200)

    def _ingest_dropped_content(
        self, files: Sequence[str], urls: Sequence[str]
    ) -> None:
        if files:
            self._insert_source_links(files, source_kind="file")
        if urls:
            self._insert_source_links(urls, source_kind="web")

    def setupEditor(self) -> None:
        self.editor = aqt.editor.Editor(
            self.mw,
            self.form.fieldsArea,
            self,
            editor_mode=aqt.editor.EditorMode.ADD_CARDS,
        )

    def setup_choosers(self) -> None:
        defaults = self.col.defaults_for_adding(
            current_review_card=self.mw.reviewer.card
        )

        self.notetype_chooser = NotetypeChooser(
            mw=self.mw,
            widget=self.form.modelArea,
            starting_notetype_id=NotetypeId(defaults.notetype_id),
            on_button_activated=self.show_notetype_selector,
            on_notetype_changed=self.on_notetype_change,
        )
        self.deck_chooser = DeckChooser(
            self.mw,
            self.form.deckArea,
            starting_deck_id=DeckId(defaults.deck_id),
            on_deck_changed=self.on_deck_changed,
        )

    def reopen(self, mw: AnkiQt) -> None:
        if not self.editor.fieldsAreBlank():
            return

        defaults = self.col.defaults_for_adding(
            current_review_card=self.mw.reviewer.card
        )
        self.set_note_type(NotetypeId(defaults.notetype_id))
        self.set_deck(DeckId(defaults.deck_id))

    def helpRequested(self) -> None:
        openHelp(HelpPage.ADDING_CARD_AND_NOTE)

    def setupButtons(self) -> None:
        bb = self.form.buttonBox
        ar = QDialogButtonBox.ButtonRole.ActionRole
        # add
        self.addButton = bb.addButton(tr.actions_add(), ar)
        qconnect(self.addButton.clicked, self.add_current_note)
        self.addButton.setShortcut(QKeySequence("Ctrl+Return"))
        # qt5.14+ doesn't handle numpad enter on Windows
        self.compat_add_shorcut = QShortcut(QKeySequence("Ctrl+Enter"), self)
        qconnect(self.compat_add_shorcut.activated, self.addButton.click)
        self.addButton.setToolTip(shortcut(tr.adding_add_shortcut_ctrlandenter()))

        # close
        self.closeButton = QPushButton(tr.actions_close())
        self.closeButton.setAutoDefault(False)
        bb.addButton(self.closeButton, QDialogButtonBox.ButtonRole.RejectRole)
        qconnect(self.closeButton.clicked, self.close)
        # help
        self.helpButton = QPushButton(tr.actions_help(), clicked=self.helpRequested)  # type: ignore
        self.helpButton.setAutoDefault(False)
        bb.addButton(self.helpButton, QDialogButtonBox.ButtonRole.HelpRole)
        # history
        b = bb.addButton(f"{tr.adding_history()} {downArrow()}", ar)
        if is_mac:
            sc = "Ctrl+Shift+H"
        else:
            sc = "Ctrl+H"
        b.setShortcut(QKeySequence(sc))
        b.setToolTip(tr.adding_shortcut(val=shortcut(sc)))
        qconnect(b.clicked, self.onHistory)
        b.setEnabled(False)
        self.historyButton = b

    def setAndFocusNote(self, note: Note) -> None:
        self.editor.set_note(note, focusTo=0)

    def show_notetype_selector(self) -> None:
        self.editor.call_after_note_saved(self.notetype_chooser.choose_notetype)

    def on_deck_changed(self, deck_id: int) -> None:
        self._update_intake_context()
        gui_hooks.add_cards_did_change_deck(deck_id)

    def on_notetype_change(
        self, notetype_id: NotetypeId, update_deck: bool = True
    ) -> None:
        # need to adjust current deck?
        if update_deck:
            if deck_id := self.col.default_deck_for_notetype(notetype_id):
                self.deck_chooser.selected_deck_id = deck_id

        # only used for detecting changed sticky fields on close
        self._last_added_note = None

        # copy fields into new note with the new notetype
        old_note = self.editor.note
        new_note = self._new_note()
        if old_note:
            old_field_names = list(old_note.keys())
            new_field_names = list(new_note.keys())
            copied_field_names = set()
            for f in new_note.note_type()["flds"]:
                field_name = f["name"]
                # copy identical non-empty fields
                if field_name in old_field_names and old_note[field_name]:
                    new_note[field_name] = old_note[field_name]
                    copied_field_names.add(field_name)
            new_idx = 0
            for old_idx, old_field_value in enumerate(old_field_names):
                # skip previously copied identical fields in new note
                while (
                    new_idx < len(new_field_names)
                    and new_field_names[new_idx] in copied_field_names
                ):
                    new_idx += 1
                if new_idx >= len(new_field_names):
                    break
                # copy non-empty old fields
                if (
                    old_field_value not in copied_field_names
                    and old_note.fields[old_idx]
                ):
                    new_note.fields[new_idx] = old_note.fields[old_idx]
                    new_idx += 1

            new_note.tags = old_note.tags

        # and update editor state
        self._update_intake_context()
        self.editor.note = new_note
        self.editor.loadNote(
            focusTo=min(self.editor.last_field_index or 0, len(new_note.fields) - 1)
        )
        gui_hooks.addcards_did_change_note_type(
            self, old_note.note_type(), new_note.note_type()
        )

    def _load_new_note(self, sticky_fields_from: Note | None = None) -> None:
        note = self._new_note()
        if old_note := sticky_fields_from:
            flds = note.note_type()["flds"]
            # copy fields from old note
            if old_note:
                for n in range(min(len(note.fields), len(old_note.fields))):
                    if flds[n]["sticky"]:
                        note.fields[n] = old_note.fields[n]
            # and tags
            note.tags = old_note.tags
        self.setAndFocusNote(note)
        self._reset_source_workflow()

    def on_operation_did_execute(
        self, changes: OpChanges, handler: object | None
    ) -> None:
        if (changes.notetype or changes.deck) and handler is not self.editor:
            self.on_notetype_change(
                NotetypeId(
                    self.col.defaults_for_adding(
                        current_review_card=self.mw.reviewer.card
                    ).notetype_id
                ),
                update_deck=False,
            )

    def _new_note(self) -> Note:
        return self.col.new_note(
            self.col.models.get(self.notetype_chooser.selected_notetype_id)
        )

    def addHistory(self, note: Note) -> None:
        self.history.insert(0, note.id)
        self.history = self.history[:15]
        self.historyButton.setEnabled(True)

    def onHistory(self) -> None:
        m = QMenu(self)
        for nid in self.history:
            if self.col.find_notes(self.col.build_search_string(SearchNode(nid=nid))):
                note = self.col.get_note(nid)
                fields = note.fields
                txt = html_to_text_line(", ".join(fields))
                if len(txt) > 30:
                    txt = f"{txt[:30]}..."
                line = tr.adding_edit(val=txt)
                line = gui_hooks.addcards_will_add_history_entry(line, note)
                line = line.replace("&", "&&")
                # In qt action "&i" means "underline i, trigger this line when i is pressed".
                # except for "&&" which is replaced by a single "&"
                a = m.addAction(line)
                qconnect(a.triggered, lambda b, nid=nid: self.editHistory(nid))
            else:
                a = m.addAction(tr.adding_note_deleted())
                a.setEnabled(False)
        gui_hooks.add_cards_will_show_history_menu(self, m)
        m.exec(self.historyButton.mapToGlobal(QPoint(0, 0)))

    def editHistory(self, nid: NoteId) -> None:
        aqt.dialogs.open("Browser", self.mw, search=(SearchNode(nid=nid),))

    def add_current_note(self) -> None:
        if self.editor.current_notetype_is_image_occlusion():
            self.editor.update_occlusions_field()
            self.editor.call_after_note_saved(self._add_current_note)
            self.editor.reset_image_occlusion()
        else:
            self.editor.call_after_note_saved(self._add_current_note)

    def _add_current_note(self) -> None:
        note = self.editor.note

        # Prevent adding a note that has already been added (e.g., from double-clicking)
        if note.id != 0:
            return

        if not self._note_can_be_added(note):
            return

        target_deck_id = self.deck_chooser.selected_deck_id

        def on_success(changes: OpChangesWithCount) -> None:
            # only used for detecting changed sticky fields on close
            self._last_added_note = note

            self.addHistory(note)

            tooltip(tr.importing_cards_added(count=changes.count), period=500)
            av_player.stop_and_clear_queue()
            self._load_new_note(sticky_fields_from=note)
            gui_hooks.add_cards_did_add_note(note)

        add_note(parent=self, note=note, target_deck_id=target_deck_id).success(
            on_success
        ).run_in_background()

    def _note_can_be_added(self, note: Note) -> bool:
        result = note.fields_check()
        # no problem, duplicate, and confirmed cloze cases
        problem = None
        if result == NoteFieldsCheckResult.EMPTY:
            if self.editor.current_notetype_is_image_occlusion():
                problem = tr.notetypes_no_occlusion_created2()
            else:
                problem = tr.adding_the_first_field_is_empty()
        elif result == NoteFieldsCheckResult.MISSING_CLOZE:
            if not askUser(tr.adding_you_have_a_cloze_deletion_note()):
                return False
        elif result == NoteFieldsCheckResult.NOTETYPE_NOT_CLOZE:
            problem = tr.adding_cloze_outside_cloze_notetype()
        elif result == NoteFieldsCheckResult.FIELD_NOT_CLOZE:
            problem = tr.adding_cloze_outside_cloze_field()

        # filter problem through add-ons
        problem = gui_hooks.add_cards_will_add_note(problem, note)
        if problem is not None:
            showWarning(problem, help=HelpPage.ADDING_CARD_AND_NOTE)
            return False

        optional_problems: list[str] = []
        gui_hooks.add_cards_might_add_note(optional_problems, note)
        if not all(askUser(op) for op in optional_problems):
            return False

        return True

    def keyPressEvent(self, evt: QKeyEvent) -> None:
        if evt.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(evt)

    def closeEvent(self, evt: QCloseEvent) -> None:
        if self._close_event_has_cleaned_up:
            evt.accept()
            return
        self.ifCanClose(self._close)
        evt.ignore()

    def _close(self) -> None:
        self.editor.cleanup()
        self.notetype_chooser.cleanup()
        self.deck_chooser.cleanup()
        gui_hooks.operation_did_execute.remove(self.on_operation_did_execute)
        self.mw.maybeReset()
        saveGeom(self, "add")
        aqt.dialogs.markClosed("AddCards")
        self._close_event_has_cleaned_up = True
        self.mw.deferred_delete_and_garbage_collect(self)
        self.close()

    def ifCanClose(self, onOk: Callable) -> None:
        def callback(choice: int) -> None:
            if choice == 0:
                onOk()

        def afterSave() -> None:
            if self.editor.fieldsAreBlank(self._last_added_note):
                return onOk()

            ask_user_dialog(
                tr.adding_discard_current_input(),
                callback=callback,
                buttons=[
                    QMessageBox.StandardButton.Discard,
                    (tr.adding_keep_editing(), QMessageBox.ButtonRole.RejectRole),
                ],
            )

        self.editor.call_after_note_saved(afterSave)

    def closeWithCallback(self, cb: Callable[[], None]) -> None:
        def doClose() -> None:
            self._close()
            cb()

        self.ifCanClose(doClose)

    # legacy aliases

    @property
    def deckChooser(self) -> DeckChooser:
        if getattr(self, "form", None):
            # show this warning only after Qt form has been initialized,
            # or PyQt's introspection triggers it
            print("deckChooser is deprecated; use deck_chooser instead")
        return self.deck_chooser

    addCards = add_current_note
    _addCards = _add_current_note
    onModelChange = on_notetype_change

    @deprecated(info="obsolete")
    def addNote(self, note: Note) -> None:
        pass

    @deprecated(info="does nothing; will go away")
    def removeTempNote(self, note: Note) -> None:
        pass
