# ig-parser Apify Fetch Backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. A fresh Sonnet subagent implements each task; the main model reviews between tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ig-parser's cookie/yt-dlp/instaloader Instagram fetch path with the Apify Instagram Scraper, keeping the entire local media-understanding pipeline (Whisper, Gemma vision, frame fallback, LLM formatting) unchanged.

**Architecture:** A new `fetcher.py` exposes `fetch_post(url, work_dir) -> (video_path, image_paths, caption, meta)` — a near-drop-in for the old `download_reel`. It calls Apify's synchronous `run-sync-get-dataset-items` endpoint, classifies the returned item (video / carousel / single image), downloads the public CDN media URLs to local files, and returns the same tuple shape plus a `meta` dict. `main.py` and `app.py` swap the import, unpack the 4-tuple, and inject a source-attribution line under the H1. The old fetch code is archived to `legacy/`.

**Tech Stack:** Python 3.12, httpx (already a dep), pytest (new dev dep), Apify Instagram Scraper actor `apify/instagram-scraper`, Docker Compose, Streamlit + Typer.

## Global Constraints

- Apify-only for v1. No HikerAPI/SociaVault/oEmbed fallback chain. The fetch layer stays behind the single `fetch_post()` function so a fallback can be added later.
- Public posts only. Private/deleted/age-gated posts fail with: `post not accessible (private/deleted/age-restricted) — forward a screenshot instead`. No cookie fallback.
- One URL per Apify call: `resultsLimit: 1`, `resultsType: "posts"`, hard request timeout (120s).
- Apify endpoint: `POST https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items?token=<APIFY_TOKEN>`.
- Token comes from env var `APIFY_TOKEN` (dedicated to ig-parser). Never commit the real token.
- Downstream modules (`transcriber.py`, `image_reader.py`, `content_extractor.py`, `caption.py`, `logger.py`) must NOT change behavior.
- Output enrichment is author + source URL + date only (skip likes/views/hashtags), injected as a `> Source: …` blockquote under the H1 — never as YAML frontmatter (collides with the Hermes ig-save skill's own frontmatter).
- Media CDN URLs expire: download immediately, never persist the URL.
- All Python files use the existing logger: `from logger import log`.

---

### Task 1: Pure helpers in `fetcher.py` + test harness + Apify fixtures

Build the pure, I/O-free core first: shortcode validation, Apify-item classification, and source-line injection. Set up pytest and recorded Apify response fixtures.

**Files:**
- Create: `fetcher.py`
- Create: `tests/__init__.py`
- Create: `tests/test_fetcher.py`
- Create: `tests/fixtures/apify_video.json`
- Create: `tests/fixtures/apify_carousel.json`
- Create: `tests/fixtures/apify_image.json`
- Create: `tests/fixtures/apify_empty.json`
- Modify: `pyproject.toml` (add `[project.optional-dependencies] dev = ["pytest>=8.0"]`)

**Interfaces:**
- Produces:
  - `_extract_shortcode(url: str) -> str`
  - `_parse_item(item: dict) -> tuple[str | None, list[str], str, dict]` — returns `(video_url, image_urls, caption, meta)`; exactly one of `video_url` / `image_urls` is non-empty (both empty only if the post has no downloadable media).
  - `inject_source_line(markdown: str, meta: dict) -> str`
  - `meta` dict keys: `author`, `full_name`, `source_url`, `timestamp`, `type`, `shortcode`.

- [ ] **Step 1: Create the venv and install dev deps**

Run:
```bash
cd "/root/Repo Apps/IG Parser"
python3 -m venv .venv
.venv/bin/pip install -q httpx python-dotenv pytest
```
Expected: installs without error. (`.venv` is git-ignored and persists for later tasks.)

- [ ] **Step 2: Add the pytest dev dependency to `pyproject.toml`**

Insert after the `dependencies = [...]` block (after line 15), before `[tool.setuptools]`:
```toml
[project.optional-dependencies]
dev = ["pytest>=8.0"]
```

- [ ] **Step 3: Create the four Apify fixtures**

`tests/fixtures/apify_video.json`:
```json
[
  {
    "type": "Video",
    "shortCode": "VID123abc",
    "caption": "My reel caption with #tags",
    "url": "https://www.instagram.com/reel/VID123abc/",
    "videoUrl": "https://cdn.example.com/reel.mp4",
    "displayUrl": "https://cdn.example.com/thumb.jpg",
    "ownerUsername": "creator",
    "ownerFullName": "The Creator",
    "timestamp": "2026-06-20T10:00:00.000Z",
    "productType": "clips",
    "videoDuration": 30.0
  }
]
```

`tests/fixtures/apify_carousel.json` (3 children: 2 images + 1 video that must be skipped):
```json
[
  {
    "type": "Sidecar",
    "shortCode": "CAR456def",
    "caption": "Swipe for tips",
    "url": "https://www.instagram.com/p/CAR456def/",
    "ownerUsername": "tipster",
    "ownerFullName": "Tip Ster",
    "timestamp": "2026-06-18T08:30:00.000Z",
    "childPosts": [
      {"type": "Image", "displayUrl": "https://cdn.example.com/s1.jpg"},
      {"type": "Image", "displayUrl": "https://cdn.example.com/s2.jpg"},
      {"type": "Video", "videoUrl": "https://cdn.example.com/s3.mp4", "displayUrl": "https://cdn.example.com/s3.jpg"}
    ]
  }
]
```

`tests/fixtures/apify_image.json`:
```json
[
  {
    "type": "Image",
    "shortCode": "IMG789ghi",
    "caption": "A single photo",
    "url": "https://www.instagram.com/p/IMG789ghi/",
    "displayUrl": "https://cdn.example.com/single.jpg",
    "ownerUsername": "photog",
    "ownerFullName": "Photo Grapher",
    "timestamp": "2026-06-15T12:00:00.000Z"
  }
]
```

`tests/fixtures/apify_empty.json`:
```json
[]
```

- [ ] **Step 4: Create `tests/__init__.py`**

Create an empty file:
```python
```

- [ ] **Step 5: Write the failing tests for the pure helpers**

`tests/test_fetcher.py`:
```python
import json
from pathlib import Path

import pytest

import fetcher

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> list:
    return json.loads((FIXTURES / name).read_text())


# --- _extract_shortcode ---

@pytest.mark.parametrize("url,expected", [
    ("https://www.instagram.com/p/ABC123/", "ABC123"),
    ("https://www.instagram.com/reel/XyZ_-9/", "XyZ_-9"),
    ("https://instagram.com/reel/abc/?igsh=foo", "abc"),
])
def test_extract_shortcode_ok(url, expected):
    assert fetcher._extract_shortcode(url) == expected


def test_extract_shortcode_rejects_non_post():
    with pytest.raises(ValueError):
        fetcher._extract_shortcode("https://www.instagram.com/someuser/")


# --- _parse_item ---

def test_parse_item_video():
    item = _load("apify_video.json")[0]
    video_url, image_urls, caption, meta = fetcher._parse_item(item)
    assert video_url == "https://cdn.example.com/reel.mp4"
    assert image_urls == []
    assert caption == "My reel caption with #tags"
    assert meta["author"] == "creator"
    assert meta["source_url"] == "https://www.instagram.com/reel/VID123abc/"
    assert meta["timestamp"] == "2026-06-20T10:00:00.000Z"
    assert meta["type"] == "Video"
    assert meta["shortcode"] == "VID123abc"


def test_parse_item_carousel_skips_video_child():
    item = _load("apify_carousel.json")[0]
    video_url, image_urls, caption, meta = fetcher._parse_item(item)
    assert video_url is None
    assert image_urls == [
        "https://cdn.example.com/s1.jpg",
        "https://cdn.example.com/s2.jpg",
    ]
    assert meta["author"] == "tipster"


def test_parse_item_single_image():
    item = _load("apify_image.json")[0]
    video_url, image_urls, caption, meta = fetcher._parse_item(item)
    assert video_url is None
    assert image_urls == ["https://cdn.example.com/single.jpg"]
    assert caption == "A single photo"


# --- inject_source_line ---

def test_inject_source_line_after_h1():
    md = "# Title\n\nBody text."
    meta = {
        "author": "creator",
        "source_url": "https://www.instagram.com/reel/VID123abc/",
        "timestamp": "2026-06-20T10:00:00.000Z",
    }
    out = fetcher.inject_source_line(md, meta)
    lines = out.splitlines()
    assert lines[0] == "# Title"
    assert lines[2] == (
        "> Source: @creator · "
        "[original post](https://www.instagram.com/reel/VID123abc/) · 2026-06-20"
    )
    assert "Body text." in out


def test_inject_source_line_no_h1_prepends():
    md = "Just body, no heading."
    meta = {"author": "x", "source_url": "https://e.com/p/1/", "timestamp": "2026-06-01T00:00:00Z"}
    out = fetcher.inject_source_line(md, meta)
    assert out.startswith("> Source: @x")


def test_inject_source_line_empty_meta_noop():
    md = "# Title\n\nBody."
    assert fetcher.inject_source_line(md, {}) == md
```

- [ ] **Step 6: Run the tests to verify they fail**

Run:
```bash
cd "/root/Repo Apps/IG Parser" && .venv/bin/python -m pytest tests/test_fetcher.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'fetcher'` (or collection error).

- [ ] **Step 7: Implement the pure helpers in `fetcher.py`**

Create `fetcher.py`:
```python
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
```

- [ ] **Step 8: Run the tests to verify they pass**

Run:
```bash
cd "/root/Repo Apps/IG Parser" && .venv/bin/python -m pytest tests/test_fetcher.py -v
```
Expected: PASS — all 10 test cases green (the shortcode test is parametrized into 3).

- [ ] **Step 9: Commit**

```bash
cd "/root/Repo Apps/IG Parser"
git add fetcher.py tests/ pyproject.toml
git commit -m "feat: fetcher pure helpers (shortcode, item parse, source line) + fixtures"
```

---

### Task 2: `fetch_post` orchestration (Apify call + media download)

Add the I/O layer: call Apify, download media to disk, return the 4-tuple. Tested entirely with mocked httpx — no live network.

**Files:**
- Modify: `fetcher.py` (add `_download_media`, `fetch_post`)
- Modify: `tests/test_fetcher.py` (add orchestration tests)

**Interfaces:**
- Consumes: `_extract_shortcode`, `_parse_item` (Task 1).
- Produces:
  - `fetch_post(url: str, work_dir: Path) -> tuple[Path | None, list[Path], str, dict]` — `(video_path, image_paths, caption, meta)`. Raises `RuntimeError` on missing token, Apify error/timeout, or an empty (inaccessible-post) dataset.
  - `_download_media(url: str, dest: Path) -> Path`

- [ ] **Step 1: Write the failing orchestration tests**

Append to `tests/test_fetcher.py`:
```python
import httpx as _httpx


class _FakeResp:
    def __init__(self, json_data=None, content=b"", status_code=200):
        self._json = json_data
        self.content = content
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise _httpx.HTTPStatusError("err", request=None, response=self)


def _patch_apify(monkeypatch, fixture_name):
    """Make fetcher.httpx.post return the given fixture, and httpx.get write bytes."""
    monkeypatch.setenv("APIFY_TOKEN", "test-token")
    items = _load(fixture_name)

    def fake_post(url, params=None, json=None, timeout=None):
        assert "run-sync-get-dataset-items" in url
        assert params["token"] == "test-token"
        assert json["resultsLimit"] == 1
        assert json["directUrls"]
        return _FakeResp(json_data=items)

    def fake_get(url, headers=None, follow_redirects=None, timeout=None):
        return _FakeResp(content=b"BINARY")

    monkeypatch.setattr(fetcher.httpx, "post", fake_post)
    monkeypatch.setattr(fetcher.httpx, "get", fake_get)


def test_fetch_post_video(monkeypatch, tmp_path):
    _patch_apify(monkeypatch, "apify_video.json")
    video, images, caption, meta = fetcher.fetch_post(
        "https://www.instagram.com/reel/VID123abc/", tmp_path
    )
    assert video == tmp_path / "reel.mp4"
    assert video.read_bytes() == b"BINARY"
    assert images == []
    assert caption == "My reel caption with #tags"
    assert meta["author"] == "creator"


def test_fetch_post_carousel(monkeypatch, tmp_path):
    _patch_apify(monkeypatch, "apify_carousel.json")
    video, images, caption, meta = fetcher.fetch_post(
        "https://www.instagram.com/p/CAR456def/", tmp_path
    )
    assert video is None
    assert images == [tmp_path / "slide_01.jpg", tmp_path / "slide_02.jpg"]
    assert all(p.read_bytes() == b"BINARY" for p in images)


def test_fetch_post_empty_dataset_raises(monkeypatch, tmp_path):
    _patch_apify(monkeypatch, "apify_empty.json")
    with pytest.raises(RuntimeError, match="not accessible"):
        fetcher.fetch_post("https://www.instagram.com/p/GONE000/", tmp_path)


def test_fetch_post_missing_token_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="APIFY_TOKEN"):
        fetcher.fetch_post("https://www.instagram.com/p/ABC123/", tmp_path)
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:
```bash
cd "/root/Repo Apps/IG Parser" && .venv/bin/python -m pytest tests/test_fetcher.py -k fetch_post -v
```
Expected: FAIL — `AttributeError: module 'fetcher' has no attribute 'fetch_post'`.

- [ ] **Step 3: Implement `_download_media` and `fetch_post`**

Append to `fetcher.py`:
```python
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
        "addParentData": False,
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
```

- [ ] **Step 4: Run the full test file to verify all pass**

Run:
```bash
cd "/root/Repo Apps/IG Parser" && .venv/bin/python -m pytest tests/test_fetcher.py -v
```
Expected: PASS — 14 test cases green.

- [ ] **Step 5: Commit**

```bash
cd "/root/Repo Apps/IG Parser"
git add fetcher.py tests/test_fetcher.py
git commit -m "feat: fetch_post Apify orchestration with media download (mocked tests)"
```

---

### Task 3: Wire the CLI (`main.py`)

Swap `download_reel` for `fetch_post`, unpack the 4-tuple, and apply the source-attribution line to the formatted markdown.

**Files:**
- Modify: `main.py` (imports at lines 8-12; download call at line 43; save block around lines 106-115)
- Modify: `tests/test_cli.py` (new — CliRunner smoke test with mocked fetch + LLM)

**Interfaces:**
- Consumes: `fetch_post`, `inject_source_line` (Tasks 1-2); `extract_content` (unchanged, returns `(markdown, slug)`).

- [ ] **Step 1: Write the failing CLI test**

Create `tests/test_cli.py`:
```python
from pathlib import Path

from typer.testing import CliRunner

import main

runner = CliRunner()


def test_cli_writes_markdown_with_attribution(monkeypatch, tmp_path):
    def fake_fetch(url, work_dir):
        return None, [], "the caption", {
            "author": "creator",
            "source_url": "https://www.instagram.com/reel/VID123abc/",
            "timestamp": "2026-06-20T10:00:00.000Z",
        }

    def fake_extract(transcript, caption, api_key):
        return "# My Title\n\nFormatted body.", "my-title"

    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    monkeypatch.setattr(main, "fetch_post", fake_fetch)
    monkeypatch.setattr(main, "extract_content", fake_extract)
    monkeypatch.setattr(main, "fetch_caption", lambda url: "")

    result = runner.invoke(
        main.app, ["https://www.instagram.com/reel/VID123abc/", "-o", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    out = (tmp_path / "my-title.md").read_text()
    assert out.splitlines()[0] == "# My Title"
    assert "> Source: @creator · [original post](https://www.instagram.com/reel/VID123abc/) · 2026-06-20" in out
    assert "Formatted body." in out
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
cd "/root/Repo Apps/IG Parser" && .venv/bin/python -m pytest tests/test_cli.py -v
```
Expected: FAIL — `main` still imports `download_reel` (ImportError once Task 5 runs) or the attribution line is missing / fetch unpack mismatch. (At this point it fails because `main` has no `fetch_post` attribute to patch and still calls the 3-tuple `download_reel`.)

- [ ] **Step 3: Update the imports in `main.py`**

Replace line 8:
```python
from downloader import download_reel
```
with:
```python
from fetcher import fetch_post, inject_source_line
```

- [ ] **Step 4: Update the download call in `main.py`**

Replace lines 42-43:
```python
        try:
            video_path, image_paths, yt_caption = download_reel(url, work_dir)
```
with:
```python
        try:
            video_path, image_paths, yt_caption, meta = fetch_post(url, work_dir)
```

- [ ] **Step 5: Apply the attribution line in the save block of `main.py`**

Replace lines 106-115:
```python
        typer.echo("Formatting content...")
        try:
            result_md, slug = extract_content(transcript, caption or "", openrouter_key)
        except Exception as e:
            typer.echo(f"Error calling LLM API: {e}", err=True)
            raise typer.Exit(1)

        output.mkdir(parents=True, exist_ok=True)
        out_file = output / f"{slug}.md"
        out_file.write_text(result_md, encoding="utf-8")
```
with:
```python
        typer.echo("Formatting content...")
        try:
            result_md, slug = extract_content(transcript, caption or "", openrouter_key)
        except Exception as e:
            typer.echo(f"Error calling LLM API: {e}", err=True)
            raise typer.Exit(1)

        result_md = inject_source_line(result_md, meta)

        output.mkdir(parents=True, exist_ok=True)
        out_file = output / f"{slug}.md"
        out_file.write_text(result_md, encoding="utf-8")
```

- [ ] **Step 6: Run the CLI test to verify it passes**

Run:
```bash
cd "/root/Repo Apps/IG Parser" && .venv/bin/python -m pytest tests/test_cli.py -v
```
Expected: PASS.

- [ ] **Step 7: Run the whole suite**

Run:
```bash
cd "/root/Repo Apps/IG Parser" && .venv/bin/python -m pytest -v
```
Expected: PASS — all tests across `test_fetcher.py` and `test_cli.py` green.

- [ ] **Step 8: Commit**

```bash
cd "/root/Repo Apps/IG Parser"
git add main.py tests/test_cli.py
git commit -m "feat: wire CLI to Apify fetch_post + source attribution"
```

---

### Task 4: Wire the Streamlit app (`app.py`)

Mirror the CLI changes in the dashboard. Streamlit executes on import, so verification is a byte-compile plus a manual run (the live run is folded into Task 7).

**Files:**
- Modify: `app.py` (imports lines 11-16; cookie sidebar lines 21, 28-44; download call line 68; format call line 145)

**Interfaces:**
- Consumes: `fetch_post`, `inject_source_line` (Tasks 1-2).

- [ ] **Step 1: Update imports in `app.py`**

Replace line 11:
```python
from downloader import download_reel
```
with:
```python
from fetcher import fetch_post, inject_source_line
```

- [ ] **Step 2: Remove the cookies sidebar (now obsolete) from `app.py`**

Delete line 21:
```python
COOKIES_PATH = Path(os.getenv("COOKIES_FILE", "cookies/instagram.txt"))
```
Then delete the entire sidebar block, lines 28-44:
```python
with st.sidebar:
    st.header("Cookies")
    if COOKIES_PATH.exists():
        mtime = COOKIES_PATH.stat().st_mtime
        import datetime
        age = datetime.datetime.now() - datetime.datetime.fromtimestamp(mtime)
        days = age.days
        color = "green" if days < 60 else "orange" if days < 90 else "red"
        st.markdown(f"Last updated: :{color}[{days}d ago]")
    else:
        st.markdown(":red[No cookies file found]")
    uploaded = st.file_uploader("Upload instagram.txt", type="txt", label_visibility="collapsed")
    if uploaded is not None:
        COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        COOKIES_PATH.write_bytes(uploaded.getvalue())
        log.info("cookies updated via UI upload (%d bytes)", len(uploaded.getvalue()))
        st.success("Cookies updated.")
```
(Leave the surrounding `st.title` / `st.caption` lines intact.)

- [ ] **Step 3: Update the download call in `app.py`**

Replace line 68:
```python
            video_path, image_paths, yt_caption = download_reel(url.strip(), WORK_DIR)
```
with:
```python
            video_path, image_paths, yt_caption, meta = fetch_post(url.strip(), WORK_DIR)
```

- [ ] **Step 4: Apply the attribution line in `app.py`**

Replace line 145:
```python
            result_md, _ = extract_content(transcript, caption or "", openrouter_key)
```
with:
```python
            result_md, _ = extract_content(transcript, caption or "", openrouter_key)
            result_md = inject_source_line(result_md, meta)
```

- [ ] **Step 5: Byte-compile to verify no syntax/import errors**

Run:
```bash
cd "/root/Repo Apps/IG Parser" && .venv/bin/python -m py_compile app.py && echo OK
```
Expected: `OK` (no traceback).

- [ ] **Step 6: Commit**

```bash
cd "/root/Repo Apps/IG Parser"
git add app.py
git commit -m "feat: wire Streamlit app to Apify fetch_post + source attribution; drop cookies sidebar"
```

---

### Task 5: Archive old fetch code + dependency / Docker / env cutover

Move the dead fetch modules to `legacy/`, strip the cookie/yt-dlp/instaloader dependencies and config, and add `APIFY_TOKEN` wiring. After this task nothing in the running app references the old code.

**Files:**
- Move: `downloader.py` → `legacy/downloader.py`
- Move: `detector.py` → `legacy/detector.py`
- Create: `legacy/README.md`
- Modify: `requirements.txt` (remove `instaloader`, `yt-dlp`)
- Modify: `pyproject.toml` (remove `yt-dlp` dep; fix stale `py-modules` list)
- Modify: `docker-compose.yml` (drop cookie env + volume; add `APIFY_TOKEN`)
- Create: `.env.example`

- [ ] **Step 1: Confirm nothing imports the modules being archived**

Run:
```bash
cd "/root/Repo Apps/IG Parser" && grep -rn "import downloader\|from downloader\|import detector\|from detector" --include=*.py . --exclude-dir=.venv --exclude-dir=legacy
```
Expected: no output (Tasks 3-4 already removed the imports). If anything prints, stop and fix the importer first.

- [ ] **Step 2: Move the dead modules into `legacy/`**

Run:
```bash
cd "/root/Repo Apps/IG Parser"
mkdir -p legacy
git mv downloader.py legacy/downloader.py
git mv detector.py legacy/detector.py
```

- [ ] **Step 3: Write `legacy/README.md`**

Create `legacy/README.md`:
```markdown
# legacy

Archived code, kept for reference only — **not imported by the running app.**

- `downloader.py` — the original Instagram fetch path: `yt-dlp` for video reels +
  `instaloader` for image carousels, authenticated via `cookies/instagram.txt`
  (sourced from the `cookie-mint` vault). Replaced 2026-06-27 by `fetcher.py`
  (Apify Instagram Scraper). The cookie path was structurally brittle on
  Heimdall's datacenter IP — see `docs/superpowers/specs/2026-06-27-ig-parser-apify-fetch-design.md`.
- `detector.py` — the original 5-type LLM classifier (recipe/movie/book/place/game),
  already superseded by the free-form formatter in `content_extractor.py`.

These files reference `yt-dlp` / `instaloader`, which are no longer installed.
Do not import them without reinstating those dependencies.
```

- [ ] **Step 4: Strip dependencies from `requirements.txt`**

Replace the entire `requirements.txt` with:
```
httpx>=0.27.0
python-dotenv>=1.0.0
streamlit>=1.35.0
typer>=0.12.0
```

- [ ] **Step 5: Fix `pyproject.toml` dependencies and module list**

Replace the `dependencies = [...]` block (lines 9-15):
```toml
dependencies = [
    "httpx>=0.27.0",
    "python-dotenv>=1.0.0",
    "streamlit>=1.35.0",
    "typer>=0.12.0",
    "yt-dlp>=2024.11.18",
]
```
with:
```toml
dependencies = [
    "httpx>=0.27.0",
    "python-dotenv>=1.0.0",
    "streamlit>=1.35.0",
    "typer>=0.12.0",
]
```
Then replace the stale `py-modules` line (line 18):
```toml
py-modules = ["main", "downloader", "transcriber", "caption", "detector", "extractor"]
```
with:
```toml
py-modules = ["main", "fetcher", "transcriber", "caption", "image_reader", "content_extractor", "logger"]
```

- [ ] **Step 6: Update `docker-compose.yml`**

Replace the full file with:
```yaml
services:
  ig-parser:
    build: .
    container_name: ig-parser
    restart: unless-stopped
    ports:
      - "127.0.0.1:8501:8501"
    environment:
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - APIFY_TOKEN=${APIFY_TOKEN}
      - LOG_DIR=/logs
    volumes:
      - ./logs:/logs
      - ./output:/output
```

- [ ] **Step 7: Create `.env.example`**

Create `.env.example`:
```
# OpenRouter API key (Whisper transcription, Gemma vision + formatting)
OPENROUTER_API_KEY=sk-or-...

# Apify API token — Instagram Scraper actor (apify/instagram-scraper).
# Dedicated token for ig-parser. Get one at https://console.apify.com/account/integrations
APIFY_TOKEN=apify_api_...
```

- [ ] **Step 8: Reinstall deps and run the full suite (confirm nothing broke)**

Run:
```bash
cd "/root/Repo Apps/IG Parser"
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -m pytest -v
```
Expected: PASS — all tests still green; no import errors from the removed deps.

- [ ] **Step 9: Commit**

```bash
cd "/root/Repo Apps/IG Parser"
git add -A
git commit -m "refactor: archive cookie/yt-dlp fetch to legacy/; cut over to Apify deps + env"
```

---

### Task 6: Update docs (`CLAUDE.md` + `README.md`)

Make the docs describe the Apify backend and remove the cookie-centric instructions.

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

- [ ] **Step 1: Update `CLAUDE.md` pipeline + fetch description**

In `CLAUDE.md`, replace the pipeline step 1 line (under "## What it does"):
```
1. `downloader.py` — returns `(video_path, image_paths, caption)`. Video reels use `yt-dlp`; image carousels use `instaloader`. Both use `cookies/instagram.txt` for auth.
```
with:
```
1. `fetcher.py` — returns `(video_path, image_paths, caption, meta)`. Calls the Apify Instagram Scraper (`apify/instagram-scraper`, `run-sync-get-dataset-items`) with the post URL, classifies the result (video / carousel / single image), and downloads the public CDN media to local files. No cookies. `meta` carries author / source_url / timestamp, injected as a `> Source: …` line under the H1 by `inject_source_line`.
```

- [ ] **Step 2: Replace the entire "## Cookies" section in `CLAUDE.md`**

Delete the whole `## Cookies` section (from the `## Cookies` heading through to just before `## Logging`) and replace it with:
```
## Retrieval (Apify)

Instagram retrieval is fully outsourced to the **Apify Instagram Scraper**
(`apify/instagram-scraper`). `fetcher.py` POSTs the post URL to the synchronous
`run-sync-get-dataset-items` endpoint (`resultsType: posts`, `resultsLimit: 1`),
then downloads the returned public CDN media URLs locally for transcription / OCR.

Requires `APIFY_TOKEN` in `.env` (dedicated ig-parser token). There are **no
cookies** anywhere in the app any more — the old yt-dlp/instaloader/cookie path is
archived under `legacy/` (see `legacy/README.md`). This sidesteps the datacenter-IP
blocking and account-lock problems entirely: Apify owns the anti-bot layer; we own
the media understanding.

Private / deleted / age-restricted posts return an empty Apify dataset and fail
with a clear "forward a screenshot instead" message — that is the deliberate
boundary, not a bug.

Full design: `docs/superpowers/specs/2026-06-27-ig-parser-apify-fetch-design.md`.
```

- [ ] **Step 3: Update the `Required in .env` block in `CLAUDE.md`**

Replace:
```
Required in `.env`:
```
OPENROUTER_API_KEY=sk-or-...
```

Optional — enables credential-based session login (see Cookies section):
```
IG_USERNAME=your_instagram_username
IG_PASSWORD=your_instagram_password
```
```
with:
```
Required in `.env`:
```
OPENROUTER_API_KEY=sk-or-...
APIFY_TOKEN=apify_api_...
```
```

- [ ] **Step 4: Update the file map and Docker section in `CLAUDE.md`**

In the "## File map" block, replace the `downloader.py` and `detector.py` lines:
```
downloader.py        yt-dlp (video) / instaloader (image carousels); session-based auth with cookies.txt fallback
```
```
detector.py          Unused — kept for reference. Was the 5-type LLM classifier (recipe/movie/book/place/game).
```
with:
```
fetcher.py           Apify Instagram Scraper fetch → downloads media → (video_path, image_paths, caption, meta); inject_source_line() adds the source blockquote
```
(and remove the `detector.py` line entirely — it now lives in `legacy/`).

Then, in the "## Docker deployment (Heimdall)" section, replace:
```
`./cookies` mounted as writable volume at `/cookies`.
```
with:
```
No cookie volume — retrieval is via Apify (`APIFY_TOKEN` env). Cookies are gone.
```
And in "## Hermes ig-save integration", append this note to the end of that paragraph:
```
NOTE (2026-06-27): retrieval is now Apify-based; the skill's cookie-install step (`ig_cookies_update.sh`) is dead and can be removed in a later Hermes-side cleanup.
```

- [ ] **Step 5: Update the "## Key constraints" section in `CLAUDE.md`**

Remove the now-obsolete cookie/credential/account-lock bullets (the ones about "Cookies expire periodically", "Credential login is blocked on VPS", and the "Account-lock gotcha (2026-06-22)" bullet) and add this single bullet in their place:
```
- Retrieval is Apify-only (`apify/instagram-scraper`). Private/deleted/age-gated posts return an empty dataset → clear "forward a screenshot" failure. No cookie fallback. A fallback provider (HikerAPI/SociaVault) can be added behind `fetch_post()` later if Apify proves unreliable.
```

- [ ] **Step 6: Update `README.md`**

Open `README.md` and update any setup / cookies / dependency references to match: retrieval is via Apify with `APIFY_TOKEN` (no cookies, no yt-dlp/instaloader). Replace any "export cookies" / "yt-dlp" / "instaloader" instructions with: set `OPENROUTER_API_KEY` and `APIFY_TOKEN` in `.env` (see `.env.example`). Keep the run commands (`streamlit run app.py`, `igrecipe <url>`) intact.

- [ ] **Step 7: Verify docs reference no removed artifacts**

Run:
```bash
cd "/root/Repo Apps/IG Parser" && grep -rn "cookies/instagram.txt\|IG_USERNAME\|IG_PASSWORD\|instaloader" CLAUDE.md README.md
```
Expected: no output (any remaining hit should be intentional historical context only; otherwise fix it).

- [ ] **Step 8: Commit**

```bash
cd "/root/Repo Apps/IG Parser"
git add CLAUDE.md README.md
git commit -m "docs: describe Apify backend; drop cookie instructions"
```

---

### Task 7 (HUMAN-GATED): Live smoke test + token provisioning

Cannot be run by a subagent — needs the real `APIFY_TOKEN` and live network. Shubham runs this; the orchestrator verifies the reported output.

**Files:** none (runtime verification only).

- [ ] **Step 1: Add the real Apify token to `.env`**

Shubham adds the dedicated ig-parser token:
```bash
cd "/root/Repo Apps/IG Parser"
# append APIFY_TOKEN=apify_api_... to the gitignored .env (do NOT commit it)
```
Verify `.env` is git-ignored:
```bash
git check-ignore .env && echo "ignored (good)"
```

- [ ] **Step 2: Rebuild and start the container**

Run:
```bash
cd "/root/Repo Apps/IG Parser" && docker compose up -d --build && docker logs --tail 20 ig-parser
```
Expected: container healthy, Streamlit serving on `127.0.0.1:8501`.

- [ ] **Step 3: Live CLI run on a public reel (with audio)**

Run:
```bash
docker exec ig-parser python main.py "<PUBLIC_REEL_URL>" -o /output
```
Expected: markdown printed and saved to `/output/<slug>.md`; the body starts with an H1 followed by `> Source: @<author> · [original post](...) · <date>`; a Whisper transcript was obtained (visible in the echoed progress / `docker logs ig-parser`).

- [ ] **Step 4: Live CLI run on a public image carousel**

Run:
```bash
docker exec ig-parser python main.py "<PUBLIC_CAROUSEL_URL>" -o /output
```
Expected: slides downloaded, Gemma vision OCR fires, markdown saved with the attribution line.

- [ ] **Step 5: Confirm the private-post boundary**

Run (any private/deleted post URL):
```bash
docker exec ig-parser python main.py "<PRIVATE_OR_DELETED_URL>" -o /output
```
Expected: clean failure with `post not accessible (private/deleted/age-restricted) — forward a screenshot instead`.

- [ ] **Step 6: Orchestrator review + finalize**

Once Shubham confirms the runs, the orchestrator:
- reviews the saved markdown samples,
- merges `apify-fetch-backend` → `master` (or opens a PR if preferred),
- updates the `cookie-mint-project` and `ig-parser-project` memory files to record the Apify cutover.

---

## Notes for the orchestrator

- Branch: work proceeds on `apify-fetch-backend` (already created). Tasks 1-6 are subagent-implementable and fully offline (mocked). Task 7 is human-gated.
- The `.venv` created in Task 1 persists across subagent tasks (same working tree).
- Do not commit the real `.env` / `APIFY_TOKEN` at any point.
- Downstream modules are intentionally untouched; reject any task diff that modifies `transcriber.py`, `image_reader.py`, `content_extractor.py`, `caption.py`, or `logger.py`.
