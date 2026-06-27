## Task 6 Report — Update docs (CLAUDE.md + README.md)

### Files changed
- `CLAUDE.md` — 9 edits applied
- `README.md` — 7 edits applied

### CLAUDE.md changes

1. **Migration banner removed** — The entire `> ⏳ MIGRATION IN PROGRESS …` blockquote at the top was stripped.
2. **Pipeline step 1** — `downloader.py` description replaced with `fetcher.py` (Apify, no cookies, returns `meta`).
3. **Caption step wording** — "downloader returned no description" → "fetcher returned no description" (coherence fix caught in self-review).
4. **`## Cookies` section replaced** — Entire section replaced with `## Retrieval (Apify)` block (verbatim from brief).
5. **Required in `.env` block** — Removed `IG_USERNAME`/`IG_PASSWORD` optional block; added `APIFY_TOKEN` as required.
6. **File map** — `downloader.py` + `detector.py` lines replaced with `fetcher.py` line; `cookies/` entry replaced with `legacy/`; `app.py` description stripped of "sidebar has cookies age + upload" (stale, cookies sidebar removed in Task 2).
7. **Docker section** — `./cookies` writable volume line replaced with "No cookie volume — retrieval is via Apify" line.
8. **Hermes ig-save paragraph** — Appended NOTE (2026-06-27) marking `ig_cookies_update.sh` as dead.
9. **Key constraints** — Removed 3 stale bullets (Cookies expire, Credential login blocked, Account-lock gotcha) and 2 stale yt-dlp/instaloader-specific bullets; added Apify-only constraint bullet. Dev setup comment updated to mention `APIFY_TOKEN`.

### README.md changes

1. **Requirements** — Replaced "Instagram cookies file" bullet with Apify token requirement.
2. **Setup step 4** — Updated comment to mention both `OPENROUTER_API_KEY` and `APIFY_TOKEN`.
3. **`## Cookies` section replaced** — Replaced with `## Retrieval` section describing Apify (no cookies/yt-dlp/instaloader).
4. **Docker section** — Replaced two-step "add key + copy cookies" with single "cp .env.example + edit" step.
5. **How it works** — Both Video reels and Image carousels now describe Apify retrieval via `fetcher.py` instead of yt-dlp/instaloader.
6. **Project structure** — `downloader.py` → `fetcher.py`; `cookies/` → `legacy/`.
7. **Limitations** — Replaced cookie-expiry and datacenter-IP bullets with Apify-specific limitations.

### Verification grep output

```
cd "/root/Repo Apps/IG Parser" && grep -rn "cookies/instagram.txt\|IG_USERNAME\|IG_PASSWORD\|instaloader" CLAUDE.md README.md
```

**Output: (empty — no matches)**

Broader scan for `yt-dlp`, `downloader.py`, `cookie` found only intentional historical context:
- `legacy/` entries noting the old path was archived
- "No cookies" / "Cookies are gone" statements describing the new behavior
- The ig-save paragraph retained per brief (NOTE appended marking cookie-install step dead)

### Self-review findings

No contradictions or stale instructions. Coherence issues caught and fixed beyond the brief's explicit steps:
- "downloader" → "fetcher" in the caption step description
- Stale "sidebar has cookies age + upload" in file map `app.py` entry removed (cookies sidebar was removed in Task 2)
- `cookies/` file map entry replaced with `legacy/`
- Dev setup comment updated to name both required keys

### Concerns

None. All changes are doc-only (no code or config touched).

### Commit

`2cfcdab` — `docs: describe Apify backend; drop cookie instructions`  
2 files changed, 44 insertions(+), 80 deletions(-)

---

## Final-review fixes

### Fix 1 — Uncaught ValueError on non-post URLs (`fetcher.py`)

`fetch_post` previously called `_extract_shortcode(url)` bare; a profile URL would
escape as a raw `ValueError` traceback. Added a try/except around the call inside
`fetch_post` to re-raise as `RuntimeError(str(e))`, keeping `_extract_shortcode`
itself raising `ValueError` (its own unit test is untouched). The conversion fires
**before** the APIFY_TOKEN check, which is the correct ordering (validated by
inspecting the function body).

### Fix 2 — Request-shape coverage (`tests/test_fetcher.py`)

Extended the `_patch_apify` helper's `fake_post` assertions to include:
- `json["resultsType"] == "posts"`
- `json["addParentData"] is False`

These match the documented Apify contract in `fetcher.py`'s payload dict and ensure
any future payload regression fails tests immediately.

### Fix 3 — Dead `.gitignore` entry (`.gitignore`)

Removed the `cookies/*.txt` line. The `cookies/` directory was deleted in the Apify
migration; the ignore entry was stale and potentially confusing.

### Fix 4 — `.dockerignore` hardening (`.dockerignore`)

Expanded the existing `.dockerignore` (which had `.venv`, `__pycache__`, `*.pyc`,
`.env`, `output/`, `cookies/`, `.git`) to also exclude `legacy/`, `tests/`,
`.superpowers/`, `docs/`, `logs/`. Removed the now-gone `cookies/` entry.
All top-level runtime modules (`main.py`, `app.py`, `fetcher.py`, `transcriber.py`,
`image_reader.py`, `content_extractor.py`, `caption.py`, `logger.py`,
`pyproject.toml`, `requirements.txt`) are retained in the image.

### New tests added

- `test_fetch_post_non_post_url_raises_runtime_error` — asserts `fetch_post` raises
  `RuntimeError` (not `ValueError`) for `https://www.instagram.com/someuser/`, with
  APIFY_TOKEN unset (fires at URL-validation stage, before token check).

### pytest output

```
19 passed in 0.32s
```

All 19 tests green, output pristine.
