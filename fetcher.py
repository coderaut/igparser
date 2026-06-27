import os
import re
from pathlib import Path

import httpx

from logger import log

APIFY_ACTOR = "apify~instagram-scraper"
APIFY_ENDPOINT = f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"
_REQUEST_TIMEOUT = 120
_IMG_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.instagram.com/"}


def _extract_shortcode(url: str) -> str:
    m = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
    if not m:
        raise ValueError(f"Cannot extract shortcode from Instagram URL: {url}")
    return m.group(1)


def _parse_item(item: dict) -> tuple[str | None, list[str], str, dict]:
    """Classify an Apify dataset item into (video_url, image_urls, caption, meta).

    Exactly one of video_url / image_urls is non-empty (both empty only when the
    post exposes no downloadable media).
    """
    caption = (item.get("caption") or "").strip()
    meta = {
        "author": item.get("ownerUsername") or "",
        "full_name": item.get("ownerFullName") or "",
        "source_url": item.get("url") or "",
        "timestamp": item.get("timestamp") or "",
        "type": item.get("type") or "",
        "shortcode": item.get("shortCode") or "",
    }

    video_url = item.get("videoUrl")
    if video_url:
        return video_url, [], caption, meta

    # Carousel: childPosts holds each slide; OCR images only, skip video slides
    # (matches legacy instaloader behavior which collected non-video sidecar nodes).
    image_urls: list[str] = []
    for child in item.get("childPosts") or []:
        if child.get("videoUrl"):
            continue
        img = child.get("displayUrl") or child.get("url")
        if img:
            image_urls.append(img)

    # Fallbacks: explicit images array, or a single-image post's displayUrl.
    if not image_urls:
        image_urls = list(item.get("images") or [])
    if not image_urls and item.get("displayUrl"):
        image_urls = [item["displayUrl"]]

    return None, image_urls, caption, meta


def _download_media(url: str, dest: Path) -> Path:
    r = httpx.get(url, headers=_IMG_HEADERS, follow_redirects=True, timeout=_REQUEST_TIMEOUT)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def fetch_post(url: str, work_dir: Path) -> tuple[Path | None, list[Path], str, dict]:
    """Fetch an Instagram post/reel/carousel via Apify and download its media.

    Returns (video_path, image_paths, caption, meta):
      - Video post:     (video_path, [], caption, meta)
      - Image carousel: (None, [slide_01.jpg, ...], caption, meta)
      - Single image:   (None, [slide_01.jpg], caption, meta)
    Exactly one of video_path / image_paths is non-empty.
    Raises RuntimeError on auth failure, inaccessible post, or total media failure.
    """
    log.info("fetch_post start: %s", url)
    work_dir.mkdir(parents=True, exist_ok=True)
    _extract_shortcode(url)  # validate the URL is a post/reel before spending an Apify call

    token = os.getenv("APIFY_TOKEN", "").strip()
    if not token:
        raise RuntimeError("APIFY_TOKEN is not set — add it to .env")

    payload = {
        "directUrls": [url],
        "resultsType": "posts",
        "resultsLimit": 1,
        "addParentData": False,  # suppress Apify parent-post inflation on carousel children
    }
    try:
        resp = httpx.post(
            APIFY_ENDPOINT, params={"token": token}, json=payload, timeout=_REQUEST_TIMEOUT
        )
        resp.raise_for_status()
    except httpx.TimeoutException as e:
        raise RuntimeError(f"Apify request timed out after {_REQUEST_TIMEOUT}s") from e
    except httpx.HTTPStatusError as e:
        code = getattr(e.response, "status_code", "?")
        if code == 401:
            raise RuntimeError("Apify rejected the token (401) — check APIFY_TOKEN") from e
        body = getattr(e.response, "text", "") or ""
        raise RuntimeError(f"Apify API error {code}: {body[:300]}") from e

    items = resp.json()
    if not items:
        raise RuntimeError(
            "post not accessible (private/deleted/age-restricted) — forward a screenshot instead"
        )

    video_url, image_urls, caption, meta = _parse_item(items[0])

    if video_url:
        video_path = _download_media(video_url, work_dir / "reel.mp4")
        log.info("video downloaded: %d bytes", video_path.stat().st_size)
        return video_path, [], caption, meta

    image_paths: list[Path] = []
    for i, img_url in enumerate(image_urls):
        dest = work_dir / f"slide_{i + 1:02d}.jpg"
        try:
            image_paths.append(_download_media(img_url, dest))
        except Exception as e:  # warn-and-continue per slide (legacy carousel semantics)
            log.warning("slide %d download failed: %s", i + 1, e)

    if not image_paths and not caption:
        raise RuntimeError("Apify returned no downloadable media and no caption")

    log.info("carousel done: %d/%d slides", len(image_paths), len(image_urls))
    return None, image_paths, caption, meta


def inject_source_line(markdown: str, meta: dict) -> str:
    """Insert a '> Source: …' blockquote immediately after the first H1.

    Falls back to prepending if there is no H1. Returns markdown unchanged if
    meta carries no author/source/date.
    """
    author = meta.get("author") or ""
    src = meta.get("source_url") or ""
    date = (meta.get("timestamp") or "")[:10]  # YYYY-MM-DD slice of the ISO timestamp

    parts: list[str] = []
    if author:
        parts.append(f"@{author}")
    if src:
        parts.append(f"[original post]({src})")
    if date:
        parts.append(date)
    if not parts:
        return markdown
    line = "> Source: " + " · ".join(parts)

    lines = markdown.splitlines()
    for idx, ln in enumerate(lines):
        if ln.strip().startswith("# "):
            lines.insert(idx + 1, "")
            lines.insert(idx + 2, line)
            return "\n".join(lines)
    return line + "\n\n" + markdown
