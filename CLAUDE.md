# ig parser

Downloads a public Instagram Reel or static post and extracts a clean markdown summary.
Supports four content types: recipes, movie/show recommendations, book recommendations, and places to visit.

## What it does

Pipeline (in order):
1. `downloader.py` — `yt-dlp` downloads the post (video or image) to a temp dir
2. `caption.py` — Instagram oEmbed API fetches the post caption (no auth needed)
3. `transcriber.py` — `ffmpeg` strips audio to mono 16 kHz MP3, then sends it base64-encoded to OpenRouter Whisper Large V3. Skipped silently for static image posts (no audio track).
4. `detector.py` — LLM classifies the content as `recipe`, `movie`, `book`, or `place`
5. `extractor.py` — Type-specific prompt sent to LLM via OpenRouter; returns structured markdown
6. Cleanup — temp files deleted; CLI saves to `output/<slug>.md`, dashboard is in-memory only

## Entry points

| Mode | Command |
|------|---------|
| Streamlit dashboard | `streamlit run app.py` → `http://localhost:8501` |
| CLI | `igrecipe <url> [--output dir] [--lang code] [--type auto|recipe|movie|book|place]` |

CLI is registered via `pyproject.toml` as `igrecipe = "main:app"`.

## Environment

Requires a single env var in `.env`:

```
OPENROUTER_API_KEY=sk-or-...
```

Also requires `ffmpeg` on PATH (only needed for video reels).

## File map

```
app.py          Streamlit UI — runs the full pipeline, no file output
main.py         CLI entrypoint (Typer) — saves output/<slug>.md
downloader.py   yt-dlp wrapper → returns Path to downloaded file
transcriber.py  ffmpeg audio strip + OpenRouter Whisper call
caption.py      Instagram oEmbed fetch → returns caption string or None
detector.py     LLM classifier → returns one of: recipe, movie, book, place
extractor.py    Type-specific LLM prompts → returns (markdown, slug)
pyproject.toml  Package config; CLI script registered here
```

## Models used (via OpenRouter)

- Transcription: `openai/whisper-large-v3` (in `transcriber.py`)
- Detection + extraction: `google/gemma-4-31b-it` (in `detector.py` and `extractor.py`)

To swap models, change the constants at the top of each file.

## Content type output formats

| Type | Key sections |
|------|-------------|
| recipe | Ingredients, Instructions, Notes |
| movie | Director/Genre/Where to watch, Why Watch It, What to Expect, Notes |
| book | Author/Genre, What It's About, Why Read It, Notes |
| place | Location/Type, Why Visit, Tips, Notes |

To add a new content type: add an entry to `_PROMPTS` in `extractor.py`, add it to `CONTENT_TYPES` in `detector.py`, and update the classifier system prompt.

## Key constraints

- Public posts only — private/age-gated/geo-restricted will fail at download
- Static image posts: audio extraction is skipped, extraction relies on caption alone
- If both transcript and caption are empty, the pipeline aborts
- Temp work dir: `/tmp/igrecipe` (CLI) or `tempfile.gettempdir()/igrecipe` (dashboard)

## Dev setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env   # add your OPENROUTER_API_KEY
```
