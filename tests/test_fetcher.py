import json
from pathlib import Path

import pytest

import fetcher

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> list:
    return json.loads((FIXTURES / name).read_text())


# --- _extract_shortcode ---

@pytest.mark.parametrize("url,expected", [
    ("https://www.instagram.com/p/ABC123/", "ABC123"),
    ("https://www.instagram.com/reel/XyZ_-9/", "XyZ_-9"),
    ("https://instagram.com/reel/abc/?igsh=foo", "abc"),
])
def test_extract_shortcode_ok(url, expected):
    assert fetcher._extract_shortcode(url) == expected


def test_extract_shortcode_rejects_non_post():
    with pytest.raises(ValueError):
        fetcher._extract_shortcode("https://www.instagram.com/someuser/")


# --- _parse_item ---

def test_parse_item_video():
    item = _load("apify_video.json")[0]
    video_url, image_urls, caption, meta = fetcher._parse_item(item)
    assert video_url == "https://cdn.example.com/reel.mp4"
    assert image_urls == []
    assert caption == "My reel caption with #tags"
    assert meta["author"] == "creator"
    assert meta["source_url"] == "https://www.instagram.com/reel/VID123abc/"
    assert meta["timestamp"] == "2026-06-20T10:00:00.000Z"
    assert meta["type"] == "Video"
    assert meta["shortcode"] == "VID123abc"


def test_parse_item_carousel_skips_video_child():
    item = _load("apify_carousel.json")[0]
    video_url, image_urls, caption, meta = fetcher._parse_item(item)
    assert video_url is None
    assert image_urls == [
        "https://cdn.example.com/s1.jpg",
        "https://cdn.example.com/s2.jpg",
    ]
    assert meta["author"] == "tipster"


def test_parse_item_single_image():
    item = _load("apify_image.json")[0]
    video_url, image_urls, caption, meta = fetcher._parse_item(item)
    assert video_url is None
    assert image_urls == ["https://cdn.example.com/single.jpg"]
    assert caption == "A single photo"


# --- inject_source_line ---

def test_inject_source_line_after_h1():
    md = "# Title\n\nBody text."
    meta = {
        "author": "creator",
        "source_url": "https://www.instagram.com/reel/VID123abc/",
        "timestamp": "2026-06-20T10:00:00.000Z",
    }
    out = fetcher.inject_source_line(md, meta)
    lines = out.splitlines()
    assert lines[0] == "# Title"
    assert lines[2] == (
        "> Source: @creator · "
        "[original post](https://www.instagram.com/reel/VID123abc/) · 2026-06-20"
    )
    assert "Body text." in out


def test_inject_source_line_no_h1_prepends():
    md = "Just body, no heading."
    meta = {"author": "x", "source_url": "https://e.com/p/1/", "timestamp": "2026-06-01T00:00:00Z"}
    out = fetcher.inject_source_line(md, meta)
    assert out.startswith("> Source: @x")


def test_inject_source_line_empty_meta_noop():
    md = "# Title\n\nBody."
    assert fetcher.inject_source_line(md, {}) == md
