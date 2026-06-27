# ig-parser: Apify fetch backend

**Date:** 2026-06-27
**Status:** Approved design — ready for implementation plan
**Author:** Shubham + Claude (brainstorming)

## Context & motivation

ig-parser currently retrieves Instagram posts with `yt-dlp` (video reels) and
`instaloader` (image carousels), both authenticated via a cookie jar
(`cookies/instagram.txt`, sourced from the `cookie-mint` vault). This retrieval
path is structurally brittle: Instagram flags Heimdall's **datacenter IP**
(`148.230.67.58`), exported cookies expire and trigger challenges, and replaying a
residential-minted session from the datacenter IP locked the account once
("impossible travel", 2026-06-22). The `cookie-mint` effort to mint sessions
on-IP was itself parked on an Instagram HTTP 429 (2026-06-27) — the wall is
structural, not a bug.

A research report (`/root/Sync/Reports/2026-06-27-instagram-link-extraction-ai-agent-report.md`)
recommends the durable architecture: **separate "reach Instagram" from "understand
the media."** Outsource retrieval to a managed provider (Apify Instagram Scraper)
that owns the anti-bot problem; keep all media understanding (OCR, Whisper
transcription, frame fallback, LLM formatting) local and unchanged.

This spec covers swapping **only** ig-parser's fetch layer to Apify. The
understanding half of the pipeline is untouched.

## Goals

- Replace the cookie/yt-dlp/instaloader fetch path with a single Apify-backed
  fetcher.
- Preserve the existing pipeline downstream of fetch byte-for-byte (transcription,
  vision OCR, frame fallback, LLM formatting).
- Enrich output with author, source URL, and post date.
- Remove the cookie dependency entirely; archive the old fetch code for reference.

## Non-goals (explicitly deferred)

- HikerAPI / SociaVault / oEmbed fallback chain. **Apify-only for v1.** The fetch
  layer is isolated behind one function so a fallback can be added later if Apify
  proves unreliable or too costly — but we do not build it speculatively (YAGNI).
- Private / follow-only content retrieval. Apify serves public posts; private
  posts fail with a clear "forward a screenshot" message. No cookie fallback.
- Changes to the Hermes `ig-save` skill. Its cookie-install step becomes dead code
  (flagged below) but Hermes-side cleanup is separate work.
- The `cookie-mint` container. It stays parked and is simply no longer referenced
  by ig-parser.

## Decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Where the change lives | Inside ig-parser (swap fetch, keep detection brain) |
| Old fetch code | Replace entirely, **archive to `legacy/`** for future reference |
| Provider scope (v1) | Apify only, behind a clean interface |
| Output enrichment | Add author + source URL + date (skip likes/views/hashtags) |
| Apify account | Token already exists; dedicated `APIFY_TOKEN` in ig-parser `.env` |
| Cost guard | One URL per call, `resultsLimit: 1`, hard request timeout |
| Module shape | `fetch_post()` returns `(video_path, image_paths, caption, meta)` — tuple + `meta` dict |

## Architecture

The pipeline is unchanged except the fetch stage.

```
fetch_post(url, work_dir) → (video_path, image_paths, caption, meta)
   → transcriber / image_reader / frame fallback   [UNCHANGED]
   → content_extractor (LLM format)                 [UNCHANGED]
   → main.py injects source-attribution line        [NEW: § output]
   → output/<slug>.md
```

The seam is the same one `download_reel` occupied: everything downstream operates
only on **local file paths**, which Apify-fetched media satisfies identically.

## Component: `fetcher.py` (new)

Single responsibility: Instagram URL → Apify → local media files + metadata.

**Public function:**

```python
def fetch_post(url: str, work_dir: Path) -> tuple[Path | None, list[Path], str, dict]:
    """Fetch an Instagram post/reel/carousel via Apify.

    Returns (video_path, image_paths, caption, meta).
      - Video post:     (video_path, [], caption, meta)
      - Image carousel: (None, [slide_01.jpg, ...], caption, meta)
      - Single image:   (None, [slide_01.jpg], caption, meta)
    Exactly one of video_path / image_paths is non-empty.
    Raises RuntimeError on auth failure, inaccessible post, or download failure.
    """
```

**Apify call:**

- Endpoint: `POST https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items?token=<APIFY_TOKEN>`
- Body: `{"directUrls": [url], "resultsType": "posts", "resultsLimit": 1, "addParentData": false}`
- `run-sync-get-dataset-items` blocks until the run finishes and returns the
  dataset items array directly — one HTTP call, no polling.
- Hard request timeout (e.g. 120s).

**Response parsing (`items[0]`), branch on shape:**

- `videoUrl` present (`type: "Video"` / `productType: "clips"`) → download to
  `work_dir/reel.mp4` → `(video_path, [], caption, meta)`
