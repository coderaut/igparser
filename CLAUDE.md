# ig parser

Downloads public Instagram Reels and static posts and formats them as clean markdown. All text is extracted first (caption + transcript or image text), then a single LLM pass chooses the appropriate structure and formats the content — no predefined type templates, nothing discarded.

## What it does

Pipeline (in order):
1. `fetcher.py` — returns `(video_path, image_paths, caption, meta)`. Calls the Apify Instagram Scraper (`apify/instagram-scraper`, `run-sync-get-dataset-items`) with the post URL, classifies the result (video / carousel / single image), and downloads the public CDN media to local files. No cookies. `meta` carries author / source_url / timestamp, injected as a `> Source: …` line under the H1 by `inject_source_line`.
2. `caption.py` — Instagram oEmbed API fallback for caption; only used if the fetcher returned no description.
3a. `transcriber.py` — (video path) `ffmpeg` strips audio to mono 16 kHz MP3, then sends it base64-encoded to OpenRouter Whisper Large V3. Skipped for image carousels or videos with no audio track.
3b. `image_reader.py` — (carousel path) Sends all slide images base64-encoded to Gemma 4 vision via OpenRouter to extract all visible text. Used instead of transcription for image-only carousels.
3c. `transcriber.py` — (video fallback) If transcript is empty or audio extraction failed, ffmpeg extracts scene-change frames (threshold 0.4, max 20) and passes them to `image_reader` to extract visible text. Catches slideshow-style reels where all content is visual.
4. `content_extractor.py` — Single LLM call with caption + transcript/image-text. The LLM decides the best markdown structure and formats everything, preserving all content. Returns `(markdown, slug)`.
5. Cleanup — temp files deleted; CLI saves to `output/<slug>.md`, dashboard is in-memory only.

## Entry points

| Mode | Command |
|------|---------|
| Streamlit dashboard | `streamlit run app.py` → `http://localhost:8501` |
| CLI | `igrecipe <url> [--lang <code>] [--output dir]` |

CLI is registered via `pyproject.toml` as `igrecipe = "main:app"`.

## Environment

Required in `.env`:
```
OPENROUTER_API_KEY=sk-or-...
APIFY_TOKEN=apify_api_...
```

Also requires `ffmpeg` on PATH (only needed for video reels).

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

## Logging

Logs write to `./logs/igrecipe.log` (rotating, 5 MB max, 3 backups). Docker mounts `./logs` as `/logs` via `LOG_DIR=/logs` env var. INFO+ goes to stdout (visible in `docker logs ig-parser`); DEBUG goes to file only.

`logger.py` sets up the logger; all modules import `from logger import log`.

## Docker deployment (Heimdall)

Port bound `127.0.0.1:8501` — loopback only, NOT exposed publicly. `0.0.0.0` would bind all interfaces (including the public IP), not just Tailscale — a real exposure caught and fixed 2026-06-08. Reached externally via `ig.heim-dall.com` through Caddy on the Tailscale interface; see [[feedback-tailscale-port-binding]].
No cookie volume — retrieval is via Apify (`APIFY_TOKEN` env). Cookies are gone.
`./logs` mounted at `/logs`.
`./output` mounted at `/output` (added 2026-06-22) — lets the host read CLI results written inside the container. Used by the Hermes `ig-save` skill (see below). git-ignored.

```bash
docker compose up -d --build
```

## Hermes ig-save integration

The Hermes agent has an `ig-save` skill (`/root/.hermes/skills/social-media/ig-save/`) that turns a shared Instagram link into an Obsidian capture note. It runs the CLI **inside this container** (`docker exec ig-parser python main.py "<url>" -o /output`) because the Heimdall host lacks the deps (no `faster_whisper`). The markdown lands in `/output` (= host `./output`), then Hermes prepends capture frontmatter and moves it to `/root/Obsidian/Valhalla/Captures/`. NOTE (2026-06-27): retrieval is now Apify-based, so the skill's old cookie-install step (`ig_cookies_update.sh`) is dead and can be removed in a later Hermes-side cleanup.

## File map

```
app.py               Streamlit UI — runs the full pipeline, no file output
main.py              CLI entrypoint (Typer) — saves output/<slug>.md; flags: --lang, --output
fetcher.py           Apify Instagram Scraper fetch → downloads media → (video_path, image_paths, caption, meta); inject_source_line() adds the source blockquote
transcriber.py       ffmpeg audio strip + OpenRouter Whisper; extract_frames() for scene-change fallback
image_reader.py      base64-encodes images → Gemma 4 vision → extracted text (carousels + frame fallback)
caption.py           Instagram oEmbed fetch → fallback caption if fetcher returned nothing
content_extractor.py Single free-form LLM prompt → chooses structure, preserves all content → returns (markdown, slug)
logger.py            Rotating file logger; LOG_DIR env var sets output dir (default /logs)
pyproject.toml       Package config; CLI script registered here
legacy/              Archived: downloader.py, detector.py (old yt-dlp/instaloader path)
logs/                Log output — git-ignored, Docker-mounted
```

## Models used (via OpenRouter)

- Transcription: `openai/whisper-large-v3` (in `transcriber.py`)
- Image reading: `google/gemma-4-31b-it` (in `image_reader.py`)
- Content formatting: `google/gemma-4-31b-it` (in `content_extractor.py`)

To swap models, change the constants at the top of each file.

## Key constraints

- Retrieval is Apify-only (`apify/instagram-scraper`). Private/deleted/age-gated posts return an empty dataset → clear "forward a screenshot" failure. No cookie fallback. A fallback provider (HikerAPI/SociaVault) can be added behind `fetch_post()` later if Apify proves unreliable.
- If both transcript/image-text and caption are empty, the pipeline aborts
- Frame extraction fallback (scene detection) works well for hard-cut slideshow reels but misses visually similar slides (same design template across slides = low scene change scores below threshold)
- Whisper returns 400 if the extracted audio file is too small (empty audio track) — `transcriber.py` checks for this and raises a clean error before sending
- Temp work dir: `/tmp/igrecipe` (CLI) or `tempfile.gettempdir()/igrecipe` (dashboard)

## Dev setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env   # add OPENROUTER_API_KEY and APIFY_TOKEN
```
