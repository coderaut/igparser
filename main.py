import shutil
from pathlib import Path

import typer
from dotenv import load_dotenv
import os

from downloader import download_reel
from transcriber import extract_audio, transcribe_audio
from caption import fetch_caption
from recipe import extract_recipe

load_dotenv()

app = typer.Typer(add_completion=False)

WORK_DIR = Path("/tmp/igrecipe")
DEFAULT_OUTPUT_DIR = Path("output")


@app.command()
def main(
    url: str = typer.Argument(..., help="Instagram Reel URL"),
    output: Path = typer.Option(
        DEFAULT_OUTPUT_DIR, "--output", "-o", help="Directory to save the recipe markdown"
    ),
    lang: str | None = typer.Option(
        None, "--lang", "-l", help="Optional language hint for Whisper (e.g. hi, ta, gu)"
    ),
) -> None:
    """Download an Instagram Reel and extract a formatted recipe as a markdown file."""
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()

    if not openrouter_key:
        typer.echo("Error: OPENROUTER_API_KEY is not set in your .env file.", err=True)
        raise typer.Exit(1)

    work_dir = WORK_DIR
    try:
        # --- Step 1: Download reel ---
        typer.echo("Downloading reel...")
        try:
            video_path = download_reel(url, work_dir)
        except RuntimeError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

        # --- Step 2: Fetch caption ---
        typer.echo("Fetching caption...")
        caption = fetch_caption(url)
        if caption:
            typer.echo(f"Caption found ({len(caption)} chars).")
        else:
            typer.echo("Warning: No caption found — proceeding with transcript only.", err=True)

        # --- Step 3: Extract audio ---
        typer.echo("Extracting audio...")
        try:
            audio_path = extract_audio(video_path, work_dir)
        except (RuntimeError, FileNotFoundError) as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

        # --- Step 4: Transcribe ---
        typer.echo("Transcribing audio...")
        try:
            transcript = transcribe_audio(audio_path, openrouter_key, language=lang)
        except RuntimeError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

        if transcript:
            typer.echo(f"Transcript obtained ({len(transcript)} chars).")
        else:
            typer.echo("Warning: Transcript is empty.", err=True)

        if not transcript and not caption:
            typer.echo(
                "Error: Both transcript and caption are empty. Cannot extract a recipe.", err=True
            )
            raise typer.Exit(1)

        # --- Step 5: Extract recipe ---
        typer.echo("Extracting recipe...")
        try:
            recipe_md, slug = extract_recipe(transcript, caption or "", openrouter_key)
        except Exception as e:
            typer.echo(f"Error calling Claude API: {e}", err=True)
            raise typer.Exit(1)

        # --- Step 6: Save output ---
        output.mkdir(parents=True, exist_ok=True)
        out_file = output / f"{slug}.md"
        out_file.write_text(recipe_md, encoding="utf-8")

        typer.echo("\n" + "─" * 60)
        typer.echo(recipe_md)
        typer.echo("─" * 60)
        typer.echo(f"\nRecipe saved to: {out_file.resolve()}")

    finally:
        # Clean up temp files
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    app()
