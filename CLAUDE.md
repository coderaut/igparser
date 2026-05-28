# ig parser

Downloads public Instagram Reels and static posts and extracts structured markdown summaries.
Supports four content types: recipes, movie/show recommendations, book recommendations, and places to visit — auto-detected via LLM.

## What it does

Pipeline (in order):
1. `downloader.py` — returns `(video_path, image_paths, caption)`. Video reels use `yt-dlp`; image carousels use `instaloader` (yt-dlp raises "No video formats found" at the extractor level for image posts and cannot be worked around). Both use `cookies/instagram.txt` for auth.
2. `caption.py` — Instagram oEmbed API fallback for caption; only used if the downloader returned no description
3a. `transcriber.py` — (video path) `ffmpeg` strips audio to mono 16 kHz MP3, then sends it base64-encoded to OpenRouter Whisper Large V3. Skipped for image carousels or videos with no audio track.
3b. `image_reader.py` — (carousel path) Sends all slide images base64-encoded to Gemma 4 vision via OpenRouter to extract visible text. Used instead of transcription for image-only carousels.
4. `detector.py` — LLM classifies the content as `recipe`, `movie`, `book`, or `place` using both caption and transcript
5. `content_extractor.py` — Type-specific prompt sent to LLM via OpenRouter using both caption and transcript; returns structured markdown
6. Cleanup — temp files deleted; CLI saves to `output/<slug>.md`, dashboard is in-memory only

## Entry points

| Mode | Command |
|------|---------|
| Streamlit dashboard | `streamlit run app.py` → `http://localhost:8501` |
| CLI | `igrecipe <url> [--type auto|recipe|movie|book|place] [--output dir]` |

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

## Docker deployment (Heimdall)

Port `127.0.0.1:8501` — SSH tunnel only, not public.
`./cookies` dir mounted as a writable volume at `/cookies`.

```bash
docker compose up -d --build
```

SSH tunnel to access: `ssh -L 8501:localhost:8501 root@<ip>`

## File map

```
app.py            Streamlit UI — runs the full pipeline, no file output
main.py           CLI entrypoint (Typer) — saves output/<slug>.md
downloader.py     yt-dlp (video) / instaloader (image carousels); reads COOKIES_FILE env var; returns (video_path, image_paths, caption)
transcriber.py    ffmpeg audio strip + OpenRouter Whisper call (video reels only)
image_reader.py   base64-encodes carousel slides → Gemma 4 vision → extracted text (carousels only)
caption.py        Instagram oEmbed fetch → fallback caption if yt-dlp returned nothing
detector.py       LLM classifier → returns one of: recipe, movie, book, place
content_extractor.py  Type-specific LLM prompts → returns (markdown, slug)
pyproject.toml    Package config; CLI script registered here
cookies/          Place instagram.txt here — git-ignored, Docker-mounted
```

## Models used (via OpenRouter)

- Transcription: `openai/whisper-large-v3` (in `transcriber.py`)
- Image reading: `google/gemma-4-31b-it` (in `image_reader.py`)
- Detection + extraction: `google/gemma-4-31b-it` (in `detector.py` and `content_extractor.py`)

To swap models, change the constants at the top of each file.

## Content type output formats

| Type | Key sections |
|------|-------------|
| recipe | Ingredients, Instructions, Notes |
| movie | Director/Genre/Where to watch, Why Watch It, What to Expect, Notes |
| book | Author/Genre, What It's About, Why Read It, Notes |
| place | Location/Type, Why Visit, Tips, Notes |

To add a new content type: add an entry to `_PROMPTS` in `content_extractor.py`, add it to `CONTENT_TYPES` in `detector.py`, and update the classifier system prompt.

## Key constraints

- Public posts only — private/age-gated/geo-restricted will fail at download
- yt-dlp is used for video reels only; instaloader handles image carousels — do NOT try to use yt-dlp for image posts, it raises "No video formats found" unconditionally
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
