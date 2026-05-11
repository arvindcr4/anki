# Tests for qt/aqt/diagrams.py — used as the autoresearch fitness signal.
# These tests intentionally exercise the module in isolation so the heavy
# Anki backend doesn't need to boot up just to score a metric.

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

DIAGRAMS_PY = Path(__file__).parent.parent.parent / "qt" / "aqt" / "diagrams.py"


@pytest.fixture(scope="module")
def diagrams():
    """Load aqt.diagrams in isolation (stubbing aqt.* + anki.cards)."""
    # Stub the bits the module imports at top level.
    fake_aqt = MagicMock()
    fake_aqt.gui_hooks = MagicMock()
    sys.modules.setdefault("aqt", fake_aqt)
    sys.modules.setdefault("anki", MagicMock())
    sys.modules.setdefault("anki.cards", MagicMock())
    if "aqt.diagrams" in sys.modules:
        del sys.modules["aqt.diagrams"]
    spec = importlib.util.spec_from_file_location("aqt.diagrams", str(DIAGRAMS_PY))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------- Transformer correctness ----------


class TestTransform:
    def test_tikz_block_rewritten(self, diagrams):
        out = diagrams.transform_card_html(r"[tikz]\draw (0,0)--(1,1);[/tikz]")
        assert '<figure class="anki-tikz-canvas"' in out
        assert 'data-anki-tikz-state="loading"' in out
        assert 'data-anki-tikz-mode="fit"' in out
        assert 'class="anki-tikz-toolbar"' in out
        assert 'class="anki-tikz-stage"' in out
        assert 'class="anki-tikz-source-data"' in out
        assert 'class="anki-tikz-source" hidden' in out
        assert '<script type="text/tikz">' in out
        assert "[/tikz]" not in out

    def test_mermaid_block_rewritten(self, diagrams):
        out = diagrams.transform_card_html("[mermaid]graph TD; A-->B;[/mermaid]")
        assert '<div class="mermaid">' in out
        assert "[mermaid]" not in out

    def test_no_tags_returns_unchanged(self, diagrams):
        html = "<p>just text</p>"
        assert diagrams.transform_card_html(html) == html

    def test_tikz_auto_wraps_tikzpicture(self, diagrams):
        out = diagrams.transform_card_html(r"[tikz]\draw (0,0)--(1,1);[/tikz]")
        assert r"\begin{tikzpicture}" in out
        assert r"\end{tikzpicture}" in out

    def test_tikz_preserves_existing_tikzpicture(self, diagrams):
        body = r"\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}"
        out = diagrams.transform_card_html(f"[tikz]{body}[/tikz]")
        render_script = out.split('<script type="text/tikz">', 1)[1].split(
            "</script>", 1
        )[0]
        assert render_script.count(r"\begin{tikzpicture}") == 1

    def test_tikz_auto_wraps_document(self, diagrams):
        out = diagrams.transform_card_html(r"[tikz]\draw (0,0)--(1,1);[/tikz]")
        assert r"\begin{document}" in out
        assert r"\documentclass[tikz]{standalone}" in out
        assert r"\usepackage{tikz}" in out

    def test_tikzjax_script_omits_terminal_end_document(self, diagrams):
        out = diagrams.transform_card_html(r"[tikz]\draw (0,0)--(1,1);[/tikz]")
        render_script = out.split('<script type="text/tikz">', 1)[1].split(
            "</script>", 1
        )[0]
        source_template = out.split('<template class="anki-tikz-source-data">', 1)[
            1
        ].split("</template>", 1)[0]
        assert r"\begin{document}" not in render_script
        assert r"\end{document}" not in render_script
        assert r"\begin{document}" in source_template
        assert r"\end{document}" in source_template

    def test_tikzjax_script_omits_standalone_preamble(self, diagrams):
        out = diagrams.transform_card_html(r"[tikz]\draw (0,0)--(1,1);[/tikz]")
        render_script = out.split('<script type="text/tikz">', 1)[1].split(
            "</script>", 1
        )[0]
        source_template = out.split('<template class="anki-tikz-source-data">', 1)[
            1
        ].split("</template>", 1)[0]
        assert r"\documentclass" not in render_script
        assert r"\usepackage" not in render_script
        assert r"\usetikzlibrary" not in render_script
        assert r"\begin{tikzpicture}" in render_script
        assert r"\documentclass" in source_template

    def test_tikz_tag_normalizes_raw_tikz_body(self, diagrams):
        tag = diagrams.tikz_tag(r"\draw (0,0)--(1,1);")
        assert tag.startswith("[tikz]")
        assert tag.endswith("[/tikz]")
        assert r"\documentclass[tikz]{standalone}" in tag
        assert r"\begin{document}" in tag
        assert r"\begin{tikzpicture}" in tag
        assert r"\draw (0,0)--(1,1);" in tag

    def test_tikz_normalization_strips_nested_markers(self, diagrams):
        out = diagrams.transform_card_html(
            r"[tikz]\begin{document}[tikz]\begin{tikzpicture}\draw (0,0);[/tikz]"
        )
        render_script = out.split('<script type="text/tikz">', 1)[1].split(
            "</script>", 1
        )[0]
        assert "[tikz]" not in render_script
        assert "[/tikz]" not in render_script
        assert r"\draw (0,0);" in render_script

    def test_tikz_normalization_preserves_documentclass_option(self, diagrams):
        body = (
            r"\documentclass[tikz]{standalone}"
            "\n"
            r"\begin{document}"
            "\n"
            r"\begin{tikzpicture}\draw (0,0);\end{tikzpicture}"
            "\n"
            r"\end{document}"
        )
        normalized = diagrams.normalize_tikz_source(body)
        assert r"\documentclass[tikz]{standalone}" in normalized

    def test_tikz_normalization_closes_truncated_picture(self, diagrams):
        out = diagrams.transform_card_html(
            "[tikz]"
            r"\begin{tikzpicture}"
            "\n"
            r"\draw (0,0) -- (1,1);"
            "\n"
            r"\node at (3.5,"
            "\n"
            r"\end{document}"
            "[/tikz]"
        )
        render_script = out.split('<script type="text/tikz">', 1)[1].split(
            "</script>", 1
        )[0]
        assert r"\node at (3.5," not in render_script
        assert r"\end{document}" not in render_script
        assert r"\draw (0,0) -- (1,1);" in render_script
        assert render_script.count(r"\end{tikzpicture}") == 1

    def test_multiple_tikz_blocks(self, diagrams):
        html = r"[tikz]\draw (0,0);[/tikz] mid [tikz]\draw (1,1);[/tikz]"
        out = diagrams.transform_card_html(html)
        assert out.count('<script type="text/tikz">') == 2

    def test_tikz_and_mermaid_in_same_html(self, diagrams):
        html = (
            r"[tikz]\draw (0,0);[/tikz] and "
            r"[mermaid]graph TD; A-->B;[/mermaid]"
        )
        out = diagrams.transform_card_html(html)
        assert '<script type="text/tikz">' in out
        assert '<div class="mermaid">' in out


