import re

import httpx

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_MODEL = "google/gemma-4-31b-it"

_PROMPTS: dict[str, tuple[str, str]] = {
    "recipe": (
        "You are a recipe extraction assistant. Given a video transcript and/or Instagram caption "
        "from a cooking post, extract a clean, complete recipe. If information is missing or "
        "ambiguous, make reasonable culinary assumptions and note them. Output only markdown, no preamble.",
        """\
CAPTION:
{caption}

TRANSCRIPT:
{transcript}

Extract the recipe and format it as markdown with this structure:
- Title (H1)
- Brief description (1–2 lines)
- Servings and prep/cook time if mentioned
- ## Ingredients (bullet list with quantities)
- ## Instructions (numbered steps)
- ## Notes (any tips, substitutions, or assumptions made)""",
    ),
    "movie": (
        "You are a film and TV recommendation assistant. Given a video transcript and/or Instagram caption "
        "recommending a movie or show, extract a clean, structured recommendation card. "
        "Output only markdown, no preamble.",
        """\
CAPTION:
{caption}

TRANSCRIPT:
{transcript}

Extract the recommendation and format it as markdown with this structure:
- Title (H1), include year if mentioned
- Brief tagline or hook (1–2 lines)
- **Director/Creator:** (if mentioned)
- **Genre:**
- **Where to watch:** (if mentioned)
- ## Why Watch It (the reviewer's reasons)
- ## What to Expect (tone, themes, target audience)
- ## Notes (caveats, trigger warnings, or context)""",
    ),
    "book": (
        "You are a book recommendation assistant. Given a video transcript and/or Instagram caption "
        "recommending a book, extract a clean, structured recommendation card. "
        "Output only markdown, no preamble.",
        """\
CAPTION:
{caption}

TRANSCRIPT:
{transcript}

Extract the recommendation and format it as markdown with this structure:
- Title (H1)
- **Author:**
- **Genre:**
- ## What It's About (brief, spoiler-free summary)
- ## Why Read It (the reviewer's reasons)
- ## Notes (content warnings, best format — audiobook vs print, etc.)""",
    ),
    "place": (
        "You are a travel recommendation assistant. Given a video transcript and/or Instagram caption "
        "recommending a place to visit (restaurant, café, city, landmark, neighbourhood, etc.), "
        "extract a clean, structured recommendation card. Output only markdown, no preamble.",
        """\
CAPTION:
{caption}

TRANSCRIPT:
{transcript}

Extract the recommendation and format it as markdown with this structure:
- Place name (H1)
- **Location:** (city, country, or address if mentioned)
- **Type:** (restaurant / café / landmark / city / neighbourhood / etc.)
- ## Why Visit (the reviewer's reasons)
- ## Tips
  - Best time to go (if mentioned)
  - How to get there (if mentioned)
  - What to order / see / do (if mentioned)
- ## Notes (reservations needed, price range, caveats)""",
    ),
}


def extract_content(
    content_type: str,
    transcript: str,
    caption: str,
    api_key: str,
) -> tuple[str, str]:
    """Call the LLM to extract and format content of the given type.

    Returns (markdown, slugified_title).
    """
    system_prompt, user_template = _PROMPTS[content_type]
    user_message = user_template.format(
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
                {"role": "system", "content": system_prompt},
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
