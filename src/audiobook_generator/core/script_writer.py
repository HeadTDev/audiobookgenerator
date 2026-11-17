"""Notes to script: turns lecture notes into a narration script with Gemini (free tier).

The pronunciation rules live in PROMPT_RULES (condensed from docs/script-writing.md, keep
both in sync) and are embedded in code, because docs/ is not shipped with the package.
The reply goes through the pre-flight check; if it finds problems, Gemini gets exactly
one chance to fix them.
"""
import os
import re
from dataclasses import dataclass

from google import genai
from google.genai import errors, types
from PySide6.QtCore import QThread, Signal

from .config import (
    GEMINI_MODEL,
    GEMINI_RETRY_ATTEMPTS,
    GEMINI_TIMEOUT_MS,
    MAX_NOTES_CHARS,
)
from .preflight import Issue, check_script, count_by_severity

MAX_REPAIR_LINES = 50
MIN_REPAIR_LENGTH_RATIO = 0.8  # a shorter rewrite is assumed to be truncated
REFUSAL_REASONS = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}
INVALID_FILE_CHARS = re.compile(r'[<>:"/\\|?*]')
NOTES_TITLE_REGEX = re.compile(r"^#[ \t]+(.+?)[ \t]*$", re.MULTILINE)

# Each rule matches what core/preflight.py reports. Greek letters, indexes like W1 and
# "ms" are read fine by Eleven v4, so they are explicitly allowed.
PROMPT_RULES = """\
You write narration scripts. A script is read aloud by an ElevenLabs Eleven v4 text-to-speech voice to a university student who is preparing for an exam, so write the way it should sound.

LANGUAGE
- Write in the same language as the notes. Never translate. Keep established English technical terms as they are.

CONTENT
- Cover everything in the notes. Invent no facts and add nothing the notes do not support.
- Turn bullet points and tables into flowing spoken sentences.
- Explain every abbreviation at its first use.
- Use short transitions between topics.

FORMAT
- The first line is the title: `# <ID>: <Title> - SCRIPT`, for example `# MI12: Nagy nyelvi modellek - SCRIPT`. Use the ID from the notes if there is one, otherwise make a short one from the title.
- Optional sub-headings start with `## `.
- Everything else is plain paragraphs. No lists, no tables, no code blocks, no `**` bold.
- Write pairs with a hyphen (`Train-Test`, `Publish-Subscribe`) and lists with commas (`RNN, LSTM, GRU`).

PRONUNCIATION (the voice misreads written notation, so spell it out in words)
- Never write a slash. Write "vagy", "és" or "per" instead: `pozitív vagy negatív`, not `pozitív/negatív`.
- Square brackets are only for these audio tags: [serious] [slowly] [emphasizes] [pauses]. Put one at the start of a sentence, and use them sparingly. Any other bracketed text is swallowed silently, so never write `[MAR]` or `a[i]`; write "a MAR címen lévő tartalom", "az a tömb i-edik eleme".
- Write formulas, powers, subscripts, arrows and math symbols (= < > ≤ ≥ ≠ ± × ÷ √ ∑ ∫ ∞) out in words: `p^n` becomes "p az n-ediken", `x_i` becomes "x i-edik eleme", `->` becomes "ebből következik" or similar.
- Never use backticks, a single `*`, the `|` character or URLs.
- Greek letters, indexes like W1 and units like ms are fine as they are.

OUTPUT
- Output only the script as Markdown. No preamble, no closing remarks, no code fence."""


class ScriptWriterError(Exception):
    """str(e) is the message shown to the user."""


@dataclass
class ScriptResult:
    text: str
    issues: list[Issue]  # pre-flight issues left in `text`
    repaired: bool  # True when the repair round's answer was kept


def read_notes(path):
    """The notes as text (UTF-8, falling back to the Windows Central European codepage)."""
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1250", errors="replace")
    text = text.strip()
    if not text:
        raise ScriptWriterError("The notes file is empty.")
    if len(text) > MAX_NOTES_CHARS:
        raise ScriptWriterError(
            f"The notes are too long ({len(text):,} characters, the limit is "
            f"{MAX_NOTES_CHARS:,}). Split the notes into smaller files."
        )
    return text


def build_system_prompt():
    return PROMPT_RULES


def build_user_prompt(notes_text, notes_name):
    match = NOTES_TITLE_REGEX.search(notes_text)
    title = match.group(1) if match else os.path.splitext(notes_name)[0]
    return f"Notes file: {notes_name}\nSuggested title: {title}\n<<<NOTES\n{notes_text}\nNOTES>>>"


def build_repair_prompt(issues):
    seen = set()
    lines = []
    for issue in issues:
        found = issue.text[issue.start : issue.end]
        key = (issue.line, found)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f'- Line {issue.line}: "{found}": {issue.message}')
        if len(lines) == MAX_REPAIR_LINES:
            break
    return (
        "The pronunciation check found problems in your script. Fix only these spots, "
        "keep everything else unchanged, and return the complete corrected script.\n"
        + "\n".join(lines)
    )


def _turn(role, text):
    return types.Content(role=role, parts=[types.Part(text=text)])


def _enum_name(value):
    """finish_reason / block_reason may be an enum or a plain string."""
    return str(getattr(value, "name", value))


def _strip_fence(text):
    text = text.strip()
    if text.startswith("```") and text.endswith("```") and len(text) >= 6:
        body = text[3:-3]
        newline = body.find("\n")  # drops the language tag after the opening fence
        text = body[newline + 1 :] if newline != -1 else body
    return text.strip()


