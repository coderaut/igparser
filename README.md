# instagram-recipe-extractor

A local CLI tool that downloads an Instagram cooking reel and outputs a formatted recipe as a Markdown file.

It downloads the video, strips the audio, transcribes it with Whisper via OpenRouter, fetches the post caption, then uses an LLM to synthesise everything into a clean recipe.

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
# 1. Clone or copy this project
cd instagram-recipe-extractor

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
.venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API keys
cp .env.example .env
# Edit .env and fill in your keys:
#   OPENROUTER_API_KEY=sk-or-...
#   ANTHROPIC_API_KEY=sk-ant-...
```

---

## Usage

### Every time you open a new terminal

```powershell
# Step 1 — navigate to the project and activate the virtual environment
cd "C:\Users\XRIG\Documents\Repo Apps\Insta-defuddler"
.venv\Scripts\activate

# Step 2 — run it
igrecipe https://www.instagram.com/reel/XXXXXXX/
```

The recipe prints to the terminal and is saved to `output/<recipe-title>.md`.

### Optional flags

```powershell
# Save to a custom output directory
igrecipe https://www.instagram.com/reel/XXXXXXX/ --output C:\Users\XRIG\recipes

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
5. **Recipe extraction** — Transcript + caption are sent to an LLM via OpenRouter, which returns a structured Markdown recipe.
6. **Save** — The `.md` file is written to the `output/` folder and the temp files are deleted.

---

## Limitations

- **Public reels only.** Private accounts, age-gated content, and geo-restricted reels will fail at the download step.
- Caption fetching relies on Instagram's oEmbed endpoint, which may return no data for some posts.
- Whisper transcription quality depends on audio clarity and background noise in the reel.

---

## Project structure

```
instagram-recipe-extractor/
├── main.py           # CLI entrypoint (typer)
├── downloader.py     # yt-dlp wrapper
├── transcriber.py    # ffmpeg audio strip + OpenRouter Whisper call
├── caption.py        # Instagram oEmbed caption fetch
├── recipe.py         # Claude API recipe extraction
├── .env.example      # API key template
├── requirements.txt
└── output/           # Generated recipes land here
```
