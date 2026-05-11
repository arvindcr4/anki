from __future__ import annotations

import ast
from pathlib import Path

REVIEWER = Path(__file__).parent.parent.parent / "qt" / "aqt" / "reviewer.py"


def _source() -> str:
    return REVIEWER.read_text()


def test_reviewer_auto_generates_missing_tikz_on_question_load() -> None:
    src = _source()
    assert "self._maybe_generate_missing_tikz()" in src
    assert "def _maybe_generate_missing_tikz" in src
    assert "_auto_diagram_attempted_note_ids" in src
    assert "_auto_diagram_in_flight_note_ids" in src


def test_reviewer_applies_saved_llm_config_before_auto_generation() -> None:
    src = _source()
    assert "apply_profile_llm_config(self.mw.pm.profile)" in src
    assert "self._auto_diagram_attempted_note_ids.discard(note_id)" in src


def test_diagram_prompt_requires_tikz_for_every_card() -> None:
    src = _source()
    assert "produce exactly ONE TikZ" in src
    assert "for every card" in src
    assert "no Mermaid, no SKIP" in src
    assert "  [mermaid]<mermaid body>[/mermaid]" not in src
    assert "literal string SKIP" not in src


def test_auto_generation_only_treats_tikz_as_present() -> None:
    src = _source()
    assert "def _note_has_tikz" in src
    assert r"\begin\{tikzpicture\}" in src
    assert r"\end\{tikzpicture\}" in src
    tree = ast.parse(src)
    note_has_tikz = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_note_has_tikz"
    )
    body_src = ast.get_source_segment(src, note_has_tikz)
    assert body_src is not None
    assert "mermaid" not in body_src.lower()


def test_auto_generation_removes_broken_tikz_before_saving_new_one() -> None:
    src = _source()
    on_done_start = src.index("        def on_done")
    on_done = src[on_done_start : src.index("        self.mw.taskman", on_done_start)]
    assert "if auto:" in on_done
    assert "re.sub(" in on_done
    assert r"\[tikz\].*?\[/tikz\]" in on_done


def test_auto_generation_stores_on_front_and_refreshes_question() -> None:
    src = _source()
    on_done_start = src.index("        def on_done")
    on_done = src[on_done_start : src.index("        self.mw.taskman", on_done_start)]
    assert "self._showAnswer()" in on_done
    assert "self._showQuestion()" in on_done
    assert "target_field = 0 if auto else 1" in on_done


def test_generated_tikz_is_normalized_before_saving() -> None:
    src = _source()
    on_done_start = src.index("        def on_done")
    on_done = src[on_done_start : src.index("        self.mw.taskman", on_done_start)]
    assert "from aqt.diagrams import tikz_tag" in on_done
    assert "text = tikz_tag(text)" in on_done
    assert r"\begin{tikzpicture}" in on_done