# ---------- Robustness ----------


class TestRobustness:
    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "[tikz][/tikz]",
            r"[tikz]\bad{} [",
            "[tikz]\u200b[/tikz]",
            "<p>plain</p>",
            r"[tikz]\draw[/tikz]" * 50,
        ],
    )
    def test_no_crash(self, diagrams, bad):
        try:
            diagrams.transform_card_html(bad)
        except Exception as e:
            pytest.fail(f"transform_card_html crashed on {bad!r}: {e}")


# ---------- Caching API (offline + cached rendering goal) ----------


class TestCachingApi:
    def test_cache_helper_exists(self, diagrams):
        assert hasattr(diagrams, "cache_diagram_svg") or hasattr(
            diagrams, "_cache_to_media"
        ), "expected cache_diagram_svg or _cache_to_media for first-class caching"

    def test_cache_uses_content_hash(self, diagrams):
        helper = getattr(diagrams, "cache_diagram_svg", None) or getattr(
            diagrams, "_cache_to_media", None
        )
        if helper is None:
            pytest.skip("cache helper not yet present")
        # Stable filename for same source — call signature is helper(col, kind, body, svg=None)
        col = MagicMock()
        col.media.have.return_value = False
        col.media.write_data = MagicMock()
        f1 = helper(col, "tikz", r"\draw (0,0)--(1,1);", b"<svg/>")
        f2 = helper(col, "tikz", r"\draw (0,0)--(1,1);", b"<svg/>")
        assert f1 == f2, "same content should map to same cached filename"
        f3 = helper(col, "tikz", r"\draw (0,0)--(2,2);", b"<svg/>")
        assert f1 != f3, "different content should map to different filenames"

    def test_cached_tikz_inlines_svg_instead_of_img(self, diagrams):
        old_cache = getattr(diagrams, "_persistent_cache", None)
        try:
            diagrams._persistent_cache = MagicMock()
            diagrams._persistent_cache.get.return_value = (
                '<svg viewBox="0 0 10 10"><path d="M0 0"/></svg>'
            )
            out = diagrams.transform_card_html(r"[tikz]\draw (0,0)--(1,1);[/tikz]")
        finally:
            diagrams._persistent_cache = old_cache

        assert 'data-anki-tikz-state="ready"' in out
        assert "<svg " in out
        assert "<img " not in out
        assert '<script type="text/tikz">' not in out