def _generate(client, contents):
    """One Gemini call; the script text, or ScriptWriterError for refusals and bad replies."""
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=build_system_prompt(), temperature=0.4),
    )
    refused = "Gemini refused the notes ({})."
    feedback = getattr(response, "prompt_feedback", None)
    block_reason = getattr(feedback, "block_reason", None)
    if block_reason:
        raise ScriptWriterError(refused.format(_enum_name(block_reason)))
    candidates = getattr(response, "candidates", None) or []
    finish = _enum_name(candidates[0].finish_reason) if candidates and candidates[0].finish_reason else ""
    if finish in REFUSAL_REASONS:
        raise ScriptWriterError(refused.format(finish))
    if finish == "MAX_TOKENS":
        raise ScriptWriterError("The script was cut off: the notes are too long. Split them into smaller files.")
    text = _strip_fence(response.text or "")
    if not text:
        raise ScriptWriterError("Gemini returned an empty response.")
    return text


def notes_to_script(client, notes_text, notes_name, log=lambda m: None):
    """Script for the notes, with at most one repair round driven by the pre-flight check."""
    contents = [_turn("user", build_user_prompt(notes_text, notes_name))]
    first = _generate(client, contents)
    first_issues = check_script(first)
    if not first_issues:
        return ScriptResult(first, [], False)

    log(f"🔧 Pre-flight found {len(first_issues)} issue(s), asking Gemini to fix them once…")
    contents += [_turn("model", first), _turn("user", build_repair_prompt(first_issues))]
    second = _generate(client, contents)
    second_issues = check_script(second)
    not_worse = count_by_severity(second_issues) <= count_by_severity(first_issues)  # MISREAD first
    complete = len(second) >= MIN_REPAIR_LENGTH_RATIO * len(first)
    if not_worse and complete:
        return ScriptResult(second, second_issues, True)
    return ScriptResult(first, first_issues, False)


def script_path_for(notes_path, scripts_folder):
    """`<stem>_SCRIPT.md` in the scripts folder; `<stem>_2_SCRIPT.md`, ... when taken."""
    stem = os.path.splitext(os.path.basename(notes_path))[0]
    stem = INVALID_FILE_CHARS.sub("", re.sub(r"\s+", "_", stem.strip())).strip("._")
    if stem.upper().endswith("_SCRIPT"):
        stem = stem[: -len("_SCRIPT")]
    stem = stem or "script"
    path = os.path.join(scripts_folder, f"{stem}_SCRIPT.md")
    number = 2
    while os.path.exists(path):  # "_SCRIPT" stays last so text.output_name_for still works
        path = os.path.join(scripts_folder, f"{stem}_{number}_SCRIPT.md")
        number += 1
    return path


def save_script(text, path):
    """Writes a new file; never overwrites an existing one."""
    with open(path, "x", encoding="utf-8") as f:
        f.write(text.rstrip("\n") + "\n")


def describe_error(e):
    if isinstance(e, ScriptWriterError):
        return str(e)
    if isinstance(e, errors.ClientError):
        if e.code == 429:
            return (
                "Gemini limit reached. Wait a minute and try again; if it keeps failing, the daily "
                "free quota is used up (it resets around 9:00 Hungarian time)."
            )
        if e.code in (401, 403) or (e.code == 400 and "API key not valid" in str(e.message)):
            return "Gemini rejected the API key. Check GEMINI_API_KEY in .env."
        if e.code == 404:
            return f"Model '{GEMINI_MODEL}' not found. Free-tier models change; update GEMINI_MODEL in core/config.py."
        return f"Gemini error (HTTP {e.code} {e.status}): {e.message}"
    if isinstance(e, errors.ServerError):
        return "Gemini is overloaded or unavailable. Try again later."
    # The SDK's HTTP transport is not httpx proper, so match by package instead of importing it.
    if type(e).__module__.split(".")[0] in ("httpx", "httpx2") or isinstance(e, (ConnectionError, TimeoutError)):
        return "Network error: check the internet connection."
    if isinstance(e, OSError):
        return f"File error: {e}"
    return f"Unexpected error: {e!r}"


class ScriptWriterThread(QThread):
    """Writes one script from a notes file. All signals are emitted from this thread's run()."""

    log_msg = Signal(str)
    done = Signal(bool, str, str)  # success, message, saved path ('' on failure)

    def __init__(self, api_key, notes_path, scripts_folder):
        super().__init__()
        self.api_key = api_key
        self.notes_path = notes_path
        self.scripts_folder = scripts_folder

    def run(self):
        try:
            if not self.api_key:
                raise ScriptWriterError("GEMINI_API_KEY is not set in .env (free key: aistudio.google.com).")
            notes_name = os.path.basename(self.notes_path)
            notes_text = read_notes(self.notes_path)
            self.log_msg.emit(f"✍️ Writing script from {notes_name} with {GEMINI_MODEL}…")
            client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(
                    timeout=GEMINI_TIMEOUT_MS,
                    # 429 is deliberately not retried: waiting seconds will not refill a quota.
                    retry_options=types.HttpRetryOptions(
                        attempts=GEMINI_RETRY_ATTEMPTS, http_status_codes=[500, 502, 503, 504]
                    ),
                ),
            )
            result = notes_to_script(client, notes_text, notes_name, self.log_msg.emit)
            path = script_path_for(self.notes_path, self.scripts_folder)
            save_script(result.text, path)
            name = os.path.basename(path)
            if result.issues:
                message = f"✅ Script saved: {name} · {len(result.issues)} pre-flight issue(s) left, see CHECK column"
            else:
                message = f"✅ Script saved: {name} · pre-flight clean"
            self.done.emit(True, message, path)
        except Exception as e:
            message = describe_error(e)
            self.log_msg.emit(f"❌ {message}")
            self.done.emit(False, message, "")
