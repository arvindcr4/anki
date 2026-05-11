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


def test_gemini_model_resource_accepts_bare_or_prefixed_model() -> None:
    llm_generate = _load_llm_generate()

    assert (
        llm_generate._gemini_model_resource_path("gemini-3-flash-preview")
        == "models/gemini-3-flash-preview"
    )
    assert (
        llm_generate._gemini_model_resource_path("models/gemini-3-flash-preview")
        == "models/gemini-3-flash-preview"
    )


def test_gemini_api_url_does_not_double_prefix_models(monkeypatch) -> None:
    llm_generate = _load_llm_generate()
    monkeypatch.setenv("ANKI_LLM_BACKEND", "api")
    monkeypatch.setenv("ANKI_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("ANKI_LLM_MODEL", "models/gemini-3-flash-preview")

    captured: dict[str, str] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

        def read(self) -> bytes:
            return (
                b'{"candidates":[{"content":{"parts":[{"text":"[tikz]x[/tikz]"}]}}]}'
            )

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        return FakeResponse()

    monkeypatch.setattr(llm_generate.urllib.request, "urlopen", fake_urlopen)

    assert (
        llm_generate._call_gemini_api(
            "key/with/slash",
            "system",
            "user",
            json_response=False,
        )
        == "[tikz]x[/tikz]"
    )
    assert (
        captured["url"]
        == "https://generativelanguage.googleapis.com/v1beta/"
        "models/gemini-3-flash-preview:generateContent?key=key%2Fwith%2Fslash"
    )
