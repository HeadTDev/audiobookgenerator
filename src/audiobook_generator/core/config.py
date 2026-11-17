"""Generation settings, voices, and the API key loader (.env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

# App root = the folder holding run.py and .env (core -> audiobook_generator -> src -> root).
# The secret lives in .env there, never in the code.
APP_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = str(APP_ROOT / ".env")
API_KEY_VAR = "ELEVENLABS_API_KEY"
GEMINI_KEY_VAR = "GEMINI_API_KEY"


def _load_env_var(name):
    """Read a variable fresh from .env, so editing .env needs no app restart. '' if unset."""
    load_dotenv(ENV_PATH, override=True)
    return os.environ.get(name, "").strip()


def load_api_key():
    """The ElevenLabs key from .env. '' if unset."""
    return _load_env_var(API_KEY_VAR)


def load_gemini_key():
    """The optional Google AI Studio key (Notes to script) from .env. '' if unset."""
    return _load_env_var(GEMINI_KEY_VAR)


MODEL_ID = "eleven_v4"
LANGUAGE_CODE = "hu"
# Pinned so cached chunks from different runs always share one format.
OUTPUT_FORMAT = "mp3_44100_128"
MAX_CHUNK_CHARS = 5000  # Eleven v4 accepts up to 10,000 characters per request
CONTEXT_CHARS = 300  # neighbouring text sent as previous_text/next_text
MAX_PARALLEL_REQUESTS = (
    3  # deliberately low to stay well inside the API's concurrency limit
)
NETWORK_ATTEMPTS = 3
# Final files are re-encoded once (loudness normalisation); a bit above the 128k source
# keeps the second-generation encode transparent.
OUTPUT_BITRATE = "160k"
LOUDNORM_FILTER = (
    "loudnorm=I=-16:TP=-1.5:LRA=11"  # same perceived volume for every file
)
LOG_DIR = "generation_logs"
# Business-tier list price; the real cost depends on the subscription plan.
LIST_PRICE_USD_PER_1K_CHARS = 0.08
CHUNK_CACHE_DIR = ".chunk_cache"
RESUME_HINT = "💾 Already generated chunks are kept; run it again to resume without paying for them twice."

VOICES = {
    "David": "polm59PrdXp5lKpce2EG",
    "Max": "Gfpl8Yo74Is0W6cPUWWT",
    "Rachel": "21m00Tcm4TlvDq8ikWAM",
}

# Notes to script (Gemini free tier).
# Free-tier models change often; edit the names here only.
# Tried in order (quota or overload moves on to the next); ranking from a comparison on
# 2026-11-18, see docs/architecture.md. Free quotas are per model.
GEMINI_MODELS = ("gemini-3.8-flash", "gemini-4-hydrogen", "gemini-3.1-flash-lite")
GEMINI_TIMEOUT_MS = 180_000
GEMINI_RETRY_ATTEMPTS = 2  # 5xx only; 429 is not retried, the quota will not recover in seconds
MAX_NOTES_CHARS = 100_000
