# Roadmap: ideas for students

Ideas for turning Audiobook Generator into a "notes in, audiobook out" study tool for
university students preparing for exams. Ranked by impact. Items marked *unverified*
depend on ElevenLabs features that have not been tested yet.

| # | Idea | Status |
|---|---|---|
| 1 | Notes to script with an LLM | Idea |
| 2 | Pre-flight pronunciation check | **Done** |
| 3 | Synchronised transcript and chapters | Idea |
| 4 | Exam mode: question, pause, answer | Idea |
| 5 | Real credit balance from the ElevenLabs account | Idea |
| 6 | Better player: live speed, resume, skip | Idea |
| 7 | Phone export as M4B audiobook | Idea |
| 8 | Dialogue mode: teacher and student voices | Idea |
| 9 | Installable app for classmates | Idea |

## 1. Notes to script with an LLM

Today scripts have to be written in advance. The app could take lecture notes, PDFs, DOCX
files or slide decks and turn them into narration-ready scripts with an LLM (for example
Claude). The pronunciation rules from [script-writing.md](script-writing.md) go straight
into the prompt: no slashes, formulas spelled out in words, brackets only for audio tags.
This is the step that turns the app into "notes in, audiobook out".

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
