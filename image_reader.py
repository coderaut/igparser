import base64
from pathlib import Path

import httpx

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
VISION_MODEL = "google/gemma-4-31b-it"

_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".png": "image/png",
}


def read_images(image_paths: list[Path], api_key: str) -> str:
    """Extract visible text from carousel image slides using a vision LLM."""
    if not image_paths:
        return ""

    content: list[dict] = [
        {
            "type": "text",
            "text": (
                "These are slides from an Instagram carousel post. "
                "Extract all visible text from each slide in order. "
                "Output only the raw text content — no image descriptions, no commentary."
            ),
        }
    ]
    for img_path in image_paths:
        mime = _MIME.get(img_path.suffix.lower(), "image/jpeg")
        data = base64.b64encode(img_path.read_bytes()).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{data}"},
        })

    response = httpx.post(
        OPENROUTER_CHAT_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": VISION_MODEL,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 4096,
        },
        timeout=180,
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"OpenRouter vision API error {response.status_code}: {response.text}"
        ) from e

    return response.json()["choices"][0]["message"]["content"].strip()
