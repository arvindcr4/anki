# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""LLM-based card generation for Anki.

Supports two backends:
1. Local MLX inference (Apple Silicon) — no server, no API key needed
2. OpenAI-compatible APIs — for cloud or external local servers

Set ANKI_LLM_BACKEND=local to force local inference.
Set ANKI_LLM_BACKEND=api to force API mode.
Default: auto (tries local first, falls back to API).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Literal

ActionType = Literal["qa", "cloze", "summarize"]


@dataclass
class GeneratedCard:
    front: str
    back: str
    tags: list[str]


@dataclass
class GeneratedCloze:
    text: str
    tags: list[str]


@dataclass
class GenerationResult:
    cards: list[GeneratedCard]
    clozes: list[GeneratedCloze]
    summary: str
    action: ActionType
    model_used: str


_SYSTEM_PROMPTS: dict[ActionType, str] = {
    "qa": (
        "You are an expert flashcard creator for spaced repetition learning. "
        "Given source material, create high-quality question-answer pairs. "
        "Each question should test one specific concept. Answers should be concise but complete. "
        "Return a JSON array of objects with 'front' and 'back' keys. "
        'Example: [{"front": "What is the capital of France?", "back": "Paris"}]'
    ),
    "cloze": (
        "You are an expert flashcard creator for spaced repetition learning. "
        "Given source material, create cloze deletion cards using Anki syntax {{c1::answer}}. "
        "Each card should test one specific concept. Use multiple cloze numbers for related facts. "
        "Return a JSON array of objects with a 'text' key containing the cloze text. "
        'Example: [{"text": "The capital of {{c1::France}} is {{c2::Paris}}"}]'
    ),
    "summarize": (
        "You are an expert at creating concise study summaries. "
        "Given source material, create a structured summary suitable for a flashcard back field. "
        "Use bullet points for key facts. Keep it under 200 words. "
        "Return a JSON object with a 'summary' key. "
        'Example: {"summary": "Key points:\\n• Point 1\\n• Point 2"}'
    ),
}

# Default local model — small enough for most Macs
DEFAULT_LOCAL_MODEL = "mlx-community/Qwen3-4B-4bit"


def get_backend() -> str:
    """Get the configured backend: 'local', 'api', or 'auto'."""
    return os.environ.get("ANKI_LLM_BACKEND", "auto")


def get_api_key() -> str | None:
    """Get the API key from environment.

    Only supports OpenAI-compatible API endpoints. For Anthropic,
    use an OpenAI-compatible proxy (e.g., LiteLLM) and set OPENAI_API_KEY.
    """
    return os.environ.get("OPENAI_API_KEY")


def get_api_base() -> str:
    """Get the API base URL, supporting local models."""
    return os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")


def get_model() -> str:
    """Get the model to use."""
    return os.environ.get("ANKI_LLM_MODEL", DEFAULT_LOCAL_MODEL)


def is_local_available() -> bool:
    """Check if local MLX inference is available."""
    try:
        import mlx_lm  # type: ignore[import-not-found]  # noqa: F401

        return True
    except ImportError:
        return False


def generate_cards(
    source_text: str,
    action: ActionType,
    *,
    num_cards: int = 5,
    context: str = "",
) -> GenerationResult:
    """Generate cards from source text using an LLM.

    Automatically selects local MLX or API backend.
    """
    backend = get_backend()

    if backend == "local" or (backend == "auto" and is_local_available()):
        return _generate_local(source_text, action, num_cards, context)
    elif backend in {"api", "auto"}:
        api_key = get_api_key()
        if not api_key:
            raise LLMError(
                "No API key found. Set OPENAI_API_KEY or install mlx-lm for local inference:\n"
                "  pip install mlx-lm"
            )
        return _generate_api(source_text, action, num_cards, context)
    else:
        raise LLMError(f"Unknown backend: {backend}. Use 'local', 'api', or 'auto'.")


# ---------------------------------------------------------------------------
# Local MLX backend
# ---------------------------------------------------------------------------

_local_model = None
_local_tokenizer = None
_local_model_name = None


def _get_local_model():
    """Load the local MLX model, caching across calls."""
    global _local_model, _local_tokenizer, _local_model_name
    model_name = get_model()

    if _local_model is not None and _local_model_name == model_name:
        return _local_model, _local_tokenizer

    try:
        import mlx_lm  # type: ignore[import-not-found]
    except ImportError:
        raise LLMError(
            "mlx-lm is not installed. Install it with:\n"
            "  pip install mlx-lm\n"
            "Or set ANKI_LLM_BACKEND=api to use an API instead."
        )

    # Check for locally cached model (e.g., from oMLX)
    short_name = model_name.split("/")[-1]
    local_paths = [
        os.path.expanduser(f"~/.omlx/models/{short_name}"),
        os.path.expanduser(
            f"~/.cache/huggingface/hub/models--{model_name.replace('/', '--')}"
        ),
    ]
    model_path = model_name
    for path in local_paths:
        if os.path.isdir(path):
            model_path = path
            break

    # If model not found locally, download it
    if model_path == model_name and not os.path.isdir(model_path):
        _download_model(model_name)

    _local_model, _local_tokenizer = mlx_lm.load(model_path)
    _local_model_name = model_name
    return _local_model, _local_tokenizer


