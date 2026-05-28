import shutil
from enum import Enum
from pathlib import Path

import typer
from dotenv import load_dotenv
import os

from downloader import download_reel
from transcriber import extract_audio, transcribe_audio
from image_reader import read_images
from caption import fetch_caption
from detector import detect_content_type
from content_extractor import extract_content

load_dotenv()

app = typer.Typer(add_completion=False)

WORK_DIR = Path("/tmp/igrecipe")
DEFAULT_OUTPUT_DIR = Path("output")


class ContentType(str, Enum):
    auto = "auto"
    recipe = "recipe"
    movie = "movie"
    book = "book"
    place = "place"


@app.command()
def main(
    url: str = typer.Argument(..., help="Instagram Reel or post URL"),
    output: Path = typer.Option(
        DEFAULT_OUTPUT_DIR, "--output", "-o", help="Directory to save the markdown file"
    ),
    lang: str | None = typer.Option(
        None, "--lang", "-l", help="Optional language hint for Whisper (e.g. hi, ta, gu)"
    ),
    content_type: ContentType = typer.Option(
        ContentType.auto, "--type", "-t", help="Content type: auto, recipe, movie, book, place"
    ),
) -> None:
    """Download a public Instagram Reel or post and extract a formatted markdown summary."""
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()

    if not openrouter_key:
        typer.echo("Error: OPENROUTER_API_KEY is not set in your .env file.", err=True)
        raise typer.Exit(1)

    work_dir = WORK_DIR
    try:
        typer.echo("Downloading post...")
        try:
            video_path, image_paths, yt_caption = download_reel(url, work_dir)
        except RuntimeError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

        typer.echo("Fetching caption...")
        caption = yt_caption or fetch_caption(url)
        if caption:
            typer.echo(f"Caption found ({len(caption)} chars).")
        else:
            typer.echo("Warning: No caption found — continuing without it.", err=True)

        transcript = ""
        if image_paths:
            typer.echo(f"Carousel post ({len(image_paths)} slides) — reading image text...")
            try:
                transcript = read_images(image_paths, openrouter_key)
                if transcript:
                    typer.echo(f"Image text extracted ({len(transcript)} chars).")
                else:
                    typer.echo("Warning: No text found in images.", err=True)
            except RuntimeError as e:
                typer.echo(f"Image reading error: {e}", err=True)
        elif video_path is not None:
            typer.echo("Extracting audio...")
            try:
                audio_path = extract_audio(video_path, work_dir)
                typer.echo("Transcribing audio...")
                try:
                    transcript = transcribe_audio(audio_path, openrouter_key, language=lang)
                    if transcript:
                        typer.echo(f"Transcript obtained ({len(transcript)} chars).")
                    else:
                        typer.echo("Warning: Transcript is empty.", err=True)
                except RuntimeError as e:
                    typer.echo(f"Transcription error: {e}", err=True)
                    raise typer.Exit(1)
            except (RuntimeError, FileNotFoundError):
                typer.echo("No audio track found — using caption only.")

        if not transcript and not caption:
            typer.echo(
                "Error: No caption or transcript available. Cannot extract content.", err=True
            )
            raise typer.Exit(1)

        if content_type == ContentType.auto:
            typer.echo("Detecting content type...")
            resolved_type = detect_content_type(transcript, caption or "", openrouter_key)
            typer.echo(f"Detected type: {resolved_type}")
        else:
            resolved_type = content_type.value

        typer.echo(f"Extracting {resolved_type}...")
        try:
            result_md, slug = extract_content(resolved_type, transcript, caption or "", openrouter_key)
        except Exception as e:
            typer.echo(f"Error calling LLM API: {e}", err=True)
            raise typer.Exit(1)

        output.mkdir(parents=True, exist_ok=True)
        out_file = output / f"{slug}.md"
        out_file.write_text(result_md, encoding="utf-8")

        typer.echo("\n" + "─" * 60)
        typer.echo(result_md)
        typer.echo("─" * 60)
        typer.echo(f"\nSaved to: {out_file.resolve()}")

    finally:
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    app()
