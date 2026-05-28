import os
from pathlib import Path

import httpx
import yt_dlp

_COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")
_IMAGE_EXTS = {".jpg", ".jpeg", ".webp", ".png"}
_IMG_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.instagram.com/"}


def download_reel(url: str, work_dir: Path) -> tuple[Path | None, list[Path], str]:
    """Download an Instagram reel/post and return (video_path, image_paths, caption).

    For video posts: (video_path, [], caption)
    For image carousels: (None, [slide1.jpg, ...], caption)
    Exactly one of video_path / image_paths will be non-empty.
    """
    work_dir.mkdir(parents=True, exist_ok=True)

    base_opts: dict = {"quiet": True, "no_warnings": True}
    cookies = Path(_COOKIES_FILE)
    if cookies.exists():
        base_opts["cookiefile"] = str(cookies)

    # --- video path ---
    video_opts = {
        **base_opts,
        "outtmpl": str(work_dir / "reel.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
    }
    try:
        with yt_dlp.YoutubeDL(video_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            ext = info.get("ext", "mp4")
            video_path = work_dir / f"reel.{ext}"
            if not video_path.exists():
                video_path = work_dir / "reel.mp4"
            if not video_path.exists():
                raise FileNotFoundError("Downloaded video file not found in work directory.")
            caption = (info.get("description") or "").strip()
            return video_path, [], caption
    except yt_dlp.utils.DownloadError as e:
        if "No video formats found" not in str(e):
            raise RuntimeError(f"yt-dlp failed to download the reel: {e}") from e

    # --- image carousel path ---
    # yt-dlp raises "No video formats found" at the extractor level for image-only
    # posts — no format selector can avoid it. Instead: extract metadata only
    # (which works fine), parse out the image URLs, download them with httpx.
    image_paths, caption = _download_carousel_images(url, work_dir, base_opts)
    return None, image_paths, caption


def _download_carousel_images(url: str, work_dir: Path, base_opts: dict) -> tuple[list[Path], str]:
    try:
        with yt_dlp.YoutubeDL({**base_opts, "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(f"yt-dlp failed to fetch post metadata: {e}") from e

    caption = _caption_from_info(info)

    # Carousel → entries list; single image → wrap info in list
    entries = info.get("entries") or [info]
    image_urls: list[str] = []
    for entry in entries:
        if not entry:
            continue
        img_url = _best_image_url(entry)
        if img_url:
            image_urls.append(img_url)

    # Last resort: top-level thumbnail
    if not image_urls and info.get("thumbnail"):
        image_urls = [info["thumbnail"]]

    image_paths: list[Path] = []
    for i, img_url in enumerate(image_urls):
        img_path = work_dir / f"slide_{i + 1:02d}.jpg"
        try:
            r = httpx.get(img_url, headers=_IMG_HEADERS, follow_redirects=True, timeout=30)
            r.raise_for_status()
            img_path.write_bytes(r.content)
            image_paths.append(img_path)
        except Exception:
            continue

    return image_paths, caption


def _best_image_url(entry: dict) -> str | None:
    for fmt in entry.get("formats") or []:
        if fmt.get("ext") in ("jpg", "jpeg", "webp", "png"):
            return fmt.get("url")
    return entry.get("url") or entry.get("thumbnail")


def _caption_from_info(info: dict) -> str:
    if info.get("description"):
        return info["description"].strip()
    for entry in (info.get("entries") or []):
        if entry and entry.get("description"):
            return entry["description"].strip()
    return ""
