import os
import shutil
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from downloader import download_reel
from transcriber import extract_audio, transcribe_audio
from caption import fetch_caption
from recipe import extract_recipe

load_dotenv()

WORK_DIR = Path(tempfile.gettempdir()) / "igrecipe"

st.set_page_config(page_title="igrecipe", layout="centered")

st.title("igrecipe")
st.caption("Paste a public Instagram Reel URL to extract a clean recipe.")

url = st.text_input(
    "Instagram Reel URL",
    placeholder="https://www.instagram.com/reel/...",
)
lang = st.text_input(
    "Language hint (optional)",
    placeholder="hi, ta, gu — leave blank for auto-detect",
)

generate = st.button("Generate Recipe", type="primary", disabled=not url.strip())

if "recipe_md" not in st.session_state:
    st.session_state.recipe_md = None

if generate and url.strip():
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not openrouter_key:
        st.error("OPENROUTER_API_KEY is not set in your .env file.")
        st.stop()

    st.session_state.recipe_md = None
    error = None

    STEPS = [
        "Downloading reel",
        "Fetching caption",
        "Extracting audio",
        "Transcribing audio",
        "Extracting recipe",
        "Done!",
    ]
    progress_bar = st.progress(0, text=STEPS[0])

    def advance(step: int, message: str) -> None:
        progress_bar.progress((step + 1) / len(STEPS), text=message)

    with st.status("Working...", expanded=True) as status:
        try:
            st.write("Downloading reel...")
            video_path = download_reel(url.strip(), WORK_DIR)
            st.write("Reel downloaded.")
            advance(0, STEPS[1])

            st.write("Fetching caption...")
            caption = fetch_caption(url.strip())
            if caption:
                st.write(f"Caption found ({len(caption)} chars).")
            else:
                st.write("No caption found — continuing with transcript only.")
            advance(1, STEPS[2])

            st.write("Extracting audio...")
            audio_path = extract_audio(video_path, WORK_DIR)
            st.write("Audio extracted.")
            advance(2, STEPS[3])

            st.write("Transcribing audio...")
            transcript = transcribe_audio(
                audio_path, openrouter_key, language=lang.strip() or None
            )
            if transcript:
                st.write(f"Transcript obtained ({len(transcript)} chars).")
            else:
                st.write("Transcript is empty.")
            advance(3, STEPS[4])

            if not transcript and not caption:
                raise ValueError("Both transcript and caption are empty — cannot extract a recipe.")

            st.write("Extracting recipe...")
            recipe_md, slug = extract_recipe(transcript, caption or "", openrouter_key)
            st.write("Recipe extracted.")
            advance(5, "Done!")

            st.session_state.recipe_md = recipe_md
            status.update(label="Done!", state="complete", expanded=False)

        except Exception as e:
            error = str(e)
            progress_bar.empty()
            status.update(label="Something went wrong.", state="error", expanded=True)

        finally:
            shutil.rmtree(WORK_DIR, ignore_errors=True)

    if error:
        st.error(error)

if st.session_state.recipe_md:
    st.divider()
    tab_recipe, tab_markdown = st.tabs(["Recipe", "Copy Markdown"])

    with tab_recipe:
        st.markdown(st.session_state.recipe_md)

    with tab_markdown:
        st.code(st.session_state.recipe_md, language="markdown")
