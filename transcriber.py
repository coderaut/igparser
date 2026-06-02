import base64
import subprocess
from pathlib import Path

import httpx

from logger import log

OPENROUTER_TRANSCRIPTION_URL = "https://openrouter.ai/api/v1/audio/transcriptions"
WHISPER_MODEL = "openai/whisper-large-v3"

# Minimum meaningful audio size — anything smaller means ffmpeg found no audio stream
_MIN_AUDIO_BYTES = 1024


def extract_audio(video_path: Path, work_dir: Path) -> Path:
    """Strip audio from video to a mono 16kHz mp3 using ffmpeg."""
    audio_path = work_dir / "audio.mp3"
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-b:a", "64k",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed:\n{result.stderr}")
    if not audio_path.exists():
        raise FileNotFoundError("ffmpeg did not produce an audio file.")
    audio_size = audio_path.stat().st_size
    log.debug("audio extracted: %d bytes", audio_size)
    if audio_size < _MIN_AUDIO_BYTES:
        raise RuntimeError("Extracted audio is empty — video has no audio track.")
    return audio_path


def transcribe_audio(audio_path: Path, api_key: str, language: str | None = None) -> str:
    """Send audio to OpenRouter Whisper API and return the transcript text.

    OpenRouter STT requires JSON with base64-encoded audio, not multipart upload.
    """
    audio_bytes = audio_path.read_bytes()
    log.debug("sending audio to Whisper: %d bytes", len(audio_bytes))
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    body: dict = {
        "model": WHISPER_MODEL,
        "input_audio": {
            "data": audio_b64,
            "format": "mp3",
        },
    }
    if language:
        body["language"] = language

    response = httpx.post(
        OPENROUTER_TRANSCRIPTION_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=120,
    )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"OpenRouter transcription API error {response.status_code}: {response.text}"
        ) from e

    return response.json().get("text", "").strip()
