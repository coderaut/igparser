from pathlib import Path

from typer.testing import CliRunner

import main

runner = CliRunner()


def test_cli_writes_markdown_with_attribution(monkeypatch, tmp_path):
    def fake_fetch(url, work_dir):
        return None, [], "the caption", {
            "author": "creator",
            "source_url": "https://www.instagram.com/reel/VID123abc/",
            "timestamp": "2026-06-20T10:00:00.000Z",
        }

    def fake_extract(transcript, caption, api_key):
        return "# My Title\n\nFormatted body.", "my-title"

    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    monkeypatch.setattr(main, "fetch_post", fake_fetch)
    monkeypatch.setattr(main, "extract_content", fake_extract)
    monkeypatch.setattr(main, "fetch_caption", lambda url: "")

    result = runner.invoke(
        main.app, ["https://www.instagram.com/reel/VID123abc/", "-o", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    out = (tmp_path / "my-title.md").read_text()
    assert out.splitlines()[0] == "# My Title"
    assert "> Source: @creator · [original post](https://www.instagram.com/reel/VID123abc/) · 2026-06-20" in out
    assert "Formatted body." in out
