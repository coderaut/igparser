import os
from pathlib import Path
import yt_dlp

_COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")
_IMAGE_EXTS = {".jpg", ".jpeg", ".webp", ".png"}


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
    img_opts = {
        **base_opts,
        "outtmpl": str(work_dir / "slide_%(autonumber)s.%(ext)s"),
        "format": "best",
    }
    try:
        with yt_dlp.YoutubeDL(img_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        caption = _caption_from_info(info)
        images = sorted(p for p in work_dir.iterdir() if p.suffix.lower() in _IMAGE_EXTS)
        return None, images, caption
    except yt_dlp.utils.DownloadError as e2:
        raise RuntimeError(f"yt-dlp failed to download carousel images: {e2}") from e2


def _caption_from_info(info: dict) -> str:
    if info.get("description"):
        return info["description"].strip()
    for entry in (info.get("entries") or []):
        if entry and entry.get("description"):
            return entry["description"].strip()
    return ""
