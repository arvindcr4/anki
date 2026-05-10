from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

LLM_GENERATE_PY = Path(__file__).parent.parent.parent / "qt" / "aqt" / "llm_generate.py"


def _load_llm_generate():
    spec = importlib.util.spec_from_file_location("aqt.llm_generate", LLM_GENERATE_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["aqt.llm_generate"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_qa_parser_recovers_complete_cards_before_truncated_tail() -> None:
    llm_generate = _load_llm_generate()
    response = """[
{
"front": "In machine learning, what is the \\"attention\\" mechanism?",
"back": "A method that weights sequence components. [mermaid]graph LR; A-->B;[/mermaid]"
},
{
"front": "How do soft weights differ?",
"back": "Hard weights ar"""

    result = llm_generate._parse_response(response, "qa", "test-model")

    assert len(result.cards) == 1
    assert result.cards[0].front == (
        'In machine learning, what is the "attention" mechanism?'
    )
    assert "[mermaid]" in result.cards[0].back


def test_qa_parser_recovers_reported_attention_response() -> None:
    llm_generate = _load_llm_generate()
    response = """[
{
"front": "In machine learning, what is the \\"attention\\" mechanism?",
"back": "A method that determines the importance of each component in a sequence relative to the other components, encoding token embeddings across a fixed-width sequence. [mermaid]graph LR; A[Input Sequence] --> B{Attention Mechanism}; B --> C[Soft Weights]; B --> D[Context Vector];[/mermaid]"
},
{
"front": "How do \\"soft\\" weights in attention differ from \\"hard\\" weights?",
"back": "Hard weights ar"""

    result = llm_generate._parse_response(response, "qa", "test-model")

    assert len(result.cards) == 1
    assert result.cards[0].front == (
        'In machine learning, what is the "attention" mechanism?'
    )


def test_cloze_parser_recovers_complete_items_before_truncated_tail() -> None:
    llm_generate = _load_llm_generate()
    response = """[
{"text": "{{c1::Attention}} assigns soft weights."},
{"text": "{{c1::Broken"""

    result = llm_generate._parse_response(response, "cloze", "test-model")

    assert len(result.clozes) == 1
    assert result.clozes[0].text == "{{c1::Attention}} assigns soft weights."


def test_summary_parser_still_rejects_malformed_json() -> None:
    llm_generate = _load_llm_generate()

    try:
        llm_generate._parse_response('{"summary": "unterminated', "summarize", "m")
    except llm_generate.LLMError as exc:
        assert "Failed to parse LLM response as JSON" in str(exc)
    else:
        raise AssertionError("expected malformed summary JSON to fail")
