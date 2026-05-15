import httpx


OEMBED_URL = "https://www.instagram.com/api/v1/oembed/"


def fetch_caption(reel_url: str) -> str | None:
    """Fetch the Instagram post caption via the public oEmbed endpoint.

    Returns the caption string, or None if unavailable.
    """
    try:
        response = httpx.get(
            OEMBED_URL,
            params={"url": reel_url, "hidecaption": "false"},
            timeout=15,
            headers={"User-Agent": "instagram-recipe-extractor/1.0"},
        )
        response.raise_for_status()
        data = response.json()
        title: str = data.get("title", "").strip()
        return title if title else None
    except httpx.HTTPStatusError as e:
        # 404 = post not found or private; 401 = auth required
        return None
    except (httpx.RequestError, ValueError):
        return None
