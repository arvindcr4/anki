# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""LLM-based card generation for Anki.

Supports four backends:
1. Local MLX inference (Apple Silicon) — no server, no API key needed
2. Anthropic Claude — set ANTHROPIC_API_KEY, ANKI_LLM_PROVIDER=claude
3. OpenAI-compatible APIs — set OPENAI_API_KEY, ANKI_LLM_PROVIDER=openai
4. Google Gemini — set GEMINI_API_KEY, ANKI_LLM_PROVIDER=gemini

Set ANKI_LLM_BACKEND=local to force local inference.
Set ANKI_LLM_BACKEND=api to force API mode.
Default: auto — uses whichever provider has a key set; local only if no key.
ANKI_LLM_PROVIDER picks among claude/openai/gemini when multiple keys are set.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal

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
        "Each question tests one specific concept; answers are concise but "
        "complete.\n\n"
        "VISUAL DIAGRAMS\n"
        "When a concept benefits from a picture (geometry, vectors, simple "
        "graphs, processes, structure, relationships, state machines, "
        "data flow, ordering), append a small diagram to the back of the "
        "card. Two syntaxes are recognised by the reviewer:\n"
        "  • TikZ — wrap with [tikz] ... [/tikz]. Restricted to the TikZ "
        "core: arrows, positioning, calc, shapes, decorations.pathreplacing, "
        "patterns. Do NOT use pgfplots, pgfplotsset, externalization, "
        "shell-escape, or \\input. Keep diagrams under ~5cm. Plain ASCII "
        "characters only inside the diagram body.\n"
        "  • Mermaid — wrap with [mermaid] ... [/mermaid]. Best for "
        "flowcharts, sequence diagrams, class diagrams, state machines, "
        "ER diagrams. Use the standard Mermaid grammar.\n\n"
        "Be selective: only add a diagram when it materially aids "
        "understanding. If plain text already conveys the answer, skip the "
        "diagram. Do NOT add diagrams to definition-style cards or simple "
        "factual recall.\n\n"
        "OUTPUT\n"
        "Return ONLY a JSON array of objects with 'front' and 'back' keys "
        "— no markdown fences, no commentary. Strings must be valid JSON "
        '(escape backslashes as \\\\ and quotes as \\"). Example:\n'
        '[{"front":"Pythagorean theorem?","back":"For a right triangle '
        "with legs a, b and hypotenuse c: a² + b² = c². "
        "[tikz]\\\\draw (0,0)--(3,0)--(3,4)--cycle; "
        "\\\\node[below] at (1.5,0) {a}; \\\\node[right] at (3,2) {b}; "
        '\\\\node[above left] at (1.5,2) {c};[/tikz]"}, '
        '{"front":"Year of the French Revolution?","back":"1789"}]'
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

DEFAULT_API_MODEL = {
    "claude": "claude-opus-4-7",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-3-flash-preview",
}


def get_backend() -> str:
    """Get the configured backend: 'local', 'api', or 'auto'."""
    return os.environ.get("ANKI_LLM_BACKEND", "auto")


def apply_llm_config(cfg: dict[str, str]) -> None:
    """Apply a saved profile LLM config to environment variables."""
    provider = cfg.get("provider", "claude")
    if provider == "local":
        os.environ["ANKI_LLM_BACKEND"] = "local"
    else:
        os.environ["ANKI_LLM_BACKEND"] = "api"
        os.environ["ANKI_LLM_PROVIDER"] = provider
    if cfg.get("model"):
        os.environ["ANKI_LLM_MODEL"] = cfg["model"]
    elif "ANKI_LLM_MODEL" in os.environ:
        del os.environ["ANKI_LLM_MODEL"]
    if cfg.get("anthropic_api_key"):
        os.environ["ANTHROPIC_API_KEY"] = cfg["anthropic_api_key"]
    if cfg.get("openai_api_key"):
        os.environ["OPENAI_API_KEY"] = cfg["openai_api_key"]
    if cfg.get("gemini_api_key"):
        os.environ["GEMINI_API_KEY"] = cfg["gemini_api_key"]


