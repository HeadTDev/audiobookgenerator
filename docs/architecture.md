# Architecture

## Layout

```
src/audiobook_generator/
├── app.py              QApplication, window icon, Windows taskbar identity
├── core/               generation engine (no widgets)
│   ├── config.py       models, voices, limits, .env loading (ELEVENLABS_API_KEY, GEMINI_API_KEY, GEMINI_MODELS)
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
calls Gemini. The prompt is embedded in code (`PROMPT_RULES`), because `docs/` is not
shipped with the package; it condenses [script-writing.md](script-writing.md). The reply is
checked with `check_script`; on issues, one repair call sends them back in a multi-turn
conversation. The repair is kept only if it has no more MISREAD/CHECK issues and is not
suspiciously shorter (a truncated rewrite). The repair always runs on the model that wrote the
first draft, and if the repair call fails for any reason the first draft is kept. The script is saved as `<stem>_SCRIPT.md`,
`<stem>_2_SCRIPT.md` and so on on a name clash, never overwriting. The SDK retries 5xx
only; 429 is not retried by the SDK. `describe_error` maps refusals, quota, key, model and
network failures to user-facing messages.

Model chain: `GEMINI_MODELS` is tried in order for the first draft, because free-tier quotas
are per model and models return 503 for long stretches. Fallback errors (next model): HTTP 429
and 404, 5xx after the SDK retries, read/write/pool timeouts. Not fallback (reported at once):
400/401/403 (same key for every model), connection errors (network down, including connect
timeouts) and `ScriptWriterError` (refusal, `MAX_TOKENS`, empty reply). All models failing
raises "All Gemini models failed". `ScriptResult.model` is the model that wrote the kept text.
The thread passes `isInterruptionRequested` as `should_stop`, so closing the window waits for
at most one call in flight.

### Model choice (2026-11-18)

Tested on one 3k-char Hungarian OS note, one run each:

1. `gemini-3.8-flash`: best language and explanations; frequent 503 at peak.
2. `gemini-4-hydrogen`: most faithful, but ~100 s and over-expands abbreviations.
3. `gemini-3.1-flash-lite`: fast, 500 requests/day, plainer, wrote "I per O".

Excluded: `gemini-3.5-flash-lite` (garbled Hungarian words that the pre-flight cannot catch),
`gemini-2.5-flash-lite` (404 for new users), `gemini-3.6-flash` (only 503s, untested).

## UI notes

- The file table sorts once per header click (live sorting is off), so status updates
  never reorder rows during a run.
- Before a run the player releases the loaded MP3: Windows locks open files, and the final
  `os.replace` would fail. Rows being regenerated cannot be played during the run.
- Settings (folders, voice, speed, window, log visibility) are stored with `QSettings`
  (Windows registry, `HKCU\Software\AudiobookGenerator`).
- Player: positions live in one `QSettings` value, `player/positions`, a JSON map
  `path -> {pos, mtime, listened}` (paths are not used as keys: `/` and `\` are group
  separators). Entries whose file is gone or has a different mtime are dropped. The position
  is read from `player.position()` before `stop()` / `setSource()` and on pause, never from
  `positionChanged`, because stopping or switching source emits `positionChanged(0)`. A resume
  position is applied on `LoadedMedia`, since a seek right after `setSource` may be ignored.
  `EndOfMedia` sets the listened flag.
- The waveform is decoded with FFmpeg on a background thread (RMS envelope, 600 points).

## Tests

`python -m pytest` runs offscreen in a few seconds. A fake ElevenLabs client and a fake Gemini
client replace the SDKs, so no request is ever paid; tests use temporary folders and settings and never read
the real `.env`. Tests that need FFmpeg are skipped when it is not on `PATH`.
