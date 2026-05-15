import re

import httpx

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_MODEL = "google/gemma-4-31b-it"

SYSTEM_PROMPT = (
    "You are a recipe extraction assistant. Given a video transcript and/or Instagram caption "
    "from a cooking reel, extract a clean, complete recipe. If information is missing or "
    "ambiguous, make reasonable culinary assumptions and note them. Output only markdown, no preamble."
)

USER_TEMPLATE = """\
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
- ## Notes (any tips, substitutions, or assumptions made)"""


def extract_recipe(
    transcript: str,
    caption: str,
    api_key: str,
) -> tuple[str, str]:
    """Call the LLM via OpenRouter to extract and format a recipe.

    Returns (recipe_markdown, slugified_title).
    """
    user_message = USER_TEMPLATE.format(
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
                {"role": "system", "content": SYSTEM_PROMPT},
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

    recipe_md: str = response.json()["choices"][0]["message"]["content"].strip()
    title = _extract_title(recipe_md)
    slug = _slugify(title)
    return recipe_md, slug


def _extract_title(markdown: str) -> str:
    """Pull the H1 title from the markdown, falling back to a default."""
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return "recipe"


def _slugify(text: str) -> str:
    """Convert a title to a filename-safe slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = text.strip("-")
    return text or "recipe"
