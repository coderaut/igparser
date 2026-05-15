# igrecipe

A local tool that downloads an Instagram cooking reel and extracts a clean, formatted recipe.

It downloads the video, strips the audio, transcribes it with Whisper via OpenRouter, fetches the post caption, then uses an LLM to synthesise everything into a markdown recipe.

---

## Requirements

- Python 3.11+
- ffmpeg (must be on your PATH)
- An [OpenRouter](https://openrouter.ai) API key

### Installing ffmpeg

| Platform | Command |
|----------|---------|
| macOS (Homebrew) | `brew install ffmpeg` |
| Ubuntu/Debian | `sudo apt install ffmpeg` |
| Windows (Chocolatey) | `choco install ffmpeg` |
| Windows (Scoop) | `scoop install ffmpeg` |

Verify with: `ffmpeg -version`

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/coderaut/igrecipe
cd igrecipe

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

## Usage

Every time you open a new terminal, activate the virtual environment first:

```bash
source .venv/bin/activate   # macOS/Linux
.venv\Scripts\activate      # Windows
```

Or use the start scripts to do it in one step:

```bash
./start.sh      # macOS/Linux
start.bat       # Windows (double-click or run from terminal)
```

### Dashboard (recommended)

```bash
streamlit run app.py
```

Opens a browser at `http://localhost:8501`. Paste a reel URL, click **Generate Recipe**, and the recipe is rendered with a tab to copy the raw markdown. Nothing is saved to disk — copy it directly into your notes.

### CLI

```bash
igrecipe https://www.instagram.com/reel/XXXXXXX/
```

The recipe prints to the terminal and is saved to `output/<recipe-title>.md`.

### CLI optional flags

```bash
# Save to a custom output directory
igrecipe https://www.instagram.com/reel/XXXXXXX/ --output ~/recipes

# Provide a language hint for Whisper (helps accuracy for non-English reels)
igrecipe https://www.instagram.com/reel/XXXXXXX/ --lang hi   # Hindi
igrecipe https://www.instagram.com/reel/XXXXXXX/ --lang ta   # Tamil
igrecipe https://www.instagram.com/reel/XXXXXXX/ --lang gu   # Gujarati
```

---

## How it works

1. **Download** — `yt-dlp` fetches the reel video to a temp directory.
2. **Caption** — Instagram's public oEmbed API is queried for the post caption (no login needed).
3. **Audio extraction** — `ffmpeg` strips audio to a mono 16 kHz MP3.
4. **Transcription** — The audio is base64-encoded and sent to OpenRouter's Whisper Large V3 endpoint.
5. **Recipe extraction** — Transcript + caption are sent to an LLM via OpenRouter, which returns a structured markdown recipe.
6. **Cleanup** — All temp files are deleted. The dashboard shows the recipe in-browser only; the CLI saves it to `output/`.

---

## Limitations

- **Public reels only.** Private accounts, age-gated content, and geo-restricted reels will fail at the download step.
- Caption fetching relies on Instagram's oEmbed endpoint, which may return no data for some posts.
- Whisper transcription quality depends on audio clarity and background noise in the reel.

---

## Project structure

```
igrecipe/
├── app.py            # Streamlit dashboard
├── main.py           # CLI entrypoint (typer)
├── downloader.py     # yt-dlp wrapper
├── transcriber.py    # ffmpeg audio strip + OpenRouter Whisper call
├── caption.py        # Instagram oEmbed caption fetch
├── recipe.py         # LLM recipe extraction via OpenRouter
├── start.sh          # Launch script for macOS/Linux
├── start.bat         # Launch script for Windows
├── .env.example      # API key template
└── requirements.txt
```
