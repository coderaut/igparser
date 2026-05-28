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
from caption import fetch_caption
from detector import detect_content_type, CONTENT_TYPES
from content_extractor import extract_content

load_dotenv()

WORK_DIR = Path(tempfile.gettempdir()) / "igrecipe"

TYPE_LABELS = {
    "recipe": "Recipe",
    "movie": "Movie / Show",
    "book": "Book",
    "place": "Place to Visit",
}

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
if "detected_type" not in st.session_state:
    st.session_state.detected_type = None

if generate and url.strip():
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not openrouter_key:
        st.error("OPENROUTER_API_KEY is not set in your .env file.")
        st.stop()

    st.session_state.result_md = None
    st.session_state.detected_type = None
    error = None

    with st.status("Working...", expanded=True) as status:
        try:
            st.write("Downloading post...")
            video_path, yt_caption = download_reel(url.strip(), WORK_DIR)
            st.write("Post downloaded.")

            st.write("Fetching caption...")
            caption = yt_caption or fetch_caption(url.strip())
            if caption:
                st.write(f"Caption found ({len(caption)} chars).")
            else:
                st.write("No caption found — continuing without it.")

            transcript = ""
            if video_path is None:
                st.write("Image-only post — using caption only.")
            else:
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
                        else:
                            st.write("Transcript is empty.")
                    except RuntimeError as e:
                        st.write(f"Transcription failed: {e}")
                except (RuntimeError, FileNotFoundError):
                    st.write("No audio track — using caption only.")

            if not transcript and not caption:
                raise ValueError("No caption or transcript available — cannot extract content.")

            st.write("Detecting content type...")
            detected = detect_content_type(transcript, caption or "", openrouter_key)
            label = TYPE_LABELS.get(detected, detected.title())
            st.write(f"Detected: **{label}**")
            st.session_state.detected_type = detected

            st.write(f"Extracting {label.lower()}...")
            result_md, _ = extract_content(detected, transcript, caption or "", openrouter_key)

            st.session_state.result_md = result_md
            status.update(label="Done!", state="complete", expanded=False)

        except Exception as e:
            error = str(e)
            status.update(label="Something went wrong.", state="error", expanded=True)

        finally:
            shutil.rmtree(WORK_DIR, ignore_errors=True)

    if error:
        st.error(error)

if st.session_state.result_md:
    detected_type = st.session_state.detected_type
    st.divider()
    if detected_type:
        st.caption(f"Type: {TYPE_LABELS.get(detected_type, detected_type.title())}")
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