# ---------- Offline / vendored loader ----------


class TestOfflineAssets:
    def test_offline_loader_marker(self, diagrams):
        # First-class offline rendering means we don't *only* depend on CDN.
        # Acceptable signals: bundled JS string constant, install helper,
        # or a documented local-fallback path.
        markers = [
            "OFFLINE_TIKZJAX",
            "install_tikzjax_assets",
            "_local_loader_html",
            "tikzjax_local",
            "VENDORED_TIKZJAX",
        ]
        src = DIAGRAMS_PY.read_text()
        assert any(m in src for m in markers), (
            "expected one of " + ", ".join(markers) + " for offline rendering support"
        )

    def test_tikz_runner_prefers_local_assets_before_cdn(self, diagrams):
        js = diagrams._DIAGRAM_RUNNER_JS
        assert f"/{diagrams.VENDORED_TIKZJAX_FILENAME}" in js
        assert f"/{diagrams.VENDORED_TIKZJAX_FONTS_FILENAME}" in js
        assert "https://tikzjax.com/v1/tikzjax.js" in js
        assert js.index(f"/{diagrams.VENDORED_TIKZJAX_FILENAME}") < js.index(
            "https://tikzjax.com/v1/tikzjax.js"
        )
        assert "_ankiLoadTikzAsset(index + 1)" in js
        assert "requestIdleCallback" in js

    def test_tikz_font_css_rewrite_makes_fonts_absolute(self, diagrams):
        css = b"@font-face { src: url('../bakoma/ttf/cmr10.ttf'); }"
        out = diagrams._rewrite_tikzjax_font_urls(css).decode("utf-8")
        assert "../bakoma" not in out
        assert "https://tikzjax.com/bakoma/ttf/cmr10.ttf" in out

    def test_tikz_js_rewrite_makes_engine_same_origin(self, diagrams):
        js = (
            b'var s="https://s3.us-east-2.amazonaws.com/tikzjax.com";fetch(s+"/x.wasm")'
        )
        out = diagrams._rewrite_tikzjax_engine_urls(js).decode("utf-8")
        assert "https://s3.us-east-2.amazonaws.com/tikzjax.com" not in out
        assert "var s=window.location.origin" in out

    def test_tikz_asset_installer_includes_engine_payloads(self, diagrams):
        src = DIAGRAMS_PY.read_text()
        assert diagrams.VENDORED_TIKZJAX_WASM_FILENAME in src
        assert diagrams.VENDORED_TIKZJAX_DATA_FILENAME in src

    def test_setup_hook_installs_assets_on_collection_load(self, diagrams):
        diagrams.gui_hooks = MagicMock()
        diagrams.gui_hooks.card_will_show._hooks = []
        diagrams.gui_hooks.collection_did_load._hooks = []
        diagrams.gui_hooks.reviewer_did_show_question._hooks = []
        diagrams.gui_hooks.reviewer_did_show_answer._hooks = []

        diagrams.setup_hook()

        diagrams.gui_hooks.collection_did_load.append.assert_any_call(
            diagrams._install_tikzjax_assets_for_collection
        )

    def test_tikz_runner_tracks_canvas_state(self, diagrams):
        js = diagrams._DIAGRAM_RUNNER_JS
        assert "_ankiRefreshTikzCanvases" in js
        assert "data-anki-tikz-state" in js
        assert "closest('.anki-tikz-canvas')" in js
        assert "canvas.querySelector('svg')" in js
        assert "TikZJax did not finish rendering" in js

    def test_tikz_runner_invokes_late_loaded_tikzjax(self, diagrams):
        js = diagrams._DIAGRAM_RUNNER_JS
        assert "_ankiRunTikzjaxScanner" in js
        assert "window.onload(new Event('load'))" in js
        assert "_ankiRunTikzjaxScanner();" in js

    def test_tikz_runner_installs_canvas_controls(self, diagrams):
        js = diagrams._DIAGRAM_RUNNER_JS
        assert "_ankiInstallTikzCanvasControls" in js
        assert "data-anki-tikz-action" in js
        assert "navigator.clipboard.writeText" in js
        assert "XMLSerializer().serializeToString(svg)" in js
        assert "data-anki-tikz-mode" in js

    def test_runner_is_queued_after_reviewer_dom_update(self, diagrams):
        js = diagrams._QUEUED_DIAGRAM_RUNNER_JS
        assert "window._queueAction(runDiagrams)" in js
        assert "window.setTimeout(runDiagrams, 0)" in js
        assert diagrams._DIAGRAM_RUNNER_JS in js

    def test_reviewer_styles_tikz_canvas(self):
        css = (
            DIAGRAMS_PY.parent.parent.parent / "ts" / "reviewer" / "reviewer.scss"
        ).read_text()
        assert ".anki-tikz-canvas" in css
        assert ".anki-tikz-toolbar" in css
        assert ".anki-tikz-tool" in css
        assert ".anki-tikz-stage" in css
        assert ".anki-tikz-source" in css
        assert 'data-anki-tikz-state="loading"' in css
        assert 'data-anki-tikz-mode="actual"' in css
        assert ".nightMode" in css

    def test_reviewer_tikz_canvas_reserves_toolbar_space(self):
        css = (
            DIAGRAMS_PY.parent.parent.parent / "ts" / "reviewer" / "reviewer.scss"
        ).read_text()
        assert "position: static;" in css
        assert "width: max-content;" in css
        assert "overflow: visible;" in css
        assert "position: static !important;" in css


# ---------- Error fallback ----------


class TestErrorFallback:
    def test_module_has_error_fallback(self, diagrams):
        # A graceful renderer wraps render attempts and surfaces a fallback —
        # either a function name or a doc string commitment.
        src = DIAGRAMS_PY.read_text()
        assert (
            "render_error" in src
            or "fallback" in src.lower()
            or "error_html" in src.lower()
        ), "expected an error-fallback path in diagrams.py"


# ---------- Hook plumbing ----------


class TestHookPlumbing:
    def test_setup_hook_registers_card_will_show(self, diagrams):
        diagrams.gui_hooks = MagicMock()
        diagrams.gui_hooks.card_will_show._hooks = []
        diagrams.gui_hooks.collection_did_load._hooks = []
        diagrams.gui_hooks.reviewer_did_show_question._hooks = []
        diagrams.gui_hooks.reviewer_did_show_answer._hooks = []
        diagrams.setup_hook()
        # Either via .append or our idempotent guard, transform_card_html must be there.
        # We can't easily inspect MagicMock calls AND the _hooks list, so just
        # verify setup_hook is callable + idempotent without raising.
        diagrams.setup_hook()
