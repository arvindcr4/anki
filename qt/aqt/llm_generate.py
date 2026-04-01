# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""LLM-based card generation for Anki.

Supports OpenAI-compatible APIs (OpenAI, Anthropic via proxy, local models).
Generates Q&A pairs, cloze deletions, and summaries from source text.
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
    return os.environ.get("ANKI_LLM_MODEL", "gpt-4o-mini")


def generate_cards(
    source_text: str,
    action: ActionType,
    *,
    num_cards: int = 5,
    context: str = "",
) -> GenerationResult:
    """Generate cards from source text using an LLM.

    Args:
        source_text: The source material to generate cards from.
        action: Type of generation (qa, cloze, summarize).
        num_cards: Target number of cards to generate.
        context: Optional context (e.g., deck name, existing tags).

    Returns:
        GenerationResult with generated cards/clozes/summary.

    Raises:
        LLMError: If the API call fails.
    """
    api_key = get_api_key()
    if not api_key:
        raise LLMError(
            "No API key found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable."
        )

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
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise LLMError(f"API error {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"Network error: {e.reason}") from e
    except TimeoutError:
        raise LLMError("API request timed out after 30 seconds")

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"Unexpected API response format: {data}") from e


def _parse_response(
    response_text: str, action: ActionType, model: str
) -> GenerationResult:
    """Parse LLM response into structured cards."""
    # Strip markdown code fences if present
    text = response_text.strip()
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