def _download_model(model_name: str) -> None:
    """Download a model from HuggingFace Hub."""
    try:
        from huggingface_hub import snapshot_download  # type: ignore[import-not-found]
    except ImportError:
        raise LLMError(
            f"Model '{model_name}' not found locally and huggingface_hub "
            "is not installed for downloading.\n"
            "Install with: pip install mlx-lm\n"
            "Or manually download the model."
        )

    dest = os.path.expanduser(f"~/.omlx/models/{model_name.split('/')[-1]}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    snapshot_download(
        repo_id=model_name,
        local_dir=dest,
        local_dir_use_symlinks=False,
    )


def ensure_local_model() -> tuple[bool, str]:
    """Check if local model is available. Downloads if needed.

    Returns (ready, status_message).
    Call from a background thread — download may take minutes.
    """
    if not is_local_available():
        return False, "mlx-lm not installed"

    model_name = get_model()
    short_name = model_name.split("/")[-1]

    # Check existing paths
    for path in [
        os.path.expanduser(f"~/.omlx/models/{short_name}"),
        os.path.expanduser(
            f"~/.cache/huggingface/hub/models--{model_name.replace('/', '--')}"
        ),
    ]:
        if os.path.isdir(path):
            return True, f"Model ready: {short_name}"

    # Need to download
    try:
        _download_model(model_name)
        return True, f"Downloaded {short_name}"
    except Exception as e:
        return False, f"Download failed: {e}"


def _generate_local(
    source_text: str, action: ActionType, num_cards: int, context: str
) -> GenerationResult:
    """Generate cards using local MLX inference."""
    import mlx_lm  # type: ignore[import-not-found]

    model, tokenizer = _get_local_model()

    system_prompt = _SYSTEM_PROMPTS[action]
    user_prompt = _build_user_prompt(source_text, action, num_cards, context)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    prompt = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=False
    )

    response_text = mlx_lm.generate(
        model, tokenizer, prompt=prompt, max_tokens=2000, verbose=False
    )

    return _parse_response(response_text, action, get_model())


# ---------------------------------------------------------------------------
# API backend
# ---------------------------------------------------------------------------


def _generate_api(
    source_text: str, action: ActionType, num_cards: int, context: str
) -> GenerationResult:
    """Generate cards using an OpenAI-compatible API."""
    api_key = get_api_key()
    if not api_key:
        raise LLMError("No API key found. Set OPENAI_API_KEY environment variable.")

    system_prompt = _SYSTEM_PROMPTS[action]
    user_prompt = _build_user_prompt(source_text, action, num_cards, context)
    response_text = _call_api(api_key, system_prompt, user_prompt)
    return _parse_response(response_text, action, get_model())


def _build_user_prompt(
    source_text: str, action: ActionType, num_cards: int, context: str
) -> str:
    parts = [f"Source material:\n\n{source_text}"]
    if context:
        parts.append(f"\nContext: {context}")
    if action == "qa":
        parts.append(
            f"\nGenerate exactly {num_cards} question-answer pairs as a JSON array."
        )
    elif action == "cloze":
        parts.append(
            f"\nGenerate exactly {num_cards} cloze deletion cards as a JSON array."
        )
    else:
        parts.append("\nGenerate a concise study summary as a JSON object.")
    parts.append("\nRespond with ONLY valid JSON, no markdown fences or explanation.")
    return "\n".join(parts)


def _call_api(api_key: str, system_prompt: str, user_prompt: str) -> str:
    """Call an OpenAI-compatible chat completions API."""
    api_base = get_api_base()
    model = get_model()
    url = f"{api_base}/chat/completions"

    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 2000,
        }
    ).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise LLMError(f"API error {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"Network error: {e.reason}") from e
    except TimeoutError:
        raise LLMError("API request timed out after 120 seconds")

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"Unexpected API response format: {data}") from e


def _parse_response(
    response_text: str, action: ActionType, model: str
) -> GenerationResult:
    """Parse LLM response into structured cards."""
    text = response_text.strip()

    # Strip thinking tags from reasoning models (e.g., Qwen3, DeepSeek)
    if "<think>" in text:
        import re

        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(
            f"Failed to parse LLM response as JSON: {e}\nResponse: {text[:500]}"
        ) from e

    cards: list[GeneratedCard] = []
    clozes: list[GeneratedCloze] = []
    summary = ""

    if action == "qa":
        if not isinstance(parsed, list):
            parsed = [parsed]
        for item in parsed:
            if isinstance(item, dict) and "front" in item and "back" in item:
                cards.append(
                    GeneratedCard(
                        front=str(item["front"]),
                        back=str(item["back"]),
                        tags=["ai-generated", "qa"],
                    )
                )
    elif action == "cloze":
        if not isinstance(parsed, list):
            parsed = [parsed]
        for item in parsed:
            if isinstance(item, dict) and "text" in item:
                clozes.append(
                    GeneratedCloze(
                        text=str(item["text"]),
                        tags=["ai-generated", "cloze"],
                    )
                )
    elif action == "summarize":
        if isinstance(parsed, dict) and "summary" in parsed:
            summary = str(parsed["summary"])
        elif isinstance(parsed, str):
            summary = parsed

    return GenerationResult(
        cards=cards,
        clozes=clozes,
        summary=summary,
        action=action,
        model_used=model,
    )


class LLMError(Exception):
    """Error from LLM generation."""

    pass
