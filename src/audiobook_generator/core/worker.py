"""Background thread that generates the audio files."""
import hashlib
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from elevenlabs.client import ElevenLabs
from elevenlabs.core.api_error import ApiError
from PySide6.QtCore import QThread, Signal

from .config import (
    CHUNK_CACHE_DIR,
    CONTEXT_CHARS,
    LANGUAGE_CODE,
    LOUDNORM_FILTER,
    MAX_PARALLEL_REQUESTS,
    MODEL_ID,
    NETWORK_ATTEMPTS,
    OUTPUT_BITRATE,
    OUTPUT_FORMAT,
    RESUME_HINT,
)
from .text import audio_metadata_for, create_chunks, output_name_for


class GeneratorThread(QThread):
    """Generates the selected scripts. All signals are emitted from this thread's run()."""

    log_msg = Signal(str)
    progress = Signal(int, int)  # chunks done, chunks total
    eta_update = Signal(int)  # seconds left
    # script path, state, detail. States: queued, generating, merging, done, failed, partial
    file_status = Signal(str, str, str)
    done = Signal(bool, str)

    def __init__(self, api_key, script_files, output_folder, voice_id, speed):
        super().__init__()
        self.api_key = api_key
        self.script_files = script_files
        self.output_folder = output_folder
        self.voice_id = voice_id
        self.speed = speed
        self._is_running = True

    def stop(self):
        self._is_running = False

    def _sleep_while_running(self, seconds):
        deadline = time.monotonic() + seconds
        while self._is_running and time.monotonic() < deadline:
            time.sleep(0.1)

    def _chunk_path(self, cache_dir, index, chunk_text):
        # The hash covers everything that changes the audio, so an edited script or a
        # different voice/model never reuses a stale cached chunk.
        key = f"{MODEL_ID}|{self.voice_id}|{OUTPUT_FORMAT}|{LANGUAGE_CODE}|{chunk_text}"
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return os.path.join(cache_dir, f"{index:04d}_{digest}.mp3")

    def _synthesize(self, client, text, previous_text, next_text):
        # The SDK already retries HTTP 408/409/429/5xx; this loop only covers network
        # failures, which can also surface while the audio stream is being read.
        context = {}
        if previous_text:
            context["previous_text"] = previous_text
        if next_text:
            context["next_text"] = next_text

        attempt = 1
        while True:
            try:
                audio = client.text_to_speech.convert(
                    voice_id=self.voice_id,
                    text=text,
                    model_id=MODEL_ID,
                    language_code=LANGUAGE_CODE,
                    output_format=OUTPUT_FORMAT,
                    **context,
                )
                data = b"".join(audio)
                if not data:
                    raise RuntimeError("The API returned empty audio.")
                return data
            except httpx.TransportError as e:
                if attempt == NETWORK_ATTEMPTS or not self._is_running:
                    raise
                wait = 2**attempt
                self.log_msg.emit(
                    f"🔁 Network error ({type(e).__name__}), retrying in {wait}s..."
                )
                self._sleep_while_running(wait)
                if not self._is_running:
                    raise  # stopped during backoff: don't send (and pay for) another request
                attempt += 1

    def _generate_chunk(self, client, job, index):
        """Runs on a pool thread. Returns True if the chunk was generated and saved."""
        if not self._is_running:
            return False
        chunks = job["chunks"]
        # Neighbouring text keeps intonation continuous across chunk boundaries;
        # it is context only and is not spoken.
        previous_text = chunks[index - 1][-CONTEXT_CHARS:] if index > 0 else ""
        next_text = chunks[index + 1][:CONTEXT_CHARS] if index + 1 < len(chunks) else ""
        data = self._synthesize(client, chunks[index], previous_text, next_text)

        chunk_path = job["paths"][index]
        part_path = chunk_path + ".part"
        with open(part_path, "wb") as f:
            f.write(data)
        os.replace(part_path, chunk_path)
        return True

    def _merge_chunks(self, job, output_file):
        # Concat demuxer instead of appending raw bytes: rewrites the MP3 headers so
        # players show the correct duration and seek properly. Chunk names are bare
        # basenames, resolved relative to the list file's own folder.
        list_path = os.path.join(job["cache_dir"], "concat.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            f.writelines(f"file '{os.path.basename(p)}'\n" for p in job["paths"])

        filters = [f"atempo={self.speed}"] if self.speed != 1.0 else []
        filters.append(LOUDNORM_FILTER)
        part_file = output_file + ".part.mp3"
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
        cmd += ["-f", "concat", "-safe", "0", "-i", list_path]
        cmd += ["-filter:a", ",".join(filters)]
        # loudnorm upsamples internally, so the output rate must be set explicitly.
        cmd += ["-ar", "44100", "-c:a", "libmp3lame", "-b:a", OUTPUT_BITRATE]
        cmd += ["-map_metadata", "-1", "-id3v2_version", "3"]
        for key, value in job["metadata"].items():
            cmd += ["-metadata", f"{key}={value}"]
        cmd.append(part_file)

        try:
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            os.replace(part_file, output_file)
        finally:
            if os.path.exists(part_file):
                os.remove(part_file)

    def _set_status(self, job, state, detail=""):
        job["state"] = state
        self.file_status.emit(job["script_file"], state, detail)

    def _chunk_count_detail(self, job):
        return f"{job['done_chunks']}/{len(job['chunks'])}"

    def _finish_job(self, job):
        """Merge a job whose chunks are all on disk; errors are logged, not raised."""
        out_name = job["out_name"]
        try:
            speed_note = f" at {self.speed}x speed" if self.speed != 1.0 else ""
            self._set_status(job, "merging")
            self.log_msg.emit(f"🔗 Merging {out_name} with FFmpeg{speed_note}...")
            self._merge_chunks(job, os.path.join(self.output_folder, out_name))
            shutil.rmtree(job["cache_dir"], ignore_errors=True)
            self._set_status(job, "done")
            self.log_msg.emit(f"✅ Success! File completed: {out_name}")
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
            self._set_status(job, "failed", "FFmpeg error")
            self.log_msg.emit(f"❌ FFmpeg error on {out_name}: {err_msg}")
            self.log_msg.emit(RESUME_HINT)
        except OSError as e:
            self._set_status(job, "failed", "File error")
            self.log_msg.emit(f"❌ File error on {out_name}: {e}")
            self.log_msg.emit(RESUME_HINT)

    def _describe_error(self, e):
        if isinstance(e, ApiError):
            return f"API error (HTTP {e.status_code}): {e.body}"
        if isinstance(e, httpx.TransportError):
            return f"Network error: {type(e).__name__}: {e}"
        if isinstance(e, OSError):
            return f"File error: {e}"
        return f"Unexpected error: {e!r}"

    def _prepare_jobs(self):
        jobs = []
        for script_file in self.script_files:
            if not self._is_running:
                break
            with open(script_file, "r", encoding="utf-8") as f:
                text = f.read()
            chunks = create_chunks(text)
            if not chunks:
                self.file_status.emit(script_file, "failed", "No readable text")
                continue
            base_name = os.path.basename(script_file)
            out_name = output_name_for(base_name)
            cache_dir = os.path.join(
                self.output_folder, CHUNK_CACHE_DIR, os.path.splitext(out_name)[0]
            )
            paths = [self._chunk_path(cache_dir, i, c) for i, c in enumerate(chunks)]
            os.makedirs(cache_dir, exist_ok=True)
            pending = [i for i, p in enumerate(paths) if not os.path.exists(p)]
            job = {
                "script_file": script_file,
                "out_name": out_name,
                "cache_dir": cache_dir,
                "chunks": chunks,
                "paths": paths,
                "pending": pending,
                "done_chunks": len(chunks) - len(pending),
                "metadata": audio_metadata_for(script_file, text),
                "failed": False,
            }
            self._set_status(job, "queued", self._chunk_count_detail(job))
            jobs.append(job)
        return jobs

    def run(self):
        try:
            if not self.api_key:
                raise ValueError("ELEVENLABS_API_KEY is not set in .env")

            self.log_msg.emit("🔄 Analyzing and preparing files...")
            client = ElevenLabs(api_key=self.api_key)
            jobs = self._prepare_jobs()

            if not jobs:
                if self._is_running:
                    self.done.emit(
                        False, "None of the selected files contain readable text!"
                    )
                return

            total_chunks = sum(len(job["chunks"]) for job in jobs)
            pending_chunks = sum(len(job["pending"]) for job in jobs)
            self.log_msg.emit(
                f"🌐 {len(jobs)} files, {total_chunks} chunks: {pending_chunks} to generate "
                f"({MAX_PARALLEL_REQUESTS} at a time), "
                f"{total_chunks - pending_chunks} already cached from an earlier run."
            )
            chunks_done = total_chunks - pending_chunks
            self.progress.emit(chunks_done, total_chunks)

            # Files with nothing left to generate are merged right away.
            for job in jobs:
                if not job["pending"] and self._is_running:
                    self._finish_job(job)

            generated = 0
            started = time.monotonic()
            pool = ThreadPoolExecutor(max_workers=MAX_PARALLEL_REQUESTS)
            try:
                futures = {}
                for job in jobs:
                    for index in job["pending"]:
                        future = pool.submit(self._generate_chunk, client, job, index)
                        futures[future] = (job, index)
                remaining_per_job = {id(job): len(job["pending"]) for job in jobs}

                # All bookkeeping happens here, on this thread, so no locks are needed.
                for future in as_completed(futures):
                    if not self._is_running:
                        break
                    job, index = futures[future]
                    remaining_per_job[id(job)] -= 1
                    try:
                        if future.result():
                            generated += 1
                            chunks_done += 1
                            job["done_chunks"] += 1
                            if not job["failed"]:
                                self._set_status(
                                    job, "generating", self._chunk_count_detail(job)
                                )
                            self.log_msg.emit(
                                f"🎙️ {job['out_name']}: chunk {index + 1}/{len(job['chunks'])} done."
                            )
                    except Exception as e:
                        if not job["failed"]:
                            self._set_status(job, "failed", "Chunk failed")
                            self.log_msg.emit(
                                f"❌ {job['out_name']}: chunk {index + 1} failed. {self._describe_error(e)}"
                            )
                            self.log_msg.emit(RESUME_HINT)
                        job["failed"] = True

                    self.progress.emit(chunks_done, total_chunks)
                    if generated:
                        elapsed = time.monotonic() - started
                        self.eta_update.emit(
                            int(elapsed / generated * (pending_chunks - generated))
                        )

                    job_complete = remaining_per_job[id(job)] == 0 and not job["failed"]
                    if job_complete and self._is_running:
                        self._finish_job(job)
            finally:
                # On Stop, queued chunks are dropped; chunks already in flight finish and
                # are kept in the cache.
                pool.shutdown(wait=True, cancel_futures=True)

            for job in jobs:
                if job.get("state") not in ("done", "failed"):
                    # Stopped before this file was merged; its chunks stay cached.
                    self._set_status(job, "partial", self._chunk_count_detail(job))

            if self._is_running:
                self.progress.emit(total_chunks, total_chunks)
                self.done.emit(True, "All selected files have been processed! 🎉")
            else:
                self.done.emit(False, f"🛑 Generation stopped by user.\n{RESUME_HINT}")

        except Exception as e:
            self.log_msg.emit(f"❌ ERROR OCCURRED:\n{e!r}")
            self.done.emit(False, str(e))
