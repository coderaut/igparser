# ig parser

Downloads public Instagram Reels and static posts and formats them as clean markdown. All text is extracted first (caption + transcript or image text), then a single LLM pass chooses the appropriate structure and formats the content — no predefined type templates, nothing discarded.

## What it does

Pipeline (in order):
1. `downloader.py` — returns `(video_path, image_paths, caption)`. Video reels use `yt-dlp`; image carousels use `instaloader`. Both use `cookies/instagram.txt` for auth.
2. `caption.py` — Instagram oEmbed API fallback for caption; only used if the downloader returned no description.
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
```

Optional — enables credential-based session login (see Cookies section):
```
IG_USERNAME=your_instagram_username
IG_PASSWORD=your_instagram_password
```

Also requires `ffmpeg` on PATH (only needed for video reels).

## Cookies

**Primary source (Heimdall): the cookie-mint vault.** As of 2026-06-27 the Docker deployment reads
its cookie from `/root/cookie-vault/instagram.txt`, mounted **read-only** at `/cookies` (single source
of truth — see the `cookie-mint` app/skill). `COOKIES_FILE=/cookies/instagram.txt` already points yt-dlp
there. Refresh via the Hermes `cookie-mint` skill or `cookie-mint`'s `/session` flow. Credential login
(`IG_USERNAME`/`IG_PASSWORD`) is **disabled** in `.env` because the vault is read-only and datacenter-IP
login never worked anyway; the sections below describe the legacy/local auth paths.

Instagram requires authenticated downloads. The app supports two auth paths — both use `cookies/instagram.txt` as the cookie store for yt-dlp.

**Browser cookie export (always works):**
Upload a fresh `instagram.txt` directly from the Streamlit sidebar (cookie age indicator + file uploader). No file transfer or restart needed — cookies are read from disk on every request.

To export: use the "Get cookies.txt LOCALLY" browser extension while logged in to Instagram. Cookies with "stay logged in" last ~90 days.

**Credential-based session (best-effort):**
If `IG_USERNAME` / `IG_PASSWORD` are set, the app uses instaloader to load or create a saved session at `cookies/session-<username>`, then syncs the session cookies to `cookies/instagram.txt` before each request. Falls back silently to the existing `cookies.txt` if login fails.

**Important:** Instagram blocks automated logins from datacenter IPs (DigitalOcean, AWS, etc.) with "Unexpected null login result". Credential login will not work when running on a VPS — browser cookie export is the only reliable method in that case.

`COOKIES_FILE` env var overrides the default cookie path (Docker sets it to `/cookies/instagram.txt`). yt-dlp rewrites the file after each request — the volume must be writable (not `:ro`).

## Logging

Logs write to `./logs/igrecipe.log` (rotating, 5 MB max, 3 backups). Docker mounts `./logs` as `/logs` via `LOG_DIR=/logs` env var. INFO+ goes to stdout (visible in `docker logs ig-parser`); DEBUG goes to file only.

`logger.py` sets up the logger; all modules import `from logger import log`.

## Docker deployment (Heimdall)

Port bound `127.0.0.1:8501` — loopback only, NOT exposed publicly. `0.0.0.0` would bind all interfaces (including the public IP), not just Tailscale — a real exposure caught and fixed 2026-06-08. Reached externally via `ig.heim-dall.com` through Caddy on the Tailscale interface; see [[feedback-tailscale-port-binding]].
`./cookies` mounted as writable volume at `/cookies`.
`./logs` mounted at `/logs`.
`./output` mounted at `/output` (added 2026-06-22) — lets the host read CLI results written inside the container. Used by the Hermes `ig-save` skill (see below). git-ignored.

```bash
docker compose up -d --build
```

## Hermes ig-save integration

The Hermes agent has an `ig-save` skill (`/root/.hermes/skills/social-media/ig-save/`) that turns a shared Instagram link into an Obsidian capture note. It runs the CLI **inside this container** (`docker exec ig-parser python main.py "<url>" -o /output`) because the Heimdall host lacks the deps (no `faster_whisper`). The markdown lands in `/output` (= host `./output`), then Hermes prepends capture frontmatter and moves it to `/root/Obsidian/Valhalla/Captures/`. The skill also installs fresh cookies sent over Telegram (`ig_cookies_update.sh`) — no container restart needed, yt-dlp re-reads the jar per request.

## File map

```
app.py               Streamlit UI — runs the full pipeline, no file output; sidebar has cookies age + upload
main.py              CLI entrypoint (Typer) — saves output/<slug>.md; flags: --lang, --output
downloader.py        yt-dlp (video) / instaloader (image carousels); session-based auth with cookies.txt fallback
transcriber.py       ffmpeg audio strip + OpenRouter Whisper; extract_frames() for scene-change fallback
image_reader.py      base64-encodes images → Gemma 4 vision → extracted text (carousels + frame fallback)
caption.py           Instagram oEmbed fetch → fallback caption if yt-dlp returned nothing
content_extractor.py Single free-form LLM prompt → chooses structure, preserves all content → returns (markdown, slug)
logger.py            Rotating file logger; LOG_DIR env var sets output dir (default /logs)
detector.py          Unused — kept for reference. Was the 5-type LLM classifier (recipe/movie/book/place/game).
pyproject.toml       Package config; CLI script registered here
cookies/             instagram.txt + session-<username> — git-ignored, Docker-mounted
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
- Cookies expire periodically (~90 days) — upload a fresh `instagram.txt` via the Streamlit sidebar, or send it to Hermes (`ig-save` skill installs it)
- Credential login is blocked on VPS/datacenter IPs — browser cookie export is required in those environments
- **Account-lock gotcha (2026-06-22):** cookies minted on a home/residential IP then replayed from Heimdall's datacenter IP (148.230.67.58) look like a stolen session → IG flags/locks the account ("impossible travel"). Fix: mint the session **from Heimdall's IP** — log in with the device routed through Heimdall's Tailscale exit node (the ig-parser container egresses the same 148.230.67.58), complete IG's "trust this device" prompt, then export those cookies. Still a datacenter IP so expect occasional checkpoints; keep download volume human-paced. Full plan: `/root/Sync/Reports/2026-06-22-ig-save-trusted-machine-cookies.md`. Planned mitigation: an `IG_USER_AGENT` env threaded through yt-dlp/instaloader/httpx so requests match the trusted browser.
- Frame extraction fallback (scene detection) works well for hard-cut slideshow reels but misses visually similar slides (same design template across slides = low scene change scores below threshold)
- Whisper returns 400 if the extracted audio file is too small (empty audio track) — `transcriber.py` checks for this and raises a clean error before sending
- Temp work dir: `/tmp/igrecipe` (CLI) or `tempfile.gettempdir()/igrecipe` (dashboard)

## Dev setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env   # add your OPENROUTER_API_KEY
```
