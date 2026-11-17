"""Worker tests with a fake ElevenLabs client: no paid calls. Merging needs FFmpeg."""
import json
import subprocess

import pytest

from audiobook_generator.core import config, worker
from audiobook_generator.core.text import output_name_for
from conftest import FakeElevenLabs, write_script


class Run:
    """Runs a GeneratorThread synchronously and records its signals."""

    def __init__(self, monkeypatch, fake, scripts, out, speed=1.0, stop_on_call=None):
        monkeypatch.setattr(worker, "ElevenLabs", fake)
        self.thread = worker.GeneratorThread("sk_test", [str(s) for s in scripts], str(out), "voice", speed)
        self.logs, self.statuses, self.progress = [], {}, []
        self.thread.log_msg.connect(self.logs.append)
        self.thread.file_status.connect(
            lambda path, state, detail: self.statuses.setdefault(path, []).append(state)
        )
        self.thread.progress.connect(lambda done, total: self.progress.append((done, total)))
        if stop_on_call:
            fake.on_call = lambda n: n == stop_on_call and self.thread.stop()
        self.thread.run()

    def final_states(self):
        return {path: states[-1] for path, states in self.statuses.items()}


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:format_tags:stream=sample_rate",
         "-of", "json", str(path)],
        capture_output=True, encoding="utf-8", check=True,  # ffprobe writes UTF-8
    )
    return json.loads(out.stdout)


def cache_files(out, suffix):
    return list((out / config.CHUNK_CACHE_DIR).rglob(f"*{suffix}"))


def test_never_more_than_three_requests_at_once(qapp, monkeypatch, tmp_path, tone_mp3):
    scripts = [write_script(tmp_path / "in", k) for k in range(1, 5)]  # 4 files x 3 chunks
    fake = FakeElevenLabs(tone_mp3, delay=0.1)
    run = Run(monkeypatch, fake, scripts, tmp_path)
    assert len(fake.calls) == 12
    assert fake.peak == config.MAX_PARALLEL_REQUESTS == 3
    assert set(run.final_states().values()) == {"done"}
    assert run.progress[-1] == (12, 12)
    assert all((tmp_path / output_name_for(s.name)).exists() for s in scripts)
    assert not (tmp_path / config.CHUNK_CACHE_DIR / "T1_Teszt").exists()  # cache cleared


def test_neighbouring_text_is_sent_as_context(qapp, monkeypatch, tmp_path, tone_mp3):
    fake = FakeElevenLabs(tone_mp3, delay=0)
    Run(monkeypatch, fake, [write_script(tmp_path / "in", 1)], tmp_path)
    first = next(c for c in fake.calls if c["text"].startswith("T1:"))
    assert "previous_text" not in first and "next_text" in first
    assert all(c["model_id"] == config.MODEL_ID and c["language_code"] == "hu" for c in fake.calls)


def test_stop_keeps_finished_chunks_and_leaves_no_partial_files(qapp, monkeypatch, tmp_path, tone_mp3):
    scripts = [write_script(tmp_path / "in", k) for k in range(1, 5)]
    fake = FakeElevenLabs(tone_mp3, delay=0.1)
    run = Run(monkeypatch, fake, scripts, tmp_path, stop_on_call=4)
    assert len(fake.calls) <= 6  # in-flight chunks finish, the queue is dropped
    assert cache_files(tmp_path, ".mp3") and not cache_files(tmp_path, ".part")
    assert "partial" in run.final_states().values()
    assert "done" not in run.final_states().values()


def test_failed_file_resumes_with_only_the_missing_chunk(qapp, monkeypatch, tmp_path, tone_mp3):
    scripts = [write_script(tmp_path / "in", k) for k in range(1, 5)]
    run = Run(monkeypatch, FakeElevenLabs(tone_mp3, fail_calls={2}), scripts, tmp_path)
    failed = [s for s in scripts if run.final_states()[str(s)] == "failed"]
    assert len(failed) == 1
    assert len(list(tmp_path.glob("*.mp3"))) == 3  # the other files still merged

    retry = FakeElevenLabs(tone_mp3)
    Run(monkeypatch, retry, failed, tmp_path)
    assert len(retry.calls) == 1
    assert (tmp_path / output_name_for(failed[0].name)).exists()


@pytest.mark.parametrize("speed", [1.0, 1.2])
def test_merged_file_format_tags_and_speed(qapp, monkeypatch, tmp_path, tone_mp3, speed):
    script = write_script(tmp_path / "Proba_Audiobook" / "Scripts", 3)
    Run(monkeypatch, FakeElevenLabs(tone_mp3, delay=0), [script], tmp_path, speed=speed)
    info = probe(tmp_path / output_name_for(script.name))
    tags = {k.lower(): v for k, v in info["format"]["tags"].items()}
    assert info["streams"][0]["sample_rate"] == "44100"
    assert tags["title"] == "T3: Teszt cím" and tags["album"] == "Proba" and tags["track"] == "3"
    assert float(info["format"]["duration"]) == pytest.approx(3.0 / speed, abs=0.15)
