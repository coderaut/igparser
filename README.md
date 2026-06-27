# ig parser

Downloads public Instagram Reels, static posts, and image carousels and formats them as clean, structured markdown.

All text is extracted first (caption, audio transcript, or image text), then a single LLM pass decides the best structure and formats the content — preserving everything without forcing it into predefined templates.

---

## Requirements

- Python 3.11+
- ffmpeg (must be on your PATH — only needed for video reels)
- An [OpenRouter](https://openrouter.ai) API key
- An [Apify](https://apify.com) API token (`APIFY_TOKEN`) for Instagram retrieval

### Installing ffmpeg

| Platform | Command |
|----------|---------|
| macOS (Homebrew) | `brew install ffmpeg` |
| Ubuntu/Debian | `sudo apt install ffmpeg` |
| Windows (Chocolatey) | `choco install ffmpeg` |
| Windows (Scoop) | `scoop install ffmpeg` |

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/coderaut/igparser
cd igparser

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
.venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -e .

# 4. Configure your API keys
cp .env.example .env
# Edit .env and add your keys:
#   OPENROUTER_API_KEY=sk-or-...
#   APIFY_TOKEN=apify_api_...
```

---

## Retrieval

Instagram media is retrieved via the **Apify Instagram Scraper** (`apify/instagram-scraper`). No cookies, no browser sessions, no yt-dlp/instaloader — just set `APIFY_TOKEN` in `.env` (see `.env.example`) and the scraper handles auth and anti-bot layers.

Private, deleted, and age-restricted posts return an empty dataset and fail with a clear error message — this is deliberate.

---

## Usage

### Dashboard (recommended)

```bash
streamlit run app.py
```

Opens a browser at `http://localhost:8501`. Paste a Reel or post URL, click **Extract**, and the result is rendered with a tab to copy the raw markdown directly to clipboard. Nothing is saved to disk.

### CLI

```bash
igrecipe https://www.instagram.com/reel/XXXXXXX/
```

The summary prints to the terminal and is saved to `output/<title>.md`.

### CLI flags

```bash
# Save to a custom output directory
igrecipe <url> --output ~/notes

# Hint the transcription language (for non-English audio)
igrecipe <url> --lang hi
igrecipe <url> --lang ta
```

---

## Docker (Heimdall / self-hosted)

```bash
# 1. Add your API keys
cp .env.example .env
# Edit .env: set OPENROUTER_API_KEY and APIFY_TOKEN

# 2. Start
docker compose up -d
```

Dashboard available at `http://localhost:8501` (bind via SSH tunnel: `ssh -L 8501:localhost:8501 user@host`).

The compose file also mounts `./output` at `/output` so CLI runs inside the container (`docker exec ig-parser igrecipe <url> -o /output`) write results back to the host — used by the Hermes `ig-save` skill on Heimdall.

Logs are written to `./logs/igrecipe.log` (rotating, 5 MB, 3 backups).

---

## How it works

**Video reels:**
1. **Retrieval** — `fetcher.py` calls the Apify Instagram Scraper with the post URL and downloads the public CDN video to a temp directory. No cookies.
2. **Caption** — Post caption is returned by Apify (oEmbed API as fallback).
3. **Audio extraction** — `ffmpeg` strips audio to a mono 16 kHz MP3.
4. **Transcription** — The audio is base64-encoded and sent to OpenRouter's Whisper Large V3 endpoint.
5. **Formatting** — Caption + transcript are sent to an LLM, which chooses the appropriate structure and formats everything as markdown.
6. **Cleanup** — All temp files are deleted.

**Image carousels:**
1. **Retrieval** — `fetcher.py` calls the Apify Instagram Scraper and downloads each slide image from the public CDN. No cookies.
2. **Caption** — Post caption is returned by Apify (oEmbed API as fallback).
3. **Image reading** — All slides are base64-encoded and sent to Gemma 4 vision via OpenRouter, which extracts all visible text in one pass.
4–6. Same formatting and cleanup as above.

---

## Project structure

```
igparser/
├── app.py               # Streamlit dashboard
├── main.py              # CLI entrypoint (igrecipe command)
├── fetcher.py           # Apify Instagram Scraper fetch → downloads media → (video_path, image_paths, caption, meta)
├── transcriber.py       # ffmpeg audio strip + OpenRouter Whisper (video reels)
├── image_reader.py      # Gemma 4 vision — extracts text from carousel slides
├── caption.py           # Instagram oEmbed caption fetch (fallback)
├── content_extractor.py # Free-form LLM formatting — preserves all content, chooses structure
├── logger.py            # Rotating file logger → logs/igrecipe.log
├── legacy/              # Archived: downloader.py, detector.py (old yt-dlp/instaloader path)
├── Dockerfile
├── docker-compose.yml
├── output/              # CLI markdown output, host-readable mount (git-ignored)
└── logs/                # Log output (git-ignored)
```

---

## Models used (via OpenRouter)

| Task | Model |
|------|-------|
| Audio transcription | `openai/whisper-large-v3` |
| Carousel image reading | `google/gemma-4-31b-it` |
| Content formatting | `google/gemma-4-31b-it` |

---

## Limitations

- **Public posts only.** Private, deleted, and age-gated content returns an empty Apify dataset — the app fails with a clear "forward a screenshot instead" message.
- Whisper accuracy depends on audio clarity and background noise.
- Carousel image reading accuracy depends on text legibility in the slides.
- Apify rate limits and occasional scraper outages can cause transient failures. A fallback provider can be wired behind `fetch_post()` if needed.
