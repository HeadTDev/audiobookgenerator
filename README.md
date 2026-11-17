# Audiobook Generator

![Logo](docs/images/logo_preview.png)

Turns Markdown scripts (`*_SCRIPT.md`) into MP3 audiobooks with ElevenLabs (Eleven v4):
parallel generation, resumable runs, a pre-flight pronunciation check, loudness-normalised
and tagged MP3s, and a built-in player with a clickable waveform.

## Setup on a new machine

1. Install Python 3.11+ and [FFmpeg](https://ffmpeg.org/) (FFmpeg must be on `PATH`, e.g. `winget install ffmpeg`).
2. Install the dependencies:

   ```
   pip install -r requirements.txt
   ```

   On Windows ARM64 with Python 3.14, use `pip install --only-binary=cryptography -r requirements.txt`
   (the latest `cryptography` release has no wheel there; 46.x does).

3. Copy `.env.example` to `.env` and set `ELEVENLABS_API_KEY`. Optional: set `GEMINI_API_KEY`
   (free key from [aistudio.google.com](https://aistudio.google.com)) for Notes → Script.

## Run

```
python run.py
```

The whole program lives in this folder; copy the folder to use it elsewhere.
Never share or commit the `.env` file, it holds the API key.

Optional: `pip install -e .` installs the package with an `audiobook-generator` command.

## Notes → Script

The sidebar button "Notes → Script…" writes a narration script from a `.txt` or `.md` notes
file with Gemini and saves it into the scripts folder as `<name>_SCRIPT.md` (an existing file
is never overwritten). The result is pre-flight checked once and fixed once; what is left
shows in the CHECK column. Keep the notes outside the scripts folder, otherwise they would
be listed as scripts. Free tier: Google may use the notes to improve its products.

## Develop

```
pip install -e ".[dev]"
python -m pytest
ruff check .
```

Tests run offscreen in seconds, use a fake ElevenLabs client (no paid requests) and never
read the real `.env`; a fake Gemini client covers Notes → Script.

## Layout

```
AudiobookGenerator/
├── run.py                      start the app (no install needed)
├── src/                        code container, kept apart from tests, docs and config
│   └── audiobook_generator/    the Python package; the folder name is the import name
│       ├── app.py              application entry point
│       ├── core/               engine: config, text, preflight, script_writer, worker
│       └── ui/                 Qt: main window, player, theme, assets
├── tests/                      pytest suite
├── docs/                       architecture, script-writing guide, images
├── pyproject.toml              package metadata, ruff/pytest/pyright settings
├── requirements.txt            runtime dependencies
└── .env / .env.example         API key (never commit .env)
```

## Docs

- [Architecture](docs/architecture.md): modules, generation pipeline, cache, threading.
- [Writing scripts](docs/script-writing.md): what Eleven v4 reads well and what to avoid.
- [Roadmap](docs/roadmap.md): ideas for students, ranked by impact.
