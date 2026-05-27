# ig parser

Downloads public Instagram Reels and static posts and extracts clean, structured markdown summaries.

Supports four content types — **recipes, movies/shows, books, and places to visit** — auto-detected via LLM.

It downloads the post, strips the audio (if video), transcribes it with Whisper via OpenRouter, fetches the caption, detects the content type, then uses an LLM to extract a structured markdown summary.

---

## Requirements

- Python 3.11+
- ffmpeg (must be on your PATH)
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

Opens a browser at `http://localhost:8501`. Paste a Reel or post URL, click **Extract**, and the result is rendered with a tab to copy the raw markdown. Nothing is saved to disk.

### CLI

```bash
igrecipe https://www.instagram.com/reel/XXXXXXX/
```

The summary prints to the terminal and is saved to `output/<title>.md`.

### CLI flags

```bash
# Force a content type instead of auto-detecting
igrecipe <url> --type recipe
igrecipe <url> --type movie
igrecipe <url> --type book
igrecipe <url> --type place

# Save to a custom output directory
igrecipe <url> --output ~/notes

# Language hint for Whisper (helps with non-English audio)
igrecipe <url> --lang hi   # Hindi
igrecipe <url> --lang ta   # Tamil
igrecipe <url> --lang gu   # Gujarati
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

---

## How it works

1. **Download** — `yt-dlp` fetches the reel or post (video or image) to a temp directory, using cookies for auth.
2. **Caption** — Instagram's oEmbed API is queried for the post caption.
3. **Audio extraction** — `ffmpeg` strips audio to a mono 16 kHz MP3. Skipped silently for static image posts.
4. **Transcription** — The audio is base64-encoded and sent to OpenRouter's Whisper Large V3 endpoint.
5. **Detection** — Transcript + caption are classified as `recipe`, `movie`, `book`, or `place` by an LLM.
6. **Extraction** — A type-specific prompt extracts a structured markdown summary.
7. **Cleanup** — All temp files are deleted.

---

## Project structure

```
igparser/
├── app.py            # Streamlit dashboard
├── main.py           # CLI entrypoint (igrecipe command)
├── downloader.py     # yt-dlp wrapper
├── transcriber.py    # ffmpeg audio strip + OpenRouter Whisper call
├── caption.py        # Instagram oEmbed caption fetch
├── detector.py       # LLM content-type classifier
├── extractor.py      # Type-specific LLM extraction prompts
├── Dockerfile
├── docker-compose.yml
├── cookies/          # Place instagram.txt here (git-ignored)
└── requirements.txt
```

---

## Limitations

- **Public posts only.** Private accounts, age-gated, and geo-restricted content will fail at download.
- Static image posts rely on caption only — no audio to transcribe.
- Whisper accuracy depends on audio clarity and background noise.
- Instagram cookies expire periodically and will need refreshing.
