# legacy

Archived code, kept for reference only — **not imported by the running app.**

- `downloader.py` — the original Instagram fetch path: `yt-dlp` for video reels +
  `instaloader` for image carousels, authenticated via `cookies/instagram.txt`
  (sourced from the `cookie-mint` vault). Replaced 2026-06-27 by `fetcher.py`
  (Apify Instagram Scraper). The cookie path was structurally brittle on
  Heimdall's datacenter IP — see `docs/superpowers/specs/2026-06-27-ig-parser-apify-fetch-design.md`.
- `detector.py` — the original 5-type LLM classifier (recipe/movie/book/place/game),
  already superseded by the free-form formatter in `content_extractor.py`.

These files reference `yt-dlp` / `instaloader`, which are no longer installed.
Do not import them without reinstating those dependencies.
