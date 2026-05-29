import httpx

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
DETECTOR_MODEL = "google/gemma-4-31b-it"

CONTENT_TYPES = ["recipe", "movie", "book", "place", "game"]

_SYSTEM_PROMPT = (
    "You are a content classifier. Given text from an Instagram post (caption and/or transcript), "
    "classify it into exactly one of these categories:\n"
    "- recipe: a cooking video or food preparation post\n"
    "- movie: a film or TV show recommendation or review\n"
    "- book: a book recommendation or review\n"
    "- place: a location, restaurant, café, city, or travel destination\n"
    "- game: a video game, board game, card game, or social game recommendation or review\n"
    "Respond with only the single lowercase word (recipe, movie, book, place, or game). No other text."
)


def detect_content_type(transcript: str, caption: str, api_key: str) -> str:
    """Classify content type from transcript and caption. Returns one of CONTENT_TYPES."""
    user_message = f"CAPTION:\n{caption or '(none)'}\n\nTRANSCRIPT:\n{transcript or '(none)'}"

    response = httpx.post(
        OPENROUTER_CHAT_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": DETECTOR_MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 10,
        },
        timeout=30,
    )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        return "recipe"

    result = response.json()["choices"][0]["message"]["content"].strip().lower()
    return result if result in CONTENT_TYPES else "recipe"
