import http.cookiejar
import os
import re
from pathlib import Path

import httpx
import instaloader
import yt_dlp

from logger import log

_COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies/instagram.txt")
_IG_USERNAME = os.getenv("IG_USERNAME", "")
_IG_PASSWORD = os.getenv("IG_PASSWORD", "")
_IMG_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.instagram.com/"}


class _AuthError(Exception):
    pass


def _make_loader() -> instaloader.Instaloader:
    return instaloader.Instaloader(
        quiet=True, sleep=False,
        download_pictures=False, download_videos=False,
        download_video_thumbnails=False, download_geotags=False,
        download_comments=False, save_metadata=False,
    )


def _session_file() -> Path:
    return Path(_COOKIES_FILE).parent / f"session-{_IG_USERNAME}"


def _load_or_login(L: instaloader.Instaloader, force: bool = False) -> bool:
    """Load saved session or log in fresh. Returns True on success."""
    sess = _session_file()
    if not force and sess.exists():
        try:
            L.load_session_from_file(_IG_USERNAME, str(sess))
            log.debug("instaloader session loaded from %s", sess)
            return True
        except Exception as e:
            log.warning("session load failed (%s) — re-logging in", e)

    log.info("logging in to Instagram as %s", _IG_USERNAME)
    try:
        L.login(_IG_USERNAME, _IG_PASSWORD)
    except instaloader.exceptions.TwoFactorAuthRequiredException:
        log.error(
            "Instagram 2FA required. Run this once to complete login interactively:\n"
            "  docker exec -it ig-parser python -c \""
            "import instaloader, os; L=instaloader.Instaloader(); "
            "L.interactive_login(os.environ['IG_USERNAME']); "
            "L.save_session_to_file('/cookies/session-' + os.environ['IG_USERNAME'])\""
        )
        return False
    except instaloader.exceptions.BadCredentialsException:
        log.error("Instagram login failed: bad credentials — check IG_USERNAME/IG_PASSWORD in .env")
        return False
    except Exception as e:
        log.error("Instagram login failed: %s", e)
        return False

    L.save_session_to_file(str(sess))
    log.info("session saved to %s", sess)
    return True


def _sync_cookies(L: instaloader.Instaloader, cookies_path: Path) -> None:
    """Write instaloader session cookies to Netscape file for yt-dlp."""
    jar = http.cookiejar.MozillaCookieJar(str(cookies_path))
    for cookie in L.context._session.cookies:
        jar.set_cookie(cookie)
    cookies_path.parent.mkdir(parents=True, exist_ok=True)
    jar.save(ignore_discard=True, ignore_expires=True)
    log.debug("synced %d cookies → %s", sum(1 for _ in L.context._session.cookies), cookies_path)


def _yt_dlp_download(
    url: str, work_dir: Path, cookies_path: Path | None
) -> tuple[Path, list, str] | None:
    """Try yt-dlp download. Returns (video_path, [], caption) on success, None for carousels.
    Raises _AuthError on Instagram auth failure, RuntimeError on other errors."""
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(work_dir / "reel.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
    }
    if cookies_path and cookies_path.exists():
        opts["cookiefile"] = str(cookies_path)
        log.debug("yt-dlp using cookies: %s", cookies_path)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            log.debug("yt-dlp extracting info...")
            info = ydl.extract_info(url, download=True)
            reported_ext = info.get("ext", "mp4")
            log.debug("yt-dlp done: ext=%s title=%r", reported_ext, info.get("title"))

            work_dir_files = [p.name for p in work_dir.iterdir()] if work_dir.exists() else []
            log.debug("work_dir contents after download: %s", work_dir_files)

            candidates = [work_dir / f"reel.{reported_ext}", work_dir / "reel.mp4"]
            video_path = next((p for p in candidates if p.exists()), None)
            if video_path is None:
                matches = [p for p in work_dir.glob("reel.*") if p.suffix not in (".part", ".ytdl")]
                video_path = matches[0] if matches else None

            if video_path is None:
                log.warning(
                    "yt-dlp reported ext=%s but wrote no file (work_dir empty) — "
                    "treating as image carousel, falling back to instaloader",
                    reported_ext,
                )
                return None

            log.info("video downloaded: %s (%d bytes)", video_path.name, video_path.stat().st_size)
            caption = (info.get("description") or "").strip()
            return video_path, [], caption

    except yt_dlp.utils.DownloadError as e:
        err_lower = str(e).lower()
        if "no video formats found" in err_lower:
            log.debug("yt-dlp: no video formats — falling back to instaloader (image carousel)")
            return None
        if any(p in err_lower for p in ("login required", "rate-limit", "not available")):
            log.error("yt-dlp DownloadError: %s", e)
            raise _AuthError(str(e)) from e
        log.error("yt-dlp DownloadError: %s", e)
        raise RuntimeError(f"yt-dlp failed to download the reel: {e}") from e


