# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
import os
import re
import urllib.parse
from collections.abc import Callable, Sequence

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
        on_organize: Callable[[], None],
    ) -> None:
        super().__init__()
        self._on_drop = on_drop
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("quickIntakeFrame")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        headline = QLabel("<b>Drop files or paste a URL</b>")
        headline.setObjectName("quickIntakeHeadline")
        layout.addWidget(headline)

        body = QLabel(
            "Capture source material into the current note, keep LLM setup visible, and add organization tags as you go."
        )
        body.setWordWrap(True)
        layout.addWidget(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)

        choose_files = QPushButton("Choose files")
        choose_files.setAutoDefault(False)
        qconnect(choose_files.clicked, on_choose_files)
        actions.addWidget(choose_files)

        paste_url = QPushButton("Paste URL")
        paste_url.setAutoDefault(False)
        qconnect(paste_url.clicked, on_paste_url)
        actions.addWidget(paste_url)

        llm_setup = QPushButton("LLM setup")
        llm_setup.setAutoDefault(False)
        qconnect(llm_setup.clicked, on_llm_setup)
        actions.addWidget(llm_setup)

        organize = QPushButton("Organize note")
        organize.setAutoDefault(False)
        qconnect(organize.clicked, on_organize)
        actions.addWidget(organize)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.context_label = QLabel()
        self.context_label.setWordWrap(True)
        layout.addWidget(self.context_label)

        self.llm_status_label = QLabel("LLM status: not configured")
        self.llm_status_label.setWordWrap(True)
        layout.addWidget(self.llm_status_label)

        self.last_source_label = QLabel("Last source: none yet")
        self.last_source_label.setWordWrap(True)
        layout.addWidget(self.last_source_label)

        self.status_label = QLabel(
            "Tip: use capture::inbox plus source:: tags so imported material stays easy to triage later."
        )
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.setStyleSheet(
            """
#quickIntakeFrame {
  border: 1px dashed palette(mid);
  border-radius: 10px;
  background: palette(base);
}
#quickIntakeHeadline {
  font-size: 15px;
}
"""
        )

    def set_context(self, *, deck_name: str, note_type_name: str) -> None:
        self.context_label.setText(
            f"Current deck: <b>{deck_name}</b> • Current note type: <b>{note_type_name}</b>"
        )

    def set_llm_status(self, text: str) -> None:
        self.llm_status_label.setText(text)

    def set_last_source(self, text: str) -> None:
        self.last_source_label.setText(text)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        mime = event.mimeData()
        if mime.hasUrls():
            event.acceptProposedAction()
            return
        if mime.hasText() and re.match(r"https?://", mime.text().strip()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

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

        if files or urls:
            self._on_drop(files, urls)
            event.acceptProposedAction()
            return

        super().dropEvent(event)


class AddCards(QMainWindow):
    def __init__(self, mw: AnkiQt) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self._close_event_has_cleaned_up = False
        self.mw = mw
        self.col = mw.col
        form = aqt.forms.addcards.Ui_Dialog()
        form.setupUi(self)
        self.form = form
        self.setWindowTitle(tr.actions_add())
        self.setMinimumHeight(300)
        self.setMinimumWidth(400)
        self.setup_choosers()
        self.setup_intake_panel()
        self.setupEditor()
        self._load_new_note()
        self.setupButtons()
        self.history: list[NoteId] = []
        self._last_added_note: Note | None = None
        gui_hooks.operation_did_execute.append(self.on_operation_did_execute)
        restoreGeom(self, "add")
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
            on_organize=self._organize_current_note,
        )
        layout = self.form.centralwidget.layout()
        assert layout is not None
        layout.insertWidget(1, self.intake_frame)
        self._update_intake_context()
        self.intake_frame.set_llm_status("LLM status: not configured")
        self.intake_frame.set_last_source("Last source: none yet")

    def _update_intake_context(self) -> None:
        self.intake_frame.set_context(
            deck_name=self.deck_chooser.selected_deck_name(),
            note_type_name=self.notetype_chooser.selected_notetype_name(),
        )

    def _update_intake_status(self, message: str) -> None:
        self.intake_frame.set_status(message)

    def _update_last_source(self, summary: str) -> None:
        self.intake_frame.set_last_source(f"Last source: {summary}")

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
            self.editor.web.evalWithCallback("focusField(0); true;", lambda _ret: insert())
        else:
            insert()

    def _insert_source_links(self, sources: Sequence[str], *, source_kind: str) -> None:
        if not sources:
            return

        html_parts: list[str] = []
        deck_tag = f"deck::{self._normalize_tag(self.deck_chooser.selected_deck_name())}"
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
        summary = ", ".join(labels[:3])
        if len(labels) > 3:
            summary += ", …"
        plural = "" if len(labels) == 1 else "s"
        self._update_last_source(summary)
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
        url, ok = QInputDialog.getText(
            self,
            "Paste a source URL",
            "Paste a web page, video, or document URL to capture into the current note:",
        )
        if ok and url.strip():
            self._insert_source_links([url.strip()], source_kind="web")

    def _show_llm_setup(self) -> None:
        self.intake_frame.set_llm_status(
            "LLM status: setup surface reserved • provider not configured yet"
        )
        showInfo(
            "LLM-era capture belongs here.\n\n"
            "Prototype goals:\n"
            "• make provider/API setup impossible to miss\n"
            "• summarize dropped files and URLs into card drafts\n"
            "• keep organization defaults visible while capturing\n\n"
            "This experiment focuses on lowering capture friction first, while reserving a front-and-center surface for future LLM APIs.",
            parent=self,
        )

    def _organize_current_note(self) -> None:
        deck_tag = f"deck::{self._normalize_tag(self.deck_chooser.selected_deck_name())}"
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
