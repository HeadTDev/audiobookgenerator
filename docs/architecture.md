# Architecture

## Layout

```
src/audiobook_generator/
├── app.py              QApplication, window icon, Windows taskbar identity
├── core/               generation engine (no widgets)
│   ├── config.py       models, voices, limits, .env loading (ELEVENLABS_API_KEY, GEMINI_API_KEY, GEMINI_MODEL)
│   ├── text.py         script cleaning, chunking, output names, MP3 tags
│   ├── preflight.py    notation the voice would misread
│   ├── script_writer.py  notes to script with Gemini: prompt, repair round, thread
│   └── worker.py       GeneratorThread: parallel requests, cache, FFmpeg merge
└── ui/                 Qt widgets
    ├── main_window.py  file table, sidebar, progress, log, settings
    ├── player.py       player bar with clickable waveform
    ├── theme.py        palette, style sheet, drawn icons, logo
    └── assets/logo.svg
```

`core` never imports from `ui`. `.env` lives in the app root, next to `run.py`
(`config.APP_ROOT`).

## Text pipeline

`clean_line` turns one Markdown line into its spoken form: it drops `**` and heading
markers, removes the ` - SCRIPT` title suffix and skips lines without letters or digits.
Square brackets are kept, because Eleven v4 interprets `[serious]`-style audio tags.
Both `clean_markdown_text` and the pre-flight check use `clean_line`, so the check sees
exactly what is sent and reports real line numbers.

`create_chunks` packs lines into chunks of at most `MAX_CHUNK_CHARS` (5000; v4 accepts
10,000). A longer line is split at sentence ends, or at spaces as a last resort.

## Generation (`core/worker.py`)

`GeneratorThread.run()` owns all bookkeeping and emits every signal; pool threads only
call the API and write chunk files.

1. **Prepare.** Every selected script is chunked. Each chunk gets a cache path
   `<output>/.chunk_cache/<file>/<index>_<hash>.mp3`. The hash covers model, voice,
   output format, language and chunk text, so an edited script or a different voice never
   reuses a stale chunk. Chunks already on disk are skipped and not billed again.
2. **Generate.** Pending chunks of all files go to one `ThreadPoolExecutor` with
   `MAX_PARALLEL_REQUESTS = 3`, which keeps load on the API low. Each request carries up to
   300 characters of the neighbouring chunks as `previous_text` / `next_text` for
   continuous intonation. The SDK retries HTTP 408/409/429/5xx; the worker additionally
   retries network errors with backoff and never retries after Stop.
3. **Merge.** When all chunks of a file exist, FFmpeg concatenates them (concat demuxer),
   applies `atempo` for the speed setting and `loudnorm`, writes 44.1 kHz / 160 kbps MP3
   with title, album and track tags to a `.part.mp3` file, then `os.replace`s it into
   place. The file's cache folder is deleted only after a successful merge.

**Stop:** queued chunks are dropped, the up to 3 in-flight chunks finish and are cached.
**Failure:** the file is marked failed, its other chunks are still cached, and the next run
generates only what is missing.

Signals: `log_msg`, `progress(done, total)`, `eta_update(seconds)`,
`file_status(path, state, detail)` with states queued, generating, merging, done, failed
and partial, and `done(success, message)`.

## Notes to script (`core/script_writer.py`)

`ScriptWriterThread` (same shape as `GeneratorThread`: `log_msg`, `done(success, message,
path)`) reads a `.txt`/`.md` file (UTF-8, cp1250 fallback; capped at `MAX_NOTES_CHARS`) and
calls Gemini once. The prompt is embedded in code (`PROMPT_RULES`), because `docs/` is not
shipped with the package; it condenses [script-writing.md](script-writing.md). The reply is
checked with `check_script`; on issues, one repair call sends them back in a multi-turn
conversation. The repair is kept only if it has no more MISREAD/CHECK issues and is not
suspiciously shorter (a truncated rewrite). The script is saved as `<stem>_SCRIPT.md`,
`<stem>_2_SCRIPT.md` and so on on a name clash, never overwriting. The SDK retries 5xx
only; 429 is reported at once. `describe_error` maps refusals, quota, key, model and network
failures to user-facing messages.

## UI notes

- The file table sorts once per header click (live sorting is off), so status updates
  never reorder rows during a run.
- Before a run the player releases the loaded MP3: Windows locks open files, and the final
  `os.replace` would fail. Rows being regenerated cannot be played during the run.
- Settings (folders, voice, speed, window, log visibility) are stored with `QSettings`
  (Windows registry, `HKCU\Software\AudiobookGenerator`).
- The waveform is decoded with FFmpeg on a background thread (RMS envelope, 600 points).

## Tests

`python -m pytest` runs offscreen in a few seconds. A fake ElevenLabs client and a fake Gemini
client replace the SDKs, so no request is ever paid; tests use temporary folders and settings and never read
the real `.env`. Tests that need FFmpeg are skipped when it is not on `PATH`.