def download_reel(url: str, work_dir: Path) -> tuple[Path | None, list[Path], str]:
    """Download an Instagram reel/post and return (video_path, image_paths, caption).

    For video posts: (video_path, [], caption)
    For image carousels: (None, [slide1.jpg, ...], caption)
    Exactly one of video_path / image_paths will be non-empty.
    """
    log.info("download_reel start: %s", url)
    work_dir.mkdir(parents=True, exist_ok=True)

    cookies = Path(_COOKIES_FILE)
    L = _make_loader()
    has_creds = bool(_IG_USERNAME and _IG_PASSWORD)

    # Credential login (best-effort — fails silently on datacenter IPs, falls back to cookies.txt)
    if has_creds and _load_or_login(L):
        _sync_cookies(L, cookies)

    # Always load cookies.txt into instaloader session for carousel use.
    # If credential login synced fresh cookies above, this just reinforces them.
    if cookies.exists():
        jar = http.cookiejar.MozillaCookieJar()
        jar.load(str(cookies), ignore_discard=True, ignore_expires=True)
        L.context._session.cookies.update({c.name: c.value for c in jar})
    else:
        log.warning("no auth available — attempting unauthenticated download")

    # --- video path (yt-dlp handles reels) ---
    try:
        result = _yt_dlp_download(url, work_dir, cookies if cookies.exists() else None)
        if result is not None:
            return result
        # None means no video file written → image carousel, fall through
    except _AuthError:
        if not has_creds:
            raise RuntimeError(
                "Instagram auth failed. Refresh cookies/instagram.txt from your browser "
                "(export via 'Get cookies.txt LOCALLY' extension), then docker restart ig-parser."
            )
        log.info("yt-dlp auth error — refreshing session and retrying once")
        for f in work_dir.glob("reel.*"):
            f.unlink(missing_ok=True)
        if not _load_or_login(L, force=True):
            # Credential login failed (likely blocked on this IP) — nothing more we can do
            raise RuntimeError(
                "Instagram auth failed. Automated login is blocked from this server IP. "
                "Refresh cookies/instagram.txt from your browser, then docker restart ig-parser."
            )
        _sync_cookies(L, cookies)
        try:
            result = _yt_dlp_download(url, work_dir, cookies)
            if result is not None:
                return result
        except _AuthError as e:
            raise RuntimeError(
                f"Instagram auth failed after session refresh: {e}\n"
                "Refresh cookies/instagram.txt from your browser, then docker restart ig-parser."
            ) from e

    # --- image carousel path (instaloader) ---
    image_paths, caption = _download_carousel_images(url, work_dir, L)
    return None, image_paths, caption


def _download_carousel_images(
    url: str, work_dir: Path, L: instaloader.Instaloader
) -> tuple[list[Path], str]:
    shortcode = _extract_shortcode(url)
    log.info("fetching carousel via instaloader: shortcode=%s", shortcode)

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

    log.info("carousel done: %d/%d slides downloaded", len(image_paths), len(image_urls))
    return image_paths, caption


def _extract_shortcode(url: str) -> str:
    m = re.search(r'/(?:p|reel)/([A-Za-z0-9_-]+)', url)
    if not m:
        raise ValueError(f"Cannot extract shortcode from Instagram URL: {url}")
    return m.group(1)
