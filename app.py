import base64
import os
import shutil
import tempfile
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from downloader import download_reel
from transcriber import extract_audio, transcribe_audio
from image_reader import read_images
from caption import fetch_caption
from content_extractor import extract_content
from logger import log

load_dotenv()

WORK_DIR = Path(tempfile.gettempdir()) / "igrecipe"

st.set_page_config(page_title="ig parser", layout="centered")

st.title("ig parser")
st.caption("Paste a public Instagram Reel or post URL to extract a clean summary.")

url = st.text_input(
    "Instagram URL",
    placeholder="https://www.instagram.com/reel/... or /p/...",
)
generate = st.button("Extract", type="primary", disabled=not url.strip())

if "result_md" not in st.session_state:
    st.session_state.result_md = None

if generate and url.strip():
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not openrouter_key:
        st.error("OPENROUTER_API_KEY is not set in your .env file.")
        st.stop()

    st.session_state.result_md = None
    error = None

    with st.status("Working...", expanded=True) as status:
        try:
            log.info("--- request start: %s ---", url.strip())
            st.write("Downloading post...")
            video_path, image_paths, yt_caption = download_reel(url.strip(), WORK_DIR)
            st.write("Post downloaded.")

            st.write("Fetching caption...")
            caption = yt_caption or fetch_caption(url.strip())
            if caption:
                st.write(f"Caption found ({len(caption)} chars).")
                log.debug("caption: %d chars", len(caption))
            else:
                st.write("No caption found — continuing without it.")
                log.warning("no caption found for %s", url.strip())

            transcript = ""
            if image_paths:
                st.write(f"Carousel post ({len(image_paths)} slides) — reading image text...")
                try:
                    transcript = read_images(image_paths, openrouter_key)
                    if transcript:
                        st.write(f"Image text extracted ({len(transcript)} chars).")
                        log.debug("image text: %d chars", len(transcript))
                    else:
                        st.write("No text found in images.")
                        log.warning("image reader returned empty text")
                except RuntimeError as e:
                    st.write(f"Image reading failed: {e}")
                    log.error("image reading failed: %s", e)
            elif video_path is not None:
                try:
                    st.write("Extracting audio...")
                    audio_path = extract_audio(video_path, WORK_DIR)
                    st.write("Audio extracted.")
                    try:
                        st.write("Transcribing audio...")
                        transcript = transcribe_audio(
                            audio_path, openrouter_key, language=None
                        )
                        if transcript:
                            st.write(f"Transcript obtained ({len(transcript)} chars).")
                            log.debug("transcript: %d chars", len(transcript))
                        else:
                            st.write("Transcript is empty.")
                            log.warning("whisper returned empty transcript")
                    except RuntimeError as e:
                        st.write(f"Transcription failed: {e}")
                        log.error("transcription failed: %s", e)
                except (RuntimeError, FileNotFoundError):
                    st.write("No audio track — using caption only.")
                    log.info("no audio track in video, using caption only")

            if not transcript and not caption:
                raise ValueError("No caption or transcript available — cannot extract content.")

            st.write("Formatting content...")
            result_md, _ = extract_content(transcript, caption or "", openrouter_key)
            log.info("extraction complete: %d chars", len(result_md))

            st.session_state.result_md = result_md
            status.update(label="Done!", state="complete", expanded=False)
            log.info("--- request done: %s ---", url.strip())

        except Exception as e:
            error = str(e)
            log.error("pipeline error for %s: %s", url.strip(), e, exc_info=True)
            status.update(label="Something went wrong.", state="error", expanded=True)

        finally:
            shutil.rmtree(WORK_DIR, ignore_errors=True)

    if error:
        st.error(error)

if st.session_state.result_md:
    st.divider()
    tab_rendered, tab_markdown = st.tabs(["Rendered", "Copy Markdown"])
    with tab_rendered:
        st.markdown(st.session_state.result_md)
    with tab_markdown:
        b64 = base64.b64encode(st.session_state.result_md.encode()).decode()
        components.html(
            f"""
            <script>
            function copyMd() {{
                var text = atob("{b64}");
                var btn = document.getElementById("cb");
                if (navigator.clipboard && window.isSecureContext) {{
                    navigator.clipboard.writeText(text).then(function() {{
                        showDone(btn);
                    }}).catch(function() {{ fallback(text, btn); }});
                }} else {{
                    fallback(text, btn);
                }}
            }}
            function fallback(text, btn) {{
                var ta = document.getElementById("ta");
                ta.value = text;
                ta.style.display = "block";
                ta.focus();
                ta.setSelectionRange(0, ta.value.length);
                try {{
                    var ok = document.execCommand("copy");
                    if (ok) {{
                        ta.style.display = "none";
                        showDone(btn);
                        return;
                    }}
                }} catch(e) {{}}
                btn.textContent = "Long-press the text below to copy";
            }}
            function showDone(btn) {{
                btn.textContent = "✓ Copied!";
                setTimeout(function() {{ btn.textContent = "Copy to clipboard"; }}, 2000);
            }}
            </script>
            <button id="cb" onclick="copyMd()"
                style="background:#ff4b4b;color:white;border:none;padding:8px 20px;
                       border-radius:6px;cursor:pointer;font-size:14px;font-family:sans-serif;">
                Copy to clipboard
            </button>
            <textarea id="ta" readonly
                style="display:none;width:100%;height:120px;margin-top:10px;
                       font-size:12px;font-family:monospace;box-sizing:border-box;"></textarea>
            """,
            height=50,
        )
        st.code(st.session_state.result_md, language="markdown")
