import http.cookiejar
import os
import re
from pathlib import Path

import httpx
import instaloader
import yt_dlp

_COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")
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

    # --- video path (yt-dlp handles reels fine) ---
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

    # --- image carousel path (instaloader handles images/carousels) ---
    # yt-dlp raises "No video formats found" at the extractor level for image posts
    # regardless of format selector or download=False — use instaloader instead.
    image_paths, caption = _download_carousel_images(url, work_dir, cookies)
    return None, image_paths, caption


def _download_carousel_images(url: str, work_dir: Path, cookies_path: Path) -> tuple[list[Path], str]:
    shortcode = _extract_shortcode(url)

    L = instaloader.Instaloader(quiet=True, sleep=False,
                                 download_pictures=False, download_videos=False,
                                 download_video_thumbnails=False, download_geotags=False,
                                 download_comments=False, save_metadata=False)

    if cookies_path.exists():
        jar = http.cookiejar.MozillaCookieJar()
        jar.load(str(cookies_path), ignore_discard=True, ignore_expires=True)
        L.context._session.cookies.update({c.name: c.value for c in jar})

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
    except Exception as e:
        raise RuntimeError(f"instaloader failed to fetch post {shortcode}: {e}") from e

    caption = post.caption or ""

    image_urls: list[str] = []
    try:
        nodes = list(post.get_sidecar_nodes())
    except Exception:
        nodes = []

    if nodes:
        for node in nodes:
            if not node.is_video:
                image_urls.append(node.display_url)
    elif not post.is_video:
        image_urls.append(post.url)

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


def _extract_shortcode(url: str) -> str:
    m = re.search(r'/(?:p|reel)/([A-Za-z0-9_-]+)', url)
    if not m:
        raise ValueError(f"Cannot extract shortcode from Instagram URL: {url}")
    return m.group(1)