- carousel (`childPosts` / `images`, `type: "Sidecar"`) → download each image
  child in order to `slide_NN.jpg` → `(None, [paths], caption, meta)`
- single image (`type: "Image"`) → one slide → `(None, [slide_01.jpg], caption, meta)`

**Media download:** `httpx.get` each CDN URL (public — no cookies/auth), write
bytes to `work_dir`. Per-slide failures warn-and-continue (matches current
carousel behavior). Treat provider media URLs as expiring: download immediately,
never persist the URL.

**`meta` dict:**

```python
{
  "author": ownerUsername,
  "full_name": ownerFullName,
  "source_url": <canonical url>,   # from item "url"
  "timestamp": timestamp,           # ISO publication date
  "type": type,                     # Video | Sidecar | Image
  "shortcode": shortCode,
}
```

Reuses the existing `_extract_shortcode` regex for URL validation.

## Output enrichment (author + source + date)

`main.py` injects a single attribution line into the markdown body, immediately
under the H1 title:

```
> Source: @<author> · [original post](<source_url>) · <YYYY-MM-DD>
```

**Why a body line, not YAML frontmatter:** the Hermes `ig-save` skill prepends its
own capture frontmatter before filing the note to Obsidian. Emitting our own
`---` block would collide and produce a malformed double-frontmatter note. A
blockquote under the H1 survives that prepend cleanly and renders fine in the
Streamlit dashboard. (Threading `meta` into `ig-save`'s frontmatter is a later,
optional enhancement — Hermes-skill territory, out of scope here.)

The Streamlit dashboard (`app.py`) shows the same enriched markdown in-memory.

Caption resolution becomes `caption = apify_caption or fetch_caption(url)` —
Apify caption is primary; the oEmbed fallback (`caption.py`) is retained because
it's free and not cookie-based.

## Removed / archived / kept

**Archived to `legacy/`** (with a short `legacy/README.md` explaining why — kept
for reference, not imported by the app):
- `downloader.py` (yt-dlp + instaloader + cookie-sync + credential login)
- `detector.py` (already dead — the old 5-type classifier)

**Removed:**
- `yt-dlp`, `instaloader` from `requirements.txt` / `pyproject.toml`
- `COOKIES_FILE`, `IG_USERNAME`, `IG_PASSWORD` env from `docker-compose.yml`
- the `/root/cookie-vault:/cookies:ro` volume mount from `docker-compose.yml`

**Added:**
- `APIFY_TOKEN` env (dedicated token for ig-parser, per the one-key-per-project rule)

**Kept (unchanged):**
- `transcriber.py`, `image_reader.py`, `content_extractor.py`
- `caption.py` (oEmbed fallback — free, non-cookie)
- `ffmpeg` in the image (Whisper audio extraction still needs it)
- `app.py` / `main.py` logic, except the fetch import + 4-tuple unpack + attribution line

## Error handling

- Missing / invalid `APIFY_TOKEN` → clear `RuntimeError`.
- **Empty dataset** (private / deleted / age-gated post — Apify returns no items)
  → `RuntimeError`: *"post not accessible (private/deleted/age-restricted) —
  forward a screenshot instead."* This is the deliberate private-content boundary.
- Apify run timeout / quota exceeded / HTTP 4xx-5xx → distinct, clear messages,
  logged via the existing `logger.py`.
- All media slides fail to download → abort with a clear error; partial success →
  continue (existing carousel semantics).
- Existing downstream guard preserved: if both transcript and caption end up
  empty, the pipeline aborts.

## Testing

**Unit (no live calls — mock `httpx`):**
- Record 4 Apify JSON fixtures: video reel, multi-image carousel, single image,
  empty/private response.
- Assert `fetch_post` returns the correct tuple shape and `meta` for each.
- URL normalization / `_extract_shortcode` cases (valid `/p/`, `/reel/`, invalid).

**Parity:** downstream modules are unchanged, so their behavior is preserved by
construction; no new tests required there.

**Live smoke (human-gated, one run):** a real public reel **and** a real carousel
through the full CLI (`python main.py <url> -o /output`), confirming:
- the markdown body and the attribution line are correct,
- Whisper transcription fires on the Apify-sourced video,
- Gemma vision OCR fires on the Apify-sourced carousel images.

## Follow-ups (noted, not in this spec)

- Hermes `ig-save` skill: the cookie-install step (`ig_cookies_update.sh`) is now
  dead code; clean up Hermes-side later. Optionally thread `meta` into ig-save's
  capture frontmatter.
- HikerAPI / SociaVault fallback, if Apify proves unreliable on real links.
- Update ig-parser `CLAUDE.md` and `README.md` to reflect the Apify backend
  (part of implementation, but called out so it isn't forgotten).
