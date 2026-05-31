# ig parser

Downloads public Instagram Reels, static posts, and image carousels and formats them as clean, structured markdown.

All text is extracted first (caption, audio transcript, or image text), then a single LLM pass decides the best structure and formats the content — preserving everything without forcing it into predefined templates.

---

## Requirements

- Python 3.11+
- ffmpeg (must be on your PATH — only needed for video reels)
- An [OpenRouter](https://openrouter.ai) API key
- Instagram cookies file (for authenticated downloads — see [Cookies](#cookies))

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

# 4. Configure your API key
cp .env.example .env
# Edit .env and add your key:
#   OPENROUTER_API_KEY=sk-or-...
```

---

## Cookies

Instagram requires authentication for downloads. Export your cookies from a logged-in browser session and save them as `cookies/instagram.txt`.

1. Install the **Get cookies.txt LOCALLY** extension (Chrome/Firefox)
2. Log into Instagram in your browser
3. Click the extension and export cookies for `instagram.com`
4. Save the file to `cookies/instagram.txt`

yt-dlp will pick this up automatically.

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
# 1. Add your API key
echo "OPENROUTER_API_KEY=sk-or-..." > .env

# 2. Add your Instagram cookies
cp /path/to/instagram.txt cookies/instagram.txt

# 3. Start
docker compose up -d
```

Dashboard available at `http://localhost:8501` (bind via SSH tunnel: `ssh -L 8501:localhost:8501 user@host`).

Logs are written to `./logs/igrecipe.log` (rotating, 5 MB, 3 backups).

---

## How it works

**Video reels:**
1. **Download** — `yt-dlp` fetches the reel to a temp directory using cookies for auth.
2. **Caption** — Post caption is extracted from yt-dlp metadata (oEmbed API as fallback).
3. **Audio extraction** — `ffmpeg` strips audio to a mono 16 kHz MP3.
4. **Transcription** — The audio is base64-encoded and sent to OpenRouter's Whisper Large V3 endpoint.
5. **Formatting** — Caption + transcript are sent to an LLM, which chooses the appropriate structure and formats everything as markdown.
6. **Cleanup** — All temp files are deleted.

**Image carousels:**
1. **Download** — `instaloader` fetches each slide image to a temp directory.
2. **Caption** — Post caption is extracted (oEmbed API as fallback).
3. **Image reading** — All slides are base64-encoded and sent to Gemma 4 vision via OpenRouter, which extracts all visible text in one pass.
4–6. Same formatting and cleanup as above.

---

## Project structure

```
igparser/
├── app.py               # Streamlit dashboard
├── main.py              # CLI entrypoint (igrecipe command)
├── downloader.py        # yt-dlp (video) / instaloader (carousels) — returns (video_path, image_paths, caption)
├── transcriber.py       # ffmpeg audio strip + OpenRouter Whisper (video reels)
├── image_reader.py      # Gemma 4 vision — extracts text from carousel slides
├── caption.py           # Instagram oEmbed caption fetch (fallback)
├── content_extractor.py # Free-form LLM formatting — preserves all content, chooses structure
├── logger.py            # Rotating file logger → logs/igrecipe.log
├── Dockerfile
├── docker-compose.yml
├── cookies/             # Place instagram.txt here (git-ignored)
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

- **Public posts only.** Private accounts, age-gated, and geo-restricted content will fail at download.
- Whisper accuracy depends on audio clarity and background noise.
- Carousel image reading accuracy depends on text legibility in the slides.
- Instagram cookies expire periodically and will need refreshing.
