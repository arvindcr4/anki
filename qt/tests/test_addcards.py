# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from aqt.qt import QApplication, QDragLeaveEvent, QMimeData, Qt, QUrl

if TYPE_CHECKING:
    from aqt.addcards import QuickIntakeFrame

_APP: QApplication | None = None


def ensure_app() -> QApplication:
    global _APP
    app = QApplication.instance()
    if app is None:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
        _APP = QApplication([])
        app = _APP
    else:
        _APP = app
    return app


class DragEventStub:
    def __init__(self, mime: QMimeData) -> None:
        self._mime = mime
        self.accepted = False

    def mimeData(self) -> QMimeData:
        return self._mime

    def acceptProposedAction(self) -> None:
        self.accepted = True


def make_frame(
    *,
    dropped: list[tuple[list[str], list[str]]] | None = None,
) -> QuickIntakeFrame:
    ensure_app()
    from aqt.addcards import QuickIntakeFrame

    dropped = dropped if dropped is not None else []

    def on_drop(files: Sequence[str], urls: Sequence[str]) -> None:
        dropped.append((list(files), list(urls)))

    frame = QuickIntakeFrame(
        on_drop=on_drop,
        on_choose_files=lambda: None,
        on_paste_url=lambda: None,
        on_llm_setup=lambda: None,
        on_codex_connect=lambda: None,
        on_llm_action=lambda _action: None,
        on_organize=lambda: None,
    )
    return frame


def test_quick_intake_actions_present_and_toggle() -> None:
    frame = make_frame()

    assert frame.objectName() == "quickIntakeFrame"
    assert frame.summarize_button.text() == "Summarize"
    assert frame.qa_button.text().replace("&&", "&") == "Q&A"
    assert frame.cloze_button.text() == "Cloze"

    frame.set_llm_actions_enabled(False)
    assert not frame.summarize_button.isEnabled()
    assert not frame.qa_button.isEnabled()
    assert not frame.cloze_button.isEnabled()

    frame.set_llm_actions_enabled(True)
    assert frame.summarize_button.isEnabled()
    assert frame.qa_button.isEnabled()
    assert frame.cloze_button.isEnabled()


def test_quick_intake_context_updates_labels() -> None:
    frame = make_frame()

    frame.set_context(deck_name="Inbox", note_type_name="Basic")

    assert frame.deck_chip.text() == "Deck: Inbox"
    assert frame.note_type_chip.text() == "Note type: Basic"
    assert "Inbox" in frame.context_label.text()
    assert "Basic" in frame.context_label.text()


def test_drag_enter_accepts_url_text_and_drag_leave_resets() -> None:
    frame = make_frame()
    mime = QMimeData()
    mime.setText("https://example.com/article")
    event = DragEventStub(mime)

    frame.dragEnterEvent(event)

    assert event.accepted
    assert frame.property("dragActive") is True

    frame.dragLeaveEvent(QDragLeaveEvent())
    assert frame.property("dragActive") is False


def test_drop_event_passes_local_files_and_urls_to_callback() -> None:
    dropped: list[tuple[list[str], list[str]]] = []
    frame = make_frame(dropped=dropped)
    mime = QMimeData()
    mime.setUrls(
        [
            QUrl.fromLocalFile("/tmp/example.pdf"),
            QUrl("https://example.com/audio"),
        ]
    )
    event = DragEventStub(mime)

    frame.dropEvent(event)  # type: ignore[arg-type]

    assert event.accepted
    assert dropped == [(["/tmp/example.pdf"], ["https://example.com/audio"])]
    assert frame.property("dragActive") is False
