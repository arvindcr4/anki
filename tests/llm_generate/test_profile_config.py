from __future__ import annotations

import importlib.util
import os
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


def test_apply_profile_llm_config_sets_reviewer_visible_env(monkeypatch) -> None:
    llm_generate = _load_llm_generate()
    for key in (
        "ANKI_LLM_BACKEND",
        "ANKI_LLM_PROVIDER",
        "ANKI_LLM_MODEL",
        "GEMINI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    profile = {
        "llm_config": {
            "provider": "gemini",
            "model": "gemini-test-model",
            "gemini_api_key": "secret",
        }
    }

    llm_generate.apply_profile_llm_config(profile)

    assert os.environ["ANKI_LLM_BACKEND"] == "api"
    assert os.environ["ANKI_LLM_PROVIDER"] == "gemini"
    assert os.environ["ANKI_LLM_MODEL"] == "gemini-test-model"
    assert os.environ["GEMINI_API_KEY"] == "secret"
    assert llm_generate.get_api_key() == "secret"
