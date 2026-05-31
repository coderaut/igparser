import re

import httpx

from logger import log

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_MODEL = "google/gemma-4-31b-it"

_SYSTEM_PROMPT = (
    "You are a content formatter for Instagram posts. "
    "You receive raw text extracted from an Instagram post — a caption and/or text read from images "
    "or transcribed from video. "
    "Your job is to produce a clean, well-structured markdown document.\n\n"
    "Rules:\n"
    "- Preserve ALL meaningful content from the source. Do not summarise away or discard anything.\n"
    "- Choose the structure that best fits the content:\n"
    "  • Quotes or sayings → list every quote, with attribution if present\n"
    "  • Recipe → ingredients and numbered steps\n"
    "  • Book / movie / place / game recommendation → structured card using the reviewer's actual words\n"
    "  • Travel or food post → location details, what to order/see/do, tips\n"
    "  • Anything else → whatever markdown structure best preserves the content\n"
    "- Start with a # Title (H1) that summarises the post.\n"
    "- Output only markdown. No preamble, no meta-commentary."
)

_USER_TEMPLATE = """\
CAPTION:
{caption}

EXTRACTED TEXT:
{transcript}

Format this as clean markdown, preserving all meaningful content."""


def extract_content(
    transcript: str,
    caption: str,
    api_key: str,
) -> tuple[str, str]:
    """Call the LLM to format the post content as markdown.

    Returns (markdown, slugified_title).
    """
    log.debug("extract_content: transcript=%d chars, caption=%d chars", len(transcript), len(caption))
    user_message = _USER_TEMPLATE.format(
        caption=caption or "(not available)",
        transcript=transcript or "(not available)",
    )

    response = httpx.post(
        OPENROUTER_CHAT_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 2048,
        },
        timeout=120,
    )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"OpenRouter LLM API error {response.status_code}: {response.text}"
        ) from e

    content_md: str = response.json()["choices"][0]["message"]["content"].strip()
    title = _extract_title(content_md)
    slug = _slugify(title)
    log.debug("extract_content done: title=%r slug=%r", title, slug)
    return content_md, slug


def _extract_title(markdown: str) -> str:
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return "untitled"


def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = text.strip("-")
    return text or "untitled"