def apply_profile_llm_config(profile: object) -> None:
    """Apply llm_config from an Anki profile object if present."""
    getter = getattr(profile, "get", None)
    if not callable(getter):
        return
    cfg = getter("llm_config")
    if isinstance(cfg, dict):
        apply_llm_config(cfg)


def get_provider() -> str:
    """Return the API provider: 'claude', 'openai', or 'gemini'.

    Honors ANKI_LLM_PROVIDER. Otherwise falls back to whichever key is set,
    preferring gemini > claude > openai. If none, defaults to openai.
    """
    explicit = os.environ.get("ANKI_LLM_PROVIDER", "").strip().lower()
    if explicit in {"claude", "anthropic"}:
        return "claude"
    if explicit in {"openai", "compat"}:
        return "openai"
    if explicit in {"gemini", "google"}:
        return "gemini"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "openai"


def get_api_key() -> str | None:
    """Return the API key for the current provider (None if not set)."""
    provider = get_provider()
    if provider == "claude":
        return os.environ.get("ANTHROPIC_API_KEY")
    if provider == "gemini":
        return os.environ.get("GEMINI_API_KEY")
    return os.environ.get("OPENAI_API_KEY")


def get_api_base() -> str:
    """Get the OpenAI-compatible API base URL (ignored for Claude)."""
    return os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")


def get_model() -> str:
    """Get the model to use, with provider-aware defaults.

    ``ANKI_LLM_MODEL`` overrides the default, but only when it matches the
    active provider. A stale local-model name (e.g. ``Qwen3-4B-4bit``) left
    in the environment after switching to an API provider would otherwise
    be sent to Gemini/Anthropic/OpenAI and rejected (400 "unexpected model
    name format").
    """
    explicit = os.environ.get("ANKI_LLM_MODEL", "").strip()
    if get_backend() == "local":
        return explicit or DEFAULT_LOCAL_MODEL
    provider = get_provider()
    if explicit and _model_matches_provider(explicit, provider):
        return explicit
    return DEFAULT_API_MODEL.get(provider, DEFAULT_LOCAL_MODEL)


def _model_matches_provider(model: str, provider: str) -> bool:
    """Return True if ``model`` looks like a valid id for ``provider``."""
    m = model.strip().strip("/").lower()
    if provider == "gemini":
        return m.startswith("gemini-") or m.startswith("models/gemini-")
    if provider == "claude":
        return m.startswith("claude-")
    if provider == "openai":
        # Reject names that clearly belong to another provider; otherwise
        # accept (OpenAI-compatible endpoints use diverse naming schemes).
        return not (m.startswith("gemini-") or m.startswith("claude-"))
    return True


