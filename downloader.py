import os
from pathlib import Path
import yt_dlp

_COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")


def download_reel(url: str, work_dir: Path) -> tuple[Path | None, str]:
    """Download an Instagram reel/post and return (video_path, caption).

    For image-only posts (carousels with no video), video_path is None and
    caption is extracted from metadata. Returns empty string for caption if unavailable.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(work_dir / "reel.%(ext)s")

    base_opts: dict = {
        "quiet": True,
        "no_warnings": True,
    }

    cookies = Path(_COOKIES_FILE)
    if cookies.exists():
        base_opts["cookiefile"] = str(cookies)

    ydl_opts = {
        **base_opts,
        "outtmpl": output_template,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            ext = info.get("ext", "mp4")
            video_path = work_dir / f"reel.{ext}"
            if not video_path.exists():
                video_path = work_dir / "reel.mp4"
            if not video_path.exists():
                raise FileNotFoundError("Downloaded video file not found in work directory.")
            caption = (info.get("description") or "").strip()
            return video_path, caption
    except yt_dlp.utils.DownloadError as e:
        if "No video formats found" in str(e):
            # Image-only carousel — fetch metadata only to get the caption
            try:
                with yt_dlp.YoutubeDL({**base_opts, "skip_download": True}) as ydl:
                    info = ydl.extract_info(url, download=False)
                caption = (info.get("description") or "").strip()
                return None, caption
            except yt_dlp.utils.DownloadError as e2:
                raise RuntimeError(f"yt-dlp failed to fetch post metadata: {e2}") from e2
        raise RuntimeError(f"yt-dlp failed to download the reel: {e}") from e
