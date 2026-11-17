"""Generation settings, voices, and the API key loader (.env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

# App root = the folder holding run.py and .env (core -> audiobook_generator -> src -> root).
# The secret lives in .env there, never in the code.
APP_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = str(APP_ROOT / ".env")
API_KEY_VAR = "ELEVENLABS_API_KEY"


def load_api_key():
    """Read the key fresh from .env, so editing .env needs no app restart. '' if unset."""
    load_dotenv(ENV_PATH, override=True)
    return os.environ.get(API_KEY_VAR, "").strip()


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
