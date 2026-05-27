import os
from pathlib import Path
import yt_dlp

_COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")


def download_reel(url: str, work_dir: Path) -> Path:
    """Download an Instagram reel and return the local video file path."""
    work_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(work_dir / "reel.%(ext)s")

    ydl_opts = {
        "outtmpl": output_template,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
    }

    cookies = Path(_COOKIES_FILE)
    if cookies.exists():
        ydl_opts["cookiefile"] = str(cookies)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            ext = info.get("ext", "mp4")
            video_path = work_dir / f"reel.{ext}"
            if not video_path.exists():
                # yt-dlp may have merged to mp4 regardless of source ext
                video_path = work_dir / "reel.mp4"
            if not video_path.exists():
                raise FileNotFoundError("Downloaded video file not found in work directory.")
            return video_path
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(f"yt-dlp failed to download the reel: {e}") from e
