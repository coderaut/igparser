import http.cookiejar
import os
import re
from pathlib import Path

import httpx
import instaloader
import yt_dlp

from logger import log

_COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")
_IMG_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.instagram.com/"}


def download_reel(url: str, work_dir: Path) -> tuple[Path | None, list[Path], str]:
    """Download an Instagram reel/post and return (video_path, image_paths, caption).

    For video posts: (video_path, [], caption)
    For image carousels: (None, [slide1.jpg, ...], caption)
    Exactly one of video_path / image_paths will be non-empty.
    """
    log.info("download_reel start: %s", url)
    work_dir.mkdir(parents=True, exist_ok=True)

    base_opts: dict = {"quiet": True, "no_warnings": True}
    cookies = Path(_COOKIES_FILE)
    if cookies.exists():
        base_opts["cookiefile"] = str(cookies)
        log.debug("cookies file: %s", cookies)
    else:
        log.warning("cookies file not found at %s — downloading without auth", cookies)

    # --- video path (yt-dlp handles reels fine) ---
    video_opts = {
        **base_opts,
        "outtmpl": str(work_dir / "reel.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
    }
    try:
        with yt_dlp.YoutubeDL(video_opts) as ydl:
            log.debug("yt-dlp extracting info...")
            info = ydl.extract_info(url, download=True)
            reported_ext = info.get("ext", "mp4")
            log.debug("yt-dlp done: ext=%s title=%r", reported_ext, info.get("title"))
            work_dir_files = [p.name for p in work_dir.iterdir()] if work_dir.exists() else []
            log.debug("work_dir contents after download: %s", work_dir_files)

            candidates = [
                work_dir / f"reel.{reported_ext}",
                work_dir / "reel.mp4",
            ]
            video_path = next((p for p in candidates if p.exists()), None)
            if video_path is None:
                matches = [p for p in work_dir.glob("reel.*") if p.suffix not in (".part", ".ytdl")]
                video_path = matches[0] if matches else None

            if video_path is None:
                # yt-dlp found metadata but wrote nothing — happens with carousel/image posts
                # where a stub video entry exists. Fall through to instaloader.
                log.warning(
                    "yt-dlp reported ext=%s but wrote no file (work_dir empty) — "
                    "treating as image carousel, falling back to instaloader",
                    reported_ext,
                )
            else:
                log.info("video downloaded: %s (%d bytes)", video_path.name, video_path.stat().st_size)
                caption = (info.get("description") or "").strip()
                return video_path, [], caption
    except yt_dlp.utils.DownloadError as e:
        if "No video formats found" not in str(e):
            log.error("yt-dlp DownloadError: %s", e)
            raise RuntimeError(f"yt-dlp failed to download the reel: {e}") from e
        log.debug("yt-dlp: no video formats — falling back to instaloader (image carousel)")

    # --- image carousel path (instaloader handles images/carousels) ---
    # yt-dlp raises "No video formats found" at the extractor level for image posts
    # regardless of format selector or download=False — use instaloader instead.
    image_paths, caption = _download_carousel_images(url, work_dir, cookies)
    return None, image_paths, caption


def _download_carousel_images(url: str, work_dir: Path, cookies_path: Path) -> tuple[list[Path], str]:
    shortcode = _extract_shortcode(url)
    log.info("fetching carousel via instaloader: shortcode=%s", shortcode)

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
        log.error("instaloader failed for shortcode %s: %s", shortcode, e)
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

    log.debug("carousel: %d image(s) to download", len(image_urls))

    image_paths: list[Path] = []
    for i, img_url in enumerate(image_urls):
        img_path = work_dir / f"slide_{i + 1:02d}.jpg"
        try:
            r = httpx.get(img_url, headers=_IMG_HEADERS, follow_redirects=True, timeout=30)
            r.raise_for_status()
            img_path.write_bytes(r.content)
            image_paths.append(img_path)
        except Exception as e:
            log.warning("slide %d download failed: %s", i + 1, e)
            continue

    log.info("carousel done: %d/%d slides downloaded", len(image_paths), len(image_urls))
    return image_paths, caption


def _extract_shortcode(url: str) -> str:
    m = re.search(r'/(?:p|reel)/([A-Za-z0-9_-]+)', url)
    if not m:
        raise ValueError(f"Cannot extract shortcode from Instagram URL: {url}")
    return m.group(1)
