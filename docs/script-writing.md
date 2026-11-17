# Writing scripts that Eleven v4 reads well

Write every script the way it should sound. The app does not rewrite notation; the
pre-flight check (CHECK column) points out what to fix before you pay.

These rules are condensed into `PROMPT_RULES` in `core/script_writer.py` (Notes → Script);
keep both in sync.

## Confirmed with Eleven v4 (tested with speech-to-text)

| Written | What v4 does | Write instead |
|---|---|---|
| `pozitív/negatív`, `Fully Connected / Dense` | reads the slash as "per" | `pozitív vagy negatív`, `Fully Connected vagy Dense` |
| `[MAR]`, `a[i]` | treats bracketed text as an audio tag and skips it | `a MAR címen lévő tartalom`, `a i-edik eleme` |
| `[serious]`, `[slowly]`, `[emphasizes]`, `[pauses]` | interprets them as delivery cues, does not read them | use freely, at the start of a sentence |
| Greek letters, indexes like `W1`, `τ(n+1)` | read naturally | fine as is |
| `ms` | read as "milliszekundum" | fine as is |

## Not verified: check by ear or write out

Arrows (`<-`, `->`, `=>`), powers (`p^n`), subscripts (`x_i`), math symbols
(`=`, `<`, `>`, `≤`), backticks, a single `*`, tables (`|`) and URLs. The safest form is
always words: "p az n-ediken", "x i-edik eleme", "MAR értéke legyen PC".

## Conventions

- Title line: `# MI12: Nagy nyelvi modellek - SCRIPT`. The heading becomes the MP3 title;
  ` - SCRIPT` is not read aloud.
- File name: `<ID>_<Short_Name>_SCRIPT.md`, e.g. `MI12_Nagy_Nyelvi_Modellek_SCRIPT.md`.
  The output is `MI12_Nagy_Nyelvi_Modellek.mp3`, track number 12.
- Folder: `<Subject>_Audiobook/Scripts/` gives the album name `<Subject>`.
- Pairs: `Publish-Subscribe`, `Train-Test`. Lists: `RNN, LSTM, GRU`.
- `**bold**` is removed before reading; headings are read as plain sentences.
