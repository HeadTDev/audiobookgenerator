# Roadmap: ideas for students

Ideas for turning Audiobook Generator into a "notes in, audiobook out" study tool for
university students preparing for exams. Ranked by impact. Items marked *unverified*
depend on ElevenLabs features that have not been tested yet.

| # | Idea | Status |
|---|---|---|
| 1 | Notes to script with an LLM | **Done** (first slice: .txt/.md notes) |
| 2 | Pre-flight pronunciation check | **Done** |
| 3 | Synchronised transcript and chapters | Idea |
| 4 | Exam mode: question, pause, answer | Idea |
| 5 | Real credit balance from the ElevenLabs account | Idea |
| 6 | Better player: live speed, resume, skip | Idea |
| 7 | Phone export as M4B audiobook | Idea |
| 8 | Dialogue mode: teacher and student voices | Idea |
| 9 | Installable app for classmates | Idea |

## 1. Notes to script with an LLM (first slice done)

The "Notes → Script…" button turns a `.txt` or `.md` notes file into a narration script
with Gemini on the free tier (a Google AI Studio key, not Claude). One prompt carries the
pronunciation rules from [script-writing.md](script-writing.md); the reply goes through the
pre-flight check, and Gemini gets one repair round for the spots it flags. The result is
saved into the scripts folder as `_SCRIPT.md`. See `core/script_writer.py`.

Remaining: PDF, DOCX and PPTX input. Notes in other languages than Hungarian still get the
fixed Hungarian TTS language code.

## 2. Pre-flight pronunciation check (done)

Before anything is paid for, every script is scanned for notation the voice would misread
(slash, bracketed text, arrows, powers, subscripts, math symbols, code, tables, URLs).
Shown in the CHECK column, with a details dialog and a summary in the cost confirmation.
See `core/preflight.py`.

## 3. Synchronised transcript and chapters

While listening, highlight the sentence being read; click a sentence to jump to it. Turn
the script's sub-headings into a chapter list ("Hazards" → 7:42). Very effective for
learning. Possible with ElevenLabs' timestamped text-to-speech endpoint; whether Eleven v4
supports it is *unverified*.

## 4. Exam mode: question, pause, answer

Generate questions from each script, read one, leave time to think, then read the answer.
Active recall makes knowledge stick far better than passive listening.

## 5. Real credit balance from the ElevenLabs account

Replace the list-price estimate with real numbers: "This run uses ~120,000 credits,
380,000 left." The API has a subscription endpoint for this; the exact call is
*unverified*.

## 6. Better player

- Change playback speed live, without re-encoding the file.
- Remember the position per file and resume from there.
- ±15 second skip buttons.
- Mark files as "listened" in the list.

## 7. Phone export as M4B audiobook

One M4B audiobook per subject, with every topic as a chapter, playable in any audiobook
app. The whole subject on the go: commuting, at the gym.

## 8. Dialogue mode: teacher and student voices

Two voices, teacher and student: one asks, the other explains. Far less tiring to listen
to than a monologue. Possible with ElevenLabs Text to Dialogue.

## 9. Installable app for classmates

A single `.exe` (PyInstaller), with the API key entered in the UI instead of a `.env` file,
so classmates can use it without installing Python.