def _gemini_model_resource_path(model: str) -> str:
    """Return the URL path segment Gemini expects for generateContent."""
    import urllib.parse

    normalized = model.strip().strip("/")
    if normalized.endswith(":generateContent"):
        normalized = normalized[: -len(":generateContent")]
    if not normalized.startswith("models/"):
        normalized = f"models/{normalized}"
    return "/".join(
        urllib.parse.quote(segment, safe="") for segment in normalized.split("/")
    )


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

    Selects backend in this order:
      - ANKI_LLM_BACKEND=local → local MLX
      - ANKI_LLM_BACKEND=api → cloud API (provider per ANKI_LLM_PROVIDER)
      - auto → API if a key is set; otherwise local if available; else error
    """
    backend = get_backend()

    if backend == "local":
        return _generate_local(source_text, action, num_cards, context)
    if backend == "auto" and not get_api_key() and is_local_available():
        return _generate_local(source_text, action, num_cards, context)
    if backend in {"api", "auto"}:
        if not get_api_key():
            raise LLMError(
                "No LLM API key set. Configure one of:\n"
                "  • ANTHROPIC_API_KEY (with ANKI_LLM_PROVIDER=claude)\n"
                "  • OPENAI_API_KEY (with ANKI_LLM_PROVIDER=openai)\n"
                "Or install mlx-lm for local inference: pip install mlx-lm"
            )
        return _generate_api(source_text, action, num_cards, context)
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
    """Generate cards using the configured cloud API (Claude or OpenAI)."""
    api_key = get_api_key()
    provider = get_provider()
    if not api_key:
        if provider == "claude":
            raise LLMError("No ANTHROPIC_API_KEY set.")
        if provider == "gemini":
            raise LLMError("No GEMINI_API_KEY set.")
        raise LLMError("No OPENAI_API_KEY set.")

    system_prompt = _SYSTEM_PROMPTS[action]
    user_prompt = _build_user_prompt(source_text, action, num_cards, context)
    if provider == "claude":
        response_text = _call_anthropic_api(api_key, system_prompt, user_prompt)
    elif provider == "gemini":
        response_text = _call_gemini_api(api_key, system_prompt, user_prompt)
    else:
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


def _call_gemini_api(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    *,
    json_response: bool = True,
) -> str:
    """Call Google's Gemini generateContent API.

    ``json_response=True`` asks Gemini to return strict JSON (used by the
    URL→cards flow); set False when the prompt expects raw text.
    """
    import urllib.parse

    model = _gemini_model_resource_path(get_model())
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"{model}:generateContent?key={urllib.parse.quote(api_key, safe='')}"
    )

    gen_config: dict[str, Any] = {
        "temperature": 0.4,
        "maxOutputTokens": 4096,
    }
    if json_response:
        gen_config["responseMimeType"] = "application/json"

    payload = json.dumps(
        {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": gen_config,
        }
    ).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise LLMError(f"Gemini API error {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"Network error: {e.reason}") from e
    except TimeoutError:
        raise LLMError("Gemini API request timed out after 120 seconds")

    try:
        candidates = data.get("candidates") or []
        if not candidates:
            raise KeyError(f"no candidates in Gemini response: {data}")
        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            if isinstance(part, dict) and "text" in part:
                return part["text"]
        raise KeyError(f"no text part in Gemini response: {data}")
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"Unexpected Gemini response format: {data}") from e


def _call_anthropic_api(api_key: str, system_prompt: str, user_prompt: str) -> str:
    """Call Anthropic's Messages API."""
    model = get_model()
    url = "https://api.anthropic.com/v1/messages"

    payload = json.dumps(
        {
            "model": model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": 0.4,
        }
    ).encode("utf-8")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise LLMError(f"Anthropic API error {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"Network error: {e.reason}") from e
    except TimeoutError:
        raise LLMError("Anthropic API request timed out after 120 seconds")

    try:
        # Messages API returns {"content": [{"type": "text", "text": "..."}], ...}
        for block in data.get("content", []):
            if block.get("type") == "text" and "text" in block:
                return block["text"]
        raise KeyError("no text block in Anthropic response")
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"Unexpected Anthropic response format: {data}") from e


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
        parsed = _recover_json_items(text, action)
        if parsed is None:
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


def _recover_json_items(text: str, action: ActionType) -> list[dict[str, Any]] | None:
    """Recover complete objects from a malformed JSON array response.

    LLMs occasionally emit a valid prefix followed by a truncated object, most
    commonly from an unterminated string. For list-producing actions, keep any
    complete objects with the required keys instead of discarding the whole
    generation.
    """
    if action not in {"qa", "cloze"}:
        return None

    required = ("front", "back") if action == "qa" else ("text",)
    items: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    for candidate in _complete_json_object_strings(text):
        try:
            item, end = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if (
            end == len(candidate)
            and isinstance(item, dict)
            and all(key in item for key in required)
        ):
            items.append(item)

    return items or None


def _complete_json_object_strings(text: str) -> list[str]:
    """Return balanced top-level JSON object substrings from text."""
    objects: list[str] = []
    depth = 0
    start: int | None = None
    in_string = False
    escaped = False

    for idx, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(text[start : idx + 1])
                start = None

    return objects


class LLMError(Exception):
    """Error from LLM generation."""

    pass
