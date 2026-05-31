# ig parser

Downloads public Instagram Reels and static posts and formats them as clean markdown. All text is extracted first (caption + transcript or image text), then a single LLM pass chooses the appropriate structure and formats the content — no predefined type templates, nothing discarded.

## What it does

Pipeline (in order):
1. `downloader.py` — returns `(video_path, image_paths, caption)`. Video reels use `yt-dlp`; image carousels use `instaloader`. Both use `cookies/instagram.txt` for auth.
2. `caption.py` — Instagram oEmbed API fallback for caption; only used if the downloader returned no description.
3a. `transcriber.py` — (video path) `ffmpeg` strips audio to mono 16 kHz MP3, then sends it base64-encoded to OpenRouter Whisper Large V3. Skipped for image carousels or videos with no audio track.
3b. `image_reader.py` — (carousel path) Sends all slide images base64-encoded to Gemma 4 vision via OpenRouter to extract all visible text. Used instead of transcription for image-only carousels.
4. `content_extractor.py` — Single LLM call with caption + transcript/image-text. The LLM decides the best markdown structure and formats everything, preserving all content. Returns `(markdown, slug)`.
5. Cleanup — temp files deleted; CLI saves to `output/<slug>.md`, dashboard is in-memory only.

## Entry points

| Mode | Command |
|------|---------|
| Streamlit dashboard | `streamlit run app.py` → `http://localhost:8501` |
| CLI | `igrecipe <url> [--lang <code>] [--output dir]` |

CLI is registered via `pyproject.toml` as `igrecipe = "main:app"`.

## Environment

Requires in `.env`:
```
OPENROUTER_API_KEY=sk-or-...
```

Also requires `ffmpeg` on PATH (only needed for video reels).

## Cookies

Instagram requires authenticated downloads. Place a Netscape-format cookies file at `cookies/instagram.txt` (exported from a logged-in browser via "Get cookies.txt LOCALLY" extension).

`COOKIES_FILE` env var overrides the default path (Docker sets it to `/cookies/instagram.txt`).

yt-dlp rewrites the cookies file after each request — the volume must be writable (not `:ro`).

## Logging

Logs write to `./logs/igrecipe.log` (rotating, 5 MB max, 3 backups). Docker mounts `./logs` as `/logs` via `LOG_DIR=/logs` env var. INFO+ goes to stdout (visible in `docker logs ig-parser`); DEBUG goes to file only.

`logger.py` sets up the logger; all modules import `from logger import log`.

## Docker deployment (Heimdall)

Port `0.0.0.0:8501` — accessible directly over Tailscale.
`./cookies` mounted as writable volume at `/cookies`.
`./logs` mounted at `/logs`.

```bash
docker compose up -d --build
```

SSH tunnel to access: `ssh -L 8501:localhost:8501 root@<ip>`

## File map

```
app.py               Streamlit UI — runs the full pipeline, no file output
main.py              CLI entrypoint (Typer) — saves output/<slug>.md; flags: --lang, --output
downloader.py        yt-dlp (video) / instaloader (image carousels); reads COOKIES_FILE env var; returns (video_path, image_paths, caption)
transcriber.py       ffmpeg audio strip + OpenRouter Whisper call (video reels only)
image_reader.py      base64-encodes carousel slides → Gemma 4 vision → extracted text (carousels only)
caption.py           Instagram oEmbed fetch → fallback caption if yt-dlp returned nothing
content_extractor.py Single free-form LLM prompt → chooses structure, preserves all content → returns (markdown, slug)
logger.py            Rotating file logger; LOG_DIR env var sets output dir (default /logs)
detector.py          Unused — kept for reference. Was the 5-type LLM classifier (recipe/movie/book/place/game).
pyproject.toml       Package config; CLI script registered here
cookies/             Place instagram.txt here — git-ignored, Docker-mounted
logs/                Log output — git-ignored, Docker-mounted
```

## Models used (via OpenRouter)

- Transcription: `openai/whisper-large-v3` (in `transcriber.py`)
- Image reading: `google/gemma-4-31b-it` (in `image_reader.py`)
- Content formatting: `google/gemma-4-31b-it` (in `content_extractor.py`)

To swap models, change the constants at the top of each file.

## Key constraints

- Public posts only — private/age-gated/geo-restricted will fail at download
- yt-dlp is used for video reels only; instaloader handles image carousels — do NOT try to use yt-dlp for image posts
- yt-dlp sometimes returns `ext=mp4` with a title but writes no file to disk (happens with some carousel posts where a stub video entry exists in the metadata). When `work_dir` is empty after a claimed successful download, the code falls through to instaloader instead of raising. This is handled in `downloader.py`.
- If both transcript/image-text and caption are empty, the pipeline aborts
- Cookies expire periodically — re-export from browser and replace the file, then `docker restart ig-parser`
- Temp work dir: `/tmp/igrecipe` (CLI) or `tempfile.gettempdir()/igrecipe` (dashboard)

## Dev setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env   # add your OPENROUTER_API_KEY
```
