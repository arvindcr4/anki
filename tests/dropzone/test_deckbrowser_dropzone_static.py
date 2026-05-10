from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
DECKBROWSER = ROOT / "qt" / "aqt" / "deckbrowser.py"
MAIN = ROOT / "qt" / "aqt" / "main.py"


def _source(path: Path) -> str:
    return path.read_text()


def test_deckbrowser_dropzone_encodes_bridge_payloads() -> None:
    src = _source(DECKBROWSER)
    assert "def encode_intake_payload" in src
    assert "def decode_intake_payload" in src
    assert "encodeURIComponent" in src
    assert "items.map(encodeURIComponent).join('|')" in src


def test_deckbrowser_dropzone_uses_native_paste_dialog() -> None:
    src = _source(DECKBROWSER)
    assert "QInputDialog.getText" in src
    assert "intake_paste" in src
    assert "window.prompt" not in src


def test_dropzone_clicks_do_not_open_modal_dialog() -> None:
    src = _source(DECKBROWSER)
    dropzone_tag = re.search(r'<div id="llm-dropzone"[^>]*>', src, re.DOTALL)
    assert dropzone_tag is not None
    assert "onclick=" not in dropzone_tag.group(0)
    assert 'id="llm-dropzone-paste"' in src


def test_temporary_dropzone_debug_log_removed() -> None:
    assert "/tmp/anki-paste-debug.log" not in _source(DECKBROWSER)


def test_main_webview_routes_pdf_and_url_drops_to_intake() -> None:
    src = _source(MAIN)
    tree = ast.parse(src)
    method_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_deck_browser_intake_items" in method_names
    assert "self.mw.deckBrowser._handle_intake_drop" in src
    assert "encode_intake_payload(items)" in src
    assert 'endswith(".pdf")' in src
    assert 'r"^https?://"' in src
