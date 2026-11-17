"""Shared fixtures. Tests never call the real API, never read the real .env and never
touch the user's saved settings."""
import os
import shutil
import subprocess
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # before any Qt import


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="session")
def tone_mp3(tmp_path_factory):
    """One second of sine tone as MP3 bytes; skips the test when FFmpeg is missing."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is not on PATH")
    path = tmp_path_factory.mktemp("tone") / "tone.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=1",
         "-ar", "44100", "-b:a", "128k", str(path)],
        check=True,
    )
    return path.read_bytes()


def write_script(folder, number, lines=5, title="Teszt"):
    """A script that splits into 3 chunks of the 5000-character limit by default."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"T{number}_{title}_SCRIPT.md"
    body = "\n".join(f"Mondat {i}. " + "x" * 1900 for i in range(lines))
    path.write_text(f"# T{number}: {title} cím - SCRIPT\n\n[serious] {body}\n", encoding="utf-8")
    return path


class FakeElevenLabs:
    """Stands in for elevenlabs.client.ElevenLabs; records calls and peak concurrency."""

    def __init__(self, audio, delay=0.05, fail_calls=(), on_call=None):
        self.audio = audio
        self.delay = delay
        self.fail_calls = set(fail_calls)
        self.on_call = on_call
        self.calls = []
        self.current = self.peak = 0
        self._lock = threading.Lock()
        self.text_to_speech = self

    def __call__(self, **kwargs):  # used as the client constructor
        return self

    def convert(self, **kwargs):
        from elevenlabs.core.api_error import ApiError

        with self._lock:
            self.calls.append(kwargs)
            number = len(self.calls)
            self.current += 1
            self.peak = max(self.peak, self.current)
        try:
            if self.on_call:
                self.on_call(number)
            time.sleep(self.delay)
            if number in self.fail_calls:
                raise ApiError(status_code=400, body="simulated failure")
            return iter([self.audio])
        finally:
            with self._lock:
                self.current -= 1
